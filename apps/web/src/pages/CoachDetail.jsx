/* ── Coach detail ─────────────────────────────────────────────────────────────
   A coach's full career across every school he has held. That framing is the
   whole point: a coach changing schools is a new row, not a new coach, so the
   signal travels with him — and the market prices that slowly.
── */

import React from 'react';
import { Link, useParams } from 'react-router-dom';
import Icon from '../icons';
import * as api from '../lib/api';
import { useApi } from '../lib/hooks';
import { useTrackVisit } from '../lib/store';
import { num, ordinal, pct, signed } from '../lib/format';
import { Badge, Card, CardHead, Empty, ErrorState, Loading, Notice, Sparkline, StatTile } from '../components/ui';

export default function CoachDetail() {
  const { coachId } = useParams();
  const c = useApi(`coachcareer:${coachId}`, (s) => api.getCoach(coachId, { signal: s }));

  useTrackVisit(c.data && {
    id: coachId, kind: 'coach', label: c.data.name,
    to: `/coaches/${encodeURIComponent(coachId)}`,
  });

  if (c.loading) return <Loading rows={3} height={100} />;
  if (c.error) return <ErrorState error={c.error} onRetry={c.refetch} />;

  const d = c.data;
  const seasons = d.seasons || [];
  const latest = seasons[seasons.length - 1];
  const schools = [...new Set(seasons.map((s) => s.school))];
  const totalW = seasons.reduce((a, s) => a + (s.wins || 0), 0);
  const totalL = seasons.reduce((a, s) => a + (s.losses || 0), 0);

  return (
    <>
      <div className="page-head">
        <div>
          <div className="eyebrow">NCAAF coach</div>
          <h1 style={{ marginTop: 4 }} className="row">
            <span className="accent" style={{ display: 'grid' }}><Icon.Whistle size={22} /></span>
            {d.name}
          </h1>
          <div className="sub">
            {schools.length} school{schools.length === 1 ? '' : 's'} · first season {d.first_season}
          </div>
        </div>
      </div>

      <div className="grid grid-stat stagger">
        <StatTile label="Record" value={`${totalW}–${totalL}`} sub="across every stint here" />
        <StatTile label="FBS seasons" value={d.history_seasons} sub="FCS stints are separate" />
        <StatTile label="Career SP+ residual" value={signed(latest?.career_sp_residual, 1)}
          sub="SP+ minus what his talent predicted" />
        <StatTile label="Trajectory" value={signed(latest?.trajectory, 1)} sub="prior school" />
      </div>

      {d.history_seasons != null && d.history_seasons < 4 && (
        <Notice tone="warn" icon={Icon.Alert}>
          Only {d.history_seasons} seasons of visible FBS history. <strong>Short history means
          uncertain</strong>, not average — the residual is a ranking signal here, not a
          calibrated projection.
        </Notice>
      )}

      {seasons.length === 0 ? (
        <Card><Empty icon={Icon.Whistle} title="No seasons recorded" /></Card>
      ) : (
        <Card>
          <CardHead title="Career" sub="One row per school-season" icon={Icon.Trophy}
            action={<Sparkline values={seasons.map((s) => s.sp_overall)} width={110} height={26} baseline={0} />} />
          <div className="table-scroll">
            <table className="data">
              <thead>
                <tr><th>Season</th><th>School</th><th>W–L</th><th>Win %</th>
                  <th>SP+</th><th>SP+ off</th><th>SP+ def</th><th>Tenure</th><th>Residual</th></tr>
              </thead>
              <tbody>
                {seasons.map((s) => (
                  <tr key={`${s.season}-${s.team_id}`}>
                    <td className="num" style={{ fontWeight: 650 }}>{s.season}</td>
                    <td>
                      <Link to={`/teams/ncaaf/${encodeURIComponent(s.team_id)}`} className="row"
                        style={{ gap: 6, justifyContent: 'flex-start' }}>
                        {s.school}
                        {s.is_first_year_at_school && <Badge tone="accent">arrived</Badge>}
                      </Link>
                    </td>
                    <td className="num">{s.wins ?? '—'}–{s.losses ?? '—'}</td>
                    <td className="num">{s.win_pct != null ? pct(s.win_pct, 0) : '—'}</td>
                    <td className="num">{num(s.sp_overall, 1)}</td>
                    <td className="num">{num(s.sp_offense, 1)}</td>
                    <td className="num">{num(s.sp_defense, 1)}</td>
                    <td className="num muted">{s.tenure_year ?? '—'}</td>
                    <td className="num" style={{ color: s.career_sp_residual > 0 ? 'var(--good)' : s.career_sp_residual < 0 ? 'var(--bad)' : undefined }}>
                      {signed(s.career_sp_residual, 1)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      )}

      <Notice>
        <strong>career_sp_residual</strong> is SP+ minus what that roster's recruited talent
        predicted, averaged over every prior season anywhere. It uses a simplified talent
        baseline — sound for ranking, not a calibrated projection. FCS success is kept as a
        separate feature and never blended in, because FCS has no SP+.
      </Notice>
    </>
  );
}
