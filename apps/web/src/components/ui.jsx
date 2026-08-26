/* ── UI primitives ────────────────────────────────────────────────────────────
   The vocabulary every page is built from. Two rules hold throughout:
   a null value renders as an em dash and never as zero, and rank colour comes
   only from `scaleColor`, so the same hue means the same thing everywhere.
── */

import React, { useEffect, useRef, useState } from 'react';
import Icon from '../icons';
import { NotBuiltYet } from '../lib/api';
import { useCountUp } from '../lib/hooks';
import { dash, num, ordinal, rankPct, scaleColor, tierLabel } from '../lib/format';

/* ── Containers ── */

export const Card = ({ children, className = '', ...rest }) => (
  <div className={`card ${className}`} {...rest}>{children}</div>
);

export function CardHead({ title, sub, icon: IconCmp, action }) {
  return (
    <div className="card-head">
      {IconCmp && <span className="muted" style={{ display: 'grid' }}><IconCmp size={15} /></span>}
      <div style={{ minWidth: 0 }}>
        <h3 className="truncate">{title}</h3>
        {sub && <div className="tiny muted truncate" style={{ marginTop: 1 }}>{sub}</div>}
      </div>
      <div className="spacer" />
      {action}
    </div>
  );
}

export const Section = ({ title, sub, action, children }) => (
  <section className="col" style={{ gap: 11 }}>
    {(title || action) && (
      <div className="row">
        <div style={{ minWidth: 0 }}>
          {title && <div className="eyebrow">{title}</div>}
          {sub && <div className="tiny muted" style={{ marginTop: 2 }}>{sub}</div>}
        </div>
        <div style={{ flex: 1 }} />
        {action}
      </div>
    )}
    {children}
  </section>
);

/* ── Badges ── */

export const Badge = ({ tone = '', children, dot, live }) => (
  <span className={`badge ${tone}`}>
    {dot && <span className={`dot${live ? ' live' : ''}`} />}
    {children}
  </span>
);

export function RankBadge({ rank, of }) {
  if (!rank) return <span className="muted">—</span>;
  const p = rankPct(rank, of);
  return (
    <span className="badge" style={{ color: scaleColor(p), background: 'var(--bg-input)' }}>
      <span className="num">{ordinal(rank)}</span>
      {of ? <span className="muted" style={{ fontWeight: 500 }}>of {of}</span> : null}
    </span>
  );
}

/* ── Stats ── */

export function Stat({ label, value, sub, tone, size = 'md', animate = false }) {
  const numeric = typeof value === 'number';
  const animated = useCountUp(numeric && animate ? value : null, { enabled: numeric && animate });
  const shown = numeric && animate ? animated : value;
  return (
    <div className="stat">
      <span className="stat-label">{label}</span>
      <span className={`stat-value num ${size === 'sm' ? 'sm' : ''}`} style={tone ? { color: tone } : undefined}>
        {typeof shown === 'number' ? num(shown, Number.isInteger(value) ? 0 : 2) : dash(shown)}
      </span>
      {sub && <span className="stat-sub">{sub}</span>}
    </div>
  );
}

export const StatTile = (props) => (
  <div className="stat-tile"><Stat {...props} /></div>
);

/* ── Rank bar ── */
/**
 * The workhorse comparison element: value, league rank, and where the field's
 * average sits — one row, readable without reading the numbers.
 *
 * Length and colour carry different information on purpose. Colour is always the
 * league percentile. Length is the value's share of `max` when the metric has a real
 * scale (a PFF grade runs 0–100), and the percentile only when it does not (EPA per
 * dropback has no natural ceiling). Mixing the two — a percentile-length bar next to a
 * magnitude-placed average marker — would put the fill and the marker on scales that
 * cannot be compared, which is worse than showing no marker at all.
 */
export function RankBar({ label, value, rank, of, leagueAvg, format = (v) => num(v, 3), max,
                         showValue = true }) {
  const p = rankPct(rank, of);
  const color = scaleColor(p);
  const [mounted, setMounted] = useState(false);
  useEffect(() => {
    const t = requestAnimationFrame(() => setMounted(true));
    return () => cancelAnimationFrame(t);
  }, []);

  const width = max
    ? Math.min(1, Math.abs(value ?? 0) / max)
    : p !== null ? p : 0;
  // Only drawn on the magnitude scale, where it means the same thing as the fill.
  const avgLeft =
    max && leagueAvg !== undefined && leagueAvg !== null
      ? Math.min(1, Math.abs(leagueAvg) / max)
      : null;

  return (
    <div className="rankbar">
      <div className="rankbar-head">
        <span className="label truncate">{label}</span>
        <span className="spacer" />
        {rank ? <span className="tiny num" style={{ color }}>{ordinal(rank)}</span> : null}
        <span className={`value${showValue ? ' num' : ''}`} style={showValue ? undefined : { color }}>
          {showValue ? format(value) : tierLabel(rank, of)}
        </span>
      </div>
      <div className="rankbar-track">
        <div className="rankbar-fill"
          style={{ width: `${(mounted ? width : 0) * 100}%`, background: color }} />
        {avgLeft !== null && <div className="rankbar-avg" style={{ left: `${avgLeft * 100}%` }} />}
      </div>
      {leagueAvg !== undefined && leagueAvg !== null && (
        <div className="tiny" style={{ color: 'var(--text-faint)' }}>
          league {format(leagueAvg)}
        </div>
      )}
    </div>
  );
}

/* ── Sparkline ── */
/** Hand-rolled so there is no chart dependency and no runtime theme mismatch. */
export function Sparkline({ values = [], width = 88, height = 24, color, baseline = null }) {
  const clean = values.filter((v) => v !== null && v !== undefined && !Number.isNaN(v));
  if (clean.length < 2) return <span className="tiny muted">—</span>;

  const min = Math.min(...clean, baseline ?? Infinity);
  const max = Math.max(...clean, baseline ?? -Infinity);
  const span = max - min || 1;
  const x = (i) => (i / (values.length - 1)) * width;
  const y = (v) => height - ((v - min) / span) * height;

  let d = '';
  let started = false;
  values.forEach((v, i) => {
    if (v === null || v === undefined || Number.isNaN(v)) return;
    d += `${started ? 'L' : 'M'}${x(i).toFixed(1)} ${y(v).toFixed(1)}`;
    started = true;
  });

  const last = clean[clean.length - 1];
  const stroke = color || (last >= (baseline ?? clean[0]) ? 'var(--good)' : 'var(--bad)');

  return (
    <svg className="spark" width={width} height={height} viewBox={`0 0 ${width} ${height}`}>
      {baseline !== null && (
        <line x1="0" x2={width} y1={y(baseline)} y2={y(baseline)}
          stroke="var(--text-faint)" strokeWidth="1" strokeDasharray="2 2" opacity="0.5" />
      )}
      <path className="spark-line" d={d} stroke={stroke} />
      <circle cx={x(values.length - 1)} cy={y(last)} r="2" fill={stroke} />
    </svg>
  );
}

/* ── States ── */

export const Spinner = () => <span className="spinner" />;

export function Loading({ label = 'Loading', rows = 3, height = 72 }) {
  return (
    <div className="col" style={{ gap: 8 }} role="status" aria-label={label}>
      {Array.from({ length: rows }).map((_, i) => (
        <div key={i} className="skeleton" style={{ height, opacity: 1 - i * 0.16 }} />
      ))}
    </div>
  );
}

export function Empty({ title = 'Nothing here', body, icon: IconCmp = Icon.Search, action }) {
  return (
    <div className="state">
      <span className="state-icon"><IconCmp size={19} /></span>
      <h4>{title}</h4>
      {body && <p>{body}</p>}
      {action}
    </div>
  );
}

/**
 * Error and "not built yet" are different things and look different. A 501 from the
 * engine is a roadmap statement, so it renders as one — no red, no retry button
 * that could not possibly help.
 */
export function ErrorState({ error, onRetry }) {
  if (error instanceof NotBuiltYet) return <PhaseGate error={error} />;
  const missing = error?.status === 404;
  return (
    <div className="state">
      <span className="state-icon" style={missing ? undefined : { color: 'var(--bad)' }}>
        {missing ? <Icon.Search size={19} /> : <Icon.Alert size={19} />}
      </span>
      <h4>{missing ? 'No data for this selection' : 'Could not load'}</h4>
      <p>{error?.message || 'Something went wrong.'}</p>
      {onRetry && !missing && (
        <button className="btn btn-sm" onClick={onRetry}>
          <Icon.Refresh size={13} /> Try again
        </button>
      )}
    </div>
  );
}

export function PhaseGate({ error, title }) {
  const phase = error?.phase;
  return (
    <div className="notice accent">
      <span className="ni"><Icon.Lock size={16} /></span>
      <div>
        <strong>{title || 'Not built yet'}</strong>
        {phase && <span className="muted"> · {phase}</span>}
        <div style={{ marginTop: 4 }}>
          {error?.message ||
            'The engine reports this surface as unimplemented. Nothing is shown rather than estimated.'}
        </div>
      </div>
    </div>
  );
}

export const Notice = ({ tone = '', icon: IconCmp = Icon.Info, children }) => (
  <div className={`notice ${tone}`}>
    <span className="ni"><IconCmp size={15} /></span>
    <div>{children}</div>
  </div>
);

/* ── Controls ── */

export function StarButton({ active, onClick, label = 'Watch' }) {
  return (
    <button className="star" data-on={active} onClick={onClick}
      aria-pressed={active} title={active ? 'Remove from watchlist' : label}>
      <Icon.Star size={16} filled={active} />
    </button>
  );
}

export function Segmented({ options, value, onChange, size }) {
  return (
    <div className="league-switch" role="group">
      {options.map((o) => (
        <button key={o.value} aria-pressed={value === o.value}
          style={size === 'sm' ? { padding: '3px 10px', fontSize: 11 } : undefined}
          onClick={() => onChange(o.value)}>
          {o.label}
        </button>
      ))}
    </div>
  );
}

/** Hover card for the tendency heatmap and anywhere else a cell needs a footnote. */
export function Tip({ label, children }) {
  const [open, setOpen] = useState(false);
  const ref = useRef(null);
  return (
    <span ref={ref} style={{ position: 'relative', display: 'inline-flex' }}
      onMouseEnter={() => setOpen(true)} onMouseLeave={() => setOpen(false)}>
      {children}
      {open && (
        <span style={{
          position: 'absolute', bottom: 'calc(100% + 6px)', left: '50%',
          transform: 'translateX(-50%)', zIndex: 30, whiteSpace: 'nowrap',
          padding: '5px 9px', borderRadius: 'var(--r-sm)', fontSize: 11,
          background: 'var(--bg-raised)', border: '1px solid var(--border-loud)',
          boxShadow: 'var(--shadow-md)', color: 'var(--text-secondary)', pointerEvents: 'none',
        }}>{label}</span>
      )}
    </span>
  );
}
