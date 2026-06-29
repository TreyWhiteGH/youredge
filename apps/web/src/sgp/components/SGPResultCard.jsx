import React, { useState } from 'react';
import {
  RecommendationBadge, CorrelationBadge, RiskBadge, GradeBadge,
  ScoreBar, LegPill, PriceRow, SectionLabel, Card, GhostButton, Divider,
  ManualSGPPriceInput, NoBetCard,
} from './shared';

export default function SGPResultCard({ result, onSave, onCritique, onVariant }) {
  const [manualPrice, setManualPrice] = useState('');
  const [copied, setCopied] = useState(false);
  if (!result) return null;
  const { best_sgp, game, sgp_price_required } = result;

  const handleCopy = () => {
    const text = best_sgp.legs.map(l => l.selection).join(' + ') + ` @ ${best_sgp.sportsbook_price}`;
    navigator.clipboard.writeText(text).catch(() => {});
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
      {/* Header */}
      <Card className="p-5">
        <div className="flex items-start justify-between mb-4">
          <div>
            <div className="text-xs font-semibold uppercase tracking-widest mb-1" style={{ color: 'var(--text-muted)' }}>Best SGP · {game}</div>
            <div className="flex items-center gap-3 flex-wrap">
              <GradeBadge grade={best_sgp.grade} />
              <RecommendationBadge recommendation={best_sgp.recommendation} />
            </div>
          </div>
          <CorrelationBadge type={best_sgp.correlation_type} />
        </div>

        <div className="rounded-lg p-3 mb-4" style={{ background: 'var(--bg-subtle)', border: '1px solid var(--border)' }}>
          <div className="text-xs mb-1" style={{ color: 'var(--text-muted)' }}>Detected Script</div>
          <p className="text-sm" style={{ color: 'var(--text-primary)' }}>{best_sgp.detected_script || best_sgp.thesis}</p>
        </div>

        <SectionLabel>Legs</SectionLabel>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8, marginBottom: 16 }}>
          {best_sgp.legs.map((leg, i) => (
            <LegPill key={i} selection={leg.selection} market={leg.market} modelProb={leg.model_probability} odds={leg.odds_american} />
          ))}
        </div>

        {sgp_price_required && (
          <div style={{ marginBottom: 16 }}>
            <ManualSGPPriceInput value={manualPrice} onChange={setManualPrice} />
          </div>
        )}
      </Card>

      {best_sgp.recommendation === 'No bet at this price' && (
        <NoBetCard bestLean={best_sgp.legs.map(l => l.selection).join(' + ')} needed={best_sgp.minimum_playable_price} current={best_sgp.sportsbook_price} />
      )}

      {best_sgp.recommendation !== 'No bet at this price' && (
        <Card className="p-5">
          <SectionLabel>Price Analysis</SectionLabel>
          <PriceRow label="Sportsbook Price" value={best_sgp.sportsbook_price} />
          <PriceRow label="YourEdge Fair Price" value={best_sgp.fair_price} />
          <PriceRow label="Minimum Playable Price" value={best_sgp.minimum_playable_price} accent />
          {best_sgp.estimated_edge !== undefined && (
            <div className="flex justify-between items-center py-2.5">
              <span className="text-sm" style={{ color: 'var(--text-muted)' }}>Estimated Edge</span>
              <span className="text-sm font-bold text-emerald-500">+{(best_sgp.estimated_edge * 100).toFixed(1)}%</span>
            </div>
          )}
        </Card>
      )}

      <Card className="p-5">
        <SectionLabel>Analysis Scores</SectionLabel>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
          <ScoreBar label="Script Confidence" value={best_sgp.script_confidence} />
          <ScoreBar label="Leg Fit" value={best_sgp.leg_fit_score} />
          <ScoreBar label="Price Score" value={best_sgp.price_score} />
        </div>
        <Divider />
        <div className="flex items-center gap-2">
          <span className="text-xs" style={{ color: 'var(--text-muted)' }}>Risk Level</span>
          <RiskBadge level={best_sgp.risk_level} />
        </div>
      </Card>

      <Card className="p-5">
        <SectionLabel>Main Risk</SectionLabel>
        <p className="text-sm leading-relaxed" style={{ color: 'var(--text-secondary)' }}>{best_sgp.main_risk}</p>
      </Card>

      <div className="flex flex-wrap gap-2">
        <GhostButton onClick={onSave}>Save SGP</GhostButton>
        <GhostButton onClick={handleCopy}>{copied ? 'Copied!' : 'Copy Pick'}</GhostButton>
        <GhostButton onClick={onCritique}>Critique This SGP</GhostButton>
        <GhostButton onClick={() => onVariant('cleaner')}>Try Cleaner Version</GhostButton>
        <GhostButton onClick={() => onVariant('aggressive')}>Try Aggressive Version</GhostButton>
      </div>
    </div>
  );
}
