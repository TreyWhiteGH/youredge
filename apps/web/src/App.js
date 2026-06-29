import React, { useEffect, useMemo, useState } from 'react';
import './index.css';
import Home from './Home';
import BetLab from './BetLab';
import LiveAlerts from './LiveAlerts';
import AlertSettings from './AlertSettings';

const SPORTS = [
  { id: 'nfl', label: 'NFL' },
  { id: 'ncaaf', label: 'College Football' },
  { id: 'nba', label: 'NBA' },
  { id: 'ncaam', label: "Men's CBB" },
  { id: 'ncaaw', label: "Women's CBB" },
];

const buildDate = (dayOffset = 0) => {
  const d = new Date();
  d.setHours(0, 0, 0, 0);
  d.setDate(d.getDate() + dayOffset);
  return d.toISOString().slice(0, 10);
};

const NAV_TABS = [
  { id: 'home',        label: 'Home' },
  { id: 'betlab',      label: '⚡ Bet Lab', accent: true },
  { id: 'scoreboard',  label: 'Scoreboard' },
  { id: 'picks',       label: 'My Picks' },
  { id: 'live',        label: 'Live Alerts' },
  { id: 'settings',    label: 'Settings' },
];

export default function App() {
  const [darkMode, setDarkMode] = useState(true);
  const [activeTab, setActiveTab] = useState('home');

  // Auth
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [authToken, setAuthToken] = useState('');
  const [loginError, setLoginError] = useState('');
  const [authMode, setAuthMode] = useState('login');
  const [showAuth, setShowAuth] = useState(false);

  // Scoreboard
  const [selectedSport, setSelectedSport] = useState(SPORTS[0]);
  const [dayOffset, setDayOffset] = useState(0);
  const [scoreboard, setScoreboard] = useState(null);
  const [loadingScores, setLoadingScores] = useState(false);
  const [scoreError, setScoreError] = useState('');

  // Picks
  const [picks, setPicks] = useState([]);
  const [loadingPicks, setLoadingPicks] = useState(false);
  const [picksError, setPicksError] = useState('');

  // Apply dark mode class
  useEffect(() => {
    document.documentElement.classList.toggle('dark', darkMode);
  }, [darkMode]);

  // Init sport
  useEffect(() => {
    const init = async () => {
      try {
        const res = await fetch('/api/sports-summary');
        if (res.ok) {
          const data = await res.json();
          const top = (data.sports || []).find(s => s.game_count > 0);
          if (top) { const s = SPORTS.find(x => x.id === top.sport); if (s) { setSelectedSport(s); return; } }
        }
      } catch {}
      const last = localStorage.getItem('lastBrowsedSport');
      setSelectedSport(SPORTS.find(s => s.id === last) || SPORTS[0]);
    };
    init();
  }, []);

  useEffect(() => { if (selectedSport) localStorage.setItem('lastBrowsedSport', selectedSport.id); }, [selectedSport]);

  // Load scores only when scoreboard tab is active
  useEffect(() => {
    if (activeTab !== 'scoreboard' || !selectedSport) return;
    let cancelled = false;
    const load = async () => {
      setLoadingScores(true); setScoreError('');
      const params = new URLSearchParams({ sport: selectedSport.id, date: buildDate(dayOffset) });
      const headers = authToken ? { Authorization: `Bearer ${authToken}` } : {};
      try {
        const res = await fetch(`/api/scoreboard?${params}`, { headers });
        if (!res.ok) throw new Error((await res.json().catch(() => ({}))).error || `Error ${res.status}`);
        if (!cancelled) setScoreboard((await res.json()).scoreboard);
      } catch (e) { if (!cancelled) { setScoreError(e.message); setScoreboard(null); } }
      finally { if (!cancelled) setLoadingScores(false); }
    };
    load();
    return () => { cancelled = true; };
  }, [activeTab, selectedSport, dayOffset, authToken]);

  // Load picks only when picks tab is active
  useEffect(() => {
    if (activeTab !== 'picks' || !selectedSport) return;
    let cancelled = false;
    const load = async () => {
      setLoadingPicks(true); setPicksError('');
      const params = new URLSearchParams({ sport: selectedSport.id, date: buildDate(dayOffset) });
      if (!authToken) params.set('userId', 'demo');
      const headers = authToken ? { Authorization: `Bearer ${authToken}` } : {};
      try {
        const res = await fetch(`/api/picks?${params}`, { headers });
        if (!res.ok) throw new Error((await res.json().catch(() => ({}))).error || `Error ${res.status}`);
        if (!cancelled) setPicks((await res.json()).picks || []);
      } catch (e) { if (!cancelled) { setPicksError(e.message); setPicks([]); } }
      finally { if (!cancelled) setLoadingPicks(false); }
    };
    load();
    return () => { cancelled = true; };
  }, [activeTab, selectedSport, dayOffset, authToken]);

  const handleAuth = async () => {
    if (!username || !password) { setLoginError('Enter username and password'); return; }
    setLoginError('');
    try {
      const res = await fetch(authMode === 'register' ? '/api/register' : '/api/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username, password }),
      });
      if (!res.ok) throw new Error((await res.json().catch(() => ({}))).error || 'Auth failed');
      setAuthToken((await res.json()).token);
      setShowAuth(false);
    } catch (e) { setLoginError(e.message); }
  };

  const selectedDate = useMemo(() => {
    const d = new Date(); d.setDate(d.getDate() + dayOffset); return d;
  }, [dayOffset]);

  const formatDate = () => selectedDate.toLocaleDateString(undefined, { weekday: 'short', month: 'short', day: 'numeric', year: 'numeric' });

  const eventsByDate = useMemo(() => {
    if (!scoreboard) return [];
    const groups = {};
    (scoreboard.events || []).forEach(ev => {
      const key = ev.start ? ev.start.slice(0, 10) : 'TBD';
      if (!groups[key]) groups[key] = [];
      groups[key].push(ev);
    });
    return Object.entries(groups).sort(([a], [b]) => a.localeCompare(b)).map(([day, events]) => ({
      day,
      events: [...events].sort((a, b) => {
        const rank = s => s === 'in' || s === 'inprogress' ? 0 : s === 'pre' || s === 'scheduled' ? 1 : 2;
        return rank((a.status || {}).state) - rank((b.status || {}).state) ||
          (a.start ? new Date(a.start) : Infinity) - (b.start ? new Date(b.start) : Infinity);
      }),
    }));
  }, [scoreboard]);

  const formatStatus = ev => {
    const st = ev.status || {};
    const start = ev.start ? new Date(ev.start) : null;
    if ((st.state === 'pre' || st.state === 'scheduled') && start)
      return start.toLocaleString(undefined, { weekday: 'short', hour: 'numeric', minute: '2-digit' });
    return st.shortDetail || st.detail || st.state || 'Scheduled';
  };

  const renderGame = ev => (
    <div key={ev.id} className="game-card">
      <div className="game-meta">
        <div className="game-name">{ev.shortName || ev.name}</div>
        <div className="game-status">{formatStatus(ev)}</div>
      </div>
      <div className="team-row">
        <TeamCard data={ev.away} />
        <TeamCard data={ev.home} />
      </div>
    </div>
  );

  // Bet Lab is full-width, skip page-container padding
  const isFull = activeTab === 'betlab';

  return (
    <div style={{ minHeight: '100vh', background: 'var(--bg-app)' }}>

      {/* ── Header ── */}
      <header className="app-header">
        <div className="app-header-inner">
          <button className="app-logo" onClick={() => setActiveTab('home')}>
            <div className="app-logo-icon">YE</div>
            <span className="app-logo-text">
              YourEdge
              <span className="app-logo-sub"> · Sports Analytics</span>
            </span>
          </button>
          <div className="header-actions">
            <button className="theme-toggle" onClick={() => setDarkMode(d => !d)} title={darkMode ? 'Light mode' : 'Dark mode'}>
              {darkMode ? '☀️' : '🌙'}
            </button>
            {authToken ? (
              <span className="login-status">Logged in</span>
            ) : (
              <button className="nav-btn" style={{ fontSize: 12, padding: '6px 14px' }} onClick={() => setShowAuth(v => !v)}>
                {showAuth ? 'Close' : 'Login'}
              </button>
            )}
          </div>
        </div>
        {showAuth && !authToken && (
          <div style={{ borderTop: '1px solid var(--border)', padding: '10px 24px', display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
            <input className="login-input" placeholder="Username" value={username} onChange={e => setUsername(e.target.value)} />
            <input className="login-input" type="password" placeholder="Password" value={password} onChange={e => setPassword(e.target.value)} />
            <select className="login-input" value={authMode} onChange={e => setAuthMode(e.target.value)}>
              <option value="login">Login</option>
              <option value="register">Register</option>
            </select>
            <button className="nav-btn" onClick={handleAuth} style={{ background: 'var(--accent)', color: 'white', border: 'none' }}>
              {authMode === 'register' ? 'Register' : 'Login'}
            </button>
            {loginError && <span className="error" style={{ margin: 0, padding: '4px 10px' }}>{loginError}</span>}
          </div>
        )}
      </header>

      {/* ── Nav ── */}
      <nav className="top-nav">
        <div className="top-nav-inner">
          {NAV_TABS.map(tab => (
            <button key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={`top-nav-item${tab.accent ? ' sgp' : ''}${activeTab === tab.id ? ' active' : ''}`}>
              {tab.label}
            </button>
          ))}
        </div>
      </nav>

      {/* ── Bet Lab (full-width) ── */}
      {isFull && <BetLab authToken={authToken} />}

      {/* ── All other tabs ── */}
      {!isFull && (
        <div className="page-container">

          {activeTab === 'home' && (
            <Home authToken={authToken} onNavigate={setActiveTab} />
          )}

          {activeTab === 'scoreboard' && (
            <div className="card">
              <div className="scoreboard-header">
                <h2 style={{ margin: 0 }}>Scoreboard</h2>
                <div className="sport-tabs">
                  {SPORTS.map(sport => (
                    <button key={sport.id}
                      className={`sport-tab${sport.id === selectedSport.id ? ' active' : ''}`}
                      onClick={() => { setSelectedSport(sport); setDayOffset(0); }}>
                      {sport.label}
                    </button>
                  ))}
                </div>
              </div>
              <div className="score-nav">
                <button className="nav-btn" onClick={() => setDayOffset(d => d - 1)}>‹</button>
                <div className="nav-label">{formatDate()}</div>
                <button className="nav-btn" onClick={() => setDayOffset(d => d + 1)}>›</button>
                <button className="nav-btn" onClick={() => setDayOffset(0)}>Today</button>
              </div>
              {loadingScores && <div className="muted">Loading scores…</div>}
              {scoreError && <div className="error">{scoreError}</div>}
              {!loadingScores && !scoreError && (
                eventsByDate.length === 0
                  ? <div className="muted">No games for this date.</div>
                  : eventsByDate.map(({ day, events }) => <div key={day} className="game-grid">{events.map(renderGame)}</div>)
              )}
            </div>
          )}

          {activeTab === 'picks' && (
            <div className="card">
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 16 }}>
                <h2 style={{ margin: 0 }}>My Picks</h2>
                <button className="nav-btn" style={{ fontSize: 12 }} onClick={() => setActiveTab('betlab')}>+ Add Pick</button>
              </div>
              {loadingPicks && <div className="muted">Loading picks…</div>}
              {picksError && <div className="error">{picksError}</div>}
              {!loadingPicks && !picksError && (
                <div className="picks-list">
                  {picks.length === 0
                    ? (
                      <div style={{ textAlign: 'center', padding: '32px 0' }}>
                        <div style={{ fontSize: 32, marginBottom: 8 }}>💼</div>
                        <p className="muted" style={{ padding: 0 }}>No picks saved yet.</p>
                        <button className="nav-btn" style={{ marginTop: 12, background: 'var(--accent)', color: 'white', border: 'none', fontSize: 13 }} onClick={() => setActiveTab('betlab')}>
                          Go to Bet Lab →
                        </button>
                      </div>
                    )
                    : picks.map((p, i) => (
                      <div key={i} className="pick">
                        <div className="pick-matchup">{p.matchup}</div>
                        <div className="pick-sub">{p.bet_type || ''} {p.selection || ''}</div>
                        <div className="pick-status">{p.status || 'Pending'}</div>
                      </div>
                    ))
                  }
                </div>
              )}
            </div>
          )}

          {activeTab === 'live' && (
            <div className="card"><LiveAlerts authToken={authToken} /></div>
          )}

          {activeTab === 'settings' && (
            <div className="card"><AlertSettings authToken={authToken} /></div>
          )}
        </div>
      )}

      {/* ── Footer ── */}
      {!isFull && (
        <footer style={{ textAlign: 'center', padding: '20px 24px', fontSize: 11, color: 'var(--text-muted)', borderTop: '1px solid var(--border)' }}>
          YourEdge provides probability-based analysis, not guarantees. No bet is a valid outcome.
        </footer>
      )}
    </div>
  );
}

function TeamCard({ data }) {
  if (!data) return <div className="team" />;
  return (
    <div className="team">
      <div className="team-header">
        <span className="team-abbrev">{data.abbrev}</span>
        {data.rank && <span className="team-rank">#{data.rank}</span>}
      </div>
      <div className="team-name">{data.shortName || data.name}</div>
      <div className="team-meta">
        <span className="team-score">{data.score ?? '—'}</span>
        {data.record && <span className="team-record">{data.record}</span>}
      </div>
    </div>
  );
}
