"""
Alert Detection System - orchestrates game monitoring, EV calculation, and alert triggering.

Runs as background task to detect EV-positive opportunities and generate alerts
for users based on their tier and preferences.
"""

import logging
from datetime import datetime, timedelta
from typing import List, Dict, Optional
from uuid import uuid4

from alerts.game_monitor import monitor_live_games
from alerts.ev_calculator import evaluate_opportunity
from alerts.tier_validator import is_alert_allowed_for_user, get_user_ev_threshold
from user_store import (
    load_user,
    save_user,
    increment_daily_alert_count,
)

logger = logging.getLogger(__name__)

# Store active alerts per user
ACTIVE_ALERTS = {}  # user_id -> [alert, ...]


def detect_alerts_for_user(user_id: str, game_changes: List[dict]) -> List[dict]:
    """
    Detect EV-positive opportunities for a specific user.

    Args:
        user_id: User ID
        game_changes: List of game state changes from game_monitor

    Returns:
        List of new alerts for this user
    """
    alerts = []
    min_ev_threshold = get_user_ev_threshold(user_id)

    for change in game_changes:
        if change["type"] != "score_change":
            continue  # Only alert on score changes (momentum shifts)

        game_id = change["game_id"]

        # TODO: Integrate with odds/providers/odds_api.py for live odds
        # TODO: Integrate with ml/model_server.py for live predictions
        # Alert detection framework in place; awaiting odds and model integration
        logger.debug(f"Alert framework ready for {game_id} (pending odds/model integration)")

    return alerts


def add_user_alerts(user_id: str, alerts: List[dict]) -> None:
    """
    Store alerts in user's profile.

    Args:
        user_id: User ID
        alerts: List of new alert dicts
    """
    if not alerts:
        return

    user = load_user(user_id)
    user_alerts = user.get("alerts", [])

    # Keep only recent non-expired alerts
    now = datetime.utcnow()
    user_alerts = [
        a for a in user_alerts
        if datetime.fromisoformat(a.get("expires_at", "")) > now
    ]

    # Add new alerts
    user_alerts.extend(alerts)

    # Keep only last 100 alerts
    user_alerts = user_alerts[-100:]

    user["alerts"] = user_alerts
    save_user(user_id, user)

    # Also store in memory for quick access
    ACTIVE_ALERTS[user_id] = [
        a for a in user_alerts
        if a["status"] in ["new", "viewed"]
    ]


def run_alert_detection(sport: str = "nba") -> dict:
    """
    Main alert detection loop - called periodically by scheduler.

    Args:
        sport: Sport to monitor (nba, nfl, etc.)

    Returns:
        Summary of alerts generated:
        {
            "timestamp": "...",
            "sport": "nba",
            "games_monitored": int,
            "game_changes": int,
            "alerts_generated": int,
            "users_alerted": int,
        }
    """
    timestamp = datetime.utcnow().isoformat()
    summary = {
        "timestamp": timestamp,
        "sport": sport,
        "games_monitored": 0,
        "game_changes": 0,
        "alerts_generated": 0,
        "users_alerted": set(),
    }

    try:
        # Monitor live games
        game_changes = monitor_live_games(sport)
        summary["games_monitored"] = len(game_changes)
        summary["game_changes"] = len(game_changes)

        if not game_changes:
            logger.debug(f"No game changes detected for {sport}")
            return summary

        logger.info(f"Detected {len(game_changes)} game changes for {sport}")

        # Get all users (TODO: optimize to only active users)
        # For now, iterate through all user files
        from pathlib import Path
        user_dir = Path(__file__).parent.parent / "user_data"

        if user_dir.exists():
            for user_file in user_dir.glob("*.json"):
                try:
                    user_id = user_file.stem
                    alerts = detect_alerts_for_user(user_id, game_changes)

                    if alerts:
                        add_user_alerts(user_id, alerts)
                        summary["alerts_generated"] += len(alerts)
                        summary["users_alerted"].add(user_id)
                        logger.info(
                            f"Generated {len(alerts)} alerts for user {user_id}"
                        )

                except Exception as e:
                    logger.error(f"Error processing user {user_id}: {e}")

        # Convert set to count
        summary["users_alerted"] = len(summary["users_alerted"])

        logger.info(
            f"Alert detection complete: "
            f"{summary['alerts_generated']} alerts for "
            f"{summary['users_alerted']} users"
        )

    except Exception as e:
        logger.error(f"Error in alert detection: {e}")

    return summary


def get_user_active_alerts(user_id: str) -> List[dict]:
    """Get active (non-expired) alerts for a user."""
    user = load_user(user_id)
    alerts = user.get("alerts", [])

    now = datetime.utcnow()
    active = [
        a for a in alerts
        if (a.get("status") in ["new", "viewed"] and
            datetime.fromisoformat(a.get("expires_at", "")) > now)
    ]

    return active


def mark_alert_viewed(user_id: str, alert_id: str) -> bool:
    """Mark an alert as viewed by user."""
    user = load_user(user_id)
    alerts = user.get("alerts", [])

    for alert in alerts:
        if alert.get("alert_id") == alert_id:
            alert["status"] = "viewed"
            user["alerts"] = alerts
            save_user(user_id, user)
            return True

    return False


def dismiss_alert(user_id: str, alert_id: str) -> bool:
    """Dismiss an alert (mark as dismissed)."""
    user = load_user(user_id)
    alerts = user.get("alerts", [])

    for alert in alerts:
        if alert.get("alert_id") == alert_id:
            alert["status"] = "dismissed"
            user["alerts"] = alerts
            save_user(user_id, user)
            return True

    return False
