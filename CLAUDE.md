# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**YoureEdge** is a monorepo sports analytics platform with three main applications:
- **Web**: React app (Create React App) for browser-based sports picks and scoreboard
- **Mobile**: Expo/React Native app for iOS/Android
- **Backend**: Python Flask API serving sports data, picks, and odds

The backend uses an npm workspace structure at the root level with subdirectories for each app.

## Architecture

### Backend (Python/Flask)
- **Primary Language**: Python 3
- **Framework**: Flask 3.0.3
- **Purpose**: REST API providing scoreboard data, picks, and odds

**Key modules**:
- `server.py`: Main Flask application with endpoints for `/api/scoreboard`, `/api/picks`, `/api/odds`, `/api/login`, `/api/register`
- `picks_logic.py`: Core business logic for computing pick progress and sentiment given game events
- `scores/`: Handles fetching scoreboard data (ESPN provider)
- `odds/`: Odds data providers (OddsAPI integration)
- `sports_ai/`: AI/ML features for picks (context models, training builders)
- `user_store.py`: User authentication and data persistence
- `user_data/`: User files stored as JSON (demo.json, trey.json, etc.)

**Request flow**:
- All requests are logged with request IDs for tracing
- Authentication via Bearer tokens in Authorization header
- Responses include requested parameters and data payload

### Web (React)
- **Framework**: React 18.2.0 with react-scripts (Create React App)
- **Purpose**: Single-page app with sport selection, scoreboard display, picks interface, and chatbot
- **Proxy**: Configured to forward requests to `http://localhost:5000` (backend)
- **Key features**: Multi-sport support (NFL, NCAAF, NBA, NCAAM, NCAAW), user authentication, pick management

### Mobile (Expo)
- **Framework**: Expo ~48.0.0 with React Native 0.71.8
- **Purpose**: Cross-platform mobile app with similar features to web
- **Simple scaffold**: App.js with basic scoreboard and chatbot UI using React Native styling

## Development Commands

### Backend
```bash
# Install dependencies
cd apps/backend && pip install -r requirements.txt

# Run development server
cd apps/backend && python -m server

# Note: Backend uses local caching (cache/ directory) and user data files (user_data/ directory)
```

### Web
```bash
# Install dependencies (from root)
npm install

# Start development server (runs on http://localhost:3000 by default)
cd apps/web && npm start

# Build for production
cd apps/web && npm build

# Run tests (jest)
cd apps/web && npm test
```

### Mobile
```bash
# Install dependencies (from root)
npm install

# Start Expo development server
cd apps/mobile && npm start

# Run on Android
cd apps/mobile && npm run android

# Run on iOS
cd apps/mobile && npm run ios

# Run on web
cd apps/mobile && npm run web
```

## Key Integration Points

**Backend ↔ Web/Mobile**:
- Scoreboard endpoint: `GET /api/scoreboard?sport={sport}&date={date}&dayOffset={dayOffset}`
- Picks endpoint: `GET /api/picks` (requires auth token)
- Odds endpoint: `GET /api/odds`
- Auth endpoints: `POST /api/login`, `POST /api/register`

**State Management**:
- Web: Local React state (useState hooks)
- Authentication: Bearer token stored in React state and sent in headers
- Date handling: Formatted as YYYY-MM-DD; dayOffset used for relative dates

## Testing Notes

- No existing test framework is set up (no Jest, Pytest, or Unittest dependencies)
- Business logic for picks is in `picks_logic.py:compute_pick_progress()` - this would be a good candidate for unit tests
- Web has Jest support via react-scripts but no tests written yet

## Important Implementation Details

**User Authentication**:
- Backend validates Bearer tokens from Authorization header
- Token-based auth flows through Flask's `@app.before_request` hook (`_auth_user_id()`)
- User data stored as JSON files in `user_data/` directory

**Pick Logic**:
- Computes whether a pick is "covering" based on game state and score differential
- Supports bet types: spread, moneyline, total
- Returns sentiment (win/loss/neutral) based on game state ("pre", in-progress, final)

**Caching**:
- Scoreboards cached locally in `cache/` directory with filenames like `scoreboard_{sport}_{date}.json`
- Helps reduce external API calls during development

**Sports Supported**:
- Backend provider abstracts sport IDs: nfl, ncaaf, nba, ncaam, ncaaw
- Web/Mobile UI lists these with display labels
