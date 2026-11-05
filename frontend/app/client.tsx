'use client';
import {useState} from 'react';
import {Badge, Empty, ErrorBox, Modal, Spinner, call, fmtDate, label, send, toneOf, useApp, useLoad} from './lib';

type Item = {id: string; name: string; role: string; experience: number | null; skills: string[]; notice_days: number | null; score: number; stage: string; evidence: Record<string, any>; my_review: null | {action: string; reason?: string; slots?: string[]; at: string}};

export default function ClientPortal({out}: {out: () => void}) {
  const {auth, toast} = useApp();
  const {data, error, loading, reload} = useLoad<Item[]>(() => call(auth.token, '/api/client/submissions'), []);
  const [dlg, setDlg] = useState<{item: Item; kind: 'reject' | 'interview'}>();
  const [reason, setReason] = useState(''), [slots, setSlots] = useState<string[]>(['']), [busy, setBusy] = useState(false), [formErr, setFormErr] = useState('');

  async function act(item: Item, action: string, body: any = {}) {
    setBusy(true); setFormErr('');
    try {
      await send(auth.token, `/api/client/submissions/${item.id}/${action}`, 'POST', body);
      toast(action === 'shortlist' ? 'Candidate shortlisted.' : action === 'reject' ? 'Candidate rejected. Your reason was saved.' : 'Interview slots sent to the recruiter.');
      setDlg(undefined); setReason(''); setSlots(['']); reload();
    } catch (e: any) { if (dlg) setFormErr(e.message); else toast(e.message, true); } finally { setBusy(false); }
  }

  return (
    <main className="client">
      <header className="top"><div><p className="eyebrow">CLIENT PORTAL · {auth.org}</p><h1>Your submitted candidates</h1></div><button onClick={out}>Sign out</button></header>
      <p className="muted">You only see candidates your recruiter has explicitly submitted to {auth.org}, with identity and contact details withheld until an interview is arranged. Scores are decision support; the decision is yours.</p>
      {loading && !data ? <Spinner /> : error ? <ErrorBox msg={error} retry={reload} /> : !data?.length ? <Empty title="No candidates have been submitted yet" hint="Your recruiter will share profiles here when they are ready for review." /> :
        data.map(c => (
          <article className="card-client" key={c.id}>
            <div className="toolbar"><h2>{c.name}</h2><span className="score sm"><b>{c.score}</b>/100</span></div>
            <p>{c.role} · {c.experience == null ? 'experience not stated' : c.experience + ' years'} · {c.notice_days == null ? 'notice period not stated' : c.notice_days + ' days notice'}</p>
            <p className="chips">{c.skills.map(s => <Badge key={s} tone="info">{s}</Badge>)}<Badge>{c.stage}</Badge></p>
            <details><summary>Why this score</summary>
              {Object.entries(c.evidence).map(([k, v]: any) => <div className="evidence" key={k}><div className="toolbar"><b>{k}</b><span><Badge tone={toneOf(v.status)}>{label(v.status)}</Badge> <small>{v.points}/{v.weight}</small></span></div>{v.quote ? <blockquote>“{v.quote}”</blockquote> : <p className="muted">Not stated in the CV.</p>}</div>)}
            </details>
            {c.my_review && <p className="hint">Your last action: <b>{label(c.my_review.action)}</b> on {fmtDate(c.my_review.at)}{c.my_review.reason ? ` — ${c.my_review.reason}` : ''}{c.my_review.slots ? ` — ${c.my_review.slots.map(fmtDate).join(', ')}` : ''}</p>}
            <div className="actions">
              <button disabled={busy || c.stage === 'Shortlisted'} onClick={() => act(c, 'shortlist')}>{c.stage === 'Shortlisted' ? 'Shortlisted ✓' : 'Shortlist'}</button>
              <button className="ghost" onClick={() => { setFormErr(''); setDlg({item: c, kind: 'interview'}); }}>Propose interview</button>
              <button className="ghost danger" onClick={() => { setFormErr(''); setDlg({item: c, kind: 'reject'}); }}>Reject…</button>
            </div>
          </article>))}

      {dlg?.kind === 'reject' && <Modal title={`Reject ${dlg.item.name}`} onClose={() => setDlg(undefined)}>
        <label>Reason (required, shared with the recruiter)<textarea autoFocus value={reason} onChange={e => setReason(e.target.value)} maxLength={1000} /></label>
        {formErr && <p className="error" role="alert">{formErr}</p>}
        <button className="danger" disabled={busy || !reason.trim()} onClick={() => act(dlg.item, 'reject', {reason})}>Confirm rejection</button>
      </Modal>}
      {dlg?.kind === 'interview' && <Modal title={`Propose interview slots · ${dlg.item.name}`} onClose={() => setDlg(undefined)}>
        {slots.map((s, i) => <label key={i}>Slot {i + 1}<input type="datetime-local" value={s} onChange={e => setSlots(slots.map((x, n) => n === i ? e.target.value : x))} /></label>)}
        {slots.length < 5 && <button className="ghost" onClick={() => setSlots([...slots, ''])}>Add another slot</button>}
        {formErr && <p className="error" role="alert">{formErr}</p>}
        <button disabled={busy || !slots.some(Boolean)} onClick={() => act(dlg.item, 'interview', {slots: slots.filter(Boolean)})}>Send proposed slots</button>
      </Modal>}
    </main>
  );
}
