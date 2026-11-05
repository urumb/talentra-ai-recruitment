'use client';
import {useState} from 'react';
import {Badge, Empty, ErrorBox, Spinner, call, fmtDate, label, send, useApp, useLoad} from '../lib';
import type {Cand} from './candidates';

export default function Privacy() {
  const {auth, toast} = useApp();
  const people = useLoad<Cand[]>(() => call(auth.token, '/api/candidates'), []);
  const reqs = useLoad<any[]>(() => call(auth.token, '/api/deletion-requests'), []);
  const log = useLoad<any[]>(() => call(auth.token, '/api/audit'), []);
  const [q, setQ] = useState('');
  const act = async (fn: () => Promise<any>, ok: string) => { try { await fn(); toast(ok); people.reload(); reqs.reload(); log.reload(); } catch (e: any) { toast(e.message, true); } };
  const name = (id: string) => people.data?.find(p => p.id === id)?.name;
  const rows = (log.data || []).filter(a => !q || `${a.action} ${a.actor} ${a.target} ${name(a.target) || ''}`.toLowerCase().includes(q.toLowerCase()));
  return (
    <div className="stack">
      <section className="panel">
        <h2>Deletion requests</h2>
        {reqs.loading && !reqs.data ? <Spinner /> : reqs.error ? <ErrorBox msg={reqs.error} retry={reqs.reload} /> : !reqs.data?.length ? <Empty title="No deletion requests" hint="Request deletion from a candidate's profile. Completing a request erases personal data and the original CV file." /> :
          reqs.data.map(r => (
            <div className="file" key={r.id}>
              <b>{r.candidate}</b><Badge tone={r.status === 'Requested' ? 'warn' : r.status === 'Completed' ? 'good' : 'neutral'}>{r.status}</Badge><small>{fmtDate(r.at + 'Z')}</small>
              {r.status === 'Requested' && <>
                <button className="danger" onClick={() => confirm(`Permanently erase ${r.candidate}'s personal data and CV file? This cannot be undone.`) && act(() => send(auth.token, `/api/deletion-requests/${r.id}/complete`, 'POST'), 'Candidate data erased.')}>Complete deletion</button>
                <button className="ghost" onClick={() => act(() => send(auth.token, `/api/deletion-requests/${r.id}/decline`, 'POST'), 'Request declined.')}>Decline</button>
              </>}
            </div>))}
      </section>
      <section className="panel">
        <h2>Candidate consent</h2>
        {people.loading && !people.data ? <Spinner /> : people.error ? <ErrorBox msg={people.error} retry={people.reload} /> : !people.data?.length ? <Empty title="No candidates yet" /> :
          people.data.map(p => (
            <div className="file" key={p.id}>
              <b>{p.name}</b><small>{p.requisition_title}</small>
              <select aria-label={`Consent for ${p.name}`} value={p.consent} onChange={e => act(() => send(auth.token, `/api/candidates/${p.id}/consent`, 'PUT', {status: e.target.value}), 'Consent recorded.')}>{['Pending', 'Granted', 'Withdrawn'].map(x => <option key={x}>{x}</option>)}</select>
            </div>))}
      </section>
      <section className="panel">
        <div className="toolbar"><h2>Access audit</h2><input className="search" placeholder="Filter by action, user or candidate…" value={q} onChange={e => setQ(e.target.value)} /></div>
        {log.loading && !log.data ? <Spinner /> : log.error ? <ErrorBox msg={log.error} retry={log.reload} /> : !rows.length ? <Empty title="No matching audit entries" /> :
          <div className="table scroll"><table><thead><tr><th>When</th><th>Who</th><th>Action</th><th>Record</th></tr></thead><tbody>
            {rows.map((a, i) => <tr key={i}><td>{fmtDate(a.at)}</td><td>{a.actor}</td><td>{label(a.action)}</td><td>{name(a.target) || a.target.slice(0, 8)}</td></tr>)}
          </tbody></table></div>}
        <small>Shows the latest 200 events: profile views, CV previews, consent, submissions and client actions.</small>
      </section>
    </div>
  );
}
