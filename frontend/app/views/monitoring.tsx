'use client';
import {useState} from 'react';
import {Badge, Empty, ErrorBox, Spinner, call, useApp, useLoad} from '../lib';

const pct = (v: number | null) => v == null ? '—' : Math.round(v * 100) + '%';

export function Fairness() {
  const {auth} = useApp();
  const {data, error, loading, reload} = useLoad<any>(() => call(auth.token, '/api/fairness?weeks=12'), []);
  const [wk, setWk] = useState('');
  if (loading && !data) return <Spinner />;
  if (error) return <ErrorBox msg={error} retry={reload} />;
  if (!data?.weeks.length) return <><Empty title="No screening data yet" hint="Weekly comparisons appear once candidates have been processed." /><Disclaimer note={data?.note} /></>;
  const week = data.weeks.find((w: any) => w.week === wk) || data.weeks[0];
  const low = week.sample_size < data.min_reliable_sample;
  return (
    <>
      <Disclaimer note={data.note} />
      <div className="metrics five">
        <article><span>All-time sample</span><b>{data.sample_size}</b></article>
        <article><span>Recruiter-selected</span><b>{data.recruiter_selected}</b></article>
        <article><span>Avg AI score · all</span><b>{data.average_ai_score ?? '—'}</b></article>
        <article><span>Avg · selected</span><b>{data.selected_average_ai_score ?? '—'}</b></article>
        <article><span>Avg · not selected</span><b>{data.not_selected_average_ai_score ?? '—'}</b></article>
      </div>
      <div className="toolbar"><label className="inline">Week<select value={week.week} onChange={e => setWk(e.target.value)}>{data.weeks.map((w: any) => <option key={w.week} value={w.week}>{w.week} (from {w.starts}) · {w.sample_size} candidates</option>)}</select></label>
        <span>Weekly sample <b>{week.sample_size}</b> · selected <b>{week.selected}</b></span></div>
      {low && <div className="notice warn">Only {week.sample_size} candidate{week.sample_size === 1 ? '' : 's'} this week (below {data.min_reliable_sample}). Treat these comparisons as anecdotal, not statistical.</div>}
      {week.requisitions.map((r: any) => (
        <section className="panel" key={r.requisition_id}>
          <div className="toolbar"><h2>{r.title || 'Requisition'}</h2><span>{r.sample_size} candidate{r.sample_size === 1 ? '' : 's'} · {r.selected} selected</span></div>
          <div className="metrics five">
            <article><span>Overlap with AI top-{r.top_k || 'K'}</span><b>{pct(r.overlap_at_k)}</b></article>
            <article><span>Mean AI rank of selected</span><b>{r.mean_ai_rank_selected ?? '—'}</b></article>
            <article><span>Avg score · selected</span><b>{r.avg_score_selected ?? '—'}</b></article>
            <article><span>Avg score · not selected</span><b>{r.avg_score_not_selected ?? '—'}</b></article>
          </div>
          {r.selected === 0 && <p className="muted">No recruiter selections for this requisition yet, so there is nothing to compare with the AI ranking.</p>}
          <div className="table scroll"><table><thead><tr><th>AI rank</th><th>Candidate</th><th>AI score</th><th>Recruiter</th><th>Stage</th></tr></thead><tbody>
            {r.candidates.map((c: any) => <tr key={c.ref}><td>{c.ai_rank}</td><td>{c.ref}</td><td><span className="bar sm"><i style={{width: c.score + '%'}} /></span> {c.score}</td><td>{c.selected ? <Badge tone="info">selected</Badge> : <small>—</small>}</td><td>{c.stage}</td></tr>)}
          </tbody></table></div>
          {r.differences.length > 0 && <><h3>Ranking differences</h3>{r.differences.map((d: any) => <p className="diff" key={d.ref}><b>{d.ref}</b> · AI rank {d.ai_rank} (score {d.score}) · {d.kind}</p>)}</>}
        </section>))}
    </>
  );
}

function Disclaimer({note}: {note?: string}) {
  return <div className="notice">{note || 'Monitoring only; this does not prove the AI is unbiased.'} Candidates are shown by pseudonymous reference. Ranking differences are prompts for human review, not findings of bias.</div>;
}
