/* ── Live ─────────────────────────────────────────────────────────────────────
   Scores, clock, down & distance, and game leaders, refreshed while you watch.

   This is the only page that does not read the engine's database. In-game state has
   no home in our schema — `games` stores a final score, not a play clock — so it comes
   from the live scoreboard endpoint, which is a short-TTL pass-through. Every card
   states how old its data is, and a failed refresh surfaces as an error rather than
   leaving yesterday's numbers on screen pretending to be current.
── */

import React, { useEffect, useMemo, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import Icon from '../icons';
import * as api from '../lib/api';
import { useApi } from '../lib/hooks';
import { useApp } from '../lib/store';
import { dayLabel, dayPhrase, isToday, kickoffTime, localDay, shiftDay } from '../lib/format';
import { Card, Empty, ErrorState, Loading, Notice, Section } from '../components/ui';

// Polled only while something is actually being played. A settled slate does not need
// to be re-fetched every twenty seconds, and the engine caches it for two minutes anyway.
const POLL_LIVE_MS = 20_000;

export default function Live() {
  const { league } = useApp();
  const [day, setDay] = useState(() => localDay());
  const [tick, setTick] = useState(0);

  const { data, loading, error, refetch } = useApi(
    `live:${league}:${day}:${tick}`,
    (s) => api.getLive(league, { date: day }, { signal: s }),
    { ttl: 0 },
  );

  const liveCount = data?.live_count ?? 0;

  // Re-key on an interval rather than calling refetch, so a poll goes through the same
  // cache path as a first load and cannot stack overlapping requests.
  useEffect(() => {
    if (!liveCount) return undefined;
    const id = setInterval(() => setTick((t) => t + 1), POLL_LIVE_MS);
    return () => clearInterval(id);
  }, [liveCount]);

  const groups = useMemo(() => {
    const g = { in: [], pre: [], post: [] };
    for (const game of data?.games || []) (g[game.state] || g.post).push(game);
    return g;
  }, [data]);

  return (
    <>
      <div className="page-head">
        <div>
          <h1 className="row">
            Live
            {liveCount > 0 && (
              <span className="badge bad"><span className="dot live" />{liveCount} in progress</span>
            )}
          </h1>
          <div className="sub">
            Scores, clock and down &amp; distance.{' '}
            {data && (
              <>Updated <Freshness fetchedAt={data.fetched_at} tick={tick} />
                {liveCount > 0 ? ` · refreshing every ${POLL_LIVE_MS / 1000}s` : ''}</>
            )}
          </div>
        </div>
        <div className="spacer" />
        <DayNav day={day} onChange={setDay} />
        <button className="icon-btn" onClick={() => setTick((t) => t + 1)} title="Refresh now">
          <Icon.Refresh size={16} />
        </button>
      </div>

      {loading && !data && <Loading rows={3} height={150} />}
      {error && <ErrorState error={error} onRetry={refetch} />}

      {data && data.count === 0 && (
        <Card><Empty
          icon={Icon.Slate}
          title={`No ${league.toUpperCase()} games ${dayPhrase(day)}`}
          body="Nothing is scheduled for this date. Use the arrows to look at another day."
        /></Card>
      )}

      {groups.in.length > 0 && (
        <Section title="In progress" sub={`${groups.in.length} game${groups.in.length === 1 ? '' : 's'}`}>
          <div className="grid grid-wide stagger">
            {groups.in.map((g) => <LiveCard key={g.espn_id} game={g} league={league} />)}
          </div>
        </Section>
      )}

      {groups.pre.length > 0 && (
        <Section title="Upcoming" sub={`${groups.pre.length} scheduled`}>
          <div className="grid grid-auto stagger">
            {groups.pre.map((g) => <LiveCard key={g.espn_id} game={g} league={league} compact />)}
          </div>
        </Section>
      )}

      {groups.post.length > 0 && (
        <Section title="Final" sub={`${groups.post.length} complete`}>
          <div className="grid grid-auto stagger">
            {groups.post.map((g) => <LiveCard key={g.espn_id} game={g} league={league} compact />)}
          </div>
        </Section>
      )}

      {data && (
        <Notice icon={Icon.Info}>
          Live game state comes from the public scoreboard feed, not from the engine's
          database — it is read on request and never cached longer than a few seconds.
          Scores, clock and possession are the feed's; everything else in this app is
          computed from our own play-by-play.
        </Notice>
      )}
    </>
  );
}

function Freshness({ fetchedAt, tick }) {
  const [, force] = useState(0);
  useEffect(() => {
    const id = setInterval(() => force((n) => n + 1), 1000);
    return () => clearInterval(id);
  }, [fetchedAt, tick]);
  const secs = Math.max(0, Math.round((Date.now() - new Date(fetchedAt).getTime()) / 1000));
  return <strong>{secs < 5 ? 'just now' : `${secs}s ago`}</strong>;
}

function DayNav({ day, onChange }) {
  return (
    <div className="row" style={{ gap: 6 }}>
      <button className="icon-btn" onClick={() => onChange(shiftDay(day, -1))} title="Previous day">
        <Icon.ChevronLeft size={16} />
      </button>
      <span className="chip" style={{ minWidth: 108, justifyContent: 'center' }}>{dayLabel(day)}</span>
      <button className="icon-btn" onClick={() => onChange(shiftDay(day, 1))} title="Next day">
        <Icon.ChevronRight size={16} />
      </button>
      {!isToday(day) && (
        <button className="btn btn-sm" onClick={() => onChange(localDay())}>Today</button>
      )}
    </div>
  );
}

function LiveCard({ game, league, compact = false }) {
  const live = game.state === 'in';
  const final = game.state === 'post';
  const s = game.situation;
  const hasBall = s?.possession_team_id;

  const body = (
    <div className="game-card">
      <div className="game-card-top">
        {live ? (
          <span className="badge bad">
            <span className="dot live" />
            {game.status.clock ? `Q${game.status.period} · ${game.status.clock}` : game.status.short_detail}
          </span>
        ) : final ? (
          <span className="badge">{game.status.short_detail || 'Final'}</span>
        ) : (
          <span className="num muted">{kickoffTime(game.kickoff)}</span>
        )}
        <span style={{ flex: 1 }} />
        {game.broadcast && <span className="tiny muted">{game.broadcast}</span>}
        {game.game_id && <Icon.ChevronRight size={13} className="muted" />}
      </div>

      <div className="game-teams">
        <LiveTeamRow team={game.away} hasBall={hasBall === game.away.team_id} game={game} />
        <LiveTeamRow team={game.home} hasBall={hasBall === game.home.team_id} game={game} />
      </div>

      {live && s && (s.down_distance_text || s.last_play) && (
        <div className="situation">
          {s.down_distance_text && (
            <div className="row" style={{ gap: 7 }}>
              <span className="dd num">{s.short_down_distance_text || s.down_distance_text}</span>
              {s.possession_abbr && <span className="tiny secondary">{s.possession_abbr} ball</span>}
              {s.is_red_zone && <span className="badge bad">Red zone</span>}
            </div>
          )}
          {s.down_distance_text && s.short_down_distance_text && (
            <div className="tiny muted">{s.down_distance_text}</div>
          )}
          {s.last_play && <div className="tiny muted last-play">{s.last_play}</div>}
        </div>
      )}

      {!compact && game.leaders?.length > 0 && (
        <div className="leaders">
          {game.leaders.map((l) => (
            <div key={l.category} className="leader">
              <span className="k">{l.label}</span>
              <span className="p truncate">
                {l.player}
                {l.team_abbr && <span className="muted"> · {l.team_abbr}</span>}
              </span>
              <span className="v truncate">{l.stat}</span>
            </div>
          ))}
        </div>
      )}

      {!compact && (game.away.linescores?.length > 0 || game.home.linescores?.length > 0) && (
        <Linescores game={game} />
      )}
    </div>
  );

  // Only games we could match to a canonical id link through — the rest are real games
  // we simply have no page for (an FCS opponent, usually), and a dead link is worse.
  return game.game_id ? (
    <Link to={`/games/${league}/${encodeURIComponent(game.game_id)}`} className="card card-link">
      {body}
    </Link>
  ) : (
    <div className="card">{body}</div>
  );
}

function LiveTeamRow({ team, hasBall, game }) {
  const final = game.state === 'post';
  const lost = final && team.winner === false;
  return (
    <div className={`game-team${lost ? ' loser' : ''}`}>
      <span className="poss">{hasBall ? <Icon.Football size={12} /> : null}</span>
      {team.rank && <span className="rk num">{team.rank}</span>}
      <span className="nm truncate">{team.name}</span>
      {team.record && <span className="tiny muted rec">{team.record}</span>}
      <span className="sp" />
      <span className="sc num">{team.score ?? '—'}</span>
    </div>
  );
}

function Linescores({ game }) {
  const n = Math.max(game.away.linescores?.length || 0, game.home.linescores?.length || 0);
  if (!n) return null;
  const cols = Array.from({ length: n }, (_, i) => (i < 4 ? `Q${i + 1}` : `OT${i - 3}`));
  return (
    <div className="table-scroll">
      <table className="data linescore">
        <thead>
          <tr><th /> {cols.map((c) => <th key={c}>{c}</th>)}<th>T</th></tr>
        </thead>
        <tbody>
          {[game.away, game.home].map((t) => (
            <tr key={t.abbr}>
              <td>{t.abbr}</td>
              {cols.map((c, i) => (
                <td key={c} className="num">{t.linescores?.[i] ?? '—'}</td>
              ))}
              <td className="num" style={{ fontWeight: 750 }}>{t.score ?? '—'}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
