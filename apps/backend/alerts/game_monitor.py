"""
Real-time game monitor for tracking live games.

Polls ESPN API at regular intervals (10-30 seconds) for live game data,
tracks game state changes, and triggers alerts when EV-positive opportunities arise.
"""

import logging
from datetime import datetime
from typing import Dict, List, Optional
from pathlib import Path

from ..scores.retrieve import fetch_scoreboard

logger = logging.getLogger(__name__)

# Store current game states
LIVE_GAMES_CACHE = {}
CACHE_DIR = Path(__file__).parent / ".game_monitor_cache"
CACHE_DIR.mkdir(parents=True, exist_ok=True)


def normalize_game_id(game: dict) -> str:
    """Create a stable game ID from game data."""
    try:
        event_id = game.get("id") or game.get("uid", "")
        home = game.get("competitions", [{}])[0].get("home", {}).get("team", {}).get("id", "")
        away = game.get("competitions", [{}])[0].get("away", {}).get("team", {}).get("id", "")
        return f"{event_id}_{away}_{home}"
    except Exception:
        return game.get("id", "unknown")


def extract_game_info(game: dict) -> dict:
    """Extract relevant game information from ESPN API response."""
    try:
        comp = game.get("competitions", [{}])[0]
        home_team = comp.get("home", {})
        away_team = comp.get("away", {})
        status = game.get("status", {})

        return {
            "game_id": normalize_game_id(game),
            "sport": "nba",  # TODO: detect from game data or pass as param
            "event_id": game.get("id"),
            "home_team": home_team.get("team", {}).get("displayName", ""),
            "away_team": away_team.get("team", {}).get("displayName", ""),
            "home_score": home_team.get("score"),
            "away_score": away_team.get("score"),
            "status": status.get("type", ""),
            "status_detail": status.get("detail", ""),
            "period": comp.get("status", {}).get("period"),
            "clock": comp.get("status", {}).get("displayClock", ""),
            "timestamp": game.get("date"),
            "links": game.get("links", []),
        }
    except Exception as e:
        logger.error(f"Error extracting game info: {e}")
        return {}


def fetch_live_games(sport: str = "nba") -> List[dict]:
    """
    Fetch live games for a sport from ESPN API.

    Returns list of games with current state.
    """
    try:
        scoreboard = fetch_scoreboard(sport)
        if not scoreboard:
            return []

        events = scoreboard.get("events", [])
        live_games = []

        for game in events:
            status = game.get("status", {})
            status_type = status.get("type", "")

            # Status types: pre=pre-game, in-progress=live, final=ended
            if status_type in ["in-progress"]:
                game_info = extract_game_info(game)
                if game_info:
                    live_games.append(game_info)

        return live_games
    except Exception as e:
        logger.error(f"Error fetching live games: {e}")
        return []


def get_game_state_change(game_id: str, new_game_info: dict) -> Optional[dict]:
    """
    Detect if a game has significant state changes since last poll.

    Returns dict with change details or None if no significant change.
    """
    cached = LIVE_GAMES_CACHE.get(game_id)
    if not cached:
        # New game being tracked
        LIVE_GAMES_CACHE[game_id] = new_game_info
        return {
            "type": "game_started",
            "game_id": game_id,
            "previous": None,
            "current": new_game_info,
        }

    old_game = cached

    # Detect score changes
    if (new_game_info.get("home_score") != old_game.get("home_score") or
        new_game_info.get("away_score") != old_game.get("away_score")):

        old_home_score = old_game.get("home_score", 0) or 0
        old_away_score = old_game.get("away_score", 0) or 0
        new_home_score = new_game_info.get("home_score", 0) or 0
        new_away_score = new_game_info.get("away_score", 0) or 0

        change = {
            "type": "score_change",
            "game_id": game_id,
            "home_team": new_game_info["home_team"],
            "away_team": new_game_info["away_team"],
            "previous_score": f"{old_away_score}-{old_home_score}",
            "current_score": f"{new_away_score}-{new_home_score}",
            "home_points_added": new_home_score - old_home_score,
            "away_points_added": new_away_score - old_away_score,
            "margin": new_home_score - new_away_score,
            "previous_margin": old_home_score - old_away_score,
            "period": new_game_info.get("period"),
            "clock": new_game_info.get("clock"),
        }

        # Update cache and return
        LIVE_GAMES_CACHE[game_id] = new_game_info
        return change

    # Detect period/quarter changes
    if (new_game_info.get("period") != old_game.get("period")):
        change = {
            "type": "period_change",
            "game_id": game_id,
            "home_team": new_game_info["home_team"],
            "away_team": new_game_info["away_team"],
            "previous_period": old_game.get("period"),
            "current_period": new_game_info.get("period"),
            "score": f"{new_game_info.get('away_score', 0)}-{new_game_info.get('home_score', 0)}",
        }

        LIVE_GAMES_CACHE[game_id] = new_game_info
        return change

    # Detect game ended
    if (new_game_info.get("status") == "final" and
        old_game.get("status") != "final"):

        change = {
            "type": "game_ended",
            "game_id": game_id,
            "home_team": new_game_info["home_team"],
            "away_team": new_game_info["away_team"],
            "final_score": f"{new_game_info.get('away_score', 0)}-{new_game_info.get('home_score', 0)}",
        }

        # Remove from live games
        del LIVE_GAMES_CACHE[game_id]
        return change

    # Update cache for minor changes
    LIVE_GAMES_CACHE[game_id] = new_game_info
    return None


def monitor_live_games(sport: str = "nba") -> List[dict]:
    """
    Poll live games and return list of games with state changes.

    Returns:
        List of dicts with detected game state changes:
        [
            {
                "type": "score_change|period_change|game_ended|game_started",
                "game_id": "...",
                ...event details...
            }
        ]
    """
    changes = []

    try:
        live_games = fetch_live_games(sport)

        for game in live_games:
            game_id = game["game_id"]
            change = get_game_state_change(game_id, game)

            if change:
                changes.append(change)

        logger.debug(f"Detected {len(changes)} game state changes in {sport}")

    except Exception as e:
        logger.error(f"Error monitoring live games: {e}")

    return changes


def get_all_live_games(sport: str = "nba") -> List[dict]:
    """Get all currently live games being monitored."""
    return fetch_live_games(sport)


def clear_cache():
    """Clear game state cache (for testing/resets)."""
    LIVE_GAMES_CACHE.clear()
