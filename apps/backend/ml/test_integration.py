#!/usr/bin/env python3
"""End-to-end integration test for AI Picks Generator MVP."""

import sys
import os
import logging
from datetime import datetime

# Add backend to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def test_data_collection():
    """Test historical data collection."""
    logger.info("\n" + "="*60)
    logger.info("TEST 1: Data Collection")
    logger.info("="*60)

    try:
        from ml.data_collection import HistoricalDataCollector

        db_path = os.path.join(os.path.dirname(__file__), "..", "data", "historical_games.db")
        collector = HistoricalDataCollector(db_path)

        # Query database
        cursor = collector.conn.cursor()
        cursor.execute("SELECT COUNT(*) as count FROM games")
        count = cursor.fetchone()['count']

        logger.info(f"✓ Data Collection: {count} games in database")
        collector.close()
        return True

    except Exception as exc:
        logger.error(f"✗ Data Collection failed: {exc}")
        return False


def test_feature_extraction():
    """Test feature extraction."""
    logger.info("\n" + "="*60)
    logger.info("TEST 2: Feature Extraction")
    logger.info("="*60)

    try:
        from ml.data_collection import HistoricalDataCollector
        from ml.features import NBAFeatureExtractor

        db_path = os.path.join(os.path.dirname(__file__), "..", "data", "historical_games.db")
        collector = HistoricalDataCollector(db_path)
        extractor = NBAFeatureExtractor(collector)

        # Create a sample game dict
        sample_game = {
            'game_id': 'test_123',
            'date': '2026-02-02',
            'home_team_id': '30',
            'home_team_name': 'Hornets',
            'away_team_id': '24',
            'away_team_name': 'Spurs',
            'home_score': 111,
            'away_score': 106,
            'season': 2026
        }

        # Extract features
        features = extractor.extract_features(sample_game)
        feature_vector = features.to_feature_vector()

        logger.info(f"✓ Feature Extraction: {len(feature_vector)} features extracted")
        collector.close()
        return True

    except Exception as exc:
        logger.error(f"✗ Feature Extraction failed: {exc}")
        return False


def test_parlay_builder():
    """Test parlay building."""
    logger.info("\n" + "="*60)
    logger.info("TEST 3: Parlay Builder")
    logger.info("="*60)

    try:
        from ml.parlay_builder import ParlayBuilder, Pick

        builder = ParlayBuilder()

        # Create sample picks
        pick1 = Pick(
            pick_id="1",
            game_id="game1",
            bet_type="spread",
            selection="home",
            line=-2.5,
            odds=-110,
            confidence=0.58,
            edge=0.05,
            home_team="Lakers",
            away_team="Celtics"
        )

        pick2 = Pick(
            pick_id="2",
            game_id="game2",
            bet_type="spread",
            selection="home",
            line=-3.5,
            odds=-110,
            confidence=0.59,
            edge=0.04,
            home_team="Warriors",
            away_team="Nuggets"
        )

        # Build parlay
        parlay = builder.build_standard_parlay([pick1, pick2], max_legs=2)

        if parlay:
            logger.info(f"✓ Parlay Builder: {len(parlay.picks)}-leg parlay with odds {parlay.combined_odds}")
            return True
        else:
            logger.error("✗ Parlay Builder: Failed to build parlay")
            return False

    except Exception as exc:
        logger.error(f"✗ Parlay Builder failed: {exc}")
        return False


def test_prompt_interpreter():
    """Test prompt interpretation."""
    logger.info("\n" + "="*60)
    logger.info("TEST 4: Prompt Interpreter")
    logger.info("="*60)

    try:
        from ml.prompt_interpreter import PromptInterpreter

        interpreter = PromptInterpreter()

        # Test various prompts
        prompts = [
            "I think Lakers will dominate the paint",
            "Expecting a high-scoring game",
            "Warriors should struggle on back-to-backs"
        ]

        for prompt in prompts:
            interpretation = interpreter.parse_prompt(prompt)
            logger.info(f"  Prompt: '{prompt}'")
            logger.info(f"  → Scenario: {interpretation.scenario}")
            logger.info(f"  → Keywords: {list(interpretation.keywords)[:3] if interpretation.keywords else []}...")

        logger.info(f"✓ Prompt Interpreter: Successfully parsed {len(prompts)} prompts")
        return True

    except Exception as exc:
        logger.error(f"✗ Prompt Interpreter failed: {exc}")
        return False


def test_reasoning_generator():
    """Test reasoning generation."""
    logger.info("\n" + "="*60)
    logger.info("TEST 5: Reasoning Generator")
    logger.info("="*60)

    try:
        from ml.reasoning import ReasoningGenerator
        from ml.parlay_builder import Pick

        generator = ReasoningGenerator()

        # Create a sample pick
        pick = Pick(
            pick_id="1",
            game_id="game1",
            bet_type="spread",
            selection="home",
            line=-2.5,
            odds=-110,
            confidence=0.58,
            edge=0.05,
            home_team="Lakers",
            away_team="Celtics"
        )

        # Sample features
        features = {
            'home_pts_avg': 110.5,
            'away_pts_avg': 105.2,
            'home_win_pct': 0.60,
            'away_win_pct': 0.55,
            'home_rest_days': 2,
            'away_rest_days': 1
        }

        # Generate reasoning
        reasoning = generator.generate_reasoning(
            pick=pick,
            features=features,
            user_prompt="Lakers will dominate",
            user_scenario="blowout"
        )

        logger.info(f"✓ Reasoning Generator: Generated reasoning with {len(reasoning.key_factors)} key factors")
        logger.info(f"  Summary: {reasoning.summary}")
        return True

    except Exception as exc:
        logger.error(f"✗ Reasoning Generator failed: {exc}")
        return False


def test_models_available():
    """Test that trained models are available."""
    logger.info("\n" + "="*60)
    logger.info("TEST 6: Trained Models")
    logger.info("="*60)

    try:
        import pickle
        from pathlib import Path

        models_dir = Path(os.path.dirname(__file__)).parent / "data" / "models"

        models_required = ["nba_spread.pkl", "nba_total.pkl", "nba_moneyline.pkl"]
        models_found = []

        for model_file in models_required:
            model_path = models_dir / model_file
            if model_path.exists():
                # Try to load the model
                with open(model_path, 'rb') as f:
                    model = pickle.load(f)
                models_found.append(model_file)

        logger.info(f"✓ Trained Models: Found {len(models_found)}/{len(models_required)} models")
        for model in models_found:
            logger.info(f"  - {model}")

        return len(models_found) == len(models_required)

    except Exception as exc:
        logger.error(f"✗ Trained Models test failed: {exc}")
        return False


def run_all_tests():
    """Run all integration tests."""
    logger.info("\n\n")
    logger.info("╔" + "="*58 + "╗")
    logger.info("║" + " "*15 + "AI PICKS GENERATOR MVP - TEST SUITE" + " "*9 + "║")
    logger.info("╚" + "="*58 + "╝")

    tests = [
        ("Data Collection", test_data_collection),
        ("Feature Extraction", test_feature_extraction),
        ("Parlay Builder", test_parlay_builder),
        ("Prompt Interpreter", test_prompt_interpreter),
        ("Reasoning Generator", test_reasoning_generator),
        ("Trained Models", test_models_available),
    ]

    results = {}
    for test_name, test_func in tests:
        try:
            results[test_name] = test_func()
        except KeyboardInterrupt:
            logger.info("\n✓ Tests interrupted by user")
            break
        except Exception as exc:
            logger.error(f"✗ Unexpected error in {test_name}: {exc}")
            results[test_name] = False

    # Summary
    logger.info("\n\n" + "="*60)
    logger.info("TEST SUMMARY")
    logger.info("="*60)

    passed = sum(1 for v in results.values() if v)
    total = len(results)

    for test_name, passed_flag in results.items():
        status = "✓ PASS" if passed_flag else "✗ FAIL"
        logger.info(f"{status}: {test_name}")

    logger.info(f"\nTotal: {passed}/{total} tests passed")
    logger.info("="*60)

    return passed == total


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
