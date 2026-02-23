# GCP Infrastructure Setup - File Index
## YoureEdge Sports ML Betting System

Quick navigation guide for all GCP setup files.

---

## Start Here

**New to this setup?** Read these in order:

1. **SETUP_SUMMARY.md** (2 min read)
   - Overview of what's been created
   - Quick start instructions
   - File locations and usage

2. **GCP_README.md** (5 min read)
   - Quick reference guide
   - Common commands
   - Python usage examples

3. **GCP_SETUP_GUIDE.md** (15 min read)
   - Detailed step-by-step walkthrough
   - Both automated and manual approaches
   - Complete documentation of each step

---

## Documentation Files

### GCP_SETUP_GUIDE.md
**Purpose:** Comprehensive step-by-step setup guide
**Read if:** You want a detailed walkthrough or manual setup
**Key sections:**
- Step 1: Create GCP Project
- Step 2: Enable Required APIs
- Step 3: Set Up Service Account
- Step 4: Install gcloud CLI
- Step 5: Create BigQuery Dataset and Tables
- Step 6: Create Cloud Storage Buckets
- Step 7: Verify Everything Works

### GCP_README.md
**Purpose:** Quick reference guide
**Read if:** You need a quick command or example
**Key sections:**
- Quick Start (5 minutes)
- Common Commands
- Python Usage Examples
- Troubleshooting
- Security Best Practices

### GCP_ADVANCED_CONFIG.md
**Purpose:** Advanced topics, troubleshooting, optimization
**Read if:**
- You're experiencing issues
- You want to optimize costs
- You need disaster recovery procedures
- You want to harden security

**Key sections:**
- Troubleshooting Common Issues (with solutions)
- Advanced BigQuery Configuration
- Cloud Storage Advanced Features
- Security Hardening
- Cost Optimization
- Monitoring and Alerting
- Disaster Recovery

### SETUP_SUMMARY.md
**Purpose:** Complete overview of the setup
**Read if:** You want a high-level understanding of what's been created
**Key sections:**
- What Has Been Created
- Getting Started (Fastest Path)
- File Locations and Usage
- Architecture Diagram
- Common Next Steps
- Production Checklist

---

## Script Files

### gcp_quickstart.sh
**Purpose:** Automated one-command setup of entire GCP infrastructure
**Language:** Bash
**Run:** `./gcp_quickstart.sh [PROJECT_NAME]`
**What it does:**
- Creates GCP project
- Enables required APIs
- Creates service account
- Generates authentication key
- Creates BigQuery dataset
- Creates Cloud Storage buckets
- Provides verification

**Time to run:** ~2-3 minutes

### gcp_setup.py
**Purpose:** Create BigQuery dataset, tables, and Cloud Storage buckets
**Language:** Python 3
**Run:** `python gcp_setup.py [--project-id PROJECT_ID]`
**What it does:**
- Creates `sports_data` dataset
- Creates 6 BigQuery tables with schemas
- Creates 3 Cloud Storage buckets
- Provides detailed verification report

**Time to run:** ~30-60 seconds

### verify_gcp_setup.py
**Purpose:** Verify all infrastructure is working correctly
**Language:** Python 3
**Run:** `python verify_gcp_setup.py`
**What it does:**
- Tests authentication
- Verifies dataset and tables exist
- Verifies buckets exist and are accessible
- Tests BigQuery connectivity
- Tests Cloud Storage connectivity
- Provides infrastructure summary

**Time to run:** ~10-20 seconds

---

## Python Client Files

### gcp_client.py
**Purpose:** Production-ready Python wrapper for BigQuery and Cloud Storage
**Language:** Python 3
**Usage:** Import in your Python code
**Classes:**
- `BigQueryClient` - Query and insert data into BigQuery
- `StorageClient` - Upload/download files from Cloud Storage
- `SportsMLClient` - High-level sports ML operations

**Key methods:**
```python
# BigQueryClient
query()                    # Execute SQL query
query_to_dataframe()       # Query and get pandas DataFrame
insert_rows()              # Insert data into table
create_table()             # Create new table

# StorageClient
upload_blob()              # Upload file to bucket
download_blob()            # Download file from bucket
list_blobs()               # List files in bucket
upload_json()              # Upload dict as JSON
download_json()            # Download JSON as dict

# SportsMLClient
insert_game()              # Insert game record
insert_prediction()        # Insert model prediction
get_recent_games()         # Get recent games by sport
get_model_performance()    # Get model prediction history
```

### gcp_requirements.txt
**Purpose:** Python package dependencies
**Usage:** `pip install -r gcp_requirements.txt`
**Contains:**
- google-cloud-bigquery
- google-cloud-storage
- google-auth
- pandas
- numpy
- python-dotenv

---

## Usage Workflows

### First-Time Setup (Easiest Path)

```
1. Read: SETUP_SUMMARY.md (overview)
2. Read: GCP_README.md (quick ref)
3. Run:  gcp_quickstart.sh (automated setup)
4. Run:  pip install -r gcp_requirements.txt (install deps)
5. Run:  gcp_setup.py (create schema)
6. Run:  verify_gcp_setup.py (test everything)
7. Read: GCP_SETUP_GUIDE.md (deep dive if needed)
```

### Manual Setup (More Control)

```
1. Read: GCP_SETUP_GUIDE.md (all steps)
2. Follow each step manually via console or CLI
3. Run:  gcp_setup.py (create schema)
4. Run:  verify_gcp_setup.py (test everything)
```

### Troubleshooting

```
1. Check: GCP_README.md > Troubleshooting
2. Check: GCP_ADVANCED_CONFIG.md > Troubleshooting Common Issues
3. Run:   verify_gcp_setup.py (identify issue)
4. Check: Relevant section in GCP_ADVANCED_CONFIG.md
```

### Optimization & Scaling

```
1. Read: GCP_ADVANCED_CONFIG.md > Cost Optimization
2. Read: GCP_ADVANCED_CONFIG.md > Advanced BigQuery Configuration
3. Read: GCP_ADVANCED_CONFIG.md > Monitoring and Alerting
```

### Production Deployment

```
1. Read: SETUP_SUMMARY.md > Production Checklist
2. Read: GCP_ADVANCED_CONFIG.md > Security Hardening
3. Read: GCP_ADVANCED_CONFIG.md > Monitoring and Alerting
4. Read: GCP_ADVANCED_CONFIG.md > Disaster Recovery
```

---

## File Reference by Use Case

### "I need a quick command"
→ **GCP_README.md** > Common Commands section

### "How do I upload data?"
→ **GCP_README.md** > Python Usage Examples
→ **gcp_client.py** > StorageClient.upload_blob()

### "How do I query data?"
→ **GCP_README.md** > Python Usage Examples
→ **gcp_client.py** > BigQueryClient.query_to_dataframe()

### "How do I set this up?"
→ **SETUP_SUMMARY.md** > Getting Started
→ **gcp_quickstart.sh** (run this)

### "Something isn't working"
→ **GCP_ADVANCED_CONFIG.md** > Troubleshooting Common Issues

### "How do I make this cheaper?"
→ **GCP_ADVANCED_CONFIG.md** > Cost Optimization

### "How do I secure this?"
→ **GCP_ADVANCED_CONFIG.md** > Security Hardening

### "How do I back this up?"
→ **GCP_ADVANCED_CONFIG.md** > Disaster Recovery

### "I need all the details"
→ **GCP_SETUP_GUIDE.md** (comprehensive guide)

---

## Infrastructure Overview

### What Gets Created

**BigQuery Dataset: `sports_data`**
- 6 tables (games, game_events, team_stats, training_labels, predictions, model_metadata)
- ~200 GB capacity
- ~$0.25-1.00/month storage

**Cloud Storage Buckets (3 total)**
- youre-edge-raw-data (for raw ESPN data)
- youre-edge-models (for trained models)
- youre-edge-training-data (for training data)
- ~$1-5/month per bucket

**Service Account**
- sports-ml-service
- BigQuery Admin + Storage Admin roles
- Secure JSON key authentication

### Resource Locations

```
Project:     youre-edge-sports-ml-[random number]
Region:      US (BigQuery), US-CENTRAL1 (Storage)
Dataset:     sports_data
Buckets:     3 (youre-edge-*)
Auth Key:    ~/.gcp/service-account-key.json
```

---

## Configuration Quick Links

### Set Environment Variables
```bash
export GOOGLE_APPLICATION_CREDENTIALS=~/.gcp/service-account-key.json
export GCLOUD_PROJECT=youre-edge-sports-ml-1234567890
```

### Check Status
```bash
gcloud config list
gcloud projects list
bq ls
gsutil ls
```

### Test Connection
```bash
python verify_gcp_setup.py
python gcp_client.py
```

---

## Common Commands Reference

| Task | Command |
|------|---------|
| List BigQuery datasets | `bq ls` |
| List BigQuery tables | `bq ls sports_data` |
| Query data | `bq query "SELECT * FROM sports_data.games"` |
| Upload file | `gsutil cp file.json gs://youre-edge-raw-data/` |
| List bucket contents | `gsutil ls gs://youre-edge-raw-data/` |
| Set default project | `gcloud config set project PROJECT_ID` |
| Authenticate | `gcloud auth application-default login` |

See **GCP_README.md** for more commands.

---

## Next Steps

1. **Read SETUP_SUMMARY.md** - Get the overview (2 min)
2. **Run gcp_quickstart.sh** - Automated setup (3 min)
3. **Run gcp_setup.py** - Create schema (1 min)
4. **Run verify_gcp_setup.py** - Test setup (1 min)
5. **Start coding** - Use gcp_client.py in your project

---

## File Sizes

| File | Size | Type |
|------|------|------|
| GCP_SETUP_GUIDE.md | 10 KB | Markdown |
| GCP_README.md | 11 KB | Markdown |
| GCP_ADVANCED_CONFIG.md | 14 KB | Markdown |
| SETUP_SUMMARY.md | 12 KB | Markdown |
| gcp_quickstart.sh | 6.6 KB | Bash |
| gcp_setup.py | 18 KB | Python |
| verify_gcp_setup.py | 7.7 KB | Python |
| gcp_client.py | 17 KB | Python |
| gcp_requirements.txt | 308 B | Text |
| **Total** | **~96 KB** | |

---

## Support

### Quick Answers
- Check **GCP_README.md** for common tasks
- Check **GCP_ADVANCED_CONFIG.md** for advanced topics

### Troubleshooting
- See **GCP_ADVANCED_CONFIG.md** > Troubleshooting section
- Run `verify_gcp_setup.py` to identify issues

### Need More Info
- See official GCP docs links in **GCP_SETUP_GUIDE.md**
- Check **GCP_ADVANCED_CONFIG.md** > Additional Resources

---

**Last Updated:** 2024-01-29
**Version:** 1.0
**Status:** Production Ready
