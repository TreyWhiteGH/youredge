"""Training pipeline for NBA pick models."""

import logging
import json
import pickle
import numpy as np
from datetime import datetime
from pathlib import Path
from typing import Dict, Tuple, Optional
import sys
import os

from sklearn.model_selection import cross_val_score
from xgboost import XGBClassifier, XGBRegressor

# Add backend to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from ml.data_collection import HistoricalDataCollector
from ml.features import NBAFeatureExtractor, NBAGameFeatures

logger = logging.getLogger(__name__)


class ModelTrainer:
    """Trainer for NBA betting ML models."""

    def __init__(self, data_path: str, output_path: str):
        """Initialize trainer.

        Args:
            data_path: Path to SQLite database with historical data
            output_path: Path to save trained models
        """
        self.data_path = data_path
        self.output_path = Path(output_path)
        self.output_path.mkdir(parents=True, exist_ok=True)

        self.collector = HistoricalDataCollector(data_path)
        self.extractor = NBAFeatureExtractor(self.collector)

        # Model definitions
        self.models = {
            'spread': XGBClassifier(
                n_estimators=100,
                max_depth=6,
                learning_rate=0.1,
                random_state=42,
                eval_metric='logloss'
            ),
            'total': XGBRegressor(
                n_estimators=100,
                max_depth=6,
                learning_rate=0.1,
                random_state=42
            ),
            'moneyline': XGBClassifier(
                n_estimators=100,
                max_depth=6,
                learning_rate=0.1,
                random_state=42,
                eval_metric='logloss'
            ),
        }

        self.results = {}

    def train_nba_models(self) -> Dict:
        """Train all NBA models.

        Returns:
            Dictionary with training results
        """
        logger.info(f"Starting NBA model training from {self.data_path}")

        # Load all games from database
        games = self._load_all_games()
        logger.info(f"Loaded {len(games)} games")

        if len(games) < 100:
            logger.error("Insufficient data for training (need at least 100 games)")
            return {'error': 'Insufficient data'}

        # Extract features and targets
        X, y_spread, y_total, y_moneyline = self._extract_training_data(games)
        logger.info(f"Extracted {len(X)} samples with {len(X[0])} features")

        # Temporal train/val/test split (important for time series data)
        split_idx_train = int(len(X) * 0.7)
        split_idx_val = int(len(X) * 0.85)

        X_train, X_val, X_test = X[:split_idx_train], X[split_idx_train:split_idx_val], X[split_idx_val:]
        y_spread_train, y_spread_val, y_spread_test = y_spread[:split_idx_train], y_spread[split_idx_train:split_idx_val], y_spread[split_idx_val:]
        y_total_train, y_total_val, y_total_test = y_total[:split_idx_train], y_total[split_idx_train:split_idx_val], y_total[split_idx_val:]
        y_mono_train, y_mono_val, y_mono_test = y_moneyline[:split_idx_train], y_moneyline[split_idx_train:split_idx_val], y_moneyline[split_idx_val:]

        logger.info(f"Train: {len(X_train)}, Val: {len(X_val)}, Test: {len(X_test)}")

        # Train spread model
        logger.info("Training spread model...")
        self.models['spread'].fit(X_train, y_spread_train)
        spread_results = self.evaluate_model(self.models['spread'], X_test, y_spread_test, 'spread')
        self.results['spread'] = spread_results

        # Train total model (regression)
        logger.info("Training total model...")
        self.models['total'].fit(X_train, y_total_train)
        total_results = self.evaluate_model(self.models['total'], X_test, y_total_test, 'total', is_regression=True)
        self.results['total'] = total_results

        # Train moneyline model
        logger.info("Training moneyline model...")
        self.models['moneyline'].fit(X_train, y_mono_train)
        mono_results = self.evaluate_model(self.models['moneyline'], X_test, y_mono_test, 'moneyline')
        self.results['moneyline'] = mono_results

        # Save models
        logger.info("Saving models...")
        for market, model in self.models.items():
            self._save_model(model, market, self.results[market])

        logger.info("Model training complete")
        return self.results

    def _load_all_games(self) -> list:
        """Load all games from database.

        Returns:
            List of game dictionaries
        """
        cursor = self.collector.conn.cursor()
        cursor.execute("""
            SELECT * FROM games
            WHERE home_score IS NOT NULL AND away_score IS NOT NULL
            ORDER BY date ASC
        """)
        return [dict(row) for row in cursor.fetchall()]

    def _extract_training_data(self, games: list) -> Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
        """Extract features and targets from games.

        Args:
            games: List of game dictionaries

        Returns:
            Tuple of (X, y_spread, y_total, y_moneyline)
        """
        X = []
        y_spread = []
        y_total = []
        y_moneyline = []

        for i, game in enumerate(games):
            try:
                # Extract features
                features = self.extractor.extract_features(game)
                X.append(features.to_feature_vector())

                # Spread target: 1 if home covers, 0 otherwise
                spread = game.get('closing_spread', 0)
                margin = game.get('home_score', 0) - game.get('away_score', 0)
                home_covers = 1 if margin > spread else 0
                y_spread.append(home_covers)

                # Total target: actual total points
                total = game.get('home_score', 0) + game.get('away_score', 0)
                y_total.append(total)

                # Moneyline target: 1 if home wins, 0 if away
                home_wins = 1 if game.get('home_score', 0) > game.get('away_score', 0) else 0
                y_moneyline.append(home_wins)

                if (i + 1) % 100 == 0:
                    logger.debug(f"Processed {i + 1} games")

            except Exception as e:
                logger.warning(f"Error processing game {game.get('game_id')}: {e}")
                continue

        return np.array(X), np.array(y_spread), np.array(y_total), np.array(y_moneyline)

    def evaluate_model(self, model, X_test: np.ndarray, y_test: np.ndarray,
                      market: str, is_regression: bool = False) -> Dict:
        """Evaluate model performance.

        Args:
            model: Trained model
            X_test: Test features
            y_test: Test targets
            market: Market name (spread/total/moneyline)
            is_regression: Whether this is a regression model

        Returns:
            Dictionary with evaluation metrics
        """
        predictions = model.predict(X_test)

        if is_regression:
            # Regression metrics
            mae = np.mean(np.abs(predictions - y_test))
            rmse = np.sqrt(np.mean((predictions - y_test) ** 2))
            mape = np.mean(np.abs((y_test - predictions) / y_test))

            results = {
                'model': market,
                'task': 'regression',
                'samples': len(X_test),
                'mae': float(mae),
                'rmse': float(rmse),
                'mape': float(mape),
                'trained_at': datetime.now().isoformat(),
            }
        else:
            # Classification metrics
            from sklearn.metrics import accuracy_score, precision_score, recall_score, f1_score

            accuracy = accuracy_score(y_test, predictions)
            precision = precision_score(y_test, predictions, zero_division=0)
            recall = recall_score(y_test, predictions, zero_division=0)
            f1 = f1_score(y_test, predictions, zero_division=0)

            results = {
                'model': market,
                'task': 'classification',
                'samples': len(X_test),
                'accuracy': float(accuracy),
                'precision': float(precision),
                'recall': float(recall),
                'f1': float(f1),
                'trained_at': datetime.now().isoformat(),
            }

        # Get feature importance
        if hasattr(model, 'feature_importances_'):
            feature_names = NBAGameFeatures.feature_names()
            importance_dict = {}
            for name, importance in zip(feature_names, model.feature_importances_):
                importance_dict[name] = float(importance)
            results['feature_importances'] = importance_dict

        logger.info(f"{market.upper()} Results: {results}")
        return results

    def _save_model(self, model, market: str, results: Dict):
        """Save model to disk.

        Args:
            model: Trained model
            market: Market name
            results: Training results dictionary
        """
        # Save model
        model_path = self.output_path / f"nba_{market}.pkl"
        with open(model_path, 'wb') as f:
            pickle.dump(model, f)
        logger.info(f"Saved model to {model_path}")

        # Save metadata
        metadata = {
            'market': market,
            'features': NBAGameFeatures.feature_names(),
            'version': '1.0',
            'trained_date': datetime.now().isoformat(),
            'performance': results,
        }
        metadata_path = self.output_path / f"nba_{market}.json"
        with open(metadata_path, 'w') as f:
            json.dump(metadata, f, indent=2)
        logger.info(f"Saved metadata to {metadata_path}")

    def close(self):
        """Close database connection."""
        self.collector.close()


def main():
    """Main training entry point."""
    import argparse

    parser = argparse.ArgumentParser(description="Train NBA betting models")
    parser.add_argument("--data", default="apps/backend/data/historical_games.db",
                       help="Path to SQLite database")
    parser.add_argument("--output", default="apps/backend/data/models",
                       help="Path to save trained models")
    parser.add_argument("--log-level", default="INFO",
                       help="Logging level")

    args = parser.parse_args()

    # Setup logging
    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    # Train models
    trainer = ModelTrainer(args.data, args.output)
    try:
        results = trainer.train_nba_models()
        print("\n" + "="*60)
        print("TRAINING COMPLETE")
        print("="*60)
        for market, result in results.items():
            print(f"\n{market.upper()}:")
            for key, value in result.items():
                if key != 'feature_importances':
                    print(f"  {key}: {value}")
    except Exception as e:
        logger.error(f"Training failed: {e}", exc_info=True)
        print(f"\nERROR: {e}")
    finally:
        trainer.close()


if __name__ == "__main__":
    main()
