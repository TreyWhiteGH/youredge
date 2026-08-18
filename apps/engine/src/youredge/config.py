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

    # Odds polling
    odds_poll_interval_seconds: int = 1800  # 30 min pregame cadence
    odds_bookmakers: str = "draftkings,fanduel,betmgm,caesars,pinnacle"


@lru_cache
def get_settings() -> Settings:
    return Settings()
