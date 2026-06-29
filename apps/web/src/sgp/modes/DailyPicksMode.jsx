import React, { useState, useEffect } from 'react';
import { Card, SectionLabel, LoadingState, EmptyState } from '../components/shared';

const SPORTS = [
  { id: 'nfl', label: 'NFL' },
  { id: 'ncaaf', label: 'College Football' },
  { id: 'nba', label: 'NBA' },
  { id: 'ncaam', label: "Men's CBB" },
  { id: 'ncaaw', label: "Women's CBB" },
];

const MARKETS = ['All', 'Spread', 'Total', 'Moneyline', 'Player Props'];

const MOCK_PICKS = [
  { matchup: 'Ravens @ Bengals', market: 'Spread', selection: 'Ravens -6.5', odds: '-110', confidence: 0.67, edge: 0.061, grade: 'A', rationale: 'Ravens project to control possession; Bengals secondary has struggled vs. RPO sets in the last three games.', risk: 'Low', script: 'Run-first, clock control' },
  { matchup: 'Chiefs @ Broncos', market: 'Total', selection: 'Under 44.5', odds: '-108', confidence: 0.63, edge: 0.049, grade: 'B+', rationale: "Denver's defense has held opponents to 17 or fewer in 4 of their last 5 home games. Cold weather projected.", risk: 'Medium', script: 'Defensive slugfest' },
  { matchup: 'Alabama @ Georgia', market: 'Spread', selection: 'Alabama -4.5', odds: '-115', confidence: 0.61, edge: 0.038, grade: 'B', rationale: "Alabama's offensive line advantage projects 5+ yards per carry. Georgia's interior DL missing two starters.", risk: 'Medium', script: 'Ground-and-pound' },
  { matchup: 'Cowboys @ Eagles', market: 'Moneyline', selection: 'Eagles ML', odds: '-140', confidence: 0.59, edge: 0.029, grade: 'B-', rationale: "Eagles at home, Cowboys secondary allowing 265 pass yards per game on the road. Hurts targeting slot heavily.", risk: 'Low', script: 'Air-it-out, tempo' },
  { matchup: 'Celtics @ Lakers', market: 'Player Props', selection: 'Tatum Over 27.5 pts', odds: '-112', confidence: 0.62, edge: 0.044, grade: 'B+', rationale: "Lakers missing two wing defenders. Tatum has scored 28+ in 5 of 6 road games. Usage rate up 4% last month.", risk: 'Medium', script: 'Volume scorer' },
];

export default function DailyPicksMode({ league, authToken }) {
  const [sport, setSport] = useState('nfl');
  const [market, setMarket] = useState('All');
  const [minConfidence, setMinConfidence] = useState(0.55);
  const [picks, setPicks] = useState([]);
  const [loading, setLoading] = useState(true);
  const [saved, setSaved] = useState({});

  useEffect(() => {
    setLoading(true);
    const t = setTimeout(async () => {
      try {
        const res = await fetch('/api/generate-picks', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ sport, date: new Date().toISOString().slice(0, 10), markets: ['spread', 'total', 'moneyline'], min_confidence: minConfidence }),
        });
        if (res.ok) {
          const json = await res.json();
          const flat = (json.picks || []).flatMap(g =>
            (g.predictions || []).map(p => ({ matchup: g.matchup, ...p }))
          );
          setPicks(flat.length ? flat : MOCK_PICKS);
        } else {
          setPicks(MOCK_PICKS);
        }
      } catch {
        setPicks(MOCK_PICKS);
      }
      setLoading(false);
    }, 700);
    return () => clearTimeout(t);
  }, [sport, minConfidence]);

  const filtered = picks.filter(p => {
    if (market !== 'All' && p.market !== market) return false;
    if (p.confidence < minConfidence) return false;
    return true;
  });

  const handleSave = (i) => setSaved(s => ({ ...s, [i]: true }));

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>

      {/* Filter bar */}
      <Card className="p-4">
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 16, alignItems: 'flex-end' }}>
          <div>
            <div className="text-xs mb-1.5" style={{ color: 'var(--text-muted)' }}>Sport</div>
            <div style={{ display: 'flex', gap: 4 }}>
              {SPORTS.map(s => (
                <button key={s.id} onClick={() => setSport(s.id)}
                  className="px-3 py-1.5 rounded-lg text-xs font-semibold transition-colors"
                  style={{
                    background: sport === s.id ? '#2563eb' : 'var(--bg-input)',
                    color: sport === s.id ? 'white' : 'var(--text-secondary)',
                    border: `1px solid ${sport === s.id ? '#2563eb' : 'var(--border)'}`,
                  }}>
                  {s.label}
                </button>
              ))}
            </div>
          </div>

          <div>
            <div className="text-xs mb-1.5" style={{ color: 'var(--text-muted)' }}>Market</div>
            <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap' }}>
              {MARKETS.map(m => (
                <button key={m} onClick={() => setMarket(m)}
                  className="px-3 py-1.5 rounded-lg text-xs font-semibold transition-colors"
                  style={{
                    background: market === m ? '#2563eb' : 'var(--bg-input)',
                    color: market === m ? 'white' : 'var(--text-secondary)',
                    border: `1px solid ${market === m ? '#2563eb' : 'var(--border)'}`,
                  }}>
                  {m}
                </button>
              ))}
            </div>
          </div>

          <div>
            <div className="text-xs mb-1.5" style={{ color: 'var(--text-muted)' }}>
              Min. Confidence — <span style={{ color: 'var(--text-primary)', fontWeight: 700 }}>{(minConfidence * 100).toFixed(0)}%</span>
            </div>
            <input type="range" min={0.50} max={0.80} step={0.01}
              value={minConfidence} onChange={e => setMinConfidence(+e.target.value)}
              style={{ width: 140, accentColor: '#2563eb' }} />
          </div>
        </div>
      </Card>

      {/* Results */}
      {loading && <LoadingState lines={['Pulling today\'s lines…', 'Running confidence models…', 'Filtering by edge…']} />}
      {!loading && filtered.length === 0 && (
        <EmptyState title="No picks match these filters" subtitle="Try lowering confidence or broadening the market filter." />
      )}
      {!loading && filtered.map((pick, i) => (
        <PickDetailCard key={i} pick={pick} index={i} saved={saved[i]} onSave={() => handleSave(i)} />
      ))}
    </div>
  );
}

function PickDetailCard({ pick, index, saved, onSave }) {
  const conf = pick.confidence * 100;
  const edge = (pick.edge * 100).toFixed(1);
  const gradeColor = pick.grade?.startsWith('A') ? '#10b981' : pick.grade?.startsWith('B') ? '#3b82f6' : '#f59e0b';
  const confColor = conf >= 65 ? '#10b981' : conf >= 60 ? '#f59e0b' : '#3b82f6';

  return (
    <Card className="p-5">
      {/* Header row */}
      <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', marginBottom: 12 }}>
        <div>
          <div className="text-xs mb-1" style={{ color: 'var(--text-muted)' }}>#{index + 1} · {pick.matchup}</div>
          <div style={{ fontSize: 16, fontWeight: 800, color: 'var(--text-primary)', lineHeight: 1.2 }}>{pick.selection}</div>
          <div style={{ display: 'flex', gap: 8, marginTop: 4, alignItems: 'center' }}>
            <span className="text-xs font-semibold" style={{ color: 'var(--text-muted)' }}>{pick.market}</span>
            {pick.odds && (
              <span className="text-xs font-bold px-2 py-0.5 rounded-md"
                style={{ background: 'var(--bg-subtle)', color: 'var(--text-secondary)', border: '1px solid var(--border)' }}>
                {pick.odds}
              </span>
            )}
          </div>
        </div>

        <div style={{ textAlign: 'right', flexShrink: 0, marginLeft: 16 }}>
          <div style={{ fontSize: 22, fontWeight: 900, color: confColor, lineHeight: 1 }}>{conf.toFixed(0)}%</div>
          <div className="text-xs" style={{ color: 'var(--text-muted)' }}>confidence</div>
          {pick.grade && (
            <div style={{ marginTop: 4, fontSize: 12, fontWeight: 700, color: gradeColor }}>{pick.grade}</div>
          )}
        </div>
      </div>

      {/* Script tag */}
      {pick.script && (
        <div className="text-xs font-semibold px-2 py-1 rounded-md inline-block mb-3"
          style={{ background: 'rgba(37,99,235,0.1)', color: '#3b82f6', border: '1px solid rgba(37,99,235,0.25)' }}>
          Script: {pick.script}
        </div>
      )}

      {/* Rationale */}
      <p className="text-sm leading-relaxed mb-4" style={{ color: 'var(--text-secondary)', margin: '0 0 16px' }}>{pick.rationale}</p>

      {/* Stats row */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 8, marginBottom: 14 }}>
        {[
          { label: 'Edge', value: `+${edge}%`, color: '#10b981' },
          { label: 'Risk', value: pick.risk || 'Medium', color: pick.risk === 'Low' ? '#10b981' : pick.risk === 'High' ? '#ef4444' : '#f59e0b' },
          { label: 'Confidence', value: `${conf.toFixed(0)}%`, color: confColor },
        ].map(stat => (
          <div key={stat.label} className="rounded-lg p-2.5" style={{ background: 'var(--bg-subtle)', border: '1px solid var(--border)' }}>
            <div className="text-xs mb-0.5" style={{ color: 'var(--text-muted)' }}>{stat.label}</div>
            <div className="text-sm font-bold" style={{ color: stat.color }}>{stat.value}</div>
          </div>
        ))}
      </div>

      {/* Actions */}
      <div style={{ display: 'flex', gap: 8 }}>
        <button onClick={onSave}
          className="px-4 py-2 rounded-lg text-xs font-semibold transition-colors"
          style={{
            background: saved ? 'rgba(16,185,129,0.1)' : 'var(--bg-input)',
            color: saved ? '#10b981' : 'var(--text-secondary)',
            border: `1px solid ${saved ? 'rgba(16,185,129,0.35)' : 'var(--border)'}`,
          }}>
          {saved ? '✓ Saved' : 'Save Pick'}
        </button>
        <button onClick={() => { navigator.clipboard.writeText(`${pick.selection} ${pick.odds || ''} — ${pick.matchup}`).catch(() => {}); }}
          className="px-4 py-2 rounded-lg text-xs font-semibold transition-colors"
          style={{ background: 'var(--bg-input)', color: 'var(--text-secondary)', border: '1px solid var(--border)' }}>
          Copy
        </button>
      </div>
    </Card>
  );
}
