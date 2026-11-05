'use client';
import {useState} from 'react';
import {Badge, DocPreview, Empty, ErrorBox, Modal, Spinner, call, send, useApp, useLoad} from '../lib';

export default function Duplicates() {
  const {auth, toast} = useApp();
  const {data, error, loading, reload} = useLoad<any[]>(() => call(auth.token, '/api/duplicates'), []);
  const [view, setView] = useState<{id: string; name: string}>();
  const resolve = async (rid: string, action: string) => {
    try { await send(auth.token, `/api/resumes/${rid}/resolve-duplicate`, 'POST', {action}); toast(action === 'discard' ? 'Duplicate discarded and its file deleted.' : 'Processing as a separate candidate…'); reload(); }
    catch (e: any) { toast(e.message, true); }
  };
  if (loading && !data) return <Spinner />;
  if (error) return <ErrorBox msg={error} retry={reload} />;
  if (!data?.length) return <Empty title="No duplicates waiting for review" hint="Documents that match an existing candidate by email, phone number or identical file appear here instead of being added twice." />;
  return (
    <>
      <div className="notice">These documents were <b>not</b> added as new candidates because they match someone already in the system. Compare them and decide.</div>
      {data.map(d => (
        <section className="panel dup" key={d.resume_id}>
          <div className="cols">
            <div><p className="eyebrow">NEW DOCUMENT</p><b>{d.filename}</b><p><Badge tone="warn">matched by {d.reason || 'unknown'}</Badge></p><button className="ghost" onClick={() => setView({id: d.resume_id, name: d.filename})}>Preview new document</button></div>
            <div><p className="eyebrow">EXISTING CANDIDATE</p>
              {d.existing ? <><b>{d.existing.name}</b><p>{d.existing.email || 'no email'} · score {d.existing.score} · {d.existing.stage}</p>{d.existing.resume_id && <button className="ghost" onClick={() => setView({id: d.existing.resume_id, name: d.existing.name})}>Preview existing CV</button>}</> : <p className="muted">The matched candidate no longer exists.</p>}
            </div>
          </div>
          <div className="actions">
            <button onClick={() => resolve(d.resume_id, 'discard')}>Discard duplicate</button>
            <button className="ghost" disabled={d.reason === 'email'} title={d.reason === 'email' ? 'Same email: two candidates cannot share an email address' : ''} onClick={() => resolve(d.resume_id, 'keep_both')}>Not a duplicate: add as new candidate</button>
          </div>
        </section>
      ))}
      {view && <Modal title={view.name} onClose={() => setView(undefined)}><DocPreview id={view.id} filename={view.name} /></Modal>}
    </>
  );
}
