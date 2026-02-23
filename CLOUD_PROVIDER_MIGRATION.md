# Cloud Provider Abstraction - Migration Guide

## Overview

Your backend is now provider-agnostic! You can easily swap between Google Cloud Platform (GCP), Amazon Web Services (AWS), Microsoft Azure, or any custom cloud solution without changing your application code.

## Architecture

### Abstract Interfaces

Three abstract base classes define the cloud provider contract:

#### 1. **AnalyticsStorageClient** (`ml/cloud_provider.py`)
For data warehouse operations (BigQuery, Athena, Redshift, Snowflake, etc.):
- `query_to_dataframe(query, job_config)` - Execute SQL queries
- `insert_rows(table_id, rows)` - Insert data
- `get_table_schema(table_id)` - Get table schema
- `table_exists(table_id)` - Check table existence

#### 2. **ObjectStorageClient** (`ml/cloud_provider.py`)
For blob/object storage (Cloud Storage, S3, Azure Blob, etc.):
- `upload_blob(bucket, source_file, destination)` - Upload files
- `download_blob(bucket, source, destination)` - Download files
- `list_blobs(bucket, prefix)` - List objects
- `upload_json(bucket, data, destination)` - Store JSON
- `download_json(bucket, source)` - Retrieve JSON

#### 3. **CloudProvider** (`ml/cloud_provider.py`)
Top-level provider interface:
- `provider_id` - Unique identifier (e.g., "gcp", "aws")
- `analytics_client` - Get analytics client
- `storage_client` - Get storage client
- `health_check()` - Verify service availability

## Implementations

### GCP (Production Ready)

**Files:**
- `ml/gcp_client.py` - BigQueryClient, StorageClient, GCPProvider
- `ml/cloud_provider.py` - Abstract interfaces

**Usage:**
```python
from ml.gcp_client import GCPProvider

# Auto-detect project from GOOGLE_CLOUD_PROJECT env var
provider = GCPProvider()

# Or specify explicitly
provider = GCPProvider(project_id="my-gcp-project")

# Access clients
provider.analytics_client.query_to_dataframe(query)
provider.storage_client.upload_blob(bucket, src, dst)

# Health check
status = provider.health_check()
```

### AWS (Example Implementation)

**File:** `ml/aws_client_example.py`

Complete implementation showing how to use Athena (BigQuery equivalent) and S3 (Cloud Storage equivalent).

**Usage:**
```python
from ml.aws_client_example import AWSProvider

# Specify region and database
provider = AWSProvider(region="us-east-1", database="sports_data")

# Same interface as GCP!
provider.analytics_client.query_to_dataframe(query)
provider.storage_client.upload_blob(bucket, src, dst)

# Health check
status = provider.health_check()
```

## Model Server Integration

The `BettingModelServer` now accepts any cloud provider:

```python
from ml.model_server import BettingModelServer
from ml.gcp_client import GCPProvider

# Initialize with GCP (default)
server = BettingModelServer(
    models_dir="/tmp/models",
    project_id="my-gcp-project"
)

# Or with AWS
from ml.aws_client_example import AWSProvider
aws_provider = AWSProvider(region="us-east-1")
server = BettingModelServer(
    models_dir="/tmp/models",
    cloud_provider=aws_provider
)

# Both work identically!
predictions = server.predict_game(
    sport="nba",
    game_id="12345",
    features=features,
    markets=["spread", "total"]
)
```

## Comprehensive Logging

All cloud operations now include detailed logging:

### BigQuery Operations
```
INFO: "BigQuery client initialized" {'project_id': 'my-project', 'dataset_id': 'sports_data'}
DEBUG: "Executing BigQuery query" {'query_length': 250}
DEBUG: "Query executed successfully" {'rows_returned': 42}
ERROR: "BigQuery insert failed" {'error': '...', 'error_type': 'NotFound', 'row_count': 10}
```

### Cloud Storage Operations
```
INFO: "Uploading file to Cloud Storage" {'bucket': 'models', 'file_size': 5242880}
INFO: "File uploaded successfully" {'bucket_name': 'models', 'blob_name': 'nba_spread_v1.pkl'}
ERROR: "Cloud Storage upload failed" {'bucket': 'invalid', 'error': '...'}
```

### Health Checks
```
INFO: "Performing GCP health check..."
DEBUG: "Checking BigQuery connectivity..."
INFO: "BigQuery health check passed"
DEBUG: "Checking Cloud Storage connectivity..."
INFO: "Cloud Storage health check passed"
INFO: "GCP health check completed" {'status': {'analytics': True, 'storage': True}}
```

## Creating a New Provider

Here's how to implement your own cloud provider (e.g., Azure, local storage):

```python
from ml.cloud_provider import (
    AnalyticsStorageClient,
    CloudProvider,
    ObjectStorageClient,
)

# 1. Implement analytics client
class MyAnalyticsClient(AnalyticsStorageClient):
    def query_to_dataframe(self, query, job_config=None):
        # Your implementation
        pass

    def insert_rows(self, table_id, rows):
        # Your implementation
        pass

    def get_table_schema(self, table_id):
        # Your implementation
        pass

    def table_exists(self, table_id):
        # Your implementation
        pass

# 2. Implement storage client
class MyStorageClient(ObjectStorageClient):
    def upload_blob(self, bucket_name, source_file, destination):
        # Your implementation
        pass

    def download_blob(self, bucket_name, source, destination):
        # Your implementation
        pass

    def list_blobs(self, bucket_name, prefix=""):
        # Your implementation
        pass

    def upload_json(self, bucket_name, data, destination):
        # Your implementation
        pass

    def download_json(self, bucket_name, source):
        # Your implementation
        pass

# 3. Implement cloud provider
class MyCloudProvider(CloudProvider):
    def __init__(self, **config):
        self._analytics_client = MyAnalyticsClient(**config)
        self._storage_client = MyStorageClient(**config)

    @property
    def provider_id(self):
        return "my-provider"

    @property
    def analytics_client(self):
        return self._analytics_client

    @property
    def storage_client(self):
        return self._storage_client

    def health_check(self):
        # Check service availability
        return {"analytics": True, "storage": True}

# 4. Use it!
provider = MyCloudProvider()
server = BettingModelServer(models_dir="/tmp/models", cloud_provider=provider)
```

## Migration from GCP-only Code

If you have code directly using GCP clients:

### Before (GCP-specific)
```python
from ml.gcp_client import BigQueryClient, StorageClient

bq = BigQueryClient("my-project")
bq.query_to_dataframe(query)
```

### After (Provider-agnostic)
```python
from ml.gcp_client import GCPProvider

provider = GCPProvider("my-project")
provider.analytics_client.query_to_dataframe(query)
```

The old GCP classes still work for backward compatibility, but new code should use the abstract interfaces.

## Environment Variables

### GCP
```bash
export GOOGLE_CLOUD_PROJECT="my-gcp-project"
export GOOGLE_APPLICATION_CREDENTIALS="/path/to/credentials.json"
export MODELS_DIR="/tmp/models"
export LOG_LEVEL="INFO"
```

### AWS
```bash
export AWS_REGION="us-east-1"
export AWS_ACCESS_KEY_ID="..."
export AWS_SECRET_ACCESS_KEY="..."
export ATHENA_DATABASE="sports_data"
export MODELS_DIR="/tmp/models"
export LOG_LEVEL="INFO"
```

## Files Changed

### New Files
- `ml/cloud_provider.py` - Abstract interfaces
- `ml/aws_client_example.py` - AWS provider example

### Modified Files
- `ml/gcp_client.py` - Refactored to implement abstractions, added logging
- `ml/model_server.py` - Updated to accept CloudProvider, added logging
- `server.py` - Enhanced initialization logging (no changes needed for new provider support)

## Key Improvements

✅ **Provider-agnostic** - Add support for any cloud provider
✅ **Type-safe** - Abstract interfaces ensure consistency
✅ **Comprehensive logging** - Track all cloud operations
✅ **Graceful degradation** - Works without cloud provider (local only)
✅ **Backward compatible** - Old GCP-specific code still works
✅ **Zero breaking changes** - Existing deployments work as-is

## Testing Your New Provider

```python
from ml.model_server import BettingModelServer

# Initialize with new provider
server = BettingModelServer(
    models_dir="/tmp/models",
    cloud_provider=your_provider_instance
)

# Check health
health = server.health_check()
print(health)
# Output:
# {
#   'models_loaded': 5,
#   'models': ['nba_spread', 'nba_total', ...],
#   'cloud_provider': {
#     'available': True,
#     'provider_id': 'my-provider',
#     'status': {'analytics': True, 'storage': True}
#   }
# }

# Use normally
predictions = server.predict_game(
    sport="nba",
    game_id="12345",
    features={...},
    markets=["spread", "total"]
)
```

## Support for Multiple Providers

You can even use different providers for different purposes:

```python
from ml.gcp_client import GCPProvider
from ml.aws_client_example import AWSProvider

# Use GCP for primary, AWS as fallback
gcp = GCPProvider("my-project")
aws = AWSProvider(region="us-east-1")

# Use GCP for main server
main_server = BettingModelServer(models_dir="/tmp/models", cloud_provider=gcp)

# Use AWS for backup/archive
backup_server = BettingModelServer(models_dir="/tmp/models", cloud_provider=aws)
```

---

## Summary

Your backend is now ready to move away from GCP or use any cloud provider seamlessly. The abstraction layer provides:

- 📦 Clean interfaces for analytics and storage
- 🔌 Pluggable provider implementations
- 📊 Comprehensive operational logging
- 🛡️ Type safety with abstract base classes
- 🔄 Backward compatibility with existing code
- 🚀 Zero application changes needed to swap providers
