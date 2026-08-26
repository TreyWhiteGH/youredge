/* ── Data hooks ───────────────────────────────────────────────────────────────
   A small fetch layer rather than a query library: one in-memory cache keyed by
   the call, request de-duplication, and abort on unmount. That is all this app
   needs, and it keeps the dependency list at three packages.
── */

import { useCallback, useEffect, useRef, useState } from 'react';
import { NotBuiltYet } from './api';

const cache = new Map();    // key -> { data, at }
const inflight = new Map(); // key -> { promise, controller, refs }

const TTL = 60_000;

export function invalidate(prefix) {
  for (const key of cache.keys()) if (!prefix || key.startsWith(prefix)) cache.delete(key);
}

/**
 * @param key   stable cache key, or null to skip the request entirely
 * @param fn    (signal) => Promise — receives an AbortSignal
 */
export function useApi(key, fn, { enabled = true, ttl = TTL } = {}) {
  const [state, setState] = useState(() => {
    const hit = key && cache.get(key);
    return hit && Date.now() - hit.at < ttl
      ? { data: hit.data, error: null, loading: false }
      : { data: null, error: null, loading: Boolean(key) && enabled };
  });

  const fnRef = useRef(fn);
  fnRef.current = fn;

  const run = useCallback((force = false) => {
    if (!key || !enabled) { setState({ data: null, error: null, loading: false }); return undefined; }

    const hit = cache.get(key);
    if (!force && hit && Date.now() - hit.at < ttl) {
      setState({ data: hit.data, error: null, loading: false });
      return undefined;
    }

    // Two components asking for the same key at the same moment share one request.
    // The entry is refcounted, and unsubscribing is what aborts it — adopting a promise
    // some other subscriber already aborted would leave this one waiting forever.
    let entry = force ? null : inflight.get(key);
    if (!entry) {
      const controller = new AbortController();
      const promise = fnRef.current(controller.signal)
        .then((data) => { cache.set(key, { data, at: Date.now() }); return data; })
        .finally(() => { if (inflight.get(key)?.promise === promise) inflight.delete(key); });
      entry = { promise, controller, refs: 0 };
      inflight.set(key, entry);
    }
    entry.refs += 1;

    let cancelled = false;
    setState((s) => ({ ...s, loading: true, error: null }));

    entry.promise.then(
      (data) => { if (!cancelled) setState({ data, error: null, loading: false }); },
      (error) => {
        if (cancelled || error?.name === 'AbortError') return;
        setState({ data: null, error, loading: false });
      },
    );

    return () => {
      cancelled = true;
      entry.refs -= 1;
      if (entry.refs <= 0) {
        // Dropped synchronously so an immediate remount (React StrictMode does exactly
        // this in development) starts a fresh request rather than adopting a dead one.
        if (inflight.get(key) === entry) inflight.delete(key);
        entry.controller.abort();
      }
    };
  }, [key, enabled, ttl]);

  useEffect(() => run(), [run]);

  return {
    ...state,
    // A deliberately-unbuilt surface is its own state; conflating it with failure is
    // what makes an honest 501 look like a bug.
    notBuilt: state.error instanceof NotBuiltYet ? state.error : null,
    refetch: () => run(true),
  };
}

/* ── localStorage-backed state ── */

export function usePersisted(key, initial) {
  const [value, setValue] = useState(() => {
    try {
      const raw = localStorage.getItem(key);
      return raw === null ? initial : JSON.parse(raw);
    } catch { return initial; }
  });
  useEffect(() => {
    try { localStorage.setItem(key, JSON.stringify(value)); } catch { /* quota / private mode */ }
  }, [key, value]);
  return [value, setValue];
}

/* ── Keyboard ── */

/** Global hotkeys. Ignores keystrokes aimed at a text field, except for Escape. */
export function useHotkeys(map) {
  const ref = useRef(map);
  ref.current = map;
  useEffect(() => {
    const onKey = (e) => {
      const el = e.target;
      const typing = el && (el.tagName === 'INPUT' || el.tagName === 'TEXTAREA' || el.isContentEditable);
      if (typing && e.key !== 'Escape') return;

      const combo = [
        e.metaKey || e.ctrlKey ? 'mod' : null,
        e.shiftKey ? 'shift' : null,
        e.key.toLowerCase(),
      ].filter(Boolean).join('+');

      const handler = ref.current[combo] || ref.current[e.key.toLowerCase()];
      if (handler) { e.preventDefault(); handler(e); }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, []);
}

/** Debounce — used by the palette so typing doesn't fire a request per keystroke. */
export function useDebounced(value, delay = 220) {
  const [v, setV] = useState(value);
  useEffect(() => {
    const t = setTimeout(() => setV(value), delay);
    return () => clearTimeout(t);
  }, [value, delay]);
  return v;
}

/** Counts a number up on mount. Purely decorative; it never changes the value shown. */
export function useCountUp(target, { duration = 620, enabled = true } = {}) {
  const [value, setValue] = useState(enabled ? 0 : target);
  const prefersReduced = useRef(
    typeof window !== 'undefined' &&
    window.matchMedia?.('(prefers-reduced-motion: reduce)').matches,
  );

  useEffect(() => {
    if (!enabled || target === null || target === undefined || Number.isNaN(target)) {
      setValue(target); return;
    }
    if (prefersReduced.current) { setValue(target); return; }

    let raf;
    const start = performance.now();
    const tick = (now) => {
      const t = Math.min(1, (now - start) / duration);
      const eased = 1 - (1 - t) ** 3;
      setValue(target * eased);
      if (t < 1) raf = requestAnimationFrame(tick);
      else setValue(target);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [target, duration, enabled]);

  return value;
}
