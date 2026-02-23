"""Betting Model Server for sports ML predictions.

Handles model loading, inference, and pick generation with confidence scores,
expected value calculations, and SHAP-based explanations.
"""

from __future__ import annotations

import json
import logging
import os
import pickle
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Tuple

if TYPE_CHECKING:
    from .cloud_provider import CloudProvider

logger = logging.getLogger(__name__)


class BettingModelServer:
    """
    Server for loading and serving betting ML models.

    Loads trained models from cloud storage or local paths, caches them in memory,
    and provides inference with confidence scores and explainability.
    """

    def __init__(
        self,
        models_dir: str,
        project_id: Optional[str] = None,
        cloud_provider: Optional[CloudProvider] = None,
    ):
        """
        Initialize betting model server.

        Args:
            models_dir: Directory containing pickled models
            project_id: Cloud project ID (GCP project ID if using GCP, ignored if cloud_provider provided)
            cloud_provider: Optional CloudProvider instance (GCP, AWS, Azure, etc.)
                           If not provided, attempts to initialize GCP provider if project_id available

        Raises:
            ValueError: If cloud_provider not provided and project_id not available
        """
        logger.info("Initializing BettingModelServer...")
        self.models_dir = Path(models_dir)
        self.project_id = project_id or os.environ.get("GOOGLE_CLOUD_PROJECT")
        self.models = {}
        self.model_metadata = {}

        # Setup cloud provider clients
        self.cloud_provider = cloud_provider
        self.analytics_client = None
        self.storage_client = None

        try:
            if self.cloud_provider:
                logger.info(
                    "Using provided cloud provider",
                    extra={"provider_id": self.cloud_provider.provider_id},
                )
                self.analytics_client = self.cloud_provider.analytics_client
                self.storage_client = self.cloud_provider.storage_client
            elif self.project_id:
                logger.info(
                    "Initializing GCP provider with project_id",
                    extra={"project_id": self.project_id},
                )
                from .gcp_client import GCPProvider

                self.cloud_provider = GCPProvider(self.project_id)
                self.analytics_client = self.cloud_provider.analytics_client
                self.storage_client = self.cloud_provider.storage_client
                logger.info(
                    "Cloud provider initialized",
                    extra={"provider_id": self.cloud_provider.provider_id},
                )
        except Exception as exc:
            logger.warning(
                "Failed to initialize cloud provider",
                extra={
                    "error": str(exc),
                    "error_type": type(exc).__name__,
                },
            )

        # Load all available models
        self._load_models()

    def _load_models(self) -> None:
        """Load all pickled models from models_dir."""
        if not self.models_dir.exists():
            logger.warning(
                "Models directory does not exist",
                extra={"models_dir": self.models_dir},
            )
            return

        logger.info(
            "Loading models from directory",
            extra={"models_dir": self.models_dir},
        )

        model_count = 0
        for model_file in self.models_dir.glob("*.pkl"):
            try:
                logger.debug(
                    "Loading model file",
                    extra={"model_file": model_file.name},
                )
                with open(model_file, "rb") as f:
                    model = pickle.load(f)
                model_name = model_file.stem
                self.models[model_name] = model
                model_count += 1
                logger.info(
                    "Model loaded",
                    extra={"model_name": model_name},
                )

                # Try to load metadata
                metadata_file = model_file.with_suffix(".json")
                if metadata_file.exists():
                    with open(metadata_file, "r") as f:
                        self.model_metadata[model_name] = json.load(f)
                    logger.debug(
                        "Model metadata loaded",
                        extra={"model_name": model_name},
                    )
            except Exception as exc:
                logger.error(
                    "Failed to load model",
                    extra={
                        "model_file": model_file.name,
                        "error": str(exc),
                        "error_type": type(exc).__name__,
                    },
                )

        logger.info(
            "Model loading completed",
            extra={"total_models_loaded": model_count},
        )

    def predict_game(
        self,
        sport: str,
        game_id: str,
        features: Dict[str, Any],
        markets: List[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Generate predictions for a game across specified markets.

        Args:
            sport: Sport ID (e.g., 'nba', 'nfl')
            game_id: Unique game identifier
            features: Feature dictionary for the game
            markets: List of market types to predict (spread, total, moneyline)

        Returns:
            List of predictions with format:
            [{
                'market': str,
                'selection': str (e.g., 'home', 'over'),
                'line': float,
                'confidence': float (0-1),
                'edge': float (expected value as decimal),
                'rationale': str,
                'risk_level': str ('low', 'medium', 'high'),
                'model_version': str,
                'timestamp': str
            }, ...]
        """
        if markets is None:
            markets = ["spread", "total"]

        predictions = []

        # Validate models exist
        if not self.models:
            logger.error("No models loaded")
            return predictions

        try:
            for market in markets:
                model_key = f"{sport}_{market}"

                # Skip if model not available
                if model_key not in self.models:
                    logger.debug(f"Model not found for {model_key}")
                    continue

                try:
                    model = self.models[model_key]
                    prediction = self._predict_market(
                        game_id=game_id,
                        sport=sport,
                        market=market,
                        features=features,
                        model=model,
                    )

                    if prediction:
                        predictions.append(prediction)
                except Exception as exc:
                    logger.error(
                        f"Prediction failed for {market}",
                        extra={
                            "game_id": game_id,
                            "sport": sport,
                            "market": market,
                            "error": str(exc),
                        },
                    )

            # Sort by confidence descending
            predictions = sorted(
                predictions, key=lambda p: p.get("confidence", 0), reverse=True
            )

            # Log predictions to BigQuery if available
            if self.bq_client:
                self._log_predictions_to_bq(game_id, sport, predictions)

        except Exception as exc:
            logger.error(
                f"predict_game failed",
                extra={"game_id": game_id, "sport": sport, "error": str(exc)},
            )

        return predictions

    def _predict_market(
        self,
        game_id: str,
        sport: str,
        market: str,
        features: Dict[str, Any],
        model: Any,
    ) -> Optional[Dict[str, Any]]:
        """
        Generate prediction for a specific market.

        Args:
            game_id: Game ID
            sport: Sport ID
            market: Market type
            features: Feature dictionary
            model: Loaded model

        Returns:
            Prediction dict or None if prediction invalid
        """
        try:
            # Extract feature vector (order matters - must match training)
            feature_vector = self._extract_feature_vector(market, features)

            if feature_vector is None:
                return None

            # Get model prediction (should return probability)
            if hasattr(model, "predict_proba"):
                # Classifier
                probs = model.predict_proba([feature_vector])[0]
                win_prob = max(probs)  # Probability of positive class
            else:
                # Regressor - treat as probability
                win_prob = model.predict([feature_vector])[0]
                win_prob = max(0, min(1, win_prob))  # Clamp to [0, 1]

            # Get default odds (-110 American)
            odds = -110
            decimal_odds = 1 + (100 / 110)  # ~1.909

            # Calculate edge
            edge = self._calculate_edge(win_prob, decimal_odds)

            # Filter by edge threshold (3% = breakeven at -110)
            if edge < 0.03:
                logger.debug(
                    f"Edge too low {edge} for {sport} {market}",
                    extra={"game_id": game_id},
                )
                return None

            # Determine selection and risk level
            selection = "home" if market != "total" else ("over" if win_prob > 0.5 else "under")
            risk_level = (
                "low" if win_prob > 0.65 else ("medium" if win_prob > 0.58 else "high")
            )

            # Get explanation
            rationale = self._explain_prediction(model, feature_vector, market)

            # Get line from features
            line = features.get(f"{market}_line", 0)

            model_version = self.model_metadata.get(
                f"{sport}_{market}", {}
            ).get("version", "v1")

            return {
                "market": market,
                "selection": selection,
                "line": line,
                "confidence": round(win_prob, 3),
                "edge": round(edge, 4),
                "rationale": rationale,
                "risk_level": risk_level,
                "model_version": model_version,
                "timestamp": datetime.utcnow().isoformat(),
            }

        except Exception as exc:
            logger.error(
                f"Market prediction failed",
                extra={
                    "game_id": game_id,
                    "market": market,
                    "error": str(exc),
                },
            )
            return None

    def _extract_feature_vector(
        self, market: str, features: Dict[str, Any]
    ) -> Optional[list]:
        """
        Extract feature vector for model input.

        This is a placeholder - actual implementation depends on
        specific features used in training.

        Args:
            market: Market type
            features: Feature dictionary

        Returns:
            Feature vector or None if invalid
        """
        try:
            # Placeholder feature extraction
            # Order must match training pipeline
            feature_names = [
                "home_elo",
                "away_elo",
                "home_avg_pts",
                "away_avg_pts",
                "home_avg_allowed",
                "away_avg_allowed",
                "rest_advantage",
                "is_playoff",
                "line",
            ]

            vector = []
            for feat_name in feature_names:
                value = features.get(feat_name, 0)
                # Handle missing values with mean/default
                if value is None:
                    value = 0
                vector.append(float(value))

            return vector

        except Exception as exc:
            logger.error(f"Feature extraction failed: {exc}")
            return None

    def _calculate_edge(self, win_prob: float, decimal_odds: float) -> float:
        """
        Calculate expected value (edge) for a bet.

        Edge = (win_prob * decimal_odds) - 1

        At -110 odds (decimal 1.909):
        - 55% win prob = 0.55 * 1.909 - 1 = 0.05 = 5% edge
        - 53.8% win prob = 0.538 * 1.909 - 1 = 0.03 = 3% edge (breakeven)
        - 52.4% win prob = 0.524 * 1.909 - 1 = 0.00 = 0% edge

        Args:
            win_prob: Probability of winning (0-1)
            decimal_odds: Decimal odds (e.g., 1.909 for -110)

        Returns:
            Edge as decimal (0.05 = 5%)
        """
        return (win_prob * decimal_odds) - 1

    def _explain_prediction(
        self, model: Any, features: list, market: str
    ) -> str:
        """
        Generate natural language explanation for prediction.

        Uses top feature importances or SHAP-like interpretation
        to generate a human-readable rationale.

        Args:
            model: Trained model
            features: Feature vector
            market: Market type

        Returns:
            Natural language explanation string
        """
        explanations = []

        try:
            # Try to get feature importances
            if hasattr(model, "feature_importances_"):
                importances = model.feature_importances_
                # Get top 3 feature indices
                top_indices = sorted(
                    range(len(importances)),
                    key=lambda i: importances[i],
                    reverse=True,
                )[:3]

                feature_names = [
                    "home elo",
                    "away elo",
                    "home scoring",
                    "away scoring",
                    "home defense",
                    "away defense",
                    "rest advantage",
                    "playoff status",
                    "line",
                ]

                for idx in top_indices:
                    if idx < len(feature_names):
                        explanations.append(feature_names[idx])

        except Exception as exc:
            logger.debug(f"Could not extract feature importances: {exc}")

        # Default explanations if none found
        if not explanations:
            explanations = ["favorable matchup", "statistical edge", "value play"]

        return f"Strong {market} pick based on {', '.join(explanations[:2])}"

    def _log_predictions_to_bq(
        self, game_id: str, sport: str, predictions: List[Dict[str, Any]]
    ) -> None:
        """
        Log predictions to analytics storage for tracking and evaluation.

        Args:
            game_id: Game ID
            sport: Sport ID
            predictions: List of predictions
        """
        try:
            if not self.analytics_client:
                logger.debug(
                    "Analytics client not available, skipping prediction logging"
                )
                return

            logger.debug(
                "Logging predictions to analytics storage",
                extra={
                    "game_id": game_id,
                    "sport": sport,
                    "prediction_count": len(predictions),
                },
            )

            rows = []
            for pred in predictions:
                row = {
                    "game_id": game_id,
                    "sport": sport,
                    "market": pred.get("market"),
                    "selection": pred.get("selection"),
                    "confidence": pred.get("confidence"),
                    "edge": pred.get("edge"),
                    "timestamp": datetime.utcnow().isoformat(),
                }
                rows.append(row)

            if rows:
                self.analytics_client.insert_rows("predictions", rows)
                logger.debug(
                    "Predictions logged to analytics storage",
                    extra={"row_count": len(rows)},
                )

        except Exception as exc:
            logger.error(
                "Failed to log predictions to analytics storage",
                extra={
                    "game_id": game_id,
                    "error": str(exc),
                    "error_type": type(exc).__name__,
                },
            )

    def health_check(self) -> Dict[str, Any]:
        """
        Check model server health.

        Returns:
            Health status dict with model and cloud provider availability
        """
        logger.info("Performing model server health check...")

        cloud_health = {}
        if self.cloud_provider:
            try:
                cloud_health = self.cloud_provider.health_check()
                logger.debug(
                    "Cloud provider health check",
                    extra={
                        "provider_id": self.cloud_provider.provider_id,
                        "status": cloud_health,
                    },
                )
            except Exception as exc:
                logger.error(
                    "Cloud provider health check failed",
                    extra={
                        "error": str(exc),
                        "error_type": type(exc).__name__,
                    },
                )

        health = {
            "models_loaded": len(self.models),
            "models": list(self.models.keys()),
            "cloud_provider": {
                "available": self.cloud_provider is not None,
                "provider_id": self.cloud_provider.provider_id
                if self.cloud_provider
                else None,
                "status": cloud_health,
            },
            "timestamp": datetime.utcnow().isoformat(),
        }

        logger.info(
            "Model server health check completed",
            extra={
                "models_loaded": len(self.models),
                "cloud_provider_available": self.cloud_provider is not None,
            },
        )

        return health
