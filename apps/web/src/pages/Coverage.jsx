/* ── Data coverage ────────────────────────────────────────────────────────────
   Every number on this page is counted live by the engine. Hard-coding them into
   the UI would let them drift the moment an ingest runs; counting them means the
   page can only ever claim what is really in the database.

   The caveats below are not fine print — they are the difference between a number
   being usable and being misleading, and they travel with the data everywhere else
   in the app.
── */

import React from 'react';
import Icon from '../icons';
import * as api from '../lib/api';
import { useApi } from '../lib/hooks';
import { int, relativeTime } from '../lib/format';
import { Badge, Card, CardHead, ErrorState, Loading, Notice, Section, StatTile } from '../components/ui';

const GROUPS = [
  { label: 'Play-by-play', icon: Icon.Football, keys: [
    ['nfl_plays', 'NFL plays', 'EPA, WPA, success, air yards, dropback, location'],
    ['ncaaf_plays', 'NCAAF plays', "CFBD's PPA in the epa column — a different scale"],
    ['games', 'Games', 'NFL 2023–26, NCAAF 2016–26, incl. postseason'],
  ] },
  { label: 'Player data', icon: Icon.Players, keys: [
    ['pff_rows', 'Charting rows', 'weekly + season, 100% game-linked'],
    ['player_game_stats', 'Game logs', 'both leagues, official weekly aggregates'],
    ['nfl_players', 'NFL players', 'nflverse gsis ids'],
    ['ncaaf_players', 'NCAAF players', 'CFBD / ESPN athlete ids'],
    ['career_links', 'Career links', 'college ↔ pro, exact by ESPN id'],
  ] },
  { label: 'Market', icon: Icon.Odds, keys: [
    ['odds_snapshots', 'Odds snapshots', 'implied and de-vigged fair probability'],
    ['bookmakers', 'Bookmakers', 'live books plus historical archives'],
  ] },
  { label: 'Context', icon: Icon.Whistle, keys: [
    ['coaches', 'Coaches', 'tracked by coach, not by school'],
    ['transfers', 'Portal entries', 'NULL before 2021, which is not zero'],
    ['venues', 'Venues', 'incl. elevation'],
    ['ncaaf_fbs_teams', 'FBS teams', 'ranks are computed within FBS only'],
  ] },
];

const CAVEATS = [
  ['On/off is correlational', 'Stars rarely sit, so "off" samples are small and confounded. Deltas are evidence, not verdicts.'],
  ['Unit cards are not opponent-adjusted', 'Honest at the top-five and bottom-five grain; adjacent ranks are noise.'],
  ['Opponent splits are tiny samples', 'Five or six games for divisional foes, one or two for everyone else.'],
  ['An alignment label is not an alignment rate', 'NGS gives a categorical label; the charting layer gives a measured percentage. Prefer the measurement. Historical targets inherit a player\'s current label.'],
  ['Pressure rate is derived here', "Pressures divided by pass-block snaps. It is not a standard published efficiency metric and is never presented as one."],
  ['Never mix leagues in one aggregate', "NCAAF's epa column holds CFBD's PPA, which averages 0.178 against the NFL's −0.004."],
  ['Weather is NFL-only', "CFBD's weather endpoint is paywalled. A null temperature means not reported — never indoors or calm."],
  ['NCAAF plays carry no player ids', 'CFBD\'s REST endpoints omit them, so college is game-markets-first until Phase 2.'],
  ['Scrambles count as runs', 'nflverse convention, and it shows up in pass-rate tendencies.'],
  ['College charting is refused, not missing', 'The source uses one player id per human across college and the pros, so a drafted player\'s college games would land as NFL production. Ingestion is deliberately blocked until a college crosswalk exists.'],
];

export default function Coverage() {
  const { data, loading, error, refetch } = useApi(
    'coverage', (s) => api.getCoverage({ signal: s }), { ttl: 3e5 });

  if (loading) return <Loading rows={4} height={110} />;
  if (error) return <ErrorState error={error} onRetry={refetch} />;

  const c = data.counts;
  const built = (data.capabilities || []).filter((x) => x.available);
  const pending = (data.capabilities || []).filter((x) => !x.available);

  return (
    <>
      <div className="page-head">
        <div>
          <h1>Data coverage</h1>
          <div className="sub">Counted live from the database, not written into this page.</div>
        </div>
        <div className="spacer" />
        <button className="icon-btn" onClick={refetch} title="Recount"><Icon.Refresh size={16} /></button>
      </div>

      {GROUPS.map((g) => (
        <Section key={g.label} title={g.label}>
          <div className="grid grid-stat stagger">
            {g.keys.map(([key, label, sub]) => (
              <StatTile key={key} label={label} value={int(c[key])} sub={sub} />
            ))}
          </div>
        </Section>
      ))}

      {c.odds_last_captured && (
        <Notice icon={Icon.Clock}>
          Odds were last polled <strong>{relativeTime(c.odds_last_captured)}</strong>. Run{' '}
          <code className="num">make poll-odds</code> to refresh the board.
        </Notice>
      )}

      <Section title="Capabilities" sub="What answers a question today, and what is waiting on a phase.">
        <div className="grid" style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 1fr))' }}>
          <Card>
            <CardHead title="Live" sub={`${built.length} surfaces`} icon={Icon.Check} />
            <div className="card-pad col" style={{ gap: 12 }}>
              {built.map((x) => (
                <div key={x.id} className="col" style={{ gap: 3 }}>
                  <span className="row" style={{ gap: 7 }}>
                    <span className="good" style={{ display: 'grid' }}><Icon.Check size={14} /></span>
                    <strong style={{ fontSize: 13 }}>{x.label}</strong>
                  </span>
                  <span className="small muted" style={{ paddingLeft: 21, lineHeight: 1.5 }}>{x.detail}</span>
                </div>
              ))}
            </div>
          </Card>

          <Card>
            <CardHead title="Not built yet" sub={`${pending.length} surfaces`} icon={Icon.Lock} />
            <div className="card-pad col" style={{ gap: 12 }}>
              {pending.map((x) => (
                <div key={x.id} className="col" style={{ gap: 3 }}>
                  <span className="row" style={{ gap: 7 }}>
                    <span className="muted" style={{ display: 'grid' }}><Icon.Lock size={14} /></span>
                    <strong style={{ fontSize: 13 }}>{x.label}</strong>
                  </span>
                  <span className="small muted" style={{ paddingLeft: 21, lineHeight: 1.5 }}>{x.detail}</span>
                </div>
              ))}
            </div>
          </Card>
        </div>
      </Section>

      <Section title="Caveats that travel with the data"
        sub="These are load-bearing. A number read without them is a number read wrong.">
        <Card>
          <div className="card-pad col" style={{ gap: 14 }}>
            {CAVEATS.map(([title, body]) => (
              <div key={title} className="col" style={{ gap: 3 }}>
                <span className="row" style={{ gap: 7 }}>
                  <span className="warn" style={{ display: 'grid' }}><Icon.Info size={14} /></span>
                  <strong style={{ fontSize: 13 }}>{title}</strong>
                </span>
                <span className="small muted" style={{ paddingLeft: 21, lineHeight: 1.55 }}>{body}</span>
              </div>
            ))}
          </div>
        </Card>
      </Section>
    </>
  );
}
