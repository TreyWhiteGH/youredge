import React, { useEffect, useState } from 'react';

export default function AIPicksParlay({ authToken }) {
  const [dailyPicks, setDailyPicks] = useState([]);
  const [selectedPickIds, setSelectedPickIds] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [buildingParlay, setBuildingParlay] = useState(false);
  const [parlayError, setParlayError] = useState('');
  const [parlayResult, setParlayResult] = useState(null);

  // Fetch daily picks on mount
  useEffect(() => {
    const fetchDailyPicks = async () => {
      setLoading(true);
      setError('');

      const headers = authToken ? { Authorization: `Bearer ${authToken}` } : {};

      try {
        const res = await fetch('/api/picks/daily', { headers });
        if (!res.ok) {
          const err = await res.json().catch(() => ({}));
          throw new Error(err.error || `Failed to load picks (${res.status})`);
        }

        const json = await res.json();
        setDailyPicks(json.single_picks || []);
      } catch (err) {
        setError(err.message);
      } finally {
        setLoading(false);
      }
    };

    fetchDailyPicks();
  }, [authToken]);

  const handlePickToggle = (pickId) => {
    setSelectedPickIds((prev) =>
      prev.includes(pickId) ? prev.filter((id) => id !== pickId) : [...prev, pickId]
    );
  };

  const handleBuildParlay = async () => {
    if (selectedPickIds.length < 2) {
      setParlayError('Select at least 2 picks to build a parlay');
      return;
    }

    setBuildingParlay(true);
    setParlayError('');
    setParlayResult(null);

    const headers = authToken ? { Authorization: `Bearer ${authToken}` } : {};

    try {
      const res = await fetch('/api/picks/parlay', {
        method: 'POST',
        headers: { ...headers, 'Content-Type': 'application/json' },
        body: JSON.stringify({
          pick_ids: selectedPickIds,
          parlay_type: 'standard',
        }),
      });

      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.error || `Failed to build parlay (${res.status})`);
      }

      const json = await res.json();
      setParlayResult(json.parlay);
    } catch (err) {
      setParlayError(err.message);
    } finally {
      setBuildingParlay(false);
    }
  };

  if (loading) {
    return <div style={{ color: '#64748b' }}>Loading daily picks...</div>;
  }

  if (error) {
    return <div style={{ color: '#991b1b', backgroundColor: '#fee2e2', padding: '12px', borderRadius: '6px' }}>❌ {error}</div>;
  }

  if (dailyPicks.length === 0) {
    return <div style={{ color: '#64748b' }}>No picks available today. Check back later!</div>;
  }

  return (
    <div className="ai-picks-container">
      <div style={{ marginBottom: '20px' }}>
        <h3 style={{ margin: '0 0 12px 0', color: '#0f172a' }}>
          Step 1: Select Picks ({selectedPickIds.length} selected)
        </h3>
        <div style={{ color: '#64748b', fontSize: '13px', marginBottom: '12px' }}>
          Choose 2-5 picks from today's recommendations to combine into a parlay. Select picks from different games.
        </div>

        <div style={{ display: 'grid', gap: '12px' }}>
          {dailyPicks.map((pick) => {
            const isSelected = selectedPickIds.includes(pick.pick_id);
            const confidencePercent = pick.confidence * 100;
            const edgePercent = pick.edge * 100;

            return (
              <div
                key={pick.pick_id}
                onClick={() => handlePickToggle(pick.pick_id)}
                style={{
                  backgroundColor: isSelected ? '#ecfdf5' : '#ffffff',
                  border: isSelected ? '2px solid #10b981' : '1px solid #e2e8f0',
                  borderRadius: '8px',
                  padding: '12px',
                  cursor: 'pointer',
                  transition: 'all 0.2s ease',
                }}
              >
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <div style={{ flex: 1 }}>
                    <div style={{ fontSize: '14px', fontWeight: 'bold', color: '#0f172a', marginBottom: '4px' }}>
                      {isSelected ? '✓ ' : ''}{pick.away_team} @ {pick.home_team}
                    </div>
                    <div style={{ fontSize: '13px', color: '#475569' }}>
                      {pick.bet_type.toUpperCase()} • {pick.selection === 'home' ? pick.home_team : pick.away_team} {pick.line > 0 ? '+' : ''}{pick.line}
                    </div>
                  </div>
                  <div style={{ display: 'flex', gap: '12px', alignItems: 'center' }}>
                    <div style={{
                      backgroundColor: confidencePercent > 60 ? '#dcfce7' : confidencePercent > 55 ? '#fef3c7' : '#fee2e2',
                      color: confidencePercent > 60 ? '#166534' : confidencePercent > 55 ? '#92400e' : '#991b1b',
                      padding: '6px 10px',
                      borderRadius: '6px',
                      fontSize: '12px',
                      fontWeight: 'bold',
                    }}>
                      {confidencePercent.toFixed(0)}%
                    </div>
                    <div style={{ fontSize: '12px', color: '#10b981', fontWeight: 'bold', minWidth: '70px', textAlign: 'right' }}>
                      +{edgePercent.toFixed(1)}%
                    </div>
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* Build Button */}
      <div style={{ marginBottom: '20px' }}>
        <button
          onClick={handleBuildParlay}
          disabled={selectedPickIds.length < 2 || buildingParlay}
          style={{
            background: selectedPickIds.length < 2 ? '#cbd5e1' : 'linear-gradient(135deg, #ec4899 0%, #f472b6 100%)',
            color: 'white',
            border: 'none',
            padding: '12px 24px',
            borderRadius: '6px',
            fontWeight: 'bold',
            cursor: selectedPickIds.length < 2 || buildingParlay ? 'not-allowed' : 'pointer',
            width: '100%',
            fontSize: '16px',
          }}
        >
          {buildingParlay ? 'Building Parlay...' : `🎲 Build Parlay (${selectedPickIds.length} picks)`}
        </button>
        {parlayError && (
          <div style={{
            marginTop: '12px',
            color: '#991b1b',
            backgroundColor: '#fee2e2',
            padding: '12px',
            borderRadius: '6px',
            fontSize: '13px',
          }}>
            ❌ {parlayError}
          </div>
        )}
      </div>

      {/* Parlay Result */}
      {parlayResult && (
        <div style={{
          backgroundColor: '#fef3c7',
          border: '2px solid #fbbf24',
          borderRadius: '8px',
          padding: '16px',
        }}>
          <h3 style={{ margin: '0 0 16px 0', color: '#92400e' }}>✅ Your Parlay</h3>

          <div style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fit, minmax(150px, 1fr))',
            gap: '12px',
            marginBottom: '16px',
          }}>
            <div>
              <div style={{ fontSize: '12px', color: '#64748b', fontWeight: 'bold', marginBottom: '4px' }}>
                Legs
              </div>
              <div style={{ fontSize: '24px', fontWeight: 'bold', color: '#0f172a' }}>
                {parlayResult.num_legs}
              </div>
            </div>

            <div>
              <div style={{ fontSize: '12px', color: '#64748b', fontWeight: 'bold', marginBottom: '4px' }}>
                Combined Odds
              </div>
              <div style={{ fontSize: '24px', fontWeight: 'bold', color: '#0f172a' }}>
                {parlayResult.combined_odds > 0 ? '+' : ''}{parlayResult.combined_odds}
              </div>
            </div>

            <div>
              <div style={{ fontSize: '12px', color: '#64748b', fontWeight: 'bold', marginBottom: '4px' }}>
                Total Edge
              </div>
              <div style={{ fontSize: '24px', fontWeight: 'bold', color: '#10b981' }}>
                +{(parlayResult.total_edge * 100).toFixed(1)}%
              </div>
            </div>

            <div>
              <div style={{ fontSize: '12px', color: '#64748b', fontWeight: 'bold', marginBottom: '4px' }}>
                Confidence
              </div>
              <div style={{ fontSize: '24px', fontWeight: 'bold', color: '#0f172a' }}>
                {(parlayResult.confidence * 100).toFixed(0)}%
              </div>
            </div>

            <div>
              <div style={{ fontSize: '12px', color: '#64748b', fontWeight: 'bold', marginBottom: '4px' }}>
                Risk Level
              </div>
              <div style={{
                fontSize: '16px',
                fontWeight: 'bold',
                color: parlayResult.risk_level === 'low' ? '#10b981' : parlayResult.risk_level === 'medium' ? '#f59e0b' : '#ef4444',
              }}>
                {parlayResult.risk_level.toUpperCase()}
              </div>
            </div>
          </div>

          {/* Picks in Parlay */}
          <div style={{
            backgroundColor: '#ffffff',
            borderRadius: '6px',
            padding: '12px',
            marginBottom: '12px',
          }}>
            <div style={{ fontSize: '12px', color: '#64748b', fontWeight: 'bold', marginBottom: '8px' }}>
              Picks Included:
            </div>
            {parlayResult.picks && parlayResult.picks.map((pick, idx) => (
              <div key={idx} style={{ fontSize: '13px', color: '#334155', marginBottom: '4px' }}>
                {idx + 1}. {pick.away_team} @ {pick.home_team} • {pick.selection === 'home' ? pick.home_team : pick.away_team} {pick.line > 0 ? '+' : ''}{pick.line}
              </div>
            ))}
          </div>

          {/* Correlation Warning */}
          {parlayResult.correlation_warning && (
            <div style={{
              backgroundColor: '#fee2e2',
              border: '1px solid #fca5a5',
              borderRadius: '6px',
              padding: '12px',
              marginBottom: '12px',
              color: '#991b1b',
              fontSize: '13px',
            }}>
              <div style={{ fontWeight: 'bold', marginBottom: '4px' }}>⚠️ Correlation Warning</div>
              {parlayResult.correlation_warning}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
