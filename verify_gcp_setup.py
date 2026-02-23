#!/usr/bin/env python3
"""
Verify GCP infrastructure setup.

Run: python verify_gcp_setup.py
"""

import sys
import os

# Add backend to path so we can import config
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "apps", "backend"))

from config import config

PROJECT_ID = config.get_secret("GOOGLE_CLOUD_PROJECT", required=True)


def check_bigquery():
    """Check BigQuery setup."""
    try:
        from google.cloud import bigquery
        client = bigquery.Client(project=PROJECT_ID)
        
        # Check dataset
        dataset_id = "sports_data"
        dataset = client.get_dataset(f"{PROJECT_ID}.{dataset_id}")
        print(f"✅ BigQuery Dataset: {dataset_id}")
        
        # Check tables
        tables = client.list_tables(dataset)
        table_names = [t.table_id for t in tables]
        for table_name in table_names:
            print(f"   ✅ Table: {table_name}")
        
        return True
    except Exception as exc:
        print(f"❌ BigQuery check failed: {exc}")
        return False


def check_storage():
    """Check Cloud Storage setup."""
    try:
        from google.cloud import storage
        client = storage.Client(project=PROJECT_ID)
        
        buckets = [
            f"{PROJECT_ID}-raw-data",
            f"{PROJECT_ID}-models",
            f"{PROJECT_ID}-training-data",
        ]
        
        for bucket_name in buckets:
            bucket = client.get_bucket(bucket_name)
            print(f"✅ Cloud Storage: {bucket_name}")
        
        return True
    except Exception as exc:
        print(f"❌ Cloud Storage check failed: {exc}")
        return False


def main():
    """Run verification."""
    print("\n" + "=" * 60)
    print("GCP Setup Verification")
    print("=" * 60)
    print(f"Project ID: {PROJECT_ID}\n")
    
    print("Checking BigQuery...")
    bq_ok = check_bigquery()
    
    print("\nChecking Cloud Storage...")
    storage_ok = check_storage()
    
    print("\n" + "=" * 60)
    if bq_ok and storage_ok:
        print("✅ All systems operational!")
        print("=" * 60)
        print("\nYou can now:")
        print("1. Collect data: python -m apps.backend.ml.run_backfill nba 2024")
        print("2. Train models: python -m apps.backend.ml.training_pipeline")
        print("3. Run backend: python apps/backend/server.py")
        return 0
    else:
        print("⚠️  Some systems need attention")
        print("=" * 60)
        return 1


if __name__ == "__main__":
    sys.exit(main())
