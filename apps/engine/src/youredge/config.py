from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+asyncpg://youredge:youredge_dev@localhost:5432/youredge"
    redis_url: str = "redis://localhost:6379/0"

    odds_api_key: str = ""
    cfbd_api_key: str = ""
    anthropic_api_key: str = ""

    env: str = "dev"
    log_level: str = "INFO"

    # Odds polling.
    # The bulk (featured-market) call costs 3 credits per league per poll, so the
    # loop interval sets a fixed monthly floor: 60 min is ~4.3k credits/month for
    # both leagues, 30 min is ~8.6k. On a 20k plan the difference is most of the
    # room the per-event prop tier needs, hence hourly by default.
    odds_poll_interval_seconds: int = 3600
    # Books are free — Odds API credits scale with markets x regions, not with
    # bookmaker count — so ask widely. Pinnacle is the sharp de-vig anchor.
    odds_bookmakers: str = "draftkings,fanduel,betmgm,caesars,pinnacle"


@lru_cache
def get_settings() -> Settings:
    return Settings()
