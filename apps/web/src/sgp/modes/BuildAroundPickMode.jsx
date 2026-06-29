import React, { useState } from 'react';
import GameSelector, { FullGameCard } from '../components/GameSelector';
import { LeagueSelector, SportsbookSelector, RiskModeSelector } from '../components/GlobalControls';
import { LoadingState, ErrorState, Card, PrimaryButton, SectionLabel, Divider, RecommendationBadge, CorrelationBadge } from '../components/shared';
import { MOCK_LEGS } from '../lib/types';
import { MOCK_BUILD_RESPONSE, mockDelay } from '../lib/mockResponses';

const FIT_COLOR = { Strong: '#10b981', Medium: '#f59e0b', Weak: '#ef4444' };

export default function BuildAroundPickMode({ league, setLeague, sportsbook, setSportsbook, riskMode, setRiskMode }) {
  const [selectedGame, setSelectedGame] = useState(null);
  const [anchorLeg, setAnchorLeg] = useState(null);
  const [legSearch, setLegSearch] = useState('');
  const [showLegList, setShowLegList] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [result, setResult] = useState(null);

  const availableLegs = selectedGame ? (MOCK_LEGS[selectedGame.id] || []) : [];
  const filteredLegs = availableLegs.filter(l => l.label.toLowerCase().includes(legSearch.toLowerCase()));

  const handleBuild = async () => {
    if (!selectedGame || !anchorLeg) return;
    setLoading(true); setError(''); setResult(null);
    try { await mockDelay(1600); setResult(MOCK_BUILD_RESPONSE); }
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
          <div><div className="text-xs mb-1.5" style={{ color: 'var(--text-muted)' }}>Risk Mode</div><RiskModeSelector value={riskMode} onChange={setRiskMode} /></div>
        </div>
        <div>
          <div className="text-xs mb-1.5" style={{ color: 'var(--text-muted)' }}>Game</div>
          <GameSelector league={league} sportsbook={sportsbook} selectedGame={selectedGame}
            onSelect={g => { setSelectedGame(g); setAnchorLeg(null); setLegSearch(''); setResult(null); }} />
        </div>
        {selectedGame && <FullGameCard game={selectedGame} />}

        {selectedGame && (
          <div className="relative">
            <div className="text-xs mb-1.5" style={{ color: 'var(--text-muted)' }}>Anchor Pick</div>
            <input value={legSearch}
              onChange={e => { setLegSearch(e.target.value); setShowLegList(true); setAnchorLeg(null); }}
              onFocus={() => setShowLegList(true)}
              placeholder="Search or type your pick… e.g. Ravens -6.5"
              className="w-full px-4 py-2.5 rounded-xl text-sm focus:outline-none"
              style={{ background: 'var(--bg-input)', border: '1px solid var(--border)', color: 'var(--text-primary)' }}
            />
            {showLegList && filteredLegs.length > 0 && (
              <div className="absolute z-50 top-full mt-1 w-full rounded-xl shadow-xl max-h-48 overflow-y-auto"
                style={{ background: 'var(--bg-surface)', border: '1px solid var(--border)' }}>
                {filteredLegs.map(leg => (
                  <button key={leg.id} onClick={() => { setAnchorLeg(leg); setLegSearch(leg.label); setShowLegList(false); setResult(null); }}
                    className="w-full text-left px-4 py-2.5 text-sm transition-colors"
                    style={{ borderBottom: '1px solid var(--border)', color: 'var(--text-primary)', background: 'transparent' }}
                    onMouseEnter={e => e.currentTarget.style.background = 'var(--bg-subtle)'}
                    onMouseLeave={e => e.currentTarget.style.background = 'transparent'}>
                    <span className="font-medium">{leg.label}</span>
                    <span className="ml-2 text-xs" style={{ color: 'var(--text-muted)' }}>{leg.market}</span>
                  </button>
                ))}
              </div>
            )}
          </div>
        )}

        {anchorLeg && (
          <div className="flex items-center justify-between rounded-lg px-4 py-2.5"
            style={{ background: 'rgba(37,99,235,0.08)', border: '1px solid rgba(37,99,235,0.25)' }}>
            <div>
              <div className="text-xs text-blue-500 mb-0.5">Anchor Pick</div>
              <div className="text-sm font-semibold" style={{ color: 'var(--text-primary)' }}>{anchorLeg.label}</div>
            </div>
            <button onClick={() => { setAnchorLeg(null); setLegSearch(''); }} className="text-xs" style={{ color: 'var(--text-muted)' }}>Clear</button>
          </div>
        )}

        <PrimaryButton onClick={handleBuild} disabled={!selectedGame || !anchorLeg || loading} className="w-full">
          {loading ? 'Building…' : 'Build Best SGP Around This Pick'}
        </PrimaryButton>
      </Card>

      {loading && <LoadingState lines={['Analyzing anchor pick…', 'Detecting implied script…', 'Finding compatible legs…', 'Checking correlation fit…']} />}
      {error && <ErrorState message={error} onRetry={handleBuild} />}
      {result && !loading && <BuildResult result={result} />}
    </div>
  );
}

function BuildResult({ result }) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
      <Card className="p-5">
        <div className="flex items-center justify-between mb-3">
          <div>
            <SectionLabel>Anchor Pick</SectionLabel>
            <div className="text-base font-bold" style={{ color: 'var(--text-primary)' }}>{result.anchor.selection}</div>
            <div className="text-xs mt-0.5" style={{ color: 'var(--text-muted)' }}>{result.anchor.type}</div>
          </div>
        </div>
        <Divider />
        <SectionLabel>Implied Script</SectionLabel>
        <ul style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
          {result.implied_script.map((s, i) => (
            <li key={i} className="flex items-start gap-2 text-sm" style={{ color: 'var(--text-secondary)' }}>
              <span className="text-blue-500 mt-0.5">›</span> {s}
            </li>
          ))}
        </ul>
      </Card>

      <Card className="p-5">
        <SectionLabel>Best Adds</SectionLabel>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
          {result.best_adds.map((add, i) => (
            <div key={i} className="flex items-start gap-3 p-3 rounded-lg"
              style={{ background: 'rgba(16,185,129,0.05)', border: '1px solid rgba(16,185,129,0.2)' }}>
              <div className="text-xs font-bold mt-0.5" style={{ color: 'var(--text-muted)' }}>#{i + 1}</div>
              <div className="flex-1">
                <div className="flex items-center gap-2 mb-0.5">
                  <span className="text-sm font-semibold" style={{ color: 'var(--text-primary)' }}>{add.selection}</span>
                  <span className="text-xs font-semibold" style={{ color: FIT_COLOR[add.fit] }}>{add.fit} Fit</span>
                </div>
                <p className="text-xs" style={{ color: 'var(--text-muted)' }}>{add.reason}</p>
              </div>
            </div>
          ))}
        </div>
      </Card>

      <Card className="p-5">
        <SectionLabel>Avoid These Legs</SectionLabel>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
          {result.avoid.map((a, i) => (
            <div key={i} className="flex items-start gap-3 p-3 rounded-lg"
              style={{ background: 'rgba(239,68,68,0.05)', border: '1px solid rgba(239,68,68,0.2)' }}>
              <span className="text-red-500 text-sm mt-0.5">✕</span>
              <div>
                <div className="text-sm font-medium" style={{ color: 'var(--text-secondary)' }}>{a.selection}</div>
                <p className="text-xs mt-0.5" style={{ color: 'var(--text-muted)' }}>{a.reason}</p>
              </div>
            </div>
          ))}
        </div>
      </Card>

      <Card className="p-5">
        <SectionLabel>Best Build</SectionLabel>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8, marginBottom: 12 }}>
          {result.best_build.legs.map((leg, i) => (
            <div key={i} className="px-3 py-2 rounded-lg text-sm font-medium" style={{ background: 'var(--bg-subtle)', color: 'var(--text-primary)' }}>{leg}</div>
          ))}
        </div>
        <div className="flex items-center gap-3 flex-wrap mb-3">
          <CorrelationBadge type={result.best_build.correlation_type} />
          <RecommendationBadge recommendation="Playable small" />
        </div>
        <div className="text-sm" style={{ color: 'var(--text-muted)' }}>{result.best_build.recommendation}</div>
        <div className="mt-2 text-xs" style={{ color: 'var(--text-muted)' }}>
          Minimum playable: <span className="font-semibold" style={{ color: 'var(--text-secondary)' }}>{result.best_build.minimum_playable_price}</span>
        </div>
      </Card>
    </div>
  );
}
