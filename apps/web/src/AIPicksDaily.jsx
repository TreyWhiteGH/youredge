import React, { useEffect, useState } from 'react';

export default function AIPicksDaily({ authToken }) {
  const [dailyPicks, setDailyPicks] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [expandedPick, setExpandedPick] = useState(null);

  useEffect(() => {
    const fetchDailyPicks = async () => {
      setLoading(true);
      setError('');
      const headers = authToken ? { Authorization: `Bearer ${authToken}` } : {};

      try {
        const res = await fetch('/api/picks/daily', { headers });
        if (!res.ok) {
          throw new Error(`HTTP ${res.status}`);
        }
        const data = await res.json();
        setDailyPicks(data);
      } catch (err) {
        setError(`Failed to load daily picks: ${err.message}`);
      } finally {
        setLoading(false);
      }
    };

    fetchDailyPicks();
  }, [authToken]);

  if (loading) {
    return (
      <div className="section">
        <h3>Daily AI Picks</h3>
        <div className="loading">Loading daily picks...</div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="section">
        <h3>Daily AI Picks</h3>
        <div className="error">{error}</div>
      </div>
    );
  }

  if (!dailyPicks) {
    return (
      <div className="section">
        <h3>Daily AI Picks</h3>
        <div className="empty">No picks available</div>
      </div>
    );
  }

  const { metadata, single_picks, parlays } = dailyPicks;

  return (
    <div className="section">
      <h3>Daily AI Picks - {dailyPicks.date}</h3>

      {metadata && (
        <div className="metadata-stats">
          <div className="stat">
            <strong>{metadata.total_games}</strong>
            <span>Games Today</span>
          </div>
          <div className="stat">
            <strong>{metadata.picks_generated}</strong>
            <span>AI Picks</span>
          </div>
          <div className="stat">
            <strong>+{(metadata.best_edge * 100).toFixed(1)}%</strong>
            <span>Best Edge</span>
          </div>
        </div>
      )}

      <div className="picks-container">
        <h4>Single Picks ({single_picks.length})</h4>
        {single_picks.length === 0 ? (
          <div className="empty">No picks available</div>
        ) : (
          <div className="picks-list">
            {single_picks.map((pick) => (
              <PickCard
                key={pick.pick_id}
                pick={pick}
                expanded={expandedPick === pick.pick_id}
                onToggle={() =>
                  setExpandedPick(
                    expandedPick === pick.pick_id ? null : pick.pick_id
                  )
                }
              />
            ))}
          </div>
        )}
      </div>

      {parlays.length > 0 && (
        <div className="parlays-container">
          <h4>Suggested Parlays ({parlays.length})</h4>
          <div className="parlays-list">
            {parlays.map((parlay) => (
              <div key={parlay.parlay_id} className="parlay-card card">
                <div className="parlay-header">
                  <span className="parlay-legs">{parlay.num_legs}-Leg</span>
                  <span className="parlay-odds">{parlay.combined_odds > 0 ? '+' : ''}{parlay.combined_odds}</span>
                  <span className={`parlay-risk risk-${parlay.risk_level}`}>
                    {parlay.risk_level.toUpperCase()}
                  </span>
                </div>
                <div className="parlay-details">
                  <p>
                    <strong>Confidence:</strong> {(parlay.confidence * 100).toFixed(1)}%
                  </p>
                  <p>
                    <strong>Edge:</strong> +{(parlay.total_edge * 100).toFixed(1)}%
                  </p>
                  {parlay.correlation_warning && (
                    <p className="warning">⚠️ {parlay.correlation_warning}</p>
                  )}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function PickCard({ pick, expanded, onToggle }) {
  const selectionLabel = {
    spread: `${pick.selection === 'home' ? pick.home_team : pick.away_team} ${pick.line > 0 ? '+' : ''}${pick.line}`,
    total: `Total ${pick.selection} ${pick.line}`,
    moneyline: `${pick.selection === 'home' ? pick.home_team : pick.away_team} ML`,
  };

  return (
    <div className="pick-card card">
      <div className="pick-header" onClick={onToggle} style={{ cursor: 'pointer' }}>
        <div className="pick-matchup">
          <strong>{pick.away_team}</strong> @ <strong>{pick.home_team}</strong>
        </div>
        <div className="pick-selection">
          {selectionLabel[pick.bet_type] || pick.selection}
        </div>
        <div className="pick-confidence">
          <span className={`confidence-badge conf-${Math.round(pick.confidence * 100)}`}>
            {(pick.confidence * 100).toFixed(0)}%
          </span>
          <span className="edge-badge">+{(pick.edge * 100).toFixed(1)}%</span>
        </div>
      </div>

      {expanded && (
        <div className="pick-details">
          <div className="detail-row">
            <span>Odds:</span>
            <strong>{pick.odds > 0 ? '+' : ''}{pick.odds}</strong>
          </div>
          {pick.rationale && (
            <div className="detail-row">
              <span>Rationale:</span>
              <p>{pick.rationale}</p>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
