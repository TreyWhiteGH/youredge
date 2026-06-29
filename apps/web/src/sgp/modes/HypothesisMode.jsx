import React, { useState } from 'react';
import GameSelector, { FullGameCard } from '../components/GameSelector';
import { LeagueSelector, SportsbookSelector } from '../components/GlobalControls';
import { LoadingState, ErrorState, Card, PrimaryButton, SectionLabel, Divider } from '../components/shared';
import { MOCK_HYPOTHESIS_RESPONSE, mockDelay } from '../lib/mockResponses';

const EXAMPLES = [
  'I think Alabama gets up early but lets up garbage-time passing yards.',
  'I think the Chiefs win but the Broncos keep throwing late.',
  'I think this game is ugly and both teams run the ball.',
  'I think the underdog keeps it close because their QB can scramble.',
];

const FIT_COLOR = { Strong: '#10b981', Medium: '#f59e0b', Weak: '#ef4444' };

export default function HypothesisMode({ league, setLeague, sportsbook, setSportsbook }) {
  const [selectedGame, setSelectedGame] = useState(null);
  const [hypothesis, setHypothesis] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [result, setResult] = useState(null);

  const handleTest = async () => {
    if (!hypothesis.trim()) return;
    setLoading(true); setError(''); setResult(null);
    try { await mockDelay(1800); setResult(MOCK_HYPOTHESIS_RESPONSE); }
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
          <div className="text-xs mb-1.5" style={{ color: 'var(--text-muted)' }}>Game <span style={{ opacity: 0.5 }}>(optional)</span></div>
          <GameSelector league={league} sportsbook={sportsbook} selectedGame={selectedGame} onSelect={setSelectedGame} />
        </div>
        {selectedGame && <FullGameCard game={selectedGame} />}
        <div>
          <div className="text-xs mb-1.5" style={{ color: 'var(--text-muted)' }}>Your Hypothesis</div>
          <textarea value={hypothesis} onChange={e => setHypothesis(e.target.value)} rows={3}
            placeholder="e.g. I think Alabama gets up early but lets up garbage-time passing yards."
            className="w-full px-4 py-3 rounded-xl text-sm focus:outline-none resize-none"
            style={{ background: 'var(--bg-input)', border: '1px solid var(--border)', color: 'var(--text-primary)' }}
          />
        </div>
        <div>
          <div className="text-xs mb-2" style={{ color: 'var(--text-muted)' }}>Try an example:</div>
          <div className="flex flex-wrap gap-1.5">
            {EXAMPLES.map((ex, i) => (
              <button key={i} onClick={() => setHypothesis(ex)}
                className="text-xs px-2.5 py-1 rounded-lg transition-colors"
                style={{ background: 'var(--bg-input)', color: 'var(--text-muted)', border: '1px solid var(--border)' }}
                onMouseEnter={e => { e.currentTarget.style.color = 'var(--text-primary)'; }}
                onMouseLeave={e => { e.currentTarget.style.color = 'var(--text-muted)'; }}>
                "{ex.slice(0, 42)}…"
              </button>
            ))}
          </div>
        </div>
        <PrimaryButton onClick={handleTest} disabled={!hypothesis.trim() || loading} className="w-full">
          {loading ? 'Testing…' : 'Test Hypothesis'}
        </PrimaryButton>
      </Card>

      {loading && <LoadingState lines={['Parsing hypothesis…', 'Tagging script elements…', 'Finding matching markets…', 'Scoring best expressions…']} />}
      {error && <ErrorState message={error} onRetry={handleTest} />}
      {result && !loading && <HypothesisResult result={result} />}
    </div>
  );
}

function HypothesisResult({ result }) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
      <Card className="p-5">
        <SectionLabel>Detected Hypothesis</SectionLabel>
        <div className="text-base font-semibold mb-4" style={{ color: 'var(--text-primary)' }}>{result.detected_hypothesis}</div>
        <SectionLabel>Script Tags</SectionLabel>
        <div className="flex flex-wrap gap-1.5">
          {result.script_tags.map(tag => (
            <span key={tag} className="px-2.5 py-1 text-xs font-mono rounded-full text-blue-500" style={{ background: 'rgba(59,130,246,0.1)' }}>{tag}</span>
          ))}
        </div>
      </Card>

      <Card className="p-5">
        <SectionLabel>Best Markets to Express It</SectionLabel>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
          {result.best_markets.map((m, i) => (
            <div key={i} className="flex items-start gap-3 p-3 rounded-lg" style={{ background: 'var(--bg-subtle)', border: '1px solid var(--border)' }}>
              <div className="text-xs font-bold mt-0.5" style={{ color: 'var(--text-muted)', width: 16 }}>#{m.rank}</div>
              <div className="flex-1">
                <div className="flex items-center gap-2 mb-0.5">
                  <span className="text-sm font-semibold" style={{ color: 'var(--text-primary)' }}>{m.market}</span>
                  <span className="text-xs font-semibold" style={{ color: FIT_COLOR[m.fit] }}>{m.fit}</span>
                </div>
                <p className="text-xs" style={{ color: 'var(--text-muted)' }}>{m.reason}</p>
              </div>
            </div>
          ))}
        </div>
      </Card>

      <Card className="p-5">
        <SectionLabel>Avoid These Markets</SectionLabel>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
          {result.avoid_markets.map((m, i) => (
            <div key={i} className="flex items-start gap-2 p-2.5 text-sm">
              <span className="text-red-500 shrink-0">✕</span>
              <div>
                <span className="font-medium" style={{ color: 'var(--text-secondary)' }}>{m.market}</span>
                <span className="ml-2" style={{ color: 'var(--text-muted)' }}>— {m.reason}</span>
              </div>
            </div>
          ))}
        </div>
      </Card>

      <Card className="p-5">
        <SectionLabel>Best SGP Structure</SectionLabel>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8, marginBottom: 12 }}>
          {result.best_sgp.legs.map((leg, i) => (
            <div key={i} className="px-3 py-2 rounded-lg text-sm font-medium" style={{ background: 'var(--bg-subtle)', color: 'var(--text-primary)' }}>{leg}</div>
          ))}
        </div>
        <p className="text-sm mb-4" style={{ color: 'var(--text-muted)' }}>{result.best_sgp.reason}</p>
        <div className="flex items-center gap-2 flex-wrap">
          <span className="text-sm font-semibold" style={{ color: 'var(--text-secondary)' }}>{result.best_sgp.grade}</span>
          <span style={{ color: 'var(--text-muted)' }}>·</span>
          <span className="text-sm" style={{ color: 'var(--text-muted)' }}>{result.best_sgp.recommendation}</span>
        </div>
        <Divider />
        <div className="flex flex-wrap gap-2">
          {['Build SGP From Hypothesis', 'Show Safer Version', 'Show Aggressive Version'].map(label => (
            <button key={label} className="px-3 py-2 text-sm font-medium rounded-lg transition-colors"
              style={{ border: '1px solid var(--border)', color: 'var(--text-secondary)', background: 'transparent' }}>
              {label}
            </button>
          ))}
        </div>
      </Card>
    </div>
  );
}
