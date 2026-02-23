# AI Picks Generator - Developer Reference

**Quick reference for developers working with the AI Picks Generator MVP**

---

## Project Structure

```
apps/backend/                    # Python Flask API
├── ml/                         # ML components
│   ├── data_collection.py      # SQLite management
│   ├── features.py             # 47-feature extraction
│   ├── parlay_builder.py       # Parlay logic
│   ├── prompt_interpreter.py   # Prompt parsing
│   ├── reasoning.py            # Explanation generation
│   ├── scheduler.py            # Daily jobs
│   ├── training/               # Model training
│   │   └── train_models.py     # XGBoost training
│   └── test_integration.py     # Test suite
├── data/                       # Data & models
│   ├── historical_games.db     # SQLite database
│   └── models/                 # Trained XGBoost models
└── server.py                   # Flask API

apps/web/                       # React frontend
├── src/
│   ├── AIPicksDaily.jsx        # Daily picks component
│   ├── AIPicksGenerate.jsx     # Prompt-based generation
│   ├── AIPicksParlay.jsx       # Parlay builder
│   ├── App.js                  # Main app (integrated)
│   └── index.css               # Styling (updated)
```

---

## Quick Commands

### Backend

```bash
# Install dependencies
cd apps/backend && pip install -r requirements.txt

# Run server
python -m server

# Run tests
python ml/test_integration.py

# Backfill data & train (one-time)
python ml/backfill_and_train.py

# Check database
sqlite3 data/historical_games.db "SELECT COUNT(*) FROM games;"

# Load model metadata
cat data/models/nba_spread.json
```

### Frontend

```bash
# Install dependencies
npm install

# Start dev server
cd apps/web && npm start

# Build for production
cd apps/web && npm build

# Run tests
cd apps/web && npm test
```

---

## API Endpoints

### GET /api/picks/daily
Auto-generated picks for today

```bash
curl http://localhost:5000/api/picks/daily

# With thresholds
curl "http://localhost:5000/api/picks/daily?min_confidence=0.55&min_edge=0.03"
```

**Response**:
```json
{
  "date": "2026-02-02",
  "sport": "nba",
  "single_picks": [...],
  "parlays": [...],
  "metadata": {
    "total_games": 10,
    "picks_generated": 15,
    "best_edge": 0.12
  }
}
```

### POST /api/picks/generate
Prompt-based pick generation

```bash
curl -X POST http://localhost:5000/api/picks/generate \
  -H "Content-Type: application/json" \
  -d '{
    "prompt": "Lakers will dominate the paint",
    "min_confidence": 0.55,
    "min_edge": 0.03,
    "parlay": true
  }'
```

**Response**:
```json
{
  "picks": [{
    "pick": {...},
    "reasoning": {
      "summary": "...",
      "key_factors": [...],
      "stats_support": {...},
      "risks": [...],
      "user_alignment": "..."
    }
  }],
  "parlay": {...},
  "prompt_interpretation": {...}
}
```

### POST /api/picks/parlay
Build parlay from picks

```bash
curl -X POST http://localhost:5000/api/picks/parlay \
  -H "Content-Type: application/json" \
  -d '{
    "pick_ids": ["id1", "id2", "id3"],
    "parlay_type": "standard"
  }'
```

**Response**:
```json
{
  "parlay": {
    "parlay_id": "uuid",
    "num_legs": 3,
    "combined_odds": -125,
    "total_edge": 0.045,
    "confidence": 0.583,
    "risk_level": "medium"
  }
}
```

---

## Frontend Components

### AIPicksDaily
Displays auto-generated daily picks

```jsx
import AIPicksDaily from './AIPicksDaily';

// Usage in App.js
<AIPicksDaily authToken={authToken} />
```

**Props**:
- `authToken` (string): Bearer token for API calls

**Behavior**:
- Fetches `/api/picks/daily` on mount
- Displays picks with expandable details
- Shows suggested parlays

### AIPicksGenerate
Prompt-based pick generation

```jsx
import AIPicksGenerate from './AIPicksGenerate';

// Usage in App.js
<AIPicksGenerate authToken={authToken} />
```

**Props**:
- `authToken` (string): Bearer token for API calls

**Behavior**:
- Form for user prompt input
- Adjustable confidence/edge thresholds
- Displays full reasoning with 5 layers

### AIPicksParlay
Parlay builder with pick selection

```jsx
import AIPicksParlay from './AIPicksParlay';

// Usage in App.js
<AIPicksParlay authToken={authToken} />
```

**Props**:
- `authToken` (string): Bearer token for API calls

**Behavior**:
- Fetches daily picks on mount
- User selects 2-5 picks
- Builds parlay with correlation warnings

---

## Database Schema

### games
```sql
CREATE TABLE games (
  game_id TEXT PRIMARY KEY,
  date DATE,
  home_team TEXT,
  away_team TEXT,
  home_score INT,
  away_score INT,
  spread REAL,
  total REAL,
  home_ml_odds INT,
  away_ml_odds INT
);
CREATE INDEX idx_games_date ON games(date);
```

### team_game_stats
```sql
CREATE TABLE team_game_stats (
  game_id TEXT,
  team_id TEXT,
  fg_pct REAL,
  three_pt_pct REAL,
  rebounds INT,
  assists INT,
  turnovers INT
);
CREATE INDEX idx_team_game_stats_team ON team_game_stats(team_id);
```

### game_features
```sql
CREATE TABLE game_features (
  game_id TEXT PRIMARY KEY,
  features JSON
);
```

---

## ML Model Information

### Available Models
- `nba_spread.pkl` - Spread prediction (classification)
- `nba_total.pkl` - Total prediction (regression)
- `nba_moneyline.pkl` - Moneyline prediction (classification)

### Model Performance
| Model | Type | Accuracy/MAE |
|-------|------|--------------|
| Spread | Classification | 42.15% |
| Total | Regression | MAE: 18.53 |
| Moneyline | Classification | 47.11% |

### Feature List (47 features)
1. home_pts_avg
2. away_pts_avg
3. home_pts_allowed_avg
4. away_pts_allowed_avg
5. home_win_pct
6. away_win_pct
7. home_rest_days
8. away_rest_days
9. home_back_to_back
10. away_back_to_back
... (37 more features)

See `ml/features.py` for complete list.

---

## Configuration

### Environment Variables
```bash
# ML Features
FEATURES_ML_ENABLED=true

# Logging
APP_LOG_LEVEL=INFO

# Paths
PATHS_DATA_DB=apps/backend/data/historical_games.db
PATHS_MODELS_DIR=apps/backend/data/models
```

### Config Files
- `conf/dev.toml` - Development config
- `conf/prod.toml` - Production config

---

## Testing

### Run All Tests
```bash
python ml/test_integration.py
```

### Individual Test Runs
```python
# Test data collection
from ml.data_collection import HistoricalDataCollector
collector = HistoricalDataCollector('apps/backend/data/historical_games.db')

# Test features
from ml.features import NBAFeatureExtractor
extractor = NBAFeatureExtractor(collector)

# Test parlay builder
from ml.parlay_builder import ParlayBuilder, Pick
builder = ParlayBuilder()

# Test prompt interpreter
from ml.prompt_interpreter import PromptInterpreter
interpreter = PromptInterpreter()

# Test reasoning
from ml.reasoning import ReasoningGenerator
generator = ReasoningGenerator()
```

---

## Common Tasks

### Add a New Betting Keyword
Edit `ml/prompt_interpreter.py`:
```python
BETTING_KEYWORDS = {
    "new_keyword": {
        "implications": ["implication1", "implication2"],
        "selection_bias": "home"  # or "away"
    }
}
```

### Adjust Correlation Thresholds
Edit `ml/parlay_builder.py`:
```python
KNOWN_CORRELATIONS = {
    ('spread', 'total'): 0.3,  # Adjust this value
    ('home_spread', 'away_total'): 0.4,
}
```

### Add New Reasoning Layer
Edit `ml/reasoning.py`:
```python
def generate_reasoning(self, pick, features):
    return {
        'summary': '...',
        'key_factors': [...],
        'stats_support': {...},
        'risks': [...],
        'user_alignment': '...',
        'new_layer': '...'  # Add here
    }
```

### Update Frontend Component
Edit `apps/web/src/AIPicks*.jsx`:
- Change styling in JSX inline styles
- Add new props to component
- Update API call if needed

### Modify CSS
Edit `apps/web/src/index.css`:
```css
.ai-picks-tab {
  /* Add or modify styles */
}
```

---

## Debugging

### Backend Logging
```bash
APP_LOG_LEVEL=DEBUG python -m server
```

### Check Database
```bash
sqlite3 apps/backend/data/historical_games.db

# Useful queries:
SELECT COUNT(*) FROM games;
SELECT * FROM games LIMIT 1;
.tables
.schema games
SELECT * FROM game_features LIMIT 1;
```

### Test API Endpoint
```bash
# Get daily picks
curl http://localhost:5000/api/picks/daily | jq .

# Generate from prompt
curl -X POST http://localhost:5000/api/picks/generate \
  -H "Content-Type: application/json" \
  -d '{"prompt":"test"}' | jq .

# Build parlay (need actual pick IDs)
curl -X POST http://localhost:5000/api/picks/parlay \
  -H "Content-Type: application/json" \
  -d '{"pick_ids":["id1","id2"],"parlay_type":"standard"}' | jq .
```

### Frontend Console
```javascript
// Check API responses
fetch('/api/picks/daily').then(r => r.json()).then(console.log)

// Check component state
// Use React Developer Tools browser extension
```

---

## Performance Tips

1. **Database**: Queries are fast with indexes. To speed up:
   - Add more indexes if querying by new fields
   - Analyze slow queries with EXPLAIN PLAN

2. **API**: Uses 4-hour cache. To clear:
   - Restart Flask server
   - Or modify cache timeout in server.py

3. **Models**: Load once on startup. To optimize:
   - Cache models in memory (already done)
   - Use ONNX format for faster inference (future)

4. **Frontend**:
   - Components fetch on mount
   - No polling enabled
   - Add pagination for large pick lists (future)

---

## Deployment Checklist

- [ ] Backend server running
- [ ] Database backfilled (803 games)
- [ ] Models trained and saved
- [ ] API endpoints responding
- [ ] Frontend dev server running
- [ ] All tests passing (6/6)
- [ ] Environment variables set
- [ ] CORS configured (if needed)
- [ ] SSL/TLS enabled (production)
- [ ] Error monitoring enabled (production)

---

## Useful Resources

- **ESPN API**: https://github.com/pseudo-r/Public-ESPN-API
- **XGBoost Docs**: https://xgboost.readthedocs.io/
- **React Docs**: https://react.dev/
- **SQLite Docs**: https://www.sqlite.org/docs.html

---

## Team Notes

### For ML Engineers
- Focus on feature engineering for accuracy improvement
- Current models use limited data (803 games)
- Add more historical seasons for better training
- Consider ensemble methods or gradient boosting tuning

### For Frontend Engineers
- Components are ready to extend with new features
- CSS uses CSS variables for easy theming
- Add responsive breakpoints for mobile
- Consider adding charts/visualizations

### For DevOps
- Backend uses Flask (single threaded, use Gunicorn for production)
- Database is SQLite (fine for MVP, consider PostgreSQL for scale)
- Scheduler runs in background (use Celery + Redis for production)
- Cache is in-memory (use Redis for multi-server setup)

---

## Quick Troubleshooting

| Issue | Solution |
|-------|----------|
| "AI Picks tab not showing" | Check App.js imports and state |
| "API endpoint not found" | Check server.py is running on port 5000 |
| "Models not loading" | Check models/ directory exists with .pkl files |
| "Database locked" | Check no other processes using SQLite |
| "No picks generated" | Check min_confidence and min_edge thresholds |
| "Styling looks broken" | Clear browser cache, check index.css is loaded |

---

**Last Updated**: February 2, 2026
**Version**: MVP 1.0
