import React, { useEffect, useState } from 'react';

export default function LiveAlerts({ authToken }) {
  const [alerts, setAlerts] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [dismissedAlerts, setDismissedAlerts] = useState(new Set());

  useEffect(() => {
    const pollAlerts = async () => {
      if (!authToken) {
        setError('Please login to see live alerts');
        setLoading(false);
        return;
      }

      try {
        setError('');
        const res = await fetch('/api/live-alerts', {
          headers: { Authorization: `Bearer ${authToken}` },
        });

        if (!res.ok) {
          const err = await res.json().catch(() => ({}));
          throw new Error(err.error || `Failed to fetch alerts (${res.status})`);
        }

        const json = await res.json();
        setAlerts(json.alerts || []);
      } catch (err) {
        setError(err.message);
      } finally {
        setLoading(false);
      }
    };

    pollAlerts();
    const interval = setInterval(pollAlerts, 10000); // Poll every 10 seconds
    return () => clearInterval(interval);
  }, [authToken]);

  const handleDismiss = async (alertId) => {
    try {
      const res = await fetch(`/api/alerts/${alertId}/dismiss`, {
        method: 'POST',
        headers: { Authorization: `Bearer ${authToken}` },
      });

      if (res.ok) {
        setDismissedAlerts(new Set([...dismissedAlerts, alertId]));
        setAlerts(alerts.filter((a) => a.alert_id !== alertId));
      }
    } catch (err) {
      console.error('Error dismissing alert:', err);
    }
  };

  const getRecommendationStyle = (recommendation) => {
    const styles = {
      strong_buy: {
        bg: '#dcfce7',
        text: '#166534',
        label: '🔥 STRONG BUY',
      },
      buy: {
        bg: '#fef3c7',
        text: '#92400e',
        label: '⚡ BUY',
      },
      fair_value: {
        bg: '#e0e7ff',
        text: '#3730a3',
        label: '💡 FAIR VALUE',
      },
    };
    return styles[recommendation] || styles.fair_value;
  };

  const activeAlerts = alerts.filter((a) => !dismissedAlerts.has(a.alert_id));

  if (!authToken) {
    return (
      <div className="card">
        <h2>🚨 Live Pick Alerts</h2>
        <div className="muted">Please login to see live EV-positive betting opportunities.</div>
      </div>
    );
  }

  return (
    <div className="card">
      <h2>🚨 Live Pick Alerts</h2>
      <div style={{ fontSize: 12, color: '#64748b', marginBottom: 16 }}>
        Real-time EV-positive opportunities based on live odds vs. model predictions
      </div>

      {loading && <div>Fetching live alerts...</div>}
      {error && <div className="error">{error}</div>}

      {!loading && !error && activeAlerts.length === 0 && (
        <div className="muted">No active alerts at the moment. Check back during live games!</div>
      )}

      {!loading && !error && activeAlerts.length > 0 && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
          {activeAlerts.map((alert) => {
            const rec = getRecommendationStyle(alert.recommendation);
            return (
              <div
                key={alert.alert_id}
                style={{
                  backgroundColor: '#f8fafc',
                  border: '2px solid #e2e8f0',
                  borderLeft: `4px solid ${rec.text}`,
                  borderRadius: 10,
                  padding: 14,
                }}
              >
                {/* Header: Team matchup + Recommendation badge */}
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'start', marginBottom: 12 }}>
                  <div>
                    <div style={{ fontWeight: 700, fontSize: 16, color: '#0f172a', marginBottom: 4 }}>
                      {alert.away_team} @ {alert.home_team}
                    </div>
                    <div style={{ fontSize: 13, color: '#64748b' }}>
                      Score: {alert.current_score} • Margin: {alert.margin > 0 ? '+' : ''}{alert.margin}
                    </div>
                  </div>
                  <div
                    style={{
                      backgroundColor: rec.bg,
                      color: rec.text,
                      padding: '8px 12px',
                      borderRadius: 6,
                      fontSize: 12,
                      fontWeight: 700,
                      textAlign: 'center',
                      whiteSpace: 'nowrap',
                    }}
                  >
                    {rec.label}
                  </div>
                </div>

                {/* Pick details */}
                <div
                  style={{
                    backgroundColor: 'white',
                    padding: 12,
                    borderRadius: 8,
                    marginBottom: 12,
                    border: '1px solid #e2e8f0',
                  }}
                >
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
                    <div>
                      <div style={{ fontSize: 13, fontWeight: 600, color: '#475569' }}>
                        {alert.opportunity_type.toUpperCase()}
                      </div>
                      <div style={{ fontSize: 14, fontWeight: 700, color: '#0f172a', marginTop: 4 }}>
                        {alert.pick.toUpperCase()} @ {alert.market_odds}
                      </div>
                    </div>
                    <div style={{ textAlign: 'right' }}>
                      <div style={{ fontSize: 12, color: '#64748b', marginBottom: 4 }}>Model Probability</div>
                      <div style={{ fontSize: 16, fontWeight: 700, color: '#10b981' }}>
                        {(alert.model_win_prob * 100).toFixed(1)}%
                      </div>
                    </div>
                  </div>

                  {/* EV breakdown */}
                  <div
                    style={{
                      display: 'grid',
                      gridTemplateColumns: '1fr 1fr 1fr',
                      gap: 10,
                      marginTop: 12,
                      paddingTop: 12,
                      borderTop: '1px solid #e2e8f0',
                    }}
                  >
                    <div>
                      <div style={{ fontSize: 11, color: '#64748b', marginBottom: 4 }}>Market Probability</div>
                      <div style={{ fontSize: 14, fontWeight: 700, color: '#0f172a' }}>
                        {(alert.ev.market_probability * 100).toFixed(1)}%
                      </div>
                    </div>
                    <div>
                      <div style={{ fontSize: 11, color: '#64748b', marginBottom: 4 }}>EV</div>
                      <div
                        style={{
                          fontSize: 14,
                          fontWeight: 700,
                          color: alert.ev.ev_percentage > 0 ? '#10b981' : '#ef4444',
                        }}
                      >
                        +{alert.ev.ev_percentage.toFixed(1)}%
                      </div>
                    </div>
                    <div>
                      <div style={{ fontSize: 11, color: '#64748b', marginBottom: 4 }}>Payout if Win</div>
                      <div style={{ fontSize: 14, fontWeight: 700, color: '#0f172a' }}>
                        ${alert.ev.payout_if_win.toFixed(2)}
                      </div>
                    </div>
                  </div>
                </div>

                {/* Action buttons */}
                <div style={{ display: 'flex', gap: 8 }}>
                  <button
                    style={{
                      flex: 1,
                      backgroundColor: '#10b981',
                      color: 'white',
                      border: 'none',
                      padding: '10px 16px',
                      borderRadius: 6,
                      cursor: 'pointer',
                      fontSize: 13,
                      fontWeight: 700,
                      transition: 'all 0.3s ease',
                    }}
                    onMouseEnter={(e) => (e.target.style.backgroundColor = '#059669')}
                    onMouseLeave={(e) => (e.target.style.backgroundColor = '#10b981')}
                    onClick={() => alert(`Place bet on ${alert.pick} at ${alert.market_odds}`)}
                  >
                    ✓ Place Bet
                  </button>
                  <button
                    style={{
                      backgroundColor: '#f1f5f9',
                      color: '#64748b',
                      border: '1px solid #e2e8f0',
                      padding: '10px 16px',
                      borderRadius: 6,
                      cursor: 'pointer',
                      fontSize: 13,
                      fontWeight: 700,
                      transition: 'all 0.3s ease',
                    }}
                    onMouseEnter={(e) => (e.target.style.backgroundColor = '#e2e8f0')}
                    onMouseLeave={(e) => (e.target.style.backgroundColor = '#f1f5f9')}
                    onClick={() => handleDismiss(alert.alert_id)}
                  >
                    ✕ Dismiss
                  </button>
                </div>

                {/* Expiry notice */}
                <div style={{ fontSize: 11, color: '#94a3b8', marginTop: 8, fontStyle: 'italic' }}>
                  ⏱ Alert expires in {calculateMinutesLeft(alert.expires_at)} min
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

function calculateMinutesLeft(expiresAt) {
  const now = new Date();
  const expiry = new Date(expiresAt);
  const diffMs = expiry - now;
  const diffMins = Math.ceil(diffMs / (1000 * 60));
  return Math.max(0, diffMins);
}
