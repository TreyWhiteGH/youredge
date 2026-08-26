/* ── Formatting ───────────────────────────────────────────────────────────────
   Presentation only. Nothing here computes a new statistic — if a number needs to
   be derived, the engine derives it, because a metric invented in the view layer
   is a metric nobody can trace.
── */

/** Nulls are real information ("not reported"), so they render as an em dash, never 0. */
export const dash = (v) => (v === null || v === undefined || Number.isNaN(v) ? '—' : v);

export const num = (v, digits = 2) =>
  v === null || v === undefined || Number.isNaN(v) ? '—' : Number(v).toFixed(digits);

export const int = (v) =>
  v === null || v === undefined || Number.isNaN(v) ? '—' : Math.round(v).toLocaleString();

export const pct = (v, digits = 1) =>
  v === null || v === undefined || Number.isNaN(v) ? '—' : `${(v * 100).toFixed(digits)}%`;

/** EPA and deltas read better with an explicit sign — "+0.15" vs "0.15". */
export const signed = (v, digits = 3) =>
  v === null || v === undefined || Number.isNaN(v)
    ? '—'
    : `${v > 0 ? '+' : v < 0 ? '−' : ''}${Math.abs(v).toFixed(digits)}`;

export const signedPct = (v, digits = 1) =>
  v === null || v === undefined || Number.isNaN(v)
    ? '—'
    : `${v > 0 ? '+' : v < 0 ? '−' : ''}${Math.abs(v * 100).toFixed(digits)}%`;

/** American odds always carry their sign; that's the whole convention. */
export const american = (v) =>
  v === null || v === undefined ? '—' : v > 0 ? `+${v}` : `${v}`;

/** A spread of 0 is "PK", and the sign matters more than the magnitude. */
export const spread = (v) =>
  v === null || v === undefined ? '—' : v === 0 ? 'PK' : v > 0 ? `+${v}` : `${v}`;

export const ordinal = (n) => {
  if (n === null || n === undefined) return '—';
  const s = ['th', 'st', 'nd', 'rd'];
  const v = n % 100;
  return n + (s[(v - 20) % 10] || s[v] || s[0]);
};

export const grade = (v) => (v === null || v === undefined ? '—' : Number(v).toFixed(1));

/* ── Time ── */

export const kickoffTime = (iso) =>
  !iso ? '—' : new Date(iso).toLocaleTimeString(undefined, { hour: 'numeric', minute: '2-digit' });

export const kickoffDay = (iso) =>
  !iso ? '—' : new Date(iso).toLocaleDateString(undefined, { weekday: 'short', month: 'short', day: 'numeric' });

export const kickoffFull = (iso) =>
  !iso ? '—' : new Date(iso).toLocaleString(undefined, {
    weekday: 'short', month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit',
  });

export function relativeTime(iso) {
  if (!iso) return '—';
  const delta = Date.now() - new Date(iso).getTime();
  const abs = Math.abs(delta);
  const mins = Math.round(abs / 60000);
  const fmt =
    mins < 1 ? 'just now'
    : mins < 60 ? `${mins}m`
    : abs < 864e5 ? `${Math.round(mins / 60)}h`
    : abs < 2592e6 ? `${Math.round(abs / 864e5)}d`
    : `${Math.round(abs / 2592e6)}mo`;
  if (fmt === 'just now') return fmt;
  return delta > 0 ? `${fmt} ago` : `in ${fmt}`;
}

/* ── Semantics ── */

/** Rank → 0..1 percentile, where 1 is best. `of` is the field size the engine ranked in. */
export const rankPct = (rank, of) =>
  !rank || !of || of < 2 ? null : 1 - (rank - 1) / (of - 1);

/**
 * Rank → plain-English tier. Used where a raw licensed grade is not shown: it carries
 * the decision-relevant part of the number, and it does not overstate precision the way
 * a grade to one decimal does on cards that are only trustworthy at the extremes.
 */
export function tierLabel(rank, of) {
  if (!rank || !of) return '—';
  if (rank <= 3) return 'Elite';
  if (rank <= Math.ceil(of * 0.2)) return 'Top tier';
  if (rank <= Math.ceil(of * 0.4)) return 'Above average';
  if (rank <= Math.ceil(of * 0.6)) return 'Average';
  if (rank <= Math.ceil(of * 0.8)) return 'Below average';
  return 'Bottom tier';
}

/** The single colour scale in the app. Percentile in, CSS variable out. */
export function scaleColor(p) {
  if (p === null || p === undefined) return 'var(--text-faint)';
  if (p >= 0.78) return 'var(--good)';
  if (p >= 0.56) return 'var(--accent)';
  if (p >= 0.34) return 'var(--text-secondary)';
  if (p >= 0.16) return 'var(--warn)';
  return 'var(--bad)';
}

/**
 * A compact team label. NCAAF's `abbr` column frequently holds the full school name,
 * so anything longer than a real abbreviation falls back to a clipped name — the goal
 * is a column that stays a column, not a guaranteed three letters.
 */
export function shortLabel(team) {
  if (!team) return '—';
  if (team.abbr && team.abbr.length <= 5) return team.abbr;
  const name = team.name || team.abbr || '';
  return name.length <= 14 ? name : `${name.slice(0, 13)}…`;
}

/** Team id → display abbreviation, without a round trip. `ncaaf:59` has no abbr. */
export const bareId = (id) => (id ? String(id).split(':').slice(1).join(':') : '');
export const leagueOf = (id) => (id ? String(id).split(':')[0] : null);

export const SCORE_STATES = ['trail_big', 'trail_1sc', 'tied', 'lead_1sc', 'lead_big'];
export const SCORE_STATE_LABEL = {
  trail_big: 'Trail 9+',
  trail_1sc: 'Trail 1sc',
  tied: 'Tied',
  lead_1sc: 'Lead 1sc',
  lead_big: 'Lead 9+',
};

export const UNIT_LABEL = {
  pass_blocking: 'Pass blocking',
  run_blocking: 'Run blocking',
  blocking: 'Blocking (all)',
  pass_rush: 'Pass rush',
  run_defense: 'Run defense',
  coverage: 'Coverage',
  receiving: 'Receiving',
  rushing: 'Rushing',
};

export const CONDITION_LABEL = {
  outdoors: 'Outdoors', dome: 'Dome', closed: 'Roof closed',
  open: 'Roof open', retractable: 'Retractable',
};
