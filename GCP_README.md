# GCP Infrastructure Setup - YoureEdge Sports ML Betting System

**Complete guide for setting up Google Cloud Platform infrastructure for the sports ML betting system**

---

## Quick Start (5 minutes)

### 1. Prerequisites
- Google Cloud account (sign up at https://cloud.google.com)
- Valid billing method
- `gcloud` CLI installed (https://cloud.google.com/sdk/docs/install)
- Python 3.8+

### 2. Run Automated Setup

```bash
# Make script executable
chmod +x gcp_quickstart.sh

# Run the automated setup
./gcp_quickstart.sh youre-edge-sports-ml

# This will:
# ✓ Create GCP project
# ✓ Enable required APIs
# ✓ Create service account
# ✓ Generate authentication key
# ✓ Create BigQuery dataset
# ✓ Create Cloud Storage buckets
```

### 3. Run Python Setup Script

```bash
# Install Python dependencies
pip install -r gcp_requirements.txt

# Run setup script
export GOOGLE_APPLICATION_CREDENTIALS=~/.gcp/service-account-key.json
python gcp_setup.py

# Verify everything works
python verify_gcp_setup.py
```

### 4. Test Connection

```bash
# Test Python client
python gcp_client.py

# Should output successful connections and bucket stats
```

---

## Project Structure

```
├── GCP_SETUP_GUIDE.md              # Detailed step-by-step guide
├── GCP_README.md                   # This file
├── GCP_ADVANCED_CONFIG.md          # Advanced topics & troubleshooting
├── gcp_quickstart.sh               # Automated setup script (bash)
├── gcp_setup.py                    # Python setup automation
├── verify_gcp_setup.py             # Verification script
├── gcp_client.py                   # Python client library
└── gcp_requirements.txt            # Python dependencies
```

---

## What Gets Created

### BigQuery Dataset: `sports_data`

| Table | Purpose |
|-------|---------|
| **games** | Game metadata (teams, scores, status) |
| **game_events** | Play-by-play events (touchdowns, goals, etc.) |
| **team_stats** | Pre-calculated team statistics |
| **training_labels** | Ground truth for model training |
| **predictions** | Model predictions for monitoring |
| **model_metadata** | Model versioning and metadata |

### Cloud Storage Buckets

| Bucket | Purpose |
|--------|---------|
| **youre-edge-raw-data** | Raw ESPN JSON files |
| **youre-edge-models** | Trained ML model artifacts (.pkl files) |
| **youre-edge-training-data** | Parquet training files |

### Service Account

- **Name:** `sports-ml-service`
- **Roles:** BigQuery Admin, Storage Admin
- **Key:** `~/.gcp/service-account-key.json`

---

## Configuration

### Environment Variables

Set these before running Python scripts:

```bash
# Required - Point to your service account key
export GOOGLE_APPLICATION_CREDENTIALS=~/.gcp/service-account-key.json

# Optional - Default project (if not using ~/.gcloud/configurations/...)
export GCLOUD_PROJECT=youre-edge-sports-ml-1234567890
```

### Permanent Setup (macOS/Linux)

Add to your shell profile (`~/.bashrc` or `~/.zshrc`):

```bash
export GOOGLE_APPLICATION_CREDENTIALS="$HOME/.gcp/service-account-key.json"
export GCLOUD_PROJECT="your-project-id"
```

Then reload:
```bash
source ~/.bashrc  # or ~/.zshrc
```

---

## Common Commands

### BigQuery Operations

```bash
# List datasets
bq ls --project_id=YOUR_PROJECT_ID

# List tables in dataset
bq ls --project_id=YOUR_PROJECT_ID sports_data

# Query data
bq query --project_id=YOUR_PROJECT_ID "SELECT * FROM sports_data.games LIMIT 10"

# Get table schema
bq show --project_id=YOUR_PROJECT_ID sports_data.games

# Insert data from JSON file
bq load --project_id=YOUR_PROJECT_ID \
  --source_format=NEWLINE_DELIMITED_JSON \
  sports_data.games \
  games.jsonl
```

### Cloud Storage Operations

```bash
# List buckets
gsutil ls -p YOUR_PROJECT_ID

# Upload file
gsutil cp local_file.json gs://youre-edge-raw-data/data/

# Download file
gsutil cp gs://youre-edge-raw-data/data/file.json .

# List bucket contents
gsutil ls -r gs://youre-edge-raw-data/

# Delete file
gsutil rm gs://youre-edge-raw-data/data/old_file.json
```

### gcloud Configuration

```bash
# Set default project
gcloud config set project YOUR_PROJECT_ID

# List current configuration
gcloud config list

# Authenticate
gcloud auth application-default login

# Check authentication
gcloud auth list
```

---

## Python Usage Examples

### Insert a Game Record

```python
from gcp_client import SportsMLClient

client = SportsMLClient(project_id="your-project-id")

client.insert_game(
    game_id="nfl_2024_001",
    sport="NFL",
    game_date="2024-09-15",
    home_team="Kansas City Chiefs",
    away_team="Cincinnati Bengals",
    home_team_id="12",
    away_team_id="5",
    venue="Arrowhead Stadium",
    status="scheduled"
)
```

### Query Games

```python
from gcp_client import BigQueryClient

bq = BigQueryClient(project_id="your-project-id")

# Get recent NFL games
games = bq.query_to_dataframe("""
    SELECT * FROM sports_data.games
    WHERE sport = 'NFL'
    ORDER BY game_date DESC
    LIMIT 10
""")

print(games)
```

### Upload Data to Storage

```python
from gcp_client import StorageClient

storage = StorageClient(project_id="your-project-id")

# Upload JSON file
storage.upload_blob(
    bucket_name="youre-edge-raw-data",
    source_file_path="games.json",
    destination_blob_name="data/games.json"
)

# Upload Python dict as JSON
storage.upload_json(
    bucket_name="youre-edge-raw-data",
    data={"sport": "NFL", "date": "2024-09-15"},
    destination_blob_name="config/settings.json"
)
```

### Download Data

```python
from gcp_client import StorageClient

storage = StorageClient(project_id="your-project-id")

# Download JSON
data = storage.download_json(
    bucket_name="youre-edge-models",
    source_blob_name="model_metadata.json"
)

print(data)
```

---

## Troubleshooting

### "Permission denied" Error

```bash
# Check authentication
echo $GOOGLE_APPLICATION_CREDENTIALS
ls -la ~/.gcp/service-account-key.json

# Re-authenticate
gcloud auth application-default login

# Or regenerate service account key
gcloud iam service-accounts keys create ~/.gcp/service-account-key.json \
  --iam-account=sports-ml-service@YOUR_PROJECT_ID.iam.gserviceaccount.com
```

### "BigQuery API not enabled"

```bash
gcloud services enable bigquery.googleapis.com --project=YOUR_PROJECT_ID
```

### "Project not found"

```bash
# Check available projects
gcloud projects list

# Set default project
gcloud config set project YOUR_PROJECT_ID
```

### Slow Queries or High Costs

See **GCP_ADVANCED_CONFIG.md** for optimization tips:
- Partition tables by date
- Use clustering
- Create materialized views
- Use slots for predictable costs

---

## Security Best Practices

### Do's ✓
- ✓ Store service account key in `~/.gcp/`
- ✓ Set file permissions to `600`: `chmod 600 ~/.gcp/service-account-key.json`
- ✓ Add `~/.gcp/` to `.gitignore`
- ✓ Rotate service account keys annually
- ✓ Use separate service accounts per environment
- ✓ Enable audit logging
- ✓ Use VPC Service Controls for sensitive data
- ✓ Set up Cloud Armor for public endpoints

### Don'ts ✗
- ✗ Commit service account keys to Git
- ✗ Share service account keys
- ✗ Use editor service account for everything
- ✗ Leave old/unused service accounts active
- ✗ Log credentials in error messages

---

## Cost Management

### Estimated Monthly Costs (Low Volume)

| Service | Volume | Cost |
|---------|--------|------|
| BigQuery Storage | 10 GB | ~$0.25 |
| BigQuery Queries | 50 GB scanned | ~$0.31 |
| Cloud Storage | 50 GB | ~$1.00 |
| **Total** | | ~$1.50 |

### Cost Optimization

1. **Use partitioned tables** - Query only date ranges you need
2. **Set lifecycle policies** - Auto-delete data after 90 days
3. **Archive old data** - Move to Cloud Archive Storage ($0.004/GB)
4. **Use BigQuery Slots** - For predictable, bulk workloads
5. **Set budget alerts** - Get notified before unexpected charges

See **Cost Optimization** section in **GCP_ADVANCED_CONFIG.md** for details.

---

## Monitoring

### Check Billing

```bash
gcloud billing accounts list
gcloud billing accounts describe ACCOUNT_ID
```

### View Recent API Calls

```bash
gcloud logging read \
  --limit 50 \
  --format json \
  "resource.type=bigquery_project"
```

### Monitor Model Performance

```python
from gcp_client import SportsMLClient

client = SportsMLClient()

# Get model accuracy trends
performance = client.bq.query_to_dataframe("""
    SELECT
      DATE(created_at) as prediction_date,
      model_id,
      COUNT(*) as predictions,
      SUM(CAST(is_correct AS INT64)) / COUNT(*) as accuracy
    FROM sports_data.predictions
    WHERE created_at >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 30 DAY)
    GROUP BY prediction_date, model_id
    ORDER BY prediction_date DESC
""")

print(performance)
```

---

## Next Steps

### 1. Load Data

```bash
# Upload ESPN data
gsutil cp espn_games.json gs://youre-edge-raw-data/data/

# Or use the Python client
python -c "
from gcp_client import StorageClient
storage = StorageClient()
storage.upload_blob('youre-edge-raw-data', 'espn_games.json', 'data/games.json')
"
```

### 2. Create Data Pipeline

Set up Cloud Functions or Cloud Run to:
- Fetch ESPN data via API
- Process and transform data
- Load into BigQuery

### 3. Train ML Models

Use BigQuery ML or vertex AI:
```sql
CREATE OR REPLACE MODEL `sports_data.spread_predictor`
  OPTIONS(
    model_type='linear_reg',
    input_label_cols=['spread']
  ) AS
SELECT
  home_team,
  away_team,
  season,
  spread as label
FROM `sports_data.training_labels`
WHERE prediction_type = 'spread';
```

### 4. Deploy Predictions API

Use Cloud Run to deploy a Flask/FastAPI app that:
- Loads trained models from Cloud Storage
- Makes predictions against BigQuery data
- Logs predictions back to BigQuery

### 5. Set Up Monitoring

- Create Cloud Monitoring dashboards
- Set up alerts for model performance degradation
- Track prediction accuracy trends

---

## Documentation Links

### GCP Official Docs
- [BigQuery Docs](https://cloud.google.com/bigquery/docs)
- [Cloud Storage Docs](https://cloud.google.com/storage/docs)
- [Cloud Run Docs](https://cloud.google.com/run/docs)
- [gcloud CLI Reference](https://cloud.google.com/sdk/gcloud/reference)

### GCP Best Practices
- [BigQuery Best Practices](https://cloud.google.com/bigquery/docs/best-practices)
- [Cloud Storage Security Best Practices](https://cloud.google.com/storage/docs/best-practices)
- [GCP Security Best Practices](https://cloud.google.com/security/best-practices)

### Python Client Libraries
- [google-cloud-bigquery](https://github.com/googleapis/python-bigquery)
- [google-cloud-storage](https://github.com/googleapis/python-storage)

---

## Support & Troubleshooting

1. **Check Advanced Guide**: `/GCP_ADVANCED_CONFIG.md`
2. **Review Setup Guide**: `/GCP_SETUP_GUIDE.md`
3. **Check GCP Status**: https://status.cloud.google.com
4. **GCP Support**: https://cloud.google.com/support
5. **Stack Overflow Tag**: `google-cloud-platform`

---

## File Reference

| File | Purpose |
|------|---------|
| `GCP_SETUP_GUIDE.md` | Detailed step-by-step setup instructions |
| `GCP_README.md` | This file - quick reference |
| `GCP_ADVANCED_CONFIG.md` | Advanced topics, troubleshooting, optimization |
| `gcp_quickstart.sh` | Automated setup script (bash) |
| `gcp_setup.py` | Python setup automation |
| `verify_gcp_setup.py` | Verify all infrastructure is working |
| `gcp_client.py` | Python client library for BigQuery & Storage |
| `gcp_requirements.txt` | Python package dependencies |

---

## License & Support

For questions or issues, refer to the documentation files or contact GCP support.

**Last Updated:** 2024-01-29
**Version:** 1.0
