# Google Cloud Platform Setup Guide
## Sports ML Betting System Infrastructure

This guide walks you through setting up a complete GCP infrastructure for the YoureEdge sports ML betting system.

---

## Table of Contents
1. [Prerequisites](#prerequisites)
2. [Step 1: Create GCP Project](#step-1-create-gcp-project)
3. [Step 2: Enable Required APIs](#step-2-enable-required-apis)
4. [Step 3: Set Up Service Account](#step-3-set-up-service-account)
5. [Step 4: Install and Configure gcloud CLI](#step-4-install-and-configure-gcloud-cli)
6. [Step 5: Create BigQuery Dataset and Tables](#step-5-create-bigquery-dataset-and-tables)
7. [Step 6: Create Cloud Storage Buckets](#step-6-create-cloud-storage-buckets)
8. [Step 7: Verify Everything Works](#step-7-verify-everything-works)

---

## Prerequisites

- A Google Cloud account (sign up at https://cloud.google.com)
- A valid billing method (required for GCP)
- macOS or Linux (this guide focuses on Unix-like systems)
- Python 3.8+ installed
- ~30 minutes to complete the setup

---

## Step 1: Create GCP Project

### Using Google Cloud Console (Web UI)

1. **Navigate to Google Cloud Console**
   - Go to https://console.cloud.google.com
   - Sign in with your Google account

2. **Create a New Project**
   - Click on the project dropdown at the top of the page
   - Click "NEW PROJECT"
   - Fill in the details:
     - **Project Name:** `youre-edge-sports-ml`
     - **Organization:** (optional, leave blank if you don't have one)
   - Click "CREATE"

3. **Wait for Project Creation**
   - The project will be created in ~30 seconds
   - A notification will appear when complete

4. **Note Your Project ID**
   - Once created, click on the project to open it
   - Copy the **Project ID** (shown under the project name in the header)
   - Format is usually something like: `youre-edge-sports-ml-1234567890`
   - **Save this ID - you'll need it throughout the setup**

### Alternative: Create Using gcloud CLI (After Installation)

```bash
gcloud projects create youre-edge-sports-ml --name="YoureEdge Sports ML Betting System"
```

---

## Step 2: Enable Required APIs

### Using Google Cloud Console

1. **Open the API & Services Dashboard**
   - In Cloud Console, search for "APIs & Services" in the search bar
   - Click on "APIs & Services" > "Library"

2. **Enable Each Required API**

   For each API below:
   - Search for the API name in the search box
   - Click on the API
   - Click "ENABLE"

   **Required APIs:**
   - ✅ BigQuery API
   - ✅ Cloud Storage API
   - ✅ Cloud Run API
   - ✅ Compute Engine API

3. **Enable All at Once (Optional)**

   You can also enable multiple APIs with gcloud:

   ```bash
   # Set your project ID first
   export PROJECT_ID="youre-edge-sports-ml-1234567890"  # Replace with your actual project ID

   gcloud services enable \
     bigquery.googleapis.com \
     storage-api.googleapis.com \
     storage-component.googleapis.com \
     run.googleapis.com \
     compute.googleapis.com \
     --project=$PROJECT_ID
   ```

---

## Step 3: Set Up Service Account

### Using Google Cloud Console

1. **Navigate to Service Accounts**
   - Go to "APIs & Services" > "Credentials"
   - Click "CREATE CREDENTIALS" > "Service Account"

2. **Fill in Service Account Details**
   - **Service Account Name:** `sports-ml-service`
   - **Service Account ID:** (auto-filled, based on name)
   - **Description:** "Service account for YoureEdge sports ML system access to BigQuery and Cloud Storage"
   - Click "CREATE AND CONTINUE"

3. **Grant Permissions**
   - Click "CONTINUE" on the service account creation page
   - Select roles to add:
     - **BigQuery Admin** (for BigQuery dataset/table management)
     - **Storage Admin** (for Cloud Storage bucket management)
   - Click "CONTINUE"

4. **Create and Download JSON Key**
   - Click "CREATE KEY"
   - Select "JSON" format
   - Click "CREATE"
   - A JSON file will automatically download
   - **Save this file securely!** This is your authentication key

5. **Store the Key Securely**
   ```bash
   # Recommended location:
   mkdir -p ~/.gcp
   mv ~/Downloads/youre-edge-sports-ml-*.json ~/.gcp/service-account-key.json
   chmod 600 ~/.gcp/service-account-key.json
   ```

### Using gcloud CLI

```bash
export PROJECT_ID="youre-edge-sports-ml-1234567890"  # Replace with your actual project ID

# Create the service account
gcloud iam service-accounts create sports-ml-service \
  --display-name="Sports ML Service Account" \
  --project=$PROJECT_ID

# Grant BigQuery Admin role
gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member="serviceAccount:sports-ml-service@${PROJECT_ID}.iam.gserviceaccount.com" \
  --role="roles/bigquery.admin"

# Grant Storage Admin role
gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member="serviceAccount:sports-ml-service@${PROJECT_ID}.iam.gserviceaccount.com" \
  --role="roles/storage.admin"

# Create and download JSON key
gcloud iam service-accounts keys create ~/.gcp/service-account-key.json \
  --iam-account=sports-ml-service@${PROJECT_ID}.iam.gserviceaccount.com \
  --project=$PROJECT_ID
```

---

## Step 4: Install and Configure gcloud CLI

### Install gcloud SDK

**macOS with Homebrew:**
```bash
brew install --cask google-cloud-sdk
gcloud init
```

**Alternative - Direct Installation:**
1. Download from: https://cloud.google.com/sdk/docs/install
2. Follow platform-specific installation instructions
3. Run: `gcloud init`

### Configure Application Default Credentials

```bash
# Set environment variable to point to your service account key
export GOOGLE_APPLICATION_CREDENTIALS=~/.gcp/service-account-key.json

# Authenticate with gcloud
gcloud auth application-default login

# Verify authentication
gcloud auth list
gcloud config list
```

### Set Default Project

```bash
gcloud config set project youre-edge-sports-ml-1234567890  # Replace with your actual project ID
```

---

## Step 5: Create BigQuery Dataset and Tables

### Run Automated Setup Script

We've created a Python script that automates this entire process:

```bash
# First, ensure the environment variable is set
export GOOGLE_APPLICATION_CREDENTIALS=~/.gcp/service-account-key.json

# Run the setup script
python gcp_setup.py

# Optional: Specify your project ID if it's not in your gcloud config
python gcp_setup.py --project-id youre-edge-sports-ml-1234567890
```

### Manual Setup (Alternative)

If you prefer to create tables manually:

```bash
export PROJECT_ID="youre-edge-sports-ml-1234567890"

# Create dataset
bq mk --dataset \
  --description="Sports betting ML system data warehouse" \
  --location=US \
  $PROJECT_ID:sports_data

# Create tables (see SQL schema in the gcp_setup.py script)
```

---

## Step 6: Create Cloud Storage Buckets

### Using Automated Script

The `gcp_setup.py` script handles this automatically.

### Manual Setup (Alternative)

```bash
export PROJECT_ID="youre-edge-sports-ml-1234567890"

# Create raw data bucket
gsutil mb -p $PROJECT_ID -l us-central1 gs://youre-edge-raw-data/

# Create models bucket
gsutil mb -p $PROJECT_ID -l us-central1 gs://youre-edge-models/

# Create training data bucket
gsutil mb -p $PROJECT_ID -l us-central1 gs://youre-edge-training-data/

# Set lifecycle policies (optional - delete old files after 90 days)
gsutil lifecycle set - gs://youre-edge-raw-data/ <<EOF
{
  "lifecycle": {
    "rule": [
      {
        "action": {"type": "Delete"},
        "condition": {"age": 90}
      }
    ]
  }
}
EOF
```

---

## Step 7: Verify Everything Works

### Quick Verification

```bash
# Check BigQuery dataset and tables
bq ls --project_id=$PROJECT_ID
bq ls --project_id=$PROJECT_ID sports_data

# Check Cloud Storage buckets
gsutil ls -p $PROJECT_ID

# Test Python connection
python -c "
from google.cloud import bigquery, storage
print('BigQuery client initialized:', bigquery.Client())
print('Storage client initialized:', storage.Client())
"
```

### Full Verification Script

```bash
python verify_gcp_setup.py
```

---

## Next Steps

1. **Upload Raw Data**
   ```bash
   gsutil cp your_data.json gs://youre-edge-raw-data/
   ```

2. **Create Python Client**
   See `gcp_client.py` for example usage

3. **Deploy ML Model Pipeline**
   Use `Cloud Run` for serverless deployment

4. **Set Up Monitoring**
   Configure Cloud Logging and Cloud Monitoring dashboards

---

## Troubleshooting

### "Permission denied" Error

**Solution:** Verify service account key path:
```bash
echo $GOOGLE_APPLICATION_CREDENTIALS
ls -la ~/.gcp/service-account-key.json
```

### "Project not found" Error

**Solution:** Check your project ID:
```bash
gcloud config list
gcloud projects list
```

### BigQuery API Not Enabled

**Solution:** Enable it via console or CLI:
```bash
gcloud services enable bigquery.googleapis.com --project=$PROJECT_ID
```

### Can't Create Buckets

**Solution:** Verify billing is enabled:
- Go to https://console.cloud.google.com/billing
- Ensure billing account is linked to your project

---

## Documentation Links

- [Google Cloud Platform Docs](https://cloud.google.com/docs)
- [BigQuery Docs](https://cloud.google.com/bigquery/docs)
- [Cloud Storage Docs](https://cloud.google.com/storage/docs)
- [gcloud CLI Reference](https://cloud.google.com/sdk/gcloud/reference)
- [Service Accounts](https://cloud.google.com/iam/docs/service-accounts)

---

## Security Best Practices

1. **Never commit service account keys to version control**
   - Add to `.gitignore`: `~/.gcp/`

2. **Rotate keys regularly**
   - Delete old keys after creating new ones
   - Delete in "APIs & Services" > "Credentials"

3. **Use least privilege**
   - Only grant necessary roles to service accounts
   - Review permissions regularly

4. **Enable audit logging**
   - Monitor all API calls in Cloud Logging
   - Set up alerts for suspicious activity

5. **Use VPC Service Controls (optional)**
   - Add an extra layer of security for sensitive data

---

## Cost Optimization

1. **BigQuery Pricing**
   - Storage: ~$0.025/GB/month
   - Queries: ~$6.25 per TB scanned (first 1 TB free per month)
   - Use partitioned/clustered tables to reduce scan costs

2. **Cloud Storage Pricing**
   - Storage: ~$0.020/GB/month
   - Requests: Minimal cost
   - Set lifecycle policies to delete old data

3. **Recommended Configuration**
   - Use partitioned tables by date
   - Archive old data to Cloud Archive Storage
   - Set up budget alerts: https://console.cloud.google.com/billing/budgets

---

## Support

For issues or questions:
- Check GCP documentation (links above)
- Visit GCP support: https://cloud.google.com/support
- Check Cloud Console logs for detailed error messages
