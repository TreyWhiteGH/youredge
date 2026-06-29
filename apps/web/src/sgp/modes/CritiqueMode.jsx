import React, { useState } from 'react';
import GameSelector from '../components/GameSelector';
import { LeagueSelector, SportsbookSelector } from '../components/GlobalControls';
import { LoadingState, ErrorState, Card, PrimaryButton, SectionLabel, Divider, GradeBadge, RecommendationBadge } from '../components/shared';
import { MOCK_LEGS } from '../lib/types';
import { MOCK_CRITIQUE_RESPONSE, mockDelay } from '../lib/mockResponses';

const VERDICT_STYLE = {
  keep:   { label: 'Keep',   color: '#10b981', bg: 'rgba(16,185,129,0.08)',  border: 'rgba(16,185,129,0.25)' },
  maybe:  { label: 'Maybe',  color: '#f59e0b', bg: 'rgba(245,158,11,0.08)',  border: 'rgba(245,158,11,0.25)' },
  remove: { label: 'Remove', color: '#ef4444', bg: 'rgba(239,68,68,0.08)',   border: 'rgba(239,68,68,0.25)' },
};

export default function CritiqueMode({ league, setLeague, sportsbook, setSportsbook }) {
  const [selectedGame, setSelectedGame] = useState(null);
  const [legs, setLegs] = useState([]);
  const [bookPrice, setBookPrice] = useState('');
  const [legSearch, setLegSearch] = useState('');
  const [showLegList, setShowLegList] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [result, setResult] = useState(null);

  const available = selectedGame ? (MOCK_LEGS[selectedGame.id] || []) : [];
  const filtered = available.filter(l => l.label.toLowerCase().includes(legSearch.toLowerCase()) && !legs.find(el => el.id === l.id));

  const handleCritique = async () => {
    if (!selectedGame || legs.length < 2) return;
    setLoading(true); setError(''); setResult(null);
    try { await mockDelay(1600); setResult(MOCK_CRITIQUE_RESPONSE); }
    catch (e) { setError(e.message); }
    finally { setLoading(false); }
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      <Card className="p-5" style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
        <SectionLabel>Configure</SectionLabel>
        <div className="flex flex-wrap gap-3 items-center">
          <div><div className="text-xs mb-1.5" style={{ color: 'var(--text-muted)' }}>League</div><LeagueSelector value={league} onChange={setLeague} /></div>
          <div><div className="text-xs mb-1.5" style={{ color: 'var(--text-muted)' }}>Sportsbook</div><SportsbookSelector value={sportsbook} onChange={setSportsbook} /></div>
        </div>
        <div>
          <div className="text-xs mb-1.5" style={{ color: 'var(--text-muted)' }}>Game</div>
          <GameSelector league={league} sportsbook={sportsbook} selectedGame={selectedGame}
            onSelect={g => { setSelectedGame(g); setLegs([]); setResult(null); }} />
        </div>

        {selectedGame && (
          <div className="relative">
            <div className="text-xs mb-1.5" style={{ color: 'var(--text-muted)' }}>Add Legs <span style={{ opacity: 0.5 }}>(min 2)</span></div>
            <input value={legSearch}
              onChange={e => { setLegSearch(e.target.value); setShowLegList(true); }}
              onFocus={() => setShowLegList(true)}
              placeholder="Search for a leg…"
              className="w-full px-4 py-2.5 rounded-xl text-sm focus:outline-none"
              style={{ background: 'var(--bg-input)', border: '1px solid var(--border)', color: 'var(--text-primary)' }}
            />
            {showLegList && filtered.length > 0 && (
              <div className="absolute z-50 top-full mt-1 w-full rounded-xl shadow-xl max-h-48 overflow-y-auto"
                style={{ background: 'var(--bg-surface)', border: '1px solid var(--border)' }}>
                {filtered.map(leg => (
                  <button key={leg.id} onClick={() => { setLegs([...legs, leg]); setLegSearch(''); setShowLegList(false); setResult(null); }}
                    className="w-full text-left px-4 py-2.5 text-sm transition-colors"
                    style={{ borderBottom: '1px solid var(--border)', color: 'var(--text-primary)', background: 'transparent' }}
                    onMouseEnter={e => e.currentTarget.style.background = 'var(--bg-subtle)'}
                    onMouseLeave={e => e.currentTarget.style.background = 'transparent'}>
                    <span className="font-medium">{leg.label}</span>
                    <span className="ml-2 text-xs" style={{ color: 'var(--text-muted)' }}>{leg.market} · {leg.odds > 0 ? '+' : ''}{leg.odds}</span>
                  </button>
                ))}
              </div>
            )}
          </div>
        )}

        {legs.length > 0 && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
            {legs.map((leg, i) => (
              <div key={leg.id} className="flex items-center justify-between px-3 py-2.5 rounded-lg"
                style={{ background: 'var(--bg-subtle)', border: '1px solid var(--border)' }}>
                <div>
                  <div className="text-sm font-medium" style={{ color: 'var(--text-primary)' }}>Leg {i + 1}: {leg.label}</div>
                  <div className="text-xs" style={{ color: 'var(--text-muted)' }}>{leg.market} · {leg.odds > 0 ? '+' : ''}{leg.odds}</div>
                </div>
                <button onClick={() => setLegs(legs.filter(l => l.id !== leg.id))} className="text-xs transition-colors"
                  style={{ color: 'var(--text-muted)' }}
                  onMouseEnter={e => e.currentTarget.style.color = '#ef4444'}
                  onMouseLeave={e => e.currentTarget.style.color = 'var(--text-muted)'}>✕</button>
              </div>
            ))}
          </div>
        )}

        <div>
          <div className="text-xs mb-1.5" style={{ color: 'var(--text-muted)' }}>SGP Price <span style={{ opacity: 0.5 }}>(optional)</span></div>
          <div className="relative w-48">
            <span className="absolute left-3 top-1/2 -translate-y-1/2 text-sm font-bold" style={{ color: 'var(--text-muted)' }}>+</span>
            <input type="number" placeholder="e.g. 525" value={bookPrice}
              onChange={e => setBookPrice(e.target.value)}
              className="pl-7 pr-3 py-2.5 rounded-xl text-sm w-full focus:outline-none"
              style={{ background: 'var(--bg-input)', border: '1px solid var(--border)', color: 'var(--text-primary)' }}
            />
          </div>
        </div>

        <PrimaryButton onClick={handleCritique} disabled={!selectedGame || legs.length < 2 || loading} className="w-full">
          {loading ? 'Critiquing…' : 'Critique This SGP'}
        </PrimaryButton>
      </Card>

      {loading && <LoadingState lines={['Reading your legs…', 'Detecting script conflicts…', 'Scoring correlation fit…', 'Building cleaner version…']} />}
      {error && <ErrorState message={error} />}
      {result && !loading && <CritiqueResult result={result} />}
    </div>
  );
}

function CritiqueResult({ result }) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
      <Card className="p-5">
        <div className="flex items-center justify-between mb-3">
          <div>
            <SectionLabel>Overall Grade</SectionLabel>
            <div className="flex items-center gap-3">
              <GradeBadge grade={result.overall_grade} />
              <span className="text-sm" style={{ color: 'var(--text-muted)' }}>{result.issue}</span>
            </div>
          </div>
        </div>
        <Divider />
        {result.conflicts.map((c, i) => (
          <div key={i} className="p-3 rounded-lg" style={{ background: 'rgba(239,68,68,0.05)', border: '1px solid rgba(239,68,68,0.2)' }}>
            <div className="text-xs font-semibold text-red-500 mb-1">{c.type}</div>
            <p className="text-sm" style={{ color: 'var(--text-secondary)' }}>{c.description}</p>
          </div>
        ))}
      </Card>

      <Card className="p-5">
        <SectionLabel>Leg-by-Leg Verdict</SectionLabel>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
          {result.leg_verdicts.map((lv, i) => {
            const s = VERDICT_STYLE[lv.verdict];
            return (
              <div key={i} className="flex items-start gap-3 p-3 rounded-lg"
                style={{ background: s.bg, border: `1px solid ${s.border}` }}>
                <span className="text-xs font-bold mt-0.5" style={{ color: s.color }}>{s.label}</span>
                <div>
                  <div className="text-sm font-semibold" style={{ color: 'var(--text-primary)' }}>{lv.selection}</div>
                  <p className="text-xs mt-0.5" style={{ color: 'var(--text-muted)' }}>{lv.reason}</p>
                </div>
              </div>
            );
          })}
        </div>
      </Card>

      {[
        { title: 'Cleaner Version', data: result.cleaner_version, rec: 'Playable small' },
        { title: 'Aggressive Version', data: result.aggressive_version, rec: 'Lean' },
      ].map(({ title, data, rec }) => (
        <Card key={title} className="p-5">
          <SectionLabel>{title}</SectionLabel>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8, marginBottom: 10 }}>
            {data.legs.map((leg, i) => (
              <div key={i} className="px-3 py-2 rounded-lg text-sm font-medium" style={{ background: 'var(--bg-subtle)', color: 'var(--text-primary)' }}>{leg}</div>
            ))}
          </div>
          <div className="flex items-center gap-2 mb-2">
            <span className="text-xs font-bold" style={{ color: 'var(--text-muted)' }}>{data.grade}</span>
            <RecommendationBadge recommendation={rec} />
          </div>
          <p className="text-xs" style={{ color: 'var(--text-muted)' }}>{data.recommendation}</p>
          <div className="mt-3">
            <button className="px-3 py-2 text-sm font-medium rounded-lg transition-colors"
              style={{ border: '1px solid var(--border)', color: 'var(--text-secondary)', background: 'transparent' }}>
              Use {title}
            </button>
          </div>
        </Card>
      ))}

      <div className="rounded-xl p-4" style={{ background: 'var(--bg-subtle)', border: '1px solid var(--border)' }}>
        <div className="text-sm font-bold" style={{ color: 'var(--text-muted)' }}>{result.overall_recommendation}</div>
      </div>
    </div>
  );
}
