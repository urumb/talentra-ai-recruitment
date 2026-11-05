'use client';
import {useState} from 'react';
import {Icon, ErrorBox, Spinner, call, pl, useApp, useLoad} from './lib';
import {CandidateDrawer} from './views/candidates';
import Requisitions from './views/requisitions';
import Uploads from './views/uploads';
import Candidates from './views/candidates';
import Duplicates from './views/duplicates';
import Pipeline from './views/pipeline';
import Privacy from './views/privacy';
import {Fairness} from './views/monitoring';

type Dash = Record<string, number>;
const NAV: {group: string; items: [string, string][]}[] = [
  {group: 'Workspace', items: [['Overview', 'home'], ['Requisitions', 'doc'], ['Uploads', 'upload']]},
  {group: 'Review', items: [['Candidates', 'users'], ['Duplicates', 'copy'], ['Pipeline', 'kanban']]},
  {group: 'Compliance', items: [['Privacy', 'shield'], ['Monitoring', 'chart']]},
];
const SUBTITLE: Record<string, string> = {
  Overview: 'What needs your attention today',
  Requisitions: 'Create a job and its scorecard',
  Uploads: 'Bulk-upload CVs and follow processing',
  Candidates: 'Ranked by score, with the evidence behind it',
  Duplicates: 'Documents that match an existing candidate',
  Pipeline: 'From sourced to joined',
  Privacy: 'Consent, deletion requests and access history',
  Monitoring: 'How AI ranking compares with recruiter choices',
};

export default function Recruiter({out}: {out: () => void}) {
  const [tab, setTab] = useState('Overview');
  const [open, setOpen] = useState<string>();       // candidate opened from any tab
  const [ver, setVer] = useState(0);                // bumped when the drawer changes data
  const {auth} = useApp();
  const dash = useLoad<Dash>(() => call(auth.token, '/api/dashboard'), [tab, ver], d => d.documents_processing > 0, 2500);
  const d = dash.data;
  const badge = (t: string): {n: number; tone: string} | null => {
    if (!d) return null;
    const m: Record<string, {n: number; tone: string}> = {
      Uploads: d.documents_failed ? {n: d.documents_failed, tone: 'bad'} : {n: d.documents_processing, tone: 'info'},
      Candidates: {n: d.awaiting_review, tone: 'info'}, Duplicates: {n: d.duplicates_to_review, tone: 'warn'}, Privacy: {n: d.open_deletion_requests, tone: 'warn'},
    };
    return m[t]?.n ? m[t] : null;
  };
  return (
    <main className="shell">
      <aside>
        <b className="brand">talentra</b>
        <nav aria-label="Workspace">{NAV.map(g => (
          <div className="navgroup" key={g.group}><span className="navlabel">{g.group}</span>
            {g.items.map(([t, ic]) => { const b = badge(t); return (
              <button key={t} className={tab === t ? 'active' : ''} aria-current={tab === t ? 'page' : undefined} onClick={() => setTab(t)}><Icon name={ic} />{t}{b && <i className={'nb ' + b.tone}>{b.n}</i>}</button>); })}
          </div>))}
        </nav>
        <div className="sidefoot"><small>{auth.email}</small><button className="ghost" onClick={out}><Icon name="out" /><span>Sign out</span></button><small>AI is decision support. Nobody is rejected automatically.</small></div>
      </aside>
      <section className="content">
        <header className="top"><div><h1>{tab}</h1><p className="sub">{SUBTITLE[tab]}</p></div></header>
        {tab === 'Overview' && <Overview d={d} loading={dash.loading} error={dash.error} reload={dash.reload} go={setTab} />}
        {tab === 'Requisitions' && <Requisitions />}
        {tab === 'Uploads' && <Uploads openCandidate={setOpen} />}
        {tab === 'Candidates' && <Candidates ver={ver} setOpenId={setOpen} go={setTab} />}
        {tab === 'Duplicates' && <Duplicates />}
        {tab === 'Pipeline' && <Pipeline ver={ver} setOpenId={setOpen} />}
        {tab === 'Privacy' && <Privacy />}
        {tab === 'Monitoring' && <Fairness />}
        {open && <CandidateDrawer id={open} onClose={() => setOpen(undefined)} onChange={() => setVer(v => v + 1)} />}
      </section>
    </main>
  );
}

function Overview({d, go, loading, error, reload}: {d?: Dash; go: (t: string) => void; loading: boolean; error: string; reload: () => void}) {
  if (loading && !d) return <Spinner />;
  if (error && !d) return <ErrorBox msg={error} retry={reload} />;
  if (!d) return null;
  const todo = [
    {n: d.documents_failed, text: `${pl(d.documents_failed, 'document')} failed to process`, hint: 'See the error and retry', tab: 'Uploads', tone: 'bad'},
    {n: d.documents_processing, text: `${pl(d.documents_processing, 'document')} still processing`, hint: 'Progress updates automatically', tab: 'Uploads', tone: 'info'},
    {n: d.duplicates_to_review, text: `${pl(d.duplicates_to_review, 'possible duplicate')} to review`, hint: 'Not added to the ranking until you decide', tab: 'Duplicates', tone: 'warn'},
    {n: d.awaiting_review, text: `${pl(d.awaiting_review, 'candidate')} waiting for your review`, hint: 'Open the CV, record consent, then submit', tab: 'Candidates', tone: 'info'},
    {n: d.open_deletion_requests, text: `${pl(d.open_deletion_requests, 'deletion request')} open`, hint: 'Candidates are entitled to deletion on request', tab: 'Privacy', tone: 'warn'},
  ].filter(x => x.n > 0);
  const kpis: [string, number, string][] = [['Open requisitions', d.active_requisitions, 'Requisitions'], ['Candidates screened', d.candidates_processed, 'Candidates'], ['Awaiting review', d.awaiting_review, 'Candidates'], ['With clients', d.submitted_to_client + d.shortlisted, 'Pipeline']];
  return (
    <>
      <div className="metrics">{kpis.map(([k, v, t]) => <button key={k} className="kpi" onClick={() => go(t)}><span>{k}</span><b>{v}</b></button>)}</div>
      <section className="panel">
        <h2>Needs your attention</h2>
        {todo.length ? todo.map(x => (
          <div className="todo" key={x.text}><i className={'dot ' + x.tone} /><div><b>{x.text}</b><small>{x.hint}</small></div><button className="ghost" onClick={() => go(x.tab)}>Open {x.tab.toLowerCase()}</button></div>
        )) : <div className="state ok"><b>You are all caught up.</b><span>Nothing is waiting on you right now.</span></div>}
      </section>
      {d.candidates_processed === 0 && (
        <section className="panel"><h2>Get started</h2>
          <ol className="steps"><li><b>Create a requisition</b><span>Paste the job description; AI drafts the scorecard and you edit it.</span></li><li><b>Upload CVs</b><span>PDF or DOCX, up to 500 at a time.</span></li><li><b>Review the ranking</b><span>Every score shows the line it came from.</span></li><li><b>Submit to the client</b><span>After you open the CV and record consent.</span></li></ol>
          <div className="actions"><button onClick={() => go('Requisitions')}>New requisition</button><button className="ghost" onClick={() => go('Uploads')}>Upload CVs</button></div>
        </section>)}
      <div className="notice">Scores are reproducible from the saved scorecard and the evidence in each CV. Facts a CV does not state are shown as <b>unknown</b> and earn no points; they are never treated as a rejection.</div>
    </>
  );
}
