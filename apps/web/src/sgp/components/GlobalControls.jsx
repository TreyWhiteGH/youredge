import React from 'react';
import { LEAGUES, SPORTSBOOKS, RISK_MODES } from '../lib/types';

export function LeagueSelector({ value, onChange }) {
  return (
    <div className="flex gap-1">
      {LEAGUES.map(l => (
        <button
          key={l.id}
          onClick={() => onChange(l.id)}
          className="px-3 py-1.5 rounded-lg text-xs font-semibold transition-colors"
          style={{
            background: value === l.id ? '#2563eb' : 'var(--bg-input)',
            color: value === l.id ? 'white' : 'var(--text-secondary)',
            border: '1px solid ' + (value === l.id ? '#2563eb' : 'var(--border)'),
          }}
        >
          {l.label}
        </button>
      ))}
    </div>
  );
}

export function SportsbookSelector({ value, onChange }) {
  return (
    <select
      value={value}
      onChange={e => onChange(e.target.value)}
      className="px-3 py-1.5 rounded-lg text-xs cursor-pointer focus:outline-none"
      style={{ background: 'var(--bg-input)', border: '1px solid var(--border)', color: 'var(--text-secondary)' }}
    >
      {SPORTSBOOKS.map(s => (
        <option key={s.id} value={s.id}>{s.label}</option>
      ))}
    </select>
  );
}

export function RiskModeSelector({ value, onChange }) {
  const activeColors = { sharp: '#059669', balanced: '#2563eb', lotto: '#7c3aed' };
  return (
    <div className="flex gap-1">
      {RISK_MODES.map(r => (
        <button
          key={r.id}
          onClick={() => onChange(r.id)}
          title={r.desc}
          className="px-3 py-1.5 rounded-lg text-xs font-semibold transition-colors"
          style={{
            background: value === r.id ? activeColors[r.id] : 'var(--bg-input)',
            color: value === r.id ? 'white' : 'var(--text-secondary)',
            border: '1px solid ' + (value === r.id ? activeColors[r.id] : 'var(--border)'),
          }}
        >
          {r.label}
        </button>
      ))}
    </div>
  );
}
