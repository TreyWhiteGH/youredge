"""Feature engineering for NBA game predictions."""

import logging
from datetime import datetime, timedelta
from typing import Dict, Optional
from dataclasses import dataclass, asdict

logger = logging.getLogger(__name__)


@dataclass
class NBAGameFeatures:
    """Container for NBA game features."""

    # Team Performance (last 10 games)
    home_pts_avg: float
    away_pts_avg: float
    home_pts_allowed_avg: float
    away_pts_allowed_avg: float
    home_win_pct: float
    away_win_pct: float

    # Rest & Schedule
    home_rest_days: int
    away_rest_days: int
    home_back_to_back: bool
    away_back_to_back: bool
    home_games_in_last_7: int
    away_games_in_last_7: int

    # Home Court Advantage
    home_court_advantage: float  # Home win% - Away win%
    home_pts_at_home_avg: float
    away_pts_on_road_avg: float

    # Head-to-Head
    h2h_home_wins_last_5: int
    h2h_away_wins_last_5: int
    h2h_avg_total_last_5: float
    h2h_avg_margin_last_5: float

    # Pace & Style
    home_pace: float  # Possessions per game
    away_pace: float
    home_three_pt_pct: float
    away_three_pt_pct: float
    home_fg_pct: float
    away_fg_pct: float
    home_ft_pct: float
    away_ft_pct: float

    # Advanced Metrics
    home_net_rating: float  # Off Rating - Def Rating
    away_net_rating: float
    home_effective_fg_pct: float
    away_effective_fg_pct: float
    home_true_shooting_pct: float
    away_true_shooting_pct: float

    # Efficiency Stats
    home_ast_per_game: float
    away_ast_per_game: float
    home_to_per_game: float
    away_to_per_game: float
    home_rebound_pct: float
    away_rebound_pct: float

    # Injury/Lineup
    home_key_players_out: int
    away_key_players_out: int

    # Market Data
    opening_line: float
    current_line: float
    line_movement: float
    opening_total: float
    current_total: float
    total_movement: float

    def to_dict(self) -> Dict:
        """Convert to dictionary."""
        return asdict(self)

    def to_feature_vector(self) -> list:
        """Convert to feature vector for model input (consistent order for training)."""
        return [
            # Team Performance
            self.home_pts_avg,
            self.away_pts_avg,
            self.home_pts_allowed_avg,
            self.away_pts_allowed_avg,
            self.home_win_pct,
            self.away_win_pct,
            # Rest & Schedule
            self.home_rest_days,
            self.away_rest_days,
            float(self.home_back_to_back),
            float(self.away_back_to_back),
            self.home_games_in_last_7,
            self.away_games_in_last_7,
            # Home Court
            self.home_court_advantage,
            self.home_pts_at_home_avg,
            self.away_pts_on_road_avg,
            # Head-to-Head
            self.h2h_home_wins_last_5,
            self.h2h_away_wins_last_5,
            self.h2h_avg_total_last_5,
            self.h2h_avg_margin_last_5,
            # Pace & Style
            self.home_pace,
            self.away_pace,
            self.home_three_pt_pct,
            self.away_three_pt_pct,
            self.home_fg_pct,
            self.away_fg_pct,
            self.home_ft_pct,
            self.away_ft_pct,
            # Advanced Metrics
            self.home_net_rating,
            self.away_net_rating,
            self.home_effective_fg_pct,
            self.away_effective_fg_pct,
            self.home_true_shooting_pct,
            self.away_true_shooting_pct,
            # Efficiency
            self.home_ast_per_game,
            self.away_ast_per_game,
            self.home_to_per_game,
            self.away_to_per_game,
            self.home_rebound_pct,
            self.away_rebound_pct,
            # Injury
            self.home_key_players_out,
            self.away_key_players_out,
            # Market Data
            self.opening_line,
            self.current_line,
            self.line_movement,
            self.opening_total,
            self.current_total,
            self.total_movement,
        ]

    @staticmethod
    def feature_names() -> list:
        """Get list of feature names in order (for model training)."""
        return [
            # Team Performance
            'home_pts_avg', 'away_pts_avg',
            'home_pts_allowed_avg', 'away_pts_allowed_avg',
            'home_win_pct', 'away_win_pct',
            # Rest & Schedule
            'home_rest_days', 'away_rest_days',
            'home_back_to_back', 'away_back_to_back',
            'home_games_in_last_7', 'away_games_in_last_7',
            # Home Court
            'home_court_advantage',
            'home_pts_at_home_avg', 'away_pts_on_road_avg',
            # Head-to-Head
            'h2h_home_wins_last_5', 'h2h_away_wins_last_5',
            'h2h_avg_total_last_5', 'h2h_avg_margin_last_5',
            # Pace & Style
            'home_pace', 'away_pace',
            'home_three_pt_pct', 'away_three_pt_pct',
            'home_fg_pct', 'away_fg_pct',
            'home_ft_pct', 'away_ft_pct',
            # Advanced Metrics
            'home_net_rating', 'away_net_rating',
            'home_effective_fg_pct', 'away_effective_fg_pct',
            'home_true_shooting_pct', 'away_true_shooting_pct',
            # Efficiency
            'home_ast_per_game', 'away_ast_per_game',
            'home_to_per_game', 'away_to_per_game',
            'home_rebound_pct', 'away_rebound_pct',
            # Injury
            'home_key_players_out', 'away_key_players_out',
            # Market Data
            'opening_line', 'current_line', 'line_movement',
            'opening_total', 'current_total', 'total_movement',
        ]


class NBAFeatureExtractor:
    """Extracts features from NBA games for ML model input."""

    def __init__(self, data_collector):
        """Initialize extractor with data collector.

        Args:
            data_collector: Instance of HistoricalDataCollector
        """
        self.collector = data_collector

    def extract_features(self, game: Dict,
                        game_date: Optional[str] = None) -> NBAGameFeatures:
        """Extract features for a game.

        Args:
            game: Game dictionary (typically from ESPN API or database)
            game_date: Optional date string for feature calculation (defaults to game date)

        Returns:
            NBAGameFeatures object
        """
        if game_date is None:
            game_date = game.get('date', datetime.now().strftime('%Y-%m-%d'))

        game_datetime = datetime.strptime(game_date, '%Y-%m-%d')
        home_team_id = game.get('home_team_id')
        away_team_id = game.get('away_team_id')

        # Get recent stats for both teams
        home_stats = self.collector.get_team_stats(home_team_id, game_datetime, window_days=10)
        away_stats = self.collector.get_team_stats(away_team_id, game_datetime, window_days=10)

        # Get home/away splits
        home_home_stats = self._get_home_splits(home_team_id, game_datetime)
        away_away_stats = self._get_away_splits(away_team_id, game_datetime)

        # Get head-to-head history
        h2h = self.collector.get_h2h_history(home_team_id, away_team_id, limit=5)

        # Get rest days
        home_rest, home_b2b, home_games_7 = self._calculate_rest(home_team_id, game_datetime)
        away_rest, away_b2b, away_games_7 = self._calculate_rest(away_team_id, game_datetime)

        # Get odds data (if available)
        opening_line = game.get('opening_spread', 0)
        current_line = game.get('closing_spread', opening_line)
        opening_total = game.get('opening_total', 0)
        current_total = game.get('closing_total', opening_total)

        return NBAGameFeatures(
            # Team Performance
            home_pts_avg=home_stats.get('avg_pts_for', 0) if home_stats else 0,
            away_pts_avg=away_stats.get('avg_pts_for', 0) if away_stats else 0,
            home_pts_allowed_avg=home_stats.get('avg_pts_against', 0) if home_stats else 0,
            away_pts_allowed_avg=away_stats.get('avg_pts_against', 0) if away_stats else 0,
            home_win_pct=home_stats.get('win_pct', 0.5) if home_stats else 0.5,
            away_win_pct=away_stats.get('win_pct', 0.5) if away_stats else 0.5,

            # Rest & Schedule
            home_rest_days=home_rest,
            away_rest_days=away_rest,
            home_back_to_back=home_b2b,
            away_back_to_back=away_b2b,
            home_games_in_last_7=home_games_7,
            away_games_in_last_7=away_games_7,

            # Home Court Advantage
            home_court_advantage=(home_stats.get('win_pct', 0.5) if home_stats else 0.5) -
                                  (away_stats.get('win_pct', 0.5) if away_stats else 0.5),
            home_pts_at_home_avg=home_home_stats.get('avg_pts_for', home_stats.get('avg_pts_for', 0) if home_stats else 0),
            away_pts_on_road_avg=away_away_stats.get('avg_pts_for', away_stats.get('avg_pts_for', 0) if away_stats else 0),

            # Head-to-Head
            h2h_home_wins_last_5=sum(1 for g in h2h if g.get('home_team_id') == home_team_id and g.get('home_score', 0) > g.get('away_score', 0)),
            h2h_away_wins_last_5=sum(1 for g in h2h if g.get('away_team_id') == home_team_id and g.get('away_score', 0) > g.get('home_score', 0)),
            h2h_avg_total_last_5=sum((g.get('home_score', 0) + g.get('away_score', 0)) for g in h2h) / max(len(h2h), 1),
            h2h_avg_margin_last_5=self._calculate_h2h_margin(h2h, home_team_id),

            # Pace & Style
            home_pace=home_stats.get('pace', 100) if home_stats else 100,
            away_pace=away_stats.get('pace', 100) if away_stats else 100,
            home_three_pt_pct=home_stats.get('avg_three_pt_pct', 0.35) if home_stats else 0.35,
            away_three_pt_pct=away_stats.get('avg_three_pt_pct', 0.35) if away_stats else 0.35,
            home_fg_pct=home_stats.get('avg_fg_pct', 0.45) if home_stats else 0.45,
            away_fg_pct=away_stats.get('avg_fg_pct', 0.45) if away_stats else 0.45,
            home_ft_pct=home_stats.get('avg_ft_pct', 0.75) if home_stats else 0.75,
            away_ft_pct=away_stats.get('avg_ft_pct', 0.75) if away_stats else 0.75,

            # Advanced Metrics
            home_net_rating=home_stats.get('net_rating', 0) if home_stats else 0,
            away_net_rating=away_stats.get('net_rating', 0) if away_stats else 0,
            home_effective_fg_pct=home_stats.get('avg_effective_fg_pct', 0.5) if home_stats else 0.5,
            away_effective_fg_pct=away_stats.get('avg_effective_fg_pct', 0.5) if away_stats else 0.5,
            home_true_shooting_pct=home_stats.get('avg_true_shooting_pct', 0.55) if home_stats else 0.55,
            away_true_shooting_pct=away_stats.get('avg_true_shooting_pct', 0.55) if away_stats else 0.55,

            # Efficiency
            home_ast_per_game=home_stats.get('avg_assists', 0) if home_stats else 0,
            away_ast_per_game=away_stats.get('avg_assists', 0) if away_stats else 0,
            home_to_per_game=home_stats.get('avg_turnovers', 0) if home_stats else 0,
            away_to_per_game=away_stats.get('avg_turnovers', 0) if away_stats else 0,
            home_rebound_pct=home_stats.get('avg_rebounds', 0) / (home_stats.get('avg_rebounds', 0) + away_stats.get('avg_rebounds', 0)) if home_stats and away_stats else 0.5,
            away_rebound_pct=away_stats.get('avg_rebounds', 0) / (home_stats.get('avg_rebounds', 0) + away_stats.get('avg_rebounds', 0)) if home_stats and away_stats else 0.5,

            # Injury/Lineup
            home_key_players_out=game.get('home_key_players_out', 0),
            away_key_players_out=game.get('away_key_players_out', 0),

            # Market Data
            opening_line=opening_line,
            current_line=current_line,
            line_movement=current_line - opening_line,
            opening_total=opening_total,
            current_total=current_total,
            total_movement=current_total - opening_total,
        )

    def _calculate_rest(self, team_id: str, game_date: datetime) -> tuple:
        """Calculate rest days, back-to-back status, and games in last 7 days.

        Args:
            team_id: Team ID
            game_date: Date of the upcoming game

        Returns:
            Tuple of (rest_days, is_back_to_back, games_in_last_7)
        """
        recent_games = self.collector.get_recent_games(team_id, limit=5)

        if not recent_games:
            return 2, False, 0

        # Find last game
        last_game = recent_games[0]
        last_game_date = datetime.strptime(last_game['date'], '%Y-%m-%d')
        rest_days = (game_date - last_game_date).days

        # Check if back-to-back
        is_b2b = rest_days == 1

        # Count games in last 7 days
        games_last_7 = sum(1 for g in recent_games
                          if (game_date - datetime.strptime(g['date'], '%Y-%m-%d')).days <= 7)

        return rest_days, is_b2b, games_last_7

    def _get_home_splits(self, team_id: str, game_date: datetime) -> Dict:
        """Get home game performance splits.

        Args:
            team_id: Team ID
            game_date: Reference date

        Returns:
            Dictionary with home game statistics
        """
        # Placeholder - would need to implement actual calculation from database
        return {'avg_pts_for': 0}

    def _get_away_splits(self, team_id: str, game_date: datetime) -> Dict:
        """Get away game performance splits.

        Args:
            team_id: Team ID
            game_date: Reference date

        Returns:
            Dictionary with away game statistics
        """
        # Placeholder - would need to implement actual calculation from database
        return {'avg_pts_for': 0}

    def _calculate_h2h_margin(self, h2h_games: list, home_team_id: str) -> float:
        """Calculate average margin from head-to-head history.

        Args:
            h2h_games: List of head-to-head game dictionaries
            home_team_id: Team ID

        Returns:
            Average margin for home team
        """
        if not h2h_games:
            return 0

        margins = []
        for game in h2h_games:
            if game.get('home_team_id') == home_team_id:
                margin = game.get('home_score', 0) - game.get('away_score', 0)
            else:
                margin = game.get('away_score', 0) - game.get('home_score', 0)
            margins.append(margin)

        return sum(margins) / len(margins) if margins else 0
