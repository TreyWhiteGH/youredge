/* ── App state ────────────────────────────────────────────────────────────────
   League, theme, watchlist, recents, and the compare tray. All of it is small,
   all of it survives a reload, and none of it is server state — that lives in
   the cache in hooks.js.
── */

import React, { createContext, useCallback, useContext, useMemo } from 'react';
import { usePersisted } from './hooks';

const Ctx = createContext(null);

const MAX_RECENTS = 12;
const MAX_COMPARE = 4;

export function AppProvider({ children }) {
  const [league, setLeague] = usePersisted('ye.league', 'nfl');
  const [theme, setTheme] = usePersisted('ye.theme', 'dark');
  const [watchlist, setWatchlist] = usePersisted('ye.watchlist', []);
  const [recents, setRecents] = usePersisted('ye.recents', []);
  const [compare, setCompare] = usePersisted('ye.compare', []);

  React.useEffect(() => {
    document.documentElement.setAttribute('data-theme', theme);
  }, [theme]);

  const toggleWatch = useCallback((entry) => {
    setWatchlist((list) =>
      list.some((w) => w.id === entry.id)
        ? list.filter((w) => w.id !== entry.id)
        : [...list, entry]);
  }, [setWatchlist]);

  const isWatched = useCallback(
    (id) => watchlist.some((w) => w.id === id), [watchlist]);

  // Most recent first, deduped by id, capped — a trail, not a history log.
  const pushRecent = useCallback((entry) => {
    if (!entry?.id) return;
    setRecents((list) =>
      [entry, ...list.filter((r) => r.id !== entry.id)].slice(0, MAX_RECENTS));
  }, [setRecents]);

  const toggleCompare = useCallback((entry) => {
    setCompare((list) => {
      if (list.some((c) => c.id === entry.id)) return list.filter((c) => c.id !== entry.id);
      // Comparing more than four columns stops being readable on a laptop, so the
      // oldest drops out rather than the click doing nothing.
      return [...list, entry].slice(-MAX_COMPARE);
    });
  }, [setCompare]);

  const inCompare = useCallback((id) => compare.some((c) => c.id === id), [compare]);

  const value = useMemo(() => ({
    league, setLeague,
    theme, setTheme,
    toggleTheme: () => setTheme((t) => (t === 'dark' ? 'light' : 'dark')),
    watchlist, toggleWatch, isWatched,
    recents, pushRecent, clearRecents: () => setRecents([]),
    compare, toggleCompare, inCompare, clearCompare: () => setCompare([]),
  }), [league, setLeague, theme, setTheme, watchlist, toggleWatch, isWatched,
      recents, pushRecent, setRecents, compare, toggleCompare, inCompare, setCompare]);

  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useApp() {
  const ctx = useContext(Ctx);
  if (!ctx) throw new Error('useApp must be used inside <AppProvider>');
  return ctx;
}

/** Records a visit for the recents rail. Entries are {id, kind, label, sub, to}. */
export function useTrackVisit(entry) {
  const { pushRecent } = useApp();
  const key = entry?.id;
  React.useEffect(() => {
    if (key) pushRecent(entry);
    // Only the id should retrigger — the label often arrives a render later.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key]);
}
