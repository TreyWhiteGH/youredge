import React, { useState } from 'react';
import { MOCK_GAMES } from '../lib/types';
import { OddsFreshnessBadge } from './shared';

export default function GameSelector({ league, sportsbook, selectedGame, onSelect }) {
  const [open, setOpen] = useState(false);
  const games = MOCK_GAMES.filter(g => g.league === league);

  return (
    <div className="relative">
      <button
        onClick={() => setOpen(!open)}
        className="w-full flex items-center justify-between px-4 py-3 rounded-xl text-sm transition-colors"
        style={{ background: 'var(--bg-input)', border: '1px solid var(--border)', color: 'var(--text-primary)' }}
      >
        {selectedGame ? (
          <span className="font-semibold">
            {selectedGame.away.abbrev} @ {selectedGame.home.abbrev}
            <span className="ml-2 font-normal" style={{ color: 'var(--text-muted)' }}>{selectedGame.date}</span>
          </span>
        ) : (
          <span style={{ color: 'var(--text-muted)' }}>Select a game…</span>
        )}
        <svg className={`w-4 h-4 transition-transform ${open ? 'rotate-180' : ''}`} style={{ color: 'var(--text-muted)' }} fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
        </svg>
      </button>

      {open && (
        <div className="absolute z-50 top-full mt-2 w-full rounded-xl shadow-xl overflow-hidden" style={{ background: 'var(--bg-surface)', border: '1px solid var(--border)' }}>
          {games.length === 0 ? (
            <div className="px-4 py-6 text-center text-sm" style={{ color: 'var(--text-muted)' }}>No games available for {league}</div>
          ) : (
            games.map(game => (
              <button
                key={game.id}
                onClick={() => { onSelect(game); setOpen(false); }}
                className="w-full text-left px-4 py-3.5 transition-colors"
                style={{
                  borderBottom: '1px solid var(--border)',
                  background: selectedGame?.id === game.id ? 'rgba(59,130,246,0.08)' : 'transparent',
                }}
                onMouseEnter={e => e.currentTarget.style.background = 'var(--bg-subtle)'}
                onMouseLeave={e => e.currentTarget.style.background = selectedGame?.id === game.id ? 'rgba(59,130,246,0.08)' : 'transparent'}
              >
                <GameCardCompact game={game} />
              </button>
            ))
          )}
        </div>
      )}
    </div>
  );
}

function GameCardCompact({ game }) {
  return (
    <div>
      <div className="flex items-center justify-between mb-1.5">
        <span className="text-sm font-bold" style={{ color: 'var(--text-primary)' }}>
          {game.away.name} @ {game.home.name}
        </span>
        <span className="text-xs" style={{ color: 'var(--text-muted)' }}>{game.date}</span>
      </div>
      <div className="flex items-center gap-4 text-xs" style={{ color: 'var(--text-secondary)' }}>
        <span><span style={{ color: 'var(--text-muted)' }}>Sprd </span>{game.spread.favorite} {game.spread.line > 0 ? '+' : ''}{game.spread.line}</span>
        <span><span style={{ color: 'var(--text-muted)' }}>O/U </span>{game.total}</span>
        <span><span style={{ color: 'var(--text-muted)' }}>ML </span>{game.moneyline.away > 0 ? '+' : ''}{game.moneyline.away} / +{game.moneyline.home}</span>
      </div>
      <div className="mt-1.5">
        <OddsFreshnessBadge sportsbook={game.sportsbook} updatedAgo={game.oddsUpdated} stale={game.stale} />
      </div>
    </div>
  );
}

export function FullGameCard({ game }) {
  if (!game) return null;
  return (
    <div className="rounded-xl p-4" style={{ background: 'var(--bg-subtle)', border: '1px solid var(--border)' }}>
      <div className="flex items-start justify-between mb-3">
        <div>
          <div className="text-base font-bold" style={{ color: 'var(--text-primary)' }}>
            {game.away.name} @ {game.home.name}
          </div>
          <div className="text-xs mt-0.5" style={{ color: 'var(--text-muted)' }}>{game.date}</div>
        </div>
        <OddsFreshnessBadge sportsbook={game.sportsbook} updatedAgo={game.oddsUpdated} stale={game.stale} />
      </div>
      <div className="grid grid-cols-3 gap-3">
        {[
          { label: 'Spread', value: `${game.spread.favorite} ${game.spread.line > 0 ? '+' : ''}${game.spread.line}` },
          { label: 'Total', value: game.total },
          { label: 'ML', value: `${game.moneyline.away > 0 ? '+' : ''}${game.moneyline.away} / +${game.moneyline.home}` },
        ].map(item => (
          <div key={item.label} className="rounded-lg p-3" style={{ background: 'var(--bg-input)' }}>
            <div className="text-xs mb-1" style={{ color: 'var(--text-muted)' }}>{item.label}</div>
            <div className="text-sm font-semibold" style={{ color: 'var(--text-primary)' }}>{item.value}</div>
          </div>
        ))}
      </div>
    </div>
  );
}
