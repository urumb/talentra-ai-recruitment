'use client';
import {useState} from 'react';
import {Badge, Empty, ErrorBox, Icon, Modal, ScoreRing, Spinner, call, fmtDate, label, pl, send, toneOf, useApp, useLoad} from './lib';

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
  const close = () => { setDlg(undefined); setFormErr(''); };
  const count = (s: string) => (data || []).filter(c => c.stage === s).length;
  const undecided = (data || []).filter(c => c.stage === 'Submitted to Client').length;

  return (
    <main className="client">
      <header className="top"><div><p className="eyebrow">CLIENT PORTAL · {auth.org}</p><h1>Candidates for your review</h1><p className="sub">Names and contact details are withheld. The decision is yours; scores are decision support.</p></div><button className="ghost" onClick={out}><Icon name="out" />Sign out</button></header>
      {data && data.length > 0 && <div className="metrics three"><div className="kpi static"><span>Awaiting your decision</span><b>{undecided}</b></div><div className="kpi static"><span>Shortlisted</span><b>{count('Shortlisted')}</b></div><div className="kpi static"><span>Interviews proposed</span><b>{count('Interview proposed')}</b></div></div>}
      {loading && !data ? <Spinner /> : error ? <ErrorBox msg={error} retry={reload} /> : !data?.length ? <Empty title="No candidates have been submitted yet" hint="Your recruiter will share profiles here when they are ready for review." /> :
        data.map(c => (
          <article className="card-client" key={c.id}>
            <div className="chead">
              <ScoreRing score={c.score} size={64} />
              <div><h2>{c.name}</h2><p className="muted">{c.role} · {c.experience == null ? 'experience not stated' : c.experience + ' years'} · {c.notice_days == null ? 'notice not stated' : c.notice_days + ' days notice'}</p></div>
              <Badge tone={c.stage === 'Shortlisted' ? 'good' : c.stage.startsWith('Rejected') ? 'bad' : 'info'}>{c.stage === 'Submitted to Client' ? 'Needs your decision' : c.stage}</Badge>
            </div>
            <p className="chips">{c.skills.map(s => <Badge key={s} tone="info">{s}</Badge>)}</p>
            <details><summary>Why this score</summary>
              {Object.entries(c.evidence).map(([k, v]: any) => (
                <div className="evidence" key={k}>
                  <div className="toolbar"><b>{k}</b><Badge tone={toneOf(v.status)}>{label(v.status)}</Badge></div>
                  <div className="pts"><span className="bar sm wide"><i style={{width: (v.weight ? (v.points / v.weight) * 100 : 0) + '%'}} /></span><small>{v.points} of {v.weight} points</small></div>
                  {v.quote ? <blockquote>“{v.quote}”</blockquote> : <p className="muted">Not stated in the CV.</p>}
                </div>))}
            </details>
            {c.my_review && <p className="hint">Your last action: <b>{label(c.my_review.action)}</b> on {fmtDate(c.my_review.at)}{c.my_review.reason ? `. Reason: ${c.my_review.reason}` : ''}{c.my_review.slots ? `. Slots: ${c.my_review.slots.map(fmtDate).join(', ')}` : ''}</p>}
            <div className="actions">
              <button disabled={busy || c.stage === 'Shortlisted'} onClick={() => act(c, 'shortlist')}>{c.stage === 'Shortlisted' ? 'Shortlisted' : 'Shortlist'}</button>
              <button className="ghost" onClick={() => { setFormErr(''); setDlg({item: c, kind: 'interview'}); }}>Propose interview</button>
              <button className="ghost danger" onClick={() => { setFormErr(''); setDlg({item: c, kind: 'reject'}); }}>Reject</button>
            </div>
          </article>))}
      <small className="foot">{data?.length ? `${pl(data.length, 'candidate')} shared with ${auth.org}.` : ''}</small>

      {dlg?.kind === 'reject' && <Modal title={`Reject ${dlg.item.name}`} onClose={close}>
        <label>Reason (required, shared with the recruiter)<textarea autoFocus value={reason} onChange={e => setReason(e.target.value)} maxLength={1000} placeholder="For example: salary expectation above budget" /></label>
        {formErr && <p className="error" role="alert">{formErr}</p>}
        <div className="actions end"><button className="ghost" onClick={close}>Cancel</button><button className="danger" disabled={busy || !reason.trim()} onClick={() => act(dlg.item, 'reject', {reason})}>Confirm rejection</button></div>
      </Modal>}
      {dlg?.kind === 'interview' && <Modal title={`Propose interview slots · ${dlg.item.name}`} onClose={close}>
        <p className="muted">Offer up to five date-times. The recruiter will arrange the interview.</p>
        {slots.map((s, i) => <label key={i}>Slot {i + 1}<input type="datetime-local" value={s} onChange={e => setSlots(slots.map((x, n) => n === i ? e.target.value : x))} /></label>)}
        {slots.length < 5 && <button className="ghost" onClick={() => setSlots([...slots, ''])}>Add another slot</button>}
        {formErr && <p className="error" role="alert">{formErr}</p>}
        <div className="actions end"><button className="ghost" onClick={close}>Cancel</button><button disabled={busy || !slots.some(Boolean)} onClick={() => act(dlg.item, 'interview', {slots: slots.filter(Boolean)})}>Send proposed slots</button></div>
      </Modal>}
    </main>
  );
}
