'use client';
import {useState} from 'react';
import {Empty, ErrorBox, Spinner, STAGES, call, useApp, useLoad} from '../lib';
import type {Cand} from './candidates';

export default function Pipeline({ver, setOpenId}: {ver: number; setOpenId: (id?: string) => void}) {
  const {auth} = useApp();
  const [req, setReq] = useState('');
  const reqs = useLoad<any[]>(() => call(auth.token, '/api/requisitions'), []);
  const {data, error, loading, reload} = useLoad<Cand[]>(() => call(auth.token, '/api/candidates' + (req ? '?requisition_id=' + req : '')), [ver, req], undefined);
  if (loading && !data) return <Spinner />;
  if (error) return <ErrorBox msg={error} retry={reload} />;
  return (
    <>
      <div className="toolbar"><label className="inline">Requisition<select value={req} onChange={e => setReq(e.target.value)}><option value="">All requisitions</option>{(reqs.data || []).map(x => <option key={x.id} value={x.id}>{x.title}</option>)}</select></label><small>Stages update when clients shortlist, reject or propose interviews. Open a card to change a stage.</small><button className="ghost" onClick={reload}>Refresh</button></div>
      {!data?.length ? <Empty title="No candidates in this pipeline" hint="Candidates appear here as soon as CVs are processed. Client shortlists and rejections update their stage." /> : <div className="board">{STAGES.map(s => {
        const items = (data || []).filter(c => c.stage === s);
        return <div className="col" key={s}><h3>{s} <span>{items.length}</span></h3>
          {items.map(c => <button key={c.id} className="card" onClick={() => setOpenId(c.id)}><b>{c.name}</b><small>{c.requisition_title}</small><strong>{c.score}</strong></button>)}
          {!items.length && <small className="muted">None</small>}
        </div>;
      })}</div>}
    </>
  );
}
