/* ── Bet Lab ──────────────────────────────────────────────────────────────────
   The four SGP modes, wired to the real endpoints. Every one of them answers 501
   today, and this page shows exactly that instead of a mock result.

   The reason it looks like this rather than a spinner-to-nowhere: an SGP price
   needs a joint distribution, the joint distribution needs the drive-level
   simulator, and the simulator has not been calibrated. A number rendered here
   before then would be invented, which is the one thing this product cannot do.
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
  { id: 'critique', label: 'Critique a slip', icon: Icon.Whistle,
    blurb: 'Paste the legs you built elsewhere. The engine flags the ones fighting each other and the ones priced too short.',
    call: (ctx) => api.sgpCritique({ ...ctx, legs: [] }) },
];

export default function BetLab() {
  const { league } = useApp();
  const [mode, setMode] = useState(MODES[0]);
  const [gameId, setGameId] = useState('');
  const [attempt, setAttempt] = useState(0);

  const games = useApi(`games:${league}:upcoming`,
    (s) => api.listGames(league, { upcoming: true, limit: 40, odds: false }, { signal: s }),
    { ttl: 120_000 });

  const run = useApi(
    attempt ? `sgp:${mode.id}:${gameId}:${attempt}` : null,
    () => mode.call({ league, game_id: gameId, sportsbook: 'draftkings', risk_mode: 'balanced' }),
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
        <strong>These modes are not live.</strong> Pricing a same-game parlay requires the
        joint distribution that only the drive-level simulator produces, and no model has been
        trained or calibrated yet. Running a mode below calls the real endpoint and shows you
        its real answer — a 501 with the phase it is waiting on. Nothing here is simulated for
        show. In the meantime, the{' '}
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
            <button className="btn btn-primary" disabled={!gameId || run.loading}
              onClick={() => setAttempt((a) => a + 1)}>
              {run.loading ? <><span className="spinner" /> Running</> : <><Icon.Bolt size={14} /> Run {mode.label.toLowerCase()}</>}
            </button>
          </div>

          {games.loading && <Loading rows={1} height={40} />}
          {!games.loading && !games.data?.games?.length && (
            <Empty icon={Icon.Slate} title="No upcoming games"
              body="There is nothing scheduled to run a mode against in this league." />
          )}

          {attempt > 0 && run.loading && <Loading rows={2} height={64} />}
          {attempt > 0 && run.notBuilt && <PhaseGate error={run.notBuilt} title={`${mode.label} is not implemented`} />}
          {attempt > 0 && run.error && !run.notBuilt && <ErrorState error={run.error} />}
          {attempt > 0 && run.data && (
            <pre className="card-pad num small" style={{ overflow: 'auto', margin: 0 }}>
              {JSON.stringify(run.data, null, 2)}
            </pre>
          )}
        </div>
      </Card>

      <Section title="What has to land first" sub="In order. Each depends on the one before it.">
        <div className="grid grid-auto">
          {[
            ['01', 'Drive-level simulator', 'Monte Carlo over drives, priors from the tendency surfaces already built.'],
            ['02', 'Calibration backtest', 'Against 2023–25 closing lines. Until it calibrates, a model probability is not evidence.'],
            ['03', 'Correlation from the sim', 'Leg-to-leg dependence read off the joint distribution rather than asserted.'],
            ['04', 'SGP pricing', 'Compare the combined fair price to the book quote. This is the first honest edge number.'],
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
