# GCP Setup Quick Start

## Project ID
**universal-wares-462322-e1**

---

## Step 1: Install & Authenticate (5 minutes)

### Install gcloud CLI
```bash
# macOS
brew install --cask google-cloud-sdk

# Linux/WSL
curl https://sdk.cloud.google.com | bash
exec -l $SHELL
```

### Initialize gcloud
```bash
gcloud init
# Select project: universal-wares-462322-e1
# Choose default region: us-central1
```

### Set up Application Default Credentials
```bash
gcloud auth application-default login
```

### Set project environment variable
```bash
export GOOGLE_CLOUD_PROJECT="universal-wares-462322-e1"
echo 'export GOOGLE_CLOUD_PROJECT="universal-wares-462322-e1"' >> ~/.bashrc
source ~/.bashrc
```

### Verify setup
```bash
gcloud config list
gcloud auth list
```

---

## Step 2: Enable Required APIs (5 minutes)

```bash
gcloud services enable bigquery.googleapis.com
gcloud services enable storage-api.googleapis.com
gcloud services enable compute.googleapis.com
```

---

## Step 3: Create GCP Infrastructure (5 minutes)

### Option A: Automated Setup (Recommended)
```bash
cd /Users/twhite02/Personal/YoureEdge
python gcp_setup.py
```

### Option B: Manual Setup

**Create BigQuery dataset:**
```bash
bq mk --dataset \
  --location=US \
  --description="Sports ML training data" \
  sports_data
```

**Create Cloud Storage buckets:**
```bash
gsutil mb -p universal-wares-462322-e1 -l US gs://universal-wares-462322-e1-raw-data
gsutil mb -p universal-wares-462322-e1 -l US gs://universal-wares-462322-e1-models
gsutil mb -p universal-wares-462322-e1 -l US gs://universal-wares-462322-e1-training-data
```

---

## Step 4: Verify Setup (2 minutes)

```bash
python verify_gcp_setup.py
```

Expected output:
```
✅ BigQuery: Connected
✅ Cloud Storage: Connected
✅ Dataset sports_data: Exists
✅ Bucket raw-data: Exists
✅ Bucket models: Exists
✅ Bucket training-data: Exists
```

---

## Step 5: Install Python Packages (2 minutes)

```bash
pip install google-cloud-bigquery google-cloud-storage
```

---

## Done! 🎉

Your GCP infrastructure is ready. Now you can:

1. **Collect data:**
   ```bash
   python -m apps.backend.ml.run_backfill nba 2024 --start 2023-10-01 --end 2024-06-30
   ```

2. **Train models:**
   ```bash
   python -c "from apps.backend.ml.training_pipeline import BettingModelTrainer; BettingModelTrainer('universal-wares-462322-e1').train_all_models('nba')"
   ```

3. **Run backend:**
   ```bash
   python apps/backend/server.py
   ```

---

## Troubleshooting

### "Permission denied" error
- Make sure you ran `gcloud auth application-default login`
- Check IAM roles: `gcloud projects get-iam-policy universal-wares-462322-e1`

### "Dataset not found" error
- Run the automated setup: `python gcp_setup.py`
- Or manually create: `bq mk --dataset --location=US sports_data`

### "Bucket already exists" error
- That's fine! The buckets already exist and are ready to use

---

## Environment Variables

Add to your `.bashrc` or `.zshrc`:

```bash
export GOOGLE_CLOUD_PROJECT="universal-wares-462322-e1"
export GOOGLE_APPLICATION_CREDENTIALS="~/.gcp/service-account-key.json"
```

Then source the file:
```bash
source ~/.bashrc  # or ~/.zshrc
```
