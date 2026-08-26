/* ── Players ──────────────────────────────────────────────────────────────────
   Search is the whole page. The engine's endpoint is alias-normalized, so "tj
   watt" and "T.J. Watt" land on the same person, and it returns NCAAF hits too —
   those are shown but not linked, because college player surfaces are Phase 2.
── */

import React, { useState } from 'react';
import { Link } from 'react-router-dom';
import Icon from '../icons';
import * as api from '../lib/api';
import { useApi, useDebounced } from '../lib/hooks';
import { useApp } from '../lib/store';
import { bareId } from '../lib/format';
import { Badge, Card, Empty, ErrorState, Loading, Notice, StarButton } from '../components/ui';

const SUGGESTIONS = ['Mahomes', 'Lamar Jackson', 'Ja’Marr Chase', 'Micah Parsons', 'Sauce Gardner'];

export default function Players() {
  const [q, setQ] = useState('');
  const term = useDebounced(q.trim(), 220);
  const { isWatched, toggleWatch, recents } = useApp();

  const { data, loading, error, refetch } = useApi(
    term.length >= 2 ? `psearch:${term}` : null,
    (s) => api.searchPlayers({ q: term, limit: 25 }, { signal: s }),
  );

  const results = data?.results || [];

  return (
    <>
      <div className="page-head">
        <div>
          <h1>Players</h1>
          <div className="sub">
            Game logs, situational splits, opponent history, and QB clutch profiles.
          </div>
        </div>
      </div>

      <div className="row" style={{ gap: 10 }}>
        <span style={{ flex: 1, position: 'relative', display: 'flex', alignItems: 'center' }}>
          <span className="muted" style={{ position: 'absolute', left: 11, display: 'grid' }}>
            <Icon.Search size={15} />
          </span>
          <input className="input" style={{ paddingLeft: 34, height: 40, fontSize: 15 }}
            value={q} onChange={(e) => setQ(e.target.value)} autoFocus
            placeholder="Search any NFL player…" spellCheck="false" />
        </span>
      </div>

      {!term && (
        <>
          <div className="scroll-x">
            {SUGGESTIONS.map((s) => (
              <button key={s} className="chip" onClick={() => setQ(s)}>{s}</button>
            ))}
          </div>
          {recents.filter((r) => r.kind === 'player').length > 0 && (
            <Card>
              <div className="card-pad col" style={{ gap: 8 }}>
                <div className="eyebrow">Recently viewed</div>
                {recents.filter((r) => r.kind === 'player').map((r) => (
                  <Link key={r.id} to={r.to} className="row" style={{ gap: 9, padding: '4px 0' }}>
                    <Icon.Players size={15} />
                    <span style={{ fontWeight: 600 }}>{r.label}</span>
                    <span style={{ flex: 1 }} />
                    <Icon.ChevronRight size={14} />
                  </Link>
                ))}
              </div>
            </Card>
          )}
        </>
      )}

      {loading && <Loading rows={4} height={54} />}
      {error && <ErrorState error={error} onRetry={refetch} />}

      {term.length >= 2 && !loading && !error && results.length === 0 && (
        <Card><Empty icon={Icon.Players} title="No player found"
          body={`Nothing matches "${term}". Search is alias-normalized, so initials and nicknames should work.`} /></Card>
      )}

      {results.length > 0 && (
        <div className="grid grid-auto stagger">
          {results.map((r) => {
            const nfl = r.league === 'nfl';
            const to = `/players/${encodeURIComponent(r.player_id)}`;
            const inner = (
              <>
                <span className={nfl ? 'accent' : 'muted'} style={{ display: 'grid' }}>
                  <Icon.Players size={18} />
                </span>
                <span style={{ minWidth: 0, flex: 1 }}>
                  <span className="truncate row" style={{ gap: 7, fontWeight: 620 }}>
                    {r.name}
                    {r.has_career_link && <Badge tone="accent">college link</Badge>}
                  </span>
                  <span className="tiny muted">
                    {[r.position, bareId(r.team_id), r.league?.toUpperCase()].filter(Boolean).join(' · ')}
                  </span>
                </span>
              </>
            );
            return (
              <Card key={r.player_id} className="card-pad row" style={{ gap: 11 }}>
                {nfl ? (
                  <Link to={to} className="row" style={{ gap: 11, flex: 1, minWidth: 0 }}>{inner}</Link>
                ) : (
                  <span className="row" style={{ gap: 11, flex: 1, minWidth: 0, opacity: 0.55 }}
                    title="College player pages need Phase 2 identity work">{inner}</span>
                )}
                {nfl && (
                  <StarButton active={isWatched(r.player_id)}
                    onClick={() => toggleWatch({ id: r.player_id, kind: 'player', label: r.name, to })} />
                )}
              </Card>
            );
          })}
        </div>
      )}

      {results.some((r) => r.league === 'ncaaf') && (
        <Notice icon={Icon.Lock}>
          College results are shown but not clickable. NCAAF play-by-play carries no player
          ids (CFBD's REST endpoints omit them), so there are no college player pages yet —
          that is Phase 2, not a missing link.
        </Notice>
      )}
    </>
  );
}
