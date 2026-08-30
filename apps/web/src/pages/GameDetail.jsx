/* ── Game detail ──────────────────────────────────────────────────────────────
   One matchup, three things: the conditions it will be played in, the two units
   facing each other, and every book's price plus how each line has moved.

   The unit comparison is the point. Two team cards side by side, ranked against
   the same field, is the fastest honest read on a game that exists before the
   simulator lands.
── */

import React, { useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import Icon from '../icons';
import * as api from '../lib/api';
import { useApi } from '../lib/hooks';
import { useTrackVisit } from '../lib/store';
import { kickoffFull, num, ordinal, pct, signed } from '../lib/format';
import { Badge, Card, CardHead, Empty, ErrorState, Loading, Notice, RankBar, Section, Stat } from '../components/ui';
import MarketBoard from '../components/MarketBoard';

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
  // Opens on this season. The engine falls back when a team has not played yet and
  // says so in the payload, which is what the badge on each panel reports.
  const [scope, setScope] = useState('current');

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

      <Section
        title="Unit matchup"
        sub="Both teams ranked against the same league field."
        action={
          <div className="league-switch" role="group" aria-label="Season basis">
            {[['current', 'This season'], ['historical', 'Historical']].map(([v, label]) => (
              <button key={v} aria-pressed={scope === v} onClick={() => setScope(v)}>{label}</button>
            ))}
          </div>
        }
      >
        <div className="grid" style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(330px, 1fr))' }}>
          <TeamPanel league={league} team={g.away} side="Away" scope={scope} />
          <TeamPanel league={league} team={g.home} side="Home" scope={scope} />
        </div>
      </Section>

      <Section title="Coaching & tendencies"
        sub="How these teams behave, independent of who they have played.">
        <div className="grid" style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(330px, 1fr))' }}>
          <TendencyPanel league={league} team={g.away} />
          <TendencyPanel league={league} team={g.home} />
        </div>
      </Section>

      <Section title="The board"
        sub="Every market a book has priced for this game. fair_prob is the price with the vig removed.">
        {odds.loading && <Loading rows={2} height={90} />}
        {odds.error && <ErrorState error={odds.error} onRetry={odds.refetch} />}
        {odds.data && (
          <MarketBoard league={league} gameId={gameId} board={odds.data}
            home={g.home} away={g.away} />
        )}
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

function TeamPanel({ league, team, side, scope }) {
  const off = useApi(`off:${team.team_id}:${scope}`,
    (s) => api.getOffense(league, team.team_id, { scope }, { signal: s }));
  const def = useApi(`def:${team.team_id}:${scope}`,
    (s) => api.getDefense(league, team.team_id, { scope }, { signal: s }));

  const body = () => {
    if (off.loading || def.loading) return <div className="card-pad"><Loading rows={2} height={54} /></div>;
    if (off.error && def.error) {
      return <div className="card-pad"><ErrorState error={off.error} /></div>;
    }
    const o = off.data, d = def.data;
    const of_ = o?.teams_ranked || d?.teams_ranked;
    const basis = o || d;
    return (
      <div className="card-pad col" style={{ gap: 16 }}>
        {basis?.fell_back && (
          <Notice icon={Icon.Clock}>
            No {basis.current_season} games played yet — showing{' '}
            <strong>{basis.seasons?.join(', ')}</strong> instead. This season's card
            appears as soon as the first game is ingested.
          </Notice>
        )}
        {basis && !basis.fell_back && basis.basis === 'current' && (
          <div className="tiny muted">
            {basis.current_season} only · {basis.games_played} game
            {basis.games_played === 1 ? '' : 's'} played
            {basis.games_played < 4 ? ' — a small sample, read it as a direction' : ''}
          </div>
        )}
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

/* ── Coaching & tendencies ────────────────────────────────────────────────────
   Behaviour rather than results. Pace and drive outcomes describe how a team plays
   regardless of who it has played, which is the read that survives a week-one slate
   where nobody has a current-season record yet. NCAAF adds the coach, because in
   college the portable signal belongs to him and not to the roster.
── */

function TendencyPanel({ league, team }) {
  const pace = useApi(`pace:${team.team_id}`,
    (s) => api.getPace(league, { team_id: team.team_id }, { signal: s }));
  const drives = useApi(`drives:${team.team_id}`,
    (s) => api.getDriveOutcomes(league, { team_id: team.team_id }, { signal: s }));
  const coach = useApi(
    league === 'ncaaf' ? `coaching:${team.team_id}` : null,
    (s) => api.getCoaching(team.team_id, {}, { signal: s }),
  );

  // Neutral-ish script: how the team plays when the game is not already decided.
  const neutral = (pace.data?.cells || []).find((c) => c.score_state === 'tied')
    || (pace.data?.cells || [])[0];

  // The single most over-indexed drive result, versus the league in the same field
  // position bucket — one honest sentence about how drives end.
  const signature = (() => {
    let best = null;
    for (const b of drives.data?.buckets || []) {
      for (const r of b.results || []) {
        if ((b.team_drives || 0) < 25) continue;
        if (!best || Math.abs(r.delta_vs_league) > Math.abs(best.delta)) {
          best = { bucket: b.bucket, result: r.result, delta: r.delta_vs_league,
                   rate: r.team_rate, league: r.league_rate, n: b.team_drives };
        }
      }
    }
    return best;
  })();

  return (
    <Card>
      <CardHead title={team.name} sub="Tendencies" icon={Icon.Grid} />
      <div className="card-pad col" style={{ gap: 14 }}>
        {league === 'ncaaf' && (
          coach.loading ? <Loading rows={1} height={44} />
          : coach.data ? (
            <div className="col" style={{ gap: 6 }}>
              <div className="eyebrow">Coach</div>
              <div className="row" style={{ gap: 8 }}>
                <Link to={`/coaches/${encodeURIComponent(coach.data.coach_id)}`}
                  className="accent" style={{ fontWeight: 700 }}>{coach.data.name}</Link>
                {coach.data.is_first_year_at_school && <Badge tone="accent">First year</Badge>}
                <span style={{ flex: 1 }} />
                <span className="tiny muted">Yr {coach.data.tenure_year ?? '—'}</span>
              </div>
              <div className="row wrap" style={{ gap: 16 }}>
                <Stat label="Career SP+ residual" value={signed(coach.data.career_sp_residual, 1)}
                  size="sm" sub="vs talent baseline" />
                <Stat label="Seasons of history" value={coach.data.seasons_of_history} size="sm"
                  sub={coach.data.seasons_of_history < 4 ? 'short — uncertain' : null} />
              </div>
            </div>
          ) : null
        )}

        {pace.loading && <Loading rows={1} height={44} />}
        {neutral && (
          <div className="col" style={{ gap: 6 }}>
            <div className="eyebrow">Pace · game tied</div>
            <div className="row wrap" style={{ gap: 16 }}>
              <Stat label="Sec / play" value={num(neutral.team_sec_per_play, 1)} size="sm"
                sub={`league ${num(neutral.league_sec_per_play, 1)}`} />
              <Stat label="Plays / drive" value={num(neutral.team_plays_per_drive, 2)} size="sm"
                sub={`league ${num(neutral.league_plays_per_drive, 2)}`} />
              <Stat label="Drives" value={neutral.team_drives} size="sm" />
            </div>
          </div>
        )}

        {drives.loading && <Loading rows={1} height={44} />}
        {signature && (
          <div className="col" style={{ gap: 4 }}>
            <div className="eyebrow">Drive signature</div>
            <div className="small secondary" style={{ lineHeight: 1.55 }}>
              From <strong>{signature.bucket.replace(/_/g, ' ')}</strong>, drives end in{' '}
              <strong>{signature.result.toLowerCase().replace(/_/g, ' ')}</strong>{' '}
              {pct(signature.rate, 0)} of the time — against a league rate of{' '}
              {pct(signature.league, 0)}.
            </div>
            <div className="row tiny" style={{ gap: 7 }}>
              <span style={{ color: signature.delta > 0 ? 'var(--good)' : 'var(--bad)' }}>
                {signed(signature.delta * 100, 1)} points vs league
              </span>
              <span className="muted">· {signature.n} drives</span>
              {/* Same rule as everywhere else here: the rate never travels without the
                  count, and a thin one is called thin rather than left to be noticed. */}
              {signature.n < 60 && <Badge tone="warn">thin sample</Badge>}
            </div>
          </div>
        )}

        {!pace.loading && !neutral && !signature && (
          <Empty icon={Icon.Grid} title="No tendency data"
            body="This team has no drives loaded for the default seasons." />
        )}
      </div>
    </Card>
  );
}
