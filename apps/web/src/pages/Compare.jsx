/* ── Compare ──────────────────────────────────────────────────────────────────
   Up to four teams as columns over the same rows. The value of this view is that
   every row is ranked in the same field, so a column is readable top to bottom
   without re-checking what each number means.
── */

import React from 'react';
import { Link } from 'react-router-dom';
import Icon from '../icons';
import * as api from '../lib/api';
import { useApi } from '../lib/hooks';
import { useApp } from '../lib/store';
import { num, ordinal, pct, rankPct, scaleColor, UNIT_LABEL } from '../lib/format';
import { Card, Empty, Notice } from '../components/ui';

/** Rows are declared once; each pulls from whichever payload holds it. */
const ROWS = [
  { group: 'Offense', label: 'Pass EPA / dropback', src: 'off', pick: (d) => d.pass_offense,
    fmt: (v) => num(v, 3), val: (u) => u?.epa },
  { group: 'Offense', label: 'Pass success', src: 'off', pick: (d) => d.pass_offense,
    fmt: pct, val: (u) => u?.success_rate, noRank: true },
  { group: 'Offense', label: 'Explosive pass', src: 'off', pick: (d) => d.pass_offense,
    fmt: pct, val: (u) => u?.explosive_rate, noRank: true },
  { group: 'Offense', label: 'Run EPA / rush', src: 'off', pick: (d) => d.run_offense,
    fmt: (v) => num(v, 3), val: (u) => u?.epa },
  { group: 'Offense', label: 'Run success', src: 'off', pick: (d) => d.run_offense,
    fmt: pct, val: (u) => u?.success_rate, noRank: true },
  { group: 'Offense', label: 'Late & close EPA', src: 'off', pick: (d) => d.situational,
    fmt: (v) => num(v, 3), val: (u) => u?.late_close_epa, rank: (u) => u?.late_close_rank },

  { group: 'Defense', label: 'Pass EPA allowed', src: 'def', pick: (d) => d.pass_defense,
    fmt: (v) => num(v, 3), val: (u) => u?.epa_allowed },
  { group: 'Defense', label: 'Pass success allowed', src: 'def', pick: (d) => d.pass_defense,
    fmt: pct, val: (u) => u?.success_rate_allowed, noRank: true },
  { group: 'Defense', label: 'Run EPA allowed', src: 'def', pick: (d) => d.run_defense,
    fmt: (v) => num(v, 3), val: (u) => u?.epa_allowed },
  { group: 'Defense', label: 'Explosive allowed', src: 'def', pick: (d) => d.pass_defense,
    fmt: pct, val: (u) => u?.explosive_rate_allowed, noRank: true },

  // Rank only — the client requests `detail=summary` for units, so no grade is fetched.
  ...['pass_blocking', 'run_blocking', 'pass_rush', 'run_defense', 'coverage', 'receiving']
    .map((k) => ({
      group: 'Unit grades', label: UNIT_LABEL[k] || k, src: 'units',
      pick: (d) => d.units?.[k], tierOnly: true, val: () => null,
    })),
];

export default function Compare() {
  const { compare, clearCompare, toggleCompare, league } = useApp();

  if (compare.length === 0) {
    return (
      <>
        <div className="page-head"><h1>Compare</h1></div>
        <Card><Empty
          icon={Icon.Compare}
          title="Nothing staged yet"
          body="Add teams from the Teams list or from any team page. Up to four fit side by side."
          action={<Link className="btn btn-primary btn-sm" to="/teams">Browse teams</Link>}
        /></Card>
      </>
    );
  }

  const groups = [...new Set(ROWS.map((r) => r.group))];

  return (
    <>
      <div className="page-head">
        <div>
          <h1>Compare</h1>
          <div className="sub">{compare.length} team{compare.length === 1 ? '' : 's'} · every row ranked in the same field</div>
        </div>
        <div className="spacer" />
        <button className="btn btn-sm" onClick={clearCompare}>
          <Icon.Close size={13} /> Clear
        </button>
      </div>

      {new Set(compare.map((c) => c.league)).size > 1 && (
        <Notice tone="warn" icon={Icon.Alert}>
          You are comparing across leagues. NCAAF's EPA column holds CFBD's PPA, which averages
          0.178 against the NFL's −0.004 — <strong>different measurements wearing the same
          name</strong>. Ranks are within each league; the raw values are not comparable.
        </Notice>
      )}

      <Card>
        <div className="table-scroll">
          <table className="data">
            <thead>
              <tr>
                <th style={{ minWidth: 180 }}>Metric</th>
                {compare.map((c) => (
                  <th key={c.id} style={{ minWidth: 130 }}>
                    <span className="row" style={{ justifyContent: 'flex-end', gap: 6 }}>
                      <Link to={c.to} className="accent">{c.label}</Link>
                      <button onClick={() => toggleCompare(c)} className="muted" aria-label={`Remove ${c.label}`}>
                        <Icon.Close size={12} />
                      </button>
                    </span>
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {groups.map((g) => (
                <React.Fragment key={g}>
                  <tr>
                    <td colSpan={compare.length + 1}
                      style={{ background: 'var(--bg-input)', paddingTop: 10, paddingBottom: 6 }}>
                      <span className="eyebrow">{g}</span>
                    </td>
                  </tr>
                  {ROWS.filter((r) => r.group === g).map((row) => (
                    <CompareRow key={`${g}-${row.label}`} row={row} teams={compare} />
                  ))}
                </React.Fragment>
              ))}
            </tbody>
          </table>
        </div>
      </Card>
    </>
  );
}

/** One metric across every staged team. Each cell fetches independently and caches. */
function CompareRow({ row, teams }) {
  return (
    <tr>
      <td style={{ fontWeight: 600 }}>{row.label}</td>
      {teams.map((t) => <CompareCell key={t.id} row={row} team={t} />)}
    </tr>
  );
}

function CompareCell({ row, team }) {
  const league = team.league || 'nfl';
  const fetcher = {
    off: (s) => api.getOffense(league, team.id, {}, { signal: s }),
    def: (s) => api.getDefense(league, team.id, {}, { signal: s }),
    units: (s) => api.getUnits(league, team.id, { season: 2025 }, { signal: s }),
  }[row.src];

  const key = { off: `off:${team.id}`, def: `def:${team.id}`, units: `units:${team.id}:2025` }[row.src];
  const { data, loading, error } = useApi(key, fetcher);

  if (loading) return <td><span className="skeleton" style={{ display: 'block', height: 14, width: 54, marginLeft: 'auto' }} /></td>;
  if (error || !data) return <td className="muted">—</td>;

  const unit = row.pick(data);
  const value = row.val(unit);
  const rank = row.noRank ? null : (row.rank ? row.rank(unit) : unit?.rank);
  const of = data.teams_ranked || unit?.teams_ranked;
  const p = rankPct(rank, of);

  if (row.tierOnly) {
    return (
      <td className="num">
        <span style={{ fontWeight: 650, color: scaleColor(p) }}>{ordinal(rank)}</span>
        <span className="tiny muted" style={{ marginLeft: 5 }}>of {of}</span>
      </td>
    );
  }

  return (
    <td className="num">
      <span style={{ fontWeight: 650 }}>{row.fmt(value)}</span>
      {rank ? (
        <span className="tiny" style={{ color: scaleColor(p), marginLeft: 6 }}>{ordinal(rank)}</span>
      ) : null}
    </td>
  );
}
