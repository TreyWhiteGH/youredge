import React, { useState } from 'react';

export default function AIPicksGenerate({ authToken }) {
  const [prompt, setPrompt] = useState('');
  const [minConfidence, setMinConfidence] = useState(0.55);
  const [minEdge, setMinEdge] = useState(0.03);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [results, setResults] = useState(null);

  const handleGenerateFromPrompt = async (e) => {
    e.preventDefault();
    if (!prompt.trim()) {
      setError('Please enter a prompt');
      return;
    }

    setLoading(true);
    setError('');
    setResults(null);

    const headers = authToken ? { Authorization: `Bearer ${authToken}` } : {};

    try {
      const res = await fetch('/api/picks/generate', {
        method: 'POST',
        headers: { ...headers, 'Content-Type': 'application/json' },
        body: JSON.stringify({
          prompt: prompt.trim(),
          parlay: true,
          min_confidence: minConfidence,
          min_edge: minEdge,
        }),
      });

      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.error || `Request failed (${res.status})`);
      }

      const json = await res.json();
      setResults(json);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="ai-picks-container">
      <form className="ai-picks-form" onSubmit={handleGenerateFromPrompt}>
        <div className="form-row">
          <label>🎯 Your Prediction/Scenario</label>
          <textarea
            value={prompt}
            onChange={(e) => setPrompt(e.target.value)}
            placeholder="E.g., 'I think Lakers will dominate the paint and it'll be high-scoring' or 'Warriors struggle on back-to-backs'"
            rows="4"
            style={{
              width: '100%',
              padding: '12px',
              borderRadius: '6px',
              border: '1px solid #cbd5e1',
              fontFamily: 'inherit',
              fontSize: '14px',
            }}
          />
        </div>

        <div style={{ display: 'flex', gap: '20px', marginBottom: '16px' }}>
          <div className="form-row" style={{ flex: 1 }}>
            <label>📊 Min Confidence</label>
            <input
              type="number"
              step="0.01"
              min="0"
              max="1"
              value={minConfidence}
              onChange={(e) => setMinConfidence(parseFloat(e.target.value))}
              style={{
                width: '100%',
                padding: '8px',
                borderRadius: '6px',
                border: '1px solid #cbd5e1',
              }}
            />
            <small style={{ color: '#64748b', marginTop: '4px' }}>
              {(minConfidence * 100).toFixed(0)}%
            </small>
          </div>

          <div className="form-row" style={{ flex: 1 }}>
            <label>💰 Min Edge</label>
            <input
              type="number"
              step="0.01"
              min="0"
              max="0.5"
              value={minEdge}
              onChange={(e) => setMinEdge(parseFloat(e.target.value))}
              style={{
                width: '100%',
                padding: '8px',
                borderRadius: '6px',
                border: '1px solid #cbd5e1',
              }}
            />
            <small style={{ color: '#64748b', marginTop: '4px' }}>
              +{(minEdge * 100).toFixed(1)}%
            </small>
          </div>
        </div>

        <button
          className="nav-btn"
          type="submit"
          style={{
            background: 'linear-gradient(135deg, #8b5cf6 0%, #a78bfa 100%)',
            color: 'white',
            border: 'none',
            fontWeight: 700,
            cursor: 'pointer',
            width: '100%',
          }}
        >
          🔮 Generate AI Picks from Prompt
        </button>
      </form>

      {loading && <div style={{ marginTop: '20px', textAlign: 'center', color: '#64748b' }}>Analyzing your prompt...</div>}

      {error && (
        <div style={{ marginTop: '20px', color: '#991b1b', backgroundColor: '#fee2e2', padding: '12px', borderRadius: '6px' }}>
          ❌ {error}
        </div>
      )}

      {results && (
        <div style={{ marginTop: '24px' }}>
          {/* Prompt Interpretation */}
          {results.prompt_interpretation && (
            <div style={{
              backgroundColor: '#f3f0ff',
              border: '1px solid #ddd6fe',
              borderRadius: '8px',
              padding: '16px',
              marginBottom: '20px',
            }}>
              <h3 style={{ margin: '0 0 12px 0', color: '#6d28d9' }}>📖 How We Interpreted Your Prompt</h3>
              <div style={{ marginBottom: '8px' }}>
                <strong>Scenario:</strong> {results.prompt_interpretation.scenario}
              </div>
              <div style={{ marginBottom: '8px' }}>
                <strong>Keywords Found:</strong> {results.prompt_interpretation.keywords.join(', ')}
              </div>
            </div>
          )}

          {/* Picks */}
          {results.picks && results.picks.length > 0 && (
            <div style={{ marginBottom: '24px' }}>
              <h3 style={{ marginBottom: '12px', color: '#0f172a' }}>🎯 Recommended Picks</h3>
              {results.picks.map((pickResult, idx) => {
                const pick = pickResult.pick;
                const reasoning = pickResult.reasoning;
                const confidencePercent = pick.confidence * 100;
                const edgePercent = pick.edge * 100;

                return (
                  <div
                    key={idx}
                    style={{
                      backgroundColor: '#ffffff',
                      border: '1px solid #e2e8f0',
                      borderLeft: `4px solid ${confidencePercent > 60 ? '#10b981' : confidencePercent > 55 ? '#f59e0b' : '#ef4444'}`,
                      borderRadius: '8px',
                      padding: '16px',
                      marginBottom: '16px',
                    }}
                  >
                    {/* Pick Header */}
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '12px' }}>
                      <div>
                        <div style={{ fontSize: '16px', fontWeight: 'bold', color: '#0f172a', marginBottom: '4px' }}>
                          {pick.away_team} @ {pick.home_team}
                        </div>
                        <div style={{ fontSize: '13px', color: '#475569' }}>
                          {pick.bet_type.toUpperCase()} • {pick.selection === 'home' ? pick.home_team : pick.away_team} {pick.line > 0 ? '+' : ''}{pick.line}
                        </div>
                      </div>
                      <div style={{ textAlign: 'right' }}>
                        <div
                          style={{
                            backgroundColor: confidencePercent > 60 ? '#dcfce7' : confidencePercent > 55 ? '#fef3c7' : '#fee2e2',
                            color: confidencePercent > 60 ? '#166534' : confidencePercent > 55 ? '#92400e' : '#991b1b',
                            padding: '6px 10px',
                            borderRadius: '6px',
                            fontSize: '12px',
                            fontWeight: 'bold',
                            marginBottom: '4px',
                          }}
                        >
                          {confidencePercent.toFixed(0)}%
                        </div>
                        <div style={{ fontSize: '12px', color: '#10b981', fontWeight: 'bold' }}>
                          +{edgePercent.toFixed(1)}% EV
                        </div>
                      </div>
                    </div>

                    {/* Reasoning */}
                    {reasoning && (
                      <div style={{
                        backgroundColor: '#f8fafc',
                        borderRadius: '6px',
                        padding: '12px',
                        marginBottom: '12px',
                      }}>
                        <div style={{ marginBottom: '12px' }}>
                          <div style={{ fontSize: '12px', color: '#64748b', fontWeight: 'bold', marginBottom: '4px' }}>
                            Summary
                          </div>
                          <div style={{ fontSize: '13px', color: '#334155' }}>
                            {reasoning.summary}
                          </div>
                        </div>

                        {reasoning.key_factors && reasoning.key_factors.length > 0 && (
                          <div style={{ marginBottom: '12px' }}>
                            <div style={{ fontSize: '12px', color: '#64748b', fontWeight: 'bold', marginBottom: '4px' }}>
                              Key Factors
                            </div>
                            <ul style={{ margin: '0 0 0 20px', fontSize: '13px', color: '#334155', lineHeight: '1.6' }}>
                              {reasoning.key_factors.map((factor, i) => (
                                <li key={i}>{factor}</li>
                              ))}
                            </ul>
                          </div>
                        )}

                        {reasoning.risks && reasoning.risks.length > 0 && (
                          <div style={{ marginBottom: '12px' }}>
                            <div style={{ fontSize: '12px', color: '#92400e', fontWeight: 'bold', marginBottom: '4px' }}>
                              ⚠️ Risks
                            </div>
                            <ul style={{ margin: '0 0 0 20px', fontSize: '13px', color: '#334155', lineHeight: '1.6' }}>
                              {reasoning.risks.map((risk, i) => (
                                <li key={i}>{risk}</li>
                              ))}
                            </ul>
                          </div>
                        )}

                        {reasoning.user_alignment && (
                          <div>
                            <div style={{ fontSize: '12px', color: '#64748b', fontWeight: 'bold', marginBottom: '4px' }}>
                              ✓ Alignment with Your Prompt
                            </div>
                            <div style={{ fontSize: '13px', color: '#334155', fontStyle: 'italic' }}>
                              {reasoning.user_alignment}
                            </div>
                          </div>
                        )}
                      </div>
                    )}

                    <div style={{ fontSize: '12px', color: '#64748b' }}>
                      Odds: {pick.odds > 0 ? '+' : ''}{pick.odds}
                    </div>
                  </div>
                );
              })}
            </div>
          )}

          {/* Parlay */}
          {results.parlay && (
            <div style={{
              backgroundColor: '#f9fafb',
              border: '2px solid #fbbf24',
              borderRadius: '8px',
              padding: '16px',
            }}>
              <h3 style={{ margin: '0 0 12px 0', color: '#92400e' }}>🎲 Suggested Parlay</h3>
              <div style={{ marginBottom: '12px' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '8px' }}>
                  <span style={{ fontWeight: 'bold' }}>Legs:</span>
                  <span>{results.parlay.num_legs}</span>
                </div>
                <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '8px' }}>
                  <span style={{ fontWeight: 'bold' }}>Combined Odds:</span>
                  <span>{results.parlay.combined_odds > 0 ? '+' : ''}{results.parlay.combined_odds}</span>
                </div>
                <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '8px' }}>
                  <span style={{ fontWeight: 'bold' }}>Total Edge:</span>
                  <span style={{ color: '#10b981', fontWeight: 'bold' }}>+{(results.parlay.total_edge * 100).toFixed(1)}%</span>
                </div>
                <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                  <span style={{ fontWeight: 'bold' }}>Confidence:</span>
                  <span>{(results.parlay.confidence * 100).toFixed(1)}%</span>
                </div>
              </div>

              {results.parlay.correlation_warning && (
                <div style={{
                  backgroundColor: '#fee2e2',
                  border: '1px solid #fca5a5',
                  borderRadius: '6px',
                  padding: '8px',
                  fontSize: '12px',
                  color: '#991b1b',
                  marginTop: '12px',
                }}>
                  ⚠️ {results.parlay.correlation_warning}
                </div>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
