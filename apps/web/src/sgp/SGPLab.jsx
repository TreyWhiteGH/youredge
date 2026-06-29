import React, { useState } from 'react';
import { SGP_MODES } from './lib/types';
import { LeagueSelector, SportsbookSelector, RiskModeSelector } from './components/GlobalControls';
import { ResponsibleGamblingFooter } from './components/shared';
import GenerateMode from './modes/GenerateMode';
import BuildAroundPickMode from './modes/BuildAroundPickMode';
import HypothesisMode from './modes/HypothesisMode';
import CritiqueMode from './modes/CritiqueMode';
import HistoryMode from './modes/HistoryMode';
import DailyPicksMode from './modes/DailyPicksMode';

const TABS = [
  { id: 'home',       label: 'Home' },
  { id: 'daily',      label: 'Daily Picks' },
  { id: 'generate',   label: 'Generate' },
  { id: 'build',      label: 'Build' },
  { id: 'hypothesis', label: 'Hypothesis' },
  { id: 'critique',   label: 'Critique' },
  { id: 'history',    label: 'History' },
];

// embedded = true when used inside BetLab (no outer chrome needed)
export default function SGPLab({ embedded = false }) {
  const [activeTab, setActiveTab] = useState('home');
  const [league, setLeague] = useState('NFL');
  const [sportsbook, setSportsbook] = useState('draftkings');
  const [riskMode, setRiskMode] = useState('balanced');

  const sharedProps = { league, setLeague, sportsbook, setSportsbook, riskMode, setRiskMode };

  return (
    <div style={embedded ? {} : { minHeight: '100vh' }}>
      {/* Controls + tab bar — sticky inside BetLab */}
      <div className="sticky z-30" style={{ top: 56, background: 'var(--bg-subtle)', borderBottom: '1px solid var(--border)' }}>
        <div style={{ maxWidth: 900, margin: '0 auto', padding: '0 16px' }}>
          {/* Controls row */}
          <div className="flex flex-wrap gap-3 items-center py-2.5" style={{ borderBottom: '1px solid var(--border)' }}>
            <LeagueSelector value={league} onChange={setLeague} />
            <div className="w-px h-4" style={{ background: 'var(--border)' }} />
            <SportsbookSelector value={sportsbook} onChange={setSportsbook} />
            <div className="w-px h-4" style={{ background: 'var(--border)' }} />
            <RiskModeSelector value={riskMode} onChange={setRiskMode} />
          </div>
          {/* SGP tabs */}
          <div className="flex overflow-x-auto">
            {TABS.map(tab => (
              <button
                key={tab.id}
                onClick={() => setActiveTab(tab.id)}
                className="px-4 py-2.5 text-xs font-semibold whitespace-nowrap transition-colors"
                style={{
                  borderBottom: `2px solid ${activeTab === tab.id ? '#3b82f6' : 'transparent'}`,
                  color: activeTab === tab.id ? '#3b82f6' : 'var(--text-muted)',
                  background: 'transparent',
                  border: 'none',
                  borderBottom: `2px solid ${activeTab === tab.id ? '#3b82f6' : 'transparent'}`,
                  cursor: 'pointer',
                }}
              >
                {tab.label}
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* Content */}
      <div style={{ maxWidth: 900, margin: '0 auto', padding: '24px 16px' }}>
        {activeTab === 'home' && <HomeScreen onSelectMode={setActiveTab} />}
        {activeTab === 'daily' && <DailyPicksMode league={league} />}
        {activeTab === 'generate' && <GenerateMode {...sharedProps} />}
        {activeTab === 'build' && <BuildAroundPickMode {...sharedProps} />}
        {activeTab === 'hypothesis' && <HypothesisMode {...sharedProps} />}
        {activeTab === 'critique' && <CritiqueMode {...sharedProps} />}
        {activeTab === 'history' && <HistoryMode />}
        <ResponsibleGamblingFooter />
      </div>
    </div>
  );
}

function HomeScreen({ onSelectMode }) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 24 }}>
      <div style={{ textAlign: 'center', padding: '16px 0 8px' }}>
        <h1 style={{ fontSize: 28, fontWeight: 900, color: 'var(--text-primary)', margin: '0 0 8px', letterSpacing: '-0.5px' }}>
          How do you want to build?
        </h1>
        <p style={{ color: 'var(--text-muted)', fontSize: 14, maxWidth: 440, margin: '0 auto' }}>
          Bring a game, pick, or theory. YourEdge finds the smartest same-game way to express it — or tells you not to bet it.
        </p>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))', gap: 12 }}>
        {SGP_MODES.map(mode => (
          <ModeCard key={mode.id} mode={mode} onSelect={() => onSelectMode(mode.id)} />
        ))}
      </div>

      {/* How it works */}
      <div className="rounded-xl p-6" style={{ background: 'var(--bg-surface)', border: '1px solid var(--border)' }}>
        <div className="text-xs font-semibold uppercase tracking-widest mb-4" style={{ color: 'var(--text-muted)' }}>How YourEdge Works</div>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: 20 }}>
          {[
            { step: '01', title: 'Script Detection', desc: 'Identifies the game script implied by your pick or hypothesis.' },
            { step: '02', title: 'Correlation Analysis', desc: 'Tests whether legs reinforce or conflict with each other.' },
            { step: '03', title: 'Price vs Fair Value', desc: 'Compares sportsbook price to model probability to find real edge.' },
          ].map(item => (
            <div key={item.step} style={{ display: 'flex', gap: 12, alignItems: 'flex-start' }}>
              <div style={{ fontFamily: 'monospace', fontWeight: 900, fontSize: 12, color: 'var(--text-muted)', marginTop: 2, minWidth: 20 }}>{item.step}</div>
              <div>
                <div style={{ fontSize: 13, fontWeight: 700, color: 'var(--text-primary)', marginBottom: 4 }}>{item.title}</div>
                <p style={{ fontSize: 12, color: 'var(--text-muted)', lineHeight: 1.5, margin: 0 }}>{item.desc}</p>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Language guide */}
      <div className="rounded-xl p-6" style={{ background: 'var(--bg-surface)', border: '1px solid var(--border)' }}>
        <div className="text-xs font-semibold uppercase tracking-widest mb-4" style={{ color: 'var(--text-muted)' }}>What YourEdge Says</div>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: 8 }}>
          {[
            { term: 'Playable small', color: '#3b82f6' },
            { term: 'No bet at this price', color: 'var(--text-muted)' },
            { term: 'The script is clean, but the price is too short', color: '#f59e0b' },
            { term: 'Negative but coherent', color: '#3b82f6' },
            { term: 'This leg hurts the script', color: '#ef4444' },
            { term: 'Minimum playable price', color: 'var(--text-secondary)' },
          ].map(item => (
            <div key={item.term} style={{ fontSize: 12, fontWeight: 500, color: item.color, background: 'var(--bg-subtle)', borderRadius: 8, padding: '8px 12px', lineHeight: 1.4 }}>
              "{item.term}"
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

function ModeCard({ mode, onSelect }) {
  const [hover, setHover] = React.useState(false);
  return (
    <button
      onClick={onSelect}
      onMouseEnter={() => setHover(true)}
      onMouseLeave={() => setHover(false)}
      style={{
        textAlign: 'left',
        padding: 20,
        background: 'var(--bg-surface)',
        border: `1px solid ${hover ? '#3b82f6' : 'var(--border)'}`,
        borderRadius: 12,
        cursor: 'pointer',
        transition: 'border-color 0.15s',
        display: 'flex',
        flexDirection: 'column',
        gap: 8,
      }}
    >
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
        <div style={{ fontSize: 22 }}>{mode.icon}</div>
        <svg style={{ width: 14, height: 14, color: hover ? '#3b82f6' : 'var(--text-muted)', transition: 'color 0.15s' }} fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
        </svg>
      </div>
      <div style={{ fontSize: 13, fontWeight: 700, color: 'var(--text-primary)' }}>{mode.label}</div>
      <p style={{ fontSize: 12, color: 'var(--text-muted)', margin: 0, lineHeight: 1.5 }}>{mode.subtitle}</p>
    </button>
  );
}
