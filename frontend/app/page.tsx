'use client';
import {FormEvent, useCallback, useEffect, useState} from 'react';
import {API, Auth, Ctx, setUnauthorizedHandler} from './lib';
import Recruiter from './recruiter';
import ClientPortal from './client';
import {Fairness} from './views/monitoring';

const KEY = 'talentra.session';

export default function Home() {
  const [auth, setAuth] = useState<Auth | null>(null);
  const [ready, setReady] = useState(false);
  const [toastMsg, setToastMsg] = useState<{m: string; bad?: boolean} | null>(null);
  const signOut = useCallback(() => { try { sessionStorage.removeItem(KEY); } catch {} setAuth(null); }, []);
  const toast = useCallback((m: string, bad = false) => { setToastMsg({m, bad}); setTimeout(() => setToastMsg(null), 4000); }, []);

  useEffect(() => {
    setUnauthorizedHandler(signOut);
    try { const s = sessionStorage.getItem(KEY); if (s) setAuth(JSON.parse(s)); } catch {}
    setReady(true);
  }, [signOut]);

  if (!ready) return null;
  if (!auth) return <Login onAuth={a => { try { sessionStorage.setItem(KEY, JSON.stringify(a)); } catch {} setAuth(a); }} />;
  return (
    <Ctx.Provider value={{auth, toast}}>
      {toastMsg && <div className={'flash ' + (toastMsg.bad ? 'bad' : '')} role="status">{toastMsg.m}</div>}
      {auth.role === 'CLIENT' ? <ClientPortal out={signOut} /> : auth.role === 'DELIVERY_HEAD' ? <DeliveryHead out={signOut} /> : <Recruiter out={signOut} />}
    </Ctx.Provider>
  );
}

function DeliveryHead({out}: {out: () => void}) {
  return (
    <main className="client wide">
      <header className="top"><div><p className="eyebrow">DELIVERY HEAD</p><h1>Screening monitoring</h1></div><button onClick={out}>Sign out</button></header>
      <Fairness />
    </main>
  );
}

function Login({onAuth}: {onAuth: (a: Auth) => void}) {
  const [email, setEmail] = useState(''), [password, setPassword] = useState(''), [err, setErr] = useState(''), [busy, setBusy] = useState(false);
  async function submit(e: FormEvent) {
    e.preventDefault(); setBusy(true); setErr('');
    try {
      const r = await fetch(API + '/api/auth/login', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({email, password})});
      if (!r.ok) { setErr(r.status === 429 ? 'Too many attempts. Try again in a few minutes.' : 'Check your email and password.'); return; }
      const x = await r.json(); onAuth({token: x.access_token, role: x.role, email: x.email, org: x.org});
    } catch { setErr('Cannot reach the Talentra API. Check that the backend is running.'); }
    finally { setBusy(false); }
  }
  return (
    <main className="login">
      <section><p className="eyebrow">TALENTRA / SCREENING OS</p><h1>Decisions with evidence.</h1><p>AI-assisted candidate screening for teams that need clarity, speed, and control.</p></section>
      <form onSubmit={submit}>
        <h2>Welcome back</h2>
        <label>Email<input type="email" autoComplete="username" required value={email} onChange={e => setEmail(e.target.value)} /></label>
        <label>Password<input type="password" autoComplete="current-password" required value={password} onChange={e => setPassword(e.target.value)} /></label>
        {err && <small className="error" role="alert">{err}</small>}
        <button disabled={busy}>{busy ? 'Signing in…' : 'Sign in'}</button>
        <p className="hint">Local demo data only (see README for the demo accounts). Disable it in production with SEED_DEMO=0.</p>
      </form>
    </main>
  );
}
