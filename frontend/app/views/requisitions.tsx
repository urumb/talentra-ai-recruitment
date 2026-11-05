'use client';
import {FormEvent, useState} from 'react';
import {Empty, ErrorBox, Spinner, call, send, useApp, useLoad} from '../lib';

type Crit = {label: string; type: string; weight: number; values?: string[]; min?: number | null; max?: number | null};
type Req = {id: string; title: string; client: string; location: string; description: string; candidates: number; scorecard: {criteria: Crit[]}};
const TYPES = ['skills', 'experience', 'notice', 'ctc', 'location', 'education'];
const DEFAULT: Crit[] = [{label: 'Required skills', type: 'skills', weight: 60, values: []}, {label: 'Experience', type: 'experience', weight: 25, min: 3}, {label: 'Notice period', type: 'notice', weight: 15, max: 60}];

export default function Requisitions() {
  const {auth, toast} = useApp();
  const reqs = useLoad<Req[]>(() => call(auth.token, '/api/requisitions'), []);
  const orgs = useLoad<string[]>(() => call(auth.token, '/api/client-orgs'), []);
  const [chosen, setChosen] = useState<Req | null>(null);
  const [title, setTitle] = useState(''), [client, setClient] = useState(''), [loc, setLoc] = useState(''), [desc, setDesc] = useState('');
  const [crit, setCrit] = useState<Crit[]>(DEFAULT);
  const [msg, setMsg] = useState<{t: string; bad?: boolean}>(), [busy, setBusy] = useState('');
  const total = Math.round(crit.reduce((n, x) => n + (Number(x.weight) || 0), 0) * 100) / 100;

  const reset = () => { setChosen(null); setTitle(''); setLoc(''); setDesc(''); setCrit(DEFAULT); setMsg(undefined); };
  const pick = (r: Req) => { setChosen(r); setTitle(r.title); setClient(r.client); setLoc(r.location); setDesc(r.description); setCrit(r.scorecard.criteria); setMsg(undefined); };
  const upd = (i: number, patch: Partial<Crit>) => setCrit(crit.map((x, n) => n === i ? {...x, ...patch} : x));

  async function extract() {
    setBusy('extract'); setMsg(undefined);
    try {
      const r = await send(auth.token, '/api/jd/extract', 'POST', {description: desc});
      setCrit(r.criteria); setMsg({t: ['Extracted by the configured AI provider. Review every criterion, then save.', ...r.warnings].join(' ')});
    } catch (e: any) { setMsg({t: e.message, bad: true}); } finally { setBusy(''); }
  }

  async function save(e: FormEvent) {
    e.preventDefault(); setBusy('save');
    const criteria = crit.map(x => ({...x, weight: Number(x.weight), values: x.values || [], min: x.type === 'experience' ? Number(x.min) || 0 : null, max: (x.type === 'notice' || x.type === 'ctc') && x.max != null && x.max !== ('' as any) ? Number(x.max) : null}));
    try {
      if (chosen) {
        const r = await send(auth.token, `/api/requisitions/${chosen.id}/scorecard`, 'PUT', {criteria});
        toast(`Scorecard saved. ${r.rescored} candidate${r.rescored === 1 ? '' : 's'} re-scored.`);
      } else {
        await send(auth.token, '/api/requisitions', 'POST', {title, client, location: loc, description: desc, scorecard: {criteria}});
        toast('Requisition created.'); reset();
      }
      reqs.reload();
    } catch (e: any) { setMsg({t: e.message, bad: true}); } finally { setBusy(''); }
  }

  return (
    <div className="split">
      <form className="panel" onSubmit={save}>
        <div className="toolbar"><h2>{chosen ? `Edit scorecard · ${chosen.title}` : 'New requisition'}</h2>{chosen && <button type="button" className="ghost" onClick={reset}>New requisition</button>}</div>
        <div className="grid2">
          <label>Title<input required disabled={!!chosen} value={title} onChange={e => setTitle(e.target.value)} /></label>
          <label>Client organization
            <select required disabled={!!chosen} value={client} onChange={e => setClient(e.target.value)}>
              <option value="">Select client…</option>{(orgs.data || []).map(o => <option key={o}>{o}</option>)}
            </select>
          </label>
        </div>
        <label>Location<input disabled={!!chosen} value={loc} onChange={e => setLoc(e.target.value)} /></label>
        <label>Job description<textarea required disabled={!!chosen} value={desc} onChange={e => setDesc(e.target.value)} placeholder="Paste the full job description" /></label>
        <div className="actions">
          <button type="button" disabled={desc.trim().length < 20 || busy === 'extract'} onClick={extract}>{busy === 'extract' ? 'Extracting…' : 'Extract scorecard with AI'}</button>
          <small>Uses the server's configured LLM. If none is configured you can build the scorecard by hand.</small>
        </div>
        <h3>Scorecard <span className={'total ' + (total === 100 ? 'ok' : 'off')}>{total} / 100</span></h3>
        {crit.map((x, i) => (
          <div className="criterion" key={i}>
            <input aria-label="Criterion name" value={x.label} onChange={e => upd(i, {label: e.target.value})} />
            <select aria-label="Type" value={x.type} onChange={e => upd(i, {type: e.target.value})}>{TYPES.map(v => <option key={v}>{v}</option>)}</select>
            <input aria-label="Weight" type="number" min={0} max={100} step="any" value={x.weight} onChange={e => upd(i, {weight: e.target.value as any})} />
            {x.type === 'experience' ? <input aria-label="Minimum years" type="number" min={0} step="any" placeholder="Min years" value={x.min ?? ''} onChange={e => upd(i, {min: e.target.value as any})} />
              : x.type === 'notice' ? <input aria-label="Maximum days" type="number" min={0} placeholder="Max notice days" value={x.max ?? ''} onChange={e => upd(i, {max: e.target.value as any})} />
              : x.type === 'ctc' ? <input aria-label="Maximum CTC in LPA" type="number" min={0} step="any" placeholder="Max CTC (LPA)" value={x.max ?? ''} onChange={e => upd(i, {max: e.target.value as any})} />
              : <input aria-label="Values" placeholder="Comma-separated, e.g. Java, Kafka" value={(x.values || []).join(', ')} onChange={e => upd(i, {values: e.target.value.split(',').map(v => v.trim()).filter(Boolean)})} />}
            <button type="button" className="ghost" aria-label={`Remove ${x.label}`} onClick={() => setCrit(crit.filter((_, n) => n !== i))}>✕</button>
          </div>
        ))}
        <div className="actions">
          <button type="button" className="ghost" onClick={() => setCrit([...crit, {label: 'New criterion', type: 'skills', weight: 0, values: []}])}>Add criterion</button>
          <button type="button" className="ghost" disabled={!crit.length} onClick={() => { const t = crit.reduce((n, x) => n + Number(x.weight || 0), 0) || 1; setCrit(crit.map(x => ({...x, weight: Math.round(Number(x.weight || 0) * 1000 / t) / 10}))); }}>Scale to 100</button>
        </div>
        {msg && <p className={msg.bad ? 'error' : 'hint'} role="status">{msg.t}</p>}
        <button disabled={total !== 100 || busy === 'save' || (!chosen && (!title || !client || !desc))}>{busy === 'save' ? 'Saving…' : chosen ? 'Save scorecard & re-score candidates' : 'Create requisition'}</button>
      </form>
      <section className="panel">
        <h2>Requisitions</h2>
        {reqs.loading && !reqs.data ? <Spinner /> : reqs.error ? <ErrorBox msg={reqs.error} retry={reqs.reload} /> : !reqs.data?.length ? <Empty title="No requisitions yet" hint="Create one to start uploading CVs." /> :
          reqs.data.map(x => <button className={'listItem ' + (chosen?.id === x.id ? 'on' : '')} key={x.id} onClick={() => pick(x)}><b>{x.title}</b><small>{x.client} · {x.location || 'No location'} · {x.candidates} candidate{x.candidates === 1 ? '' : 's'}</small></button>)}
      </section>
    </div>
  );
}
