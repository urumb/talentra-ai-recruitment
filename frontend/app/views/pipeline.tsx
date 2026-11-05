'use client';
import {Empty, ErrorBox, Spinner, STAGES, call, useApp, useLoad} from '../lib';
import type {Cand} from './candidates';

export default function Pipeline({ver, setOpenId}: {ver: number; setOpenId: (id?: string) => void}) {
  const {auth} = useApp();
  const {data, error, loading, reload} = useLoad<Cand[]>(() => call(auth.token, '/api/candidates'), [ver], undefined);
  if (loading && !data) return <Spinner />;
  if (error) return <ErrorBox msg={error} retry={reload} />;
  if (!data?.length) return <Empty title="Pipeline is empty" hint="Candidates appear here as soon as CVs are processed. Client shortlists and rejections update their stage." />;
  return (
    <>
      <div className="toolbar"><small>Stages update when clients shortlist, reject or propose interviews. Open a card to change a stage.</small><button className="ghost" onClick={reload}>Refresh</button></div>
      <div className="board">{STAGES.map(s => {
        const items = data.filter(c => c.stage === s);
        return <div className="col" key={s}><h3>{s} <span>{items.length}</span></h3>
          {items.map(c => <button key={c.id} className="card" onClick={() => setOpenId(c.id)}><b>{c.name}</b><small>{c.requisition_title}</small><strong>{c.score}</strong></button>)}
          {!items.length && <small className="muted">None</small>}
        </div>;
      })}</div>
    </>
  );
}
