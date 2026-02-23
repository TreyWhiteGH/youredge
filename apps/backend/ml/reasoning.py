"""Generates detailed reasoning for picks and parlays."""

import logging
from typing import Dict, List, Optional
from dataclasses import dataclass, asdict

logger = logging.getLogger(__name__)


@dataclass
class PickReasoning:
    """Detailed reasoning for a pick."""
    summary: str  # 1-sentence why
    key_factors: List[str]  # Top 3-5 factors
    stats_support: Dict  # Supporting statistics
    risks: List[str]  # What could go wrong
    user_alignment: Optional[str] = None  # How pick aligns with user prompt


class ReasoningGenerator:
    """Generates detailed reasoning for picks."""

    # Situational factor probabilities
    SITUATIONAL_FACTORS = {
        'back_to_back': {
            'description': 'Back-to-back games',
            'impact': -0.02,  # Negative impact on away team
            'cover_pct': 42,
        },
        'rest_advantage': {
            'description': 'Home team has 2+ day rest advantage',
            'impact': 0.03,  # Positive impact
            'cover_pct': 52,
        },
        'home_court': {
            'description': 'Home court advantage',
            'impact': 0.02,
            'cover_pct': 50,
        },
        'key_injury': {
            'description': 'Key player(s) out',
            'impact': -0.03,
            'cover_pct': 45,
        },
        'line_movement': {
            'description': 'Sharp money movement',
            'impact': 0.01,
            'cover_pct': 48,
        },
    }

    def __init__(self):
        """Initialize generator."""
        self.logger = logger

    def generate_reasoning(self, pick, features: Dict, model_importance: Optional[Dict] = None,
                          user_prompt: Optional[str] = None,
                          user_scenario: Optional[str] = None) -> PickReasoning:
        """Generate comprehensive pick reasoning.

        Args:
            pick: Pick object
            features: NBAGameFeatures as dictionary
            model_importance: Feature importance from ML model
            user_prompt: Original user prompt
            user_scenario: Scenario type from prompt interpretation

        Returns:
            PickReasoning object
        """
        # Generate different layers of reasoning
        summary = self._generate_summary(pick, features, user_scenario)
        key_factors = self._identify_key_factors(pick, features, model_importance)
        stats_support = self._gather_stats_support(pick, features)
        risks = self._identify_risks(pick, features)
        user_alignment = self._align_with_user(pick, user_prompt, user_scenario) if user_prompt else None

        return PickReasoning(
            summary=summary,
            key_factors=key_factors,
            stats_support=stats_support,
            risks=risks,
            user_alignment=user_alignment,
        )

    def _generate_summary(self, pick, features: Dict,
                         scenario: Optional[str] = None) -> str:
        """Generate 1-sentence summary.

        Args:
            pick: Pick object
            features: Feature dictionary
            scenario: User scenario if applicable

        Returns:
            Summary string
        """
        home = pick.home_team
        away = pick.away_team
        team = home if pick.selection == 'home' else away

        if pick.bet_type == 'spread':
            verb = 'covers'
            if scenario == 'tight_game':
                return f"{team} in a tightly contested matchup with solid fundamentals."
            elif scenario == 'blowout':
                return f"{team} dominates with expected blowout potential."
            else:
                return f"{team} {verb} the spread with {pick.confidence:.1%} confidence."

        elif pick.bet_type == 'total':
            direction = 'over' if pick.selection == 'over' else 'under'
            return f"Game goes {direction} {pick.line} based on pace, efficiency, and recent trends."

        elif pick.bet_type == 'moneyline':
            return f"{team} wins outright with {pick.confidence:.1%} confidence."

        return f"Pick recommendation with {pick.confidence:.1%} confidence."

    def _identify_key_factors(self, pick, features: Dict,
                             model_importance: Optional[Dict] = None) -> List[str]:
        """Identify 3-5 key factors supporting the pick.

        Args:
            pick: Pick object
            features: Feature dictionary
            model_importance: XGBoost feature importances

        Returns:
            List of key factor strings
        """
        factors = []

        # Model-based factors (if available)
        if model_importance:
            top_features = sorted(model_importance.items(), key=lambda x: x[1], reverse=True)[:3]
            for feat_name, importance in top_features:
                feat_value = features.get(feat_name)
                if feat_value is not None:
                    # Format the value nicely
                    if isinstance(feat_value, (int, float)):
                        if 'pct' in feat_name:
                            formatted = f"{feat_value:.1%}"
                        elif 'avg' in feat_name or 'rating' in feat_name:
                            formatted = f"{feat_value:.1f}"
                        else:
                            formatted = f"{feat_value:.1f}"
                    else:
                        formatted = str(feat_value)

                    factors.append(f"{feat_name.replace('_', ' ').title()}: {formatted}")

        # Statistical factors
        home = pick.home_team
        away = pick.away_team

        if pick.selection == 'home':
            home_pts_avg = features.get('home_pts_avg', 0)
            away_pts_allowed = features.get('away_pts_allowed_avg', 0)
            factors.append(f"{home} averaging {home_pts_avg:.1f} PPG vs {away} defense allowing {away_pts_allowed:.1f}")

        # Situational factors
        if features.get('home_back_to_back') and pick.selection == 'away':
            factors.append(f"{away} benefits from {home} back-to-back fatigue")

        if features.get('home_rest_days', 0) > features.get('away_rest_days', 0) + 1 and pick.selection == 'home':
            factors.append(f"{home} has rest advantage ({features['home_rest_days']} days vs {features['away_rest_days']} days)")

        # Lineup/Health
        if features.get('home_key_players_out', 0) > 0 and pick.selection == 'away':
            factors.append(f"{home} missing key player(s)")

        # Market movement
        line_movement = features.get('line_movement', 0)
        if abs(line_movement) > 2:
            direction = 'moving in pick\'s favor' if line_movement > 0 else 'moving against pick'
            factors.append(f"Line {direction} ({line_movement:+.1f} points)")

        return factors[:5]  # Return top 5

    def _gather_stats_support(self, pick, features: Dict) -> Dict:
        """Gather supporting statistics for the pick.

        Args:
            pick: Pick object
            features: Feature dictionary

        Returns:
            Dictionary of supporting stats
        """
        stats = {}

        home = pick.home_team
        away = pick.away_team

        # Team performance stats
        if pick.selection == 'home':
            stats[f'{home}_scoring'] = features.get('home_pts_avg', 0)
            stats[f'{away}_defense'] = features.get('away_pts_allowed_avg', 0)
            stats[f'{home}_fg_pct'] = f"{features.get('home_fg_pct', 0):.1%}"
            stats[f'{home}_win_pct'] = f"{features.get('home_win_pct', 0):.1%}"

        elif pick.selection == 'away':
            stats[f'{away}_scoring'] = features.get('away_pts_avg', 0)
            stats[f'{home}_defense'] = features.get('home_pts_allowed_avg', 0)
            stats[f'{away}_fg_pct'] = f"{features.get('away_fg_pct', 0):.1%}"
            stats[f'{away}_win_pct'] = f"{features.get('away_win_pct', 0):.1%}"

        # Head-to-head if available
        h2h_wins = features.get('h2h_home_wins_last_5', 0) if pick.selection == 'home' else features.get('h2h_away_wins_last_5', 0)
        if h2h_wins is not None:
            stats['h2h_recent_success'] = f"{h2h_wins}/5 recent meetings"

        # Market odds
        stats['line'] = f"{pick.line:+.1f}"
        stats['odds'] = f"{pick.odds:+d}"
        stats['confidence'] = f"{pick.confidence:.1%}"
        stats['edge'] = f"+{pick.edge:.1%}"

        return stats

    def _identify_risks(self, pick, features: Dict) -> List[str]:
        """Identify risks that could cause the pick to lose.

        Args:
            pick: Pick object
            features: Feature dictionary

        Returns:
            List of risk strings
        """
        risks = []

        # Personnel risks
        if features.get('home_key_players_out', 0) > 0 and pick.selection == 'home':
            risks.append(f"Key player(s) out for {pick.home_team} increases volatility")

        if features.get('away_key_players_out', 0) > 0 and pick.selection == 'away':
            risks.append(f"Injuries to {pick.away_team} could impact performance")

        # Schedule/Rest risks
        if features.get('home_back_to_back') and pick.selection == 'home':
            risks.append(f"{pick.home_team} on back-to-back (teams only cover 42% in this spot)")

        # Market risks
        line_movement = features.get('line_movement', 0)
        if line_movement > 2 and pick.line > line_movement:
            risks.append("Line has moved significantly against the pick (sharp money)")

        # Confidence risks
        if pick.confidence < 0.55:
            risks.append("Below 55% confidence level - higher variance expected")

        # Home court risks
        home_court_advantage = features.get('home_court_advantage', 0)
        if abs(home_court_advantage) > 0.15 and pick.selection == 'away':
            risks.append(f"Strong home court advantage ({home_court_advantage:+.1%}) could favor home team")

        return risks

    def _align_with_user(self, pick, user_prompt: str,
                        scenario: Optional[str] = None) -> Optional[str]:
        """Explain how pick aligns with user expectations.

        Args:
            pick: Pick object
            user_prompt: Original user prompt
            scenario: Scenario type from interpretation

        Returns:
            Alignment string or None
        """
        if not user_prompt or not scenario:
            return None

        scenario_descriptions = {
            'blowout': f"Aligns with your expectation of a blowout. {pick.home_team} dominates with high cover probability.",
            'high_scoring': f"Supports your high-scoring game prediction with {pick.away_team if pick.selection == 'under' else pick.home_team} scoring strength.",
            'low_scoring': f"Matches defensive battle expectation given both teams' defensive rankings.",
            'tight_game': f"Pick respects the close game nature while targeting small advantage.",
            'upset': f"Supports upset potential with {pick.away_team}'s recent performance and value.",
            'bounce_back': f"Aligns with bounce-back expectation for {pick.home_team}.",
        }

        alignment = scenario_descriptions.get(scenario, None)

        if alignment:
            return f"This pick aligns with your scenario: {alignment}"

        return None

    def generate_parlay_reasoning(self, picks: List, parlay, user_prompt: Optional[str] = None) -> str:
        """Generate reasoning for a parlay.

        Args:
            picks: List of picks in parlay
            parlay: Parlay object
            user_prompt: Original user prompt

        Returns:
            Parlay reasoning string
        """
        num_legs = len(picks)
        avg_confidence = sum(p.confidence for p in picks) / len(picks)
        avg_edge = parlay.total_edge

        picks_summary = []
        for pick in picks:
            if pick.bet_type == 'spread':
                picks_summary.append(f"{pick.home_team if pick.selection == 'home' else pick.away_team} spread")
            elif pick.bet_type == 'total':
                picks_summary.append(f"Total {pick.selection}")
            elif pick.bet_type == 'moneyline':
                picks_summary.append(f"{pick.home_team if pick.selection == 'home' else pick.away_team} ML")

        picks_str = " + ".join(picks_summary)

        reasoning = f"{num_legs}-leg parlay: {picks_str}. "
        reasoning += f"Average confidence: {avg_confidence:.1%}. "
        reasoning += f"Projected edge: +{avg_edge:.1%}."

        if parlay.correlation_warning:
            reasoning += f" ⚠️ {parlay.correlation_warning}"

        if user_prompt:
            reasoning += f" Based on your expectation: \"{user_prompt[:50]}...\""

        return reasoning
