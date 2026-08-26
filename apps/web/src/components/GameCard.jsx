/* ── Game card ────────────────────────────────────────────────────────────────
   The slate's unit of information: who, when, and what the market says. Prices
   come straight from the engine's best-book pick; nothing is averaged or
   re-derived here, and an archive book is labelled as one.
── */

import React from 'react';
import { Link } from 'react-router-dom';
import Icon from '../icons';
import { american, kickoffFull, kickoffTime, leagueOf, relativeTime, shortLabel, spread } from '../lib/format';

function OddsStrip({ odds, home, away }) {
  if (!odds) {
    return (
      <div className="odds-strip">
        <div className="odds-cell" style={{ gridColumn: '1 / -1' }}>
          <span className="k">Market</span>
          <span className="v muted" style={{ fontWeight: 500, fontSize: 11.5 }}>No book quoting yet</span>
        </div>
      </div>
    );
  }

  // Show the spread from the favourite's side — that's how it is quoted and read.
  const hs = odds.spread?.home, as = odds.spread?.away;
  const fav = hs?.line != null && as?.line != null ? (hs.line < 0 ? 'home' : 'away') : null;
  const favLine = fav === 'home' ? hs : fav === 'away' ? as : null;
  const favAbbr = fav === 'home' ? shortLabel(home) : fav === 'away' ? shortLabel(away) : null;
  const total = odds.total?.over;
  const ml = odds.moneyline;

  // The number leads and the team sits underneath: a school called "North Dakota
  // State" cannot share a line with its spread inside a card column.
  return (
    <div className="odds-strip">
      <div className="odds-cell">
        <span className="k">Spread</span>
        <span className="v num">{spread(favLine?.line)}</span>
        <span className="p truncate">
          {favAbbr ? `${favAbbr} · ${american(favLine?.price_american)}` : '—'}
        </span>
      </div>
      <div className="odds-cell">
        <span className="k">Total</span>
        <span className="v num">{total?.line ?? '—'}</span>
        <span className="p num">{total ? `o ${american(total.price_american)}` : '—'}</span>
      </div>
      <div className="odds-cell"
        title={`${away.name} ${american(ml?.away?.price_american)} · ${home.name} ${american(ml?.home?.price_american)}`}>
        {/* Away above home, matching the two rows directly overhead. */}
        <span className="k">Moneyline</span>
        <span className="v num">{american(ml?.away?.price_american)}</span>
        <span className="p num">{american(ml?.home?.price_american)}</span>
      </div>
    </div>
  );
}

// NCAAF `abbr` is often the full school name — printing both would read
// "North Carolina  North Carolina". Show the code only when it is really a code.
function TeamRow({ team, dim, showScore }) {
  const code = team.abbr && team.abbr !== team.name && team.abbr.length <= 5 ? team.abbr : null;
  return (
    <div className={`game-team${dim ? ' loser' : ''}`}>
      {code && <span className="abbr num">{code}</span>}
      <span className="nm truncate">{team.name}</span>
      <span className="sp" />
      {showScore ? <span className="sc num">{team.score ?? '—'}</span> : null}
    </div>
  );
}

export default function GameCard({ game, showDate = true }) {
  const league = leagueOf(game.game_id);
  const final = game.status === 'final';
  const live = game.status === 'live';
  const { home, away } = game;
  const homeWon = final && home.score > away.score;
  const awayWon = final && away.score > home.score;
  const cond = game.conditions || {};
  const odds = game.odds;

  return (
    <Link
      to={`/games/${league}/${encodeURIComponent(game.game_id)}`}
      className="card card-link game-card"
      title={kickoffFull(game.kickoff)}
    >
      <div className="game-card-top">
        {live ? (
          <span className="badge bad" ><span className="dot live" />Live</span>
        ) : final ? (
          <span className="badge">Final</span>
        ) : (
          <span className="num muted">
            {showDate ? kickoffFull(game.kickoff) : kickoffTime(game.kickoff)}
          </span>
        )}
        <span style={{ flex: 1 }} />
        {game.neutral_site && <span className="badge">Neutral</span>}
        {cond.dome || cond.roof === 'dome' || cond.roof === 'closed' ? (
          <span className="muted" title="Indoors"><Icon.Dome size={13} /></span>
        ) : null}
        {cond.wind != null && cond.wind >= 12 && (
          <span className="badge warn" title={`${cond.wind} mph wind`}>
            <Icon.Wind size={11} />{Math.round(cond.wind)}
          </span>
        )}
        {game.week ? <span className="tiny muted">Wk {game.week}</span> : null}
      </div>

      <div className="game-teams">
        <TeamRow team={away} dim={final && !awayWon} showScore={final || live} />
        <TeamRow team={home} dim={final && !homeWon} showScore={final || live} />
      </div>

      <OddsStrip odds={odds} home={home} away={away} />

      {odds && (
        <div className="row tiny" style={{ color: 'var(--text-faint)', gap: 6 }}>
          <span className={`pulse-dot ${odds.is_live_book ? 'live' : 'down'}`}
            style={!odds.is_live_book ? { background: 'var(--text-faint)' } : undefined} />
          <span>{odds.bookmaker}</span>
          {!odds.is_live_book && <span className="badge warn">archive</span>}
          <span style={{ flex: 1 }} />
          <span>{relativeTime(odds.captured_at)}</span>
          {game.books_quoting > 1 && <span>· {game.books_quoting} books</span>}
        </div>
      )}
    </Link>
  );
}
