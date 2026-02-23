#!/usr/bin/env python3
"""Backfill historical NBA data and train initial models."""

import sys
import os
import logging
from datetime import datetime, timedelta

# Add backend to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from ml.data_collection import HistoricalDataCollector
from ml.features import NBAFeatureExtractor
from ml.training.train_models import ModelTrainer

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def fetch_scoreboard_data():
    """Fetch historical scoreboard data from ESPN using dates parameter."""
    import requests
    import time

    logger.info("Fetching historical NBA scoreboard data from ESPN...")
    games_data = []
    current_date = datetime.now().date()

    # Fetch games from last 120 days (roughly 4 months)
    for days_back in range(120, 0, -1):
        check_date = current_date - timedelta(days=days_back)
        date_str = check_date.strftime('%Y%m%d')  # Format: YYYYMMDD

        try:
            # Use ESPN API with dates parameter
            url = f"https://site.api.espn.com/apis/site/v2/sports/basketball/nba/scoreboard?dates={date_str}"
            headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}

            response = requests.get(url, headers=headers, timeout=10)
            response.raise_for_status()

            scoreboard = response.json()
            events = scoreboard.get('events', [])

            for event in events:
                try:
                    # Extract competition data
                    competition = event.get('competitions', [{}])[0]
                    competitors = competition.get('competitors', [])

                    if len(competitors) < 2:
                        continue

                    # Determine home/away
                    home_comp = None
                    away_comp = None
                    for comp in competitors:
                        if comp.get('homeAway') == 'home':
                            home_comp = comp
                        elif comp.get('homeAway') == 'away':
                            away_comp = comp

                    if not home_comp or not away_comp:
                        continue

                    # Only include final games
                    status = competition.get('status', {})
                    # Check if game is completed - the 'completed' field is nested in 'type'
                    if not status.get('type', {}).get('completed'):
                        continue

                    home_team = home_comp.get('team', {})
                    away_team = away_comp.get('team', {})
                    home_score = int(home_comp.get('score', 0) or 0)
                    away_score = int(away_comp.get('score', 0) or 0)

                    if home_score == 0 and away_score == 0:
                        continue  # Skip invalid scores

                    # Extract team names with fallbacks
                    home_name = (home_team.get('shortDisplayName') or
                                home_team.get('displayName') or
                                home_team.get('abbreviation') or
                                home_team.get('name'))
                    away_name = (away_team.get('shortDisplayName') or
                                away_team.get('displayName') or
                                away_team.get('abbreviation') or
                                away_team.get('name'))

                    if not home_name or not away_name:
                        logger.debug(f"Missing team names: home={home_name}, away={away_name}")
                        continue

                    # Extract season from the competition data
                    season = event.get('season', {}).get('year', 2026)

                    games_data.append({
                        'game_id': event.get('id'),
                        'date': check_date.isoformat(),
                        'season': season,
                        'home_team_id': home_team.get('id'),
                        'home_team_name': home_name,
                        'away_team_id': away_team.get('id'),
                        'away_team_name': away_name,
                        'home_score': home_score,
                        'away_score': away_score,
                        'opening_spread': -2.5,  # Placeholder
                        'closing_spread': -2.5,  # Placeholder
                        'opening_total': 215.0,  # Placeholder
                        'closing_total': 215.0,  # Placeholder
                        'status': 'final'
                    })
                except Exception as e:
                    logger.debug(f"Skipping event: {e}")
                    continue

            if len(games_data) % 20 == 0 and len(games_data) > 0:
                logger.info(f"Fetched {len(games_data)} games so far...")

            # Rate limiting - be nice to the API
            time.sleep(0.2)

        except requests.exceptions.RequestException as e:
            logger.debug(f"Error fetching scoreboard for {date_str}: {e}")
            continue
        except Exception as e:
            logger.debug(f"Unexpected error for {date_str}: {e}")
            continue

    logger.info(f"Total games fetched: {len(games_data)}")
    return games_data


def backfill_data(db_path: str):
    """Backfill historical game data into SQLite database."""
    logger.info(f"Starting data backfill to {db_path}")

    # Fetch data from ESPN
    games_data = fetch_scoreboard_data()

    if not games_data:
        logger.error("No games fetched from ESPN")
        return False

    # Initialize collector
    collector = HistoricalDataCollector(db_path)

    # Insert games
    logger.info(f"Inserting {len(games_data)} games into database...")
    for i, game in enumerate(games_data):
        try:
            # Ensure we have required fields
            if all(game.get(k) for k in ['game_id', 'date', 'home_team_name', 'away_team_name',
                                          'home_score', 'away_score']):
                collector.insert_game(game)
                if (i + 1) % 20 == 0:
                    logger.info(f"Inserted {i + 1} games...")
        except Exception as e:
            logger.debug(f"Skipping game {game.get('game_id')}: {e}")
            continue

    # Verify we have enough data
    cursor = collector.conn.cursor()
    cursor.execute("SELECT COUNT(*) as count FROM games")
    total = cursor.fetchone()['count']
    collector.close()

    logger.info(f"Total games in database: {total}")

    if total < 100:
        logger.warning(f"Warning: Only {total} games in database (need at least 100 for training)")
        return False

    return True


def train_models(data_path: str, output_path: str):
    """Train NBA models on historical data."""
    logger.info(f"Starting model training...")
    logger.info(f"  Data: {data_path}")
    logger.info(f"  Output: {output_path}")

    trainer = ModelTrainer(data_path, output_path)

    try:
        results = trainer.train_nba_models()

        logger.info("=" * 60)
        logger.info("TRAINING COMPLETE")
        logger.info("=" * 60)

        for market, result in results.items():
            logger.info(f"\n{market.upper()}:")
            for key, value in result.items():
                if key != 'feature_importances':
                    if isinstance(value, float):
                        if key in ['accuracy', 'precision', 'recall', 'f1', 'mae', 'rmse', 'mape']:
                            logger.info(f"  {key}: {value:.4f}")
                        else:
                            logger.info(f"  {key}: {value}")
                    else:
                        logger.info(f"  {key}: {value}")

        return True

    except Exception as e:
        logger.error(f"Training failed: {e}", exc_info=True)
        return False
    finally:
        trainer.close()


def main():
    """Main backfill and training entrypoint."""
    # Use absolute paths or relative to backend directory
    backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    data_path = os.path.join(backend_dir, "data", "historical_games.db")
    output_path = os.path.join(backend_dir, "data", "models")

    logger.info("AI Picks Generator - Data Backfill & Model Training")
    logger.info("=" * 60)

    # Step 1: Backfill data
    logger.info("\nStep 1: Backfilling historical data...")
    if not backfill_data(data_path):
        logger.error("Data backfill failed or insufficient data. Aborting.")
        return 1

    # Step 2: Train models
    logger.info("\nStep 2: Training models...")
    if not train_models(data_path, output_path):
        logger.error("Model training failed. Aborting.")
        return 1

    logger.info("\n" + "=" * 60)
    logger.info("SUCCESS: Data backfill and model training complete!")
    logger.info("=" * 60)
    logger.info(f"\nModels saved to: {output_path}")
    logger.info("Ready for API integration (Phase 6)")

    return 0


if __name__ == "__main__":
    sys.exit(main())
