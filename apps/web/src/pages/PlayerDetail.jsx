/* ── Player detail ────────────────────────────────────────────────────────────
   Bio and season aggregates up top; game log, PFF, opponent splits, clutch and
   the college career behind tabs.

   Two honesty rules are enforced in the layout rather than in a footnote: every
   opponent split ships its game count next to the rate, and the clutch tab
   refuses to render for a non-quarterback because the engine refuses to compute it.
── */

import React, { useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import Icon from '../icons';
import * as api from '../lib/api';
import { useApi } from '../lib/hooks';
import { useApp, useTrackVisit } from '../lib/store';
import { bareId, num, pct, signed } from '../lib/format';
import {
  Badge, Card, CardHead, Empty, ErrorState, Loading, Notice, Section,
  Sparkline, Stat, StatTile, StarButton,
} from '../components/ui';

const TABS = [
  { id: 'season', label: 'Seasons', icon: Icon.Grid },
  { id: 'gamelog', label: 'Game log', icon: Icon.Slate },
  { id: 'pff', label: 'Analysis', icon: Icon.Layers },
  { id: 'opponents', label: 'Vs opponent', icon: Icon.Shield },
  { id: 'clutch', label: 'Clutch', icon: Icon.Bolt },
  { id: 'college', label: 'College', icon: Icon.Trophy },
];

export default function PlayerDetail() {
  const { playerId } = useParams();
  const [tab, setTab] = useState('season');
  const { isWatched, toggleWatch } = useApp();

  const p = useApi(`player:${playerId}`, (s) => api.getPlayer(playerId, {}, { signal: s }));
  const to = `/players/${encodeURIComponent(playerId)}`;
  useTrackVisit(p.data && { id: playerId, kind: 'player', label: p.data.name, to });

  if (p.loading) return <Loading rows={3} height={120} />;
  if (p.error) return <ErrorState error={p.error} onRetry={p.refetch} />;

  const d = p.data;
  const isQb = d.position === 'QB';
  const tabs = TABS.filter((t) => t.id !== 'clutch' || isQb);

  return (
    <>
      <div className="page-head">
        <div style={{ minWidth: 0 }}>
          <div className="eyebrow row" style={{ gap: 7 }}>
            {d.position}
            {d.team_id && (
              <Link to={`/teams/nfl/${encodeURIComponent(d.team_id)}`} className="accent">
                {d.team_name || bareId(d.team_id)}
              </Link>
            )}
          </div>
          <h1 style={{ marginTop: 4 }}>{d.name}</h1>
          <div className="sub num">{d.player_id}</div>
        </div>
        <div className="spacer" />
        <StarButton active={isWatched(playerId)}
          onClick={() => toggleWatch({ id: playerId, kind: 'player', label: d.name, to })} />
      </div>

      {isQb && d.ngs_passing?.length > 0 && <NgsStrip rows={d.ngs_passing} />}

      <div className="scroll-x">
        {tabs.map((t) => (
          <button key={t.id} className="chip" aria-pressed={tab === t.id} onClick={() => setTab(t.id)}>
            <t.icon size={13} /> {t.label}
          </button>
        ))}
      </div>

      {tab === 'season' && <SeasonsTab player={d} />}
      {tab === 'gamelog' && <GamelogTab playerId={playerId} position={d.position} />}
      {tab === 'pff' && <PffTab playerId={playerId} />}
      {tab === 'opponents' && <OpponentsTab playerId={playerId} />}
      {tab === 'clutch' && <ClutchTab playerId={playerId} />}
      {tab === 'college' && <CollegeTab playerId={playerId} />}
    </>
  );
}

function NgsStrip({ rows }) {
  const latest = rows[rows.length - 1];
  return (
    <div className="grid grid-stat stagger">
      <StatTile label="Time to throw" value={num(latest.avg_time_to_throw, 2)} sub={`${latest.season} · seconds`} />
      <StatTile label="Intended air yards" value={num(latest.avg_intended_air_yards, 1)} sub={`${latest.season}`} />
      <StatTile label="Aggressiveness" value={pct(latest.aggressiveness / 100)} sub="throws into tight coverage" />
      <StatTile label="CPOE" value={signed(latest.cpoe, 1)} sub="completion % over expected" />
      <StatTile label="Passer rating" value={num(latest.passer_rating, 1)} sub={`${latest.season}`} />
    </div>
  );
}

function SeasonsTab({ player }) {
  const seasons = player.seasons || [];
  if (!seasons.length) {
    return <Card><Empty icon={Icon.Grid} title="No game logs"
      body="This player has no rows in player_game_stats for 2023–2025." /></Card>;
  }

  // Show only the stat families this player actually produced in — a corner's card
  // should not be mostly empty passing columns. The floor is five rather than one
  // because a quarterback with a single trick-play target does not have a receiving
  // profile, and a table that says so is noise.
  const has = (key, floor = 5) =>
    seasons.some((s) => s[key] != null && s[key] >= floor);
  const groups = [
    has('attempts') && { label: 'Passing', cols: [
      ['Att', 'attempts'], ['Cmp', 'completions'], ['Yds', 'passing_yards'],
      ['TD', 'passing_tds'], ['INT', 'interceptions'],
      ['EPA/g', 'passing_epa_per_game'], ['CPOE', 'cpoe'],
    ] },
    has('carries') && { label: 'Rushing', cols: [
      ['Car', 'carries'], ['Yds', 'rushing_yards'], ['TD', 'rushing_tds'],
    ] },
    has('targets') && { label: 'Receiving', cols: [
      ['Tgt', 'targets'], ['Rec', 'receptions'], ['Yds', 'receiving_yards'],
      ['TD', 'receiving_tds'], ['Tgt share', 'avg_target_share'],
    ] },
  ].filter(Boolean);

  return (
    <>
      {groups.map((g) => (
        <Card key={g.label}>
          <CardHead title={g.label} icon={Icon.Grid} />
          <div className="table-scroll">
            <table className="data">
              <thead>
                <tr><th>Season</th><th>G</th>{g.cols.map(([h]) => <th key={h}>{h}</th>)}</tr>
              </thead>
              <tbody>
                {seasons.map((s) => (
                  <tr key={s.season}>
                    <td style={{ fontWeight: 650 }}>{s.season}</td>
                    <td className="num">{s.games}</td>
                    {g.cols.map(([h, key]) => (
                      <td key={h} className="num">
                        {key.includes('share') ? pct(s[key])
                          : key.includes('epa') || key === 'cpoe' ? signed(s[key], 2)
                          : s[key] ?? '—'}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      ))}
    </>
  );
}

function GamelogTab({ playerId, position }) {
  const g = useApi(`glog:${playerId}`, (s) => api.getGamelog(playerId, {}, { signal: s }));

  if (g.loading) return <Loading rows={3} height={60} />;
  if (g.error) return <ErrorState error={g.error} onRetry={g.refetch} />;

  const games = g.data?.games || [];
  if (!games.length) return <Card><Empty icon={Icon.Slate} title="No games logged" /></Card>;

  const qb = position === 'QB';
  const metric = qb ? 'passing_yards' : 'receiving_yards';
  const series = games.map((r) => r[metric] ?? r.rushing_yards ?? null);
  const nonNull = series.filter((v) => v != null);
  const mean = nonNull.length ? nonNull.reduce((a, b) => a + b, 0) / nonNull.length : null;

  return (
    <>
      {mean != null && (
        <Card className="card-pad row" style={{ gap: 16 }}>
          <div className="stat">
            <span className="stat-label">{qb ? 'Passing yards' : 'Receiving yards'} · per game</span>
            <span className="stat-value num">{num(mean, 1)}</span>
            <span className="stat-sub">{nonNull.length} games, dashed line is the average</span>
          </div>
          <div style={{ flex: 1 }} />
          <Sparkline values={series} width={260} height={46} baseline={mean} color="var(--accent)" />
        </Card>
      )}

      <Card>
        <CardHead title="Game log" sub={`${games.length} games`} icon={Icon.Slate} />
        <div className="table-scroll" style={{ maxHeight: 560, overflowY: 'auto' }}>
          <table className="data">
            <thead>
              <tr>
                <th>Season</th><th>Wk</th><th>Opp</th>
                {qb ? <><th>Cmp/Att</th><th>Yds</th><th>TD</th><th>INT</th><th>EPA</th><th>CPOE</th><th>Sacks</th></>
                    : <><th>Tgt</th><th>Rec</th><th>Yds</th><th>TD</th><th>Tgt share</th><th>Car</th><th>Rush yds</th></>}
              </tr>
            </thead>
            <tbody>
              {[...games].reverse().map((r) => (
                <tr key={r.game_id}>
                  <td className="num">{r.season}</td>
                  <td className="num">{r.week}{r.season_type === 'postseason' ? '*' : ''}</td>
                  <td className="num muted">{bareId(r.opponent_team_id)}</td>
                  {qb ? (
                    <>
                      <td className="num">{r.completions ?? '—'}/{r.attempts ?? '—'}</td>
                      <td className="num">{r.passing_yards ?? '—'}</td>
                      <td className="num">{r.passing_tds ?? '—'}</td>
                      <td className="num">{r.passing_interceptions ?? '—'}</td>
                      <td className="num" style={{ color: r.passing_epa > 0 ? 'var(--good)' : r.passing_epa < 0 ? 'var(--bad)' : undefined }}>
                        {signed(r.passing_epa, 1)}
                      </td>
                      <td className="num">{signed(r.passing_cpoe, 1)}</td>
                      <td className="num">{r.sacks_suffered ?? '—'}</td>
                    </>
                  ) : (
                    <>
                      <td className="num">{r.targets ?? '—'}</td>
                      <td className="num">{r.receptions ?? '—'}</td>
                      <td className="num">{r.receiving_yards ?? '—'}</td>
                      <td className="num">{r.receiving_tds ?? '—'}</td>
                      <td className="num">{pct(r.target_share)}</td>
                      <td className="num">{r.carries ?? '—'}</td>
                      <td className="num">{r.rushing_yards ?? '—'}</td>
                    </>
                  )}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div className="card-pad tiny muted" style={{ borderTop: '1px solid var(--border-soft)' }}>
          * postseason. Columns come from official weekly aggregates, not sums over play-by-play.
        </div>
      </Card>
    </>
  );
}

function PffTab({ playerId }) {
  // Usage and alignment only. How many snaps a player took, how many routes he ran, and
  // how often he lined up in the slot are facts about what happened on the field — the
  // charting vendor's evaluation of how well he played is not requested and not shown.
  const pff = useApi(`pffsum:${playerId}`,
    (s) => api.getPlayerPff(playerId, {}, { signal: s }));

  if (pff.loading) return <Loading rows={2} height={70} />;
  if (pff.error) return <ErrorState error={pff.error} onRetry={pff.refetch} />;

  // A receiver credited with one pass-blocking snap is a trick play, not a role. The
  // floor keeps the table to the roles the player actually filled.
  const rows = (pff.data?.rows || []).filter(
    (r) => (r.snaps ?? 0) >= 20 || r.slot_rate != null || r.wide_rate != null);

  if (!rows.length) {
    return <Card><Empty icon={Icon.Layers} title="No usage data"
      body="Charting covers the NFL only, 2023–2025. Nothing is recorded for this player." /></Card>;
  }

  const aligned = rows.filter((r) => r.slot_rate != null);
  const latest = aligned[aligned.length - 1];

  return (
    <>
      {latest && (
        <div className="grid grid-stat stagger">
          <StatTile label="Slot rate" value={pct(latest.slot_rate)}
            sub={`${latest.season} · ${latest.facet.replace(/_/g, ' ')}`} />
          <StatTile label="Wide rate" value={pct(latest.wide_rate)} sub={`${latest.season}`} />
          <StatTile label="Snaps" value={latest.snaps} sub={`${latest.season}`} />
        </div>
      )}

      <Card>
        <CardHead title="Usage & alignment" sub="Season totals, by role" icon={Icon.Layers} />
        <div className="table-scroll">
          <table className="data">
            <thead>
              <tr><th>Role</th><th>Season</th><th>Snaps</th><th>Slot rate</th><th>Wide rate</th></tr>
            </thead>
            <tbody>
              {rows.map((r, i) => (
                <tr key={`${r.facet}-${r.season}-${i}`}>
                  <td style={{ fontWeight: 600 }}>{r.facet.replace(/_/g, ' ')}</td>
                  <td className="num">{r.season}</td>
                  <td className="num">{r.snaps ?? '—'}</td>
                  <td className="num">{r.slot_rate != null ? pct(r.slot_rate) : '—'}</td>
                  <td className="num">{r.wide_rate != null ? pct(r.wide_rate) : '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>

      <Notice icon={Icon.Info}>
        A measured alignment rate beats a positional label: NGS calls a receiver
        <code className="num"> SLOT_WR</code> or not, while this is the share of snaps he
        actually lined up inside. It is what the absence model uses to pick a replacement —
        the next slot-heavy body, not whoever sits one rank below on the depth chart.
      </Notice>
    </>
  );
}

function OpponentsTab({ playerId }) {
  const o = useApi(`vsopp:${playerId}`, (s) => api.getVsOpponent(playerId, {}, { signal: s }));

  if (o.loading) return <Loading rows={3} height={60} />;
  if (o.error) return <ErrorState error={o.error} onRetry={o.refetch} />;

  const rows = o.data?.by_opponent || [];
  if (!rows.length) return <Card><Empty icon={Icon.Shield} title="No opponent splits" /></Card>;

  const qb = rows.some((r) => r.attempts > 0);

  return (
    <>
      <Notice tone="warn" icon={Icon.Alert}>
        <strong>Samples here are tiny.</strong> Divisional opponents reach five or six games
        over three seasons; everyone else gets one or two. The game count sits next to every
        rate for exactly this reason — "he torches Miami" is usually a sampling story.
      </Notice>

      <Card>
        <CardHead title="By opponent" sub={`Seasons ${o.data.seasons?.join(', ')}`} icon={Icon.Shield} />
        <div className="table-scroll">
          <table className="data">
            <thead>
              <tr>
                <th>Opponent</th><th>G</th>
                {qb ? <><th>Att</th><th>Yds</th><th>TD</th><th>INT</th><th>EPA/g</th></>
                    : <><th>Tgt</th><th>Rec</th><th>Yds</th><th>TD</th><th>Tgt share</th></>}
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.opponent_team_id}>
                  <td>
                    <Link to={`/teams/nfl/${encodeURIComponent(r.opponent_team_id)}`}
                      style={{ fontWeight: 600 }}>
                      {r.opponent_name || bareId(r.opponent_team_id)}
                    </Link>
                  </td>
                  <td className="num">
                    <span className={r.games < 3 ? 'warn' : ''} title={r.games < 3 ? 'Very small sample' : undefined}>
                      {r.games}
                    </span>
                  </td>
                  {qb ? (
                    <>
                      <td className="num">{r.attempts ?? '—'}</td>
                      <td className="num">{r.passing_yards ?? '—'}</td>
                      <td className="num">{r.passing_tds ?? '—'}</td>
                      <td className="num">{r.interceptions ?? '—'}</td>
                      <td className="num">{signed(r.passing_epa_per_game, 2)}</td>
                    </>
                  ) : (
                    <>
                      <td className="num">{r.targets ?? '—'}</td>
                      <td className="num">{r.receptions ?? '—'}</td>
                      <td className="num">{r.receiving_yards ?? '—'}</td>
                      <td className="num">{r.receiving_tds ?? '—'}</td>
                      <td className="num">{pct(r.avg_target_share)}</td>
                    </>
                  )}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>
    </>
  );
}

function ClutchTab({ playerId }) {
  const c = useApi(`clutch:${playerId}`, (s) => api.getClutch(playerId, {}, { signal: s }));

  if (c.loading) return <Loading rows={2} height={110} />;
  if (c.error) return <ErrorState error={c.error} onRetry={c.refetch} />;

  const d = c.data;
  const lc = d.late_close || {};
  const delta = lc.delta_vs_own_baseline;

  return (
    <>
      <div className="grid grid-stat stagger">
        <StatTile label="Baseline EPA/db" value={num(d.baseline?.epa_per_dropback, 3)}
          sub={`${d.baseline?.dropbacks} dropbacks`} />
        <StatTile label="Late & close EPA/db" value={num(lc.epa_per_dropback, 3)}
          sub={`${lc.dropbacks} dropbacks`} />
        <StatTile label="Vs own baseline" value={signed(delta, 3)}
          sub={delta > 0 ? 'raises his level' : 'below his own norm'} />
        <StatTile label="League late & close" value={num(lc.league_epa_per_dropback, 3)}
          sub="every QB, same situation" />
      </div>

      {lc.small_sample && (
        <Notice tone="warn" icon={Icon.Alert}>
          The engine flags this late-and-close sample as small. Treat the delta as a
          direction, not a measurement.
        </Notice>
      )}

      <div className="grid" style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))' }}>
        <Card>
          <CardHead title="Two-minute drill" icon={Icon.Clock} />
          <div className="card-pad grid grid-stat">
            <Stat label="Plays" value={d.two_minute?.plays} />
            <Stat label="EPA / play" value={num(d.two_minute?.epa_per_play, 3)} />
            <Stat label="Success" value={pct(d.two_minute?.success_rate)} />
            <Stat label="Completion" value={pct(d.two_minute?.comp_rate)} />
          </div>
        </Card>
        <Card>
          <CardHead title="Clutch drives" sub="Late, one score either way" icon={Icon.Bolt} />
          <div className="card-pad grid grid-stat">
            <Stat label="Drives" value={d.clutch_drives?.drives} />
            <Stat label="Scoring drives" value={d.clutch_drives?.scoring_drives} />
            <Stat label="Score rate" value={pct(d.clutch_drives?.score_rate)} animate />
            <Stat label="Late WPA total" value={signed(lc.wpa_total, 2)} />
          </div>
        </Card>
      </div>
    </>
  );
}

function CollegeTab({ playerId }) {
  const c = useApi(`college:${playerId}`, (s) => api.getCollege(playerId, { signal: s }));

  if (c.loading) return <Loading rows={2} height={80} />;
  if (c.error) {
    return c.error.isMissing
      ? <Card><Empty icon={Icon.Trophy} title="No college career linked"
          body="Career links come from ESPN athlete ids, which only cover rosters from 2023 on. Older college careers sit outside that window." /></Card>
      : <ErrorState error={c.error} onRetry={c.refetch} />;
  }

  const d = c.data;
  const rows = d.college_seasons || [];

  return (
    <>
      <Card className="card-pad row wrap" style={{ gap: 18 }}>
        <div className="stat">
          <span className="stat-label">School</span>
          <span className="stat-value sm">{d.college?.school || '—'}</span>
        </div>
        <div className="stat">
          <span className="stat-label">College name</span>
          <span className="stat-value sm">{d.college?.name}</span>
        </div>
        <div className="stat">
          <span className="stat-label">Jersey</span>
          <span className="stat-value sm num">{d.college?.jersey ?? '—'}</span>
        </div>
        <div style={{ flex: 1 }} />
        {!d.name_agrees && (
          <Badge tone="warn">Name differs across sources</Badge>
        )}
      </Card>

      {!d.name_agrees && (
        <Notice icon={Icon.Info}>
          The link is by ESPN athlete id, which persists from college to the pros — it is exact,
          not a fuzzy name match. A differing name is nearly always formatting (Cam/Cameron,
          suffixes, M.J./MJ), and it is surfaced rather than hidden.
        </Notice>
      )}

      {rows.length === 0 ? (
        <Card><Empty icon={Icon.Trophy} title="No college seasons stored" /></Card>
      ) : (
        <Card>
          <CardHead title="College production" icon={Icon.Trophy} />
          <div className="table-scroll">
            <table className="data">
              <thead>
                <tr><th>Season</th><th>G</th><th>Att</th><th>Pass yds</th><th>TD</th>
                  <th>Car</th><th>Rush yds</th><th>Rec</th><th>Rec yds</th><th>Rec TD</th></tr>
              </thead>
              <tbody>
                {rows.map((r) => (
                  <tr key={r.season}>
                    <td style={{ fontWeight: 650 }}>{r.season}</td>
                    <td className="num">{r.games}</td>
                    <td className="num">{r.attempts ?? '—'}</td>
                    <td className="num">{r.passing_yards ?? '—'}</td>
                    <td className="num">{r.passing_tds ?? '—'}</td>
                    <td className="num">{r.carries ?? '—'}</td>
                    <td className="num">{r.rushing_yards ?? '—'}</td>
                    <td className="num">{r.receptions ?? '—'}</td>
                    <td className="num">{r.receiving_yards ?? '—'}</td>
                    <td className="num">{r.receiving_tds ?? '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      )}
    </>
  );
}
