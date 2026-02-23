#!/bin/bash

# GCP QuickStart Script for YoureEdge Sports ML Betting System
#
# This script automates the initial GCP setup process.
# Prerequisites: gcloud CLI installed, valid Google Cloud account with billing enabled
#
# Usage: ./gcp_quickstart.sh [PROJECT_NAME]

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
PROJECT_NAME="${1:-youre-edge-sports-ml}"
PROJECT_ID="${PROJECT_NAME}-$(date +%s | tail -c 5)"
REGION="us-central1"
SERVICE_ACCOUNT_NAME="sports-ml-service"
DATASET_NAME="sports_data"

echo -e "${BLUE}================================================${NC}"
echo -e "${BLUE}GCP QuickStart for YoureEdge Sports ML${NC}"
echo -e "${BLUE}================================================${NC}\n"

# Function to print status
print_status() {
    echo -e "${GREEN}✓${NC} $1"
}

print_error() {
    echo -e "${RED}✗${NC} $1"
}

print_info() {
    echo -e "${YELLOW}ℹ${NC} $1"
}

# Check if gcloud is installed
if ! command -v gcloud &> /dev/null; then
    print_error "gcloud CLI not found. Install it from: https://cloud.google.com/sdk/docs/install"
    exit 1
fi

print_status "gcloud CLI found"

# Step 1: Create GCP Project
echo -e "\n${BLUE}Step 1: Creating GCP Project${NC}"
echo "Project ID: ${PROJECT_ID}"

if gcloud projects create "${PROJECT_ID}" \
    --name="${PROJECT_NAME}" \
    --set-as-default \
    2>/dev/null; then
    print_status "Project created: ${PROJECT_ID}"
else
    print_info "Project might already exist or failed to create"
fi

# Wait for project to be ready
sleep 2

# Set project as default
gcloud config set project "${PROJECT_ID}" 2>/dev/null
print_status "Project set as default"

# Step 2: Enable Required APIs
echo -e "\n${BLUE}Step 2: Enabling Required APIs${NC}"

APIS=(
    "bigquery.googleapis.com"
    "storage-api.googleapis.com"
    "storage-component.googleapis.com"
    "run.googleapis.com"
    "compute.googleapis.com"
)

for api in "${APIS[@]}"; do
    if gcloud services enable "${api}" --project="${PROJECT_ID}" 2>/dev/null; then
        print_status "Enabled: ${api}"
    else
        print_info "Could not enable ${api} (might already be enabled)"
    fi
done

# Step 3: Create Service Account
echo -e "\n${BLUE}Step 3: Creating Service Account${NC}"

SERVICE_ACCOUNT_EMAIL="${SERVICE_ACCOUNT_NAME}@${PROJECT_ID}.iam.gserviceaccount.com"

if gcloud iam service-accounts create "${SERVICE_ACCOUNT_NAME}" \
    --display-name="Sports ML Service Account" \
    --project="${PROJECT_ID}" \
    2>/dev/null; then
    print_status "Service account created: ${SERVICE_ACCOUNT_EMAIL}"
else
    print_info "Service account might already exist"
fi

# Grant BigQuery Admin role
echo "Granting BigQuery Admin role..."
gcloud projects add-iam-policy-binding "${PROJECT_ID}" \
    --member="serviceAccount:${SERVICE_ACCOUNT_EMAIL}" \
    --role="roles/bigquery.admin" \
    --quiet \
    2>/dev/null
print_status "BigQuery Admin role granted"

# Grant Storage Admin role
echo "Granting Storage Admin role..."
gcloud projects add-iam-policy-binding "${PROJECT_ID}" \
    --member="serviceAccount:${SERVICE_ACCOUNT_EMAIL}" \
    --role="roles/storage.admin" \
    --quiet \
    2>/dev/null
print_status "Storage Admin role granted"

# Step 4: Create and Download Service Account Key
echo -e "\n${BLUE}Step 4: Creating Service Account Key${NC}"

KEY_PATH="${HOME}/.gcp/service-account-key.json"
KEY_DIR="${HOME}/.gcp"

# Create directory if it doesn't exist
if [ ! -d "${KEY_DIR}" ]; then
    mkdir -p "${KEY_DIR}"
    print_status "Created directory: ${KEY_DIR}"
fi

if [ -f "${KEY_PATH}" ]; then
    print_info "Service account key already exists at ${KEY_PATH}"
else
    gcloud iam service-accounts keys create "${KEY_PATH}" \
        --iam-account="${SERVICE_ACCOUNT_EMAIL}" \
        --project="${PROJECT_ID}" \
        2>/dev/null

    chmod 600 "${KEY_PATH}"
    print_status "Service account key created and saved to: ${KEY_PATH}"
fi

# Step 5: Set up Application Default Credentials
echo -e "\n${BLUE}Step 5: Setting up Application Default Credentials${NC}"

export GOOGLE_APPLICATION_CREDENTIALS="${KEY_PATH}"
echo "export GOOGLE_APPLICATION_CREDENTIALS=\"${KEY_PATH}\"" >> ~/.bashrc
echo "export GOOGLE_APPLICATION_CREDENTIALS=\"${KEY_PATH}\"" >> ~/.zshrc 2>/dev/null || true

print_status "Environment variable set: GOOGLE_APPLICATION_CREDENTIALS"

# Step 6: Create BigQuery Dataset
echo -e "\n${BLUE}Step 6: Creating BigQuery Dataset${NC}"

bq mk --dataset \
    --description="Sports betting ML system data warehouse" \
    --location=US \
    "${PROJECT_ID}:${DATASET_NAME}" \
    2>/dev/null || print_info "Dataset might already exist"

print_status "Dataset created/verified: ${DATASET_NAME}"

# Step 7: Create Cloud Storage Buckets
echo -e "\n${BLUE}Step 7: Creating Cloud Storage Buckets${NC}"

BUCKETS=(
    "youre-edge-raw-data"
    "youre-edge-models"
    "youre-edge-training-data"
)

for bucket in "${BUCKETS[@]}"; do
    if gsutil mb -p "${PROJECT_ID}" -l "${REGION}" "gs://${bucket}/" 2>/dev/null; then
        print_status "Bucket created: ${bucket}"
    else
        print_info "Bucket might already exist: ${bucket}"
    fi
done

# Step 8: Verification
echo -e "\n${BLUE}Step 8: Verifying Setup${NC}"

# Test BigQuery
if bq ls --project_id="${PROJECT_ID}" > /dev/null 2>&1; then
    print_status "BigQuery accessible"
else
    print_error "Could not access BigQuery"
fi

# Test Cloud Storage
if gsutil ls -p "${PROJECT_ID}" > /dev/null 2>&1; then
    print_status "Cloud Storage accessible"
else
    print_error "Could not access Cloud Storage"
fi

# Final Summary
echo -e "\n${BLUE}================================================${NC}"
echo -e "${GREEN}Setup Complete!${NC}"
echo -e "${BLUE}================================================${NC}\n"

echo "Project Details:"
echo "  Project ID: ${PROJECT_ID}"
echo "  Service Account: ${SERVICE_ACCOUNT_EMAIL}"
echo "  Key Location: ${KEY_PATH}"
echo "  Region: ${REGION}"
echo "  Dataset: ${DATASET_NAME}"
echo ""

echo "Next Steps:"
echo "1. Run the Python setup script to create BigQuery tables:"
echo "   export GOOGLE_APPLICATION_CREDENTIALS=\"${KEY_PATH}\""
echo "   python gcp_setup.py --project-id ${PROJECT_ID}"
echo ""
echo "2. Verify the setup:"
echo "   python verify_gcp_setup.py"
echo ""
echo "3. Test Python client:"
echo "   python gcp_client.py"
echo ""
echo "Documentation:"
echo "  - See GCP_SETUP_GUIDE.md for detailed instructions"
echo "  - See gcp_client.py for Python API examples"
echo ""
echo -e "${YELLOW}Important: Keep your service account key secure!${NC}"
echo "  - Never commit it to version control"
echo "  - Rotate keys regularly"
echo "  - Set appropriate file permissions (chmod 600)"
echo ""
