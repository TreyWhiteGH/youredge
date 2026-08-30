/* ── Teams index ──────────────────────────────────────────────────────────────
   A browsable, filterable list. NCAAF defaults to FBS because the 105 FCS teams
   carry no odds and no context rows — listing them makes the picker worse.
── */

import React, { useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import Icon from '../icons';
import * as api from '../lib/api';
import { useApi } from '../lib/hooks';
import { useApp } from '../lib/store';
import { Card, Empty, ErrorState, Loading, StarButton } from '../components/ui';

export default function Teams() {
  const { league, isWatched, toggleWatch, compare, toggleCompare, inCompare } = useApp();
  const [q, setQ] = useState('');
  const [rankedOnly, setRankedOnly] = useState(false);

  const { data, loading, error, refetch } = useApi(
    `teams:${league}`, (s) => api.listTeams(league, {}, { signal: s }), { ttl: 6e5 });

  // The poll only exists for college; flipping to the NFL drops the filter rather than
  // leaving a control that would silently match nothing.
  const hasPoll = (data?.ranked_count || 0) > 0;
  useEffect(() => { if (!hasPoll) setRankedOnly(false); }, [hasPoll]);

  const teams = useMemo(() => {
    const needle = q.trim().toLowerCase();
    let all = data?.teams || [];
    if (rankedOnly) all = all.filter((t) => t.rank);
    if (needle) {
      all = all.filter((t) =>
        t.name.toLowerCase().includes(needle) || t.abbr?.toLowerCase().includes(needle));
    }
    // Ranked teams lead, in poll order — a Top 25 list sorted alphabetically is not a
    // Top 25. Everyone else keeps the alphabetical order the API returned.
    return [...all].sort((a, b) => {
      if (a.rank && b.rank) return a.rank - b.rank;
      if (a.rank) return -1;
      if (b.rank) return 1;
      return 0;
    });
  }, [data, q, rankedOnly]);

  return (
    <>
      <div className="page-head">
        <div>
          <h1>{league === 'nfl' ? 'NFL' : 'FBS'} teams</h1>
          <div className="sub">
            {data ? `${teams.length} of ${data.count} teams` : 'Loading'}
            {hasPoll && data.rank_week != null && (
              <> · {data.poll}, {data.rank_season} week {data.rank_week}</>
            )}
          </div>
        </div>
        <div className="spacer" />
        {hasPoll && (
          <button className="chip" aria-pressed={rankedOnly}
            onClick={() => setRankedOnly((v) => !v)}
            title={`Show only the ${data.poll}`}>
            <Icon.Trophy size={13} /> Top 25
            <span className="tiny muted num">{data.ranked_count}</span>
          </button>
        )}
        <input className="input" style={{ maxWidth: 220 }} value={q}
          onChange={(e) => setQ(e.target.value)} placeholder="Filter teams…" />
      </div>

      {compare.length > 0 && (
        <div className="notice accent">
          <span className="ni"><Icon.Compare size={15} /></span>
          <div>
            {compare.length} team{compare.length === 1 ? '' : 's'} staged.{' '}
            <Link to="/compare" className="accent"><strong>Open compare →</strong></Link>
          </div>
        </div>
      )}

      {loading && <Loading rows={5} height={54} />}
      {error && <ErrorState error={error} onRetry={refetch} />}

      {!loading && !error && teams.length === 0 && (
        <Card><Empty icon={Icon.Teams} title="No teams match"
          body={rankedOnly && q
            ? `No ranked team matches "${q}".`
            : rankedOnly
              ? 'No poll is loaded for this league.'
              : `Nothing in ${league.toUpperCase()} matches "${q}".`} /></Card>
      )}

      <div className="grid grid-auto stagger">
        {teams.map((t) => {
          const to = `/teams/${league}/${encodeURIComponent(t.team_id)}`;
          const staged = inCompare(t.team_id);
          return (
            <Card key={t.team_id} className="card-pad row" style={{ gap: 12 }}>
              <Link to={to} className="row" style={{ gap: 11, flex: 1, minWidth: 0 }}>
                {t.rank ? (
                  <span className="rank-chip num" title={`${data.poll} — ${t.points} points`}>
                    {t.rank}
                  </span>
                ) : (
                  <span className="accent" style={{ display: 'grid' }}><Icon.Shield size={19} /></span>
                )}
                <span style={{ minWidth: 0 }}>
                  <span className="truncate" style={{ display: 'block', fontWeight: 620 }}>{t.name}</span>
                  {/* NCAAF's abbr column usually repeats the school name; show the id
                      instead of printing "Air Force" twice. */}
                  <span className="tiny muted num">
                    {t.abbr && t.abbr !== t.name ? t.abbr : t.team_id}
                  </span>
                </span>
              </Link>
              <button
                className="icon-btn"
                aria-pressed={staged}
                title={staged ? 'Remove from compare' : 'Add to compare'}
                onClick={() => toggleCompare({ id: t.team_id, kind: 'team', label: t.abbr || t.name, league, to })}
              >
                {staged ? <Icon.Check size={15} /> : <Icon.Plus size={15} />}
              </button>
              <StarButton
                active={isWatched(t.team_id)}
                onClick={() => toggleWatch({ id: t.team_id, kind: 'team', label: t.name, to })}
              />
            </Card>
          );
        })}
      </div>
    </>
  );
}
