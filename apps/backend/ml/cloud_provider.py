"""Abstract base class for cloud providers."""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class AnalyticsStorageClient(ABC):
    """Abstract base for analytics/data warehouse (BigQuery, Redshift, Snowflake, etc.)."""

    @abstractmethod
    def query_to_dataframe(self, query: str, job_config: Optional[Any] = None):
        """
        Execute query and return as pandas DataFrame.

        Args:
            query: SQL query string
            job_config: Optional job configuration

        Returns:
            pandas DataFrame with results

        Raises:
            RuntimeError: If query fails
        """
        pass

    @abstractmethod
    def insert_rows(self, table_id: str, rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Insert rows into analytics table.

        Args:
            table_id: Table name (e.g., 'games', 'predictions')
            rows: List of row dictionaries

        Returns:
            List of insert errors (empty if successful)

        Raises:
            RuntimeError: If insert fails
        """
        pass

    @abstractmethod
    def get_table_schema(self, table_id: str) -> List[Dict[str, Any]]:
        """
        Get table schema.

        Args:
            table_id: Table name

        Returns:
            List of field dictionaries with type information

        Raises:
            RuntimeError: If table not found
        """
        pass

    @abstractmethod
    def table_exists(self, table_id: str) -> bool:
        """Check if table exists."""
        pass


class ObjectStorageClient(ABC):
    """Abstract base for object/blob storage (Cloud Storage, S3, Azure Blob, etc.)."""

    @abstractmethod
    def upload_blob(
        self,
        bucket_name: str,
        source_file_name: str,
        destination_blob_name: str,
    ) -> None:
        """
        Upload file to bucket.

        Args:
            bucket_name: Bucket name
            source_file_name: Local file path
            destination_blob_name: Remote blob path

        Raises:
            RuntimeError: If upload fails
        """
        pass

    @abstractmethod
    def download_blob(
        self,
        bucket_name: str,
        source_blob_name: str,
        destination_file_name: str,
    ) -> None:
        """
        Download file from bucket.

        Args:
            bucket_name: Bucket name
            source_blob_name: Remote blob path
            destination_file_name: Local file path

        Raises:
            RuntimeError: If download fails
        """
        pass

    @abstractmethod
    def list_blobs(self, bucket_name: str, prefix: str = "") -> List[str]:
        """
        List blob names in bucket with optional prefix filter.

        Args:
            bucket_name: Bucket name
            prefix: Optional prefix to filter results

        Returns:
            List of blob names

        Raises:
            RuntimeError: If list fails
        """
        pass

    @abstractmethod
    def upload_json(
        self,
        bucket_name: str,
        data: Dict[str, Any],
        destination_blob_name: str,
    ) -> None:
        """
        Upload JSON data to bucket.

        Args:
            bucket_name: Bucket name
            data: Dictionary to store as JSON
            destination_blob_name: Remote blob path

        Raises:
            RuntimeError: If upload fails
        """
        pass

    @abstractmethod
    def download_json(
        self,
        bucket_name: str,
        source_blob_name: str,
    ) -> Dict[str, Any]:
        """
        Download JSON data from bucket.

        Args:
            bucket_name: Bucket name
            source_blob_name: Remote blob path

        Returns:
            Dictionary from JSON

        Raises:
            RuntimeError: If download or parse fails
        """
        pass


class CloudProvider(ABC):
    """Abstract base class for cloud providers."""

    @property
    @abstractmethod
    def provider_id(self) -> str:
        """Unique identifier for this provider (e.g., 'gcp', 'aws', 'azure')."""
        pass

    @property
    @abstractmethod
    def analytics_client(self) -> AnalyticsStorageClient:
        """Get analytics/data warehouse client."""
        pass

    @property
    @abstractmethod
    def storage_client(self) -> ObjectStorageClient:
        """Get object storage client."""
        pass

    @abstractmethod
    def health_check(self) -> Dict[str, bool]:
        """
        Check if cloud services are accessible.

        Returns:
            Dict with 'analytics' and 'storage' boolean status keys

        Raises:
            RuntimeError: If health check fails
        """
        pass
