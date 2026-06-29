import React, { useState, useEffect } from 'react';
import { Card, SectionLabel, RecommendationBadge, LoadingState, EmptyState } from '../components/shared';
import { MOCK_HISTORY } from '../lib/mockResponses';

const RESULT_STYLE = {
  win:  { label: 'Win',     color: '#10b981' },
  loss: { label: 'Loss',    color: '#ef4444' },
  null: { label: 'Pending', color: 'var(--text-muted)' },
};

export default function HistoryMode() {
  const [history, setHistory] = useState([]);
  const [loading, setLoading] = useState(true);
  const [leagueFilter, setLeagueFilter] = useState('all');
  const [recFilter, setRecFilter] = useState('all');

  useEffect(() => {
    const t = setTimeout(() => { setHistory(MOCK_HISTORY); setLoading(false); }, 600);
    return () => clearTimeout(t);
  }, []);

  const filtered = history.filter(h => {
    if (leagueFilter !== 'all' && h.league !== leagueFilter) return false;
    if (recFilter === 'bet' && !h.recommendation.includes('Playable') && !h.recommendation.includes('Strong')) return false;
    if (recFilter === 'nobets' && h.recommendation.includes('Playable')) return false;
    return true;
  });

  const FilterBtn = ({ value, current, onChange, children }) => (
    <button onClick={() => onChange(value)}
      className="px-3 py-1.5 rounded-lg text-xs font-semibold transition-colors"
      style={{
        background: current === value ? '#2563eb' : 'var(--bg-input)',
        color: current === value ? 'white' : 'var(--text-secondary)',
        border: '1px solid ' + (current === value ? '#2563eb' : 'var(--border)'),
      }}>
      {children}
    </button>
  );

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      <Card className="p-4">
        <div className="flex flex-wrap gap-4 items-center">
          <div>
            <div className="text-xs mb-1.5" style={{ color: 'var(--text-muted)' }}>League</div>
            <div className="flex gap-1">
              {['all', 'NFL', 'NCAAF'].map(l => <FilterBtn key={l} value={l} current={leagueFilter} onChange={setLeagueFilter}>{l === 'all' ? 'All' : l}</FilterBtn>)}
            </div>
          </div>
          <div>
            <div className="text-xs mb-1.5" style={{ color: 'var(--text-muted)' }}>Recommendation</div>
            <div className="flex gap-1">
              {[{ id: 'all', label: 'All' }, { id: 'bet', label: 'Playable' }, { id: 'nobets', label: 'No Bet' }].map(r => (
                <FilterBtn key={r.id} value={r.id} current={recFilter} onChange={setRecFilter}>{r.label}</FilterBtn>
              ))}
            </div>
          </div>
        </div>
      </Card>

      {loading && <LoadingState lines={['Loading SGP history…']} />}
      {!loading && filtered.length === 0 && <EmptyState title="No SGPs match these filters" subtitle="Try a different filter." />}
      {!loading && filtered.map(h => <HistoryCard key={h.id} item={h} />)}
    </div>
  );
}

function HistoryCard({ item }) {
  const rs = RESULT_STYLE[item.result] || RESULT_STYLE.null;
  return (
    <Card className="p-5">
      <div className="flex items-start justify-between mb-3">
        <div>
          <div className="text-xs mb-0.5" style={{ color: 'var(--text-muted)' }}>{item.date} · {item.league} · {item.sportsbook}</div>
          <div className="text-base font-bold" style={{ color: 'var(--text-primary)' }}>{item.game}</div>
        </div>
        <div className="text-right shrink-0 ml-4">
          <div className="text-sm font-bold" style={{ color: rs.color }}>{rs.label}</div>
          <div className="text-xs mt-0.5" style={{ color: 'var(--text-muted)' }}>{item.grade}</div>
        </div>
      </div>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 4, marginBottom: 10 }}>
        {item.legs.map((leg, i) => (
          <div key={i} className="text-sm flex items-center gap-1.5" style={{ color: 'var(--text-secondary)' }}>
            <span style={{ color: 'var(--text-muted)', fontSize: 10 }}>›</span>{leg}
          </div>
        ))}
      </div>
      <div className="flex items-center gap-2 flex-wrap mb-3">
        <RecommendationBadge recommendation={item.recommendation.includes('Playable') ? 'Playable small' : item.recommendation.includes('No bet') ? 'No bet at this price' : 'Lean'} />
        <span className="text-xs px-2 py-0.5 rounded-full" style={{ background: 'var(--bg-subtle)', color: 'var(--text-muted)', border: '1px solid var(--border)' }}>{item.script_type}</span>
      </div>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 8 }}>
        {[
          { label: 'Book Price', value: item.book_price },
          { label: 'Fair Price', value: item.fair_price },
          { label: 'Min. Playable', value: item.min_playable_price, accent: true },
        ].map(row => (
          <div key={row.label} className="rounded-lg p-2" style={{ background: 'var(--bg-subtle)' }}>
            <div className="text-xs mb-0.5" style={{ color: 'var(--text-muted)' }}>{row.label}</div>
            <div className="text-xs font-semibold" style={{ color: row.accent ? '#3b82f6' : 'var(--text-secondary)' }}>{row.value}</div>
          </div>
        ))}
      </div>
    </Card>
  );
}
