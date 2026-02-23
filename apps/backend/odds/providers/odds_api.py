import logging
import os
import time

import requests

from config import config
from .base import OddsProvider

# Map our sport ids to The Odds API sport keys
SPORT_KEY_MAP = {
    "nfl": "americanfootball_nfl",
    "ncaaf": "americanfootball_ncaaf",
    "nba": "basketball_nba",
    "ncaam": "basketball_ncaab",
    "ncaab": "basketball_ncaab",
    "ncaaw": "basketball_ncaaw",
}

class OddsApiError(Exception):
    pass


class OddsApiProvider(OddsProvider):
    id = "odds_api"

    def __init__(self):
        self.cache = {}
        self.cache_ttl = config.get("cache.odds_ttl", 300)
        self.logger = logging.getLogger(__name__)
        self.default_regions = config.get("odds_api.regions", "us")
        self.default_markets = config.get("odds_api.markets", "all")
        self.default_format = config.get("odds_api.format", "american")
        self.default_date_format = config.get("odds_api.date_format", "iso")

    def supported_sports(self):
        return tuple(SPORT_KEY_MAP.keys())

    def _cache_key(self, sport, regions, markets, odds_format, date_format):
        return f"{sport}|{regions}|{markets}|{odds_format}|{date_format}"

    def _get_api_key(self):
        api_key = config.get_secret("THE_ODDS_API_KEY") or config.get_secret("ODDS_API_KEY")

        if not api_key:
            raise OddsApiError(
                "Missing THE_ODDS_API_KEY. Set it in secrets.env or as environment variable."
            )

        return api_key

    def fetch_odds(self, sport_id, regions=None, markets=None, odds_format=None, date_format=None):
        api_key = self._get_api_key()

        sport_key = SPORT_KEY_MAP.get(sport_id)
        if not sport_key:
            raise OddsApiError(f"Unsupported sport_id '{sport_id}' for odds API")

        regions = regions or self.default_regions
        # markets=all returns all available including props/derivatives
        markets = markets or self.default_markets
        odds_format = odds_format or self.default_format
        date_format = date_format or self.default_date_format

        key = self._cache_key(sport_key, regions, markets, odds_format, date_format)
        now = time.time()
        cached = self.cache.get(key)
        if cached and now - cached["time"] < self.cache_ttl:
            self.logger.debug("Odds cache hit %s %s", sport_id, key)
            return cached["data"]
        self.logger.debug("Odds cache miss %s %s", sport_id, key)

        base_url = "https://api.the-odds-api.com/v4/sports/{sport_key}/odds"
        url = base_url.format(sport_key=sport_key)
        params = {
            "apiKey": api_key,
            "regions": regions,
            "markets": markets,
            "oddsFormat": odds_format,
            "dateFormat": date_format,
        }

        try:
            resp = requests.get(url, params=params, timeout=15)
        except requests.RequestException as exc:
            self.logger.error("Odds API request error for %s: %s", sport_id, exc)
            raise OddsApiError(f"Request failed: {exc}") from exc

        if resp.status_code == 401:
            self.logger.warning("Odds API unauthorized for %s", sport_id)
            raise OddsApiError("Unauthorized: check THE_ODDS_API_KEY or HARDCODED_API_KEY")
        if resp.status_code == 429:
            self.logger.warning("Odds API rate limited for %s", sport_id)
            raise OddsApiError("Rate limited by The Odds API")
        if not resp.ok:
            self.logger.error(
                "Odds API error %s for %s: %s", resp.status_code, sport_id, resp.text
            )
            raise OddsApiError(f"Odds API error ({resp.status_code}): {resp.text}")

        data = resp.json()
        self.cache[key] = {"time": now, "data": data}
        self.logger.info(
            "Odds API fetched",
            extra={
                "sport": sport_id,
                "markets": markets,
                "regions": regions,
                "format": odds_format,
                "cache_ttl": self.cache_ttl,
            },
        )
        return data
