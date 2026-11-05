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

const DEMOS: [string, string, string][] = [
  ['Recruiter', 'recruiter@talentra.demo', 'Screen CVs, review evidence, submit'],
  ['Client (Acme)', 'client@acme.demo', 'Shortlist, reject, propose interviews'],
  ['Client (Globex)', 'client@globex.demo', 'Sees nothing from Acme (isolation)'],
  ['Delivery head', 'head@talentra.demo', 'Weekly AI vs recruiter comparison'],
];

function Login({onAuth}: {onAuth: (a: Auth) => void}) {
  const [email, setEmail] = useState(''), [password, setPassword] = useState(''), [err, setErr] = useState(''), [busy, setBusy] = useState(false), [show, setShow] = useState(false), [demo, setDemo] = useState(false);
  useEffect(() => {
    if (process.env.NEXT_PUBLIC_DEMO_LOGINS === '0') return;
    fetch(API + '/api/health').then(r => r.json()).then(j => setDemo(!!j.demo)).catch(() => {});
  }, []);
  async function signIn(em: string, pw: string) {
    setBusy(true); setErr('');
    try {
      const r = await fetch(API + '/api/auth/login', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({email: em, password: pw})});
      if (!r.ok) { setErr(r.status === 429 ? 'Too many attempts. Try again in a few minutes.' : 'Check your email and password.'); return; }
      const x = await r.json(); onAuth({token: x.access_token, role: x.role, email: x.email, org: x.org});
    } catch { setErr('Cannot reach the Talentra API. Check that the backend is running.'); }
    finally { setBusy(false); }
  }
  const submit = (e: FormEvent) => { e.preventDefault(); signIn(email, password); };
  return (
    <main className="login">
      <section>
        <p className="eyebrow">TALENTRA</p>
        <h1>Decisions with evidence.</h1>
        <p className="lead">Rank CVs against a scorecard. Every score shows the line in the CV it came from, and nobody is rejected automatically.</p>
        <ul className="points"><li>Bulk-screen up to 500 CVs, including scans</li><li>Clients review masked profiles on any device</li><li>Consent, deletion and access history built in</li></ul>
      </section>
      <div className="logincol">
        <form onSubmit={submit}>
          <h2>Sign in</h2>
          <label>Email<input type="email" autoComplete="username" required value={email} onChange={e => setEmail(e.target.value)} /></label>
          <label>Password<span className="pw"><input type={show ? 'text' : 'password'} autoComplete="current-password" required value={password} onChange={e => setPassword(e.target.value)} /><button type="button" className="ghost" onClick={() => setShow(!show)} aria-label={show ? 'Hide password' : 'Show password'}>{show ? 'Hide' : 'Show'}</button></span></label>
          {err && <small className="error" role="alert">{err}</small>}
          <button disabled={busy}>{busy ? 'Signing in…' : 'Sign in'}</button>
        </form>
        {demo && (
          <div className="demo">
            <p><b>Try the demo</b><small>Synthetic data. One click signs you in.</small></p>
            {DEMOS.map(([name, em, what]) => <button key={em} type="button" className="demobtn" disabled={busy} onClick={() => signIn(em, 'DemoPass123!')}><b>{name}</b><small>{what}</small></button>)}
          </div>)}
      </div>
    </main>
  );
}
