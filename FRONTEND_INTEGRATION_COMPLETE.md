# AI Picks Generator - Frontend Integration Complete

**Date**: February 2, 2026
**Status**: ✅ Frontend integration with backend API complete

---

## What Was Integrated

### 1. Frontend Components Created

#### AIPicksDaily.jsx (180 lines)
- Displays auto-generated daily picks from `/api/picks/daily` endpoint
- Shows metadata: total games, picks generated, best edge
- Renders single picks with expandable details
- Shows suggested parlays with risk assessment
- Metadata displays games count, picks count, best edge

#### AIPicksGenerate.jsx (280+ lines)
- Prompt-based pick generation interface
- Users can describe game scenarios in natural language
- Example: "Lakers will dominate the paint" or "Warriors struggle on back-to-backs"
- Configurable thresholds for min confidence and min edge
- Displays full 5-layer reasoning:
  - Summary
  - Key factors
  - Stats support
  - Risks
  - User alignment
- Shows prompt interpretation (scenario, keywords)
- Displays suggested parlay if available

#### AIPicksParlay.jsx (260+ lines)
- Parlay builder interface
- Step 1: Select 2-5 picks from daily recommendations
- Step 2: Click "Build Parlay" button
- Displays constructed parlay with:
  - Number of legs
  - Combined odds
  - Total edge
  - Confidence percentage
  - Risk level (low/medium/high)
  - Picks included in parlay
  - Correlation warnings if applicable

### 2. App.js Integration

**Added imports**:
```jsx
import AIPicksDaily from './AIPicksDaily';
import AIPicksGenerate from './AIPicksGenerate';
import AIPicksParlay from './AIPicksParlay';
```

**Added state**:
```jsx
const [aiPicksSubTab, setAiPicksSubTab] = useState('daily');
```

**Added tab button**:
```jsx
<button
  className={`top-nav-item ${activeTab === 'aipicks' ? 'active' : ''}`}
  onClick={() => setActiveTab('aipicks')}
>
  🤖 AI Picks
</button>
```

**Added tab content** with sub-tabs for daily/generate/parlay

### 3. CSS Styling (index.css)

Added 70+ lines of CSS for AI Picks components:
- `.ai-picks-tabs` - Tab navigation styling
- `.ai-picks-tab` - Individual tab button styling with hover/active states
- `.ai-picks-container` - Container for AI picks content
- `.ai-picks-form` - Form styling for prompt input
- Responsive design for mobile

---

## Backend API Endpoints Used

### 1. GET /api/picks/daily
- Fetches auto-generated daily picks
- Returns: single_picks, parlays, metadata
- Used by: AIPicksDaily component

### 2. POST /api/picks/generate
- Generates picks based on user prompt
- Request: `{ prompt, min_confidence, min_edge, parlay }`
- Response: `{ picks, parlay, prompt_interpretation }`
- Used by: AIPicksGenerate component

### 3. POST /api/picks/parlay
- Builds parlay from selected pick IDs
- Request: `{ pick_ids, parlay_type }`
- Response: `{ parlay: { num_legs, combined_odds, total_edge, ... } }`
- Used by: AIPicksParlay component

---

## Frontend Workflow

### Daily Picks Tab
1. User clicks "AI Picks" tab → "Daily Picks" sub-tab
2. Component fetches `/api/picks/daily`
3. Displays metadata (total games, picks generated, best edge)
4. Shows single picks in expandable cards
5. Shows suggested parlays with risk assessment

### Generate from Prompt Tab
1. User clicks "Generate from Prompt" sub-tab
2. User types natural language prompt (e.g., "Lakers will dominate")
3. User adjusts min confidence and min edge thresholds
4. User clicks "Generate AI Picks from Prompt"
5. Component calls `/api/picks/generate` endpoint
6. Displays:
   - Prompt interpretation (scenario detected, keywords found)
   - Recommended picks with 5-layer reasoning
   - Suggested parlay if building one

### Parlay Builder Tab
1. User clicks "Parlay Builder" sub-tab
2. Component fetches daily picks
3. User selects 2-5 picks by clicking on them
4. User clicks "Build Parlay" button
5. Component calls `/api/picks/parlay` with selected pick IDs
6. Displays constructed parlay with:
   - Legs, odds, edge, confidence, risk level
   - All picks included
   - Correlation warnings if any

---

## User Experience Flow

```
Login → 🤖 AI Picks Tab
    ├── 📅 Daily Picks
    │   ├── See daily recommendations
    │   ├── View metadata (games, picks, best edge)
    │   └── Check suggested parlays
    │
    ├── 💭 Generate from Prompt
    │   ├── Describe your scenario/prediction
    │   ├── Set confidence/edge thresholds
    │   ├── Get AI-generated picks with reasoning
    │   └── See prompt interpretation
    │
    └── 🎲 Parlay Builder
        ├── Select 2-5 picks from daily list
        ├── Click "Build Parlay"
        ├── Review combined odds, edge, risk
        └── See correlation warnings (if any)
```

---

## Component Communication with Backend

### AIPicksDaily
```
Component Mount
    ↓
Fetch GET /api/picks/daily
    ↓
Parse: single_picks, parlays, metadata
    ↓
Render picks with expandable details
Render suggested parlays
```

### AIPicksGenerate
```
User enters prompt + thresholds
    ↓
Click "Generate AI Picks from Prompt"
    ↓
POST /api/picks/generate { prompt, min_confidence, min_edge, parlay: true }
    ↓
Parse: picks[], parlay, prompt_interpretation
    ↓
Render interpretation (scenario, keywords)
Render each pick with 5-layer reasoning
Render suggested parlay
```

### AIPicksParlay
```
Component Mount
    ↓
Fetch GET /api/picks/daily
    ↓
Display selectable pick cards
    ↓
User selects 2-5 picks
    ↓
Click "Build Parlay"
    ↓
POST /api/picks/parlay { pick_ids: [...], parlay_type: 'standard' }
    ↓
Parse: parlay { num_legs, combined_odds, total_edge, risk_level, ... }
    ↓
Render parlay results with metrics and warnings
```

---

## Styling & Colors

- **Daily Picks Tab**: Teal primary color scheme
- **Generate Tab**: Purple gradient (#8b5cf6 to #a78bfa)
- **Parlay Tab**: Pink/magenta gradient (#ec4899 to #f472b6)

### Confidence Badges
- Green (#dcfce7) for >60%
- Amber (#fef3c7) for 55-60%
- Red (#fee2e2) for <55%

### Risk Levels (Parlays)
- Green for "low" risk
- Amber for "medium" risk
- Red for "high" risk

---

## Files Modified/Created

### Created
- `apps/web/src/AIPicksDaily.jsx` (180 lines)
- `apps/web/src/AIPicksGenerate.jsx` (280+ lines)
- `apps/web/src/AIPicksParlay.jsx` (260+ lines)
- `FRONTEND_INTEGRATION_COMPLETE.md` (this file)

### Modified
- `apps/web/src/App.js` (+50 lines)
  - Added imports (3 lines)
  - Added state (1 line)
  - Added tab button (6 lines)
  - Added rendering logic (28 lines)
- `apps/web/src/index.css` (+70 lines)
  - Added AI Picks component styling

---

## Testing Checklist

Before deployment, verify:

- [ ] Backend server running (`python -m server` in apps/backend)
- [ ] Web frontend running (`npm start` in apps/web)
- [ ] "🤖 AI Picks" tab appears in navigation
- [ ] Clicking tab shows "Daily Picks" / "Generate from Prompt" / "Parlay Builder" sub-tabs
- [ ] Daily Picks loads and displays picks
- [ ] Generate from Prompt accepts user input and calls API
- [ ] Parlay Builder lets user select picks and builds parlays
- [ ] All styling renders correctly
- [ ] Mobile responsive layout works

---

## Known Limitations (MVP)

1. Only NBA pre-game picks (sports selection removed from AI Picks interface)
2. Prompt interpretation uses keyword matching (not LLM)
3. No user pick saving to portfolio yet (separate endpoint)
4. No live bet tracking or P&L calculation
5. Models trained on limited data (803 games) = lower accuracy

---

## Next Steps (Post-MVP)

1. Add player props support
2. Implement LLM-enhanced prompt interpretation
3. Add bet tracker and P&L dashboard
4. Integrate live odds updates
5. Add email/SMS notifications for new parlays
6. Multi-sport support (NFL, NCAAB, NCAAW)
7. Advanced parlay optimization (Kelly criterion)
8. Backtest on hold-out test set

---

## API Response Examples

### GET /api/picks/daily
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
      "away_team": "Celtics",
      "line": -2.5,
      "odds": -110
    }
  ],
  "parlays": [...],
  "metadata": {
    "total_games": 10,
    "picks_generated": 15,
    "best_edge": 0.12
  }
}
```

### POST /api/picks/generate
```json
{
  "picks": [
    {
      "pick": { ... },
      "reasoning": {
        "summary": "Lakers dominates with expected blowout potential",
        "key_factors": ["High scoring potential", "Lakers paint dominance"],
        "stats_support": { "Lakers_scoring": 110.5 },
        "risks": ["Key injuries"],
        "user_alignment": "This pick aligns with your scenario: blowout"
      }
    }
  ],
  "parlay": { ... },
  "prompt_interpretation": {
    "scenario": "high_scoring",
    "keywords": ["dominate", "paint", "high-scoring"]
  }
}
```

---

**Frontend integration complete! 🎉 Ready for testing and deployment.**
