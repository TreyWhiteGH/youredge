# Configuration Guide

The YoureEdge backend uses a TOML-based configuration system with environment variable overrides and secrets management.

## Quick Start

1. **Copy the secrets template:**
   ```bash
   cp secrets.env.example secrets.env
   ```

2. **Set your secrets in `secrets.env`:**
   ```bash
   GOOGLE_CLOUD_PROJECT=your-gcp-project-id
   THE_ODDS_API_KEY=your-odds-api-key
   GOOGLE_APPLICATION_CREDENTIALS=/path/to/gcp-credentials.json
   ```

3. **Run the backend:**
   ```bash
   cd apps/backend
   python -m server
   ```

## Configuration Priority

Configuration is loaded in this priority order (highest to lowest):

1. **Environment Variables** - Both legacy and new format
2. **TOML Configuration File** - `conf/dev.toml` or `conf/prod.toml`
3. **Default Values** - Hardcoded in `config/defaults.py`

## Configuration Sources

### 1. TOML Files

Located in the `conf/` directory at project root:

- **`conf/dev.toml`** - Development environment (default)
- **`conf/prod.toml`** - Production environment

Select environment via `APP_ENV` variable:
```bash
APP_ENV=prod python -m server
```

### 2. Environment Variables

#### Legacy Format
Works with existing environment variable names:
```bash
LOG_LEVEL=DEBUG
PORT=8080
MODELS_DIR=/opt/models
ODDS_CACHE_TTL=600
```

#### New Format (YOUREDGE_*)
Using the new format `YOUREDGE_SECTION_KEY`:
```bash
YOUREDGE_APP_LOG_LEVEL=DEBUG
YOUREDGE_APP_PORT=8080
YOUREDGE_CACHE_SCORE_TTL=1800
```

### 3. Secrets File

The `secrets.env` file (gitignored) loads secrets into environment variables:
```bash
# File: secrets.env
GOOGLE_CLOUD_PROJECT=my-gcp-project
THE_ODDS_API_KEY=my-api-key
GOOGLE_APPLICATION_CREDENTIALS=/home/user/.config/gcloud/application_default_credentials.json
```

## Using Configuration in Code

### Getting Config Values

```python
from config import config

# Get a configuration value with default
log_level = config.get("app.log_level", "INFO")

# Get a configuration section
cache_config = config.get_section("cache")
print(cache_config)  # {'dir': '...', 'score_ttl': 900, ...}

# Check environment
if config.is_production:
    # Production-specific code
    pass

# Get a secret (from environment variables only)
api_key = config.get_secret("THE_ODDS_API_KEY")

# Get a required secret (raises error if not found)
project_id = config.get_secret("GOOGLE_CLOUD_PROJECT", required=True)
```

## GCP Credentials Setup

### Development with Local Credentials

1. **Option A: Set in `secrets.env`**
   ```bash
   GOOGLE_APPLICATION_CREDENTIALS=/path/to/gcp-key.json
   ```

2. **Option B: Set in `conf/dev.toml`**
   ```toml
   [gcp]
   credentials_path = "~/.config/gcloud/application_default_credentials.json"
   ```

3. **Option C: Standard Google Cloud SDK**
   ```bash
   gcloud auth application-default login
   # Credentials saved to ~/.config/gcloud/application_default_credentials.json
   ```

### Production Deployment

In production, set `GOOGLE_APPLICATION_CREDENTIALS` in your deployment environment (e.g., as a secret in your orchestration platform). The config system will detect it automatically.

## Configuration Schema

### App Section
```toml
[app]
environment = "development"  # "development" or "production"
debug = true                 # Enable/disable debug mode
log_level = "DEBUG"          # DEBUG, INFO, WARNING, ERROR, CRITICAL
port = 5000                  # Flask server port
```

### Server Section
```toml
[server]
host = "0.0.0.0"
workers = 1                  # Number of workers (1 for dev, 4+ for prod)
```

### Providers Section
```toml
[providers]
sports = "espn"              # Sports data provider
odds = "odds_api"            # Odds data provider
```

### Cache Section
```toml
[cache]
dir = "./apps/backend/cache"  # Cache directory
score_ttl = 900               # Score cache TTL in seconds (15 minutes)
odds_ttl = 300                # Odds cache TTL in seconds (5 minutes)
```

### Paths Section
```toml
[paths]
models_dir = "/tmp/models"          # ML models directory
user_dir = "./apps/backend/user_data"  # User data directory
```

### GCP Section
```toml
[gcp]
project_id = ""                           # Leave empty, set via GOOGLE_CLOUD_PROJECT
dataset_id = "sports_data"                # BigQuery dataset
bucket_prefix = ""                        # Cloud Storage bucket prefix
credentials_path = ""                     # Path to credentials JSON (optional)
```

### Odds API Section
```toml
[odds_api]
regions = "us"                    # Regions for odds
markets = "all"                   # Markets to fetch
format = "american"               # Odds format (american or decimal)
date_format = "iso"               # Date format
```

### Features Section
```toml
[features]
ml_enabled = false                # Enable/disable ML features
alerts_enabled = true             # Enable/disable alert system
```

## Secrets Management

**Secrets are NEVER stored in TOML files.** They must come from environment variables:

- `GOOGLE_CLOUD_PROJECT` - GCP project ID
- `THE_ODDS_API_KEY` - The Odds API key
- `GOOGLE_APPLICATION_CREDENTIALS` - Path to GCP credentials

Set these in:
1. `secrets.env` (development, gitignored)
2. Environment variables (production)

Example accessing secrets:
```python
from config import config

project_id = config.get_secret("GOOGLE_CLOUD_PROJECT")
api_key = config.get_secret("THE_ODDS_API_KEY", required=True)
```

## Testing Configuration

### Test basic loading
```bash
cd apps/backend
python -c "from config import config; print(config.get('app.log_level'))"
```

### Test environment override
```bash
LOG_LEVEL=WARNING python -c "from config import config; print(config.get('app.log_level'))"
```

### Test production config
```bash
APP_ENV=prod python -c "from config import config; print(config.get('app.environment'))"
```

### Test with custom port
```bash
YOUREDGE_APP_PORT=8080 python -c "from config import config; print(config.get('app.port'))"
```

## Migration from Old System

The new configuration system is **backward compatible**. All existing environment variables continue to work:

```python
# Old way (still works)
LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO")

# New way (recommended)
from config import config
LOG_LEVEL = config.get("app.log_level", "INFO")
```

Migrate at your own pace - both systems can coexist.

## Troubleshooting

### Config file not found
```
WARNING: TOML config file not found at /path/to/conf/dev.toml. Using defaults.
```
**Solution:** Ensure you're running from the project root, or set `APP_ENV` correctly.

### Missing required secret
```
ValueError: Required secret 'GOOGLE_CLOUD_PROJECT' not found in environment variables.
```
**Solution:** Set the secret in `secrets.env` or as an environment variable.

### Type validation error
```
ConfigValidationError: Invalid log_level: INVALID. Must be one of {'DEBUG', 'INFO', ...}
```
**Solution:** Use a valid value for the configuration key.

## Files Reference

- **Configuration module:** `apps/backend/config/`
  - `loader.py` - Main configuration loader
  - `schema.py` - Validation logic
  - `defaults.py` - Default values
  - `__init__.py` - Public API

- **Configuration files:** `conf/`
  - `dev.toml` - Development config
  - `prod.toml` - Production config

- **Secrets template:** `secrets.env.example`

- **Gitignore:** `.gitignore` (prevents committing `secrets.env`)
