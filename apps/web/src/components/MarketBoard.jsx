/* ── Market board ─────────────────────────────────────────────────────────────
   Every market a book has priced for one game, in the sections people actually
   think in: the three featured lines, alternates, period markets, team totals,
   and player props grouped by the person they are about.

   Props are loaded only when their tab is opened. A busy NFL game carries 80+ prop
   markets across six categories, and pulling that on every game view to render a
   panel most visits never open is the wrong trade.
── */

import React, { useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import Icon from '../icons';
import * as api from '../lib/api';
import { useApi } from '../lib/hooks';
import { american, marketLabel, pct, relativeTime, spread } from '../lib/format';
import { Card, Empty, ErrorState, Loading, Notice } from './ui';

export default function MarketBoard({ league, gameId, board, home, away }) {
  const [tab, setTab] = useState('featured');

  const sections = board?.sections || {};
  const propKeys = board?.prop_market_keys || [];

  const tabs = [
    { id: 'featured', label: 'Featured', count: board?.books?.length || 0, icon: Icon.Odds },
    { id: 'props', label: 'Player props', count: propKeys.length, icon: Icon.Players },
    { id: 'alternates', label: 'Alternates', count: sections.alternates?.length || 0, icon: Icon.Layers },
    { id: 'periods', label: 'Halves & quarters', count: sections.periods?.length || 0, icon: Icon.Clock },
    { id: 'team_totals', label: 'Team totals', count: sections.team_totals?.length || 0, icon: Icon.Shield },
  ].filter((t) => t.count > 0 || t.id === 'featured');

  return (
    <>
      <div className="scroll-x">
        {tabs.map((t) => (
          <button key={t.id} className="chip" aria-pressed={tab === t.id} onClick={() => setTab(t.id)}>
            <t.icon size={13} /> {t.label}
            <span className="tiny muted num">{t.count}</span>
          </button>
        ))}
      </div>

      {tab === 'featured' && <Featured board={board} home={home} away={away} />}
      {tab === 'props' && <Props league={league} gameId={gameId} home={home} away={away} />}
      {tab === 'alternates' && <SideMarkets rows={sections.alternates} home={home} away={away} />}
      {tab === 'periods' && <SideMarkets rows={sections.periods} home={home} away={away} />}
      {tab === 'team_totals' && <SideMarkets rows={sections.team_totals} home={home} away={away} />}
    </>
  );
}

/* ── Featured: the three lines, one row per book ── */

function Featured({ board, home, away }) {
  const books = board?.books || [];

  const moves = useMemo(() => {
    const seen = new Map();
    for (const m of board?.movement || []) {
      const k = `${m.bookmaker}|${m.market_key}|${m.outcome}`;
      if (!seen.has(k)) seen.set(k, { first: m, last: m, n: 1 });
      else { const e = seen.get(k); e.last = m; e.n += 1; }
    }
    return seen;
  }, [board?.movement]);

  if (!books.length) {
    return <Card><Empty icon={Icon.Odds} title="No prices stored"
      body="No bookmaker has been polled for this game yet. Run the odds poller to populate it." /></Card>;
  }

  const drift = (book, outcome) => {
    const e = moves.get(`${book}|spreads|${outcome}`);
    if (!e || e.n < 2) return null;
    const a = e.first.line, b = e.last.line;
    return a == null || b == null || a === b ? null : b - a;
  };

  return (
    <Card>
      <div className="table-scroll">
        <table className="data">
          <thead>
            <tr>
              <th>Book</th>
              <th>{away.abbr} spread</th><th>{home.abbr} spread</th><th>Total</th>
              <th>{away.abbr} ML</th><th>{home.abbr} ML</th>
              <th>Fair {away.abbr}</th><th>Updated</th>
            </tr>
          </thead>
          <tbody>
            {books.map((b) => {
              const d = drift(b.bookmaker, home.name);
              return (
                <tr key={b.bookmaker}>
                  <td>
                    <span className="row" style={{ gap: 6 }}>
                      <span className={`pulse-dot ${b.is_live_book ? 'live' : ''}`}
                        style={!b.is_live_book ? { background: 'var(--text-faint)' } : undefined} />
                      {b.bookmaker}
                      {!b.is_live_book && <span className="badge warn">archive</span>}
                    </span>
                  </td>
                  <td className="num">{spread(b.spread?.away?.line)}
                    <span className="muted"> {american(b.spread?.away?.price_american)}</span></td>
                  <td className="num">{spread(b.spread?.home?.line)}
                    <span className="muted"> {american(b.spread?.home?.price_american)}</span>
                    {d != null && <span className={d < 0 ? ' good' : ' bad'}> {d > 0 ? '↑' : '↓'}{Math.abs(d).toFixed(1)}</span>}
                  </td>
                  <td className="num">{b.total?.over?.line ?? '—'}
                    <span className="muted"> {american(b.total?.over?.price_american)}</span></td>
                  <td className="num">{american(b.moneyline?.away?.price_american)}</td>
                  <td className="num">{american(b.moneyline?.home?.price_american)}</td>
                  <td className="num accent">{pct(b.moneyline?.away?.fair_prob)}</td>
                  <td className="num muted">{relativeTime(b.captured_at)}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <div className="card-pad tiny muted" style={{ borderTop: '1px solid var(--border-soft)' }}>
        {board.movement?.length || 0} snapshots stored. Arrows show how each book's home
        spread has moved since its first snapshot.
      </div>
    </Card>
  );
}

/* ── Alternates, periods, team totals ── */

function SideMarkets({ rows = [], home, away }) {
  const [book, setBook] = useState('all');
  const books = useMemo(() => [...new Set(rows.map((r) => r.bookmaker))].sort(), [rows]);
  const shown = book === 'all' ? rows : rows.filter((r) => r.bookmaker === book);

  const byMarket = useMemo(() => {
    const m = new Map();
    for (const r of shown) {
      if (!m.has(r.market_key)) m.set(r.market_key, []);
      m.get(r.market_key).push(r);
    }
    return [...m.entries()];
  }, [shown]);

  if (!rows.length) return <Card><Empty icon={Icon.Layers} title="No markets here" />
    </Card>;

  const label = (r) => {
    if (r.team_id === home.team_id) return home.abbr;
    if (r.team_id === away.team_id) return away.abbr;
    return r.outcome;
  };

  return (
    <>
      {books.length > 1 && (
        <div className="scroll-x">
          <button className="chip" aria-pressed={book === 'all'} onClick={() => setBook('all')}>All books</button>
          {books.map((b) => (
            <button key={b} className="chip" aria-pressed={book === b} onClick={() => setBook(b)}>{b}</button>
          ))}
        </div>
      )}
      {byMarket.map(([key, list]) => (
        <Card key={key}>
          <div className="card-head"><h3>{marketLabel(key)}</h3>
            <span className="spacer" /><span className="tiny muted num">{list.length} prices</span></div>
          <div className="table-scroll">
            <table className="data">
              <thead><tr><th>Selection</th><th>Line</th><th>Price</th><th>Fair</th><th>Book</th></tr></thead>
              <tbody>
                {list.map((r, i) => (
                  <tr key={`${r.bookmaker}-${r.outcome}-${r.line}-${i}`}>
                    <td style={{ fontWeight: 600 }}>{label(r)}</td>
                    <td className="num">{r.line ?? '—'}</td>
                    <td className="num">{american(r.price_american)}</td>
                    <td className="num accent">{pct(r.fair_prob)}</td>
                    <td className="muted">{r.bookmaker}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      ))}
    </>
  );
}

/* ── Player props ── */

function Props({ league, gameId, home, away }) {
  const [market, setMarket] = useState('all');
  const [team, setTeam] = useState('all');

  const { data, loading, error, refetch } = useApi(
    `props:${gameId}`, (s) => api.getGameProps(league, gameId, {}, { signal: s }));

  if (loading) return <Loading rows={4} height={64} />;
  if (error) return <ErrorState error={error} onRetry={refetch} />;

  const subjects = data?.subjects || [];
  if (!subjects.length) {
    return <Card><Empty icon={Icon.Players} title="No player props stored"
      body="Props cost separate API credits, so they are only polled for a subset of games." /></Card>;
  }

  const keys = data.market_keys || [];
  const filtered = subjects.filter((s) => {
    if (team !== 'all' && s.team_id !== team) return false;
    if (market !== 'all' && !s.markets.some((m) => m.market_key === market)) return false;
    return true;
  });

  return (
    <>
      <div className="scroll-x">
        <button className="chip" aria-pressed={market === 'all'} onClick={() => setMarket('all')}>
          All markets
        </button>
        {keys.map((k) => (
          <button key={k} className="chip" aria-pressed={market === k} onClick={() => setMarket(k)}>
            {marketLabel(k)}
          </button>
        ))}
      </div>
      <div className="scroll-x">
        <button className="chip" aria-pressed={team === 'all'} onClick={() => setTeam('all')}>Both teams</button>
        {[away, home].map((t) => (
          <button key={t.team_id} className="chip" aria-pressed={team === t.team_id}
            onClick={() => setTeam(t.team_id)}>{t.abbr}</button>
        ))}
      </div>

      {filtered.length === 0 ? (
        <Card><Empty icon={Icon.Players} title="Nothing matches those filters" /></Card>
      ) : (
        <div className="grid grid-wide stagger">
          {filtered.map((s) => (
            <SubjectCard key={s.subject_id} subject={s} market={market} league={league} />
          ))}
        </div>
      )}

      <Notice icon={Icon.Info}>
        Prices are the latest each book has shown. <strong>fair_prob is the de-vigged
        price</strong> where both sides of a market exist — anytime-touchdown is quoted
        one-sided, so it has no fair value here and the column stays empty rather than
        guessing at the hold.
      </Notice>
    </>
  );
}

function SubjectCard({ subject, market, league }) {
  const markets = market === 'all'
    ? subject.markets
    : subject.markets.filter((m) => m.market_key === market);
  if (!markets.length) return null;

  return (
    <Card>
      <div className="card-head">
        <span className="muted" style={{ display: 'grid' }}>
          {subject.is_team_unit ? <Icon.Shield size={15} /> : <Icon.Players size={15} />}
        </span>
        <div style={{ minWidth: 0 }}>
          <h3 className="truncate">
            {subject.player_id ? (
              <Link to={`/players/${encodeURIComponent(subject.player_id)}`} className="accent">
                {subject.name}
              </Link>
            ) : subject.name}
          </h3>
          {subject.is_team_unit && <div className="tiny muted">team unit · not a player page</div>}
        </div>
      </div>
      <div className="card-pad col" style={{ gap: 12 }}>
        {markets.map((m) => (
          <div key={m.market_key} className="col" style={{ gap: 5 }}>
            <div className="eyebrow">{marketLabel(m.market_key)}</div>
            {m.lines.map((ln) => (
              <div key={String(ln.line)} className="prop-line">
                {ln.line != null && <span className="ln num">{ln.line}</span>}
                <div className="prop-books">
                  {ln.books.map((b) => (
                    <span key={b.bookmaker} className="prop-book" title={b.bookmaker}>
                      <span className="bk">{b.bookmaker.slice(0, 2)}</span>
                      {b.over && <span className="num">O {american(b.over.price_american)}</span>}
                      {b.under && <span className="num muted">U {american(b.under.price_american)}</span>}
                      {b.yes && <span className="num">{american(b.yes.price_american)}</span>}
                    </span>
                  ))}
                </div>
              </div>
            ))}
          </div>
        ))}
      </div>
    </Card>
  );
}
