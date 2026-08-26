/* ── Slate ────────────────────────────────────────────────────────────────────
   The landing surface: what is coming up, what the market says about it, and a
   direct line into anything on the card. Games are grouped by day because that
   is how a football week is actually read.
── */

import React, { useMemo, useState } from 'react';
import Icon from '../icons';
import * as api from '../lib/api';
import { useApi } from '../lib/hooks';
import { useApp } from '../lib/store';
import { kickoffDay, relativeTime } from '../lib/format';
import { Card, Empty, ErrorState, Loading, Notice, Section } from '../components/ui';
import GameCard from '../components/GameCard';

const RANGES = [
  { value: 'upcoming', label: 'Upcoming' },
  { value: 'recent', label: 'Results' },
];

export default function Slate() {
  const { league, watchlist } = useApp();
  const [range, setRange] = useState('upcoming');

  const upcoming = range === 'upcoming';
  const params = upcoming
    ? { upcoming: true, limit: 60, order: 'asc' }
    : { status: 'final', limit: 40, order: 'desc' };

  const key = `games:${league}:${range}`;
  const { data, loading, error, refetch } = useApi(
    key, (s) => api.listGames(league, params, { signal: s }), { ttl: 120_000 });

  const days = useMemo(() => {
    const groups = new Map();
    for (const g of data?.games || []) {
      const day = g.kickoff ? g.kickoff.slice(0, 10) : 'tbd';
      if (!groups.has(day)) groups.set(day, []);
      groups.get(day).push(g);
    }
    return [...groups.entries()];
  }, [data]);

  const watched = useMemo(() => {
    const ids = new Set(watchlist.map((w) => w.id));
    return (data?.games || []).filter(
      (g) => ids.has(g.home.team_id) || ids.has(g.away.team_id));
  }, [data, watchlist]);

  const lastOdds = useMemo(() => {
    const stamps = (data?.games || [])
      .map((g) => g.odds?.captured_at).filter(Boolean).sort();
    return stamps[stamps.length - 1] || null;
  }, [data]);

  return (
    <>
      <div className="page-head">
        <div>
          <h1>{league === 'nfl' ? 'NFL' : 'College football'} slate</h1>
          <div className="sub">
            {upcoming ? 'Scheduled games and the prices books are showing.'
                      : 'Completed games, most recent first.'}
          </div>
        </div>
        <div className="spacer" />
        <div className="row" style={{ gap: 6 }}>
          {RANGES.map((r) => (
            <button key={r.value} className="chip" aria-pressed={range === r.value}
              onClick={() => setRange(r.value)}>{r.label}</button>
          ))}
          <button className="icon-btn" onClick={refetch} title="Refresh">
            <Icon.Refresh size={16} />
          </button>
        </div>
      </div>

      {upcoming && lastOdds && (
        <Notice icon={Icon.Clock}>
          Prices last polled <strong>{relativeTime(lastOdds)}</strong>. Every probability shown
          on this app is a <strong>de-vigged market price</strong>, not a model projection —
          the simulator that would produce one is Phase 1.
        </Notice>
      )}

      {loading && <Loading rows={4} height={150} />}
      {error && <ErrorState error={error} onRetry={refetch} />}

      {!loading && !error && days.length === 0 && (
        <Card><Empty
          icon={Icon.Slate}
          title={upcoming ? 'No games scheduled' : 'No completed games'}
          body={upcoming
            ? 'The schedule for this league has no future kickoffs loaded. Run the schedules ingest to populate it.'
            : 'No finals are stored for this league yet.'}
        /></Card>
      )}

      {watched.length > 0 && (
        <Section title="On your watchlist" sub={`${watched.length} game${watched.length === 1 ? '' : 's'} involving teams you follow`}>
          <div className="grid grid-auto stagger">
            {watched.map((g) => <GameCard key={`w-${g.game_id}`} game={g} />)}
          </div>
        </Section>
      )}

      {days.map(([day, games]) => (
        <Section
          key={day}
          title={day === 'tbd' ? 'Date to be confirmed' : kickoffDay(`${day}T12:00:00Z`)}
          sub={`${games.length} game${games.length === 1 ? '' : 's'}`}
        >
          <div className="grid grid-auto stagger">
            {games.map((g) => <GameCard key={g.game_id} game={g} showDate={false} />)}
          </div>
        </Section>
      ))}
    </>
  );
}
