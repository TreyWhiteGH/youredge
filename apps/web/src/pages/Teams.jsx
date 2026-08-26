/* ── Teams index ──────────────────────────────────────────────────────────────
   A browsable, filterable list. NCAAF defaults to FBS because the 105 FCS teams
   carry no odds and no context rows — listing them makes the picker worse.
── */

import React, { useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import Icon from '../icons';
import * as api from '../lib/api';
import { useApi } from '../lib/hooks';
import { useApp } from '../lib/store';
import { Card, Empty, ErrorState, Loading, StarButton } from '../components/ui';

export default function Teams() {
  const { league, isWatched, toggleWatch, compare, toggleCompare, inCompare } = useApp();
  const [q, setQ] = useState('');

  const { data, loading, error, refetch } = useApi(
    `teams:${league}`, (s) => api.listTeams(league, {}, { signal: s }), { ttl: 6e5 });

  const teams = useMemo(() => {
    const needle = q.trim().toLowerCase();
    const all = data?.teams || [];
    if (!needle) return all;
    return all.filter((t) =>
      t.name.toLowerCase().includes(needle) || t.abbr?.toLowerCase().includes(needle));
  }, [data, q]);

  return (
    <>
      <div className="page-head">
        <div>
          <h1>{league === 'nfl' ? 'NFL' : 'FBS'} teams</h1>
          <div className="sub">
            {data ? `${data.count} teams` : 'Loading'} · open one for unit cards, grades and tendencies
          </div>
        </div>
        <div className="spacer" />
        <input className="input" style={{ maxWidth: 240 }} value={q}
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
          body={`Nothing in ${league.toUpperCase()} matches "${q}".`} /></Card>
      )}

      <div className="grid grid-auto stagger">
        {teams.map((t) => {
          const to = `/teams/${league}/${encodeURIComponent(t.team_id)}`;
          const staged = inCompare(t.team_id);
          return (
            <Card key={t.team_id} className="card-pad row" style={{ gap: 12 }}>
              <Link to={to} className="row" style={{ gap: 11, flex: 1, minWidth: 0 }}>
                <span className="accent" style={{ display: 'grid' }}><Icon.Shield size={19} /></span>
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
