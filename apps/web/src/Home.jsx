import React, { useState, useEffect } from 'react';
import { MOCK_GAMES } from './sgp/lib/types';

const FEATURED_GAMES = MOCK_GAMES.slice(0, 3);

const MOCK_TOP_PICKS = [
  { matchup: 'Ravens @ Bengals', market: 'Spread', selection: 'Ravens -6.5', confidence: 0.67, edge: 0.061, rationale: 'Ravens project to control possession; Bengals secondary struggles vs. RPO sets.' },
  { matchup: 'Chiefs @ Broncos', market: 'Total', selection: 'Under 44.5', confidence: 0.63, edge: 0.049, rationale: 'Denver\'s defense has held opponents to 17 or fewer in 4 of last 5 home games.' },
  { matchup: 'Alabama @ Georgia', market: 'Spread', selection: 'Alabama -4.5', confidence: 0.61, edge: 0.038, rationale: 'Alabama\'s offensive line advantage projects 5+ yards per carry opportunity.' },
];

export default function Home({ onNavigate, authToken }) {
  const [topPicks, setTopPicks] = useState([]);
  const [loadingPicks, setLoadingPicks] = useState(true);
  const [myPicks, setMyPicks] = useState([]);
  const [loadingMyPicks, setLoadingMyPicks] = useState(true);

  // Load top picks
  useEffect(() => {
    const load = async () => {
      setLoadingPicks(true);
      try {
        const res = await fetch('/api/generate-picks', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ sport: 'nfl', date: new Date().toISOString().slice(0, 10), markets: ['spread', 'total'], min_confidence: 0.60, min_edge: 0.03 }),
        });
        if (res.ok) {
          const json = await res.json();
          const picks = (json.picks || []).flatMap(g =>
            (g.predictions || []).map(p => ({ matchup: g.matchup, ...p }))
          ).slice(0, 3);
          setTopPicks(picks.length ? picks : MOCK_TOP_PICKS);
        } else {
          setTopPicks(MOCK_TOP_PICKS);
        }
      } catch {
        setTopPicks(MOCK_TOP_PICKS);
      } finally {
        setLoadingPicks(false);
      }
    };
    load();
  }, []);

  // Load my picks
  useEffect(() => {
    const load = async () => {
      setLoadingMyPicks(true);
      try {
        const params = new URLSearchParams({ sport: 'nfl', date: new Date().toISOString().slice(0, 10) });
        if (!authToken) params.set('userId', 'demo');
        const headers = authToken ? { Authorization: `Bearer ${authToken}` } : {};
        const res = await fetch(`/api/picks?${params}`, { headers });
        if (res.ok) {
          const json = await res.json();
          setMyPicks((json.picks || []).slice(0, 3));
        }
      } catch {}
      finally { setLoadingMyPicks(false); }
    };
    load();
  }, [authToken]);

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 24 }}>

      {/* ── Top Picks ── */}
      <section>
        <SectionHeader title="Top Picks Today" cta="View All Picks" onCta={() => onNavigate('getpicks')} />
        {loadingPicks ? (
          <SkeletonCards />
        ) : (
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))', gap: 12 }}>
            {topPicks.map((pick, i) => (
              <PickCard key={i} pick={pick} rank={i + 1} onNavigate={onNavigate} />
            ))}
          </div>
        )}
      </section>

      {/* ── Featured Games ── */}
      <section>
        <SectionHeader title="Featured Games" cta="Full Scoreboard" onCta={() => onNavigate('scoreboard')} />
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))', gap: 12 }}>
          {FEATURED_GAMES.map(game => (
            <FeaturedGameCard key={game.id} game={game} onNavigate={onNavigate} />
          ))}
        </div>
      </section>

      {/* ── My Picks ── */}
      <section>
        <SectionHeader title="My Picks" cta="View Portfolio" onCta={() => onNavigate('picks')} />
        {loadingMyPicks ? (
          <SkeletonCards count={2} />
        ) : myPicks.length === 0 ? (
          <EmptyMyPicks onNavigate={onNavigate} />
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
            {myPicks.map((p, i) => <MyPickRow key={i} pick={p} />)}
          </div>
        )}
      </section>

      {/* ── Quick actions ── */}
      <section>
        <div className="text-xs font-semibold uppercase tracking-widest mb-3" style={{ color: 'var(--text-muted)' }}>Quick Actions</div>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(200px, 1fr))', gap: 10 }}>
          {[
            { label: '⚡ Build an SGP', sub: 'Same-game parlay intelligence', tab: 'betlab' },
            { label: '🎯 Get AI Picks', sub: 'Best single bets for today', tab: 'betlab' },
            { label: '📊 Scoreboard', sub: 'Live scores across all leagues', tab: 'scoreboard' },
            { label: '💼 My Portfolio', sub: 'Track your active picks', tab: 'picks' },
          ].map(action => (
            <QuickActionCard key={action.tab + action.label} {...action} onNavigate={onNavigate} />
          ))}
        </div>
      </section>
    </div>
  );
}

function SectionHeader({ title, cta, onCta }) {
  return (
    <div className="flex items-center justify-between mb-3">
      <h2 style={{ margin: 0, fontSize: 16, fontWeight: 700, color: 'var(--text-primary)' }}>{title}</h2>
      <button onClick={onCta}
        className="text-xs font-semibold text-blue-500 hover:text-blue-400 transition-colors flex items-center gap-1">
        {cta} →
      </button>
    </div>
  );
}

function PickCard({ pick, rank, onNavigate }) {
  const conf = pick.confidence * 100;
  const edge = pick.edge * 100;
  const color = conf > 65 ? '#10b981' : conf > 58 ? '#f59e0b' : '#3b82f6';
  return (
    <div className="rounded-xl p-4 transition-all cursor-pointer"
      style={{ background: 'var(--bg-surface)', border: '1px solid var(--border)', borderLeft: `3px solid ${color}` }}
      onClick={() => onNavigate('getpicks')}>
      <div className="flex items-start justify-between mb-2">
        <div>
          <div className="text-xs mb-0.5" style={{ color: 'var(--text-muted)' }}>#{rank} · {pick.matchup}</div>
          <div className="text-sm font-bold" style={{ color: 'var(--text-primary)' }}>
            {pick.selection || `${pick.market} ${pick.line}`}
          </div>
          <div className="text-xs mt-0.5" style={{ color: 'var(--text-muted)' }}>{pick.market}</div>
        </div>
        <div style={{ textAlign: 'right', flexShrink: 0, marginLeft: 12 }}>
          <div className="text-sm font-black" style={{ color }}>{conf.toFixed(0)}%</div>
          <div className="text-xs" style={{ color: 'var(--text-muted)' }}>conf</div>
        </div>
      </div>
      <p className="text-xs leading-relaxed" style={{ color: 'var(--text-muted)', margin: 0 }}>{pick.rationale}</p>
      <div className="flex items-center justify-between mt-3">
        <span className="text-xs font-semibold" style={{ color: '#10b981' }}>+{edge.toFixed(1)}% edge</span>
        <span className="text-xs" style={{ color: 'var(--text-muted)' }}>View details →</span>
      </div>
    </div>
  );
}

function FeaturedGameCard({ game, onNavigate }) {
  return (
    <div className="rounded-xl p-4 cursor-pointer transition-all"
      style={{ background: 'var(--bg-surface)', border: '1px solid var(--border)' }}
      onClick={() => onNavigate('scoreboard')}
      onMouseEnter={e => e.currentTarget.style.borderColor = '#3b82f6'}
      onMouseLeave={e => e.currentTarget.style.borderColor = 'var(--border)'}>
      <div className="flex items-center justify-between mb-3">
        <div className="text-sm font-bold" style={{ color: 'var(--text-primary)' }}>
          {game.away.name} @ {game.home.name}
        </div>
        <span className="text-xs" style={{ color: 'var(--text-muted)' }}>{game.league}</span>
      </div>
      <div className="text-xs mb-3" style={{ color: 'var(--text-muted)' }}>{game.date}</div>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 6 }}>
        {[
          { label: 'Spread', val: `${game.spread.favorite} ${game.spread.line > 0 ? '+' : ''}${game.spread.line}` },
          { label: 'Total', val: game.total },
          { label: 'ML', val: `${game.moneyline.away > 0 ? '+' : ''}${game.moneyline.away}` },
        ].map(item => (
          <div key={item.label} className="rounded-lg p-2" style={{ background: 'var(--bg-subtle)' }}>
            <div className="text-xs mb-0.5" style={{ color: 'var(--text-muted)' }}>{item.label}</div>
            <div className="text-xs font-semibold" style={{ color: 'var(--text-primary)' }}>{item.val}</div>
          </div>
        ))}
      </div>
      <div className="flex items-center justify-between mt-3">
        <span className="text-xs flex items-center gap-1" style={{ color: game.stale ? '#f59e0b' : '#10b981' }}>
          <span className="w-1.5 h-1.5 rounded-full inline-block" style={{ background: game.stale ? '#f59e0b' : '#10b981' }} />
          {game.sportsbook} · {game.oddsUpdated}
        </span>
        <span className="text-xs text-blue-500">Build SGP →</span>
      </div>
    </div>
  );
}

function MyPickRow({ pick }) {
  const statusColor = pick.status === 'won' ? '#10b981' : pick.status === 'lost' ? '#ef4444' : 'var(--text-muted)';
  return (
    <div className="flex items-center justify-between px-4 py-3 rounded-xl"
      style={{ background: 'var(--bg-surface)', border: '1px solid var(--border)', borderLeft: '3px solid #3b82f6' }}>
      <div>
        <div className="text-sm font-semibold" style={{ color: 'var(--text-primary)' }}>{pick.matchup}</div>
        <div className="text-xs mt-0.5" style={{ color: 'var(--text-muted)' }}>{pick.bet_type || pick.home} vs {pick.away}</div>
      </div>
      <div className="text-xs font-semibold" style={{ color: statusColor }}>{pick.status || 'Pending'}</div>
    </div>
  );
}

function EmptyMyPicks({ onNavigate }) {
  return (
    <div className="rounded-xl p-6 text-center" style={{ background: 'var(--bg-surface)', border: '1px solid var(--border)', borderStyle: 'dashed' }}>
      <div className="text-2xl mb-2">💼</div>
      <p className="text-sm font-medium mb-1" style={{ color: 'var(--text-secondary)' }}>No picks saved yet</p>
      <p className="text-xs mb-4" style={{ color: 'var(--text-muted)' }}>Get picks or build an SGP and save your best bets.</p>
      <button onClick={() => onNavigate('betlab')}
        className="px-4 py-2 bg-blue-600 hover:bg-blue-500 text-white text-sm font-semibold rounded-lg transition-colors">
        Start in Bet Lab
      </button>
    </div>
  );
}

function QuickActionCard({ label, sub, tab, onNavigate }) {
  const [hover, setHover] = useState(false);
  return (
    <button onClick={() => onNavigate(tab)}
      onMouseEnter={() => setHover(true)}
      onMouseLeave={() => setHover(false)}
      style={{
        textAlign: 'left', padding: '14px 16px',
        background: 'var(--bg-surface)',
        border: `1px solid ${hover ? '#3b82f6' : 'var(--border)'}`,
        borderRadius: 12, cursor: 'pointer', transition: 'border-color 0.15s',
      }}>
      <div className="text-sm font-bold mb-1" style={{ color: 'var(--text-primary)' }}>{label}</div>
      <div className="text-xs" style={{ color: 'var(--text-muted)' }}>{sub}</div>
    </button>
  );
}

function SkeletonCards({ count = 3 }) {
  return (
    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))', gap: 12 }}>
      {Array.from({ length: count }).map((_, i) => (
        <div key={i} className="rounded-xl p-4 animate-pulse" style={{ background: 'var(--bg-surface)', border: '1px solid var(--border)', height: 120 }} />
      ))}
    </div>
  );
}
