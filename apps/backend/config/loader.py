"""Configuration loader with TOML file support and environment variable overrides."""

import copy
import os
import tomllib
from pathlib import Path
from typing import Any, Optional

from .defaults import DEFAULTS, LEGACY_ENV_MAP
from .schema import ConfigValidationError, coerce_types, validate_config


class Config:
    """Configuration manager with TOML file support and environment variable overrides.

    Priority order (highest to lowest):
    1. Environment variables (both legacy and new format YOUREDGE_*)
    2. TOML configuration file (dev.toml or prod.toml)
    3. Default values
    """

    def __init__(self):
        self._config = {}
        self._loaded = False
        self.load()

    def load(self):
        """Load configuration from all sources.

        Configuration is loaded in this order:
        1. Start with defaults
        2. Load and merge TOML file
        3. Load secrets.env file
        4. Apply environment variable overrides
        5. Coerce types and validate

        Raises:
            ConfigValidationError: If configuration validation fails
        """
        # Start with defaults (deep copy to avoid mutation)
        self._config = self._deep_copy(DEFAULTS)

        # Load and merge TOML configuration file
        toml_config = self._load_toml()
        if toml_config:
            self._config = self._deep_merge(self._config, toml_config)

        # Load secrets from secrets.env file if present
        self._load_env_file()

        # Apply environment variable overrides
        self._apply_env_overrides()

        # Coerce types (strings to ints, bools, etc.)
        self._config = coerce_types(self._config)

        # Validate configuration
        validate_config(self._config)

        self._loaded = True

    def _load_toml(self) -> dict:
        """Load TOML configuration file based on APP_ENV variable.

        Returns:
            Dictionary from TOML file, or empty dict if file not found

        Raises:
            Exception: If TOML file exists but fails to parse
        """
        env = os.environ.get("APP_ENV", "dev")

        # Calculate path to conf/ directory at project root
        config_file = Path(__file__)
        # Path: ...apps/backend/config/loader.py -> back to root
        root_dir = config_file.parent.parent.parent.parent
        toml_path = root_dir / "conf" / f"{env}.toml"

        if not toml_path.exists():
            print(f"WARNING: TOML config file not found at {toml_path}. Using defaults.")
            return {}

        try:
            with open(toml_path, "rb") as f:
                config = tomllib.load(f)
            print(f"Loaded configuration from {toml_path}")
            return config
        except Exception as e:
            print(f"ERROR: Failed to load TOML config from {toml_path}: {e}")
            raise

    def _load_env_file(self):
        """Load environment variables from secrets.env file if present.

        The secrets.env file is loaded into os.environ, allowing env var overrides
        to take precedence in _apply_env_overrides().
        """
        root_dir = Path(__file__).parent.parent.parent.parent
        env_file = root_dir / "secrets.env"

        if not env_file.exists():
            return

        try:
            with open(env_file) as f:
                for line in f:
                    line = line.strip()
                    # Skip empty lines and comments
                    if not line or line.startswith("#"):
                        continue
                    # Parse KEY=value format
                    if "=" in line:
                        key, value = line.split("=", 1)
                        os.environ[key.strip()] = value.strip()
        except Exception as e:
            print(f"WARNING: Failed to load secrets.env: {e}")

    def _apply_env_overrides(self):
        """Apply environment variable overrides to configuration.

        Supports two formats:
        1. Legacy env vars (e.g., LOG_LEVEL, PORT, MODELS_DIR)
        2. New format: YOUREDGE_{SECTION}_{KEY} (e.g., YOUREDGE_APP_LOG_LEVEL)
        """
        # Apply legacy environment variables first
        for env_var, config_path in LEGACY_ENV_MAP.items():
            value = os.environ.get(env_var)
            if value is not None:
                self._set_nested(config_path, value)

        # Apply new format YOUREDGE_* variables
        for key, value in os.environ.items():
            if key.startswith("YOUREDGE_"):
                # Strip YOUREDGE_ prefix and convert to lowercase
                config_key = key[9:].lower()
                # Split on first underscore to get section and setting
                parts = config_key.split("_", 1)
                if len(parts) == 2:
                    section, setting = parts
                    self._set_nested(f"{section}.{setting}", value)

    def _deep_merge(self, base: dict, override: dict) -> dict:
        """Deep merge override dictionary into base dictionary.

        Args:
            base: Base configuration dictionary
            override: Dictionary to merge into base

        Returns:
            Merged dictionary (base is not modified)
        """
        result = base.copy()
        for key, value in override.items():
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                result[key] = self._deep_merge(result[key], value)
            else:
                result[key] = value
        return result

    def _deep_copy(self, d: dict) -> dict:
        """Create a deep copy of a dictionary.

        Args:
            d: Dictionary to copy

        Returns:
            Deep copy of the dictionary
        """
        return copy.deepcopy(d)

    def _set_nested(self, path: str, value: Any):
        """Set a nested configuration value using dot notation.

        Args:
            path: Configuration path (e.g., "app.log_level")
            value: Value to set
        """
        parts = path.split(".")
        current = self._config
        for part in parts[:-1]:
            if part not in current:
                current[part] = {}
            current = current[part]
        current[parts[-1]] = value

    def get(self, path: str, default: Any = None) -> Any:
        """Get a configuration value using dot notation.

        Args:
            path: Configuration path (e.g., "app.log_level")
            default: Default value if path not found

        Returns:
            Configuration value or default
        """
        parts = path.split(".")
        current = self._config
        for part in parts:
            if isinstance(current, dict) and part in current:
                current = current[part]
            else:
                return default
        return current

    def get_section(self, section: str) -> dict:
        """Get an entire configuration section.

        Args:
            section: Section name (e.g., "app", "cache", "gcp")

        Returns:
            Dictionary containing the section's configuration
        """
        return self._config.get(section, {})

    def get_secret(self, env_var: str, required: bool = False) -> Optional[str]:
        """Get a secret from environment variables.

        Secrets are NOT stored in TOML files for security. They must come from
        environment variables or secrets.env file.

        Args:
            env_var: Environment variable name (e.g., "GOOGLE_CLOUD_PROJECT")
            required: If True, raises ValueError if not found

        Returns:
            Secret value or None if not found (and not required)

        Raises:
            ValueError: If required=True and secret not found
        """
        value = os.environ.get(env_var)
        if required and not value:
            raise ValueError(
                f"Required secret '{env_var}' not found in environment variables. "
                f"Please set it in secrets.env or as an environment variable."
            )
        return value

    @property
    def is_production(self) -> bool:
        """Check if running in production environment."""
        return self.get("app.environment") == "production"

    @property
    def is_development(self) -> bool:
        """Check if running in development environment."""
        return self.get("app.environment") == "development"


# Singleton instance
_config_instance: Optional[Config] = None


def get_config() -> Config:
    """Get or create the singleton configuration instance.

    Returns:
        The singleton Config instance
    """
    global _config_instance
    if _config_instance is None:
        _config_instance = Config()
    return _config_instance
