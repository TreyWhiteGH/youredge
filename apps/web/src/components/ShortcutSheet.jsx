import React from 'react';
import Icon from '../icons';

const GROUPS = [
  {
    label: 'Global',
    keys: [
      [['⌘', 'K'], 'Search everything'],
      [['/'], 'Search everything'],
      [['?'], 'This sheet'],
      [['L'], 'Flip league'],
      [['T'], 'Flip theme'],
      [['M'], 'Team logos on / off'],
      [['esc'], 'Close'],
    ],
  },
  {
    label: 'Navigate',
    keys: [
      [['1'], 'Slate'], [['2'], 'Live'], [['3'], 'Teams'], [['4'], 'Players'],
      [['5'], 'Compare'], [['6'], 'Bet Lab'], [['7'], 'Data'],
    ],
  },
  {
    label: 'In the palette',
    keys: [[['↑', '↓'], 'Move'], [['↵'], 'Open']],
  },
];

export default function ShortcutSheet({ open, onClose }) {
  if (!open) return null;
  return (
    <div className="overlay" onMouseDown={(e) => { if (e.target === e.currentTarget) onClose(); }}>
      <div className="palette" style={{ maxWidth: 480 }} role="dialog" aria-label="Keyboard shortcuts">
        <div className="palette-input" style={{ paddingBottom: 12 }}>
          <Icon.CommandKey size={17} />
          <strong style={{ flex: 1, fontSize: 14 }}>Keyboard shortcuts</strong>
          <button className="icon-btn" onClick={onClose} aria-label="Close"><Icon.Close size={15} /></button>
        </div>
        <div className="palette-list" style={{ padding: '4px 14px 14px' }}>
          {GROUPS.map((g) => (
            <div key={g.label} style={{ marginTop: 12 }}>
              <div className="eyebrow" style={{ marginBottom: 7 }}>{g.label}</div>
              {g.keys.map(([keys, desc]) => (
                <div key={desc + keys.join()} className="row" style={{ padding: '4px 0' }}>
                  <span className="small secondary" style={{ flex: 1 }}>{desc}</span>
                  <span className="kbd-group">
                    {keys.map((k) => <span key={k} className="kbd">{k}</span>)}
                  </span>
                </div>
              ))}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
