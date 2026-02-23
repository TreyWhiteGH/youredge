"""
Expected Value (EV) calculator for betting opportunities.

Compares model predictions vs live market odds to identify EV-positive bets.
"""

import logging
from typing import Optional, Dict

logger = logging.getLogger(__name__)


def american_to_probability(odds: float) -> float:
    """
    Convert American odds to implied probability.

    Args:
        odds: American format odds (e.g., -110, +200)

    Returns:
        Probability as decimal (0-1)
    """
    if odds == 0:
        return 0.5

    if odds < 0:
        # Negative odds: prob = -odds / (-odds + 100)
        return -odds / (-odds + 100)
    else:
        # Positive odds: prob = 100 / (odds + 100)
        return 100 / (odds + 100)


def probability_to_american(probability: float) -> float:
    """
    Convert probability (0-1) to American odds.

    Args:
        probability: Win probability (0-1)

    Returns:
        American format odds
    """
    if probability <= 0 or probability >= 1:
        return 0

    if probability >= 0.5:
        # Negative odds
        return -probability / (1 - probability) * 100
    else:
        # Positive odds
        return (1 - probability) / probability * 100


def calculate_payout(stake: float, odds: float) -> float:
    """
    Calculate potential payout from a bet.

    Args:
        stake: Bet amount
        odds: American format odds

    Returns:
        Total payout (stake + winnings)
    """
    if odds == 0:
        return stake * 2

    if odds < 0:
        # Negative odds: payout = stake * (100 / -odds)
        return stake + (stake * 100 / -odds)
    else:
        # Positive odds: payout = stake * (1 + odds / 100)
        return stake + (stake * odds / 100)


def calculate_ev(
    model_probability: float,
    market_odds: float,
    stake: float = 100,
) -> dict:
    """
    Calculate Expected Value for a bet.

    Args:
        model_probability: Model's predicted win probability (0-1)
        market_odds: Market odds in American format
        stake: Bet amount (default $100)

    Returns:
        Dict with EV analysis:
        {
            "market_probability": implied prob from odds,
            "model_probability": model prediction,
            "probability_edge": model_prob - market_prob,
            "payout_if_win": potential winnings,
            "ev_dollars": expected value in dollars,
            "ev_percentage": EV as % of stake,
            "is_positive_ev": bool,
        }
    """
    market_prob = american_to_probability(market_odds)
    payout = calculate_payout(stake, market_odds)
    winnings = payout - stake

    # EV = (win_prob * winnings) - (loss_prob * stake)
    win_prob = model_probability
    loss_prob = 1 - model_probability
    ev_dollars = (win_prob * winnings) - (loss_prob * stake)
    ev_percentage = (ev_dollars / stake) * 100

    return {
        "market_probability": round(market_prob, 4),
        "model_probability": round(model_probability, 4),
        "probability_edge": round(model_probability - market_prob, 4),
        "payout_if_win": round(payout, 2),
        "winnings_if_win": round(winnings, 2),
        "ev_dollars": round(ev_dollars, 2),
        "ev_percentage": round(ev_percentage, 2),
        "is_positive_ev": ev_percentage > 0,
    }


def is_ev_positive(ev_analysis: dict, min_threshold: float = 5.0) -> bool:
    """
    Check if EV meets the minimum threshold.

    Args:
        ev_analysis: Result from calculate_ev()
        min_threshold: Minimum EV% threshold (default 5%)

    Returns:
        True if EV% >= threshold
    """
    return ev_analysis.get("ev_percentage", 0) >= min_threshold


def evaluate_opportunity(
    game_info: dict,
    model_prediction: dict,
    market_odds: dict,
    min_ev_threshold: float = 5.0,
) -> Optional[dict]:
    """
    Evaluate if a game presents an EV-positive betting opportunity.

    Args:
        game_info: Game details (home_team, away_team, score, etc.)
        model_prediction: Model's prediction {
            "home_win_prob": 0-1,
            "away_win_prob": 0-1,
            "home_spread_prob": 0-1,
        }
        market_odds: Available market odds {
            "home_moneyline": american odds,
            "away_moneyline": american odds,
            "home_spread": value,
            "home_spread_odds": american odds,
            "total": value,
            "over_odds": american odds,
            "under_odds": american odds,
        }
        min_ev_threshold: Minimum EV% to trigger alert

    Returns:
        Alert data if opportunity found, None otherwise:
        {
            "game_id": "...",
            "opportunity_type": "moneyline|spread|total",
            "pick": "home|away|over|under",
            "model_win_prob": float,
            "market_odds": float,
            "ev": dict from calculate_ev,
            "recommendation": "strong_buy|buy|fair_value",
        }
    """
    opportunities = []

    # Check moneyline opportunities
    if market_odds.get("home_moneyline"):
        home_ev = calculate_ev(
            model_prediction.get("home_win_prob", 0.5),
            market_odds["home_moneyline"],
        )
        if is_ev_positive(home_ev, min_ev_threshold):
            opportunities.append({
                "game_id": game_info.get("game_id"),
                "home_team": game_info.get("home_team"),
                "away_team": game_info.get("away_team"),
                "opportunity_type": "moneyline",
                "pick": "home",
                "model_win_prob": round(model_prediction.get("home_win_prob", 0.5), 3),
                "market_odds": market_odds["home_moneyline"],
                "ev": home_ev,
                "recommendation": _get_recommendation(home_ev["ev_percentage"]),
            })

    if market_odds.get("away_moneyline"):
        away_ev = calculate_ev(
            model_prediction.get("away_win_prob", 0.5),
            market_odds["away_moneyline"],
        )
        if is_ev_positive(away_ev, min_ev_threshold):
            opportunities.append({
                "game_id": game_info.get("game_id"),
                "home_team": game_info.get("home_team"),
                "away_team": game_info.get("away_team"),
                "opportunity_type": "moneyline",
                "pick": "away",
                "model_win_prob": round(model_prediction.get("away_win_prob", 0.5), 3),
                "market_odds": market_odds["away_moneyline"],
                "ev": away_ev,
                "recommendation": _get_recommendation(away_ev["ev_percentage"]),
            })

    # Check spread opportunities
    if market_odds.get("home_spread_odds") and market_odds.get("home_spread"):
        spread_ev = calculate_ev(
            model_prediction.get("home_spread_prob", 0.5),
            market_odds["home_spread_odds"],
        )
        if is_ev_positive(spread_ev, min_ev_threshold):
            opportunities.append({
                "game_id": game_info.get("game_id"),
                "home_team": game_info.get("home_team"),
                "away_team": game_info.get("away_team"),
                "opportunity_type": "spread",
                "pick": f"home {market_odds['home_spread']}",
                "model_win_prob": round(model_prediction.get("home_spread_prob", 0.5), 3),
                "market_odds": market_odds["home_spread_odds"],
                "ev": spread_ev,
                "recommendation": _get_recommendation(spread_ev["ev_percentage"]),
            })

    # Return strongest opportunity or None
    if opportunities:
        opportunities.sort(
            key=lambda x: x["ev"]["ev_percentage"],
            reverse=True
        )
        return opportunities[0]

    return None


def _get_recommendation(ev_percentage: float) -> str:
    """Get recommendation based on EV percentage."""
    if ev_percentage >= 15:
        return "strong_buy"
    elif ev_percentage >= 10:
        return "buy"
    else:
        return "fair_value"
