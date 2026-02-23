#!/usr/bin/env python3
"""
GCP Client Example for YoureEdge Sports ML Betting System

This module provides convenient wrapper classes for interacting with BigQuery
and Cloud Storage for the sports ML system.

Usage:
    from gcp_client import BigQueryClient, StorageClient

    # BigQuery operations
    bq = BigQueryClient()
    games = bq.query("SELECT * FROM sports_data.games LIMIT 10")

    # Cloud Storage operations
    storage = StorageClient()
    storage.upload_file("local_data.json", "youre-edge-raw-data", "data/raw.json")
"""

import json
from typing import List, Dict, Any, Optional
from datetime import datetime
import logging

from google.cloud import bigquery, storage
from google.cloud.storage import Bucket
from pandas import DataFrame

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class BigQueryClient:
    """Wrapper for BigQuery operations."""

    def __init__(self, project_id: Optional[str] = None):
        """Initialize BigQuery client.

        Args:
            project_id: GCP project ID. If None, uses default project.
        """
        self.client = bigquery.Client(project=project_id)
        self.project_id = self.client.project
        logger.info(f"BigQuery client initialized for project: {self.project_id}")

    def query(
        self,
        query_string: str,
        use_legacy_sql: bool = False,
        dry_run: bool = False,
    ) -> bigquery.QueryJob:
        """Execute a BigQuery SQL query.

        Args:
            query_string: SQL query to execute
            use_legacy_sql: Whether to use legacy SQL syntax
            dry_run: If True, only estimates query cost without executing

        Returns:
            QueryJob object with results
        """
        job_config = bigquery.QueryJobConfig(
            use_legacy_sql=use_legacy_sql,
            dry_run=dry_run,
        )

        query_job = self.client.query(query_string, job_config=job_config)

        if dry_run:
            logger.info(f"Query would process {query_job.total_bytes_billed} bytes")
            return query_job

        logger.info(f"Query job started: {query_job.job_id}")
        query_job.result()  # Wait for job to complete
        logger.info(f"Query completed. Rows: {query_job.total_rows}")

        return query_job

    def query_to_dataframe(self, query_string: str) -> DataFrame:
        """Execute query and return results as pandas DataFrame.

        Args:
            query_string: SQL query to execute

        Returns:
            pandas DataFrame with query results
        """
        query_job = self.query(query_string)
        return query_job.to_dataframe()

    def insert_rows(
        self,
        table_id: str,
        rows: List[Dict[str, Any]],
        skip_invalid_rows: bool = False,
    ) -> bool:
        """Insert rows into a BigQuery table.

        Args:
            table_id: Full table ID (project.dataset.table)
            rows: List of dictionaries to insert
            skip_invalid_rows: If True, skip rows with schema errors

        Returns:
            True if successful, False otherwise
        """
        table = self.client.get_table(table_id)

        errors = self.client.insert_rows_json(
            table,
            rows,
            skip_invalid_rows=skip_invalid_rows,
        )

        if errors:
            logger.error(f"Errors inserting rows: {errors}")
            return False

        logger.info(f"Successfully inserted {len(rows)} rows into {table_id}")
        return True

    def create_table(
        self,
        dataset_id: str,
        table_id: str,
        schema: List[bigquery.SchemaField],
        description: str = "",
    ) -> bigquery.Table:
        """Create a new BigQuery table.

        Args:
            dataset_id: Dataset ID
            table_id: Table ID
            schema: List of SchemaField objects
            description: Table description

        Returns:
            Created Table object
        """
        table_ref = f"{self.project_id}.{dataset_id}.{table_id}"
        table = bigquery.Table(table_ref, schema=schema)
        table.description = description

        try:
            table = self.client.create_table(table)
            logger.info(f"Created table {table_ref}")
            return table
        except Exception as e:
            logger.error(f"Error creating table: {e}")
            raise

    def get_table_schema(self, dataset_id: str, table_id: str) -> List[bigquery.SchemaField]:
        """Get schema of an existing table.

        Args:
            dataset_id: Dataset ID
            table_id: Table ID

        Returns:
            List of SchemaField objects
        """
        table = self.client.get_table(f"{self.project_id}.{dataset_id}.{table_id}")
        return table.schema

    def list_tables(self, dataset_id: str) -> List[str]:
        """List all tables in a dataset.

        Args:
            dataset_id: Dataset ID

        Returns:
            List of table IDs
        """
        tables = self.client.list_tables(dataset_id)
        return [table.table_id for table in tables]

    def get_table_stats(self, dataset_id: str, table_id: str) -> Dict[str, Any]:
        """Get statistics about a table.

        Args:
            dataset_id: Dataset ID
            table_id: Table ID

        Returns:
            Dictionary with table statistics
        """
        table = self.client.get_table(f"{self.project_id}.{dataset_id}.{table_id}")

        return {
            "table_id": table_id,
            "rows": table.num_rows,
            "size_bytes": table.num_bytes,
            "size_mb": table.num_bytes / (1024 * 1024) if table.num_bytes else 0,
            "columns": len(table.schema),
            "created": table.created.isoformat() if table.created else None,
            "modified": table.modified.isoformat() if table.modified else None,
        }


class StorageClient:
    """Wrapper for Cloud Storage operations."""

    def __init__(self, project_id: Optional[str] = None):
        """Initialize Storage client.

        Args:
            project_id: GCP project ID. If None, uses default project.
        """
        self.client = storage.Client(project=project_id)
        self.project_id = self.client.project
        logger.info(f"Storage client initialized for project: {self.project_id}")

    def upload_blob(
        self,
        bucket_name: str,
        source_file_path: str,
        destination_blob_name: str,
        content_type: str = "application/json",
    ) -> bool:
        """Upload a local file to Cloud Storage.

        Args:
            bucket_name: GCS bucket name
            source_file_path: Local file path
            destination_blob_name: Path in GCS bucket
            content_type: MIME type of the file

        Returns:
            True if successful
        """
        try:
            bucket = self.client.bucket(bucket_name)
            blob = bucket.blob(destination_blob_name)
            blob.upload_from_filename(source_file_path, content_type=content_type)

            logger.info(
                f"Uploaded {source_file_path} to gs://{bucket_name}/{destination_blob_name}"
            )
            return True
        except Exception as e:
            logger.error(f"Error uploading file: {e}")
            return False

    def download_blob(
        self,
        bucket_name: str,
        source_blob_name: str,
        destination_file_path: str,
    ) -> bool:
        """Download a file from Cloud Storage.

        Args:
            bucket_name: GCS bucket name
            source_blob_name: Path in GCS bucket
            destination_file_path: Local file path to save to

        Returns:
            True if successful
        """
        try:
            bucket = self.client.bucket(bucket_name)
            blob = bucket.blob(source_blob_name)
            blob.download_to_filename(destination_file_path)

            logger.info(
                f"Downloaded gs://{bucket_name}/{source_blob_name} to {destination_file_path}"
            )
            return True
        except Exception as e:
            logger.error(f"Error downloading file: {e}")
            return False

    def list_blobs(
        self,
        bucket_name: str,
        prefix: str = "",
    ) -> List[str]:
        """List blobs in a bucket.

        Args:
            bucket_name: GCS bucket name
            prefix: Optional prefix to filter results

        Returns:
            List of blob names
        """
        blobs = self.client.list_blobs(bucket_name, prefix=prefix)
        return [blob.name for blob in blobs]

    def upload_json(
        self,
        bucket_name: str,
        data: Dict[str, Any],
        destination_blob_name: str,
    ) -> bool:
        """Upload a Python dictionary as JSON to Cloud Storage.

        Args:
            bucket_name: GCS bucket name
            data: Dictionary to upload as JSON
            destination_blob_name: Path in GCS bucket

        Returns:
            True if successful
        """
        try:
            bucket = self.client.bucket(bucket_name)
            blob = bucket.blob(destination_blob_name)

            json_string = json.dumps(data, default=str)
            blob.upload_from_string(json_string, content_type="application/json")

            logger.info(
                f"Uploaded JSON to gs://{bucket_name}/{destination_blob_name}"
            )
            return True
        except Exception as e:
            logger.error(f"Error uploading JSON: {e}")
            return False

    def download_json(
        self,
        bucket_name: str,
        source_blob_name: str,
    ) -> Optional[Dict[str, Any]]:
        """Download a JSON file from Cloud Storage.

        Args:
            bucket_name: GCS bucket name
            source_blob_name: Path in GCS bucket

        Returns:
            Parsed JSON as dictionary, or None if error
        """
        try:
            bucket = self.client.bucket(bucket_name)
            blob = bucket.blob(source_blob_name)

            json_string = blob.download_as_text()
            data = json.loads(json_string)

            logger.info(
                f"Downloaded JSON from gs://{bucket_name}/{source_blob_name}"
            )
            return data
        except Exception as e:
            logger.error(f"Error downloading JSON: {e}")
            return None

    def get_bucket_stats(self, bucket_name: str) -> Dict[str, Any]:
        """Get statistics about a bucket.

        Args:
            bucket_name: GCS bucket name

        Returns:
            Dictionary with bucket statistics
        """
        bucket = self.client.get_bucket(bucket_name)
        blobs = list(self.client.list_blobs(bucket_name))

        total_size = sum(blob.size for blob in blobs)

        return {
            "bucket_name": bucket_name,
            "location": bucket.location,
            "storage_class": bucket.storage_class,
            "blob_count": len(blobs),
            "total_size_bytes": total_size,
            "total_size_mb": total_size / (1024 * 1024),
            "created": bucket.time_created.isoformat() if bucket.time_created else None,
        }


class SportsMLClient:
    """High-level client for sports ML operations."""

    def __init__(self, project_id: Optional[str] = None):
        """Initialize Sports ML client.

        Args:
            project_id: GCP project ID
        """
        self.bq = BigQueryClient(project_id)
        self.storage = StorageClient(project_id)

    def insert_game(
        self,
        game_id: str,
        sport: str,
        game_date: str,
        home_team: str,
        away_team: str,
        home_team_id: str,
        away_team_id: str,
        status: str = "scheduled",
        **kwargs,
    ) -> bool:
        """Insert a game record into BigQuery.

        Args:
            game_id: Unique game identifier
            sport: Sport type (NFL, NBA, MLB, NHL)
            game_date: Game date in YYYY-MM-DD format
            home_team: Home team name
            away_team: Away team name
            home_team_id: ESPN ID for home team
            away_team_id: ESPN ID for away team
            status: Game status
            **kwargs: Additional fields (home_score, away_score, venue, etc.)

        Returns:
            True if successful
        """
        row = {
            "game_id": game_id,
            "sport": sport,
            "game_date": game_date,
            "home_team": home_team,
            "away_team": away_team,
            "home_team_id": home_team_id,
            "away_team_id": away_team_id,
            "status": status,
            "created_at": datetime.utcnow().isoformat() + "Z",
            "updated_at": datetime.utcnow().isoformat() + "Z",
            **kwargs,
        }

        return self.bq.insert_rows(f"{self.bq.project_id}.sports_data.games", [row])

    def insert_prediction(
        self,
        prediction_id: str,
        game_id: str,
        model_id: str,
        model_version: str,
        prediction_type: str,
        predicted_value: float,
        confidence: float = None,
        **kwargs,
    ) -> bool:
        """Insert a model prediction into BigQuery.

        Args:
            prediction_id: Unique prediction identifier
            game_id: Reference to game
            model_id: ID of model making prediction
            model_version: Version of the model
            prediction_type: Type of prediction (spread, moneyline, over_under)
            predicted_value: Predicted value
            confidence: Confidence score 0-1
            **kwargs: Additional fields

        Returns:
            True if successful
        """
        row = {
            "prediction_id": prediction_id,
            "game_id": game_id,
            "model_id": model_id,
            "model_version": model_version,
            "prediction_type": prediction_type,
            "predicted_value": predicted_value,
            "confidence": confidence,
            "created_at": datetime.utcnow().isoformat() + "Z",
            **kwargs,
        }

        return self.bq.insert_rows(
            f"{self.bq.project_id}.sports_data.predictions", [row]
        )

    def get_recent_games(self, sport: str, limit: int = 10) -> DataFrame:
        """Get recent games for a sport.

        Args:
            sport: Sport type (NFL, NBA, MLB, NHL)
            limit: Number of recent games to return

        Returns:
            pandas DataFrame with game records
        """
        query = f"""
            SELECT *
            FROM sports_data.games
            WHERE sport = '{sport}'
            ORDER BY game_date DESC
            LIMIT {limit}
        """
        return self.bq.query_to_dataframe(query)

    def get_model_performance(
        self,
        model_id: str,
        limit: int = 100,
    ) -> DataFrame:
        """Get recent predictions and performance for a model.

        Args:
            model_id: ID of the model
            limit: Number of recent predictions

        Returns:
            pandas DataFrame with predictions
        """
        query = f"""
            SELECT
                prediction_id,
                game_id,
                predicted_value,
                actual_value,
                is_correct,
                confidence,
                created_at
            FROM sports_data.predictions
            WHERE model_id = '{model_id}'
            ORDER BY created_at DESC
            LIMIT {limit}
        """
        return self.bq.query_to_dataframe(query)


def example_usage():
    """Example usage of the GCP clients."""
    print("GCP Client Example Usage\n")

    # Initialize client
    client = SportsMLClient()

    # Example: Insert a game
    print("1. Inserting a game record...")
    success = client.insert_game(
        game_id="nfl_2024_001",
        sport="NFL",
        game_date="2024-09-15",
        home_team="Kansas City Chiefs",
        away_team="Cincinnati Bengals",
        home_team_id="12",
        away_team_id="5",
        status="scheduled",
        venue="Arrowhead Stadium",
    )
    print(f"   Result: {'Success' if success else 'Failed'}\n")

    # Example: Get recent games
    print("2. Fetching recent NFL games...")
    try:
        games = client.get_recent_games("NFL", limit=5)
        print(f"   Found {len(games)} games")
        if len(games) > 0:
            print(f"   Columns: {list(games.columns)}\n")
    except Exception as e:
        print(f"   No games found or error: {e}\n")

    # Example: Check BigQuery tables
    print("3. Checking BigQuery tables...")
    tables = client.bq.list_tables("sports_data")
    print(f"   Tables in sports_data: {tables}\n")

    # Example: Check Storage buckets
    print("4. Checking Cloud Storage buckets...")
    for bucket in [
        "youre-edge-raw-data",
        "youre-edge-models",
        "youre-edge-training-data",
    ]:
        try:
            stats = client.storage.get_bucket_stats(bucket)
            print(f"   {bucket}: {stats['blob_count']} blobs\n")
        except Exception as e:
            print(f"   {bucket}: Not accessible\n")


if __name__ == "__main__":
    example_usage()
