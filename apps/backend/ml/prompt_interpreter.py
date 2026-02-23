"""Interprets user prompts and maps them to betting scenarios."""

import logging
import re
from typing import Dict, List, Optional, Set
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class PromptInterpretation:
    """Result of prompt interpretation."""
    scenario: str
    scenario_description: str
    keywords: Set[str]
    constraints: Dict
    confidence_boost: float  # How much to trust user input vs model


class PromptInterpreter:
    """Interprets user prompts and generates betting constraints."""

    # Betting keywords and their implications
    KEYWORDS = {
        'dominate': {
            'implications': ['blowout', 'high_margin', 'high_spread'],
            'market_bias': 'spread',
            'selection_bias': 'home',
        },
        'dominates': {
            'implications': ['blowout', 'high_margin'],
            'market_bias': 'spread',
            'selection_bias': 'home',
        },
        'dominating': {
            'implications': ['blowout', 'high_margin'],
            'market_bias': 'spread',
            'selection_bias': 'home',
        },
        'high-scoring': {
            'implications': ['over', 'fast_pace', 'fast paced'],
            'market_bias': 'total',
            'selection_bias': 'over',
        },
        'high scoring': {
            'implications': ['over', 'fast_pace'],
            'market_bias': 'total',
            'selection_bias': 'over',
        },
        'low-scoring': {
            'implications': ['under', 'defense', 'defensive'],
            'market_bias': 'total',
            'selection_bias': 'under',
        },
        'low scoring': {
            'implications': ['under', 'defense'],
            'market_bias': 'total',
            'selection_bias': 'under',
        },
        'close game': {
            'implications': ['tight', 'small_spread'],
            'market_bias': 'spread',
            'selection_bias': None,
        },
        'close': {
            'implications': ['tight'],
            'market_bias': 'spread',
            'selection_bias': None,
        },
        'tight': {
            'implications': ['close', 'small_spread'],
            'market_bias': 'spread',
            'selection_bias': None,
        },
        'defense': {
            'implications': ['under', 'low_scoring'],
            'market_bias': 'total',
            'selection_bias': 'under',
        },
        'defensive': {
            'implications': ['under'],
            'market_bias': 'total',
            'selection_bias': 'under',
        },
        'offense': {
            'implications': ['over', 'high_scoring'],
            'market_bias': 'total',
            'selection_bias': 'over',
        },
        'offensive': {
            'implications': ['over'],
            'market_bias': 'total',
            'selection_bias': 'over',
        },
        'struggle': {
            'implications': ['under', 'fade_team'],
            'market_bias': 'total',
            'selection_bias': 'under',
        },
        'struggling': {
            'implications': ['under'],
            'market_bias': 'total',
            'selection_bias': 'under',
        },
        'blowout': {
            'implications': ['high_spread', 'high_margin'],
            'market_bias': 'spread',
            'selection_bias': None,
        },
        'bounce back': {
            'implications': ['cover'],
            'market_bias': 'spread',
            'selection_bias': 'home',
        },
        'comeback': {
            'implications': ['upset', 'close'],
            'market_bias': 'spread',
            'selection_bias': 'away',
        },
        'upset': {
            'implications': ['underdog', 'away_win'],
            'market_bias': 'moneyline',
            'selection_bias': 'away',
        },
        'underdog': {
            'implications': ['plus_money'],
            'market_bias': 'moneyline',
            'selection_bias': 'away',
        },
        'favorite': {
            'implications': ['minus_money'],
            'market_bias': 'moneyline',
            'selection_bias': 'home',
        },
        'homecourt': {
            'implications': ['home_advantage'],
            'market_bias': 'spread',
            'selection_bias': 'home',
        },
        'home court': {
            'implications': ['home_advantage'],
            'market_bias': 'spread',
            'selection_bias': 'home',
        },
        'road': {
            'implications': ['away_struggles'],
            'market_bias': 'spread',
            'selection_bias': 'home',
        },
        'momentum': {
            'implications': ['streak'],
            'market_bias': 'spread',
            'selection_bias': 'home',
        },
        'streak': {
            'implications': ['hot', 'cold'],
            'market_bias': 'spread',
            'selection_bias': 'home',
        },
        'rest': {
            'implications': ['rest_advantage', 'fresh'],
            'market_bias': 'spread',
            'selection_bias': 'home',
        },
        'tired': {
            'implications': ['fatigue', 'back_to_back'],
            'market_bias': 'spread',
            'selection_bias': 'away',
        },
        'back-to-back': {
            'implications': ['fatigue'],
            'market_bias': 'spread',
            'selection_bias': 'away',
        },
        'injury': {
            'implications': ['missing_player', 'weakened'],
            'market_bias': 'spread',
            'selection_bias': 'away',
        },
        'injured': {
            'implications': ['missing_player'],
            'market_bias': 'spread',
            'selection_bias': 'away',
        },
        'three-pointer': {
            'implications': ['perimeter_game', 'high_scoring'],
            'market_bias': 'total',
            'selection_bias': 'over',
        },
        'three point': {
            'implications': ['perimeter'],
            'market_bias': 'total',
            'selection_bias': 'over',
        },
        'rebounding': {
            'implications': ['paint_game', 'interior'],
            'market_bias': 'spread',
            'selection_bias': None,
        },
        'rebounds': {
            'implications': ['paint'],
            'market_bias': 'spread',
            'selection_bias': None,
        },
        'paint': {
            'implications': ['interior_game'],
            'market_bias': 'spread',
            'selection_bias': None,
        },
    }

    # Scenario templates
    SCENARIOS = {
        'blowout': {
            'description': 'Home team expected to win decisively',
            'markets': ['spread', 'total'],
            'picks': [
                {'bet_type': 'spread', 'selection': 'home', 'edge_boost': 0.02},
                {'bet_type': 'total', 'selection': 'under', 'edge_boost': 0.01},
            ],
        },
        'high_scoring': {
            'description': 'Expect a lot of points scored',
            'markets': ['total'],
            'picks': [
                {'bet_type': 'total', 'selection': 'over', 'edge_boost': 0.02},
            ],
        },
        'low_scoring': {
            'description': 'Expect defensive battle with low scoring',
            'markets': ['total'],
            'picks': [
                {'bet_type': 'total', 'selection': 'under', 'edge_boost': 0.02},
            ],
        },
        'tight_game': {
            'description': 'Close contest with small margins',
            'markets': ['spread'],
            'picks': [
                {'bet_type': 'spread', 'selection': None, 'edge_boost': -0.01},  # Lower confidence
            ],
        },
        'upset': {
            'description': 'Underdog expected to pull off upset',
            'markets': ['spread', 'moneyline'],
            'picks': [
                {'bet_type': 'spread', 'selection': 'away', 'edge_boost': 0.02},
                {'bet_type': 'moneyline', 'selection': 'away', 'edge_boost': 0.01},
            ],
        },
        'bounce_back': {
            'description': 'Team expected to bounce back from losses',
            'markets': ['spread'],
            'picks': [
                {'bet_type': 'spread', 'selection': 'home', 'edge_boost': 0.02},
            ],
        },
        'home_advantage': {
            'description': 'Home court advantage expected to be significant',
            'markets': ['spread'],
            'picks': [
                {'bet_type': 'spread', 'selection': 'home', 'edge_boost': 0.01},
            ],
        },
    }

    def __init__(self):
        """Initialize interpreter."""
        self.logger = logger

    def parse_prompt(self, prompt: str, game_id: Optional[str] = None) -> PromptInterpretation:
        """Parse user prompt and generate betting constraints.

        Args:
            prompt: User's game expectation prompt
            game_id: Optional specific game ID

        Returns:
            PromptInterpretation object
        """
        if not prompt or len(prompt.strip()) < 3:
            self.logger.warning("Empty or too short prompt")
            return PromptInterpretation(
                scenario='balanced',
                scenario_description='No specific scenario detected',
                keywords=set(),
                constraints={'min_edge': 0.03, 'max_edge': None},
                confidence_boost=0.0,
            )

        # Extract keywords
        keywords = self._extract_keywords(prompt.lower())
        self.logger.debug(f"Extracted keywords: {keywords}")

        # Map to scenario
        scenario, confidence = self._map_to_scenario(keywords)

        # Generate constraints
        constraints = self._generate_constraints(scenario, keywords, game_id)

        # Get scenario description
        scenario_desc = self.SCENARIOS.get(scenario, {}).get('description', f'{scenario} scenario')

        return PromptInterpretation(
            scenario=scenario,
            scenario_description=scenario_desc,
            keywords=keywords,
            constraints=constraints,
            confidence_boost=confidence,
        )

    def _extract_keywords(self, prompt: str) -> Set[str]:
        """Extract betting-relevant keywords from prompt.

        Args:
            prompt: Lowercase prompt text

        Returns:
            Set of extracted keywords
        """
        keywords = set()

        # Check for exact keyword matches (case-insensitive)
        for keyword in self.KEYWORDS.keys():
            # Use word boundaries to avoid partial matches
            pattern = r'\b' + re.escape(keyword) + r'\b'
            if re.search(pattern, prompt):
                keywords.add(keyword)

        # Check for team names (mentioned teams)
        nba_teams = [
            'lakers', 'celtics', 'warriors', 'heat', 'suns',
            'mavericks', 'nets', '76ers', 'grizzlies', 'raptors',
            'nuggets', 'clippers', 'kings', 'cavaliers', 'bucks',
            'pacers', 'knicks', 'pistons', 'hawks', 'pelicans'
        ]
        for team in nba_teams:
            if team in prompt:
                keywords.add(f'team_{team}')

        return keywords

    def _map_to_scenario(self, keywords: Set[str]) -> tuple:
        """Map keywords to betting scenario.

        Args:
            keywords: Set of extracted keywords

        Returns:
            Tuple of (scenario_name, confidence_boost)
        """
        scenario_scores = {}

        # Score each scenario based on keyword matches
        for keyword in keywords:
            if keyword not in self.KEYWORDS:
                continue

            implications = self.KEYWORDS[keyword].get('implications', [])
            for implication in implications:
                # Map implications to scenarios
                if 'blowout' in implications or 'high_margin' in implications:
                    scenario_scores['blowout'] = scenario_scores.get('blowout', 0) + 2
                if 'over' in implications or 'high_scoring' in implications:
                    scenario_scores['high_scoring'] = scenario_scores.get('high_scoring', 0) + 2
                if 'under' in implications or 'low_scoring' in implications:
                    scenario_scores['low_scoring'] = scenario_scores.get('low_scoring', 0) + 2
                if 'tight' in implications or 'small_spread' in implications:
                    scenario_scores['tight_game'] = scenario_scores.get('tight_game', 0) + 1
                if 'upset' in implications:
                    scenario_scores['upset'] = scenario_scores.get('upset', 0) + 2
                if 'cover' in implications:
                    scenario_scores['bounce_back'] = scenario_scores.get('bounce_back', 0) + 1
                if 'home_advantage' in implications:
                    scenario_scores['home_advantage'] = scenario_scores.get('home_advantage', 0) + 1

        # Return top scenario or balanced
        if not scenario_scores:
            return 'balanced', 0.0

        top_scenario = max(scenario_scores.items(), key=lambda x: x[1])
        # Confidence based on score (0-1 boost, max 0.05)
        confidence = min(top_scenario[1] / 10, 0.05)

        return top_scenario[0], confidence

    def _generate_constraints(self, scenario: str, keywords: Set[str],
                             game_id: Optional[str] = None) -> Dict:
        """Generate pick generation constraints from scenario.

        Args:
            scenario: Scenario name
            keywords: Set of keywords
            game_id: Optional game ID for same-game parlay

        Returns:
            Dictionary of constraints for pick generation
        """
        scenario_config = self.SCENARIOS.get(scenario, {})

        # Base constraints
        constraints = {
            'scenario': scenario,
            'required_markets': scenario_config.get('markets', ['spread', 'total']),
            'preferred_markets': scenario_config.get('markets', ['spread']),
            'pick_templates': scenario_config.get('picks', []),
            'min_edge': 0.02,  # Lower threshold for user-guided picks
            'min_confidence': 0.50,  # Lower threshold for user-guided picks
            'same_game': game_id is not None,
            'parlay': True,
        }

        # Adjust based on specific keywords
        if 'injury' in keywords or 'injured' in keywords:
            constraints['min_confidence'] = 0.45  # Lower confidence due to uncertainty

        if 'back-to-back' in keywords:
            constraints['edge_boost'] = 0.02  # Situational edge boost

        return constraints
