import os

from .odds_api import OddsApiProvider

ODDS_PROVIDERS = {
    "odds_api": OddsApiProvider,
}


def get_odds_provider():
    key = os.environ.get("ODDS_PROVIDER", "odds_api").lower()
    provider_cls = ODDS_PROVIDERS.get(key)
    if not provider_cls:
        raise ValueError(f"Unsupported odds provider '{key}'")
    return provider_cls()
