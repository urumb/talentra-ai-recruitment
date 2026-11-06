import json, sys, types
from pathlib import Path
import pytest
from conftest import make_docx, make_pdf, wait_batch
from app import main

CARD = {"criteria": [{"label": "Skills", "type": "skills", "values": ["Python", "Django"], "weight": 70}, {"label": "Experience", "type": "experience", "min": 4, "weight": 30}]}


def cv(name, email, extra="Python Django developer. 6 years of experience.", phone=""):
    return make_docx(name, f"{email} {phone}", extra)


@pytest.fixture(scope='module')
def req(client, rec):
    r = client.post('/api/requisitions', headers=rec, json={'title': 'Python Dev', 'client': 'acme systems', 'description': 'Python role', 'scorecard': CARD})
    assert r.status_code == 200, r.text
    return r.json()['id']


def upload(client, rec, req, files):
    r = client.post(f'/api/requisitions/{req}/uploads', headers=rec, files=[('files', (n, b, t)) for n, b, t in files])
    assert r.status_code == 200, r.text
    return r.json()


def one(client, rec, req, name, blob):
    r = upload(client, rec, req, [(name, blob, 'application/octet-stream')])
    return wait_batch(client, rec, r['batch_id'])['files'][0]


# ---- auth & roles
def test_auth_required_and_bad_login(client):
    assert client.get('/api/candidates').status_code == 401
    assert client.get('/api/candidates', headers={'Authorization': 'Bearer junk'}).status_code == 401
    assert client.post('/api/auth/login', json={'email': 'recruiter@talentra.demo', 'password': 'nope'}).status_code == 401


def test_role_restrictions(client, rec, acme, head):
    assert client.get('/api/candidates', headers=acme).status_code == 403
    assert client.post('/api/requisitions/x/uploads', headers=acme, files=[('files', ('a.pdf', b'%PDF-', 'application/pdf'))]).status_code == 403
    assert client.get('/api/client/submissions', headers=rec).status_code == 403
    assert client.get('/api/candidates', headers=head).status_code == 403
    assert client.get('/api/fairness', headers=head).status_code == 200
    assert client.get('/api/fairness', headers=acme).status_code == 403
    assert client.get('/api/audit', headers=acme).status_code == 403


# ---- JD extraction (LLM mocked)
def test_jd_not_configured(client, rec, monkeypatch):
    monkeypatch.delenv('LLM_API_KEY', raising=False)
    r = client.post('/api/jd/extract', headers=rec, json={'description': 'x' * 40})
    assert r.status_code == 503 and 'not configured' in r.json()['detail']


def test_jd_extract_validates_and_normalizes(client, rec, monkeypatch):
    monkeypatch.setenv('LLM_API_KEY', 'k'); monkeypatch.setenv('LLM_MODEL', 'm')
    jd = {'description': 'Looking for a Go dev with 3 years'}
    monkeypatch.setattr(main, 'call_llm', lambda d: {'criteria': [{'label': 'Skills', 'type': 'skills', 'weight': 30, 'values': ['Go']}, {'label': 'Exp', 'type': 'experience', 'weight': 30, 'min': 3}]})
    r = client.post('/api/jd/extract', headers=rec, json=jd); assert r.status_code == 200
    j = r.json(); assert sum(c['weight'] for c in j['criteria']) == 100 and j['warnings']
    monkeypatch.setattr(main, 'call_llm', lambda d: {'criteria': [{'label': 'x', 'type': 'bogus', 'weight': 100}]})
    assert client.post('/api/jd/extract', headers=rec, json=jd).status_code == 502

    def boom(d): raise RuntimeError('network down')
    monkeypatch.setattr(main, 'call_llm', boom)
    r = client.post('/api/jd/extract', headers=rec, json=jd); assert r.status_code == 502 and 'network down' in r.json()['detail']


def test_scorecard_validation_and_unknown_client(client, rec):
    bad = {'criteria': [{'label': 'a', 'type': 'skills', 'weight': 50}]}
    assert client.post('/api/requisitions', headers=rec, json={'title': 't', 'client': 'Acme Systems', 'description': 'd', 'scorecard': bad}).status_code == 422
    assert client.post('/api/requisitions', headers=rec, json={'title': 't', 'client': 'Nobody Inc', 'description': 'd', 'scorecard': CARD}).status_code == 422


# ---- bulk upload
def test_bulk_upload_mixed_batch(client, rec, req):
    r = upload(client, rec, req, [
        ('good1.docx', cv('Alice Smith', 'alice@bulk.test'), ''),
        ('good2.pdf', make_pdf('Bob Jones', 'bob@bulk.test', 'Python Django engineer. 3 years of experience.'), ''),
        ('corrupt.pdf', b'%PDF-1.4 garbage that is not a pdf', ''),
        ('fake.docx', b'not a zip', ''),
        ('notes.txt', b'hello', ''),
        ('empty.pdf', b'', '')])
    assert r['accepted'] == 3 and r['rejected'] == 3
    b = wait_batch(client, rec, r['batch_id']); st = {f['filename']: f for f in b['files']}
    assert st['good1.docx']['status'] == 'completed' and st['good2.pdf']['status'] == 'completed'
    assert st['corrupt.pdf']['status'] == 'failed' and st['corrupt.pdf']['error']
    assert 'Unsupported' in st['notes.txt']['error']
    assert b['counts']['completed'] == 2 and b['counts']['failed'] == 4 and b['total'] == 6
    assert any(x['id'] == r['batch_id'] and x['total'] == 6 for x in client.get('/api/batches', headers=rec).json())


def test_scoring_evidence_on_uploaded_pdf(client, rec, req):
    f = one(client, rec, req, 'ev.pdf', make_pdf('Carl Dane', 'carl@ev.test', 'Skills: Python, Django', '5 years of experience'))
    assert f['status'] == 'completed'
    c = client.get(f"/api/candidates/{f['candidate_id']}", headers=rec).json()
    assert c['score'] == 100 and c['evidence']['Skills']['page'] == 1 and 'Python' in c['evidence']['Skills']['quote']
    assert c['evidence']['Experience']['quote'] and c['stage'] == 'Sourced'


def test_unknown_not_rejected(client, rec, req):
    f = one(client, rec, req, 'vague.docx', make_docx('Dana Lee', 'dana@vague.test', 'Enthusiastic engineer.'))
    c = client.get(f"/api/candidates/{f['candidate_id']}", headers=rec).json()
    assert c['score'] == 0 and c['stage'] == 'Sourced' and c['evidence']['Experience']['status'] == 'unknown' and c['experience'] is None


def test_retry_failed_document(client, rec, req, monkeypatch):
    calls = {'n': 0}; real = main.parse

    def flaky(p):
        calls['n'] += 1
        if calls['n'] == 1: raise ValueError('temporary parser failure')
        return real(p)
    monkeypatch.setattr(main, 'parse', flaky)
    r = upload(client, rec, req, [('flaky.docx', cv('Eve Fox', 'eve@retry.test'), '')])
    f = wait_batch(client, rec, r['batch_id'])['files'][0]; assert f['status'] == 'failed' and 'temporary' in f['error']
    assert client.post(f"/api/resumes/{f['id']}/retry", headers=rec).status_code == 200
    assert wait_batch(client, rec, r['batch_id'])['files'][0]['status'] == 'completed'
    assert client.post(f"/api/resumes/{f['id']}/retry", headers=rec).status_code == 404


def blank_pdf():
    import fitz
    doc = fitz.open(); doc.new_page(); return doc.tobytes()


def test_scanned_pdf_goes_through_ocr(client, rec, req, monkeypatch):
    monkeypatch.setattr(main, 'ocr_page', lambda page: 'Fiona Gray\nfiona@ocr.test\nPython Django 5 years of experience')
    monkeypatch.setitem(sys.modules, 'pytesseract', types.SimpleNamespace(get_tesseract_version=lambda: '5'))
    f = one(client, rec, req, 'scan.pdf', blank_pdf()); assert f['status'] == 'completed', f
    assert client.get(f"/api/candidates/{f['candidate_id']}", headers=rec).json()['email'] == 'fiona@ocr.test'


def test_scanned_pdf_without_tesseract_fails_clearly(client, rec, req, monkeypatch):
    def nope(): raise RuntimeError('tesseract is not installed')
    monkeypatch.setitem(sys.modules, 'pytesseract', types.SimpleNamespace(get_tesseract_version=nope))
    f = one(client, rec, req, 'scan2.pdf', blank_pdf()); assert f['status'] == 'failed' and 'Tesseract' in f['error']


# ---- duplicates
def test_duplicate_detection_and_resolution(client, rec, req):
    one(client, rec, req, 'orig.docx', cv('Gus Hall', 'gus@dup.test', phone='9811122233'))
    second = upload(client, rec, req, [('copy.docx', cv('Gus H', 'gus@dup.test'), ''), ('phone.docx', cv('G Hall', 'other@dup.test', phone='9811122233'), '')])
    b = wait_batch(client, rec, second['batch_id']); assert b['counts']['duplicate'] == 2 and b['counts']['completed'] == 0
    dups = {x['filename']: x for x in client.get('/api/duplicates', headers=rec).json()}
    assert dups['copy.docx']['reason'] == 'email' and dups['copy.docx']['existing']['name'] == 'Gus Hall'
    url = lambda n: f"/api/resumes/{dups[n]['resume_id']}/resolve-duplicate"
    assert client.post(url('copy.docx'), headers=rec, json={'action': 'keep_both'}).status_code == 409
    assert client.post(url('copy.docx'), headers=rec, json={'action': 'discard'}).status_code == 200
    assert client.post(url('phone.docx'), headers=rec, json={'action': 'keep_both'}).status_code == 200
    b = wait_batch(client, rec, second['batch_id']); assert b['counts']['completed'] == 1 and b['counts']['resolved_duplicate'] == 1
    assert not [x for x in client.get('/api/duplicates', headers=rec).json() if x['filename'] in dups]


# ---- documents
def test_document_access_requires_recruiter(client, rec, acme, req):
    f = one(client, rec, req, 'prev.pdf', make_pdf('Hal Ito', 'hal@doc.test', 'Python 5 years of experience'))
    cand = client.get(f"/api/candidates/{f['candidate_id']}", headers=rec).json(); url = f"/api/documents/{cand['resume_id']}"
    assert client.get(url).status_code == 401 and client.get(url, headers=acme).status_code == 403
    ok = client.get(url, headers=rec); assert ok.status_code == 200 and ok.content.startswith(b'%PDF') and 'inline' in ok.headers['content-disposition']
    actions = [a['action'] for a in client.get(f"/api/candidates/{cand['id']}/audit", headers=rec).json()]
    assert 'document_preview' in actions and 'candidate_view' in actions


# ---- client portal, isolation, persistence
def make_candidate(client, rec, req, tag):
    return one(client, rec, req, f'{tag}.docx', cv('Ivy Moss', f'{tag}@cl.test', extra='Python Django. 6 years of experience. Contact ivy@secret.test'))['candidate_id']


def review(client, rec, cid):
    """Open the original CV, as a recruiter must before submitting."""
    rid = client.get(f'/api/candidates/{cid}', headers=rec).json()['resume_id']
    assert client.get(f'/api/documents/{rid}', headers=rec).status_code == 200


def ids(client, who):
    return [x['id'] for x in client.get('/api/client/submissions', headers=who).json()]


def test_submit_requires_consent_then_client_flow(client, rec, acme, globex, req):
    cid = make_candidate(client, rec, req, 'flow')
    assert client.post(f'/api/candidates/{cid}/submit', headers=rec).status_code == 409
    assert client.put(f'/api/candidates/{cid}/consent', headers=rec, json={'status': 'Granted'}).status_code == 200
    r = client.post(f'/api/candidates/{cid}/submit', headers=rec); assert r.status_code == 409 and 'Open the original CV' in r.json()['detail']
    assert client.get(f'/api/candidates/{cid}', headers=rec).json()['cv_reviewed'] is False
    review(client, rec, cid)
    assert client.get(f'/api/candidates/{cid}', headers=rec).json()['cv_reviewed'] is True
    assert client.post(f'/api/candidates/{cid}/submit', headers=rec).status_code == 200
    assert cid in ids(client, acme) and cid not in ids(client, globex)
    assert client.post(f'/api/client/submissions/{cid}/shortlist', headers=globex, json={}).status_code == 404
    view = next(x for x in client.get('/api/client/submissions', headers=acme).json() if x['id'] == cid)
    blob = json.dumps(view)
    assert 'Ivy' not in blob and 'flow@cl.test' not in blob and 'ivy@secret.test' not in blob and view['name'].startswith('Candidate ')
    assert client.post(f'/api/client/submissions/{cid}/reject', headers=acme, json={'reason': '  '}).status_code == 422
    assert client.post(f'/api/client/submissions/{cid}/interview', headers=acme, json={'slots': []}).status_code == 422
    assert client.post(f'/api/client/submissions/{cid}/interview', headers=acme, json={'slots': ['soon']}).status_code == 422
    assert client.post(f'/api/client/submissions/{cid}/shortlist', headers=acme, json={}).status_code == 200
    assert client.get(f'/api/candidates/{cid}', headers=rec).json()['stage'] == 'Shortlisted'
    assert client.post(f'/api/client/submissions/{cid}/interview', headers=acme, json={'slots': ['2030-01-10T10:00', '2030-01-11T15:30']}).status_code == 200
    assert client.post(f'/api/client/submissions/{cid}/reject', headers=acme, json={'reason': 'Salary mismatch'}).status_code == 200
    d = client.get(f'/api/candidates/{cid}', headers=rec).json(); assert d['stage'] == 'Rejected by Client'
    assert [r['action'] for r in d['client_reviews']] == ['reject', 'interview', 'shortlist']
    assert d['client_reviews'][0]['reason'] == 'Salary mismatch' and d['client_reviews'][1]['slots']
    assert next(x for x in client.get('/api/client/submissions', headers=acme).json() if x['id'] == cid)['my_review']['action'] == 'reject'
    assert 'client_reject' in [a['action'] for a in client.get(f'/api/candidates/{cid}/audit', headers=rec).json()]


def test_unsubmitted_hidden_withdraw_and_consent_withdrawal(client, rec, acme, req):
    cid = make_candidate(client, rec, req, 'hidden')
    assert cid not in ids(client, acme)
    assert client.post(f'/api/client/submissions/{cid}/shortlist', headers=acme, json={}).status_code == 404
    client.put(f'/api/candidates/{cid}/consent', headers=rec, json={'status': 'Granted'}); review(client, rec, cid); assert client.post(f'/api/candidates/{cid}/submit', headers=rec).status_code == 200
    assert cid in ids(client, acme)
    client.put(f'/api/candidates/{cid}/consent', headers=rec, json={'status': 'Withdrawn'})
    assert cid not in ids(client, acme)
    client.put(f'/api/candidates/{cid}/consent', headers=rec, json={'status': 'Granted'})
    assert client.delete(f'/api/candidates/{cid}/submit', headers=rec).status_code == 200
    assert cid not in ids(client, acme)


def test_stage_validation(client, rec, req):
    cid = make_candidate(client, rec, req, 'stage')
    assert client.patch(f'/api/candidates/{cid}/stage', headers=rec, json={'stage': 'Bogus'}).status_code == 422
    assert client.patch(f'/api/candidates/{cid}/stage', headers=rec, json={'stage': 'Submitted to Client'}).status_code == 422
    assert client.patch(f'/api/candidates/{cid}/stage', headers=rec, json={'stage': 'Offered'}).status_code == 200
    assert client.patch('/api/candidates/none/stage', headers=rec, json={'stage': 'Offered'}).status_code == 404


# ---- deletion
def test_deletion_workflow_removes_data_and_files(client, rec, acme, req):
    f = one(client, rec, req, 'del.docx', cv('Jo Ng', 'jo@del.test')); cid = f['candidate_id']
    rid = client.get(f'/api/candidates/{cid}', headers=rec).json()['resume_id']; folder = Path(main.UPLOADS); before = len(list(folder.iterdir()))
    client.put(f'/api/candidates/{cid}/consent', headers=rec, json={'status': 'Granted'}); review(client, rec, cid); client.post(f'/api/candidates/{cid}/submit', headers=rec)
    q = client.post(f'/api/candidates/{cid}/deletion-request', headers=rec).json()
    assert client.post(f'/api/candidates/{cid}/deletion-request', headers=rec).json()['id'] == q['id']
    assert any(x['id'] == q['id'] and x['status'] == 'Requested' for x in client.get('/api/deletion-requests', headers=rec).json())
    assert client.post(f"/api/deletion-requests/{q['id']}/complete", headers=rec).status_code == 200
    assert len(list(folder.iterdir())) == before - 1
    assert client.get(f'/api/candidates/{cid}', headers=rec).status_code == 404
    assert client.get(f'/api/documents/{rid}', headers=rec).status_code == 404
    assert cid not in [x['id'] for x in client.get('/api/candidates', headers=rec).json()] and cid not in ids(client, acme)
    assert next(x for x in client.get('/api/deletion-requests', headers=rec).json() if x['id'] == q['id'])['status'] == 'Completed'
    assert 'secure_delete' in [a['action'] for a in client.get(f'/api/candidates/{cid}/audit', headers=rec).json()]
    assert client.post(f"/api/deletion-requests/{q['id']}/complete", headers=rec).status_code == 404


def test_deletion_decline(client, rec, req):
    cid = make_candidate(client, rec, req, 'decline'); q = client.post(f'/api/candidates/{cid}/deletion-request', headers=rec).json()
    assert client.post(f"/api/deletion-requests/{q['id']}/decline", headers=rec).status_code == 200
    assert client.get(f'/api/candidates/{cid}', headers=rec).status_code == 200


# ---- scorecard re-scoring + monitoring
def test_scorecard_update_rescores(client, rec, req):
    cid = make_candidate(client, rec, req, 'rescore'); before = client.get(f'/api/candidates/{cid}', headers=rec).json()['score']
    r = client.put(f'/api/requisitions/{req}/scorecard', headers=rec, json={'criteria': [{'label': 'Skills', 'type': 'skills', 'values': ['Rust'], 'weight': 100}]})
    assert r.status_code == 200 and r.json()['rescored'] > 0
    assert before > 0 and client.get(f'/api/candidates/{cid}', headers=rec).json()['score'] == 0
    assert client.put(f'/api/requisitions/{req}/scorecard', headers=rec, json=CARD).status_code == 200
    assert client.get(f'/api/candidates/{cid}', headers=rec).json()['score'] == before
    assert client.put(f'/api/requisitions/{req}/scorecard', headers=rec, json={'criteria': [{'label': 'a', 'type': 'skills', 'weight': 10}]}).status_code == 422


def test_fairness_report(client, rec, head, req):
    f = client.get('/api/fairness', headers=head).json()
    assert f['sample_size'] > 0 and f['weeks'] and 'not prove' in f['note'] and f['recruiter_selected'] > 0
    w = f['weeks'][0]; assert w['sample_size'] >= w['selected'] and w['requisitions']
    for r in w['requisitions']:
        assert [c['ai_rank'] for c in r['candidates']] == list(range(1, r['sample_size'] + 1))
        assert all(c['ref'].startswith('C-') for c in r['candidates'])
    assert 'Ritika' not in json.dumps(f) and 'Pooja' not in json.dumps(f)


def test_dashboard_and_audit(client, rec):
    d = client.get('/api/dashboard', headers=rec).json(); assert d['candidates_processed'] > 0 and 'documents_failed' in d
    a = client.get('/api/audit', headers=rec).json(); assert a and {'actor', 'action', 'at'} <= set(a[0])


def test_upload_limits(client, rec, req):
    assert client.post(f'/api/requisitions/{req}/uploads', headers=rec, files=[]).status_code in (400, 422)
    assert client.post('/api/requisitions/missing/uploads', headers=rec, files=[('files', ('a.pdf', b'%PDF-', ''))]).status_code == 404


# ---- brief sample data, CTC, pipeline stage
def test_brief_sample_data_is_seeded_and_scored_from_real_cvs(client, rec):
    people = {c['id']: c for c in client.get('/api/candidates', headers=rec).json()}
    assert people['CND-91022']['name'] == 'Ritika Bansal' and people['CND-91047']['name'] == 'Arjun Rawat' and people['CND-91088']['name'] == 'Pooja Nair'
    assert people['CND-91022']['score'] > people['CND-91088']['score'] and people['CND-91088']['score'] > 0  # lower scorers stay listed
    assert people['CND-91088']['notice_days'] == 90 and people['CND-91022']['resume_id']
    pooja = client.get('/api/candidates/CND-91088', headers=rec).json()['evidence']
    assert pooja['Notice up to 60 days']['status'] == 'not_met' and 'Notice period: 90' in pooja['Notice up to 60 days']['quote']


def test_ctc_criterion_and_unknown(client, rec, req):
    from app.main import score, find_ctc
    assert find_ctc('Current CTC: 12 LPA. Expected CTC: 18.5 lakhs')[0] == 18.5 and find_ctc('no money info')[0] is None
    card = {'criteria': [{'label': 'CTC', 'type': 'ctc', 'max': 20, 'weight': 100}]}
    assert score({'raw_text': 'Expected CTC: 18 LPA'}, card)[0] == 100 and score({'raw_text': 'Expected CTC: 25 LPA'}, card)[0] == 0
    assert score({'raw_text': 'nothing here'}, card)[1]['CTC']['status'] == 'unknown'
    assert client.put(f'/api/requisitions/{req}/scorecard', headers=rec, json={'criteria': [{'label': 'CTC', 'type': 'ctc', 'max': 20.5, 'weight': 100}]}).status_code == 200
    assert client.put(f'/api/requisitions/{req}/scorecard', headers=rec, json=CARD).status_code == 200


def test_candidates_start_as_sourced_and_client_refs_are_unique(client, rec, acme):
    assert client.get('/api/candidates/CND-91088', headers=rec).json()['stage'] == 'Sourced'
    refs = [x['name'] for x in client.get('/api/client/submissions', headers=acme).json()]
    assert len(refs) == len(set(refs))


def test_jd_status_health_and_dotenv(client, rec, monkeypatch, tmp_path):
    monkeypatch.delenv('LLM_API_KEY', raising=False)
    assert client.get('/api/jd/status', headers=rec).json() == {'configured': False}
    monkeypatch.setenv('LLM_API_KEY', 'k'); monkeypatch.setenv('LLM_MODEL', 'm')
    assert client.get('/api/jd/status', headers=rec).json() == {'configured': True}
    assert client.get('/api/jd/status').status_code == 401 and client.get('/api/health').json()['status'] == 'ok'
    # .env loader: values load, comments are stripped, real environment wins
    env = tmp_path / '.env'; env.write_text('ZZ_NEW=abc  # note\nZZ_KEEP=fromfile\n# c\nZZ_QUOTED="q v"\n', encoding='utf-8')
    monkeypatch.setenv('ZZ_KEEP', 'real'); monkeypatch.delenv('TALENTRA_NO_DOTENV', raising=False); monkeypatch.delenv('ZZ_NEW', raising=False); monkeypatch.delenv('ZZ_QUOTED', raising=False)
    main.load_dotenv([env])
    import os
    assert os.environ['ZZ_NEW'] == 'abc' and os.environ['ZZ_KEEP'] == 'real' and os.environ['ZZ_QUOTED'] == 'q v'


def test_demo_flag_only_with_documented_password(client, monkeypatch):
    monkeypatch.delenv('DEMO_PASSWORD', raising=False); monkeypatch.setenv('SEED_DEMO', '1')
    assert client.get('/api/health').json()['demo'] is True
    monkeypatch.setenv('DEMO_PASSWORD', 'DemoPass123!'); assert client.get('/api/health').json()['demo'] is True  # compose always sets it
    monkeypatch.setenv('DEMO_PASSWORD', 'something-else'); assert client.get('/api/health').json()['demo'] is False
    monkeypatch.setenv('DEMO_PASSWORD', 'DemoPass123!'); monkeypatch.setenv('SEED_DEMO', '0'); assert client.get('/api/health').json()['demo'] is False
