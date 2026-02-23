# GCP Advanced Configuration & Troubleshooting
## YoureEdge Sports ML Betting System

---

## Table of Contents
1. [Troubleshooting Common Issues](#troubleshooting-common-issues)
2. [Advanced BigQuery Configuration](#advanced-bigquery-configuration)
3. [Cloud Storage Advanced Features](#cloud-storage-advanced-features)
4. [Security Hardening](#security-hardening)
5. [Cost Optimization](#cost-optimization)
6. [Monitoring and Alerting](#monitoring-and-alerting)
7. [Disaster Recovery](#disaster-recovery)

---

## Troubleshooting Common Issues

### Issue: "Permission denied" when running Python scripts

**Symptoms:**
```
google.auth.exceptions.DefaultCredentialsError: Could not automatically determine credentials
```

**Solutions:**

1. **Set Environment Variable**
   ```bash
   export GOOGLE_APPLICATION_CREDENTIALS=~/.gcp/service-account-key.json
   ```

2. **Verify File Exists and is Readable**
   ```bash
   ls -la ~/.gcp/service-account-key.json
   # Should show: -rw------- (600 permissions)

   # Fix permissions if needed
   chmod 600 ~/.gcp/service-account-key.json
   ```

3. **Check Service Account Permissions**
   ```bash
   # List service accounts
   gcloud iam service-accounts list --project=YOUR_PROJECT_ID

   # Check roles
   gcloud projects get-iam-policy YOUR_PROJECT_ID \
     --flatten="bindings[].members" \
     --filter="bindings.members:sports-ml-service@*"
   ```

4. **Regenerate Service Account Key**
   ```bash
   # List existing keys
   gcloud iam service-accounts keys list \
     --iam-account=sports-ml-service@PROJECT_ID.iam.gserviceaccount.com

   # Delete old key
   gcloud iam service-accounts keys delete KEY_ID \
     --iam-account=sports-ml-service@PROJECT_ID.iam.gserviceaccount.com

   # Create new key
   gcloud iam service-accounts keys create ~/.gcp/service-account-key.json \
     --iam-account=sports-ml-service@PROJECT_ID.iam.gserviceaccount.com
   ```

---

### Issue: "BigQuery API not enabled"

**Symptoms:**
```
google.api_core.exceptions.NotFound: 404 Not found. API not enabled for project
```

**Solution:**
```bash
export PROJECT_ID="your-project-id"

# Enable the API
gcloud services enable bigquery.googleapis.com --project=$PROJECT_ID

# Verify it's enabled
gcloud services list --enabled --project=$PROJECT_ID | grep bigquery
```

---

### Issue: "Cannot create bucket - insufficient permissions"

**Symptoms:**
```
google.cloud.exceptions.Forbidden: 403 Forbidden
```

**Solution:**

1. **Verify Service Account Roles**
   ```bash
   gcloud projects get-iam-policy $PROJECT_ID \
     --flatten="bindings[].members" \
     --format='table(bindings.role)' \
     --filter="bindings.members:sports-ml-service@*"
   ```

2. **Add Storage Admin Role if Missing**
   ```bash
   gcloud projects add-iam-policy-binding $PROJECT_ID \
     --member="serviceAccount:sports-ml-service@${PROJECT_ID}.iam.gserviceaccount.com" \
     --role="roles/storage.admin"
   ```

---

### Issue: "Project not found" or "Authentication failed"

**Solutions:**

1. **Check Default Project Configuration**
   ```bash
   gcloud config list

   # Set default project
   gcloud config set project YOUR_PROJECT_ID
   ```

2. **List Available Projects**
   ```bash
   gcloud projects list
   ```

3. **Re-authenticate**
   ```bash
   gcloud auth application-default login
   # This opens a browser for OAuth2 authentication
   ```

---

### Issue: BigQuery queries are very slow or expensive

**Symptoms:**
- Queries take >30 seconds
- Billing costs higher than expected

**Solutions:**

1. **Use Partition and Clustering**
   ```sql
   -- Query to check table size and partitioning
   SELECT
     table_name,
     size_bytes / (1024*1024*1024) as size_gb,
     row_count,
     type
   FROM `project.dataset.__TABLES__`
   WHERE table_name IN ('games', 'game_events', 'predictions')
   ORDER BY size_bytes DESC;
   ```

2. **Create Partitioned Tables**
   ```sql
   -- Example: Create partitioned game_events table
   CREATE OR REPLACE TABLE `project.sports_data.game_events_partitioned`
   PARTITION BY DATE(created_at)
   CLUSTER BY game_id
   AS
   SELECT * FROM `project.sports_data.game_events`;
   ```

3. **Use Materialized Views for Aggregations**
   ```sql
   -- Create materialized view for daily stats
   CREATE MATERIALIZED VIEW `project.sports_data.daily_game_stats` AS
   SELECT
     DATE(created_at) as stats_date,
     COUNT(DISTINCT game_id) as games_count,
     COUNT(*) as events_count
   FROM `project.sports_data.game_events`
   GROUP BY stats_date;

   -- Refresh materialized view
   CALL BQ.REFRESH_MATERIALIZED_VIEW('project.sports_data.daily_game_stats');
   ```

4. **Estimate Query Cost Before Running**
   ```bash
   # Use dry_run flag in Python
   query_job = bq_client.query(query_string, job_config=bigquery.QueryJobConfig(dry_run=True))
   print(f"Query will scan: {query_job.total_bytes_billed} bytes")
   ```

---

## Advanced BigQuery Configuration

### Scheduled Queries

Set up queries to run automatically:

```python
from google.cloud import bigquery

client = bigquery.Client()

# Create a scheduled query that runs daily
transfer_config = bigquery.TransferConfig(
    display_name="Daily Team Stats Update",
    data_source_id="google_cloud_storage",
    destination_dataset_id="sports_data",
    schedule="every day 02:00",
)

transfer = client.create_transfer_config(
    parent=client.common_project_path(client.project),
    transfer_config=transfer_config,
)
```

---

### Export Data to Cloud Storage

```python
from google.cloud import bigquery
import uuid

client = bigquery.Client()

job_config = bigquery.ExtractJobConfig()
job_config.compression = bigquery.Compression.GZIP
job_config.destination_format = bigquery.DestinationFormat.NEWLINE_DELIMITED_JSON

extract_job = client.extract_table(
    "sports_data.games",
    "gs://youre-edge-training-data/exports/games_*.json.gz",
    job_config=job_config,
)

extract_job.result()  # Wait for job to complete
print("Export completed")
```

---

### Create Snapshots for Data Recovery

```python
from google.cloud import bigquery
from datetime import datetime, timedelta

client = bigquery.Client()

# Create a snapshot of a table from 7 days ago
table_id = "sports_data.games"
table = client.get_table(table_id)

snapshot_id = f"{table_id}@{int((datetime.utcnow() - timedelta(days=7)).timestamp() * 1000)}"
snapshot_table = client.copy_table(
    snapshot_id,
    f"sports_data.games_snapshot_7days",
)

snapshot_table.result()
print("Snapshot created")
```

---

## Cloud Storage Advanced Features

### Lifecycle Management

Automatically delete or archive old data:

```bash
# Create lifecycle policy file
cat > lifecycle.json <<EOF
{
  "lifecycle": {
    "rule": [
      {
        "action": {"type": "Delete"},
        "condition": {
          "age": 90,
          "matchesPrefix": ["temp/"]
        }
      },
      {
        "action": {
          "type": "SetStorageClass",
          "storageClass": "NEARLINE"
        },
        "condition": {
          "age": 30
        }
      }
    ]
  }
}
EOF

# Apply to bucket
gsutil lifecycle set lifecycle.json gs://youre-edge-raw-data/
```

---

### Enable Versioning

Keep previous versions of objects:

```bash
# Enable versioning
gsutil versioning set on gs://youre-edge-models/

# List all versions of an object
gsutil ls -L gs://youre-edge-models/model_v1.pkl

# Restore a previous version
gsutil cp gs://youre-edge-models/model_v1.pkl#GENERATION_NUMBER gs://youre-edge-models/model_v1.pkl
```

---

### Set Up Signed URLs for Secure Access

Allow temporary access without authentication:

```python
from google.cloud import storage
from datetime import timedelta

client = storage.Client()
bucket = client.bucket("youre-edge-models")
blob = bucket.blob("model_v1.pkl")

# Generate URL valid for 1 hour
url = blob.generate_signed_url(
    version="v4",
    expiration=timedelta(hours=1),
    method="GET",
)

print(f"Signed URL: {url}")
```

---

### Enable Logging and Audit Trail

```bash
# Enable access logs
gsutil logging set on -b gs://youre-edge-logs gs://youre-edge-raw-data/

# View logs
gsutil ls gs://youre-edge-logs/
```

---

## Security Hardening

### 1. Use Workload Identity (if running on GKE)

```bash
# Bind service account to Kubernetes service account
gcloud iam service-accounts add-iam-policy-binding \
  sports-ml-service@PROJECT_ID.iam.gserviceaccount.com \
  --role roles/iam.workloadIdentityUser \
  --member "serviceAccount:PROJECT_ID.svc.id.goog[NAMESPACE/KSA_NAME]"
```

---

### 2. Enable Audit Logging

View all API calls in Cloud Logging:

```bash
# View recent admin activity logs
gcloud logging read \
  "resource.type=service_account AND protoPayload.methodName=google.iam.admin.v1.CreateServiceAccount" \
  --limit 10 \
  --format json
```

---

### 3. Restrict Data Access with VPC Service Controls

```bash
# Create VPC Service Perimeter (via console or gcloud)
gcloud access-context-manager perimeters create restricted-perimeter \
  --vpc-allowed-services=bigquery.googleapis.com,storage.googleapis.com
```

---

### 4. Use Customer-Managed Encryption Keys (CMEK)

```bash
# Create Cloud KMS key
gcloud kms keys create sports-ml-key \
  --location=us \
  --keyring=sports-ml-keyring

# Configure BigQuery to use CMEK
# (Requires gcloud bq command or console - Python API support limited)
```

---

### 5. Set Up Private Google Access

```bash
# Configure VPC to use private Google API endpoints
gcloud compute networks create sports-ml-vpc \
  --subnet-mode=custom

gcloud compute networks subnets create sports-ml-subnet \
  --network=sports-ml-vpc \
  --region=us-central1 \
  --range=10.0.0.0/20 \
  --enable-private-ip-google-access
```

---

## Cost Optimization

### 1. Monitor Costs with Billing Alerts

```bash
# Set up a billing alert via console
# Billing > Budgets and Alerts > CREATE BUDGET
# Or use Python admin API
```

---

### 2. Use BigQuery Slots for Predictable Costs

```bash
# Create a slot reservation
gcloud bigquery reservations create sports-ml-reservation \
  --location=us \
  --slot-capacity=100 \
  --commitment-plan=monthly
```

---

### 3. Archive Old Data to Cold Storage

```bash
# Create archive bucket with lower storage class
gsutil mb -l us-central1 -c ARCHIVE gs://youre-edge-archive/

# Transfer old data
gsutil -m cp -r gs://youre-edge-raw-data/archive/* gs://youre-edge-archive/

# Delete after confirming transfer
gsutil -m rm -r gs://youre-edge-raw-data/archive/
```

---

### 4. Use Materialized Views Instead of Regular Queries

```sql
-- Materialized views cache results and use slots more efficiently
CREATE MATERIALIZED VIEW `project.sports_data.team_stats_cached` AS
SELECT
  team_id,
  COUNT(*) as games_played,
  AVG(points_for) as avg_points_for,
  AVG(points_against) as avg_points_against
FROM `project.sports_data.team_stats`
WHERE stat_date >= DATE_SUB(CURRENT_DATE(), INTERVAL 30 DAY)
GROUP BY team_id;
```

---

## Monitoring and Alerting

### Set Up Cloud Monitoring Dashboard

```python
from google.cloud import monitoring_v3

project = "projects/PROJECT_ID"
client = monitoring_v3.MetricServiceClient()

# Example: Create a chart for BigQuery query costs
# (Recommend using console for easier setup)
```

---

### Create Log-Based Alerts

```bash
# Alert when BigQuery job fails
gcloud alpha monitoring policies create \
  --notification-channels=CHANNEL_ID \
  --display-name="BigQuery Job Failures" \
  --condition-display-name="Failed Jobs" \
  --condition-threshold-value=1 \
  --condition-threshold-duration=300s
```

---

### Monitor Model Prediction Performance

```python
from google.cloud import bigquery

client = bigquery.Client()

# Query to monitor model accuracy trends
query = """
SELECT
  DATE(created_at) as prediction_date,
  model_id,
  COUNT(*) as predictions,
  SUM(CAST(is_correct AS INT64)) / COUNT(*) as accuracy,
  AVG(confidence) as avg_confidence
FROM sports_data.predictions
WHERE created_at >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 30 DAY)
GROUP BY prediction_date, model_id
ORDER BY prediction_date DESC
"""

results = client.query(query).result()
for row in results:
    print(row)
```

---

## Disaster Recovery

### Backup Strategy

1. **BigQuery Dataset Snapshot**
   ```python
   from google.cloud import bigquery

   client = bigquery.Client()

   # Export entire dataset weekly
   for table in client.list_tables("sports_data"):
       export_job = client.extract_table(
           f"sports_data.{table.table_id}",
           f"gs://youre-edge-training-data/backups/{table.table_id}_{{YYYY}}_{{MM}}_{{DD}}/*.parquet",
       )
       export_job.result()
   ```

2. **Cloud Storage Cross-Region Replication**
   ```bash
   # Use Cloud Storage Transfer Service for cross-region backup
   # Configure via console or use:
   gcloud transfer operations create \
     --source-bucket=youre-edge-raw-data \
     --destination-bucket=youre-edge-backup \
     --allow-empty-days
   ```

---

### Recovery Procedures

1. **Restore BigQuery Table from Snapshot**
   ```bash
   # Restore from exported parquet files
   bq load --source_format=PARQUET \
     sports_data.games_restored \
     gs://youre-edge-training-data/backups/games_2024_01_29/*.parquet
   ```

2. **Restore Cloud Storage Objects**
   ```bash
   # Restore specific file from backup
   gsutil cp gs://youre-edge-backup/models/model_v1.pkl gs://youre-edge-models/model_v1.pkl.recovered
   ```

---

## Additional Resources

- [BigQuery Best Practices](https://cloud.google.com/bigquery/docs/best-practices)
- [Cloud Storage Security](https://cloud.google.com/storage/docs/security)
- [GCP Security Command Center](https://cloud.google.com/security-command-center/docs)
- [Cloud Audit Logs](https://cloud.google.com/logging/docs/audit)
- [Cost Optimization Best Practices](https://cloud.google.com/architecture/cost-optimization)
