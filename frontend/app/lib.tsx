'use client';
import {createContext, useCallback, useContext, useEffect, useRef, useState} from 'react';

export const API = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

export class ApiError extends Error {
  constructor(message: string, public status: number) { super(message); }
}

let onUnauthorized: () => void = () => {};
export const setUnauthorizedHandler = (fn: () => void) => { onUnauthorized = fn; };

async function detail(r: Response) {
  try {
    const j = await r.json();
    if (typeof j.detail === 'string') return j.detail;
    if (Array.isArray(j.detail)) return j.detail.map((x: any) => (x.msg || '').replace(/^Value error, /, '')).join('; ');
  } catch {}
  return `Request failed (${r.status})`;
}

/** Authenticated JSON call. Throws ApiError with the server's message. */
export async function call<T = any>(token: string, path: string, init: RequestInit = {}): Promise<T> {
  let r: Response;
  try {
    r = await fetch(API + path, {...init, headers: {Authorization: `Bearer ${token}`, ...(typeof init.body === 'string' ? {'Content-Type': 'application/json'} : {}), ...init.headers}});
  } catch {
    throw new ApiError('Cannot reach the Talentra API. Check that the backend is running.', 0);
  }
  if (r.status === 401) { onUnauthorized(); throw new ApiError('Your session has expired. Please sign in again.', 401); }
  if (!r.ok) throw new ApiError(await detail(r), r.status);
  return r.status === 204 ? (undefined as T) : r.json();
}

export const send = (token: string, path: string, method: string, body?: unknown) => call(token, path, {method, body: body === undefined ? undefined : JSON.stringify(body)});

export async function fetchBlob(token: string, path: string) {
  const r = await fetch(API + path, {headers: {Authorization: `Bearer ${token}`}});
  if (r.status === 401) onUnauthorized();
  if (!r.ok) throw new ApiError(await detail(r), r.status);
  return r.blob();
}

/** Loads data, exposes loading/error and a reload. Optional polling while `poll(data)` is true. */
export function useLoad<T>(fn: () => Promise<T>, deps: any[], poll?: (d: T) => boolean, ms = 1500) {
  const [data, setData] = useState<T>();
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);
  const fnRef = useRef(fn); fnRef.current = fn;
  const pollRef = useRef(poll); pollRef.current = poll;
  const timer = useRef<any>(null);
  const run = useCallback(async (quiet = false) => {
    if (!quiet) setLoading(true);
    clearTimeout(timer.current);
    try {
      const d = await fnRef.current(); setData(d); setError('');
      if (pollRef.current?.(d)) timer.current = setTimeout(() => run(true), ms);
    } catch (e: any) { setError(e.message || 'Something went wrong'); }
    finally { setLoading(false); }
  }, [ms]);
  useEffect(() => { run(); return () => clearTimeout(timer.current); }, deps); // eslint-disable-line react-hooks/exhaustive-deps
  return {data, error, loading, reload: () => run(true)};
}

export type Auth = {token: string; role: string; email: string; org: string};
export const Ctx = createContext<{auth: Auth; toast: (m: string, bad?: boolean) => void}>(null as any);
export const useApp = () => useContext(Ctx);

export const STAGES = ['Sourced', 'Screened', 'Submitted to Client', 'Shortlisted', 'Interview proposed', 'Interview scheduled', 'Offered', 'Joined', 'Rejected by Client', 'Rejected'];
export const fmtDate = (s?: string) => s ? new Date(s).toLocaleString(undefined, {dateStyle: 'medium', timeStyle: 'short'}) : '';
export const label = (s: string) => s.replaceAll('_', ' ');

export function Spinner({text = 'Loading…'}: {text?: string}) { return <div className="state" role="status"><span className="spin" aria-hidden />{text}</div>; }
export function ErrorBox({msg, retry}: {msg: string; retry?: () => void}) { return <div className="state bad" role="alert">{msg}{retry && <button className="ghost" onClick={retry}>Retry</button>}</div>; }
export function Empty({title, hint}: {title: string; hint?: string}) { return <div className="state"><b>{title}</b>{hint && <span>{hint}</span>}</div>; }
export function Badge({children, tone = 'neutral'}: {children: React.ReactNode; tone?: 'neutral' | 'good' | 'warn' | 'bad' | 'info'}) { return <span className={'badge ' + tone}>{children}</span>; }
export const toneOf = (s: string) => ({matched: 'good', completed: 'good', partial: 'warn', not_met: 'bad', not_found: 'bad', unknown: 'neutral', failed: 'bad', duplicate: 'warn', processing: 'info', queued: 'neutral', Granted: 'good', Withdrawn: 'bad', Pending: 'warn', High: 'good', Medium: 'warn', Low: 'bad'} as any)[s] || 'neutral';

export function Modal({title, onClose, children}: {title: string; onClose: () => void; children: React.ReactNode}) {
  useEffect(() => { const k = (e: KeyboardEvent) => e.key === 'Escape' && onClose(); window.addEventListener('keydown', k); return () => window.removeEventListener('keydown', k); }, [onClose]);
  return <div className="modal" onMouseDown={e => e.target === e.currentTarget && onClose()}><article role="dialog" aria-modal aria-label={title}><button className="close" onClick={onClose} aria-label="Close">×</button><h2>{title}</h2>{children}</article></div>;
}

/** Fetches a protected document with the bearer token and shows PDFs inline; DOCX is offered as a download. */
export function DocPreview({id, filename, onLoaded}: {id: string; filename?: string; onLoaded?: () => void}) {
  const {auth} = useApp();
  const [url, setUrl] = useState(''); const [type, setType] = useState(''); const [err, setErr] = useState('');
  useEffect(() => {
    let u = ''; let alive = true;
    fetchBlob(auth.token, '/api/documents/' + id).then(b => { if (!alive) return; u = URL.createObjectURL(b); setUrl(u); setType(b.type); onLoaded?.(); }).catch(e => alive && setErr(e.message));
    return () => { alive = false; if (u) URL.revokeObjectURL(u); };
  }, [id, auth.token]);
  if (err) return <ErrorBox msg={err} />;
  if (!url) return <Spinner text="Loading original document…" />;
  if (type === 'application/pdf') return <iframe className="pdf" src={url} title="Original CV" />;
  return <div className="state"><b>Word documents cannot be previewed in the browser.</b><a className="btn" href={url} download={filename || 'cv.docx'}>Download original</a></div>;
}

export const pl = (n: number, w: string) => `${n} ${w}${n === 1 ? '' : 's'}`;

/** Circular score. Deliberately one neutral hue (no red/green) so a low score never reads as a verdict. */
export function ScoreRing({score, size = 52}: {score: number; size?: number}) {
  const r = (size - 8) / 2, c = 2 * Math.PI * r, v = Math.max(0, Math.min(100, score));
  return (
    <span className="ring" style={{width: size, height: size}} role="img" aria-label={`Score ${score} out of 100`}>
      <svg width={size} height={size} aria-hidden><circle cx={size / 2} cy={size / 2} r={r} className="ring-bg" /><circle cx={size / 2} cy={size / 2} r={r} className="ring-fg" strokeDasharray={`${(v / 100) * c} ${c}`} transform={`rotate(-90 ${size / 2} ${size / 2})`} /></svg>
      <b style={{fontSize: size * 0.3}}>{Math.round(score)}</b>
    </span>
  );
}

const ICONS: Record<string, string> = {
  home: 'M3 11l9-8 9 8M5 10v10h5v-6h4v6h5V10',
  doc: 'M7 3h7l5 5v13H7zM14 3v5h5M10 13h6M10 17h6',
  upload: 'M12 16V4m0 0l-4 4m4-4l4 4M5 20h14',
  users: 'M16 19v-1a4 4 0 00-4-4H7a4 4 0 00-4 4v1M9.5 10a3.5 3.5 0 100-7 3.5 3.5 0 000 7zM21 19v-1a4 4 0 00-3-3.9M16 3.1a3.5 3.5 0 010 6.8',
  copy: 'M9 9h11v11H9zM5 15H4V4h11v1',
  kanban: 'M4 4h5v16H4zM10 4h5v10h-5zM16 4h4v13h-4z',
  shield: 'M12 3l8 3v6c0 5-3.5 8-8 9-4.5-1-8-4-8-9V6z M9 12l2 2 4-4',
  chart: 'M4 20V10M10 20V4M16 20v-8M22 20H2',
  out: 'M9 21H5V3h4M16 17l5-5-5-5M21 12H9',
  check: 'M5 13l4 4L19 7',
};
export function Icon({name}: {name: string}) {
  return <svg className="icon" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden><path d={ICONS[name] || ICONS.doc} /></svg>;
}

/** Right-hand slide-over panel. */
export function Drawer({title, onClose, children}: {title: string; onClose: () => void; children: React.ReactNode}) {
  useEffect(() => { const k = (e: KeyboardEvent) => e.key === 'Escape' && onClose(); window.addEventListener('keydown', k); return () => window.removeEventListener('keydown', k); }, [onClose]);
  return (
    <div className="scrim" onMouseDown={e => e.target === e.currentTarget && onClose()}>
      <div className="drawer" role="dialog" aria-modal aria-label={title}>
        <button className="close" onClick={onClose} aria-label="Close">×</button>
        {children}
      </div>
    </div>
  );
}

export function Confirm({title, text, confirmLabel, danger, onConfirm, onClose}: {title: string; text: string; confirmLabel: string; danger?: boolean; onConfirm: () => void; onClose: () => void}) {
  return (
    <Modal title={title} onClose={onClose}>
      <p className="muted">{text}</p>
      <div className="actions end"><button className="ghost" onClick={onClose}>Cancel</button><button className={danger ? 'danger' : ''} onClick={() => { onConfirm(); onClose(); }}>{confirmLabel}</button></div>
    </Modal>
  );
}
