/* ── Game detail ──────────────────────────────────────────────────────────────
   One matchup, three things: the conditions it will be played in, the two units
   facing each other, and every book's price plus how each line has moved.

   The unit comparison is the point. Two team cards side by side, ranked against
   the same field, is the fastest honest read on a game that exists before the
   simulator lands.
── */

import React, { useMemo } from 'react';
import { Link, useParams } from 'react-router-dom';
import Icon from '../icons';
import * as api from '../lib/api';
import { useApi } from '../lib/hooks';
import { useTrackVisit } from '../lib/store';
import { american, kickoffFull, pct, relativeTime, spread } from '../lib/format';
import { Card, CardHead, Empty, ErrorState, Loading, Notice, RankBar, Section, Stat } from '../components/ui';

/* The Game Tag Surface. Two claims, kept visibly apart: how this game tends to
   go given its line, and what each side tends to do. Neither is a projection —
   both are counts, and the sample and conditioning level travel with every
   number so a league average is never mistaken for a read on this game. */
function ScriptSurface({ data }) {
  const scripts = (data.scripts || []).filter((s) => s.probability > 0);
  if (!scripts.length && !(data.teams || []).some((t) => t.tendencies?.length)) return null;
  const pct = (x) => `${(x * 100).toFixed(0)}%`;
  return (
    <Section title="Script surface"
      sub={`How games with this line have gone, and what each side tends to do. ${
        data.spread != null ? `Line ${data.spread > 0 ? '+' : ''}${data.spread} / ${data.total}` : ''}`}>
      <div className="grid grid-auto" style={{ gap: 12 }}>
        <Card className="card-pad col" style={{ gap: 10 }}>
          <span className="small muted">Likely shape</span>
          {scripts.map((s) => {
            /* Lift is the honest part: without it a 32% sitting on a 31% base
               reads like a finding instead of the league average. */
            const strong = s.lift_vs_base != null && Math.abs(s.lift_vs_base - 1) >= 0.25;
            return (
              <div key={s.script} className="col" style={{ gap: 3 }}>
                <span className="row" style={{ gap: 8 }}>
                  <strong style={{ fontSize: 12.5 }}>{s.script}</strong>
                  <span style={{ flex: 1 }} />
                  <span className="num" style={{ fontSize: 12.5 }}>{pct(s.probability)}</span>
                </span>
                <div style={{ height: 4, background: 'var(--surface-2)', borderRadius: 2 }}>
                  <div style={{ width: `${Math.min(100, s.probability * 200)}%`, height: '100%',
                    borderRadius: 2,
                    background: strong ? 'var(--accent)' : 'var(--text-faint)' }} />
                </div>
                <span className="small muted">
                  league {pct(s.league_base_rate)}
                  {s.lift_vs_base != null && <> · {s.lift_vs_base}× </>}
                  · n={s.n} · {s.basis}
                </span>
              </div>
            );
          })}
        </Card>

        {(data.teams || []).map((t) => (
          <Card key={t.side} className="card-pad col" style={{ gap: 8 }}>
            <span className="small muted">{t.name} · last {t.games} games</span>
            {t.tendencies?.length ? t.tendencies.map((d) => (
              <span key={d.diagnostic} className="row" style={{ gap: 8 }}>
                <span style={{ fontSize: 12.5 }}>{d.diagnostic}</span>
                <span style={{ flex: 1 }} />
                <span className="num small">{pct(d.rate)}</span>
                <span className="small muted" style={{ minWidth: 44, textAlign: 'right' }}>
                  {d.n}/{d.of}
                </span>
              </span>
            )) : <Empty icon={Icon.Activity} title="No diagnosed games yet"
                   body="This team has no finished games in the window." />}
          </Card>
        ))}
      </div>
      <div className="small muted" style={{ marginTop: 10, lineHeight: 1.55 }}>
        {data.basis_note}
      </div>
    </Section>
  );
}

export default function GameDetail() {
  const { league, gameId } = useParams();

  const game = useApi(`game:${gameId}`, (s) => api.getGame(league, gameId, { signal: s }));
  const odds = useApi(`odds:${gameId}`, (s) => api.getGameOdds(league, gameId, {}, { signal: s }));
  const scripts = useApi(`scripts:${gameId}`, (s) => api.getGameScripts(league, gameId, { signal: s }));

  const g = game.data;
  useTrackVisit(g && {
    id: g.game_id, kind: 'game',
    label: `${g.away.abbr} @ ${g.home.abbr}`,
    to: `/games/${league}/${encodeURIComponent(g.game_id)}`,
  });

  if (game.loading) return <Loading rows={3} height={140} />;
  if (game.error) return <ErrorState error={game.error} onRetry={game.refetch} />;
  if (!g) return null;

  const cond = g.conditions || {};
  const final = g.status === 'final';

  return (
    <>
      <div className="page-head">
        <div style={{ minWidth: 0 }}>
          <div className="eyebrow">
            {league.toUpperCase()} · {g.season}
            {g.week ? ` · Week ${g.week}` : ''}
            {g.season_type === 'postseason' ? ' · Postseason' : ''}
          </div>
          <h1 style={{ marginTop: 4 }}>{g.away.name} at {g.home.name}</h1>
          <div className="sub row" style={{ gap: 8 }}>
            <span>{kickoffFull(g.kickoff)}</span>
            {g.notes && <span className="badge accent">{g.notes}</span>}
            {g.neutral_site && <span className="badge">Neutral site</span>}
            {final && (
              <span className="badge">
                Final {g.away.abbr} {g.away.score} — {g.home.abbr} {g.home.score}
              </span>
            )}
          </div>
        </div>
      </div>

      <Conditions cond={cond} />

      {scripts.data && <ScriptSurface data={scripts.data} />}

      <Section title="Unit matchup" sub="Both teams ranked against the same league field, 2023–2025.">
        <div className="grid" style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(330px, 1fr))' }}>
          <TeamPanel league={league} team={g.away} side="Away" />
          <TeamPanel league={league} team={g.home} side="Home" />
        </div>
      </Section>

      <Section title="The board" sub="Every book quoting this game. fair_prob is the price with the vig removed.">
        {odds.loading && <Loading rows={2} height={90} />}
        {odds.error && <ErrorState error={odds.error} onRetry={odds.refetch} />}
        {odds.data && <OddsBoard board={odds.data} home={g.home} away={g.away} />}
      </Section>

      <Notice>
        Edge is a model probability minus <strong>fair_prob</strong>, never minus the raw
        implied price — that overstates it by exactly the hold. No model probability exists
        yet, so this page quotes the market and stops there.
      </Notice>
    </>
  );
}

function Conditions({ cond }) {
  const items = [
    cond.venue && { icon: Icon.Field, label: 'Venue', value: cond.venue,
      sub: [cond.city, cond.state].filter(Boolean).join(', ') || null },
    cond.roof && { icon: Icon.Dome, label: 'Roof', value: cond.roof },
    cond.surface && { icon: Icon.Field, label: 'Surface', value: cond.surface },
    // A null temp means "not reported" — CFBD's weather feed is paywalled — so the
    // tile is only rendered when there is a real reading behind it.
    cond.temp != null && { icon: Icon.Thermometer, label: 'Temp', value: `${Math.round(cond.temp)}°F` },
    cond.wind != null && { icon: Icon.Wind, label: 'Wind', value: `${Math.round(cond.wind)} mph` },
    cond.elevation != null && { icon: Icon.Mountain, label: 'Elevation',
      value: `${Math.round(cond.elevation)} m` },
  ].filter(Boolean);

  if (!items.length) return null;

  return (
    <div className="grid grid-stat stagger">
      {items.map((it) => (
        <div key={it.label} className="stat-tile row" style={{ gap: 10 }}>
          <span className="muted" style={{ display: 'grid' }}><it.icon size={17} /></span>
          <div className="stat" style={{ minWidth: 0 }}>
            <span className="stat-label">{it.label}</span>
            <span className="stat-value sm truncate" style={{ textTransform: 'capitalize' }}>{it.value}</span>
            {it.sub && <span className="stat-sub truncate">{it.sub}</span>}
          </div>
        </div>
      ))}
    </div>
  );
}

function TeamPanel({ league, team, side }) {
  const off = useApi(`off:${team.team_id}`, (s) => api.getOffense(league, team.team_id, {}, { signal: s }));
  const def = useApi(`def:${team.team_id}`, (s) => api.getDefense(league, team.team_id, {}, { signal: s }));

  const body = () => {
    if (off.loading || def.loading) return <div className="card-pad"><Loading rows={2} height={54} /></div>;
    if (off.error && def.error) {
      return <div className="card-pad"><ErrorState error={off.error} /></div>;
    }
    const o = off.data, d = def.data;
    const of_ = o?.teams_ranked || d?.teams_ranked;
    return (
      <div className="card-pad col" style={{ gap: 16 }}>
        {o && (
          <div className="col" style={{ gap: 10 }}>
            <div className="eyebrow">Offense</div>
            <RankBar label="Pass EPA / dropback" value={o.pass_offense?.epa}
              rank={o.pass_offense?.rank} of={of_} leagueAvg={o.pass_offense?.league_avg} />
            <RankBar label="Run EPA / rush" value={o.run_offense?.epa}
              rank={o.run_offense?.rank} of={of_} leagueAvg={o.run_offense?.league_avg} />
            <div className="row wrap" style={{ gap: 14 }}>
              <Stat label="Pass success" value={pct(o.pass_offense?.success_rate)} size="sm" />
              <Stat label="Explosive" value={pct(o.pass_offense?.explosive_rate)} size="sm" />
              {o.situational?.rz_td_rate != null && (
                <Stat label="Red zone TD" value={pct(o.situational.rz_td_rate)} size="sm" />
              )}
            </div>
          </div>
        )}
        {d && (
          <div className="col" style={{ gap: 10 }}>
            <div className="eyebrow">Defense</div>
            <RankBar label="Pass EPA allowed" value={d.pass_defense?.epa_allowed}
              rank={d.pass_defense?.rank} of={of_} leagueAvg={d.pass_defense?.league_avg} />
            <RankBar label="Run EPA allowed" value={d.run_defense?.epa_allowed}
              rank={d.run_defense?.rank} of={of_} leagueAvg={d.run_defense?.league_avg} />
          </div>
        )}
        {!o && !d && <Empty title="No unit data" body="This team has no plays loaded for the default seasons." />}
      </div>
    );
  };

  return (
    <Card>
      <CardHead
        title={team.name}
        sub={`${side} · ${team.abbr}`}
        icon={Icon.Shield}
        action={
          <Link className="btn btn-sm btn-ghost" to={`/teams/${league}/${encodeURIComponent(team.team_id)}`}>
            Team page <Icon.ChevronRight size={13} />
          </Link>
        }
      />
      {body()}
    </Card>
  );
}

function OddsBoard({ board, home, away }) {
  const books = board.books || [];

  // Line movement: first and latest snapshot per (book, market, outcome). Opening
  // price is where the book started, not a consensus open.
  const moves = useMemo(() => {
    const seen = new Map();
    for (const m of board.movement || []) {
      const k = `${m.bookmaker}|${m.market_key}|${m.outcome}`;
      if (!seen.has(k)) seen.set(k, { first: m, last: m, n: 1 });
      else { const e = seen.get(k); e.last = m; e.n += 1; }
    }
    return seen;
  }, [board.movement]);

  if (!books.length) {
    return <Card><Empty icon={Icon.Odds} title="No prices stored"
      body="No bookmaker has been polled for this game yet. Run the odds poller to populate it." /></Card>;
  }

  const drift = (book, market, outcome) => {
    const e = moves.get(`${book}|${market}|${outcome}`);
    if (!e || e.n < 2) return null;
    const a = e.first.line ?? e.first.price_american;
    const b = e.last.line ?? e.last.price_american;
    if (a == null || b == null || a === b) return null;
    return b - a;
  };

  return (
    <Card>
      <div className="table-scroll">
        <table className="data">
          <thead>
            <tr>
              <th>Book</th>
              <th>{away.abbr} spread</th>
              <th>{home.abbr} spread</th>
              <th>Total</th>
              <th>{away.abbr} ML</th>
              <th>{home.abbr} ML</th>
              <th>Fair {away.abbr}</th>
              <th>Updated</th>
            </tr>
          </thead>
          <tbody>
            {books.map((b) => {
              const d = drift(b.bookmaker, 'spreads', home.name);
              return (
                <tr key={b.bookmaker}>
                  <td>
                    <span className="row" style={{ gap: 6 }}>
                      <span className={`pulse-dot ${b.is_live_book ? 'live' : ''}`}
                        style={!b.is_live_book ? { background: 'var(--text-faint)' } : undefined} />
                      {b.bookmaker}
                      {!b.is_live_book && <span className="badge warn">archive</span>}
                    </span>
                  </td>
                  <td className="num">
                    {spread(b.spread?.away?.line)}
                    <span className="muted"> {american(b.spread?.away?.price_american)}</span>
                  </td>
                  <td className="num">
                    {spread(b.spread?.home?.line)}
                    <span className="muted"> {american(b.spread?.home?.price_american)}</span>
                    {d != null && (
                      <span className={d < 0 ? ' good' : ' bad'} title="Movement since this book opened">
                        {' '}{d > 0 ? '↑' : '↓'}{Math.abs(d).toFixed(1)}
                      </span>
                    )}
                  </td>
                  <td className="num">
                    {b.total?.over?.line ?? '—'}
                    <span className="muted"> {american(b.total?.over?.price_american)}</span>
                  </td>
                  <td className="num">{american(b.moneyline?.away?.price_american)}</td>
                  <td className="num">{american(b.moneyline?.home?.price_american)}</td>
                  <td className="num accent">{pct(b.moneyline?.away?.fair_prob)}</td>
                  <td className="num muted">{relativeTime(b.captured_at)}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <div className="card-pad tiny muted" style={{ borderTop: '1px solid var(--border-soft)' }}>
        {board.movement?.length || 0} snapshots stored for this game. Arrows show how each
        book's home spread has moved since its first snapshot.
      </div>
    </Card>
  );
}
