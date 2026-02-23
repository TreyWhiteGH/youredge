# Sports ML Betting System - API Endpoints Reference

## Quick Navigation

- [Generate Picks](#post-apigenerate-picks)
- [Create Pick](#post-apipicks)
- [Update Pick](#put-apipicksid)
- [Delete Pick](#delete-apipicksid)

---

## POST /api/generate-picks

Generate AI-powered pick recommendations using trained ML models.

**Authentication:** Not required

**Request Body:**
```json
{
  "sport": "nba",
  "date": "2024-01-15",
  "markets": ["spread", "total"],
  "min_confidence": 0.58,
  "min_edge": 0.03
}
```

**Parameters:**
| Name | Type | Required | Default | Description |
|------|------|----------|---------|-------------|
| sport | string | No | "nba" | Sport ID (nba, nfl, ncaaf, nhl, mlb) |
| date | string | No | Today | Date in YYYY-MM-DD format |
| dayOffset | integer | No | - | Days offset from date |
| markets | array | No | ["spread", "total"] | Markets to predict |
| min_confidence | float | No | 0.58 | Minimum win probability (0-1) |
| min_edge | float | No | 0.03 | Minimum expected value |

**Success Response (200):**
```json
{
  "picks": [
    {
      "event_id": "12345678",
      "matchup": "LAL @ BOS",
      "status": "pre",
      "home": {
        "id": "25",
        "name": "Boston Celtics",
        "shortName": "BOS",
        "abbrev": "BOS",
        "score": null,
        "rank": 2
      },
      "away": {
        "id": "20",
        "name": "Los Angeles Lakers",
        "shortName": "LAL",
        "abbrev": "LAL",
        "score": null,
        "rank": 5
      },
      "predictions": [
        {
          "market": "spread",
          "selection": "home",
          "line": -5.5,
          "confidence": 0.65,
          "edge": 0.0425,
          "rationale": "Strong home court advantage with elite defense",
          "risk_level": "low",
          "model_version": "v1",
          "timestamp": "2024-01-15T10:30:00.000000"
        },
        {
          "market": "total",
          "selection": "under",
          "line": 221.5,
          "confidence": 0.62,
          "edge": 0.0358,
          "rationale": "Defensive strength of both teams",
          "risk_level": "medium",
          "model_version": "v1",
          "timestamp": "2024-01-15T10:30:00.000000"
        }
      ],
      "game_context": {
        "id": "12345678",
        "shortName": "LAL @ BOS",
        "status": {"state": "pre"},
        "home": {...},
        "away": {...}
      }
    }
  ],
  "metadata": {
    "total_games": 10,
    "recommended": 3,
    "avg_confidence": 0.624,
    "generated_at": "2024-01-15T10:30:00.000000",
    "disclaimer": "These AI-generated picks are for informational purposes only..."
  }
}
```

**Error Response (503):**
```json
{
  "error": "Model server not available",
  "message": "ML models are not loaded. Please try again later."
}
```

**Error Response (400):**
```json
{
  "error": "Unsupported sport 'xyz'",
  "request_id": "uuid"
}
```

**Curl Example:**
```bash
curl -X POST http://localhost:5000/api/generate-picks \
  -H "Content-Type: application/json" \
  -d '{
    "sport": "nba",
    "markets": ["spread", "total"],
    "min_confidence": 0.60
  }'
```

---

## POST /api/picks

Create a new pick for the authenticated user.

**Authentication:** Required (Bearer token)

**Request Body:**
```json
{
  "sport": "nba",
  "event_id": "12345678",
  "bet_type": "spread",
  "selection": "home",
  "line": -5.5,
  "odds": -110,
  "stake": 100,
  "confidence": 0.65,
  "rationale": "Strong matchup based on analytics"
}
```

**Parameters:**
| Name | Type | Required | Description |
|------|------|----------|-------------|
| sport | string | Yes | Sport ID (nba, nfl, ncaaf, nhl, mlb) |
| event_id | string | Yes | Unique game identifier |
| bet_type | string | Yes | Type: 'spread', 'moneyline', 'total' |
| selection | string | Yes | Prediction: 'home'/'away' or 'over'/'under' |
| line | float | No | Betting line (required for spread/total) |
| odds | float | Yes | American odds (-110, +110, etc.) |
| stake | float | Yes | Amount to wager (must be positive) |
| confidence | float | No | Win probability (0-1) |
| rationale | string | No | Explanation for the pick |

**Validation Rules:**
- `bet_type` must be: 'spread', 'moneyline', or 'total'
- For spread/moneyline: `selection` must be 'home', 'away', 'h', or 'a'
- For total: `selection` must be 'over', 'under', 'o', or 'u'
- `stake` must be positive number
- `odds` must be valid number (typically negative for favorites)

**Success Response (200):**
```json
{
  "pick": {
    "pick_id": "550e8400-e29b-41d4-a716-446655440000",
    "user_id": "username",
    "created_at": "2024-01-15T10:30:00.000000",
    "status": "pending",
    "sport": "nba",
    "event_id": "12345678",
    "bet_type": "spread",
    "selection": "home",
    "line": -5.5,
    "odds": -110,
    "stake": 100,
    "confidence": 0.65,
    "rationale": "Strong matchup based on analytics"
  },
  "disclaimer": "This pick was created manually. Always verify odds and terms before betting."
}
```

**Error Response (401):**
```json
{
  "error": "Authentication required"
}
```

**Error Response (400):**
```json
{
  "error": "Missing required fields: event_id, bet_type"
}
```

or

```json
{
  "error": "Invalid selection 'under' for bet_type 'spread'. Valid: home, away"
}
```

**Curl Example:**
```bash
curl -X POST http://localhost:5000/api/picks \
  -H "Authorization: Bearer <your-token>" \
  -H "Content-Type: application/json" \
  -d '{
    "sport": "nba",
    "event_id": "12345678",
    "bet_type": "spread",
    "selection": "home",
    "line": -5.5,
    "odds": -110,
    "stake": 100,
    "confidence": 0.65,
    "rationale": "Strong home advantage"
  }'
```

---

## PUT /api/picks/{id}

Update an existing pick (e.g., settle after game ends).

**Authentication:** Required (Bearer token)

**Request Body:**
```json
{
  "status": "won",
  "result": true,
  "profit": 90.91,
  "settled_at": "2024-01-15T15:30:00"
}
```

**Parameters:**
| Name | Type | Required | Description |
|------|------|----------|-------------|
| status | string | No | Pick status: 'pending', 'won', 'lost', 'push', 'settled' |
| result | boolean | No | true=won, false=lost, null=push |
| profit | float | No | Profit/loss amount |
| settled_at | string | No | ISO timestamp of settlement |

**Success Response (200):**
```json
{
  "pick": {
    "pick_id": "550e8400-e29b-41d4-a716-446655440000",
    "created_at": "2024-01-15T10:30:00.000000",
    "status": "won",
    "result": true,
    "profit": 90.91,
    "settled_at": "2024-01-15T15:30:00.000000",
    "sport": "nba",
    "event_id": "12345678",
    "bet_type": "spread",
    "selection": "home",
    "line": -5.5,
    "odds": -110,
    "stake": 100,
    "confidence": 0.65,
    "rationale": "Strong matchup based on analytics"
  }
}
```

**Error Response (401):**
```json
{
  "error": "Authentication required"
}
```

**Error Response (404):**
```json
{
  "error": "Pick not found: <pick_id>"
}
```

**Error Response (500):**
```json
{
  "error": "Failed to update pick: <error message>"
}
```

**Curl Example:**
```bash
curl -X PUT http://localhost:5000/api/picks/550e8400-e29b-41d4-a716-446655440000 \
  -H "Authorization: Bearer <your-token>" \
  -H "Content-Type: application/json" \
  -d '{
    "status": "won",
    "result": true,
    "profit": 90.91,
    "settled_at": "2024-01-15T15:30:00"
  }'
```

---

## DELETE /api/picks/{id}

Delete a pending pick (only pending picks can be deleted).

**Authentication:** Required (Bearer token)

**Request Body:** None

**Success Response (200):**
```json
{
  "deleted": true,
  "message": "Pick 550e8400-e29b-41d4-a716-446655440000 deleted successfully"
}
```

**Error Response (401):**
```json
{
  "error": "Authentication required"
}
```

**Error Response (404):**
```json
{
  "error": "Pick not found: 550e8400-e29b-41d4-a716-446655440000"
}
```

**Error Response (400):**
```json
{
  "deleted": false,
  "message": "Cannot delete won pick. Only pending picks can be deleted."
}
```

**Curl Example:**
```bash
curl -X DELETE http://localhost:5000/api/picks/550e8400-e29b-41d4-a716-446655440000 \
  -H "Authorization: Bearer <your-token>"
```

---

## Authentication

All `/api/picks` endpoints require Bearer token authentication:

```bash
Authorization: Bearer <your-token>
```

Get a token by registering or logging in:

**Register:**
```bash
curl -X POST http://localhost:5000/api/register \
  -H "Content-Type: application/json" \
  -d '{
    "username": "myuser",
    "password": "mypassword"
  }'
```

**Login:**
```bash
curl -X POST http://localhost:5000/api/login \
  -H "Content-Type: application/json" \
  -d '{
    "username": "myuser",
    "password": "mypassword"
  }'
```

Both return:
```json
{
  "token": "hex-encoded-token",
  "userId": "myuser"
}
```

---

## HTTP Status Codes

| Code | Meaning | Scenarios |
|------|---------|-----------|
| 200 | OK | Successful request |
| 400 | Bad Request | Invalid input, validation errors |
| 401 | Unauthorized | Missing/invalid authentication |
| 404 | Not Found | Pick doesn't exist |
| 500 | Internal Server Error | Unexpected error |
| 503 | Service Unavailable | Models not loaded |

---

## Common Error Scenarios

### Missing Authentication
```json
{
  "error": "Authentication required"
}
```
**Solution:** Add `Authorization: Bearer <token>` header

### Invalid Bet Type
```json
{
  "error": "Invalid bet_type 'totals'. Must be spread, moneyline, or total"
}
```
**Solution:** Use 'spread', 'moneyline', or 'total' (not 'totals')

### Invalid Selection for Bet Type
```json
{
  "error": "Invalid selection 'under' for bet_type 'spread'"
}
```
**Solution:** For spread, use 'home' or 'away'. For total, use 'over' or 'under'

### Cannot Delete Settled Pick
```json
{
  "deleted": false,
  "message": "Cannot delete won pick. Only pending picks can be deleted."
}
```
**Solution:** Only pending picks can be deleted. Settled picks are immutable.

### Model Server Unavailable
```json
{
  "error": "Model server not available",
  "message": "ML models are not loaded. Please try again later."
}
```
**Solution:** Check that models are loaded in `MODELS_DIR` and system has sufficient resources

---

## Rate Limiting

Currently: No rate limiting (recommended to add in production)

**Suggested Limits:**
- 100 pick creations per user per day
- 10 generate-picks requests per minute per IP
- 1000 total API requests per user per day

---

## Data Types

**Float Examples:**
- Confidence: 0.65 (65%), 0.58 (58%)
- Odds: -110 (negative = favorite), +150 (positive = underdog)
- Edge: 0.03 (3%), 0.045 (4.5%)
- Stake: 100 (dollars), 50.50 (dollars)

**String Examples:**
- Sport: 'nba', 'nfl', 'ncaaf', 'nhl', 'mlb'
- Bet Type: 'spread', 'moneyline', 'total'
- Selection: 'home', 'away', 'over', 'under' (or 'h', 'a', 'o', 'u')
- Status: 'pending', 'won', 'lost', 'push'

---

## Request/Response Headers

**Required Headers:**
```
Content-Type: application/json
Authorization: Bearer <token>  (for /api/picks endpoints)
```

**Response Headers:**
```
Content-Type: application/json
X-Request-ID: <uuid>  (for debugging)
```

---

## Testing Tools

**Using cURL:**
```bash
curl -X POST http://localhost:5000/api/picks \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d @pick.json
```

**Using Python:**
```python
import requests

token = "your-token"
headers = {"Authorization": f"Bearer {token}"}

# Create pick
response = requests.post(
    "http://localhost:5000/api/picks",
    headers=headers,
    json={
        "sport": "nba",
        "event_id": "12345678",
        "bet_type": "spread",
        "selection": "home",
        "odds": -110,
        "stake": 100
    }
)
print(response.json())
```

**Using JavaScript/Fetch:**
```javascript
const token = "your-token";

const response = await fetch("http://localhost:5000/api/picks", {
  method: "POST",
  headers: {
    "Authorization": `Bearer ${token}`,
    "Content-Type": "application/json"
  },
  body: JSON.stringify({
    sport: "nba",
    event_id: "12345678",
    bet_type: "spread",
    selection: "home",
    odds: -110,
    stake: 100
  })
});

const data = await response.json();
console.log(data);
```

---

Version: 1.0
Last Updated: 2024-01-15
