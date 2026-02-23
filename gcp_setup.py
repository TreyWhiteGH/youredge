#!/usr/bin/env python3
"""
Automated GCP setup script.

Creates BigQuery dataset, tables, and Cloud Storage buckets.
Run: python gcp_setup.py
"""

import sys
import os

# Add backend to path so we can import config
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "apps", "backend"))

from config import config

PROJECT_ID = config.get_secret("GOOGLE_CLOUD_PROJECT", required=True)


def setup_bigquery():
    """Create BigQuery dataset and tables."""
    try:
        from google.cloud import bigquery
    except ImportError:
        print("❌ google-cloud-bigquery not installed")
        print("   Run: pip install google-cloud-bigquery")
        return False

    try:
        client = bigquery.Client(project=PROJECT_ID)
        dataset_id = "sports_data"
        dataset = bigquery.Dataset(f"{PROJECT_ID}.{dataset_id}")
        dataset.location = "US"
        dataset = client.create_dataset(dataset, exists_ok=True)
        print(f"✅ BigQuery Dataset: {dataset_id}")

        # Create tables with schema
        tables = {
            'games': [
                bigquery.SchemaField('game_id', 'STRING', mode='REQUIRED'),
                bigquery.SchemaField('sport', 'STRING', mode='REQUIRED'),
                bigquery.SchemaField('season', 'INTEGER'),
                bigquery.SchemaField('game_date', 'DATE', mode='REQUIRED'),
                bigquery.SchemaField('home_team_id', 'STRING'),
                bigquery.SchemaField('away_team_id', 'STRING'),
                bigquery.SchemaField('home_score', 'INTEGER'),
                bigquery.SchemaField('away_score', 'INTEGER'),
                bigquery.SchemaField('status', 'STRING'),
                bigquery.SchemaField('espn_event_id', 'STRING'),
                bigquery.SchemaField('created_at', 'TIMESTAMP'),
            ],
            'game_events': [
                bigquery.SchemaField('game_id', 'STRING'),
                bigquery.SchemaField('period', 'INTEGER'),
                bigquery.SchemaField('clock_seconds', 'INTEGER'),
                bigquery.SchemaField('event_type', 'STRING'),
                bigquery.SchemaField('team_id', 'STRING'),
                bigquery.SchemaField('description', 'STRING'),
                bigquery.SchemaField('home_score', 'INTEGER'),
                bigquery.SchemaField('away_score', 'INTEGER'),
                bigquery.SchemaField('created_at', 'TIMESTAMP'),
            ],
            'training_labels': [
                bigquery.SchemaField('game_id', 'STRING'),
                bigquery.SchemaField('market', 'STRING'),
                bigquery.SchemaField('selection', 'STRING'),
                bigquery.SchemaField('line', 'FLOAT64'),
                bigquery.SchemaField('outcome', 'BOOLEAN'),
                bigquery.SchemaField('created_at', 'TIMESTAMP'),
            ],
            'predictions': [
                bigquery.SchemaField('game_id', 'STRING'),
                bigquery.SchemaField('sport', 'STRING'),
                bigquery.SchemaField('market', 'STRING'),
                bigquery.SchemaField('selection', 'STRING'),
                bigquery.SchemaField('confidence', 'FLOAT64'),
                bigquery.SchemaField('edge', 'FLOAT64'),
                bigquery.SchemaField('correct', 'BOOLEAN'),
                bigquery.SchemaField('created_at', 'TIMESTAMP'),
            ],
            'model_metadata': [
                bigquery.SchemaField('model_name', 'STRING', mode='REQUIRED'),
                bigquery.SchemaField('sport', 'STRING'),
                bigquery.SchemaField('market', 'STRING'),
                bigquery.SchemaField('version', 'STRING'),
                bigquery.SchemaField('accuracy', 'FLOAT64'),
                bigquery.SchemaField('roi_pct', 'FLOAT64'),
                bigquery.SchemaField('created_at', 'TIMESTAMP'),
            ],
        }

        for table_name, schema in tables.items():
            table_id = f"{PROJECT_ID}.{dataset_id}.{table_name}"
            table = bigquery.Table(table_id, schema=schema)
            table = client.create_table(table, exists_ok=True)
            print(f"  ✅ Table: {table_name}")

        return True

    except Exception as exc:
        print(f"❌ BigQuery setup failed: {exc}")
        return False


def setup_storage():
    """Create Cloud Storage buckets."""
    try:
        from google.cloud import storage
    except ImportError:
        print("❌ google-cloud-storage not installed")
        print("   Run: pip install google-cloud-storage")
        return False

    try:
        client = storage.Client(project=PROJECT_ID)

        buckets = [
            f"{PROJECT_ID}-raw-data",
            f"{PROJECT_ID}-models",
            f"{PROJECT_ID}-training-data",
        ]

        for bucket_name in buckets:
            bucket = storage.Bucket(client, name=bucket_name)
            bucket.location = "US"
            try:
                client.create_bucket(bucket)
                print(f"✅ Cloud Storage Bucket: {bucket_name}")
            except:
                print(f"  ℹ️  Bucket exists: {bucket_name}")

        return True

    except Exception as exc:
        print(f"❌ Cloud Storage setup failed: {exc}")
        return False


def main():
    """Run all setup steps."""
    print("\n" + "=" * 60)
    print("GCP Infrastructure Setup")
    print("=" * 60)
    print(f"Project ID: {PROJECT_ID}\n")

    print("Setting up BigQuery...")
    bq_ok = setup_bigquery()

    print("\nSetting up Cloud Storage...")
    storage_ok = setup_storage()

    print("\n" + "=" * 60)
    if bq_ok and storage_ok:
        print("✅ GCP Setup Complete!")
        print("=" * 60)
        print("\nNext steps:")
        print("1. Collect data:")
        print("   python -m apps.backend.ml.run_backfill nba 2024 \\")
        print("     --start 2023-10-01 --end 2024-06-30")
        print("\n2. Verify setup:")
        print("   python verify_gcp_setup.py")
        return 0
    else:
        print("❌ GCP Setup Incomplete")
        print("=" * 60)
        return 1


if __name__ == "__main__":
    sys.exit(main())
