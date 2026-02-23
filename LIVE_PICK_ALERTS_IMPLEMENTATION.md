# Live Pick Alerts MVP - Implementation Guide

## Overview

**Live Pick Alerts** is now the MVP for YoureEdge. This document outlines what has been built, the architecture, and what still needs to be integrated.

## What's Been Built ✅

### Backend Infrastructure

#### 1. **User Tier System** (`apps/backend/user_store.py`)
- Three subscription tiers: Free, Pro, Elite
- Default: All dev users on Elite tier (unlimited features)
- Tier features include:
  - `allowed_sports`: Which sports user can get alerts for
  - `max_favorite_teams`: Max teams to follow (null = unlimited)
  - `max_alerts_per_day`: Alert frequency cap (null = unlimited)
  - `custom_game_subscriptions`: Allow picking specific games
  - `notification_channels`: In-app, email, SMS, push (configurable per tier)
  - `custom_ev_threshold`: Can set custom EV thresholds

**Functions Added:**
- `_get_default_tier_features()` - Tier configuration templates
- `_get_default_alert_preferences()` - Default user preferences
- `get_user_tier()`, `set_user_tier()` - Tier management
- `get_user_tier_features()` - Get tier limits
- `get_user_alert_preferences()`, `update_user_alert_preferences()` - Preference management
- `increment_daily_alert_count()`, `get_daily_alert_count()` - Track alert quota

#### 2. **Tier Validator** (`apps/backend/alerts/tier_validator.py`)
Checks if user is allowed to receive an alert based on:
- Alerts enabled?
- Sport in allowed list?
- Team in favorites (if list is set)?
- Custom game subscribed (if using subscriptions)?
- Daily limit exceeded?
- In quiet hours?

**Functions:**
- `is_alert_allowed_for_user(user_id, alert_data)` - Main validation
- `get_user_notification_channels(user_id)` - Which channels to use
- `can_use_custom_ev_threshold(user_id)` - Tier check
- `get_user_ev_threshold(user_id)` - Get user's EV trigger

#### 3. **Real-Time Game Monitor** (`apps/backend/alerts/game_monitor.py`)
Polls ESPN API for live game changes (score, period, status)

**Architecture:**
- `fetch_live_games(sport)` - Get current live games
- `extract_game_info(game)` - Parse ESPN data
- `normalize_game_id(game)` - Stable game ID generation
- `get_game_state_change(game_id, new_game_info)` - Detect momentum shifts
- `monitor_live_games(sport)` - Main polling loop
- `get_all_live_games(sport)` - Current live games

**Returns for each game change:**
```python
{
  "type": "score_change|period_change|game_ended|game_started",
  "game_id": "...",
  "home_team": "...",
  "away_team": "...",
  "current_score": "...",
  "margin": int,
  "period": int,
  "clock": str
}
```

#### 4. **EV Calculation Engine** (`apps/backend/alerts/ev_calculator.py`)
Compares model predictions vs. market odds

**Functions:**
- `american_to_probability(odds)` - Convert -110 to ~0.5 prob
- `probability_to_american(probability)` - Reverse conversion
- `calculate_payout(stake, odds)` - Potential winnings
- `calculate_ev(model_probability, market_odds, stake)` - EV analysis
- `is_ev_positive(ev_analysis, min_threshold)` - Check EV threshold
- `evaluate_opportunity(game_info, model_prediction, market_odds, min_ev_threshold)` - Find best opportunity

**Returns:**
```python
{
  "market_probability": 0.52,
  "model_probability": 0.65,
  "probability_edge": 0.13,
  "payout_if_win": 195.45,
  "ev_dollars": 12.50,
  "ev_percentage": 12.5,
  "is_positive_ev": True
}
```

#### 5. **Alert Detection System** (`apps/backend/alerts/alert_detector.py`)
Orchestrates game monitoring, EV calc, tier validation, and alert storage

**Architecture:**
- `detect_alerts_for_user(user_id, game_changes)` - Find opportunities for user
- `add_user_alerts(user_id, alerts)` - Store in user profile
- `run_alert_detection(sport)` - Main detection loop (called by scheduler)
- `get_user_active_alerts(user_id)` - Get non-expired alerts
- `mark_alert_viewed(user_id, alert_id)` - User sees alert
- `dismiss_alert(user_id, alert_id)` - User dismisses alert

**Alert Structure:**
```python
{
  "alert_id": "uuid",
  "game_id": "...",
  "home_team": "Lakers",
  "away_team": "Celtics",
  "current_score": "45-38",
  "margin": 7,
  "opportunity_type": "moneyline|spread|total",
  "pick": "home|away|over|under",
  "model_win_prob": 0.65,
  "market_odds": -110,
  "ev": {...},  # From EV calculator
  "recommendation": "strong_buy|buy|fair_value",
  "status": "new|viewed|dismissed",
  "created_at": "2026-01-30T...",
  "expires_at": "2026-01-30T..."  # 5 min TTL
}
```

#### 6. **Alert API Endpoints** (`apps/backend/server.py`)

**New Endpoints Added:**

1. **GET /api/live-alerts**
   - Returns: List of active (non-expired) alerts for user
   - Auth: Required (Bearer token)
   - Response: `{ alerts: [...], user: "...", tier: "elite", total: int }`

2. **GET /api/alert-preferences**
   - Returns: User's current alert preferences
   - Auth: Required
   - Response: `{ preferences: {...}, tier: "elite" }`

3. **POST /api/alert-preferences**
   - Updates: User's alert preferences
   - Auth: Required
   - Body:
     ```json
     {
       "alerts_enabled": true,
       "favorite_teams": ["Lakers", "Warriors"],
       "favorite_sports": ["nba"],
       "min_ev_threshold": 5,
       "quiet_hours": {"start": "23:00", "end": "08:00"},
       "subscribed_games": [
         {"home": "Lakers", "away": "Celtics", "sport": "nba"}
       ]
     }
     ```

4. **POST /api/alerts/{alert_id}/dismiss**
   - Dismisses an alert
   - Returns: `{ dismissed: true, alert_id: "..." }`

5. **POST /api/alerts/{alert_id}/view**
   - Marks alert as viewed
   - Returns: `{ viewed: true, alert_id: "..." }`

### Frontend Components

#### 1. **LiveAlerts.jsx** (`apps/web/src/LiveAlerts.jsx`)
Displays real-time EV-positive betting opportunities

**Features:**
- Polls `/api/live-alerts` every 10 seconds
- Shows active alerts with:
  - Team matchup + current score
  - Recommendation badge (Strong Buy / Buy / Fair Value)
  - Opportunity type and pick
  - Model probability vs market probability
  - EV breakdown (probability edge, payout, EV %)
  - "Place Bet" and "Dismiss" buttons
  - Time until alert expires
- Requires authentication

#### 2. **AlertSettings.jsx** (`apps/web/src/AlertSettings.jsx`)
User preference management

**Features:**
- Toggle alerts on/off
- Set EV threshold (slider 0-20%)
- Select favorite sports (NBA, NFL, NCAAF, etc.)
- Select favorite teams (grid UI)
- Quiet hours configuration (time pickers)
- Save preferences button
- All preferences persist to backend

#### 3. **Integration with App.js**
- Imported both components
- Added "Live" tab → renders `<LiveAlerts>`
- Added "Settings" tab → renders `<AlertSettings>`

## Architecture Flow

```
Live Game Starts
    ↓
[Game Monitor] polls ESPN API every 10-30 seconds
    ↓
Detects game state change (score, momentum)
    ↓
[Alert Detector] for each user:
    - Get live odds for game
    - Get model prediction for game
    - Calculate EV opportunity
    - Apply tier/preference filters
    ↓
[EV Calculator] compares:
    Model Win Prob (65%) vs Market Prob (52%)
    → EV = +12.5%
    ↓
[Tier Validator] checks:
    - Sport allowed? ✓
    - Team in favorites? ✓
    - Daily limit hit? ✗
    - Quiet hours? ✗
    ↓
Create Alert & Store in User Profile
    ↓
[Frontend] polls /api/live-alerts every 10s
    ↓
User sees alert with "Place Bet" button
```

## What Still Needs Integration

### 1. **Scheduler Integration**
Need to set up APScheduler to run `run_alert_detection()` continuously

**In `apps/backend/server.py` or new `background_tasks.py`:**
```python
from apscheduler.schedulers.background import BackgroundScheduler
from alerts.alert_detector import run_alert_detection

scheduler = BackgroundScheduler()

# Run every 15 seconds for NBA
scheduler.add_job(
    func=lambda: run_alert_detection('nba'),
    trigger="interval",
    seconds=15,
    id="monitor_nba_alerts"
)

scheduler.start()
```

### 2. **Live Odds Integration**
Replace placeholder in `alerts/alert_detector.py:get_live_odds_for_game()`

Currently returns `None`. Need to:
- Call `odds/providers/odds_api.py` to get live odds
- Parse market odds for moneyline, spread, total
- Handle caching (OddsAPI has 5-min TTL)

**Mock implementation for testing:**
```python
def get_live_odds_for_game(game_id: str) -> dict:
    # TODO: Call odds provider with game_id
    return {
        "home_moneyline": -110,
        "away_moneyline": -110,
        "home_spread": -5.5,
        "home_spread_odds": -110,
        "total": 215,
        "over_odds": -110,
        "under_odds": -110,
    }
```

### 3. **Live Model Predictions**
Replace placeholder in `alerts/alert_detector.py:get_model_prediction_for_game()`

Currently returns `None`. Need to:
- Adapt `ml/model_server.py` for mid-game predictions
- Enhance `sports_ai/snapshot_builder.py` for live features
- Create endpoint for live prediction requests

**Mock implementation for testing:**
```python
def get_model_prediction_for_game(game_info: dict) -> dict:
    # TODO: Call model server for live predictions
    return {
        "home_win_prob": 0.65,
        "away_win_prob": 0.35,
        "home_spread_prob": 0.58,
    }
```

### 4. **Notification Channels** (Phase 2+)
Infrastructure ready, but actual delivery not implemented:
- **Email**: Need SendGrid/AWS SES integration
- **SMS**: Need Twilio integration
- **Push**: Need Firebase Cloud Messaging

For now, alerts are stored and served via `/api/live-alerts` (in-app notifications).

### 5. **Tests**
No tests written yet. Recommended:
- Unit tests for EV calculator
- Unit tests for tier validator
- Integration tests for alert detector
- E2E tests for full flow

## Development Setup

### To Run MVP (without live odds/predictions):

1. **Start backend:**
```bash
cd apps/backend
python -m server
```

2. **Start web app:**
```bash
cd apps/web
npm start
```

3. **Login** and navigate to Settings tab to configure preferences

4. **Watch for alerts** during live games (manual testing for now since odds/models not yet integrated)

### To Test Alert Flow:

1. Create a user account
2. Configure favorite teams/sports in Settings
3. Start a live game (check `/api/scoreboard?sport=nba`)
4. Manually trigger `run_alert_detection('nba')` in Python shell
5. Check `/api/live-alerts` endpoint

### Environment Variables (Optional):

```bash
# User data directory
export USER_DIR=/path/to/user_data

# Cache directory
export CACHE_DIR=/path/to/cache

# Odds API key
export ODDS_API_KEY=your_key
```

## Database Schema (User JSON)

Each user gets a JSON file with tier and alert data:

```json
{
  "user_id": "trey",
  "created_at": "2026-01-30T...",
  "password_hash": "...",
  "tokens": ["..."],
  "picks": [...],
  "subscription_tier": "elite",
  "tier_features": {
    "allowed_sports": ["nba", "nfl", ...],
    "max_favorite_teams": null,
    "max_alerts_per_day": null,
    "custom_game_subscriptions": true,
    "notification_channels": ["in_app", "email", "sms", "push"],
    "custom_ev_threshold": true
  },
  "alert_preferences": {
    "alerts_enabled": true,
    "favorite_teams": ["Lakers", "Warriors"],
    "favorite_sports": ["nba"],
    "min_ev_threshold": 5,
    "favorite_markets": ["spread", "moneyline"],
    "quiet_hours": {"start": "23:00", "end": "08:00"},
    "subscribed_games": [
      {"home": "Lakers", "away": "Celtics", "sport": "nba"}
    ]
  },
  "alert_usage": {
    "alerts_today": 12,
    "last_reset": "2026-01-30T00:00:00Z"
  },
  "alerts": [
    {
      "alert_id": "uuid",
      "created_at": "2026-01-30T14:30:00Z",
      "game_id": "...",
      "home_team": "Lakers",
      "away_team": "Celtics",
      "current_score": "45-38",
      "margin": 7,
      "opportunity_type": "moneyline",
      "pick": "home",
      "model_win_prob": 0.65,
      "market_odds": -110,
      "ev": {...},
      "recommendation": "strong_buy",
      "status": "new",
      "expires_at": "2026-01-30T14:35:00Z"
    }
  ]
}
```

## Next Steps

1. **Hook up scheduler** - Add APScheduler to continuously monitor games
2. **Integrate live odds** - Connect to OddsAPI in alert detector
3. **Integrate live model** - Enhance model server for mid-game predictions
4. **Add notification delivery** - Implement email/SMS/push channels
5. **Write tests** - Unit and integration tests for all alert systems
6. **Monitor & iterate** - Track alert quality and adjust thresholds
7. **Multi-sport support** - Extend to NFL, NCAAF, etc. as needed

## Key Files

**Backend:**
- `apps/backend/user_store.py` - Tier and preference management
- `apps/backend/alerts/tier_validator.py` - Permission checking
- `apps/backend/alerts/game_monitor.py` - Live game polling
- `apps/backend/alerts/ev_calculator.py` - EV analysis
- `apps/backend/alerts/alert_detector.py` - Alert orchestration
- `apps/backend/server.py` - API endpoints (added to existing file)

**Frontend:**
- `apps/web/src/LiveAlerts.jsx` - Alert display component
- `apps/web/src/AlertSettings.jsx` - Preference management component
- `apps/web/src/App.js` - Integration (updated)

## Notes

- All users default to **Elite tier** in development
- Alerts expire after **5 minutes** (TTL in alert object)
- Daily alert counts reset at **midnight UTC**
- System uses **file-based storage** (user JSON files)
- **No database** currently (can add PostgreSQL later)
- **APScheduler already in requirements.txt** (v3.10.0+)
- **BigQuery ready** for analytics logging (optional)
