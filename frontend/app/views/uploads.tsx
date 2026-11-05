'use client';
import {DragEvent, useRef, useState} from 'react';
import {API, Badge, Empty, ErrorBox, Spinner, call, fmtDate, send, toneOf, useApp, useLoad} from '../lib';

type Counts = Record<string, number>;
type BatchRow = {id: string; requisition_title: string; created_at: string; total: number; counts: Counts};
type FileRow = {id: string; filename: string; status: string; error?: string; candidate_id?: string};
type Detail = {id: string; total: number; counts: Counts; files: FileRow[]};
const active = (c: Counts) => (c.queued || 0) + (c.processing || 0) > 0;

export default function Uploads({openCandidate}: {openCandidate: (id: string) => void}) {
  const {auth, toast} = useApp();
  const reqs = useLoad<any[]>(() => call(auth.token, '/api/requisitions'), []);
  const batches = useLoad<BatchRow[]>(() => call(auth.token, '/api/batches'), [], d => d.some(b => active(b.counts)), 2500);
  const [sel, setSel] = useState<string>();
  const [req, setReq] = useState(''), [files, setFiles] = useState<File[]>([]), [pct, setPct] = useState<number | null>(null), [err, setErr] = useState(''), [over, setOver] = useState(false);
  const input = useRef<HTMLInputElement>(null);

  const add = (list: FileList | File[]) => { const ok = Array.from(list).filter(f => /\.(pdf|docx)$/i.test(f.name)); if (ok.length < Array.from(list).length) toast('Only PDF and DOCX files were added.', true); setFiles(f => [...f, ...ok].slice(0, 500)); };
  const drop = (e: DragEvent) => { e.preventDefault(); setOver(false); add(e.dataTransfer.files); };

  function start() {
    if (!req || !files.length) return;
    setErr(''); setPct(0);
    const form = new FormData(); files.forEach(f => form.append('files', f));
    const xhr = new XMLHttpRequest(); xhr.open('POST', `${API}/api/requisitions/${req}/uploads`); xhr.setRequestHeader('Authorization', 'Bearer ' + auth.token);
    xhr.upload.onprogress = e => e.lengthComputable && setPct(Math.round(e.loaded * 100 / e.total));
    xhr.onerror = () => { setPct(null); setErr('Upload failed: cannot reach the API.'); };
    xhr.onload = () => {
      setPct(null);
      let j: any = {}; try { j = JSON.parse(xhr.responseText); } catch {}
      if (xhr.status !== 200) return setErr(typeof j.detail === 'string' ? j.detail : `Upload failed (${xhr.status})`);
      toast(`${j.accepted} file${j.accepted === 1 ? '' : 's'} queued${j.rejected ? `, ${j.rejected} rejected` : ''}.`);
      setFiles([]); if (input.current) input.current.value = ''; setSel(j.batch_id); batches.reload();
    };
    xhr.send(form);
  }

  return (
    <>
      <section className="panel">
        <h2>Upload CV batch</h2>
        <div className="grid2">
          <label>Requisition<select value={req} onChange={e => setReq(e.target.value)}><option value="">Select requisition…</option>{(reqs.data || []).map(x => <option key={x.id} value={x.id}>{x.title} · {x.client}</option>)}</select></label>
        </div>
        <div className={'drop ' + (over ? 'over' : '')} onDragOver={e => { e.preventDefault(); setOver(true); }} onDragLeave={() => setOver(false)} onDrop={drop} onClick={() => input.current?.click()} role="button" tabIndex={0} onKeyDown={e => e.key === 'Enter' && input.current?.click()}>
          <b>Drop PDF or DOCX files here, or click to choose</b>
          <small>Up to 500 files per batch · 10 MB each (server limit) · scanned PDFs are read with OCR</small>
          <input ref={input} type="file" accept=".pdf,.docx" multiple hidden onChange={e => e.target.files && add(e.target.files)} />
        </div>
        {files.length > 0 && <div className="actions"><span>{files.length} file{files.length === 1 ? '' : 's'} selected ({(files.reduce((n, f) => n + f.size, 0) / 1048576).toFixed(1)} MB)</span><button className="ghost" onClick={() => setFiles([])}>Clear</button></div>}
        {pct !== null && <div className="bar" aria-label="Upload progress"><i style={{width: pct + '%'}} /><span>Uploading {pct}%</span></div>}
        {err && <p className="error" role="alert">{err}</p>}
        <button disabled={!req || !files.length || pct !== null} onClick={start}>{pct !== null ? 'Uploading…' : `Upload ${files.length || ''} and process`}</button>
        {!req && files.length > 0 && <small>Select a requisition to continue.</small>}
      </section>

      <section className="panel">
        <div className="toolbar"><h2>Batch history</h2><button className="ghost" onClick={batches.reload}>Refresh</button></div>
        {batches.loading && !batches.data ? <Spinner /> : batches.error ? <ErrorBox msg={batches.error} retry={batches.reload} /> : !batches.data?.length ? <Empty title="No uploads yet" hint="Uploaded batches and their processing status appear here." /> :
          <div className="table">{batches.data.map(b => {
            const done = b.total - (b.counts.queued || 0) - (b.counts.processing || 0);
            return <button key={b.id} className={'row batch ' + (sel === b.id ? 'on' : '')} onClick={() => setSel(sel === b.id ? undefined : b.id)}>
              <span><b>{b.requisition_title || 'Requisition'}</b><small>{fmtDate(b.created_at + 'Z')}</small></span>
              <span>{b.total} doc{b.total === 1 ? '' : 's'}</span>
              <span className="bar sm"><i style={{width: (b.total ? done * 100 / b.total : 0) + '%'}} /></span>
              <span className="chips">{active(b.counts) && <Badge tone="info">processing</Badge>}{b.counts.failed > 0 && <Badge tone="bad">{b.counts.failed} failed</Badge>}{b.counts.duplicate > 0 && <Badge tone="warn">{b.counts.duplicate} duplicate</Badge>}{!active(b.counts) && !b.counts.failed && !b.counts.duplicate && <Badge tone="good">done</Badge>}</span>
            </button>;
          })}</div>}
      </section>

      {sel && <BatchDetail id={sel} onChange={batches.reload} openCandidate={openCandidate} />}
    </>
  );
}

function BatchDetail({id, onChange, openCandidate}: {id: string; onChange: () => void; openCandidate: (id: string) => void}) {
  const {auth, toast} = useApp();
  const {data, error, loading, reload} = useLoad<Detail>(() => call(auth.token, '/api/batches/' + id), [id], d => active(d.counts));
  const [filter, setFilter] = useState('all');
  if (loading && !data) return <Spinner />;
  if (error && !data) return <ErrorBox msg={error} retry={reload} />;
  if (!data) return null;
  const c = data.counts; const finished = data.total - (c.queued || 0) - (c.processing || 0);
  const tiles: [string, number, string][] = [['Total', data.total, ''], ['Completed', c.completed || 0, 'good'], ['Processing', (c.processing || 0) + (c.queued || 0), 'info'], ['Failed', c.failed || 0, 'bad'], ['Duplicates', (c.duplicate || 0) + (c.resolved_duplicate || 0), 'warn']];
  const shown = data.files.filter(f => filter === 'all' || (filter === 'processing' ? ['queued', 'processing'].includes(f.status) : filter === 'duplicate' ? f.status.includes('duplicate') : f.status === filter));
  const retry = async (rid: string) => { try { await send(auth.token, `/api/resumes/${rid}/retry`, 'POST'); reload(); onChange(); } catch (e: any) { toast(e.message, true); } };
  const retryAll = async () => { try { const r = await send(auth.token, `/api/batches/${id}/retry-failed`, 'POST'); toast(`${r.requeued} document${r.requeued === 1 ? '' : 's'} re-queued.`); reload(); onChange(); } catch (e: any) { toast(e.message, true); } };
  return (
    <section className="panel">
      <div className="toolbar"><h2>Processing status</h2>{(c.failed || 0) > 0 && <button onClick={retryAll}>Retry all failed</button>}</div>
      <div className="bar" aria-label="Processing progress"><i style={{width: (data.total ? finished * 100 / data.total : 0) + '%'}} /><span>{finished} of {data.total} processed{active(c) ? ' · working…' : ''}</span></div>
      <div className="metrics five">{tiles.map(([k, v, tone]) => <article key={k} className={tone}><span>{k}</span><b>{v}</b></article>)}</div>
      <div className="chips">{['all', 'processing', 'completed', 'failed', 'duplicate'].map(f => <button key={f} className={'chip cap ' + (filter === f ? 'on' : '')} onClick={() => setFilter(f)}>{f}</button>)}</div>
      {!shown.length ? <Empty title="No documents in this view" /> : shown.map(f => (
        <div className="file" key={f.id}>
          <b>{f.filename}</b><Badge tone={toneOf(f.status)}>{f.status.replaceAll('_', ' ')}</Badge>
          {f.candidate_id && <button className="link" onClick={() => openCandidate(f.candidate_id!)}>Open candidate →</button>}
          {f.status === 'failed' && <button className="ghost" onClick={() => retry(f.id)}>Retry</button>}
          {f.error && <small className={f.status === 'failed' ? 'error' : ''}>{f.error}</small>}
        </div>
      ))}
    </section>
  );
}
