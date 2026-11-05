'use client';
import {useState} from 'react';
import {Badge, Confirm, DocPreview, Drawer, Empty, ErrorBox, ScoreRing, Spinner, STAGES, call, fmtDate, label, pl, send, toneOf, useApp, useLoad} from '../lib';

export type Cand = {id: string; name: string; role: string; requisition_id: string; requisition_title: string; rank: number; experience: number | null; skills: string[]; notice_days: number | null; score: number; stage: string; confidence: string; consent: string; resume_id?: string};

export default function Candidates({ver, setOpenId, go}: {ver: number; setOpenId: (id?: string) => void; go: (t: string) => void}) {
  const {auth} = useApp();
  const reqs = useLoad<any[]>(() => call(auth.token, '/api/requisitions'), []);
  const [req, setReq] = useState(''), [q, setQ] = useState(''), [stage, setStage] = useState('');
  const list = useLoad<Cand[]>(() => call(auth.token, '/api/candidates' + (req ? '?requisition_id=' + req : '')), [req, ver]);
  const all = list.data || [];
  const shown = all.filter(p => (!stage || p.stage === stage) && (!q || `${p.name} ${p.stage} ${p.role} ${p.skills.join(' ')}`.toLowerCase().includes(q.toLowerCase())));
  const stages = STAGES.filter(s => all.some(p => p.stage === s));
  return (
    <>
      <div className="toolbar">
        <label className="inline">Requisition<select value={req} onChange={e => { setReq(e.target.value); setStage(''); }}><option value="">All requisitions</option>{(reqs.data || []).map(x => <option key={x.id} value={x.id}>{x.title}</option>)}</select></label>
        <input className="search" aria-label="Search candidates" placeholder="Search name, skill or stage…" value={q} onChange={e => setQ(e.target.value)} />
        <button className="ghost" onClick={list.reload}>Refresh</button>
      </div>
      {stages.length > 1 && <div className="chips filters"><button className={'chip ' + (!stage ? 'on' : '')} onClick={() => setStage('')}>All · {all.length}</button>{stages.map(s => <button key={s} className={'chip ' + (stage === s ? 'on' : '')} onClick={() => setStage(stage === s ? '' : s)}>{s} · {all.filter(p => p.stage === s).length}</button>)}</div>}
      {list.loading && !list.data ? <Spinner /> : list.error ? <ErrorBox msg={list.error} retry={list.reload} /> : !all.length ? (
        <div className="state"><b>No candidates yet</b><span>Upload CVs to a requisition and the processed candidates are ranked here.</span><button onClick={() => go('Uploads')}>Go to uploads</button></div>
      ) : !shown.length ? <Empty title="No candidates match" hint="Low-scoring candidates are never hidden. Clear the search or filter to see everyone." /> : (
        <div className="table">
          {shown.map(p => (
            <button className="row cand" key={p.id} onClick={() => setOpenId(p.id)}>
              <span className="who"><ScoreRing score={p.score} /><span><b>{p.name}</b><small>#{p.rank} for {p.requisition_title} · {p.experience == null ? 'experience not stated' : p.experience + ' yrs'}</small></span></span>
              <span className="skills">{p.skills.slice(0, 4).map(x => <i key={x}>{x}</i>)}{!p.skills.length && <small>no skills detected</small>}</span>
              <span className="meta">{p.notice_days == null ? <small>notice unknown</small> : <>{p.notice_days}<small> days notice</small></>}</span>
              <span className="chips"><Badge>{p.stage}</Badge><Badge tone={toneOf(p.consent)}>Consent {p.consent.toLowerCase()}</Badge></span>
            </button>
          ))}
        </div>)}
      <small className="foot">{shown.length} of {pl(all.length, 'candidate')}. Scores are decision support; nobody is rejected automatically.</small>
    </>
  );
}

export function CandidateDrawer({id, onClose, onChange}: {id: string; onClose: () => void; onChange: () => void}) {
  const {auth, toast} = useApp();
  const {data: c, error, loading, reload} = useLoad<any>(() => call(auth.token, '/api/candidates/' + id), [id]);
  const hist = useLoad<any[]>(() => call(auth.token, `/api/candidates/${id}/audit`), [id]);
  const [tab, setTab] = useState('Evidence'), [ask, setAsk] = useState(false);
  const act = async (fn: () => Promise<any>, ok: string) => { try { await fn(); toast(ok); reload(); hist.reload(); onChange(); } catch (e: any) { toast(e.message, true); } };
  const setConsent = (s: string) => act(() => send(auth.token, `/api/candidates/${id}/consent`, 'PUT', {status: s}), 'Consent recorded.');

  // one clear next step, in the order the server enforces
  const next = !c ? null : c.submitted ? {text: `Submitted to ${c.client_org}. Their decision will appear under Client feedback.`, btn: null}
    : !c.cv_reviewed ? {text: 'Step 1 of 3: open the original CV. It must be reviewed before it can go to the client.', btn: <button onClick={() => setTab('Original CV')}>Open original CV</button>}
    : c.consent !== 'Granted' ? {text: 'Step 2 of 3: record that the candidate has consented to be shared.', btn: <button onClick={() => setConsent('Granted')}>Mark consent granted</button>}
    : {text: `Step 3 of 3: ready to share with ${c.client_org}.`, btn: <button onClick={() => act(() => send(auth.token, `/api/candidates/${id}/submit`, 'POST'), `Submitted to ${c.client_org}.`)}>Submit to {c.client_org}</button>};

  return (
    <Drawer title={c ? c.name : 'Candidate'} onClose={onClose}>
      {loading && !c ? <Spinner /> : error ? <ErrorBox msg={error} retry={reload} /> : c && <>
        <div className="dhead">
          <ScoreRing score={c.score} size={76} />
          <div><h2>{c.name}</h2><p className="muted">{c.requisition_title} · {c.client_org}</p><div className="chips"><Badge>{c.stage}</Badge><Badge tone={toneOf(c.consent)}>Consent {c.consent.toLowerCase()}</Badge><Badge tone={toneOf(c.confidence)}>Extraction {c.confidence.toLowerCase()}</Badge></div></div>
        </div>
        <dl className="facts">
          <div><dt>Experience</dt><dd>{c.experience == null ? 'Not stated' : c.experience + ' years'}</dd></div>
          <div><dt>Notice</dt><dd>{c.notice_days == null ? 'Not stated' : c.notice_days + ' days'}</dd></div>
          <div><dt>CTC</dt><dd>{c.ctc_lpa == null ? 'Not stated' : c.ctc_lpa + ' LPA'}</dd></div>
          <div><dt>Email</dt><dd>{c.email || 'Not found'}</dd></div>
          <div><dt>Phone</dt><dd>{c.phone || 'Not found'}</dd></div>
        </dl>
        {next && <div className="next"><span>{next.text}</span>{next.btn}</div>}
        <div className="chips tabs">{['Evidence', 'Original CV', 'Client feedback', 'Access history', 'Manage'].map(t => <button key={t} className={'chip ' + (tab === t ? 'on' : '')} onClick={() => setTab(t)}>{t}</button>)}</div>

        {tab === 'Evidence' && <>
          {Object.entries(c.evidence || {}).map(([k, v]: any) => (
            <div className="evidence" key={k}>
              <div className="toolbar"><b>{k}</b><span><Badge tone={toneOf(v.status)}>{label(v.status)}</Badge></span></div>
              <div className="pts"><span className="bar sm wide"><i style={{width: (v.weight ? (v.points / v.weight) * 100 : 0) + '%'}} /></span><small>{v.points} of {v.weight} points</small></div>
              {v.quote ? <blockquote>“{v.quote}”</blockquote> : <p className="muted">{v.status === 'unknown' ? 'The CV does not state this. It is treated as unknown, not as a failure.' : 'No supporting text found in the CV.'}</p>}
              <small>{v.source_document || 'CV'}{v.page ? ` · page ${v.page}` : ''}</small>
            </div>
          ))}
          <details><summary>Extracted CV text</summary><pre>{c.raw_text}</pre></details>
        </>}
        {tab === 'Original CV' && (c.resume_id ? <DocPreview id={c.resume_id} onLoaded={reload} /> : <Empty title="Original document not available" hint="No file is stored for this candidate." />)}
        {tab === 'Client feedback' && (!c.client_reviews.length ? <Empty title="No client feedback yet" /> : c.client_reviews.map((r: any, i: number) => (
          <div className="evidence" key={i}><b>{label(r.action)}</b> <small>{fmtDate(r.at + 'Z')}</small>{r.reason && <p>Reason: {r.reason}</p>}{r.slots && <ul>{r.slots.map((s: string) => <li key={s}>{fmtDate(s)}</li>)}</ul>}</div>)))}
        {tab === 'Access history' && (hist.loading && !hist.data ? <Spinner /> : !hist.data?.length ? <Empty title="No access recorded" /> : hist.data.map((a, i) => <small className="audit" key={i}>{fmtDate(a.at)} · <b>{label(a.action)}</b> · {a.actor}</small>))}
        {tab === 'Manage' && (
          <div className="stack">
            <div className="grid2">
              <label>Pipeline stage<select value={c.stage} onChange={e => act(() => send(auth.token, `/api/candidates/${id}/stage`, 'PATCH', {stage: e.target.value}), 'Stage updated.')}>{STAGES.map(s => <option key={s} disabled={s === 'Submitted to Client'}>{s}</option>)}</select></label>
              <label>Consent<select value={c.consent} onChange={e => setConsent(e.target.value)}>{['Pending', 'Granted', 'Withdrawn'].map(s => <option key={s}>{s}</option>)}</select></label>
            </div>
            <div className="actions">
              {c.submitted && <button className="ghost" onClick={() => act(() => send(auth.token, `/api/candidates/${id}/submit`, 'DELETE'), 'Withdrawn from client.')}>Withdraw from client</button>}
              {c.deletion_request ? <Badge tone="warn">Deletion requested. Complete it under Privacy.</Badge> : <button className="ghost danger" onClick={() => setAsk(true)}>Request deletion</button>}
            </div>
            <small>Withdrawing consent hides the candidate from the client immediately.</small>
          </div>)}
        {ask && <Confirm title="Request deletion?" text={`This records ${c.name}'s deletion request. Nothing is erased until you complete it under Privacy.`} confirmLabel="Record request" onConfirm={() => act(() => send(auth.token, `/api/candidates/${id}/deletion-request`, 'POST'), 'Deletion request recorded.')} onClose={() => setAsk(false)} />}
      </>}
    </Drawer>
  );
}
