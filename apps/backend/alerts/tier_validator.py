"""
Tier validation and alert filtering logic.

Checks if a user is allowed to receive an alert based on their subscription tier,
preferences, and limits.
"""

from ..user_store import (
    get_user_tier_features,
    get_user_alert_preferences,
    get_daily_alert_count,
)
from datetime import datetime


def is_alert_allowed_for_user(user_id: str, alert_data: dict) -> tuple[bool, str]:
    """
    Check if an alert should be sent to a user based on tier and preferences.

    Args:
        user_id: User ID
        alert_data: Alert data with keys:
            - sport: Sport key (nba, nfl, ncaaf, etc.)
            - home_team: Home team name
            - away_team: Away team name
            - game_id: Unique game identifier

    Returns:
        Tuple of (is_allowed: bool, reason: str)
    """
    tier_features = get_user_tier_features(user_id)
    preferences = get_user_alert_preferences(user_id)

    # Check if alerts are enabled
    if not preferences.get("alerts_enabled", True):
        return False, "Alerts disabled by user"

    # Check sport allowed
    allowed_sports = tier_features.get("allowed_sports", [])
    alert_sport = alert_data.get("sport", "").lower()
    if alert_sport not in allowed_sports:
        return False, f"Sport {alert_sport} not allowed on tier"

    # Check favorite sports filter
    favorite_sports = preferences.get("favorite_sports", [])
    if favorite_sports and alert_sport not in favorite_sports:
        return False, "Sport not in user's favorites"

    # Check team filter
    max_teams = tier_features.get("max_favorite_teams")
    favorite_teams = preferences.get("favorite_teams", [])

    home_team = alert_data.get("home_team", "")
    away_team = alert_data.get("away_team", "")

    if favorite_teams:
        team_match = any(
            team.lower() in [home_team.lower(), away_team.lower()]
            for team in favorite_teams
        )
        if not team_match:
            return False, "No favorite teams in this game"

    # Check custom game subscriptions
    if tier_features.get("custom_game_subscriptions", False):
        subscribed_games = preferences.get("subscribed_games", [])
        if subscribed_games:
            game_match = any(
                (sub.get("home", "").lower() == home_team.lower()
                 and sub.get("away", "").lower() == away_team.lower()
                 and sub.get("sport", "").lower() == alert_sport)
                for sub in subscribed_games
            )
            if not game_match:
                return False, "Game not in subscribed games"

    # Check quiet hours
    quiet_hours = preferences.get("quiet_hours", {})
    if quiet_hours.get("start") and quiet_hours.get("end"):
        now = datetime.utcnow().time()
        start_time = datetime.strptime(quiet_hours["start"], "%H:%M").time()
        end_time = datetime.strptime(quiet_hours["end"], "%H:%M").time()

        if start_time < end_time:
            in_quiet = start_time <= now < end_time
        else:
            in_quiet = now >= start_time or now < end_time

        if in_quiet:
            return False, "In quiet hours"

    # Check daily alert limit
    max_alerts = tier_features.get("max_alerts_per_day")
    if max_alerts:
        current_count = get_daily_alert_count(user_id)
        if current_count >= max_alerts:
            return False, f"Daily alert limit ({max_alerts}) reached"

    return True, "Alert allowed"


def get_user_notification_channels(user_id: str) -> list[str]:
    """Get enabled notification channels for user based on tier."""
    tier_features = get_user_tier_features(user_id)
    return tier_features.get("notification_channels", ["in_app"])


def can_use_custom_ev_threshold(user_id: str) -> bool:
    """Check if user's tier allows custom EV threshold."""
    tier_features = get_user_tier_features(user_id)
    return tier_features.get("custom_ev_threshold", False)


def get_user_ev_threshold(user_id: str) -> float:
    """Get EV threshold for user (in percentage)."""
    preferences = get_user_alert_preferences(user_id)
    return preferences.get("min_ev_threshold", 5)
