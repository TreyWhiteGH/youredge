"""Default configuration values for YoureEdge backend."""

DEFAULTS = {
    "app": {
        "environment": "development",
        "debug": False,
        "log_level": "INFO",
        "port": 5000,
    },
    "server": {
        "host": "0.0.0.0",
        "workers": 1,
    },
    "providers": {
        "sports": "espn",
        "odds": "odds_api",
    },
    "cache": {
        "dir": "./apps/backend/cache",
        "score_ttl": 900,
        "odds_ttl": 300,
    },
    "paths": {
        "models_dir": "/tmp/models",
        "user_dir": "./apps/backend/user_data",
    },
    "gcp": {
        "project_id": "",
        "dataset_id": "sports_data",
        "bucket_prefix": "",
        "credentials_path": "",
    },
    "odds_api": {
        "regions": "us",
        "markets": "all",
        "format": "american",
        "date_format": "iso",
    },
    "features": {
        "ml_enabled": False,
        "alerts_enabled": True,
    },
}

# Map legacy environment variables to new config paths
LEGACY_ENV_MAP = {
    "LOG_LEVEL": "app.log_level",
    "PORT": "app.port",
    "MODELS_DIR": "paths.models_dir",
    "USER_DIR": "paths.user_dir",
    "SPORTS_PROVIDER": "providers.sports",
    "ODDS_PROVIDER": "providers.odds",
    "CACHE_DIR": "cache.dir",
    "SCORE_CACHE_TTL": "cache.score_ttl",
    "ODDS_CACHE_TTL": "cache.odds_ttl",
    "ODDS_REGIONS": "odds_api.regions",
    "ODDS_MARKETS": "odds_api.markets",
    "ODDS_FORMAT": "odds_api.format",
    "ODDS_DATE_FORMAT": "odds_api.date_format",
}

# Secrets that must only come from environment variables
SECRET_ENV_VARS = [
    "GOOGLE_CLOUD_PROJECT",
    "THE_ODDS_API_KEY",
    "ODDS_API_KEY",
]
