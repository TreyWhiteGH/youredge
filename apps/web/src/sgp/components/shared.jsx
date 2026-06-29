import React from 'react';
import { RECOMMENDATION_CONFIG, CORRELATION_CONFIG } from '../lib/types';

// ── Semantic color helpers via CSS vars ──────────────────────────────
// All colors use CSS variables so light/dark mode work automatically.

export function RecommendationBadge({ recommendation }) {
  const cfg = RECOMMENDATION_CONFIG[recommendation] || RECOMMENDATION_CONFIG['Lean'];
  return (
    <span className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold border ${cfg.bg} ${cfg.color}`}>
      <span className={`w-1.5 h-1.5 rounded-full ${cfg.dot}`} />
      {recommendation}
    </span>
  );
}

export function CorrelationBadge({ type }) {
  const cfg = CORRELATION_CONFIG[type] || { color: 'text-slate-400', bg: 'bg-slate-400/10' };
  return (
    <span className={`inline-flex items-center px-2.5 py-1 rounded-full text-xs font-medium ${cfg.bg} ${cfg.color}`}>
      {type}
    </span>
  );
}

export function RiskBadge({ level }) {
  const colors = {
    Low: 'text-emerald-600 bg-emerald-500/10',
    Medium: 'text-yellow-600 bg-yellow-500/10',
    'Medium-High': 'text-orange-600 bg-orange-500/10',
    High: 'text-red-600 bg-red-500/10',
    'Entertainment Only': 'text-slate-500 bg-slate-500/10',
  };
  return (
    <span className={`inline-flex items-center px-2.5 py-1 rounded-full text-xs font-medium ${colors[level] || colors['Medium']}`}>
      {level}
    </span>
  );
}

export function GradeBadge({ grade }) {
  const isA = grade?.startsWith('A');
  const isB = grade?.startsWith('B');
  return (
    <span className={`text-2xl font-black ${isA ? 'text-emerald-500' : isB ? 'text-blue-500' : 'text-yellow-500'}`}>
      {grade}
    </span>
  );
}

export function ScoreBar({ label, value, max = 100 }) {
  const pct = Math.round((value / max) * 100);
  const color = pct >= 75 ? 'bg-emerald-500' : pct >= 55 ? 'bg-blue-500' : pct >= 40 ? 'bg-yellow-500' : 'bg-red-500';
  return (
    <div>
      <div className="flex justify-between text-xs mb-1">
        <span style={{ color: 'var(--text-muted)' }}>{label}</span>
        <span style={{ color: 'var(--text-primary)' }} className="font-semibold">
          {value}<span style={{ color: 'var(--text-muted)' }}>/100</span>
        </span>
      </div>
      <div className="h-1.5 rounded-full overflow-hidden" style={{ background: 'var(--border)' }}>
        <div className={`h-full rounded-full transition-all duration-700 ${color}`} style={{ width: `${pct}%` }} />
      </div>
    </div>
  );
}

export function OddsFreshnessBadge({ updatedAgo, sportsbook, stale }) {
  return (
    <div className="flex items-center gap-1.5 text-xs" style={{ color: stale ? '#f59e0b' : 'var(--text-muted)' }}>
      <span className={`w-1.5 h-1.5 rounded-full ${stale ? 'bg-yellow-400' : 'bg-emerald-400'}`} />
      {stale ? 'Odds may be stale · ' : ''}{sportsbook} · Updated {updatedAgo}
    </div>
  );
}

export function LoadingState({ lines = [] }) {
  const defaultLines = [
    'Analyzing game scripts…',
    'Fetching odds…',
    'Scoring candidates…',
    'Testing correlation…',
    'Checking price…',
  ];
  const display = lines.length ? lines : defaultLines;
  return (
    <div className="flex flex-col items-center justify-center py-16 gap-4">
      <div className="relative w-12 h-12">
        <div className="absolute inset-0 rounded-full border-2 border-blue-500/20" />
        <div className="absolute inset-0 rounded-full border-2 border-t-blue-500 animate-spin" />
      </div>
      <div className="text-center space-y-1">
        {display.map((line, i) => (
          <p key={i} className="text-sm animate-pulse" style={{ color: 'var(--text-muted)', animationDelay: `${i * 0.15}s` }}>{line}</p>
        ))}
      </div>
    </div>
  );
}

export function ErrorState({ message, onRetry }) {
  return (
    <div className="flex flex-col items-center justify-center py-12 gap-3">
      <div className="w-10 h-10 rounded-full bg-red-500/10 flex items-center justify-center text-red-500 text-xl font-bold">!</div>
      <p className="text-sm" style={{ color: 'var(--text-secondary)' }}>{message}</p>
      {onRetry && (
        <button onClick={onRetry} className="text-xs text-blue-500 hover:underline underline-offset-2">Try again</button>
      )}
    </div>
  );
}

export function EmptyState({ title, subtitle }) {
  return (
    <div className="flex flex-col items-center justify-center py-12 gap-2 text-center">
      <div className="text-3xl opacity-20">—</div>
      <p className="text-sm font-medium" style={{ color: 'var(--text-secondary)' }}>{title}</p>
      {subtitle && <p className="text-xs max-w-xs" style={{ color: 'var(--text-muted)' }}>{subtitle}</p>}
    </div>
  );
}

export function SectionLabel({ children }) {
  return (
    <div className="text-xs font-semibold uppercase tracking-widest mb-3" style={{ color: 'var(--text-muted)' }}>{children}</div>
  );
}

export function Divider() {
  return <div className="my-4" style={{ borderTop: '1px solid var(--border)' }} />;
}

export function Card({ children, className = '' }) {
  return (
    <div className={`rounded-xl ${className}`} style={{ background: 'var(--bg-surface)', border: '1px solid var(--border)' }}>
      {children}
    </div>
  );
}

export function PrimaryButton({ onClick, disabled, children, className = '' }) {
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      className={`px-4 py-2.5 bg-blue-600 hover:bg-blue-500 disabled:opacity-40 disabled:cursor-not-allowed text-white text-sm font-semibold rounded-lg transition-colors ${className}`}
    >
      {children}
    </button>
  );
}

export function GhostButton({ onClick, children, className = '' }) {
  return (
    <button
      onClick={onClick}
      className={`px-3 py-2 text-sm font-medium rounded-lg transition-colors ${className}`}
      style={{ border: '1px solid var(--border)', color: 'var(--text-secondary)' }}
      onMouseEnter={e => { e.currentTarget.style.color = 'var(--text-primary)'; e.currentTarget.style.borderColor = 'var(--text-muted)'; }}
      onMouseLeave={e => { e.currentTarget.style.color = 'var(--text-secondary)'; e.currentTarget.style.borderColor = 'var(--border)'; }}
    >
      {children}
    </button>
  );
}

export function ManualSGPPriceInput({ value, onChange }) {
  return (
    <div className="rounded-xl p-4" style={{ background: 'rgba(245,158,11,0.05)', border: '1px solid rgba(245,158,11,0.2)' }}>
      <div className="text-xs font-semibold text-yellow-500 mb-1">SGP Price Required</div>
      <p className="text-xs mb-3" style={{ color: 'var(--text-muted)' }}>
        Single-leg odds were fetched, but the combined SGP price isn't available via API.
        Enter the price shown in your sportsbook bet slip.
      </p>
      <div className="flex items-center gap-2">
        <div className="relative">
          <span className="absolute left-3 top-1/2 -translate-y-1/2 text-sm font-bold" style={{ color: 'var(--text-muted)' }}>+</span>
          <input
            type="number"
            placeholder="e.g. 390"
            value={value}
            onChange={e => onChange(e.target.value)}
            className="pl-7 pr-3 py-2 rounded-lg text-sm w-36 focus:outline-none"
            style={{ background: 'var(--bg-input)', border: '1px solid var(--border)', color: 'var(--text-primary)' }}
          />
        </div>
        <span className="text-xs" style={{ color: 'var(--text-muted)' }}>Enter to calculate edge</span>
      </div>
    </div>
  );
}

export function PriceRow({ label, value, accent }) {
  return (
    <div className="flex justify-between items-center py-2.5" style={{ borderBottom: '1px solid var(--border)' }}>
      <span className="text-sm" style={{ color: 'var(--text-muted)' }}>{label}</span>
      <span className={`text-sm font-bold ${accent ? 'text-blue-500' : ''}`} style={!accent ? { color: 'var(--text-primary)' } : {}}>{value}</span>
    </div>
  );
}

export function LegPill({ selection, market, modelProb, odds }) {
  return (
    <div className="flex items-start justify-between p-3 rounded-lg" style={{ background: 'var(--bg-subtle)', border: '1px solid var(--border)' }}>
      <div>
        <div className="text-sm font-semibold" style={{ color: 'var(--text-primary)' }}>{selection}</div>
        <div className="text-xs mt-0.5" style={{ color: 'var(--text-muted)' }}>{market}</div>
      </div>
      <div className="text-right shrink-0 ml-4">
        {modelProb !== undefined && (
          <div className="text-xs font-semibold text-blue-500">{Math.round(modelProb * 100)}%</div>
        )}
        {odds !== undefined && (
          <div className="text-xs" style={{ color: 'var(--text-muted)' }}>{odds > 0 ? `+${odds}` : odds}</div>
        )}
      </div>
    </div>
  );
}

export function NoBetCard({ needed, current, bestLean }) {
  return (
    <div className="rounded-xl p-5" style={{ background: 'var(--bg-subtle)', border: '1px solid var(--border)' }}>
      <div className="flex items-center gap-2 mb-3">
        <span className="w-2 h-2 rounded-full" style={{ background: 'var(--text-muted)' }} />
        <span className="text-sm font-bold" style={{ color: 'var(--text-secondary)' }}>No Playable SGP</span>
      </div>
      <p className="text-xs mb-4" style={{ color: 'var(--text-muted)' }}>
        The best scripts are either priced too short or the legs don't fit cleanly enough.
      </p>
      {bestLean && (
        <div className="mb-3">
          <div className="text-xs mb-1" style={{ color: 'var(--text-muted)' }}>Best Lean</div>
          <div className="text-sm font-medium" style={{ color: 'var(--text-secondary)' }}>{bestLean}</div>
        </div>
      )}
      {needed && current && (
        <div className="grid grid-cols-2 gap-3">
          <div className="rounded-lg p-3" style={{ background: 'var(--bg-input)' }}>
            <div className="text-xs mb-1" style={{ color: 'var(--text-muted)' }}>Needed Price</div>
            <div className="text-sm font-bold" style={{ color: 'var(--text-secondary)' }}>{needed} or better</div>
          </div>
          <div className="rounded-lg p-3" style={{ background: 'var(--bg-input)' }}>
            <div className="text-xs mb-1" style={{ color: 'var(--text-muted)' }}>Current Price</div>
            <div className="text-sm font-bold text-red-500">{current}</div>
          </div>
        </div>
      )}
      <div className="mt-3 text-xs font-semibold" style={{ color: 'var(--text-muted)' }}>No bet at this price.</div>
    </div>
  );
}

export function ResponsibleGamblingFooter() {
  return (
    <div className="pt-4 mt-6" style={{ borderTop: '1px solid var(--border)' }}>
      <p className="text-xs text-center leading-relaxed" style={{ color: 'var(--text-muted)' }}>
        YourEdge provides probability-based analysis, not guarantees. No bet is a valid outcome.
        Avoid chasing losses or increasing stake because of payout size.
      </p>
    </div>
  );
}
