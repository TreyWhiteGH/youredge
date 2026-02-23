"""YoureEdge Backend Configuration Module.

This module provides centralized configuration management with support for:
- TOML configuration files (dev.toml, prod.toml)
- Environment variable overrides
- Secrets management
- Configuration validation

Usage:
    from config import config

    # Get a configuration value
    log_level = config.get("app.log_level")

    # Get a secret from environment variables
    api_key = config.get_secret("THE_ODDS_API_KEY")

    # Check environment
    if config.is_production:
        # Production-specific code
        pass
"""

from .loader import Config, get_config
from .schema import ConfigValidationError

# Create and export the singleton configuration instance
config = get_config()

__all__ = ["config", "Config", "get_config", "ConfigValidationError"]
