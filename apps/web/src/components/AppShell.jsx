/* ── App shell ────────────────────────────────────────────────────────────────
   Header, navigation rail, mobile tab bar, compare tray, and the global keyboard
   layer. Everything persistent lives here so pages stay purely about their data.
── */

import React, { useState } from 'react';
import { NavLink, Outlet, useLocation, useNavigate } from 'react-router-dom';
import Icon from '../icons';
import * as api from '../lib/api';
import { useApi, useHotkeys } from '../lib/hooks';
import { useApp } from '../lib/store';
import { relativeTime } from '../lib/format';
import CommandPalette from './CommandPalette';
import ShortcutSheet from './ShortcutSheet';

const NAV = [
  { to: '/slate',   label: 'Slate',    icon: Icon.Slate },
  { to: '/teams',   label: 'Teams',    icon: Icon.Teams },
  { to: '/players', label: 'Players',  icon: Icon.Players },
  { to: '/compare', label: 'Compare',  icon: Icon.Compare },
  { to: '/lab',     label: 'Bet Lab',  icon: Icon.Lab },
  { to: '/data',    label: 'Data',     icon: Icon.Data },
];

const MOBILE_NAV = NAV.filter((n) => n.to !== '/compare');

export default function AppShell() {
  const [paletteOpen, setPaletteOpen] = useState(false);
  const [helpOpen, setHelpOpen] = useState(false);
  const { league, setLeague, theme, toggleTheme, compare, toggleCompare, clearCompare, watchlist, recents } = useApp();
  const navigate = useNavigate();
  const { pathname } = useLocation();
  // On /compare the tray is redundant — it links to the page you are already reading,
  // and being fixed to the viewport it sits on top of the last rows of the table.
  const showTray = compare.length > 0 && pathname !== '/compare';

  // Health doubles as the connection indicator in the header. A 30s poll is enough
  // to notice the engine going away without being a background load.
  const health = useApi('health', (s) => api.getHealth({ signal: s }), { ttl: 30_000 });

  useHotkeys({
    'mod+k': () => setPaletteOpen(true),
    '/': () => setPaletteOpen(true),
    '?': () => setHelpOpen((v) => !v),
    'escape': () => { setPaletteOpen(false); setHelpOpen(false); },
    'g': () => {},
    '1': () => navigate('/slate'),
    '2': () => navigate('/teams'),
    '3': () => navigate('/players'),
    '4': () => navigate('/compare'),
    '5': () => navigate('/lab'),
    '6': () => navigate('/data'),
    'l': () => setLeague(league === 'nfl' ? 'ncaaf' : 'nfl'),
    't': () => toggleTheme(),
  });

  const isMac = typeof navigator !== 'undefined' && /Mac|iPhone|iPad/.test(navigator.platform || '');
  const engineUp = health.data?.status === 'ok';

  return (
    <div className="shell">
      <header className="topbar">
        <NavLink to="/slate" className="brand">
          <span className="brand-mark"><Icon.Logo size={24} /></span>
          <span className="brand-text">YourEdge</span>
        </NavLink>

        <div className="league-switch" role="group" aria-label="League">
          <button aria-pressed={league === 'nfl'} onClick={() => setLeague('nfl')}>NFL</button>
          <button aria-pressed={league === 'ncaaf'} onClick={() => setLeague('ncaaf')}>NCAAF</button>
        </div>

        <button className="search-trigger" onClick={() => setPaletteOpen(true)}>
          <Icon.Search size={14} />
          <span className="label">Search players, teams, coaches…</span>
          <span className="kbd-group">
            <span className="kbd">{isMac ? '⌘' : 'Ctrl'}</span><span className="kbd">K</span>
          </span>
        </button>

        <div className="topbar-spacer" />

        <div className="topbar-actions">
          <span className="badge" title={
            health.loading ? 'Checking the engine'
            : engineUp ? `Engine healthy · database connected` : 'Engine unreachable'
          }>
            <span className={`pulse-dot ${engineUp ? 'live' : 'down'}`} />
            <span className="tiny">{health.loading ? '…' : engineUp ? 'Engine' : 'Offline'}</span>
          </span>
          <button className="icon-btn" onClick={() => setHelpOpen(true)} title="Keyboard shortcuts (?)">
            <Icon.CommandKey size={16} />
          </button>
          <button className="icon-btn" onClick={toggleTheme}
            title={theme === 'dark' ? 'Switch to light (T)' : 'Switch to dark (T)'}>
            {theme === 'dark' ? <Icon.Sun size={16} /> : <Icon.Moon size={16} />}
          </button>
        </div>
      </header>

      <div className="body-grid">
        <aside className="rail">
          <nav className="rail-group">
            {NAV.map((item) => (
              <NavLink key={item.to} to={item.to}
                className={({ isActive }) => `nav-item${isActive ? ' active' : ''}`}>
                <item.icon size={16} />
                {item.label}
                {item.to === '/compare' && compare.length > 0 && (
                  <span className="count num">{compare.length}</span>
                )}
              </NavLink>
            ))}
          </nav>

          {watchlist.length > 0 && (
            <div className="rail-group">
              <div className="rail-title eyebrow">Watchlist</div>
              {watchlist.slice(0, 8).map((w) => (
                <NavLink key={w.id} to={w.to} className="nav-item">
                  <Icon.Star size={14} filled />
                  <span className="truncate">{w.label}</span>
                </NavLink>
              ))}
            </div>
          )}

          {recents.length > 0 && (
            <div className="rail-group">
              <div className="rail-title eyebrow">Recent</div>
              {recents.slice(0, 6).map((r) => (
                <NavLink key={r.id} to={r.to} className="nav-item">
                  <Icon.Clock size={14} />
                  <span className="truncate">{r.label}</span>
                </NavLink>
              ))}
            </div>
          )}

          <div className="rail-group" style={{ marginTop: 'auto', paddingTop: 12 }}>
            <div className="tiny" style={{ color: 'var(--text-faint)', padding: '0 10px', lineHeight: 1.6 }}>
              {health.data?.version && <div>Engine v{health.data.version}</div>}
              <div>Analysis, not advice. No bet is a valid outcome.</div>
            </div>
          </div>
        </aside>

        {/* Extra bottom room while the tray is up, so it never covers the last row. */}
        <main className="main" style={showTray ? { paddingBottom: 56 } : undefined}>
          <Outlet />
        </main>
      </div>

      <nav className="tabbar">
        {MOBILE_NAV.map((item) => (
          <NavLink key={item.to} to={item.to}
            className={({ isActive }) => (isActive ? 'active' : '')}>
            <item.icon size={18} />
            {item.label}
          </NavLink>
        ))}
      </nav>

      {showTray && (
        <div className="tray">
          <span className="eyebrow">Compare</span>
          <div className="tray-items">
            {compare.map((c) => (
              <span key={c.id} className="tray-item">
                <span className="truncate" style={{ maxWidth: 110 }}>{c.label}</span>
                <button onClick={() => toggleCompare(c)} aria-label={`Remove ${c.label}`}>
                  <Icon.Close size={12} />
                </button>
              </span>
            ))}
          </div>
          <button className="btn btn-sm btn-primary" onClick={() => navigate('/compare')}>
            Open <Icon.ChevronRight size={13} />
          </button>
          <button className="icon-btn" onClick={clearCompare} aria-label="Clear compare">
            <Icon.Close size={14} />
          </button>
        </div>
      )}

      <CommandPalette open={paletteOpen} onClose={() => setPaletteOpen(false)} />
      <ShortcutSheet open={helpOpen} onClose={() => setHelpOpen(false)} />
    </div>
  );
}
