import json
import logging
import os
import time
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import urlencode

import requests

# Scoreboard endpoints per sport (overridable via env)
DEFAULT_SCOREBOARDS = {
    "ncaaf": "https://site.api.espn.com/apis/site/v2/sports/football/college-football/scoreboard",
    "nfl": "https://site.api.espn.com/apis/site/v2/sports/football/nfl/scoreboard",
    "ncaam": "https://site.api.espn.com/apis/site/v2/sports/basketball/mens-college-basketball/scoreboard",
    "ncaaw": "https://site.api.espn.com/apis/site/v2/sports/basketball/womens-college-basketball/scoreboard",
    "nba": "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/scoreboard",
    # Alias to keep the common "ncaab" key working for men's college hoops
    "ncaab": "https://site.api.espn.com/apis/site/v2/sports/basketball/mens-college-basketball/scoreboard",
}

# Spoofed user agent for consistency with browser requests
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.110 Safari/537.3"

API_URLS = {key: os.environ.get(key, value) for key, value in DEFAULT_SCOREBOARDS.items()}
SUPPORTED_SPORTS = tuple(API_URLS.keys())
_CACHE = {}
_NON_TODAY_CACHE_TTL = int(os.environ.get("SCORE_CACHE_TTL", "900"))
CACHE_DIR = Path(os.environ.get("CACHE_DIR", Path(__file__).parent / ".cache"))
CACHE_DIR.mkdir(parents=True, exist_ok=True)
logger = logging.getLogger(__name__)


def fetch_scoreboard(sport_id, date=None, day_offset=None):
    """
    Fetch scoreboard data for the given sport.

    - date: explicit YYYY-MM-DD string (preferred).
    - day_offset: legacy integer relative to today; if provided we convert to date.
    """
    headers = {"User-Agent": USER_AGENT}
    target_date = _resolve_date(date, day_offset)
    url = build_scoreboard_url(sport_id, target_date)

    use_cache = target_date != _today_str()
    cache_key = (sport_id, target_date)
    cache_file = CACHE_DIR / f"scoreboard_{sport_id}_{target_date}.json"
    now = time.time()
    if use_cache:
        cached = _CACHE.get(cache_key)
        if cached and now - cached["time"] < _NON_TODAY_CACHE_TTL:
            logger.debug("Scoreboard cache hit (memory) %s date=%s", sport_id, target_date)
            return cached["data"]
        if cache_file.exists() and now - cache_file.stat().st_mtime < _NON_TODAY_CACHE_TTL:
            try:
                with cache_file.open("r", encoding="utf-8") as fh:
                    disk_data = json.load(fh)
                _CACHE[cache_key] = {"time": cache_file.stat().st_mtime, "data": disk_data}
                logger.debug("Scoreboard cache hit (disk) %s date=%s", sport_id, target_date)
                return disk_data
            except Exception as exc:  # noqa: BLE001
                logger.warning("Failed to read disk cache %s: %s", cache_file, exc)
        logger.debug("Scoreboard cache miss for %s date=%s", sport_id, target_date)

    try:
        response = requests.get(url, headers=headers, timeout=15)
        response.raise_for_status()
        data = response.json()
        if use_cache and data is not None:
            _CACHE[cache_key] = {"time": now, "data": data}
            try:
                with cache_file.open("w", encoding="utf-8") as fh:
                    json.dump(data, fh)
            except Exception as exc:  # noqa: BLE001
                logger.warning("Failed to write disk cache %s: %s", cache_file, exc)
            logger.info(
                "Cached scoreboard for %s date=%s (ttl=%ss)",
                sport_id,
                target_date,
                _NON_TODAY_CACHE_TTL,
            )
        return data
    except requests.RequestException as exc:
        logger.error("Error fetching scoreboard from %s: %s", url, exc)
        return None


def build_scoreboard_url(sport_id, date_str):
    """
    Build a scoreboard URL for supported sports with explicit date.
    """
    base_url = API_URLS.get(sport_id)
    if not base_url:
        raise ValueError(f"Unsupported sport ID: {sport_id}")

    params = {"dates": date_str}

    query = urlencode(params)
    return f"{base_url}?{query}" if query else base_url


def _today_str():
    return datetime.now().strftime("%Y%m%d")


def _resolve_date(date_str, day_offset):
    """
    Prefer explicit YYYY-MM-DD (or YYYYMMDD); fallback to day_offset; default today.
    """
    if date_str:
        try:
            if "-" in date_str:
                return datetime.fromisoformat(date_str).strftime("%Y%m%d")
            # assume already YYYYMMDD
            datetime.strptime(date_str, "%Y%m%d")
            return date_str
        except ValueError as exc:
            raise ValueError(f"Invalid date format: {date_str}") from exc
    if day_offset is not None:
        try:
            offset = int(day_offset)
        except (TypeError, ValueError):
            raise ValueError("day_offset must be int")
        target = datetime.now() + timedelta(days=offset)
        return target.strftime("%Y%m%d")
    return _today_str()


if __name__ == "__main__":
    # Example usage: NBA today
    nba_today = fetch_scoreboard("nba")
    print("NBA today:", bool(nba_today))
