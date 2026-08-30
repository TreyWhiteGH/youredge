/* ── Command palette ──────────────────────────────────────────────────────────
   ⌘K / Ctrl-K, or `/`. One box that reaches every player, team, coach, and page.

   Teams and coaches are fetched once and filtered locally, so those results are
   instant. Players go to the engine's alias-normalized search (`tj watt` finds
   T.J. Watt), debounced, and the request is aborted the moment you type again.
── */

import React, { useEffect, useMemo, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import Icon from '../icons';
import * as api from '../lib/api';
import { useApi, useDebounced } from '../lib/hooks';
import { useApp } from '../lib/store';
import { bareId } from '../lib/format';

const PAGES = [
  { id: 'nav:slate',    title: 'Slate',        sub: 'Upcoming games and market prices', to: '/slate', icon: Icon.Slate },
  { id: 'nav:live',     title: 'Live',         sub: 'Scores, clock, down & distance',    to: '/live', icon: Icon.Live },
  { id: 'nav:teams',    title: 'Teams',        sub: 'Every team, ranked by unit',       to: '/teams', icon: Icon.Teams },
  { id: 'nav:players',  title: 'Players',      sub: 'NFL player search',                to: '/players', icon: Icon.Players },
  { id: 'nav:compare',  title: 'Compare',      sub: 'Stack teams side by side',         to: '/compare', icon: Icon.Compare },
  { id: 'nav:lab',      title: 'Bet Lab',      sub: 'SGP modes — phase-gated',          to: '/lab', icon: Icon.Lab },
  { id: 'nav:coverage', title: 'Data coverage',sub: 'What the engine actually holds',   to: '/data', icon: Icon.Data },
];

export default function CommandPalette({ open, onClose }) {
  const [q, setQ] = useState('');
  const [cursor, setCursor] = useState(0);
  const debounced = useDebounced(q.trim(), 200);
  const navigate = useNavigate();
  const { league } = useApp();
  const inputRef = useRef(null);
  const listRef = useRef(null);

  // Focus on the frame after the overlay paints. Calling focus() synchronously in the
  // effect races the keydown that opened the palette — the element exists, but the
  // browser can still deliver the next keystroke to whatever had focus before.
  useEffect(() => {
    if (!open) return undefined;
    setQ('');
    setCursor(0);
    const raf = requestAnimationFrame(() => inputRef.current?.focus());
    return () => cancelAnimationFrame(raf);
  }, [open]);

  // Both leagues' teams, always — searching "Georgia" should work without first
  // flipping the league switch.
  const nfl = useApi(open ? 'teams:nfl' : null, (s) => api.listTeams('nfl', {}, { signal: s }), { ttl: 6e5 });
  const ncaaf = useApi(open ? 'teams:ncaaf' : null, (s) => api.listTeams('ncaaf', {}, { signal: s }), { ttl: 6e5 });

  const players = useApi(
    debounced.length >= 2 ? `psearch:${debounced}` : null,
    (s) => api.searchPlayers({ q: debounced, limit: 8 }, { signal: s }),
  );
  const coaches = useApi(
    debounced.length >= 2 ? `csearch:${debounced}` : null,
    (s) => api.searchCoaches({ q: debounced, limit: 5 }, { signal: s }),
  );

  const groups = useMemo(() => {
    const needle = debounced.toLowerCase();
    const out = [];

    const pages = needle
      ? PAGES.filter((p) => p.title.toLowerCase().includes(needle) || p.sub.toLowerCase().includes(needle))
      : PAGES;
    if (pages.length) out.push({ label: 'Go to', items: pages });

    if (needle.length >= 1) {
      const allTeams = [
        ...(nfl.data?.teams || []).map((t) => ({ ...t, league: 'nfl' })),
        ...(ncaaf.data?.teams || []).map((t) => ({ ...t, league: 'ncaaf' })),
      ];
      const hits = allTeams
        .filter((t) => t.name.toLowerCase().includes(needle) || t.abbr?.toLowerCase() === needle)
        // Prefix matches first, then the active league — the team you meant is
        // almost always the one whose name starts with what you typed.
        .sort((a, b) => {
          const ap = a.name.toLowerCase().startsWith(needle) ? 0 : 1;
          const bp = b.name.toLowerCase().startsWith(needle) ? 0 : 1;
          return ap - bp || (a.league === league ? -1 : 1) - (b.league === league ? -1 : 1);
        })
        .slice(0, 7)
        .map((t) => ({
          id: `team:${t.team_id}`, title: t.name, sub: t.league.toUpperCase(),
          right: t.abbr || bareId(t.team_id), to: `/teams/${t.league}/${encodeURIComponent(t.team_id)}`,
          icon: Icon.Shield,
        }));
      if (hits.length) out.push({ label: 'Teams', items: hits });
    }

    const p = (players.data?.results || []).map((r) => ({
      id: `player:${r.player_id}`, title: r.name,
      sub: [r.position, bareId(r.team_id)].filter(Boolean).join(' · '),
      right: r.has_career_link ? 'college link' : r.league?.toUpperCase(),
      to: `/players/${encodeURIComponent(r.player_id)}`, icon: Icon.Players,
      disabled: r.league !== 'nfl',
    }));
    if (p.length) out.push({ label: 'Players', items: p });

    const c = (coaches.data?.results || []).map((r) => ({
      id: `coach:${r.coach_id}`, title: r.name,
      sub: `${r.history_seasons} FBS seasons`,
      to: `/coaches/${encodeURIComponent(r.coach_id)}`, icon: Icon.Whistle,
    }));
    if (c.length) out.push({ label: 'Coaches', items: c });

    return out;
  }, [debounced, nfl.data, ncaaf.data, players.data, coaches.data, league]);

  const flat = useMemo(() => groups.flatMap((g) => g.items), [groups]);
  useEffect(() => { setCursor(0); }, [debounced]);

  // Keep the highlighted row in view when arrowing past the fold.
  useEffect(() => {
    const el = listRef.current?.querySelector('[data-active="true"]');
    el?.scrollIntoView({ block: 'nearest' });
  }, [cursor]);

  if (!open) return null;

  const go = (item) => {
    if (!item || item.disabled) return;
    navigate(item.to);
    onClose();
  };

  const onKeyDown = (e) => {
    if (e.key === 'ArrowDown') { e.preventDefault(); setCursor((c) => Math.min(flat.length - 1, c + 1)); }
    else if (e.key === 'ArrowUp') { e.preventDefault(); setCursor((c) => Math.max(0, c - 1)); }
    else if (e.key === 'Enter') { e.preventDefault(); go(flat[cursor]); }
    else if (e.key === 'Escape') { e.preventDefault(); onClose(); }
  };

  const searching = players.loading || coaches.loading;
  let index = -1;

  return (
    <div className="overlay" onMouseDown={(e) => { if (e.target === e.currentTarget) onClose(); }}>
      <div className="palette" role="dialog" aria-modal="true" aria-label="Search">
        <div className="palette-input">
          {searching ? <span className="spinner" /> : <Icon.Search size={17} />}
          <input
            ref={inputRef}
            value={q}
            onChange={(e) => setQ(e.target.value)}
            onKeyDown={onKeyDown}
            placeholder="Search players, teams, coaches…"
            spellCheck="false"
            autoComplete="off"
            autoFocus
          />
          <button className="icon-btn" onClick={onClose} aria-label="Close"><Icon.Close size={15} /></button>
        </div>

        <div className="palette-list" ref={listRef}>
          {flat.length === 0 && (
            <div className="state" style={{ padding: '28px 20px' }}>
              <p className="muted small">
                {debounced.length < 2 ? 'Type at least two characters.' : `Nothing matches "${debounced}".`}
              </p>
            </div>
          )}

          {groups.map((group) => (
            <div key={group.label}>
              <div className="palette-group eyebrow">{group.label}</div>
              {group.items.map((item) => {
                index += 1;
                const i = index;
                const ItemIcon = item.icon || Icon.ChevronRight;
                return (
                  <button
                    key={item.id}
                    className="palette-item"
                    data-active={i === cursor}
                    onMouseMove={() => setCursor(i)}
                    onClick={() => go(item)}
                    disabled={item.disabled}
                    style={item.disabled ? { opacity: 0.45 } : undefined}
                  >
                    <span className="muted" style={{ display: 'grid' }}><ItemIcon size={15} /></span>
                    <span style={{ minWidth: 0 }}>
                      <span className="p-title truncate" style={{ display: 'block' }}>{item.title}</span>
                      {item.sub && <span className="p-sub">{item.sub}</span>}
                    </span>
                    {item.right && <span className="p-right">{item.right}</span>}
                  </button>
                );
              })}
            </div>
          ))}
        </div>

        <div className="palette-foot">
          <span className="row" style={{ gap: 5 }}>
            <span className="kbd-group"><span className="kbd">↑</span><span className="kbd">↓</span></span> navigate
          </span>
          <span className="row" style={{ gap: 5 }}><span className="kbd">↵</span> open</span>
          <span className="row" style={{ gap: 5 }}><span className="kbd">esc</span> close</span>
          <span style={{ flex: 1 }} />
          <span>NCAAF player pages need Phase 2 identity</span>
        </div>
      </div>
    </div>
  );
}
