from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional
import secrets
import hashlib

USER_DIR = Path(os.environ.get("USER_DIR", Path(__file__).parent / "user_data"))
USER_DIR.mkdir(parents=True, exist_ok=True)


def _user_path(user_id: str) -> Path:
    safe_id = "".join(ch for ch in user_id if ch.isalnum() or ch in ("_", "-"))
    return USER_DIR / f"{safe_id}.json"


def _get_default_tier_features(tier: str = "elite") -> Dict:
    """Get tier features configuration."""
    tier_configs = {
        "free": {
            "allowed_sports": ["nba"],
            "max_favorite_teams": 5,
            "max_alerts_per_day": 5,
            "custom_game_subscriptions": False,
            "notification_channels": ["in_app"],
            "custom_ev_threshold": False,
        },
        "pro": {
            "allowed_sports": ["nba", "nfl", "ncaaf", "ncaam", "ncaaw"],
            "max_favorite_teams": None,
            "max_alerts_per_day": None,
            "custom_game_subscriptions": True,
            "notification_channels": ["in_app", "email"],
            "custom_ev_threshold": False,
        },
        "elite": {
            "allowed_sports": ["nba", "nfl", "ncaaf", "ncaam", "ncaaw"],
            "max_favorite_teams": None,
            "max_alerts_per_day": None,
            "custom_game_subscriptions": True,
            "notification_channels": ["in_app", "email", "sms", "push"],
            "custom_ev_threshold": True,
        },
    }
    return tier_configs.get(tier, tier_configs["elite"])


def _get_default_alert_preferences() -> Dict:
    """Get default alert preferences for new users."""
    return {
        "alerts_enabled": True,
        "favorite_teams": [],
        "favorite_sports": ["nba"],
        "min_ev_threshold": 5,
        "favorite_markets": ["spread", "moneyline"],
        "quiet_hours": {"start": "23:00", "end": "08:00"},
        "subscribed_games": [],
    }


def load_user(user_id: str) -> Dict:
    path = _user_path(user_id)
    if not path.exists():
        data = {
            "user_id": user_id,
            "created_at": datetime.utcnow().isoformat(),
            "picks": [],
            "password_hash": None,
            "tokens": [],
            "subscription_tier": "elite",
            "tier_features": _get_default_tier_features("elite"),
            "alert_preferences": _get_default_alert_preferences(),
            "alert_usage": {
                "alerts_today": 0,
                "last_reset": datetime.utcnow().isoformat(),
            },
        }
        save_user(user_id, data)
        return data
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def save_user(user_id: str, data: Dict) -> None:
    path = _user_path(user_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2)


def get_user_picks(user_id: str) -> List[Dict]:
    data = load_user(user_id)
    return data.get("picks", [])


def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode("utf-8")).hexdigest()


def create_or_login_user(user_id: str, password: str) -> str:
    """
    Create the user if not exists; if exists, verify password.
    Returns a new token on success.
    """
    user = load_user(user_id)
    pw_hash = user.get("password_hash")
    if pw_hash:
        if pw_hash != hash_password(password):
            raise ValueError("Invalid credentials")
    else:
        user["password_hash"] = hash_password(password)
    token = secrets.token_hex(16)
    tokens = user.get("tokens") or []
    tokens.append(token)
    user["tokens"] = tokens[-10:]  # keep last 10 tokens
    save_user(user_id, user)
    return token


def register_user(user_id: str, password: str) -> str:
    """
    Register a new user. Fails if user already exists with a password.
    """
    path = _user_path(user_id)
    if path.exists():
        data = load_user(user_id)
        if data.get("password_hash"):
            raise ValueError("User already exists")
    user = load_user(user_id)
    user["password_hash"] = hash_password(password)
    user["tokens"] = []
    save_user(user_id, user)
    return create_or_login_user(user_id, password)


def user_from_token(token: str) -> Optional[str]:
    for path in USER_DIR.glob("*.json"):
        try:
            with path.open("r", encoding="utf-8") as fh:
                data = json.load(fh)
            if token in data.get("tokens", []):
                return data.get("user_id")
        except Exception:
            continue
    return None


def add_user_pick(user_id: str, pick_data: Dict) -> Dict:
    """
    Add a new pick for a user.

    Generates pick_id, adds created_at timestamp, sets status to 'pending',
    and saves to user JSON file.

    Args:
        user_id: User ID
        pick_data: Pick data dict with keys: sport, event_id, bet_type,
                   selection, line, odds, stake, confidence, rationale, etc.

    Returns:
        Complete pick dict including pick_id, created_at, status
    """
    import uuid

    user = load_user(user_id)
    pick_id = str(uuid.uuid4())

    pick = {
        "pick_id": pick_id,
        "created_at": datetime.utcnow().isoformat(),
        "status": "pending",
        **pick_data,
    }

    picks = user.get("picks", [])
    picks.append(pick)
    user["picks"] = picks

    save_user(user_id, user)
    return pick


def update_user_pick(user_id: str, pick_id: str, updates: Dict) -> Optional[Dict]:
    """
    Update a user's pick with new data.

    Finds pick by ID, applies updates, and saves to JSON.

    Args:
        user_id: User ID
        pick_id: Pick ID to update
        updates: Dict of fields to update

    Returns:
        Updated pick dict or None if pick not found
    """
    user = load_user(user_id)
    picks = user.get("picks", [])

    for i, pick in enumerate(picks):
        if pick.get("pick_id") == pick_id:
            pick.update(updates)
            picks[i] = pick
            user["picks"] = picks
            save_user(user_id, user)
            return pick

    return None


def delete_user_pick(user_id: str, pick_id: str) -> bool:
    """
    Delete a user's pick.

    Only allows deletion of pending picks. If pick is not pending,
    returns False.

    Args:
        user_id: User ID
        pick_id: Pick ID to delete

    Returns:
        True if deleted, False if not found or not pending
    """
    user = load_user(user_id)
    picks = user.get("picks", [])

    for i, pick in enumerate(picks):
        if pick.get("pick_id") == pick_id:
            # Only allow deletion of pending picks
            if pick.get("status") == "pending":
                picks.pop(i)
                user["picks"] = picks
                save_user(user_id, user)
                return True
            else:
                return False

    return False


def get_user_pick_by_id(user_id: str, pick_id: str) -> Optional[Dict]:
    """
    Get a specific pick by ID.

    Args:
        user_id: User ID
        pick_id: Pick ID to retrieve

    Returns:
        Pick dict or None if not found
    """
    user = load_user(user_id)
    picks = user.get("picks", [])

    for pick in picks:
        if pick.get("pick_id") == pick_id:
            return pick

    return None


def get_user_tier(user_id: str) -> str:
    """Get user's subscription tier."""
    user = load_user(user_id)
    return user.get("subscription_tier", "elite")


def set_user_tier(user_id: str, tier: str) -> None:
    """
    Set user's subscription tier.

    Args:
        user_id: User ID
        tier: Tier name (free, pro, elite)
    """
    user = load_user(user_id)
    user["subscription_tier"] = tier
    user["tier_features"] = _get_default_tier_features(tier)
    save_user(user_id, user)


def get_user_tier_features(user_id: str) -> Dict:
    """Get user's tier feature limits."""
    user = load_user(user_id)
    return user.get("tier_features", _get_default_tier_features("elite"))


def get_user_alert_preferences(user_id: str) -> Dict:
    """Get user's alert preferences."""
    user = load_user(user_id)
    return user.get("alert_preferences", _get_default_alert_preferences())


def update_user_alert_preferences(user_id: str, updates: Dict) -> Dict:
    """
    Update user's alert preferences.

    Args:
        user_id: User ID
        updates: Dict of fields to update

    Returns:
        Updated alert preferences
    """
    user = load_user(user_id)
    prefs = user.get("alert_preferences", _get_default_alert_preferences())
    prefs.update(updates)
    user["alert_preferences"] = prefs
    save_user(user_id, user)
    return prefs


def increment_daily_alert_count(user_id: str) -> int:
    """
    Increment the daily alert count for a user.

    Returns:
        Updated alert count
    """
    user = load_user(user_id)
    alert_usage = user.get("alert_usage", {})

    # Reset if it's a new day
    last_reset = alert_usage.get("last_reset", "")
    today = datetime.utcnow().date().isoformat()

    if not last_reset.startswith(today):
        alert_usage["alerts_today"] = 0
        alert_usage["last_reset"] = datetime.utcnow().isoformat()

    alert_usage["alerts_today"] = alert_usage.get("alerts_today", 0) + 1
    user["alert_usage"] = alert_usage
    save_user(user_id, user)

    return alert_usage["alerts_today"]


def get_daily_alert_count(user_id: str) -> int:
    """Get current daily alert count for a user."""
    user = load_user(user_id)
    alert_usage = user.get("alert_usage", {})

    # Reset if it's a new day
    last_reset = alert_usage.get("last_reset", "")
    today = datetime.utcnow().date().isoformat()

    if not last_reset.startswith(today):
        return 0

    return alert_usage.get("alerts_today", 0)
