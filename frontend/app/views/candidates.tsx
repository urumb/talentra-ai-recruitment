'use client';
import {useState} from 'react';
import {Badge, DocPreview, Empty, ErrorBox, Modal, Spinner, STAGES, call, fmtDate, label, send, toneOf, useApp, useLoad} from '../lib';

export type Cand = {id: string; name: string; role: string; requisition_id: string; requisition_title: string; rank: number; experience: number | null; skills: string[]; notice_days: number | null; score: number; stage: string; confidence: string; consent: string; resume_id?: string};

export default function Candidates({ver, setOpenId}: {ver: number; setOpenId: (id?: string) => void}) {
  const {auth} = useApp();
  const reqs = useLoad<any[]>(() => call(auth.token, '/api/requisitions'), []);
  const [req, setReq] = useState(''), [q, setQ] = useState('');
  const list = useLoad<Cand[]>(() => call(auth.token, '/api/candidates' + (req ? '?requisition_id=' + req : '')), [req, ver]);
  const shown = (list.data || []).filter(p => !q || `${p.name} ${p.stage} ${p.role} ${p.skills.join(' ')}`.toLowerCase().includes(q.toLowerCase()));
  return (
    <>
      <div className="toolbar">
        <label className="inline">Requisition<select value={req} onChange={e => setReq(e.target.value)}><option value="">All requisitions</option>{(reqs.data || []).map(x => <option key={x.id} value={x.id}>{x.title}</option>)}</select></label>
        <input className="search" aria-label="Search candidates" placeholder="Search name, skill or stage…" value={q} onChange={e => setQ(e.target.value)} />
        <span>{list.data ? `${shown.length} of ${list.data.length} candidate${list.data.length === 1 ? '' : 's'}` : ''}</span>
        <button className="ghost" onClick={list.reload}>Refresh</button>
      </div>
      {list.loading && !list.data ? <Spinner /> : list.error ? <ErrorBox msg={list.error} retry={list.reload} /> : !list.data?.length ? <Empty title="No candidates yet" hint="Upload CVs to a requisition and processed candidates are ranked here." /> : !shown.length ? <Empty title="No candidates match your search" hint="Low-scoring candidates are never hidden; clear the search to see everyone." /> :
        <div className="table">
          <div className="row head"><span>Rank in requisition · Candidate</span><span>Top skills</span><span>Notice</span><span>Score</span><span>Stage</span></div>
          {shown.map(p => (
            <button className="row" key={p.id} onClick={() => setOpenId(p.id)}>
              <span><b><i className="rank">{p.rank}</i>{p.name}</b><small>{p.requisition_title} · {p.experience == null ? 'experience unknown' : p.experience + ' yrs'}</small></span>
              <span className="skills">{p.skills.slice(0, 3).map(x => <i key={x}>{x}</i>)}{!p.skills.length && <small>none detected</small>}</span>
              <span>{p.notice_days == null ? <small>unknown</small> : p.notice_days + 'd'}</span>
              <strong>{p.score}<small>/100</small></strong>
              <span className="chips"><Badge>{p.stage}</Badge><Badge tone={toneOf(p.consent)}>{p.consent}</Badge></span>
            </button>
          ))}
        </div>}
    </>
  );
}

export function CandidateDrawer({id, onClose, onChange}: {id: string; onClose: () => void; onChange: () => void}) {
  const {auth, toast} = useApp();
  const {data: c, error, loading, reload} = useLoad<any>(() => call(auth.token, '/api/candidates/' + id), [id]);
  const hist = useLoad<any[]>(() => call(auth.token, `/api/candidates/${id}/audit`), [id]);
  const [tab, setTab] = useState('Evidence');
  const act = async (fn: () => Promise<any>, ok: string) => { try { await fn(); toast(ok); reload(); hist.reload(); onChange(); } catch (e: any) { toast(e.message, true); } };
  return (
    <Modal title={c ? c.name : 'Candidate'} onClose={onClose}>
      {loading && !c ? <Spinner /> : error ? <ErrorBox msg={error} retry={reload} /> : c && <>
        <p className="eyebrow">{c.requisition_title} · {c.client_org}</p>
        <p>{c.email || <i>email not found in CV</i>} · {c.phone || <i>phone not found</i>}<br />{c.experience == null ? 'Experience not stated' : c.experience + ' years'} · {c.notice_days == null ? 'notice period not stated' : c.notice_days + ' days notice'} · {c.ctc_lpa == null ? 'CTC not stated' : c.ctc_lpa + ' LPA CTC'} · extraction confidence <Badge tone={toneOf(c.confidence)}>{c.confidence}</Badge></p>
        <div className="score"><b>{c.score}</b><span>/ 100 match<br /><small>Decision support only</small></span></div>
        <div className="grid3">
          <label>Stage<select value={c.stage} onChange={e => act(() => send(auth.token, `/api/candidates/${id}/stage`, 'PATCH', {stage: e.target.value}), 'Stage updated.')}>{STAGES.filter(s => s !== 'Submitted to Client' || c.stage === s).map(s => <option key={s} disabled={s === 'Submitted to Client'}>{s}</option>)}</select></label>
          <label>Consent<select value={c.consent} onChange={e => act(() => send(auth.token, `/api/candidates/${id}/consent`, 'PUT', {status: e.target.value}), 'Consent recorded.')}>{['Pending', 'Granted', 'Withdrawn'].map(s => <option key={s}>{s}</option>)}</select></label>
        </div>
        <div className="actions">
          {!c.submitted ? <button disabled={c.consent !== 'Granted' || !c.cv_reviewed} title={c.consent !== 'Granted' ? 'Consent must be Granted before sharing with a client' : !c.cv_reviewed ? 'Open the original CV first' : ''} onClick={() => act(() => send(auth.token, `/api/candidates/${id}/submit`, 'POST'), `Submitted to ${c.client_org}.`)}>Submit to {c.client_org}</button>
            : <button className="ghost" onClick={() => act(() => send(auth.token, `/api/candidates/${id}/submit`, 'DELETE'), 'Withdrawn from client.')}>Withdraw from client</button>}
          {c.deletion_request ? <Badge tone="warn">Deletion requested</Badge> : <button className="ghost danger" onClick={() => act(() => send(auth.token, `/api/candidates/${id}/deletion-request`, 'POST'), 'Deletion request recorded. Complete it under Privacy.')}>Request deletion</button>}
        </div>
        {!c.submitted && (c.consent !== 'Granted' || !c.cv_reviewed) && <small>To submit: {[c.consent !== 'Granted' && 'record the candidate\'s consent', !c.cv_reviewed && 'open the original CV (Original CV tab)'].filter(Boolean).join(' and ')}.</small>}
        <div className="chips tabs">{['Evidence', 'Original CV', 'Client feedback', 'Access history'].map(t => <button key={t} className={'chip ' + (tab === t ? 'on' : '')} onClick={() => setTab(t)}>{t}</button>)}</div>

        {tab === 'Evidence' && <>
          {Object.entries(c.evidence || {}).map(([k, v]: any) => (
            <div className="evidence" key={k}>
              <div className="toolbar"><b>{k}</b><span><Badge tone={toneOf(v.status)}>{label(v.status)}</Badge> <small>{v.points}/{v.weight} pts</small></span></div>
              {v.quote ? <blockquote>“{v.quote}”</blockquote> : <p className="muted">{v.status === 'unknown' ? 'The CV does not state this. Treated as unknown, not as a failure.' : 'No supporting text found in the CV.'}</p>}
              <small>{v.source_document || 'CV'}{v.page ? ` · page ${v.page}` : ''} · confidence {v.confidence}</small>
            </div>
          ))}
          <details><summary>Extracted CV text</summary><pre>{c.raw_text}</pre></details>
        </>}
        {tab === 'Original CV' && (c.resume_id ? <DocPreview id={c.resume_id} onLoaded={reload} /> : <Empty title="Original document not available" hint="Seeded demo candidates have no uploaded file." />)}
        {tab === 'Client feedback' && (!c.client_reviews.length ? <Empty title="No client feedback yet" /> : c.client_reviews.map((r: any, i: number) => (
          <div className="evidence" key={i}><b>{label(r.action)}</b> <small>{fmtDate(r.at + 'Z')}</small>{r.reason && <p>Reason: {r.reason}</p>}{r.slots && <ul>{r.slots.map((s: string) => <li key={s}>{fmtDate(s)}</li>)}</ul>}</div>)))}
        {tab === 'Access history' && (hist.loading && !hist.data ? <Spinner /> : !hist.data?.length ? <Empty title="No access recorded" /> : hist.data.map((a, i) => <small className="audit" key={i}>{fmtDate(a.at)} · <b>{label(a.action)}</b> · {a.actor}</small>))}
      </>}
    </Modal>
  );
}
