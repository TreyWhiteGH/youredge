"""Parlay builder for combining multiple picks."""

import logging
from dataclasses import dataclass, field, asdict
from typing import List, Dict, Optional, Tuple
import uuid

logger = logging.getLogger(__name__)


@dataclass
class Pick:
    """Single betting pick."""
    pick_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    game_id: str = ""
    sport: str = "nba"
    bet_type: str = ""  # 'spread', 'moneyline', 'total'
    selection: str = ""  # 'home', 'away', 'over', 'under'
    line: float = 0.0
    odds: int = -110  # American odds
    confidence: float = 0.0  # 0-1
    edge: float = 0.0  # Expected value
    rationale: str = ""
    home_team: str = ""
    away_team: str = ""

    def to_dict(self) -> Dict:
        """Convert to dictionary."""
        return asdict(self)

    def to_json(self) -> Dict:
        """Convert to JSON-compatible format."""
        return self.to_dict()


@dataclass
class Parlay:
    """Parlay combining multiple picks."""
    parlay_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    picks: List[Pick] = field(default_factory=list)
    parlay_type: str = "standard"  # 'standard' or 'same_game'
    combined_odds: int = 0
    individual_edges: List[float] = field(default_factory=list)
    total_edge: float = 0.0
    correlation_factor: float = 0.0  # Adjustment for correlated picks
    adjusted_edge: float = 0.0  # Edge after correlation adjustment
    confidence: float = 0.0
    risk_level: str = "medium"  # 'low', 'medium', 'high'
    reasoning: str = ""
    correlation_warning: Optional[str] = None
    game_ids: List[str] = field(default_factory=list)
    num_legs: int = 0

    def to_dict(self) -> Dict:
        """Convert to dictionary."""
        d = asdict(self)
        d['picks'] = [p.to_dict() for p in self.picks]
        return d

    def to_json(self) -> Dict:
        """Convert to JSON-compatible format."""
        return self.to_dict()


class ParlayBuilder:
    """Builder for constructing parlays from picks."""

    # Correlation factors between different bet types
    KNOWN_CORRELATIONS = {
        ('spread', 'total'): 0.25,  # Blowouts often go under
        ('moneyline', 'spread'): 0.40,  # Very correlated
        ('spread', 'moneyline'): 0.40,
    }

    # Risk level thresholds
    RISK_THRESHOLDS = {
        'low': (0.65, 0.10),  # (min_avg_confidence, max_correlation)
        'medium': (0.55, 0.25),
        'high': (0.45, 0.50),
    }

    def __init__(self):
        """Initialize builder."""
        self.logger = logger

    def build_standard_parlay(self, picks: List[Pick], max_legs: int = 5,
                             min_confidence: float = 0.55,
                             min_edge: float = 0.03) -> Optional[Parlay]:
        """Build a standard parlay from multiple game picks.

        Args:
            picks: List of Pick objects from different games
            max_legs: Maximum number of legs in parlay
            min_confidence: Minimum average confidence threshold
            min_edge: Minimum edge threshold

        Returns:
            Parlay object or None if validation fails
        """
        # Validate inputs
        if len(picks) < 2:
            self.logger.warning("Cannot create parlay with less than 2 picks")
            return None

        if len(picks) > max_legs:
            self.logger.warning(f"Too many legs ({len(picks)} > {max_legs}), keeping top {max_legs}")
            picks = sorted(picks, key=lambda p: p.edge, reverse=True)[:max_legs]

        # Check for duplicate games (not allowed in standard parlay)
        game_ids = set(p.game_id for p in picks)
        if len(game_ids) != len(picks):
            self.logger.warning("Duplicate games in parlay, filtering duplicates")
            picks_dedup = []
            seen = set()
            for pick in picks:
                if pick.game_id not in seen:
                    picks_dedup.append(pick)
                    seen.add(pick.game_id)
            picks = picks_dedup

        # Validate minimum requirements
        avg_confidence = sum(p.confidence for p in picks) / len(picks)
        if avg_confidence < min_confidence:
            self.logger.warning(f"Average confidence {avg_confidence:.2f} below minimum {min_confidence}")
            return None

        avg_edge = sum(p.edge for p in picks) / len(picks)
        if avg_edge < min_edge:
            self.logger.warning(f"Average edge {avg_edge:.2f} below minimum {min_edge}")
            return None

        # Calculate combined odds
        combined_odds = self._calculate_combined_odds([p.odds for p in picks])

        # Detect correlations
        correlation_factor, correlation_warning = self._detect_correlations(picks)

        # Calculate edge
        individual_edges = [p.edge for p in picks]
        total_edge = sum(individual_edges) / len(picks)  # Average edge
        adjusted_edge = total_edge * (1 - correlation_factor)

        # Determine risk level
        risk_level = self._calculate_risk_level(avg_confidence, correlation_factor)

        # Generate reasoning
        reasoning = self._generate_parlay_reasoning(picks, len(picks), adjusted_edge)

        # Create parlay
        parlay = Parlay(
            picks=picks,
            parlay_type='standard',
            combined_odds=combined_odds,
            individual_edges=individual_edges,
            total_edge=total_edge,
            correlation_factor=correlation_factor,
            adjusted_edge=adjusted_edge,
            confidence=avg_confidence,
            risk_level=risk_level,
            reasoning=reasoning,
            correlation_warning=correlation_warning,
            game_ids=list(game_ids),
            num_legs=len(picks),
        )

        return parlay

    def build_same_game_parlay(self, game_id: str, picks: List[Pick],
                              min_confidence: float = 0.55) -> Optional[Parlay]:
        """Build a same-game parlay from multiple picks on one game.

        Args:
            game_id: Game ID
            picks: List of Pick objects for the same game
            min_confidence: Minimum average confidence threshold

        Returns:
            Parlay object or None if validation fails
        """
        # Validate all picks are for same game
        if not all(p.game_id == game_id for p in picks):
            self.logger.warning("Not all picks are for the same game")
            return None

        if len(picks) < 2:
            self.logger.warning("Cannot create same-game parlay with less than 2 picks")
            return None

        # Validate minimum requirements
        avg_confidence = sum(p.confidence for p in picks) / len(picks)
        if avg_confidence < min_confidence:
            self.logger.warning(f"Average confidence {avg_confidence:.2f} below minimum {min_confidence}")
            return None

        # Calculate combined odds
        combined_odds = self._calculate_combined_odds([p.odds for p in picks])

        # Detect correlations (more important for SGP)
        correlation_factor, correlation_warning = self._detect_correlations(picks)

        # Apply correlation penalty to SGP more aggressively
        correlation_factor *= 1.5  # SGPs more correlated than standard parlays

        # Calculate edge
        individual_edges = [p.edge for p in picks]
        total_edge = sum(individual_edges) / len(picks)
        adjusted_edge = total_edge * (1 - correlation_factor)

        # Determine risk level
        risk_level = self._calculate_risk_level(avg_confidence, correlation_factor)

        # Generate reasoning for SGP
        reasoning = self._generate_sgp_reasoning(picks, game_id)

        # Create parlay
        parlay = Parlay(
            picks=picks,
            parlay_type='same_game',
            combined_odds=combined_odds,
            individual_edges=individual_edges,
            total_edge=total_edge,
            correlation_factor=correlation_factor,
            adjusted_edge=adjusted_edge,
            confidence=avg_confidence,
            risk_level=risk_level,
            reasoning=reasoning,
            correlation_warning=correlation_warning,
            game_ids=[game_id],
            num_legs=len(picks),
        )

        return parlay

    def _calculate_combined_odds(self, odds_list: List[int]) -> int:
        """Calculate combined American odds for parlay.

        Args:
            odds_list: List of American odds

        Returns:
            Combined American odds
        """
        # Convert American to decimal
        decimals = [self._american_to_decimal(o) for o in odds_list]

        # Multiply decimals
        combined_decimal = 1
        for d in decimals:
            combined_decimal *= d

        # Convert back to American
        combined_american = self._decimal_to_american(combined_decimal)
        return int(combined_american)

    def _american_to_decimal(self, american_odds: int) -> float:
        """Convert American odds to decimal.

        Args:
            american_odds: American odds (e.g., -110, +150)

        Returns:
            Decimal odds
        """
        if american_odds > 0:
            return (american_odds + 100) / 100
        else:
            return (100 / abs(american_odds)) + 1

    def _decimal_to_american(self, decimal_odds: float) -> float:
        """Convert decimal odds to American.

        Args:
            decimal_odds: Decimal odds

        Returns:
            American odds
        """
        if decimal_odds >= 2.0:
            return (decimal_odds - 1) * 100
        else:
            return -100 / (decimal_odds - 1)

    def _detect_correlations(self, picks: List[Pick]) -> Tuple[float, Optional[str]]:
        """Detect correlated picks in parlay.

        Args:
            picks: List of picks to check

        Returns:
            Tuple of (correlation_factor, warning_message)
        """
        correlation_factor = 0.0
        warnings = []

        # Check for same market on different sides (highly correlated)
        markets_by_type = {}
        for pick in picks:
            market_key = (pick.game_id, pick.bet_type)
            if market_key in markets_by_type:
                warnings.append(f"Multiple bets on {pick.bet_type} in same game")
            markets_by_type[market_key] = pick

        # Check known correlations
        for i, pick1 in enumerate(picks):
            for pick2 in picks[i+1:]:
                if pick1.game_id == pick2.game_id:
                    # Same game - likely correlated
                    corr_key = (pick1.bet_type, pick2.bet_type)
                    if corr_key in self.KNOWN_CORRELATIONS:
                        correlation_factor += self.KNOWN_CORRELATIONS[corr_key]
                    elif (pick2.bet_type, pick1.bet_type) in self.KNOWN_CORRELATIONS:
                        correlation_factor += self.KNOWN_CORRELATIONS[(pick2.bet_type, pick1.bet_type)]
                    else:
                        # Different games
                        correlation_factor += 0.05  # Small correlation for reducing variance

        # Normalize correlation factor
        max_correlations = len(picks) * (len(picks) - 1) / 2
        if max_correlations > 0:
            correlation_factor = min(correlation_factor / max_correlations, 1.0)

        warning_message = None
        if warnings and correlation_factor > 0.2:
            warning_message = "; ".join(warnings) + f". Correlation factor: {correlation_factor:.2f}"

        return correlation_factor, warning_message

    def _calculate_risk_level(self, confidence: float, correlation: float) -> str:
        """Calculate risk level for parlay.

        Args:
            confidence: Average confidence of picks
            correlation: Correlation factor

        Returns:
            Risk level ('low', 'medium', 'high')
        """
        # Check thresholds
        if confidence >= self.RISK_THRESHOLDS['low'][0] and correlation <= self.RISK_THRESHOLDS['low'][1]:
            return 'low'
        elif confidence >= self.RISK_THRESHOLDS['medium'][0] and correlation <= self.RISK_THRESHOLDS['medium'][1]:
            return 'medium'
        else:
            return 'high'

    def _generate_parlay_reasoning(self, picks: List[Pick], num_legs: int,
                                  edge: float) -> str:
        """Generate reasoning for standard parlay.

        Args:
            picks: List of picks
            num_legs: Number of legs
            edge: Adjusted edge

        Returns:
            Reasoning string
        """
        teams = set()
        for pick in picks:
            if pick.home_team:
                teams.add(pick.home_team)
            if pick.away_team:
                teams.add(pick.away_team)

        team_str = ", ".join(sorted(list(teams))[:3])
        if len(teams) > 3:
            team_str += f" and {len(teams)-3} others"

        edge_pct = edge * 100
        return (f"{num_legs}-leg parlay featuring {team_str}. "
                f"Average confidence: {sum(p.confidence for p in picks)/len(picks):.1%}. "
                f"Projected edge: +{edge_pct:.1f}% at -110 odds.")

    def _generate_sgp_reasoning(self, picks: List[Pick], game_id: str) -> str:
        """Generate reasoning for same-game parlay.

        Args:
            picks: List of picks for same game
            game_id: Game ID

        Returns:
            Reasoning string
        """
        # Get game info from first pick
        first_pick = picks[0]
        matchup = f"{first_pick.away_team}@{first_pick.home_team}"

        # Describe the scenario
        descriptions = []
        for pick in picks:
            if pick.bet_type == 'spread':
                team = pick.home_team if pick.selection == 'home' else pick.away_team
                descriptions.append(f"{team} covers the spread")
            elif pick.bet_type == 'total':
                descriptions.append(f"Total goes {'over' if pick.selection == 'over' else 'under'}")
            elif pick.bet_type == 'moneyline':
                team = pick.home_team if pick.selection == 'home' else pick.away_team
                descriptions.append(f"{team} wins")

        scenario = " AND ".join(descriptions)
        avg_confidence = sum(p.confidence for p in picks) / len(picks)

        return (f"{matchup} same-game parlay: {scenario}. "
                f"Confidence: {avg_confidence:.1%}.")


class CorrelationDetector:
    """Detects and manages correlation between picks."""

    CORRELATION_MATRIX = {
        # (home_spread, away_spread) - same game, opposite sides
        ('spread_home', 'spread_away'): 0.95,
        # (spread, total) - same game
        ('spread', 'total'): 0.30,
        # (moneyline, spread) - same game
        ('moneyline', 'spread'): 0.50,
        # Different games - minimal correlation
        ('different_game', 'different_game'): 0.02,
    }

    @staticmethod
    def get_correlation(pick1: Pick, pick2: Pick) -> float:
        """Get correlation between two picks.

        Args:
            pick1: First pick
            pick2: Second pick

        Returns:
            Correlation factor (0-1)
        """
        if pick1.game_id == pick2.game_id:
            # Same game - check bet type
            if pick1.bet_type == 'spread' and pick2.bet_type == 'spread':
                # Same game spread on different sides
                if pick1.selection != pick2.selection:
                    return 0.95
                else:
                    return 1.0
            elif (pick1.bet_type, pick2.bet_type) in CorrelationDetector.CORRELATION_MATRIX:
                return CorrelationDetector.CORRELATION_MATRIX[(pick1.bet_type, pick2.bet_type)]
            else:
                # Different bet types, same game
                return 0.25
        else:
            # Different games
            return 0.02
