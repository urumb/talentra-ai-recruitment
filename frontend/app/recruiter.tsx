'use client';
import {useState} from 'react';
import {Spinner, ErrorBox, call, label, useApp, useLoad} from './lib';
import {CandidateDrawer} from './views/candidates';
import Requisitions from './views/requisitions';
import Uploads from './views/uploads';
import Candidates from './views/candidates';
import Duplicates from './views/duplicates';
import Pipeline from './views/pipeline';
import Privacy from './views/privacy';
import {Fairness} from './views/monitoring';

const TABS = ['Overview', 'Requisitions', 'Uploads', 'Candidates', 'Duplicates', 'Pipeline', 'Privacy', 'Monitoring'];

export default function Recruiter({out}: {out: () => void}) {
  const [tab, setTab] = useState('Overview');
  const [open, setOpen] = useState<string>();       // candidate id opened from any tab
  const [ver, setVer] = useState(0);                // bumped when the drawer changes data
  const {auth} = useApp();
  return (
    <main className="shell">
      <aside>
        <b>talentra</b>
        <nav aria-label="Workspace">{TABS.map(x => <button key={x} className={tab === x ? 'active' : ''} aria-current={tab === x} onClick={() => setTab(x)}>{x}</button>)}</nav>
        <small>AI is decision support, never a hiring decision. Nobody is rejected automatically.</small>
      </aside>
      <section className="content">
        <header className="top"><div><p className="eyebrow">RECRUITER WORKSPACE · {auth.email}</p><h1>{tab}</h1></div><button onClick={out}>Sign out</button></header>
        {tab === 'Overview' && <Overview go={setTab} />}
        {tab === 'Requisitions' && <Requisitions />}
        {tab === 'Uploads' && <Uploads openCandidate={setOpen} />}
        {tab === 'Candidates' && <Candidates ver={ver} setOpenId={setOpen} />}
        {tab === 'Duplicates' && <Duplicates />}
        {tab === 'Pipeline' && <Pipeline ver={ver} setOpenId={setOpen} />}
        {tab === 'Privacy' && <Privacy />}
        {tab === 'Monitoring' && <Fairness />}
        {open && <CandidateDrawer id={open} onClose={() => setOpen(undefined)} onChange={() => setVer(v => v + 1)} />}
      </section>
    </main>
  );
}

const TARGET: Record<string, string> = {documents_failed: 'Uploads', duplicates_to_review: 'Duplicates', awaiting_review: 'Candidates', open_deletion_requests: 'Privacy', active_requisitions: 'Requisitions', documents_processing: 'Uploads'};

function Overview({go}: {go: (t: string) => void}) {
  const {auth} = useApp();
  const {data, error, loading, reload} = useLoad<Record<string, number>>(() => call(auth.token, '/api/dashboard'), [], d => d.documents_processing > 0, 2500);
  if (loading && !data) return <Spinner />;
  if (error && !data) return <ErrorBox msg={error} retry={reload} />;
  return (
    <>
      <div className="metrics">{data && Object.entries(data).map(([k, v]) => {
        const t = TARGET[k]; const alert = v > 0 && ['documents_failed', 'duplicates_to_review', 'open_deletion_requests'].includes(k);
        return <article key={k} className={alert ? 'alert' : ''}><span>{label(k)}</span><b>{v}</b>{t && <button className="link" onClick={() => go(t)}>Open {t.toLowerCase()} →</button>}</article>;
      })}</div>
      <div className="notice">Scores are reproducible from the saved scorecard and the evidence in each CV. Facts a CV does not state are shown as <b>unknown</b> and earn no points; they are never treated as a rejection.</div>
    </>
  );
}
