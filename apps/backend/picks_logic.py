"""Core business logic for computing pick progress and sentiment."""

from __future__ import annotations

from typing import Any, Dict, Optional


def compute_pick_progress(pick: Dict[str, Any], event: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Compute pick progress and sentiment given a simplified scoreboard event.
    """
    if not event:
        return {
            "status": "no_data",
            "status_detail": "No event data",
            "cover_margin": None,
            "is_covering": None,
            "win_sentiment": "unknown",
        }

    state = (event.get("status") or {}).get("state")
    detail = (event.get("status") or {}).get("shortDetail") or (event.get("status") or {}).get("detail")
    home = event.get("home") or {}
    away = event.get("away") or {}
    home_score = _int_or_zero(home.get("score"))
    away_score = _int_or_zero(away.get("score"))

    bet_type = (pick.get("bet_type") or "").lower()
    selection = (pick.get("selection") or "").lower()
    line = pick.get("line")
    is_covering = None
    cover_margin = None
    win_sentiment = "neutral"

    if bet_type in {"spread", "moneyline"}:
        team_id = pick.get("team_id") or pick.get("team")
        is_home = str(team_id) == str(home.get("id")) or selection == "home"
        team_score = home_score if is_home else away_score
        opp_score = away_score if is_home else home_score
        score_diff = team_score - opp_score
        if bet_type == "spread" and line is not None:
            cover_margin = score_diff - float(line)
            is_covering = cover_margin > 0
        elif bet_type == "moneyline":
            is_covering = score_diff > 0 if state != "pre" else None
        win_sentiment = _sentiment(is_covering, score_diff, state)
    elif bet_type == "total" and line is not None:
        total = home_score + away_score
        if selection in {"over", "o"}:
            cover_margin = total - float(line)
            is_covering = cover_margin > 0
        elif selection in {"under", "u"}:
            cover_margin = float(line) - total
            is_covering = cover_margin > 0
        win_sentiment = _sentiment(is_covering, cover_margin or 0, state)

    return {
        "status": state,
        "status_detail": detail,
        "cover_margin": cover_margin,
        "is_covering": is_covering,
        "win_sentiment": win_sentiment,
        "score": f"{away_score}-{home_score}",
    }


def build_game_context(event: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    if not event:
        return {}
    return {
        "id": event.get("id"),
        "shortName": event.get("shortName"),
        "status": event.get("status"),
        "home": event.get("home"),
        "away": event.get("away"),
    }


def _int_or_zero(val: Any) -> int:
    try:
        return int(val)
    except Exception:
        return 0


def _sentiment(is_covering: Optional[bool], margin: float, state: Optional[str]) -> str:
    if is_covering is None or state == "pre":
        return "neutral"
    if is_covering and margin is not None and margin > 0:
        return "positive"
    if is_covering is False:
        return "negative"
    return "neutral"
