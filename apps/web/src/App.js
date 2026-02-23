import React, { useEffect, useMemo, useState } from 'react';
import './index.css';
import LiveAlerts from './LiveAlerts';
import AlertSettings from './AlertSettings';
import AIPicksDaily from './AIPicksDaily';
import AIPicksGenerate from './AIPicksGenerate';
import AIPicksParlay from './AIPicksParlay';

const SPORTS = [
  { id: 'nfl', label: 'NFL' },
  { id: 'ncaaf', label: 'College Football' },
  { id: 'nba', label: 'NBA' },
  { id: 'ncaam', label: "Men's College BB" },
  { id: 'ncaaw', label: "Women's College BB" },
];

const buildDate = (dayOffset = 0) => {
  const d = new Date();
  d.setHours(0, 0, 0, 0);
  d.setDate(d.getDate() + dayOffset);
  return d.toISOString().slice(0, 10); // YYYY-MM-DD
};

export default function App() {
  const [selectedSport, setSelectedSport] = useState(SPORTS[0]);
  const [dayOffset, setDayOffset] = useState(0);
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [authToken, setAuthToken] = useState('');
  const [loginError, setLoginError] = useState('');
  const [authMode, setAuthMode] = useState('login');
  const [activeTab, setActiveTab] = useState('scoreboard');
  const [scoreboard, setScoreboard] = useState(null);
  const [loadingScores, setLoadingScores] = useState(true);
  const [scoreError, setScoreError] = useState('');
  const [picks, setPicks] = useState([]);
  const [loadingPicks, setLoadingPicks] = useState(true);
  const [picksError, setPicksError] = useState('');
  const [chat, setChat] = useState([{ from: 'bot', text: 'Ask me for picks!' }]);
  const [msg, setMsg] = useState('');
  const [getPicksForm, setGetPicksForm] = useState({
    sport: 'nfl',
    date: buildDate(0),
    market: 'spread',
  });
  const [getPicksResults, setGetPicksResults] = useState([]);
  const [loadingGetPicks, setLoadingGetPicks] = useState(false);
  const [getPicksError, setGetPicksError] = useState('');
  const [aiPicksSubTab, setAiPicksSubTab] = useState('daily');

  // Initialize selected sport on mount
  useEffect(() => {
    const initializeSport = async () => {
      try {
        // Try to get sports summary to find sport with most games
        const res = await fetch('/api/sports-summary');
        if (res.ok) {
          const data = await res.json();
          const sportsList = data.sports || [];

          // Find sport with most games
          const sportWithMostGames = sportsList.find(s => s.game_count > 0);
          if (sportWithMostGames) {
            const sport = SPORTS.find(s => s.id === sportWithMostGames.sport);
            if (sport) {
              setSelectedSport(sport);
              localStorage.setItem('lastBrowsedSport', sport.id);
              return;
            }
          }
        }
      } catch (err) {
        // Silently fail and fall back to localStorage
      }

      // Fall back to last browsed sport or first sport
      const lastSport = localStorage.getItem('lastBrowsedSport');
      const sport = lastSport ? SPORTS.find(s => s.id === lastSport) : null;
      setSelectedSport(sport || SPORTS[0]);
    };

    initializeSport();
  }, []);

  // Save sport selection to localStorage whenever it changes
  useEffect(() => {
    if (selectedSport) {
      localStorage.setItem('lastBrowsedSport', selectedSport.id);
    }
  }, [selectedSport]);

  useEffect(() => {
    if (!selectedSport) return;

    const loadScores = async () => {
      setLoadingScores(true);
      setScoreError('');
      const targetDate = buildDate(dayOffset);
      const params = new URLSearchParams({ sport: selectedSport.id, date: targetDate });
      const headers = authToken ? { Authorization: `Bearer ${authToken}` } : {};
      try {
        const res = await fetch(`/api/scoreboard?${params.toString()}`, { headers });
        if (!res.ok) {
          const err = await res.json().catch(() => ({}));
          throw new Error(err.error || `Request failed (${res.status})`);
        }
        const json = await res.json();
        setScoreboard(json.scoreboard);
      } catch (err) {
        setScoreError(err.message);
        setScoreboard(null);
      } finally {
        setLoadingScores(false);
      }
    };
    loadScores();
  }, [selectedSport, dayOffset]);

  useEffect(() => {
    if (!selectedSport) return;

    const loadPicks = async () => {
      setLoadingPicks(true);
      setPicksError('');
      const targetDate = buildDate(dayOffset);
      const params = new URLSearchParams({
        sport: selectedSport.id,
        date: targetDate,
      });
      if (!authToken) {
        params.set('userId', 'demo');
      }
      const headers = authToken ? { Authorization: `Bearer ${authToken}` } : {};
      try {
        const res = await fetch(`/api/picks?${params.toString()}`, { headers });
        if (!res.ok) {
          const err = await res.json().catch(() => ({}));
          throw new Error(err.error || `Picks request failed (${res.status})`);
        }
        const json = await res.json();
        setPicks(json.picks || []);
      } catch (err) {
        setPicksError(err.message);
        setPicks([]);
      } finally {
        setLoadingPicks(false);
      }
    };
    loadPicks();
  }, [selectedSport, dayOffset]);

  const addMessage = () => {
    if (!msg) return;
    setChat([
      ...chat,
      { from: 'user', text: msg },
      { from: 'bot', text: 'You said: ' + msg },
    ]);
    setMsg('');
  };

  const handleAuth = async () => {
    if (!username || !password) {
      setLoginError('Enter username and password');
      return;
    }
    setLoginError('');
    try {
      const endpoint = authMode === 'register' ? '/api/register' : '/api/login';
      const res = await fetch(endpoint, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username, password }),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.error || 'Auth failed');
      }
      const json = await res.json();
      setAuthToken(json.token);
    } catch (err) {
      setLoginError(err.message);
    }
  };

  const handlePrevious = () => setDayOffset(dayOffset - 1);
  const handleNext = () => setDayOffset(dayOffset + 1);
  const handleToday = () => setDayOffset(0);

  const handleGetPicksSubmit = async (e) => {
    e.preventDefault();
    setLoadingGetPicks(true);
    setGetPicksError('');
    setGetPicksResults([]);

    try {
      const payload = {
        sport: getPicksForm.sport,
        date: getPicksForm.date,
        markets: [getPicksForm.market],
        min_confidence: 0.58,
        min_edge: 0.03,
      };

      const headers = authToken ? { Authorization: `Bearer ${authToken}` } : {};

      const res = await fetch('/api/generate-picks', {
        method: 'POST',
        headers: { ...headers, 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });

      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.error || `Request failed (${res.status})`);
      }

      const json = await res.json();
      setGetPicksResults(json.picks || []);
    } catch (err) {
      setGetPicksError(err.message);
      setGetPicksResults([]);
    } finally {
      setLoadingGetPicks(false);
    }
  };

  const handleSavePick = async (game, prediction) => {
    if (!authToken) {
      alert('Please login to save picks');
      return;
    }

    const stake = prompt('Enter stake amount ($):', '100');
    if (!stake) return;

    try {
      const pickData = {
        sport: game.sport,
        event_id: game.game_id,
        event_date: game.date,
        matchup: game.matchup,
        bet_type: prediction.market,
        selection: prediction.selection,
        team: prediction.selection === 'home' ? game.matchup.split(' vs ')[1] : game.matchup.split(' vs ')[0],
        line: prediction.line,
        odds: -110,
        stake: parseFloat(stake),
        confidence: prediction.confidence,
        rationale: prediction.rationale,
      };

      const res = await fetch('/api/picks', {
        method: 'POST',
        headers: {
          Authorization: `Bearer ${authToken}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(pickData),
      });

      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.error || 'Failed to save pick');
      }

      alert('✅ Pick saved!');
      setActiveTab('picks');
    } catch (err) {
      alert(`Error: ${err.message}`);
    }
  };

  const formatDateLabel = (iso) => {
    const date = iso ? new Date(iso) : null;
    if (!date) return '';
    return date.toLocaleDateString(undefined, {
      weekday: 'short',
      month: 'short',
      day: 'numeric',
    });
  };

  const selectedDate = useMemo(() => {
    const d = new Date();
    d.setDate(d.getDate() + dayOffset);
    return d;
  }, [dayOffset]);

  const formatSelectedDate = () =>
    selectedDate.toLocaleDateString(undefined, {
      weekday: 'short',
      month: 'short',
      day: 'numeric',
      year: 'numeric',
    });

  const eventsByDate = useMemo(() => {
    if (!scoreboard) return [];
    const groups = {};
    (scoreboard.events || []).forEach((ev) => {
      const dayKey = ev.start ? ev.start.slice(0, 10) : 'TBD';
      if (!groups[dayKey]) groups[dayKey] = [];
      groups[dayKey].push(ev);
    });
    return Object.entries(groups)
      .sort((a, b) => a[0].localeCompare(b[0]))
      .map(([day, events]) => ({
        day,
        events: [...events].sort((a, b) => {
          const stateA = (a.status || {}).state;
          const stateB = (b.status || {}).state;
          const rank = (state) => {
            if (state === 'in' || state === 'inprogress') return 0; // live
            if (state === 'pre' || state === 'scheduled') return 1; // upcoming
            if (state === 'post' || state === 'final') return 2; // finals
            return 3;
          };
          const rA = rank(stateA);
          const rB = rank(stateB);
          if (rA !== rB) return rA - rB;
          const tA = a.start ? new Date(a.start).getTime() : Number.MAX_SAFE_INTEGER;
          const tB = b.start ? new Date(b.start).getTime() : Number.MAX_SAFE_INTEGER;
          return tA - tB;
        }),
      }));
  }, [scoreboard]);

  const formatStatus = (event) => {
    const status = event.status || {};
    const detail = status.shortDetail || status.detail;
    const start = event.start ? new Date(event.start) : null;
    if (status.state === 'pre' && start) {
      return start.toLocaleString(undefined, {
        weekday: 'short',
        hour: 'numeric',
        minute: '2-digit',
      });
    }
    return detail || status.state || 'Scheduled';
  };

  const renderGame = (event) => {
    const { home, away } = event;
    return (
      <div key={event.id} className="game-card">
        <div className="game-meta">
          <div className="game-name">{event.shortName || event.name}</div>
          <div className="game-status">{formatStatus(event)}</div>
        </div>
        <div className="team-row">
          <TeamLineup side="away" data={away} />
          <TeamLineup side="home" data={home} />
        </div>
      </div>
    );
  };

  return (
    <div>
      <header className="app-header">
        <div>
          <h1>🏆 Your Edge in Every Play</h1>
          <div style={{ color: 'rgba(255,255,255,0.9)', fontSize: 13, fontWeight: 500 }}>
            AI-Powered Sports Picks · Live Updates · Expert Analysis
          </div>
        </div>
        <div className="login-box">
          {authToken ? (
            <div className="login-status">Logged in</div>
          ) : (
            <>
              <input
                className="login-input"
                placeholder="Username"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
              />
              <input
                className="login-input"
                type="password"
                placeholder="Password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
              />
              <select
                className="login-input"
                value={authMode}
                onChange={(e) => setAuthMode(e.target.value)}
              >
                <option value="login">Login</option>
                <option value="register">Register</option>
              </select>
              <button className="nav-btn" onClick={handleAuth}>
                {authMode === 'register' ? 'Register' : 'Login'}
              </button>
              {loginError && <div className="error small">{loginError}</div>}
            </>
          )}
        </div>
      </header>
      <nav className="top-nav">
        <button
          className={`top-nav-item ${activeTab === 'scoreboard' ? 'active' : ''}`}
          onClick={() => setActiveTab('scoreboard')}
        >
          Scoreboard
        </button>
        <button
          className={`top-nav-item ${activeTab === 'picks' ? 'active' : ''}`}
          onClick={() => setActiveTab('picks')}
        >
          Your Picks
        </button>
        <button
          className={`top-nav-item ${activeTab === 'live' ? 'active' : ''}`}
          onClick={() => setActiveTab('live')}
        >
          🚨 Live Alerts
        </button>
        <button
          className={`top-nav-item ${activeTab === 'chat' ? 'active' : ''}`}
          onClick={() => setActiveTab('chat')}
        >
          Chatbot
        </button>
        <button
          className={`top-nav-item ${activeTab === 'settings' ? 'active' : ''}`}
          onClick={() => setActiveTab('settings')}
        >
          ⚙️ Alert Settings
        </button>
        <button
          className={`top-nav-item ${activeTab === 'getpicks' ? 'active' : ''}`}
          onClick={() => setActiveTab('getpicks')}
        >
          Get Picks
        </button>
        <button
          className={`top-nav-item ${activeTab === 'aipicks' ? 'active' : ''}`}
          onClick={() => setActiveTab('aipicks')}
        >
          🤖 AI Picks
        </button>
      </nav>
      <div className="container">
        <main style={{ gridColumn: activeTab === 'chat' ? '1' : '1 / span 2' }}>
          {activeTab === 'live' && <LiveAlerts authToken={authToken} />}
          {activeTab === 'settings' && <AlertSettings authToken={authToken} />}
          {activeTab === 'scoreboard' && (
            <div className="card">
              <div className="scoreboard-header">
                <h2>📊 Live Scoreboard</h2>
                <div className="sport-tabs">
                  {SPORTS.map((sport) => (
                    <button
                      key={sport.id}
                      className={`sport-tab ${
                        sport.id === selectedSport.id ? 'active' : ''
                      }`}
                      onClick={() => {
                        setSelectedSport(sport);
                        setDayOffset(0);
                      }}
                    >
                      {sport.label}
                    </button>
                  ))}
                </div>
              </div>
              <div className="score-nav">
                <div className="nav-left">
                  <button className="nav-btn" onClick={handlePrevious}>
                    &lt;
                  </button>
                  <div className="nav-label">
                    {formatSelectedDate()}
                  </div>
                  <button className="nav-btn" onClick={handleNext}>
                    &gt;
                  </button>
                  <button className="nav-btn secondary" onClick={handleToday}>
                    Today
                  </button>
                </div>
              </div>
              {loadingScores && <div>Loading scores...</div>}
              {scoreError && <div className="error">{scoreError}</div>}
              {!loadingScores && !scoreError && scoreboard && (
                <>
                  {eventsByDate.length === 0 ? (
                    <div className="muted">No games for this selection.</div>
                  ) : (
                    eventsByDate.map(({ day, events }) => (
                      <div key={day}>
                        <div className="game-grid">
                          {events.map(renderGame)}
                        </div>
                      </div>
                    ))
                  )}
                </>
              )}
            </div>
          )}
          {activeTab === 'picks' && (
            <div className="card">
              <h2>💼 Your Picks Portfolio</h2>
              {loadingPicks && <div>Loading picks...</div>}
              {picksError && <div className="error">{picksError}</div>}
              {!loadingPicks && !picksError && (
                <div className="picks-list">
                  {picks.length === 0 ? (
                    <div className="muted">No picks yet.</div>
                  ) : (
                    picks.map((p, i) => (
                      <div key={i} className="pick">
                        <div className="pick-matchup">{p.matchup}</div>
                        <div className="pick-sub">
                          {p.home} vs {p.away}
                        </div>
                        <div className="pick-status">{p.status}</div>
                      </div>
                    ))
                  )}
                </div>
              )}
            </div>
          )}
          {activeTab === 'getpicks' && (
            <div className="card">
              <h2>⚡ AI-Powered Picks Generator</h2>
              <form className="getpicks-form" onSubmit={handleGetPicksSubmit}>
                <div className="form-row">
                  <label>🏆 Sport</label>
                  <select
                    value={getPicksForm.sport}
                    onChange={(e) => setGetPicksForm({ ...getPicksForm, sport: e.target.value })}
                  >
                    {SPORTS.map((s) => (
                      <option key={s.id} value={s.id}>
                        {s.label}
                      </option>
                    ))}
                  </select>
                </div>
                <div className="form-row">
                  <label>📅 Date</label>
                  <input
                    type="date"
                    value={getPicksForm.date}
                    onChange={(e) => setGetPicksForm({ ...getPicksForm, date: e.target.value })}
                  />
                </div>
                <div className="form-row">
                  <label>📊 Market</label>
                  <select
                    value={getPicksForm.market}
                    onChange={(e) => setGetPicksForm({ ...getPicksForm, market: e.target.value })}
                  >
                    <option value="spread">Spread</option>
                    <option value="moneyline">Moneyline</option>
                    <option value="total">Total</option>
                    <option value="prop">Player Prop</option>
                    <option value="sgp">Same Game Parlay</option>
                  </select>
                </div>
                <button
                  className="nav-btn"
                  type="submit"
                  style={{
                    background: 'linear-gradient(135deg, #0f766e 0%, #14b8a6 100%)',
                    color: 'white',
                    border: 'none',
                    fontWeight: 700,
                    cursor: 'pointer'
                  }}
                >
                  🎯 Generate Picks
                </button>
              </form>
              <div className="picks-list" style={{ marginTop: 12 }}>
                {loadingGetPicks && <div>Generating AI picks...</div>}
                {getPicksError && <div className="error">{getPicksError}</div>}
                {!loadingGetPicks && !getPicksError && getPicksResults.length === 0 && (
                  <div className="muted">Fill the form and hit Generate to see suggestions.</div>
                )}
                {!loadingGetPicks && !getPicksError && getPicksResults.length > 0 && (
                  <div>
                    {getPicksResults.map((game, gameIdx) => (
                      <div key={gameIdx} style={{ marginBottom: 20, paddingBottom: 20, borderBottom: '1px solid #e2e8f0' }}>
                        <div className="pick-matchup" style={{ fontSize: 16, marginBottom: 6 }}>
                          🎯 {game.matchup}
                        </div>
                        <div className="pick-sub" style={{ fontSize: 12 }}>
                          📅 {new Date(game.date).toLocaleDateString()}
                        </div>
                        {game.predictions && game.predictions.map((pred, predIdx) => {
                          const confidencePercent = pred.confidence * 100;
                          const edgePercent = pred.edge * 100;
                          const isHighConfidence = confidencePercent > 65;
                          const isMediumConfidence = confidencePercent > 58;
                          return (
                            <div key={predIdx} style={{
                              backgroundColor: '#f8fafc',
                              padding: 14,
                              borderRadius: 10,
                              marginTop: 12,
                              marginBottom: 12,
                              border: '1px solid #e2e8f0',
                              borderLeft: `4px solid ${isHighConfidence ? '#10b981' : isMediumConfidence ? '#f59e0b' : '#ef4444'}`
                            }}>
                              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 10 }}>
                                <div>
                                  <div style={{ fontWeight: 700, fontSize: 14, color: '#0f172a' }}>
                                    {pred.market.toUpperCase()}
                                  </div>
                                  <div style={{ marginTop: 4, fontSize: 13, color: '#475569', fontWeight: 600 }}>
                                    {pred.selection === 'over' || pred.selection === 'under' ? '📊 ' : '⚪ '}
                                    {pred.selection.charAt(0).toUpperCase() + pred.selection.slice(1)} @ {pred.line}
                                  </div>
                                </div>
                                <div style={{ display: 'flex', gap: 12, alignItems: 'center' }}>
                                  <div style={{
                                    backgroundColor: isHighConfidence ? '#dcfce7' : isMediumConfidence ? '#fef3c7' : '#fee2e2',
                                    color: isHighConfidence ? '#166534' : isMediumConfidence ? '#92400e' : '#991b1b',
                                    padding: '6px 10px',
                                    borderRadius: 6,
                                    fontSize: 12,
                                    fontWeight: 700,
                                    textAlign: 'center',
                                    minWidth: '90px'
                                  }}>
                                    {confidencePercent.toFixed(0)}%<br/>
                                    <span style={{ fontSize: 10, opacity: 0.8 }}>confidence</span>
                                  </div>
                                  <div style={{ fontWeight: 700, color: '#10b981', fontSize: 14, textAlign: 'center', minWidth: '70px' }}>
                                    +{edgePercent.toFixed(1)}%<br/>
                                    <span style={{ fontSize: 10, opacity: 0.8, color: '#059669', fontWeight: 500 }}>EV</span>
                                  </div>
                                </div>
                              </div>
                              <div style={{ fontSize: 13, color: '#475569', marginBottom: 12, fontStyle: 'italic', lineHeight: 1.4 }}>
                                💡 {pred.rationale}
                              </div>
                              <div style={{ display: 'flex', gap: 8 }}>
                                {authToken && (
                                  <button
                                    style={{
                                      backgroundColor: '#0f766e',
                                      color: 'white',
                                      border: 'none',
                                      padding: '8px 16px',
                                      borderRadius: 6,
                                      cursor: 'pointer',
                                      fontSize: 13,
                                      fontWeight: 700,
                                      transition: 'all 0.3s ease'
                                    }}
                                    onMouseEnter={(e) => e.target.style.backgroundColor = '#14b8a6'}
                                    onMouseLeave={(e) => e.target.style.backgroundColor = '#0f766e'}
                                    onClick={() => handleSavePick(game, pred)}
                                  >
                                    ✓ Save to My Picks
                                  </button>
                                )}
                                {!authToken && (
                                  <div style={{ fontSize: 12, color: '#64748b', fontStyle: 'italic' }}>
                                    🔒 Login to save picks
                                  </div>
                                )}
                              </div>
                            </div>
                          );
                        })}
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>
          )}
          {activeTab === 'aipicks' && (
            <div className="card">
              <h2>🤖 AI Picks Generator MVP</h2>
              <div className="ai-picks-tabs">
                <button
                  className={`ai-picks-tab ${aiPicksSubTab === 'daily' ? 'active' : ''}`}
                  onClick={() => setAiPicksSubTab('daily')}
                >
                  📅 Daily Picks
                </button>
                <button
                  className={`ai-picks-tab ${aiPicksSubTab === 'generate' ? 'active' : ''}`}
                  onClick={() => setAiPicksSubTab('generate')}
                >
                  💭 Generate from Prompt
                </button>
                <button
                  className={`ai-picks-tab ${aiPicksSubTab === 'parlay' ? 'active' : ''}`}
                  onClick={() => setAiPicksSubTab('parlay')}
                >
                  🎲 Parlay Builder
                </button>
              </div>
              {aiPicksSubTab === 'daily' && <AIPicksDaily authToken={authToken} />}
              {aiPicksSubTab === 'generate' && <AIPicksGenerate authToken={authToken} />}
              {aiPicksSubTab === 'parlay' && <AIPicksParlay authToken={authToken} />}
            </div>
          )}
        </main>
        {activeTab === 'chat' && (
          <aside className="card">
            <>
              <h2>💬 AI Assistant</h2>
              <div className="chat-area">
                <div className="chat-messages">
                  {chat.map((c, i) => (
                    <div key={i} className={'chat-message ' + c.from}>
                      {c.text}
                    </div>
                  ))}
                </div>
                <div style={{ display: 'flex', gap: 6 }}>
                  <input
                    value={msg}
                    onChange={(e) => setMsg(e.target.value)}
                    style={{ flex: 1 }}
                    placeholder="Ask for picks..."
                  />
                  <button onClick={addMessage}>Send</button>
                </div>
              </div>
            </>
          </aside>
        )}
      </div>
      <footer className="card footer">
        <div style={{ marginBottom: 8 }}>✨ Powered by advanced sports analytics engine</div>
        <div style={{ fontSize: 12, opacity: 0.8 }}>Live ESPN data • AI-driven predictions • Responsible gambling</div>
      </footer>
    </div>
  );
}

function TeamLineup({ side, data }) {
  if (!data) {
    return (
      <div className="team">
        <div className="team-name">{side}</div>
      </div>
    );
  }
  return (
    <div className="team">
      <div className="team-header">
        <span className="team-abbrev">{data.abbrev}</span>
        {data.rank ? <span className="team-rank">#{data.rank}</span> : null}
      </div>
      <div className="team-name">{data.shortName || data.name}</div>
      <div className="team-meta">
        <span className="team-score">{data.score ?? '-'}</span>
        {data.record ? <span className="team-record">{data.record}</span> : null}
      </div>
    </div>
  );
}
