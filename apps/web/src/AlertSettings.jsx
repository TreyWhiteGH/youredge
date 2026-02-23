import React, { useEffect, useState } from 'react';

export default function AlertSettings({ authToken }) {
  const [prefs, setPrefs] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [saved, setSaved] = useState(false);

  // Form state
  const [alertsEnabled, setAlertsEnabled] = useState(true);
  const [favoriteTeams, setFavoriteTeams] = useState([]);
  const [favoriteSports, setFavoriteSports] = useState(['nba']);
  const [minEvThreshold, setMinEvThreshold] = useState(5);
  const [quietHoursStart, setQuietHoursStart] = useState('23:00');
  const [quietHoursEnd, setQuietHoursEnd] = useState('08:00');

  const TEAMS = [
    // NBA
    'Lakers', 'Warriors', 'Celtics', 'Heat', 'Nuggets', '76ers', 'Suns', 'Mavericks',
    'Clippers', 'Kings', 'Grizzlies', 'Wolves', 'Bucks', 'Nets', 'Knicks', 'Raptors',
  ];

  useEffect(() => {
    const fetchPreferences = async () => {
      if (!authToken) {
        setLoading(false);
        return;
      }

      try {
        setError('');
        const res = await fetch('/api/alert-preferences', {
          headers: { Authorization: `Bearer ${authToken}` },
        });

        if (!res.ok) {
          throw new Error('Failed to load preferences');
        }

        const json = await res.json();
        const p = json.preferences;

        setPrefs(p);
        setAlertsEnabled(p.alerts_enabled ?? true);
        setFavoriteTeams(p.favorite_teams || []);
        setFavoriteSports(p.favorite_sports || ['nba']);
        setMinEvThreshold(p.min_ev_threshold ?? 5);
        setQuietHoursStart(p.quiet_hours?.start || '23:00');
        setQuietHoursEnd(p.quiet_hours?.end || '08:00');
      } catch (err) {
        setError(err.message);
      } finally {
        setLoading(false);
      }
    };

    fetchPreferences();
  }, [authToken]);

  const handleSave = async (e) => {
    e.preventDefault();
    setSaved(false);

    if (!authToken) {
      setError('Please login to save preferences');
      return;
    }

    try {
      const payload = {
        alerts_enabled: alertsEnabled,
        favorite_teams: favoriteTeams,
        favorite_sports: favoriteSports,
        min_ev_threshold: minEvThreshold,
        quiet_hours: {
          start: quietHoursStart,
          end: quietHoursEnd,
        },
      };

      const res = await fetch('/api/alert-preferences', {
        method: 'POST',
        headers: {
          Authorization: `Bearer ${authToken}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(payload),
      });

      if (!res.ok) {
        throw new Error('Failed to save preferences');
      }

      setSaved(true);
      setTimeout(() => setSaved(false), 3000);
    } catch (err) {
      setError(err.message);
    }
  };

  const toggleTeam = (team) => {
    if (favoriteTeams.includes(team)) {
      setFavoriteTeams(favoriteTeams.filter((t) => t !== team));
    } else {
      setFavoriteTeams([...favoriteTeams, team]);
    }
  };

  const toggleSport = (sport) => {
    if (favoriteSports.includes(sport)) {
      setFavoriteSports(favoriteSports.filter((s) => s !== sport));
    } else {
      setFavoriteSports([...favoriteSports, sport]);
    }
  };

  if (!authToken) {
    return (
      <div className="card">
        <h2>⚙️ Alert Settings</h2>
        <div className="muted">Please login to configure alert settings.</div>
      </div>
    );
  }

  return (
    <div className="card">
      <h2>⚙️ Alert Settings</h2>

      {loading && <div>Loading preferences...</div>}
      {error && <div className="error">{error}</div>}
      {saved && <div style={{ color: '#10b981', fontWeight: 700, marginBottom: 12 }}>✓ Settings saved successfully!</div>}

      {!loading && (
        <form onSubmit={handleSave} style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
          {/* Alerts Enabled */}
          <div>
            <label style={{ display: 'flex', alignItems: 'center', gap: 12, cursor: 'pointer' }}>
              <input
                type="checkbox"
                checked={alertsEnabled}
                onChange={(e) => setAlertsEnabled(e.target.checked)}
              />
              <span style={{ fontWeight: 600 }}>🚨 Enable Live Pick Alerts</span>
            </label>
          </div>

          {/* EV Threshold */}
          <div>
            <label style={{ display: 'block', fontWeight: 600, marginBottom: 8 }}>
              💰 Minimum EV Threshold ({minEvThreshold}%)
            </label>
            <input
              type="range"
              min="0"
              max="20"
              step="1"
              value={minEvThreshold}
              onChange={(e) => setMinEvThreshold(parseInt(e.target.value))}
              style={{ width: '100%', cursor: 'pointer' }}
            />
            <div style={{ fontSize: 12, color: '#64748b', marginTop: 4 }}>
              Only receive alerts for opportunities with expected value above {minEvThreshold}%
            </div>
          </div>

          {/* Favorite Sports */}
          <div>
            <label style={{ display: 'block', fontWeight: 600, marginBottom: 8 }}>🏆 Favorite Sports</label>
            <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
              {['nba', 'nfl', 'ncaaf', 'ncaam', 'ncaaw'].map((sport) => (
                <button
                  key={sport}
                  type="button"
                  onClick={() => toggleSport(sport)}
                  style={{
                    padding: '8px 16px',
                    borderRadius: 6,
                    border: '2px solid',
                    backgroundColor: favoriteSports.includes(sport) ? '#0f766e' : 'white',
                    color: favoriteSports.includes(sport) ? 'white' : '#0f766e',
                    borderColor: favoriteSports.includes(sport) ? '#0f766e' : '#cbd5e1',
                    cursor: 'pointer',
                    fontWeight: 600,
                    transition: 'all 0.3s ease',
                  }}
                >
                  {sport === 'nba' ? '🏀 NBA' : sport === 'nfl' ? '🏈 NFL' : sport === 'ncaaf' ? '🏈 NCAAF' : sport === 'ncaam' ? '🏀 NCAAM' : '🏀 NCAAW'}
                </button>
              ))}
            </div>
          </div>

          {/* Favorite Teams */}
          <div>
            <label style={{ display: 'block', fontWeight: 600, marginBottom: 8 }}>🎯 Favorite Teams (optional)</label>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(120px, 1fr))', gap: 8 }}>
              {TEAMS.map((team) => (
                <button
                  key={team}
                  type="button"
                  onClick={() => toggleTeam(team)}
                  style={{
                    padding: '8px 12px',
                    borderRadius: 6,
                    border: '1px solid',
                    backgroundColor: favoriteTeams.includes(team) ? '#14b8a6' : 'white',
                    color: favoriteTeams.includes(team) ? 'white' : '#0f172a',
                    borderColor: favoriteTeams.includes(team) ? '#14b8a6' : '#e2e8f0',
                    cursor: 'pointer',
                    fontWeight: 600,
                    fontSize: 13,
                    transition: 'all 0.3s ease',
                  }}
                >
                  {team}
                </button>
              ))}
            </div>
            <div style={{ fontSize: 12, color: '#64748b', marginTop: 8 }}>
              {favoriteTeams.length === 0
                ? 'No teams selected - receive alerts for all games'
                : `Receiving alerts for: ${favoriteTeams.join(', ')}`}
            </div>
          </div>

          {/* Quiet Hours */}
          <div>
            <label style={{ display: 'block', fontWeight: 600, marginBottom: 8 }}>🌙 Quiet Hours</label>
            <div style={{ display: 'flex', gap: 12, alignItems: 'center' }}>
              <div>
                <label style={{ display: 'block', fontSize: 12, color: '#64748b', marginBottom: 4 }}>From</label>
                <input
                  type="time"
                  value={quietHoursStart}
                  onChange={(e) => setQuietHoursStart(e.target.value)}
                  style={{ padding: '8px 12px', borderRadius: 6, border: '1px solid #e2e8f0' }}
                />
              </div>
              <div style={{ color: '#94a3b8', fontWeight: 600 }}>to</div>
              <div>
                <label style={{ display: 'block', fontSize: 12, color: '#64748b', marginBottom: 4 }}>To</label>
                <input
                  type="time"
                  value={quietHoursEnd}
                  onChange={(e) => setQuietHoursEnd(e.target.value)}
                  style={{ padding: '8px 12px', borderRadius: 6, border: '1px solid #e2e8f0' }}
                />
              </div>
            </div>
            <div style={{ fontSize: 12, color: '#64748b', marginTop: 8 }}>
              No alerts will be sent between {quietHoursStart} and {quietHoursEnd}
            </div>
          </div>

          {/* Save Button */}
          <button
            type="submit"
            style={{
              backgroundColor: '#0f766e',
              color: 'white',
              border: 'none',
              padding: '12px 24px',
              borderRadius: 6,
              cursor: 'pointer',
              fontWeight: 700,
              fontSize: 14,
              transition: 'all 0.3s ease',
            }}
            onMouseEnter={(e) => (e.target.style.backgroundColor = '#14b8a6')}
            onMouseLeave={(e) => (e.target.style.backgroundColor = '#0f766e')}
          >
            ✓ Save Settings
          </button>
        </form>
      )}
    </div>
  );
}
