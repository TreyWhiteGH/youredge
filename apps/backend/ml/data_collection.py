"""Historical NBA data collection for ML model training."""

import sqlite3
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional
import sys
import os

logger = logging.getLogger(__name__)


class HistoricalDataCollector:
    """Collects and stores historical NBA game data for training."""

    def __init__(self, db_path: str):
        """Initialize collector with SQLite database path.

        Args:
            db_path: Path to SQLite database file
        """
        self.db_path = db_path
        self.conn = None
        self._init_db()

    def _init_db(self):
        """Initialize database connection and create schema."""
        self.conn = sqlite3.connect(self.db_path)
        self.conn.row_factory = sqlite3.Row
        self._create_schema()
        logger.info(f"Initialized database at {self.db_path}")

    def _create_schema(self):
        """Create database tables if they don't exist."""
        cursor = self.conn.cursor()

        # Games table - core game information
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS games (
                game_id TEXT PRIMARY KEY,
                date DATE NOT NULL,
                season INTEGER NOT NULL,
                home_team_id TEXT NOT NULL,
                home_team_name TEXT NOT NULL,
                away_team_id TEXT NOT NULL,
                away_team_name TEXT NOT NULL,
                home_score INTEGER,
                away_score INTEGER,
                opening_spread REAL,
                closing_spread REAL,
                opening_total REAL,
                closing_total REAL,
                home_ml_odds INTEGER,
                away_ml_odds INTEGER,
                location TEXT,
                arena TEXT,
                status TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Create indexes separately (SQLite doesn't support inline INDEX)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_games_date ON games(date)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_games_season ON games(season)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_games_home_team ON games(home_team_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_games_away_team ON games(away_team_id)")

        # Team game stats - per-game statistics
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS team_game_stats (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                game_id TEXT NOT NULL,
                team_id TEXT NOT NULL,
                is_home INTEGER NOT NULL,

                -- Scoring
                points INTEGER,
                field_goals_made INTEGER,
                field_goals_attempted INTEGER,
                three_pointers_made INTEGER,
                three_pointers_attempted INTEGER,
                free_throws_made INTEGER,
                free_throws_attempted INTEGER,

                -- Rebounds and Ball Handling
                total_rebounds INTEGER,
                offensive_rebounds INTEGER,
                defensive_rebounds INTEGER,
                assists INTEGER,
                turnovers INTEGER,

                -- Defense and Other
                steals INTEGER,
                blocks INTEGER,
                personal_fouls INTEGER,
                bench_points INTEGER,
                fast_break_points INTEGER,
                second_chance_points INTEGER,

                -- Shooting percentages (computed)
                fg_pct REAL,
                three_pt_pct REAL,
                ft_pct REAL,
                true_shooting_pct REAL,
                effective_fg_pct REAL,

                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (game_id) REFERENCES games(game_id)
            )
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_game_team ON team_game_stats(game_id, team_id)")

        # Team rolling stats - aggregated statistics
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS team_rolling_stats (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                team_id TEXT NOT NULL,
                date DATE NOT NULL,
                window_days INTEGER NOT NULL,

                -- Aggregated statistics
                games_played INTEGER,
                wins INTEGER,
                losses INTEGER,
                win_pct REAL,

                -- Points
                avg_pts_for REAL,
                avg_pts_against REAL,
                net_rating REAL,

                -- Shooting
                avg_fg_pct REAL,
                avg_three_pt_pct REAL,
                avg_ft_pct REAL,

                -- Rebounds and assists
                avg_rebounds REAL,
                avg_assists REAL,
                avg_turnovers REAL,

                -- Other
                avg_steals REAL,
                avg_blocks REAL,
                pace REAL,

                -- Home/Away splits
                home_avg_pts_for REAL,
                home_avg_pts_against REAL,
                away_avg_pts_for REAL,
                away_avg_pts_against REAL,
                home_win_pct REAL,
                away_win_pct REAL,

                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_team_date ON team_rolling_stats(team_id, date, window_days)")

        # Head-to-head history
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS head_to_head (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                home_team_id TEXT NOT NULL,
                away_team_id TEXT NOT NULL,
                game_id TEXT NOT NULL,
                date DATE NOT NULL,
                home_score INTEGER,
                away_score INTEGER,
                home_spread REAL,
                total REAL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (game_id) REFERENCES games(game_id)
            )
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_matchup ON head_to_head(home_team_id, away_team_id)")

        # Feature cache - computed features for games
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS game_features (
                game_id TEXT PRIMARY KEY,
                date DATE NOT NULL,
                home_team_id TEXT NOT NULL,
                away_team_id TEXT NOT NULL,
                features JSON NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_features_date ON game_features(date)")

        self.conn.commit()
        logger.info("Database schema initialized")

    def insert_game(self, game_data: Dict) -> bool:
        """Insert a game record into the database.

        Args:
            game_data: Dictionary with game information

        Returns:
            True if successful, False otherwise
        """
        try:
            cursor = self.conn.cursor()
            cursor.execute("""
                INSERT OR REPLACE INTO games (
                    game_id, date, season, home_team_id, home_team_name,
                    away_team_id, away_team_name, home_score, away_score,
                    opening_spread, closing_spread, opening_total, closing_total,
                    home_ml_odds, away_ml_odds, location, arena, status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                game_data['game_id'],
                game_data['date'],
                game_data['season'],
                game_data['home_team_id'],
                game_data['home_team_name'],
                game_data['away_team_id'],
                game_data['away_team_name'],
                game_data.get('home_score'),
                game_data.get('away_score'),
                game_data.get('opening_spread'),
                game_data.get('closing_spread'),
                game_data.get('opening_total'),
                game_data.get('closing_total'),
                game_data.get('home_ml_odds'),
                game_data.get('away_ml_odds'),
                game_data.get('location'),
                game_data.get('arena'),
                game_data.get('status', 'final')
            ))
            self.conn.commit()
            return True
        except Exception as e:
            logger.error(f"Error inserting game {game_data.get('game_id')}: {e}")
            return False

    def insert_team_stats(self, game_id: str, team_id: str, is_home: bool,
                         stats: Dict) -> bool:
        """Insert team game statistics.

        Args:
            game_id: Game ID
            team_id: Team ID
            is_home: Whether this is the home team
            stats: Dictionary of statistics

        Returns:
            True if successful, False otherwise
        """
        try:
            cursor = self.conn.cursor()
            cursor.execute("""
                INSERT INTO team_game_stats (
                    game_id, team_id, is_home,
                    points, field_goals_made, field_goals_attempted,
                    three_pointers_made, three_pointers_attempted,
                    free_throws_made, free_throws_attempted,
                    total_rebounds, offensive_rebounds, defensive_rebounds,
                    assists, turnovers, steals, blocks, personal_fouls,
                    fg_pct, three_pt_pct, ft_pct, effective_fg_pct
                ) VALUES (
                    ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
                )
            """, (
                game_id, team_id, 1 if is_home else 0,
                stats.get('points'),
                stats.get('field_goals_made'),
                stats.get('field_goals_attempted'),
                stats.get('three_pointers_made'),
                stats.get('three_pointers_attempted'),
                stats.get('free_throws_made'),
                stats.get('free_throws_attempted'),
                stats.get('total_rebounds'),
                stats.get('offensive_rebounds'),
                stats.get('defensive_rebounds'),
                stats.get('assists'),
                stats.get('turnovers'),
                stats.get('steals'),
                stats.get('blocks'),
                stats.get('personal_fouls'),
                stats.get('fg_pct'),
                stats.get('three_pt_pct'),
                stats.get('ft_pct'),
                stats.get('effective_fg_pct')
            ))
            self.conn.commit()
            return True
        except Exception as e:
            logger.error(f"Error inserting stats for {game_id}: {e}")
            return False

    def get_team_stats(self, team_id: str, date: datetime,
                      window_days: int = 10) -> Optional[Dict]:
        """Get rolling team statistics up to a given date.

        Args:
            team_id: Team ID
            date: Reference date
            window_days: Number of days to look back

        Returns:
            Dictionary of aggregated statistics or None if not found
        """
        cursor = self.conn.cursor()
        start_date = (date - timedelta(days=window_days)).strftime('%Y-%m-%d')
        end_date = date.strftime('%Y-%m-%d')

        # Get games in window
        cursor.execute("""
            SELECT gs.*, g.date, g.home_team_id, g.away_team_id
            FROM team_game_stats gs
            JOIN games g ON gs.game_id = g.game_id
            WHERE gs.team_id = ?
            AND g.date BETWEEN ? AND ?
            ORDER BY g.date DESC
            LIMIT ?
        """, (team_id, start_date, end_date, window_days))

        rows = cursor.fetchall()
        if not rows:
            return None

        # Calculate aggregate statistics
        total_pts_for = sum(row['points'] for row in rows if row['points'])
        total_pts_against = 0
        total_games = len(rows)
        total_wins = 0
        total_assists = sum(row['assists'] for row in rows if row['assists'])
        total_rebounds = sum(row['total_rebounds'] for row in rows if row['total_rebounds'])

        return {
            'team_id': team_id,
            'games_played': total_games,
            'avg_pts_for': total_pts_for / total_games if total_games > 0 else 0,
            'avg_pts_against': total_pts_against / total_games if total_games > 0 else 0,
            'avg_assists': total_assists / total_games if total_games > 0 else 0,
            'avg_rebounds': total_rebounds / total_games if total_games > 0 else 0,
        }

    def get_h2h_history(self, home_team_id: str, away_team_id: str,
                       limit: int = 5) -> List[Dict]:
        """Get head-to-head matchup history.

        Args:
            home_team_id: Home team ID
            away_team_id: Away team ID
            limit: Maximum number of matchups to return

        Returns:
            List of matchup dictionaries
        """
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT *
            FROM head_to_head
            WHERE (home_team_id = ? AND away_team_id = ?)
               OR (home_team_id = ? AND away_team_id = ?)
            ORDER BY date DESC
            LIMIT ?
        """, (home_team_id, away_team_id, away_team_id, home_team_id, limit))

        return [dict(row) for row in cursor.fetchall()]

    def get_recent_games(self, team_id: str, limit: int = 10) -> List[Dict]:
        """Get recent games for a team.

        Args:
            team_id: Team ID
            limit: Number of games to return

        Returns:
            List of game dictionaries
        """
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT g.*
            FROM games g
            WHERE g.home_team_id = ? OR g.away_team_id = ?
            ORDER BY g.date DESC
            LIMIT ?
        """, (team_id, team_id, limit))

        return [dict(row) for row in cursor.fetchall()]

    def get_game(self, game_id: str) -> Optional[Dict]:
        """Get a specific game by ID.

        Args:
            game_id: Game ID

        Returns:
            Game dictionary or None
        """
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM games WHERE game_id = ?", (game_id,))
        row = cursor.fetchone()
        return dict(row) if row else None

    def get_games_by_date(self, date: str, season: Optional[int] = None) -> List[Dict]:
        """Get all games on a specific date.

        Args:
            date: Date in YYYY-MM-DD format
            season: Optional season year to filter

        Returns:
            List of game dictionaries
        """
        cursor = self.conn.cursor()
        if season:
            cursor.execute(
                "SELECT * FROM games WHERE date = ? AND season = ? ORDER BY date",
                (date, season)
            )
        else:
            cursor.execute(
                "SELECT * FROM games WHERE date = ? ORDER BY date",
                (date,)
            )
        return [dict(row) for row in cursor.fetchall()]

    def get_team_season_stats(self, team_id: str, season: int) -> Optional[Dict]:
        """Get season-level statistics for a team.

        Args:
            team_id: Team ID
            season: Season year

        Returns:
            Dictionary of season statistics or None
        """
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT
                COUNT(*) as games_played,
                SUM(CASE WHEN
                    (is_home = 1 AND home_score > away_score) OR
                    (is_home = 0 AND away_score > home_score)
                    THEN 1 ELSE 0 END) as wins,
                AVG(points) as avg_points,
                AVG(assists) as avg_assists,
                AVG(total_rebounds) as avg_rebounds,
                AVG(fg_pct) as avg_fg_pct,
                AVG(three_pt_pct) as avg_three_pt_pct
            FROM team_game_stats tgs
            JOIN games g ON tgs.game_id = g.game_id
            WHERE tgs.team_id = ? AND g.season = ?
        """, (team_id, season))

        row = cursor.fetchone()
        return dict(row) if row else None

    def close(self):
        """Close database connection."""
        if self.conn:
            self.conn.close()
            logger.info("Database connection closed")


if __name__ == "__main__":
    # Example usage
    import argparse

    parser = argparse.ArgumentParser(description="Collect historical NBA data")
    parser.add_argument("--db", default="apps/backend/data/historical_games.db",
                       help="Path to SQLite database")
    parser.add_argument("--list-tables", action="store_true",
                       help="List database tables")

    args = parser.parse_args()

    collector = HistoricalDataCollector(args.db)

    if args.list_tables:
        cursor = collector.conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = cursor.fetchall()
        print("Database tables:")
        for table in tables:
            print(f"  - {table[0]}")

    collector.close()
