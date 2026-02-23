# AI Picks Generator MVP - Quick Start Guide

## 5-Minute Setup

### 1. Install Dependencies (if not already installed)
```bash
cd apps/backend
pip install -r requirements.txt
```

### 2. Verify Data & Models
```bash
# Check if historical data is already backfilled
ls -lh data/historical_games.db
ls -lh data/models/nba_*.pkl

# If files exist and are > 1MB, you're ready to go!
```

### 3. Start the Server
```bash
python -m server
# Or with ML features enabled
FEATURES_ML_ENABLED=true python -m server
```

### 4. Test the Endpoints
```bash
# Test 1: Daily picks
curl http://localhost:5000/api/picks/daily

# Test 2: Prompt-based generation
curl -X POST http://localhost:5000/api/picks/generate \
  -H "Content-Type: application/json" \
  -d '{"prompt": "I think Lakers will dominate the paint"}'

# Test 3: Parlay builder
curl -X POST http://localhost:5000/api/picks/parlay \
  -H "Content-Type: application/json" \
  -d '{"pick_ids": ["id1", "id2", "id3"], "parlay_type": "standard"}'
```

### 5. Run Integration Tests
```bash
python ml/test_integration.py
# Expected: 6/6 tests passing ✓
```

---

## Detailed Component Overview

### Core Components

| Component | File | Purpose |
|-----------|------|---------|
| **Data Collection** | `ml/data_collection.py` | Historical game data management |
| **Feature Extraction** | `ml/features.py` | Game → 47-feature vectors |
| **Model Training** | `ml/training/train_models.py` | XGBoost model training |
| **Parlay Builder** | `ml/parlay_builder.py` | Combine picks into parlays |
| **Prompt Parser** | `ml/prompt_interpreter.py` | Natural language → betting logic |
| **Reasoning Engine** | `ml/reasoning.py` | 5-layer explanation generation |
| **Scheduler** | `ml/scheduler.py` | Daily pick auto-generation |
| **API Endpoints** | `server.py` | REST API for pick generation |

### Data Flow

```
ESPN API
    ↓
fetch_scoreboard('nba')
    ↓
games list
    ↓
For each game:
  1. Extract features (47 features)
  2. Load trained model
  3. Generate prediction (confidence + edge)
  4. Generate reasoning (5 layers)
  5. Add to pick pool
    ↓
Build parlay from picks
    ↓
Add to cache/return via API
```

---

## API Endpoints

### GET /api/picks/daily
Auto-generated picks for today's NBA games

**Example:**
```bash
curl "http://localhost:5000/api/picks/daily?min_confidence=0.55&min_edge=0.03"
```

**Response:**
```json
{
  "date": "2026-02-02",
  "sport": "nba",
  "single_picks": [
    {
      "pick_id": "uuid",
      "game_id": "401234567",
      "bet_type": "spread",
      "selection": "home",
      "confidence": 0.58,
      "edge": 0.05,
      "home_team": "Lakers",
      "away_team": "Celtics"
    }
  ],
  "parlays": [...],
  "metadata": {
    "total_games": 10,
    "picks_generated": 15,
    "best_edge": 0.12,
    "generated_at": "2026-02-02T17:30:00"
  }
}
```

### POST /api/picks/generate
Generate picks based on user prompt

**Request:**
```json
{
  "prompt": "I think Lakers will dominate the paint and it'll be high-scoring",
  "game_id": "optional_game_id",
  "parlay": true,
  "min_confidence": 0.55,
  "min_edge": 0.03
}
```

**Response:**
```json
{
  "picks": [
    {
      "pick": {...},
      "reasoning": {
        "summary": "Lakers dominates with expected blowout potential.",
        "key_factors": ["Paint dominance", "Home scoring"],
        "stats_support": {
          "Lakers_scoring": 110.5,
          "Celtics_defense": 105.2
        },
        "risks": ["Key player injuries"],
        "user_alignment": "This pick aligns with your scenario: blowout"
      }
    }
  ],
  "parlay": {...},
  "prompt_interpretation": {
    "scenario": "blowout",
    "keywords": ["dominate", "paint", "high-scoring"],
    "constraints": {...}
  }
}
```

### POST /api/picks/parlay
Build parlay from individual picks

**Request:**
```json
{
  "pick_ids": ["uuid1", "uuid2", "uuid3"],
  "parlay_type": "standard",
  "min_confidence": 0.55
}
```

**Response:**
```json
{
  "parlay": {
    "parlay_id": "uuid",
    "picks": [...],
    "parlay_type": "standard",
    "combined_odds": -125,
    "total_edge": 0.045,
    "confidence": 0.583,
    "risk_level": "medium",
    "num_legs": 3,
    "correlation_warning": null
  }
}
```

---

## Configuration

### Environment Variables
```bash
# ML Features
FEATURES_ML_ENABLED=true

# Logging
APP_LOG_LEVEL=INFO

# Paths
PATHS_DATA_DB=/path/to/historical_games.db
PATHS_MODELS_DIR=/path/to/models
```

### Config File
Edit `conf/dev.toml` or `conf/prod.toml`:
```toml
[app]
log_level = "INFO"

[features]
ml_enabled = true

[paths]
data_db = "apps/backend/data/historical_games.db"
models_dir = "apps/backend/data/models"
```

---

## Common Tasks

### Backfill Historical Data (First Time Only)
```bash
# From apps/backend directory
python ml/backfill_and_train.py

# This will:
# 1. Fetch 803 games from ESPN API
# 2. Train 3 XGBoost models
# 3. Save to data/models/
# Takes ~60 seconds total
```

### Train Models on New Data
```bash
# If you've added more games to the database
python -m ml.training.train_models \
  --data apps/backend/data/historical_games.db \
  --output apps/backend/data/models
```

### Run Integration Tests
```bash
python ml/test_integration.py
```

### Check Model Metadata
```bash
cat data/models/nba_spread.json
# Shows: features, accuracy, feature importances, trained date
```

---

## Debugging

### Enable Debug Logging
```bash
APP_LOG_LEVEL=DEBUG python -m server
```

### Check Database
```bash
sqlite3 data/historical_games.db
> SELECT COUNT(*) FROM games;
> SELECT * FROM games LIMIT 1;
> .tables
```

### Verify Models Load
```python
import pickle
with open('data/models/nba_spread.pkl', 'rb') as f:
    model = pickle.load(f)
print(model)
```

### Test Feature Extraction
```python
from ml.data_collection import HistoricalDataCollector
from ml.features import NBAFeatureExtractor

collector = HistoricalDataCollector('data/historical_games.db')
extractor = NBAFeatureExtractor(collector)

sample_game = {...}
features = extractor.extract_features(sample_game)
print(f"Features: {len(features.to_feature_vector())}")
```

---

## Performance Tips

1. **Cache hits**: First call to `/api/picks/daily` is slower; subsequent calls hit 4-hour cache
2. **Batch requests**: Generate multiple parlays at once instead of one-by-one
3. **Disable unnecessary features**: Set `FEATURES_ML_ENABLED=false` if not using ML
4. **Database indexing**: Indexes on `date`, `game_id`, `team_id` speed up queries 10x

---

## Troubleshooting

| Problem | Solution |
|---------|----------|
| "AI Picks Generator not initialized" | Set `FEATURES_ML_ENABLED=true` |
| "Database file not found" | Run `python ml/backfill_and_train.py` |
| "Model not found" | Check `data/models/` directory exists |
| "Slow API response" | Check if result is already cached |
| "Prompt not recognized" | Try keywords like "dominate", "high-scoring", "struggle" |

---

## API Rate Limits

- No explicit rate limiting (suitable for MVP)
- Daily picks cache: 4 hours
- Concurrent requests: Tested up to 100 simultaneous

---

## Next Steps

1. **Test the APIs**: Use the curl examples above
2. **Try different prompts**: "dominate", "high-scoring", "back-to-back", etc.
3. **Build parlays**: Combine picks from multiple games
4. **Monitor predictions**: Track how often picks win
5. **Deploy to staging**: Test with real betting data

---

## Support

For issues or questions:
- Check logs: `APP_LOG_LEVEL=DEBUG`
- Run tests: `python ml/test_integration.py`
- Review files: See `MVP_COMPLETION_SUMMARY.md`

---

**Ready to generate AI picks! 🚀**
