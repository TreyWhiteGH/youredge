"""Google Cloud Platform provider implementation."""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from config import config

logger = logging.getLogger(__name__)

from .cloud_provider import (
    AnalyticsStorageClient,
    CloudProvider,
    ObjectStorageClient,
)


def _setup_gcp_credentials():
    """Set up GCP credentials from config or environment variables.

    Priority order:
    1. GOOGLE_APPLICATION_CREDENTIALS environment variable (if already set)
    2. gcp.credentials_path from config file
    3. GOOGLE_APPLICATION_CREDENTIALS from secrets.env (already loaded by config)

    This allows for flexibility:
    - Production: Use GOOGLE_APPLICATION_CREDENTIALS env var from deployment
    - Development: Use gcp.credentials_path in dev.toml pointing to local ~/gcp-key.json
    """
    # If already set in environment, use it (highest priority)
    if os.environ.get("GOOGLE_APPLICATION_CREDENTIALS"):
        logger.debug("Using GOOGLE_APPLICATION_CREDENTIALS from environment")
        return

    # Check if config specifies a credentials path
    creds_path = config.get("gcp.credentials_path", "")
    if creds_path:
        creds_path = os.path.expanduser(creds_path)  # Expand ~ to home directory
        if os.path.exists(creds_path):
            os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = creds_path
            logger.info(f"Set GOOGLE_APPLICATION_CREDENTIALS from config: {creds_path}")
        else:
            logger.warning(f"GCP credentials file not found at configured path: {creds_path}")
    else:
        logger.debug("No GCP credentials path configured (GOOGLE_APPLICATION_CREDENTIALS not set)")


class BigQueryClient(AnalyticsStorageClient):
    """BigQuery client for sports data analytics."""

    def __init__(self, project_id: Optional[str] = None):
        """
        Initialize BigQuery client.

        Args:
            project_id: GCP project ID (uses GOOGLE_CLOUD_PROJECT env var if not provided)

        Raises:
            ImportError: If google-cloud-bigquery not installed
            ValueError: If project_id not provided and not in environment
        """
        logger.info("Initializing BigQuery client...")

        # Set up credentials from config or environment variables
        _setup_gcp_credentials()

        try:
            from google.cloud import bigquery
        except ImportError as exc:
            logger.error("google-cloud-bigquery not installed")
            raise ImportError(
                "google-cloud-bigquery not installed. Run: pip install google-cloud-bigquery"
            ) from exc

        self.project_id = project_id or config.get_secret("GOOGLE_CLOUD_PROJECT")
        if not self.project_id:
            logger.error("project_id not provided and GOOGLE_CLOUD_PROJECT not set")
            raise ValueError(
                "project_id required or set GOOGLE_CLOUD_PROJECT env var"
            )

        self.client = bigquery.Client(project=self.project_id)
        self.dataset_id = config.get("gcp.dataset_id", "sports_data")

        logger.info(
            "BigQuery client initialized",
            extra={
                "project_id": self.project_id,
                "dataset_id": self.dataset_id,
            },
        )

    def query_to_dataframe(self, query: str, job_config: Optional[Any] = None):
        """Execute query and return as pandas DataFrame."""
        try:
            logger.debug(
                "Executing BigQuery query",
                extra={
                    "project_id": self.project_id,
                    "query_length": len(query),
                },
            )
            results = self.client.query(query, job_config=job_config)
            df = results.to_dataframe()
            logger.debug(
                "Query executed successfully",
                extra={
                    "project_id": self.project_id,
                    "rows_returned": len(df),
                },
            )
            return df
        except Exception as exc:
            logger.error(
                "BigQuery query failed",
                extra={
                    "project_id": self.project_id,
                    "error": str(exc),
                    "error_type": type(exc).__name__,
                },
            )
            raise

    def insert_rows(self, table_id: str, rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Insert rows into BigQuery table."""
        try:
            logger.debug(
                "Inserting rows to BigQuery",
                extra={
                    "project_id": self.project_id,
                    "dataset_id": self.dataset_id,
                    "table_id": table_id,
                    "row_count": len(rows),
                },
            )
            table = self.client.get_table(f"{self.dataset_id}.{table_id}")
            errors = self.client.insert_rows_json(table, rows)

            if errors:
                logger.error(
                    "BigQuery insert errors",
                    extra={
                        "project_id": self.project_id,
                        "table_id": table_id,
                        "error_count": len(errors),
                        "errors": str(errors[:3]),  # log first 3 errors
                    },
                )
            else:
                logger.debug(
                    "Rows inserted successfully",
                    extra={
                        "table_id": table_id,
                        "row_count": len(rows),
                    },
                )

            return errors
        except Exception as exc:
            logger.error(
                "BigQuery insert failed",
                extra={
                    "project_id": self.project_id,
                    "table_id": table_id,
                    "row_count": len(rows),
                    "error": str(exc),
                    "error_type": type(exc).__name__,
                },
            )
            raise

    def get_table_schema(self, table_id: str) -> List[Dict[str, Any]]:
        """Get table schema."""
        logger.debug(
            "Fetching table schema",
            extra={
                "project_id": self.project_id,
                "dataset_id": self.dataset_id,
                "table_id": table_id,
            },
        )
        table = self.client.get_table(f"{self.dataset_id}.{table_id}")
        schema = [field.to_api_repr() for field in table.schema]
        logger.debug(
            "Table schema retrieved",
            extra={
                "table_id": table_id,
                "field_count": len(schema),
            },
        )
        return schema

    def table_exists(self, table_id: str) -> bool:
        """Check if table exists."""
        try:
            logger.debug(
                "Checking table existence",
                extra={
                    "table_id": table_id,
                },
            )
            self.client.get_table(f"{self.dataset_id}.{table_id}")
            logger.debug("Table exists", extra={"table_id": table_id})
            return True
        except Exception as exc:
            logger.debug(
                "Table does not exist",
                extra={
                    "table_id": table_id,
                    "error": str(exc),
                },
            )
            return False


class StorageClient(ObjectStorageClient):
    """Google Cloud Storage client."""

    def __init__(self, project_id: Optional[str] = None):
        """
        Initialize Storage client.

        Args:
            project_id: GCP project ID (uses GOOGLE_CLOUD_PROJECT env var if not provided)

        Raises:
            ImportError: If google-cloud-storage not installed
            ValueError: If project_id not provided and not in environment
        """
        logger.info("Initializing Cloud Storage client...")

        # Set up credentials from config or environment variables
        _setup_gcp_credentials()

        try:
            from google.cloud import storage
        except ImportError as exc:
            logger.error("google-cloud-storage not installed")
            raise ImportError(
                "google-cloud-storage not installed. Run: pip install google-cloud-storage"
            ) from exc

        self.project_id = project_id or config.get_secret("GOOGLE_CLOUD_PROJECT")
        if not self.project_id:
            logger.error("project_id not provided and GOOGLE_CLOUD_PROJECT not set")
            raise ValueError(
                "project_id required or set GOOGLE_CLOUD_PROJECT env var"
            )

        self.client = storage.Client(project=self.project_id)
        logger.info(
            "Cloud Storage client initialized",
            extra={"project_id": self.project_id},
        )

    def upload_blob(
        self,
        bucket_name: str,
        source_file_name: str,
        destination_blob_name: str,
    ) -> None:
        """Upload file to bucket."""
        try:
            logger.info(
                "Uploading file to Cloud Storage",
                extra={
                    "project_id": self.project_id,
                    "bucket_name": bucket_name,
                    "source_file": source_file_name,
                    "destination_blob": destination_blob_name,
                    "file_size": Path(source_file_name).stat().st_size if Path(source_file_name).exists() else 0,
                },
            )
            bucket = self.client.bucket(bucket_name)
            blob = bucket.blob(destination_blob_name)
            blob.upload_from_filename(source_file_name)
            logger.info(
                "File uploaded successfully",
                extra={
                    "bucket_name": bucket_name,
                    "blob_name": destination_blob_name,
                },
            )
        except Exception as exc:
            logger.error(
                "Cloud Storage upload failed",
                extra={
                    "project_id": self.project_id,
                    "bucket_name": bucket_name,
                    "destination_blob": destination_blob_name,
                    "error": str(exc),
                    "error_type": type(exc).__name__,
                },
            )
            raise

    def download_blob(
        self,
        bucket_name: str,
        source_blob_name: str,
        destination_file_name: str,
    ) -> None:
        """Download file from bucket."""
        try:
            logger.info(
                "Downloading file from Cloud Storage",
                extra={
                    "project_id": self.project_id,
                    "bucket_name": bucket_name,
                    "source_blob": source_blob_name,
                    "destination_file": destination_file_name,
                },
            )
            bucket = self.client.bucket(bucket_name)
            blob = bucket.blob(source_blob_name)
            blob.download_to_filename(destination_file_name)
            logger.info(
                "File downloaded successfully",
                extra={
                    "bucket_name": bucket_name,
                    "blob_name": source_blob_name,
                    "destination": destination_file_name,
                },
            )
        except Exception as exc:
            logger.error(
                "Cloud Storage download failed",
                extra={
                    "project_id": self.project_id,
                    "bucket_name": bucket_name,
                    "source_blob": source_blob_name,
                    "error": str(exc),
                    "error_type": type(exc).__name__,
                },
            )
            raise

    def list_blobs(self, bucket_name: str, prefix: str = "") -> List[str]:
        """List blobs in bucket."""
        logger.debug(
            "Listing Cloud Storage blobs",
            extra={
                "bucket_name": bucket_name,
                "prefix": prefix,
            },
        )
        bucket = self.client.bucket(bucket_name)
        blobs = self.client.list_blobs(bucket, prefix=prefix)
        blob_names = [blob.name for blob in blobs]
        logger.debug(
            "Blobs listed",
            extra={
                "bucket_name": bucket_name,
                "blob_count": len(blob_names),
            },
        )
        return blob_names

    def upload_json(
        self,
        bucket_name: str,
        data: Dict[str, Any],
        destination_blob_name: str,
    ) -> None:
        """Upload JSON data to bucket."""
        try:
            logger.debug(
                "Uploading JSON to Cloud Storage",
                extra={
                    "bucket_name": bucket_name,
                    "destination_blob": destination_blob_name,
                    "data_size": len(json.dumps(data)),
                },
            )
            bucket = self.client.bucket(bucket_name)
            blob = bucket.blob(destination_blob_name)
            blob.upload_from_string(
                json.dumps(data),
                content_type="application/json",
            )
            logger.debug(
                "JSON uploaded successfully",
                extra={
                    "bucket_name": bucket_name,
                    "blob_name": destination_blob_name,
                },
            )
        except Exception as exc:
            logger.error(
                "Cloud Storage JSON upload failed",
                extra={
                    "bucket_name": bucket_name,
                    "destination_blob": destination_blob_name,
                    "error": str(exc),
                    "error_type": type(exc).__name__,
                },
            )
            raise

    def download_json(
        self,
        bucket_name: str,
        source_blob_name: str,
    ) -> Dict[str, Any]:
        """Download JSON data from bucket."""
        try:
            logger.debug(
                "Downloading JSON from Cloud Storage",
                extra={
                    "bucket_name": bucket_name,
                    "source_blob": source_blob_name,
                },
            )
            bucket = self.client.bucket(bucket_name)
            blob = bucket.blob(source_blob_name)
            data = json.loads(blob.download_as_string())
            logger.debug(
                "JSON downloaded successfully",
                extra={
                    "bucket_name": bucket_name,
                    "blob_name": source_blob_name,
                },
            )
            return data
        except Exception as exc:
            logger.error(
                "Cloud Storage JSON download failed",
                extra={
                    "bucket_name": bucket_name,
                    "source_blob": source_blob_name,
                    "error": str(exc),
                    "error_type": type(exc).__name__,
                },
            )
            raise


class GCPProvider(CloudProvider):
    """Google Cloud Platform cloud provider implementation."""

    def __init__(self, project_id: Optional[str] = None):
        """
        Initialize GCP provider.

        Args:
            project_id: GCP project ID (uses GOOGLE_CLOUD_PROJECT env var if not provided)

        Raises:
            ImportError: If GCP libraries not installed
            ValueError: If project_id not provided and not in environment
        """
        logger.info("Initializing GCPProvider...")
        self.project_id = project_id or os.environ.get("GOOGLE_CLOUD_PROJECT")
        if not self.project_id:
            logger.error("GCP project_id not provided")
            raise ValueError(
                "project_id required or set GOOGLE_CLOUD_PROJECT env var"
            )

        self._analytics_client = BigQueryClient(self.project_id)
        self._storage_client = StorageClient(self.project_id)

        logger.info(
            "GCPProvider initialized",
            extra={"project_id": self.project_id},
        )

    @property
    def provider_id(self) -> str:
        """Return provider identifier."""
        return "gcp"

    @property
    def analytics_client(self) -> AnalyticsStorageClient:
        """Get analytics/data warehouse client."""
        return self._analytics_client

    @property
    def storage_client(self) -> ObjectStorageClient:
        """Get object storage client."""
        return self._storage_client

    def health_check(self) -> Dict[str, bool]:
        """Check if GCP services are accessible."""
        logger.info("Performing GCP health check...")
        status = {
            "analytics": False,
            "storage": False,
        }

        try:
            logger.debug("Checking BigQuery connectivity...")
            self._analytics_client.client.list_datasets(max_results=1)
            status["analytics"] = True
            logger.info("BigQuery health check passed")
        except Exception as exc:
            logger.error(
                "BigQuery health check failed",
                extra={
                    "error": str(exc),
                    "error_type": type(exc).__name__,
                },
            )

        try:
            logger.debug("Checking Cloud Storage connectivity...")
            self._storage_client.client.list_buckets(max_results=1)
            status["storage"] = True
            logger.info("Cloud Storage health check passed")
        except Exception as exc:
            logger.error(
                "Cloud Storage health check failed",
                extra={
                    "error": str(exc),
                    "error_type": type(exc).__name__,
                },
            )

        logger.info(
            "GCP health check completed",
            extra={"status": status},
        )
        return status


class SportsMLClient:
    """High-level client for sports ML operations (backward compatible)."""

    def __init__(self, project_id: Optional[str] = None):
        """Initialize client with BigQuery and Storage."""
        logger.info("Initializing SportsMLClient...")
        self.project_id = project_id or os.environ.get("GOOGLE_CLOUD_PROJECT")
        self.bq = BigQueryClient(self.project_id)
        self.storage = StorageClient(self.project_id)
        logger.info(
            "SportsMLClient initialized",
            extra={"project_id": self.project_id},
        )

    def insert_game(self, game_id: str, sport: str, game_date: str,
                   home_team_id: str, away_team_id: str,
                   **kwargs) -> List[Dict]:
        """
        Insert game record.

        Args:
            game_id: Unique game ID
            sport: Sport ID (e.g., 'nba')
            game_date: Date (YYYY-MM-DD)
            home_team_id: Home team ID
            away_team_id: Away team ID
            **kwargs: Additional fields (home_score, away_score, status, etc.)

        Returns:
            Insert errors (empty if successful)
        """
        row = {
            'game_id': game_id,
            'sport': sport,
            'game_date': game_date,
            'home_team_id': home_team_id,
            'away_team_id': away_team_id,
            **kwargs
        }
        return self.bq.insert_rows('games', [row])

    def insert_game_events(self, game_id: str, events: List[Dict]) -> List[Dict]:
        """Insert play-by-play events."""
        for event in events:
            event['game_id'] = game_id
        return self.bq.insert_rows('game_events', events)

    def insert_prediction(self, game_id: str, sport: str, market: str,
                         model_version: str, selection: str,
                         confidence: float, edge: float, **kwargs) -> List[Dict]:
        """
        Insert model prediction.

        Args:
            game_id: Game ID
            sport: Sport ID
            market: Market type ('spread', 'moneyline', 'total')
            model_version: Model version string
            selection: Predicted selection
            confidence: Confidence score (0-1)
            edge: Expected value (EV)
            **kwargs: Additional fields

        Returns:
            Insert errors
        """
        row = {
            'game_id': game_id,
            'sport': sport,
            'market': market,
            'model_version': model_version,
            'selection': selection,
            'confidence': confidence,
            'edge': edge,
            **kwargs
        }
        return self.bq.insert_rows('predictions', [row])

    def get_recent_games(self, sport: str, limit: int = 10) -> List[Dict]:
        """Get recent games for sport."""
        query = f"""
            SELECT * FROM `{self.project_id}.sports_data.games`
            WHERE sport = '{sport}'
            ORDER BY game_date DESC
            LIMIT {limit}
        """
        df = self.bq.query_to_dataframe(query)
        return df.to_dict('records')

    def get_game_events(self, game_id: str) -> List[Dict]:
        """Get play-by-play events for game."""
        query = f"""
            SELECT * FROM `{self.project_id}.sports_data.game_events`
            WHERE game_id = '{game_id}'
            ORDER BY clock_seconds
        """
        df = self.bq.query_to_dataframe(query)
        return df.to_dict('records')

    def store_model(self, model_name: str, model_bytes: bytes,
                   metadata: Dict) -> None:
        """
        Store trained model in Cloud Storage.

        Args:
            model_name: Model filename (e.g., 'nba_spread_v1.pkl')
            model_bytes: Model file bytes
            metadata: Model metadata dict
        """
        # Store model
        bucket = self.project_id + "-models"
        self.storage.upload_blob(
            bucket,
            model_bytes,
            f"models/{model_name}"
        )

        # Store metadata
        self.storage.upload_json(
            bucket,
            metadata,
            f"metadata/{model_name.replace('.pkl', '.json')}"
        )

    def load_model(self, model_name: str):
        """Load trained model from Cloud Storage."""
        import pickle
        bucket = self.project_id + "-models"

        # This is a placeholder - actual implementation would download
        # the pickle file and deserialize
        logger.info(f"Loading model {model_name} from {bucket}")
        # Implementation depends on model storage approach
        pass

    def health_check(self) -> Dict[str, bool]:
        """Check if GCP services are accessible."""
        logger.info("Performing SportsMLClient health check...")
        status = {
            "bigquery": False,
            "storage": False,
        }

        try:
            logger.debug("Checking BigQuery connectivity...")
            self.bq.client.list_datasets(max_results=1)
            status["bigquery"] = True
            logger.info("BigQuery health check passed")
        except Exception as exc:
            logger.error(
                "BigQuery health check failed",
                extra={
                    "error": str(exc),
                    "error_type": type(exc).__name__,
                },
            )

        try:
            logger.debug("Checking Cloud Storage connectivity...")
            self.storage.client.list_buckets(max_results=1)
            status["storage"] = True
            logger.info("Cloud Storage health check passed")
        except Exception as exc:
            logger.error(
                "Cloud Storage health check failed",
                extra={
                    "error": str(exc),
                    "error_type": type(exc).__name__,
                },
            )

        logger.info(
            "SportsMLClient health check completed",
            extra={"status": status},
        )
        return status
