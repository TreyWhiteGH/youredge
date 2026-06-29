import React, { useState } from 'react';
import GameSelector, { FullGameCard } from '../components/GameSelector';
import { LeagueSelector, SportsbookSelector, RiskModeSelector } from '../components/GlobalControls';
import SGPResultCard from '../components/SGPResultCard';
import { LoadingState, ErrorState, Card, PrimaryButton, SectionLabel } from '../components/shared';
import { MOCK_GENERATE_RESPONSE, mockDelay } from '../lib/mockResponses';

const SINGLE_MARKETS = ['Spread', 'Moneyline', 'Total', 'Player Props'];

const MOCK_SINGLE_RESULT = {
  selection: 'Ravens -6.5',
  market: 'Spread',
  odds: '-110',
  confidence: 0.67,
  edge: 0.061,
  grade: 'A',
  rationale: 'Ravens project to control possession; Bengals secondary has struggled vs. RPO sets. Line movement suggests sharp money on Baltimore.',
  risk: 'Low',
  script: 'Run-first, clock control',
  fair_odds: '-124',
  min_playable: '-118',
};

export default function GenerateMode({ league, setLeague, sportsbook, setSportsbook, riskMode, setRiskMode }) {
  const [pickType, setPickType] = useState('sgp'); // 'sgp' | 'single'

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      {/* SGP / Singles toggle */}
      <div style={{ display: 'flex', gap: 0, padding: 4, borderRadius: 12, background: 'var(--bg-input)', border: '1px solid var(--border)', alignSelf: 'flex-start' }}>
        <TypeBtn active={pickType === 'sgp'} onClick={() => setPickType('sgp')}>⚡ Same-Game Parlay</TypeBtn>
        <TypeBtn active={pickType === 'single'} onClick={() => setPickType('single')}>🎯 Single Pick</TypeBtn>
      </div>

      {pickType === 'sgp'
        ? <SGPGenerate league={league} setLeague={setLeague} sportsbook={sportsbook} setSportsbook={setSportsbook} riskMode={riskMode} setRiskMode={setRiskMode} />
        : <SingleGenerate league={league} setLeague={setLeague} sportsbook={sportsbook} setSportsbook={setSportsbook} />
      }
    </div>
  );
}

function TypeBtn({ active, onClick, children }) {
  return (
    <button onClick={onClick}
      className="px-4 py-2 rounded-lg text-xs font-semibold transition-all"
      style={{ background: active ? '#2563eb' : 'transparent', color: active ? 'white' : 'var(--text-muted)', border: 'none', cursor: 'pointer' }}>
      {children}
    </button>
  );
}

/* ── SGP Generator ── */
function SGPGenerate({ league, setLeague, sportsbook, setSportsbook, riskMode, setRiskMode }) {
  const [selectedGame, setSelectedGame] = useState(null);
  const [allowNegCorr, setAllowNegCorr] = useState(true);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [result, setResult] = useState(null);

  const handleGenerate = async () => {
    if (!selectedGame) return;
    setLoading(true); setError(''); setResult(null);
    try {
      await mockDelay(2000);
      setResult({ ...MOCK_GENERATE_RESPONSE, game: `${selectedGame.away.name} @ ${selectedGame.home.name}` });
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <>
      <Card className="p-5" style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
        <SectionLabel>Configure SGP</SectionLabel>
        <div className="flex flex-wrap gap-3 items-center">
          <div>
            <div className="text-xs mb-1.5" style={{ color: 'var(--text-muted)' }}>League</div>
            <LeagueSelector value={league} onChange={setLeague} />
          </div>
          <div>
            <div className="text-xs mb-1.5" style={{ color: 'var(--text-muted)' }}>Sportsbook</div>
            <SportsbookSelector value={sportsbook} onChange={setSportsbook} />
          </div>
          <div>
            <div className="text-xs mb-1.5" style={{ color: 'var(--text-muted)' }}>Risk Mode</div>
            <RiskModeSelector value={riskMode} onChange={setRiskMode} />
          </div>
        </div>

        <div>
          <div className="text-xs mb-1.5" style={{ color: 'var(--text-muted)' }}>Game</div>
          <GameSelector league={league} sportsbook={sportsbook} selectedGame={selectedGame} onSelect={setSelectedGame} />
        </div>

        {selectedGame && <FullGameCard game={selectedGame} />}

        <div className="flex items-center gap-2">
          <button onClick={() => setAllowNegCorr(!allowNegCorr)}
            className="relative w-9 h-5 rounded-full transition-colors"
            style={{ background: allowNegCorr ? '#2563eb' : 'var(--border)' }}>
            <span className={`absolute top-0.5 left-0.5 w-4 h-4 rounded-full bg-white transition-transform ${allowNegCorr ? 'translate-x-4' : ''}`} />
          </button>
          <span className="text-xs" style={{ color: 'var(--text-muted)' }}>Allow negative-but-coherent correlation</span>
        </div>

        <PrimaryButton onClick={handleGenerate} disabled={!selectedGame || loading} className="w-full">
          {loading ? 'Analyzing…' : 'Generate SGP'}
        </PrimaryButton>
      </Card>

      {loading && <LoadingState lines={['Analyzing game scripts…', 'Fetching current odds…', 'Testing correlation…', 'Checking price vs fair value…']} />}
      {error && <ErrorState message={error} onRetry={handleGenerate} />}
      {result && !loading && (
        <SGPResultCard result={result} onSave={() => {}} onCritique={() => {}} onVariant={() => { setResult(null); setTimeout(handleGenerate, 100); }} />
      )}
    </>
  );
}

/* ── Single Pick Generator ── */
function SingleGenerate({ league, setLeague, sportsbook, setSportsbook }) {
  const [selectedGame, setSelectedGame] = useState(null);
  const [market, setMarket] = useState('Spread');
  const [prompt, setPrompt] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [result, setResult] = useState(null);

  const handleGenerate = async () => {
    if (!selectedGame) return;
    setLoading(true); setError(''); setResult(null);
    try {
      await mockDelay(1400);
      setResult({
        ...MOCK_SINGLE_RESULT,
        matchup: `${selectedGame.away.name} @ ${selectedGame.home.name}`,
        market,
      });
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  };

  const [saved, setSaved] = useState(false);

  return (
    <>
      <Card className="p-5" style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
        <SectionLabel>Configure Single Pick</SectionLabel>

        <div className="flex flex-wrap gap-3 items-center">
          <div>
            <div className="text-xs mb-1.5" style={{ color: 'var(--text-muted)' }}>League</div>
            <LeagueSelector value={league} onChange={setLeague} />
          </div>
          <div>
            <div className="text-xs mb-1.5" style={{ color: 'var(--text-muted)' }}>Sportsbook</div>
            <SportsbookSelector value={sportsbook} onChange={setSportsbook} />
          </div>
        </div>

        <div>
          <div className="text-xs mb-1.5" style={{ color: 'var(--text-muted)' }}>Game</div>
          <GameSelector league={league} sportsbook={sportsbook} selectedGame={selectedGame} onSelect={setSelectedGame} />
        </div>

        {selectedGame && <FullGameCard game={selectedGame} />}

        <div>
          <div className="text-xs mb-1.5" style={{ color: 'var(--text-muted)' }}>Market</div>
          <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
            {SINGLE_MARKETS.map(m => (
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
          <div className="text-xs mb-1.5" style={{ color: 'var(--text-muted)' }}>Your angle (optional)</div>
          <input
            value={prompt}
            onChange={e => setPrompt(e.target.value)}
            placeholder="e.g. I think this game goes under due to the wind…"
            className="w-full rounded-lg px-3 py-2.5 text-sm"
            style={{ background: 'var(--bg-input)', border: '1px solid var(--border)', color: 'var(--text-primary)', outline: 'none' }}
          />
        </div>

        <PrimaryButton onClick={handleGenerate} disabled={!selectedGame || loading} className="w-full">
          {loading ? 'Analyzing…' : 'Find Best Single Pick'}
        </PrimaryButton>
      </Card>

      {loading && <LoadingState lines={['Pulling current lines…', 'Scoring market edge…', 'Checking model probability…']} />}
      {error && <ErrorState message={error} onRetry={handleGenerate} />}

      {result && !loading && (
        <Card className="p-5">
          <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', marginBottom: 12 }}>
            <div>
              <div className="text-xs mb-1" style={{ color: 'var(--text-muted)' }}>{result.matchup}</div>
              <div style={{ fontSize: 18, fontWeight: 800, color: 'var(--text-primary)' }}>{result.selection}</div>
              <div style={{ display: 'flex', gap: 8, marginTop: 4, alignItems: 'center' }}>
                <span className="text-xs font-semibold" style={{ color: 'var(--text-muted)' }}>{result.market}</span>
                <span className="text-xs font-bold px-2 py-0.5 rounded-md"
                  style={{ background: 'var(--bg-subtle)', color: 'var(--text-secondary)', border: '1px solid var(--border)' }}>
                  {result.odds}
                </span>
              </div>
            </div>
            <div style={{ textAlign: 'right' }}>
              <div style={{ fontSize: 24, fontWeight: 900, color: '#10b981' }}>{(result.confidence * 100).toFixed(0)}%</div>
              <div className="text-xs" style={{ color: 'var(--text-muted)' }}>confidence</div>
              <div style={{ fontSize: 12, fontWeight: 700, color: '#10b981', marginTop: 2 }}>{result.grade}</div>
            </div>
          </div>

          {result.script && (
            <div className="text-xs font-semibold px-2 py-1 rounded-md inline-block mb-3"
              style={{ background: 'rgba(37,99,235,0.1)', color: '#3b82f6', border: '1px solid rgba(37,99,235,0.25)' }}>
              Script: {result.script}
            </div>
          )}

          <p className="text-sm leading-relaxed mb-4" style={{ color: 'var(--text-secondary)', margin: '0 0 16px' }}>{result.rationale}</p>

          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 8, marginBottom: 14 }}>
            {[
              { label: 'Edge', value: `+${(result.edge * 100).toFixed(1)}%`, color: '#10b981' },
              { label: 'Fair Odds', value: result.fair_odds },
              { label: 'Min. Playable', value: result.min_playable, color: '#3b82f6' },
            ].map(stat => (
              <div key={stat.label} className="rounded-lg p-2.5" style={{ background: 'var(--bg-subtle)', border: '1px solid var(--border)' }}>
                <div className="text-xs mb-0.5" style={{ color: 'var(--text-muted)' }}>{stat.label}</div>
                <div className="text-sm font-bold" style={{ color: stat.color || 'var(--text-secondary)' }}>{stat.value}</div>
              </div>
            ))}
          </div>

          <div style={{ display: 'flex', gap: 8 }}>
            <button onClick={() => setSaved(true)}
              className="px-4 py-2 rounded-lg text-xs font-semibold"
              style={{
                background: saved ? 'rgba(16,185,129,0.1)' : 'var(--bg-input)',
                color: saved ? '#10b981' : 'var(--text-secondary)',
                border: `1px solid ${saved ? 'rgba(16,185,129,0.35)' : 'var(--border)'}`,
              }}>
              {saved ? '✓ Saved' : 'Save Pick'}
            </button>
            <button onClick={() => { setResult(null); handleGenerate(); }}
              className="px-4 py-2 rounded-lg text-xs font-semibold"
              style={{ background: 'var(--bg-input)', color: 'var(--text-secondary)', border: '1px solid var(--border)' }}>
              Try Another
            </button>
          </div>
        </Card>
      )}
    </>
  );
}
