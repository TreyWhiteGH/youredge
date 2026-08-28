/* ── Bet Lab ──────────────────────────────────────────────────────────────────
   The four SGP modes, wired to the real endpoints.

   Critique is live. It runs on counted history — how often these legs actually
   won together — plus de-vigged market prices, and needs no simulator. It shows
   per-leg edge against the sharpest book, which legs are the same bet twice, and
   which want the game to go in different directions.

   It does not show a combined price, and the absence is the point. Pricing a
   parlay needs this game's joint distribution; multiplying historical base rates
   would render a number that looks like a price and is not one. The other three
   modes still answer 501 for the same reason, and this page shows that answer
   rather than a mock.
── */

import React, { useState } from 'react';
import { Link } from 'react-router-dom';
import Icon from '../icons';
import * as api from '../lib/api';
import { useApi } from '../lib/hooks';
import { useApp } from '../lib/store';
import { kickoffFull } from '../lib/format';
import { Card, CardHead, Empty, ErrorState, Loading, Notice, PhaseGate, Section } from '../components/ui';

const MODES = [
  { id: 'generate', label: 'Generate', icon: Icon.Bolt,
    blurb: 'Pick a game; the engine proposes the same-game combinations whose legs reinforce one script.',
    call: (ctx) => api.sgpGenerate(ctx) },
  { id: 'anchor', label: 'Build around a pick', icon: Icon.Layers,
    blurb: 'Start from a leg you already like. The engine conditions on it and finds what correlates — or tells you the anchor itself is −EV.',
    call: (ctx) => api.sgpAnchor({ ...ctx, anchor: '' }) },
  { id: 'hypothesis', label: 'Test a hypothesis', icon: Icon.Activity,
    blurb: '"Does this defense fade in the fourth?" becomes a query over 635k plays, not an opinion.',
    call: (ctx) => api.sgpHypothesis({ ...ctx, hypothesis: '' }) },
  { id: 'critique', label: 'Critique a slip', icon: Icon.Whistle, live: true,
    blurb: 'Paste the legs you built elsewhere. The engine flags the ones fighting each other and the ones priced too short.',
    call: (ctx) => api.sgpCritique(ctx) },
];

/* Renders what Critique actually knows. Two rules from FRONTEND.md apply hard
   here: a null is an em dash and never a zero, and a sample size travels with
   every rate — a correlation over 40 games is a rumour and must not look like a
   finding. */
const VERDICT = {
  redundant:       { tone: 'warn', label: 'Redundant',       hint: 'These are close to the same bet. The second leg lengthens the price without adding much that can independently fail.' },
  script_conflict: { tone: 'warn', label: 'Script conflict', hint: 'These want the game to go in different directions. Both can land, but the slip is fighting itself.' },
  correlated:      { tone: 'ok',   label: 'Correlated',      hint: 'These move together. That is what a same-game parlay is for — and what a book charges you for.' },
  independent:     { tone: 'mute', label: 'Independent',     hint: 'No meaningful relationship in the sample.' },
  no_sample:       { tone: 'mute', label: 'No sample',       hint: 'Not enough games where both were on the board to say anything.' },
};

function CritiqueResult({ data }) {
  const legs = data.legs || [];
  return (
    <div className="col" style={{ gap: 16 }}>
      {data.unparsed_legs?.length > 0 && (
        <Notice tone="warn" icon={Icon.Alert}>
          <strong>Not read:</strong> {data.unparsed_legs.join(', ')}. These were left out rather
          than guessed at — a leg matched to the wrong market would corrupt every check below it.
        </Notice>
      )}

      <div className="col" style={{ gap: 8 }}>
        <div className="small muted">Per leg, against the sharpest book quoting it</div>
        <div style={{ overflowX: 'auto' }}>
          <table className="table num small">
            <thead><tr>
              <th style={{ textAlign: 'left' }}>Leg</th><th>Your book</th><th>Fair</th>
              <th>Edge</th><th style={{ textAlign: 'left' }}>Anchor</th>
            </tr></thead>
            <tbody>
              {legs.map((l) => {
                const p = l.pricing || {};
                const edge = p.quotable && p.edge != null ? p.edge : null;
                return (
                  <tr key={l.raw}>
                    <td style={{ textAlign: 'left' }}>{l.raw}</td>
                    <td>{p.book_price != null ? (p.book_price > 0 ? `+${p.book_price}` : p.book_price) : '—'}</td>
                    <td>{p.fair_prob != null ? `${(p.fair_prob * 100).toFixed(1)}%` : '—'}</td>
                    <td style={{ color: edge == null ? undefined : edge > 0 ? 'var(--pos)' : 'var(--neg)' }}>
                      {edge == null ? '—' : `${edge > 0 ? '+' : ''}${(edge * 100).toFixed(1)}%`}
                    </td>
                    <td style={{ textAlign: 'left' }} className="muted">{p.anchor_book || '—'}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
        <div className="small muted" style={{ lineHeight: 1.55 }}>
          Edge is the de-vigged sharp price minus what your book is paying, never minus the raw
          implied price — that overstates it by exactly the hold. A dash means the leg was not
          priced at your book, or the line is too stale to quote.
        </div>
      </div>

      <div className="col" style={{ gap: 8 }}>
        <div className="small muted">Leg against leg, counted over finished games</div>
        {(data.pairs || []).map((pr, i) => {
          const v = VERDICT[pr.verdict] || VERDICT.independent;
          return (
            <div key={i} className="card card-pad col" style={{ gap: 4 }}>
              <span className="row" style={{ gap: 8, flexWrap: 'wrap' }}>
                <strong style={{ fontSize: 13 }}>{pr.legs[0]}</strong>
                <span className="muted">×</span>
                <strong style={{ fontSize: 13 }}>{pr.legs[1]}</strong>
                <span style={{ flex: 1 }} />
                <span className={`pill pill-${v.tone}`}>{v.label}</span>
              </span>
              <span className="small muted">
                {pr.phi != null
                  ? <>correlation {pr.phi > 0 ? '+' : ''}{pr.phi} · both landed {(pr.p_both * 100).toFixed(0)}% of the time · n={pr.n}</>
                  : <>n={pr.n ?? 0}</>}
              </span>
              <span className="small muted" style={{ lineHeight: 1.55 }}>{v.hint}</span>
            </div>
          );
        })}
      </div>

      {data.script_sensitivity?.length > 0 && (
        <div className="col" style={{ gap: 8 }}>
          <div className="small muted">
            How the first pair behaves inside each script — where a relationship changes, the
            slip depends on the game taking that shape
          </div>
          <div style={{ overflowX: 'auto' }}>
            <table className="table num small">
              <thead><tr><th style={{ textAlign: 'left' }}>Script</th><th>Correlation</th><th>Games</th></tr></thead>
              <tbody>
                {data.script_sensitivity.map((s) => (
                  <tr key={s.script}>
                    <td style={{ textAlign: 'left' }}>{s.script}</td>
                    <td>{s.phi > 0 ? '+' : ''}{s.phi}</td>
                    <td>{s.n}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      <Notice tone="mute" icon={Icon.Lock}>
        <strong>No combined price.</strong> {data.combined_price_unavailable}
      </Notice>
    </div>
  );
}

export default function BetLab() {
  const { league } = useApp();
  const [mode, setMode] = useState(MODES[0]);
  const [gameId, setGameId] = useState('');
  const [attempt, setAttempt] = useState(0);
  const [legsText, setLegsText] = useState('');
  const [quotedOdds, setQuotedOdds] = useState('');

  // One leg per line, blanks dropped. The engine parses these itself for now;
  // richer phrasing is the narrator's job once Phase 3 lands.
  const legs = legsText.split('\n').map((l) => l.trim()).filter(Boolean);

  const games = useApi(`games:${league}:upcoming`,
    (s) => api.listGames(league, { upcoming: true, limit: 40, odds: false }, { signal: s }),
    { ttl: 120_000 });

  const run = useApi(
    attempt ? `sgp:${mode.id}:${gameId}:${attempt}` : null,
    () => mode.call({
      league, game_id: gameId, sportsbook: 'draftkings', risk_mode: 'balanced',
      legs, quoted_odds: quotedOdds || null,
    }),
    { ttl: 0 },
  );

  return (
    <>
      <div className="page-head">
        <div>
          <h1 className="row"><span className="accent" style={{ display: 'grid' }}><Icon.Lab size={22} /></span> Bet Lab</h1>
          <div className="sub">Same-game parlay analysis. Correlation, script coherence, and price versus fair value.</div>
        </div>
      </div>

      <Notice tone="warn" icon={Icon.Lock}>
        <strong>Critique is live; the other three are not.</strong> Critique runs on counted
        history and de-vigged prices, so it can tell you which legs are redundant, which fight
        each other, and what each one is worth against the sharpest book — all with the number
        of games behind every claim. It will not quote you a combined price: that needs the
        joint distribution only the simulator produces, and no model has been calibrated. The
        other modes call the real endpoint and show its real answer — a 501 with the phase it
        is waiting on. In the meantime, the{' '}
        <Link to="/slate" className="accent"><strong>slate</strong></Link>,{' '}
        <Link to="/teams" className="accent"><strong>team cards</strong></Link> and{' '}
        <Link to="/compare" className="accent"><strong>compare</strong></Link> run on data that
        is fully loaded.
      </Notice>

      <Section title="Mode">
        <div className="grid grid-auto stagger">
          {MODES.map((m) => (
            <button key={m.id} className="card card-link card-pad col"
              style={{ gap: 8, textAlign: 'left',
                borderColor: mode.id === m.id ? 'var(--accent-edge)' : undefined,
                background: mode.id === m.id ? 'var(--accent-wash)' : undefined }}
              onClick={() => { setMode(m); setAttempt(0); }}>
              <span className="row">
                <span className={mode.id === m.id ? 'accent' : 'muted'} style={{ display: 'grid' }}>
                  <m.icon size={18} />
                </span>
                <strong style={{ fontSize: 13.5 }}>{m.label}</strong>
                {mode.id === m.id && <><span style={{ flex: 1 }} /><Icon.Check size={15} /></>}
              </span>
              <span className="small muted" style={{ lineHeight: 1.55 }}>{m.blurb}</span>
            </button>
          ))}
        </div>
      </Section>

      <Card>
        <CardHead title={mode.label} sub={`${league.toUpperCase()} · balanced risk · DraftKings`} icon={mode.icon} />
        <div className="card-pad col" style={{ gap: 12 }}>
          <div className="row wrap" style={{ gap: 10 }}>
            <select className="input" style={{ maxWidth: 380 }} value={gameId}
              onChange={(e) => { setGameId(e.target.value); setAttempt(0); }}>
              <option value="">Select a game…</option>
              {(games.data?.games || []).map((g) => (
                <option key={g.game_id} value={g.game_id}>
                  {g.away.abbr} @ {g.home.abbr} — {kickoffFull(g.kickoff)}
                </option>
              ))}
            </select>
            <button className="btn btn-primary"
              disabled={!gameId || run.loading || (mode.id === 'critique' && legs.length < 1)}
              onClick={() => setAttempt((a) => a + 1)}>
              {run.loading ? <><span className="spinner" /> Running</> : <><Icon.Bolt size={14} /> Run {mode.label.toLowerCase()}</>}
            </button>
          </div>

          {mode.id === 'critique' && (
            <div className="col" style={{ gap: 8 }}>
              <textarea className="input" rows={4} value={legsText}
                placeholder={'One leg per line, e.g.\nSEA -3.5\nover 44.5\nSEA team total over 24.5'}
                onChange={(e) => { setLegsText(e.target.value); setAttempt(0); }} />
              <div className="row wrap" style={{ gap: 10 }}>
                <input className="input" style={{ maxWidth: 200 }} value={quotedOdds}
                  placeholder="Your book's SGP price (e.g. +450)"
                  onChange={(e) => setQuotedOdds(e.target.value)} />
                <span className="small muted" style={{ lineHeight: 1.5 }}>
                  Optional, and stored rather than used: no API sells same-game parlay quotes,
                  so collecting real ones is how a book's correlation haircut becomes
                  measurable later.
                </span>
              </div>
            </div>
          )}

          {games.loading && <Loading rows={1} height={40} />}
          {!games.loading && !games.data?.games?.length && (
            <Empty icon={Icon.Slate} title="No upcoming games"
              body="There is nothing scheduled to run a mode against in this league." />
          )}

          {attempt > 0 && run.loading && <Loading rows={2} height={64} />}
          {attempt > 0 && run.notBuilt && <PhaseGate error={run.notBuilt} title={`${mode.label} is not implemented`} />}
          {attempt > 0 && run.error && !run.notBuilt && <ErrorState error={run.error} />}
          {attempt > 0 && run.data && mode.id === 'critique' && <CritiqueResult data={run.data} />}
          {attempt > 0 && run.data && mode.id !== 'critique' && (
            <pre className="card-pad num small" style={{ overflow: 'auto', margin: 0 }}>
              {JSON.stringify(run.data, null, 2)}
            </pre>
          )}
        </div>
      </Card>

      <Section title="What has to land first" sub="In order. Each depends on the one before it.">
        <div className="grid grid-auto">
          {[
            ['01', 'Empirical joint — done', 'How often legs actually won together, sliced by script. Critique runs on this.'],
            ['02', 'Drive-level simulator', 'Monte Carlo over drives, anchored so its spread and total match the market by construction.'],
            ['03', 'Calibration gates', 'Against 2023–25 closing lines, and against the empirical surface above — two independent estimates that must agree.'],
            ['04', 'SGP pricing', 'Only once the sim clears those gates does a combined fair price mean anything.'],
          ].map(([n, title, body]) => (
            <Card key={n} className="card-pad col" style={{ gap: 6 }}>
              <span className="num" style={{ color: 'var(--text-faint)', fontWeight: 800, fontSize: 12 }}>{n}</span>
              <strong style={{ fontSize: 13 }}>{title}</strong>
              <span className="small muted" style={{ lineHeight: 1.55 }}>{body}</span>
            </Card>
          ))}
        </div>
      </Section>

      <Notice>
        YourEdge produces probability-based analysis, not guarantees. <strong>No bet is a valid
        outcome</strong> — and it is the one the engine returns most often when a price is short.
        Avoid chasing losses or sizing up because a payout looks large.
      </Notice>
    </>
  );
}
