"""Configuration validation and type coercion."""


class ConfigValidationError(Exception):
    """Raised when configuration validation fails."""
    pass


def validate_config(config_dict):
    """Validate configuration values.

    Args:
        config_dict: Configuration dictionary to validate

    Raises:
        ConfigValidationError: If validation fails
    """
    # Validate log_level
    valid_log_levels = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
    log_level = config_dict.get("app", {}).get("log_level", "INFO").upper()
    if log_level not in valid_log_levels:
        raise ConfigValidationError(
            f"Invalid log_level: {log_level}. Must be one of {valid_log_levels}"
        )

    # Validate port
    try:
        port = int(config_dict.get("app", {}).get("port", 5000))
        if not (1 <= port <= 65535):
            raise ConfigValidationError(f"Invalid port: {port}. Must be 1-65535")
    except ValueError as e:
        raise ConfigValidationError(f"Invalid port: must be an integer") from e

    # Validate cache TTLs
    try:
        score_ttl = int(config_dict.get("cache", {}).get("score_ttl", 0))
        if score_ttl < 0:
            raise ConfigValidationError(f"Invalid score_ttl: {score_ttl}. Must be non-negative")
    except ValueError as e:
        raise ConfigValidationError(f"Invalid score_ttl: must be an integer") from e

    try:
        odds_ttl = int(config_dict.get("cache", {}).get("odds_ttl", 0))
        if odds_ttl < 0:
            raise ConfigValidationError(f"Invalid odds_ttl: {odds_ttl}. Must be non-negative")
    except ValueError as e:
        raise ConfigValidationError(f"Invalid odds_ttl: must be an integer") from e

    # Validate providers
    valid_sports_providers = {"espn"}  # Add more as supported
    sports_provider = config_dict.get("providers", {}).get("sports", "espn")
    if sports_provider not in valid_sports_providers:
        raise ConfigValidationError(
            f"Invalid sports provider: {sports_provider}. Must be one of {valid_sports_providers}"
        )

    valid_odds_providers = {"odds_api"}  # Add more as supported
    odds_provider = config_dict.get("providers", {}).get("odds", "odds_api")
    if odds_provider not in valid_odds_providers:
        raise ConfigValidationError(
            f"Invalid odds provider: {odds_provider}. Must be one of {valid_odds_providers}"
        )


def coerce_types(config_dict):
    """Convert string values to appropriate types.

    Args:
        config_dict: Configuration dictionary to coerce

    Returns:
        The same dictionary with coerced types
    """
    # Convert port to int
    if "app" in config_dict and "port" in config_dict["app"]:
        config_dict["app"]["port"] = int(config_dict["app"]["port"])

    # Convert TTLs to int
    if "cache" in config_dict:
        if "score_ttl" in config_dict["cache"]:
            config_dict["cache"]["score_ttl"] = int(config_dict["cache"]["score_ttl"])
        if "odds_ttl" in config_dict["cache"]:
            config_dict["cache"]["odds_ttl"] = int(config_dict["cache"]["odds_ttl"])

    # Convert workers to int
    if "server" in config_dict and "workers" in config_dict["server"]:
        config_dict["server"]["workers"] = int(config_dict["server"]["workers"])

    # Convert debug to bool
    if "app" in config_dict and "debug" in config_dict["app"]:
        debug = config_dict["app"]["debug"]
        if isinstance(debug, str):
            config_dict["app"]["debug"] = debug.lower() in ("true", "1", "yes")
        else:
            config_dict["app"]["debug"] = bool(debug)

    # Convert feature flags to bool
    if "features" in config_dict:
        for key in config_dict["features"]:
            value = config_dict["features"][key]
            if isinstance(value, str):
                config_dict["features"][key] = value.lower() in ("true", "1", "yes")
            else:
                config_dict["features"][key] = bool(value)

    return config_dict
