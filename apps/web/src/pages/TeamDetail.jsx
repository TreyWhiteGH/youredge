/* ── Team detail ──────────────────────────────────────────────────────────────
   Everything the engine knows about one team, in tabs so the page stays legible.

   Which tabs exist depends on the league, and that is a data fact, not a styling
   choice: PFF grades and protection are NFL-only, while coaching, returning
   production and portal churn are the college signal and have no NFL analog.
── */

import React, { useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import Icon from '../icons';
import * as api from '../lib/api';
import { useApi } from '../lib/hooks';
import { useApp, useTrackVisit } from '../lib/store';
import {
  bareId, num, ordinal, pct, signed, SCORE_STATES, SCORE_STATE_LABEL, UNIT_LABEL,
} from '../lib/format';
import {
  Badge, Card, CardHead, Empty, ErrorState, Loading, Notice, RankBar, RankBadge,
  Section, Stat, StatTile, StarButton, Tip,
} from '../components/ui';
import GameCard from '../components/GameCard';
import TeamMark from '../components/TeamMark';

const NFL_TABS = [
  { id: 'units', label: 'Units', icon: Icon.Shield },
  { id: 'pff', label: 'Analysis', icon: Icon.Layers },
  { id: 'protection', label: 'Protection', icon: Icon.Field },
  { id: 'tendencies', label: 'Tendencies', icon: Icon.Grid },
  { id: 'schedule', label: 'Schedule', icon: Icon.Slate },
];
const NCAAF_TABS = [
  { id: 'units', label: 'Units', icon: Icon.Shield },
  { id: 'context', label: 'Roster & coaching', icon: Icon.Whistle },
  { id: 'transfers', label: 'Portal', icon: Icon.TrendUp },
  { id: 'tendencies', label: 'Tendencies', icon: Icon.Grid },
  { id: 'schedule', label: 'Schedule', icon: Icon.Slate },
];

export default function TeamDetail() {
  const { league, teamId } = useParams();
  const [tab, setTab] = useState('units');
  const { isWatched, toggleWatch, toggleCompare, inCompare } = useApp();

  const tabs = league === 'nfl' ? NFL_TABS : NCAAF_TABS;
  const to = `/teams/${league}/${encodeURIComponent(teamId)}`;

  // The offense card is also how we learn the team's display name — there is no
  // single "get team" endpoint, and the card 404s honestly when there are no plays.
  const off = useApi(`off:${teamId}`, (s) => api.getOffense(league, teamId, {}, { signal: s }));
  const def = useApi(`def:${teamId}`, (s) => api.getDefense(league, teamId, {}, { signal: s }));
  const teams = useApi(`teams:${league}`, (s) => api.listTeams(league, {}, { signal: s }), { ttl: 6e5 });

  const meta = (teams.data?.teams || []).find((t) => t.team_id === teamId);
  const name = meta?.name || bareId(teamId);
  const poll = teams.data?.poll;

  useTrackVisit(meta && { id: teamId, kind: 'team', label: name, to });

  return (
    <>
      <div className="page-head">
        <div style={{ minWidth: 0 }}>
          <div className="eyebrow">{league.toUpperCase()}{meta?.classification ? ` · ${meta.classification.toUpperCase()}` : ''}</div>
          <h1 style={{ marginTop: 4 }} className="row">
            {meta && <TeamMark team={meta} size={34} />}
            {meta?.rank ? (
              <span className="rank-chip lg num" title={`${poll} — ${meta.points} points`}>
                {meta.rank}
              </span>
            ) : null}
            {name}
          </h1>
          <div className="sub row" style={{ gap: 8 }}>
            <span className="num">{teamId}</span>
            {meta?.rank && (
              <span className="tiny muted">
                {poll} · {teams.data.rank_season} week {teams.data.rank_week}
                {meta.first_place_votes ? ` · ${meta.first_place_votes} first-place votes` : ''}
              </span>
            )}
          </div>
        </div>
        <div className="spacer" />
        <div className="row" style={{ gap: 6 }}>
          <button className="chip" aria-pressed={inCompare(teamId)}
            onClick={() => toggleCompare({ id: teamId, kind: 'team', label: meta?.abbr || name, league, to })}>
            {inCompare(teamId) ? <Icon.Check size={13} /> : <Icon.Compare size={13} />} Compare
          </button>
          <StarButton active={isWatched(teamId)}
            onClick={() => toggleWatch({ id: teamId, kind: 'team', label: name, to })} />
        </div>
      </div>

      <div className="scroll-x">
        {tabs.map((t) => (
          <button key={t.id} className="chip" aria-pressed={tab === t.id} onClick={() => setTab(t.id)}>
            <t.icon size={13} /> {t.label}
          </button>
        ))}
      </div>

      {tab === 'units' && <UnitsTab off={off} def={def} />}
      {tab === 'pff' && <PffTab league={league} teamId={teamId} />}
      {tab === 'protection' && <ProtectionTab league={league} teamId={teamId} />}
      {tab === 'tendencies' && <TendenciesTab league={league} teamId={teamId} />}
      {tab === 'context' && <ContextTab teamId={teamId} />}
      {tab === 'transfers' && <TransfersTab teamId={teamId} />}
      {tab === 'schedule' && <ScheduleTab league={league} teamId={teamId} />}
    </>
  );
}

/* ── Units ── */

function UnitsTab({ off, def }) {
  if (off.loading || def.loading) return <Loading rows={2} height={190} />;
  if (off.error && def.error) return <ErrorState error={off.error} onRetry={off.refetch} />;

  const o = off.data, d = def.data;
  const of_ = o?.teams_ranked || d?.teams_ranked;

  return (
    <>
      <Notice>
        Unit cards are <strong>raw, not opponent-adjusted</strong>. They are honest at the
        top-five and bottom-five grain; adjacent ranks are noise.
      </Notice>

      <div className="grid" style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(330px, 1fr))' }}>
        {o && (
          <Card>
            <CardHead title="Offense" sub={`Seasons ${o.seasons?.join(', ')}`} icon={Icon.TrendUp} />
            <div className="card-pad col" style={{ gap: 16 }}>
              <div className="col" style={{ gap: 11 }}>
                <RankBar label="Pass EPA / dropback" value={o.pass_offense?.epa}
                  rank={o.pass_offense?.rank} of={of_} leagueAvg={o.pass_offense?.league_avg} />
                <RankBar label="Run EPA / rush" value={o.run_offense?.epa}
                  rank={o.run_offense?.rank} of={of_} leagueAvg={o.run_offense?.league_avg} />
              </div>
              <div className="grid grid-stat">
                <StatTile label="Dropbacks" value={o.pass_offense?.dropbacks} />
                <StatTile label="Pass success" value={pct(o.pass_offense?.success_rate)} />
                <StatTile label="Explosive pass" value={pct(o.pass_offense?.explosive_rate)} />
                <StatTile label="Completion" value={pct(o.pass_offense?.comp_rate)} />
                <StatTile label="INT rate" value={pct(o.pass_offense?.int_rate, 2)} />
                <StatTile label="Rushes" value={o.run_offense?.rushes} />
                <StatTile label="Run success" value={pct(o.run_offense?.success_rate)} />
                <StatTile label="Explosive run" value={pct(o.run_offense?.explosive_rate)} />
              </div>
              <Situational s={o.situational} of={of_} label="Offense" />
            </div>
          </Card>
        )}

        {d && (
          <Card>
            <CardHead title="Defense" sub={`Seasons ${d.seasons?.join(', ')}`} icon={Icon.Shield} />
            <div className="card-pad col" style={{ gap: 16 }}>
              <div className="col" style={{ gap: 11 }}>
                <RankBar label="Pass EPA allowed" value={d.pass_defense?.epa_allowed}
                  rank={d.pass_defense?.rank} of={of_} leagueAvg={d.pass_defense?.league_avg} />
                <RankBar label="Run EPA allowed" value={d.run_defense?.epa_allowed}
                  rank={d.run_defense?.rank} of={of_} leagueAvg={d.run_defense?.league_avg} />
              </div>
              <div className="grid grid-stat">
                <StatTile label="Dropbacks faced" value={d.pass_defense?.dropbacks_faced} />
                <StatTile label="Pass success allowed" value={pct(d.pass_defense?.success_rate_allowed)} />
                <StatTile label="Explosive allowed" value={pct(d.pass_defense?.explosive_rate_allowed)} />
                <StatTile label="Completion allowed" value={pct(d.pass_defense?.comp_rate_allowed)} />
                <StatTile label="INT rate" value={pct(d.pass_defense?.int_rate, 2)} />
                <StatTile label="Rushes faced" value={d.run_defense?.rushes_faced} />
                <StatTile label="Run success allowed" value={pct(d.run_defense?.success_rate_allowed)} />
                <StatTile label="Explosive run allowed" value={pct(d.run_defense?.explosive_rate_allowed)} />
              </div>
              <Situational s={d.situational} of={of_} label="Defense" />
            </div>
          </Card>
        )}
      </div>

      {!o && !d && <Card><Empty icon={Icon.Shield} title="No play-by-play for this team"
        body="Nothing is loaded for the default seasons. Run the ingest for this league." /></Card>}
    </>
  );
}

function Situational({ s, of, label }) {
  if (!s) return null;
  // Offense and defense report the same idea under different keys (`rz_td_rate` vs
  // `rz_td_rate_allowed`); read whichever this side supplies.
  const rz = s.rz_td_rate ?? s.rz_td_rate_allowed;
  const lateClose = s.late_close_epa ?? s.late_close_epa_allowed;
  const allowed = s.rz_td_rate_allowed !== undefined;
  return (
    <div className="col" style={{ gap: 9, paddingTop: 12, borderTop: '1px solid var(--border-soft)' }}>
      <div className="eyebrow">{label} · situational</div>
      <div className="row wrap" style={{ gap: 18 }}>
        {rz != null ? (
          <Stat label={allowed ? 'Red zone TD allowed' : 'Red zone TD'} value={pct(rz)} size="sm" />
        ) : (
          <Tip label="touchdown is an nflverse-only column, so college red-zone rate is unavailable">
            <Stat label="Red zone TD" value="—" size="sm" sub="NFL only" />
          </Tip>
        )}
        <Stat label={allowed ? 'Late & close EPA allowed' : 'Late & close EPA'}
          value={signed(lateClose)} size="sm"
          sub={s.late_close_rank ? `${ordinal(s.late_close_rank)} of ${of}` : null} />
      </div>
    </div>
  );
}

/* ── PFF ── */

function PffTab({ league, teamId }) {
  const [season, setSeason] = useState(2025);
  const units = useApi(`units:${teamId}:${season}`,
    (s) => api.getUnits(league, teamId, { season }, { signal: s }));

  return (
    <>
      <div className="row">
        <div className="eyebrow" style={{ flex: 1 }}>Snap-weighted unit grades, ranked league-wide</div>
        <SeasonPicker value={season} onChange={setSeason} />
      </div>

      {units.loading && <Loading rows={2} height={120} />}
      {units.error && <ErrorState error={units.error} onRetry={units.refetch} />}

      {units.data && (
        <Card>
          <CardHead title="Unit grades" sub={`Season ${units.data.season}`} icon={Icon.Layers} />
          <div className="card-pad grid" style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(260px, 1fr))', gap: 16 }}>
            {Object.entries(units.data.units || {}).map(([key, u]) => (
              <div key={key} className="col" style={{ gap: 6 }}>
                {/* Rank and tier, not the underlying grade — see api.js on why the
                    client never asks for it. Bar length is the league percentile. */}
                <RankBar
                  label={UNIT_LABEL[key] || key}
                  rank={u.rank}
                  of={u.teams_ranked}
                  showValue={false}
                />
                <div className="tiny" style={{ color: 'var(--text-faint)' }}>
                  {u.players} players · {u.snaps?.toLocaleString()} snaps
                  {u.vs_league ? ` · ${u.vs_league} the league` : ''}
                </div>
              </div>
            ))}
          </div>
        </Card>
      )}

      <Notice icon={Icon.Info}>
        Each unit is scored across every charted player, weighted by snaps, then ranked
        against the league. These measure what a box score cannot — offensive-line
        performance, coverage allowed, pressure created and given up. Rank is shown rather
        than an underlying score on purpose: these cards are trustworthy at the top and
        bottom of the league, and adjacent ranks are noise.
      </Notice>
    </>
  );
}

function ProtectionTab({ league, teamId }) {
  const [season, setSeason] = useState(2025);
  const p = useApi(`prot:${teamId}:${season}`,
    (s) => api.getProtection(league, teamId, { season }, { signal: s }));

  return (
    <>
      <div className="row">
        <div className="eyebrow" style={{ flex: 1 }}>Pass protection, per lineman</div>
        <SeasonPicker value={season} onChange={setSeason} />
      </div>

      {p.loading && <Loading rows={2} height={120} />}
      {p.error && <ErrorState error={p.error} onRetry={p.refetch} />}

      {p.data && (
        <>
          <div className="grid grid-stat stagger">
            <StatTile label="Pass-block snaps" value={p.data.unit.pass_block_snaps} animate />
            <StatTile label="Pressures allowed" value={p.data.unit.pressures_allowed} animate />
            <StatTile label="Pressure rate" value={pct(p.data.unit.pressure_rate_allowed, 2)}
              sub="derived, not a standard metric" />
            <StatTile label="Linemen charted" value={p.data.unit.linemen} />
          </div>

          <Card>
            <CardHead title="By lineman" sub="100+ pass-block snaps" icon={Icon.Field} />
            <div className="table-scroll">
              <table className="data">
                <thead>
                  <tr>
                    <th>Player</th><th>Pos</th><th>PB snaps</th><th>Pressures</th>
                    <th>Sacks</th><th>Hits</th><th>Hurries</th><th>Pressure rate</th>
                  </tr>
                </thead>
                <tbody>
                  {p.data.by_lineman.map((l) => (
                    <tr key={l.name}>
                      <td style={{ fontWeight: 600 }}>{l.name}</td>
                      <td className="muted">{l.position}</td>
                      <td className="num">{l.pb_snaps}</td>
                      <td className="num">{l.pressures}</td>
                      <td className="num">{l.sacks}</td>
                      <td className="num">{l.hits}</td>
                      <td className="num">{l.hurries}</td>
                      <td className="num" style={{ color: l.pressure_rate_allowed > 0.08 ? 'var(--bad)' : undefined }}>
                        {pct(l.pressure_rate_allowed, 2)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Card>

          <Notice icon={Icon.Info}>
            Every column here is a counted event — snaps taken, pressures, sacks, hits and
            hurries given up. <strong>Pressure rate is derived</strong>: pressures divided by
            pass-block snaps. It is said plainly rather than presented as a standard
            efficiency metric, because it is not one.
          </Notice>
        </>
      )}
    </>
  );
}

/* ── Tendencies ── */

function TendenciesTab({ league, teamId }) {
  const t = useApi(`pr:${teamId}`,
    (s) => api.getPassRate(league, { team_id: teamId }, { signal: s }));

  if (t.loading) return <Loading rows={2} height={160} />;
  if (t.error) return <ErrorState error={t.error} onRetry={t.refetch} />;

  const cells = t.data?.cells || [];
  const quarters = [...new Set(cells.map((c) => c.quarter))].sort();
  const byKey = new Map(cells.map((c) => [`${c.quarter}|${c.score_state}`, c]));

  return (
    <>
      <Card>
        <CardHead title="Pass rate vs league"
          sub="Delta from the league's rate in the same quarter and score state"
          icon={Icon.Grid} />
        <div className="card-pad">
          <div className="heat" style={{ gridTemplateColumns: `56px repeat(${SCORE_STATES.length}, 1fr)` }}>
            <div />
            {SCORE_STATES.map((s) => (
              <div key={s} className="heat-axis">{SCORE_STATE_LABEL[s]}</div>
            ))}
            {quarters.map((q) => (
              <React.Fragment key={q}>
                <div className="heat-axis" style={{ justifyContent: 'flex-end', paddingRight: 8 }}>
                  {q > 4 ? 'OT' : `Q${q}`}
                </div>
                {SCORE_STATES.map((state) => {
                  const c = byKey.get(`${q}|${state}`);
                  if (!c) return <div key={state} className="heat-cell" style={{ background: 'var(--bg-input)' }} />;
                  // A handful of plays is not a tendency. Cells below 25 plays are
                  // drawn washed out so the eye skips them.
                  const thin = c.team_plays < 25;
                  const d = c.delta_vs_league;
                  const mag = Math.min(1, Math.abs(d) / 0.2);
                  const tone = d > 0 ? '76, 141, 255' : '255, 95, 109';
                  return (
                    <Tip key={state}
                      label={`${c.team_plays} plays · team ${pct(c.team_pass_rate)} vs league ${pct(c.league_pass_rate)}`}>
                      <div className="heat-cell" style={{
                        width: '100%',
                        background: `rgba(${tone}, ${(thin ? 0.12 : 0.9) * mag + 0.05})`,
                        color: mag > 0.5 && !thin ? '#fff' : 'var(--text-secondary)',
                        opacity: thin ? 0.45 : 1,
                      }}>
                        <span className="d num">{d > 0 ? '+' : '−'}{Math.abs(d * 100).toFixed(0)}</span>
                        <span className="n num">{c.team_plays}</span>
                      </div>
                    </Tip>
                  );
                })}
              </React.Fragment>
            ))}
          </div>
        </div>
        <div className="card-pad col" style={{ gap: 7, borderTop: '1px solid var(--border-soft)' }}>
          {/* Red is "bad" everywhere else in this app, so the diverging scale here gets an
              explicit key — these two colours mean direction, not quality. */}
          <div className="row tiny" style={{ gap: 14, color: 'var(--text-muted)' }}>
            <span className="row" style={{ gap: 6 }}>
              <span style={{ width: 11, height: 11, borderRadius: 3, background: 'rgba(76,141,255,0.85)' }} />
              passes more than the league
            </span>
            <span className="row" style={{ gap: 6 }}>
              <span style={{ width: 11, height: 11, borderRadius: 3, background: 'rgba(255,95,109,0.85)' }} />
              runs more than the league
            </span>
          </div>
          <div className="tiny muted">
            Big number is the pass-rate delta in points; small number is the team's play count
            in that cell. Faded cells have fewer than 25 plays. Scrambles count as runs
            (nflverse convention).
          </div>
        </div>
      </Card>
    </>
  );
}

/* ── NCAAF context ── */

function ContextTab({ teamId }) {
  const [season, setSeason] = useState(2026);
  const ctx = useApi(`ctx:${teamId}:${season}`, (s) => api.getContext(teamId, { season }, { signal: s }));
  const coach = useApi(`coach:${teamId}:${season}`, (s) => api.getCoaching(teamId, { season }, { signal: s }));

  return (
    <>
      <div className="row">
        <div className="eyebrow" style={{ flex: 1 }}>Preseason signal — where college reasoning starts</div>
        <SeasonPicker value={season} onChange={setSeason} years={[2023, 2024, 2025, 2026]} />
      </div>

      <div className="grid" style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(330px, 1fr))' }}>
        <Card>
          <CardHead title="Coaching" icon={Icon.Whistle} />
          <div className="card-pad">
            {coach.loading && <Loading rows={1} height={80} />}
            {coach.error && <ErrorState error={coach.error} />}
            {coach.data && (
              <div className="col" style={{ gap: 13 }}>
                <div className="row">
                  <Link to={`/coaches/${encodeURIComponent(coach.data.coach_id)}`}
                    className="accent" style={{ fontSize: 17, fontWeight: 700 }}>
                    {coach.data.name}
                  </Link>
                  {coach.data.is_first_year_at_school && <Badge tone="accent">First year here</Badge>}
                </div>
                <div className="grid grid-stat">
                  <StatTile label="Tenure" value={`Yr ${coach.data.tenure_year ?? '—'}`} />
                  <StatTile label="Career SP+ residual" value={signed(coach.data.career_sp_residual, 1)}
                    sub="vs talent baseline" />
                  <StatTile label="Trajectory" value={signed(coach.data.trajectory, 1)} />
                  <StatTile label="Seasons of history" value={coach.data.seasons_of_history} />
                </div>
                {coach.data.seasons_of_history != null && coach.data.seasons_of_history < 4 && (
                  <Notice tone="warn" icon={Icon.Alert}>
                    Only {coach.data.seasons_of_history} seasons of FBS history. Short history
                    means <strong>uncertain</strong>, not average.
                  </Notice>
                )}
              </div>
            )}
          </div>
        </Card>

        <Card>
          <CardHead title="Roster continuity" sub="With league percentile" icon={Icon.Players} />
          <div className="card-pad">
            {ctx.loading && <Loading rows={1} height={80} />}
            {ctx.error && <ErrorState error={ctx.error} />}
            {ctx.data && (
              <div className="col" style={{ gap: 13 }}>
                <RankBar label="Returning production (PPA)" value={ctx.data.pct_ppa}
                  format={(v) => pct(v)} max={1}
                  rank={null} of={null} />
                <div className="tiny" style={{ color: 'var(--text-faint)', marginTop: -8 }}>
                  {ctx.data.pct_ppa_pctile != null
                    ? `${pct(ctx.data.pct_ppa_pctile, 0)} percentile in ${season}`
                    : 'percentile unavailable'}
                </div>
                <div className="grid grid-stat">
                  <StatTile label="Passing PPA back" value={pct(ctx.data.pct_passing_ppa)} />
                  <StatTile label="Rushing PPA back" value={pct(ctx.data.pct_rushing_ppa)} />
                  <StatTile label="Receiving PPA back" value={pct(ctx.data.pct_receiving_ppa)} />
                  <StatTile label="SP+ overall" value={num(ctx.data.sp_overall, 1)}
                    sub={ctx.data.sp_ranking ? `${ordinal(ctx.data.sp_ranking)} nationally` : null} />
                  <StatTile label="Recruiting rank" value={ctx.data.recruiting_rank} />
                  <StatTile label="Talent"
                    value={ctx.data.talent != null ? num(ctx.data.talent, 1) : '—'}
                    sub={ctx.data.talent == null ? 'not published' : null} />
                </div>
              </div>
            )}
          </div>
        </Card>
      </div>

      <Notice>
        College turnover means last season's player grades travel poorly. The predictive
        signal sits in <strong>who is coaching</strong> and <strong>how much production
        returned</strong> — and the coaching signal belongs to the coach, not the school,
        so it travels when he moves.
      </Notice>
    </>
  );
}

function TransfersTab({ teamId }) {
  const [season, setSeason] = useState(2026);
  const t = useApi(`xfer:${teamId}:${season}`, (s) => api.getTransfers(teamId, { season }, { signal: s }));

  if (t.loading) return <Loading rows={3} height={60} />;
  if (t.error) return <ErrorState error={t.error} onRetry={t.refetch} />;

  const rows = t.data?.transfers || [];
  const incoming = rows.filter((r) => r.direction === 'in');
  const outgoing = rows.filter((r) => r.direction === 'out');

  return (
    <>
      <div className="row">
        <div className="eyebrow" style={{ flex: 1 }}>Transfer portal</div>
        <SeasonPicker value={season} onChange={setSeason} years={[2022, 2023, 2024, 2025, 2026]} />
      </div>

      <div className="grid grid-stat stagger">
        <StatTile label="In" value={t.data.in_count} animate />
        <StatTile label="Out" value={t.data.out_count} animate />
        <StatTile label="Net" value={t.data.in_count - t.data.out_count} />
      </div>

      {rows.length === 0 ? (
        <Card><Empty icon={Icon.TrendUp} title="No portal activity recorded"
          body="Portal data is NULL before 2021, which is not the same as zero." /></Card>
      ) : (
        <div className="grid" style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 1fr))' }}>
          {[['Incoming', incoming, 'good'], ['Outgoing', outgoing, 'bad']].map(([label, list, tone]) => (
            <Card key={label}>
              <CardHead title={label} sub={`${list.length} players`}
                icon={tone === 'good' ? Icon.TrendUp : Icon.TrendDown} />
              <div className="table-scroll" style={{ maxHeight: 420, overflowY: 'auto' }}>
                <table className="data">
                  <thead><tr><th>Player</th><th>Pos</th><th>Stars</th><th>Eligibility</th></tr></thead>
                  <tbody>
                    {list.map((r, i) => (
                      <tr key={`${r.player_name}-${i}`}>
                        <td style={{ fontWeight: 600 }}>{r.player_name}</td>
                        <td className="muted">{r.position || '—'}</td>
                        <td className="num" style={{ color: r.stars >= 4 ? 'var(--warn)' : undefined }}>
                          {r.stars ?? '—'}
                        </td>
                        <td className="muted">{r.eligibility || '—'}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </Card>
          ))}
        </div>
      )}
    </>
  );
}

/* ── Schedule ── */

function ScheduleTab({ league, teamId }) {
  const g = useApi(`tsched:${teamId}`,
    (s) => api.listGames(league, { team_id: teamId, limit: 40, order: 'desc' }, { signal: s }));

  if (g.loading) return <Loading rows={3} height={150} />;
  if (g.error) return <ErrorState error={g.error} onRetry={g.refetch} />;
  if (!g.data?.games?.length) {
    return <Card><Empty icon={Icon.Slate} title="No games" body="No schedule rows are loaded for this team." /></Card>;
  }

  return (
    <div className="grid grid-auto stagger">
      {g.data.games.map((game) => <GameCard key={game.game_id} game={game} />)}
    </div>
  );
}

/* ── Shared ── */

function SeasonPicker({ value, onChange, years = [2023, 2024, 2025] }) {
  return (
    <select className="input" style={{ width: 'auto' }} value={value}
      onChange={(e) => onChange(Number(e.target.value))} aria-label="Season">
      {years.map((y) => <option key={y} value={y}>{y}</option>)}
    </select>
  );
}
