"""
S3-compatible storage service for file upload and management.

Features:
- AWS S3 and S3-compatible storage (MinIO, LocalStack)
- Local filesystem fallback
- Automatic retry with exponential backoff
- Health checks for monitoring
- Automatic bucket creation on startup
"""

import asyncio
import logging
import mimetypes
from collections.abc import Callable
from datetime import UTC, datetime
from functools import wraps
from io import BytesIO
from pathlib import Path
from typing import Any, BinaryIO, TypeVar
from uuid import UUID

import aioboto3
from botocore.config import Config
from botocore.exceptions import ClientError, NoCredentialsError

from airbeeps.config import settings

logger = logging.getLogger(__name__)

T = TypeVar("T")


def with_retry(
    max_attempts: int | None = None,
    backoff_factor: float | None = None,
    retryable_errors: tuple[str, ...] = (
        "ServiceUnavailable",
        "InternalError",
        "RequestTimeout",
        "ThrottlingException",
        "SlowDown",
    ),
):
    """
    Decorator for S3 operations with exponential backoff retry.

    Args:
        max_attempts: Maximum retry attempts (uses settings.S3_RETRY_MAX_ATTEMPTS if None)
        backoff_factor: Backoff multiplier (uses settings.S3_RETRY_BACKOFF_FACTOR if None)
        retryable_errors: S3 error codes that should trigger retry
    """

    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> T:
            attempts = max_attempts or settings.S3_RETRY_MAX_ATTEMPTS
            backoff = backoff_factor or settings.S3_RETRY_BACKOFF_FACTOR

            last_exception = None
            for attempt in range(attempts):
                try:
                    return await func(*args, **kwargs)
                except ClientError as e:
                    error_code = e.response.get("Error", {}).get("Code", "")
                    if error_code not in retryable_errors:
                        raise

                    last_exception = e
                    if attempt < attempts - 1:
                        wait_time = backoff * (2**attempt)
                        logger.warning(
                            f"S3 operation failed with {error_code}, "
                            f"retrying in {wait_time:.1f}s (attempt {attempt + 1}/{attempts})"
                        )
                        await asyncio.sleep(wait_time)
                except Exception:
                    # For non-ClientError exceptions, don't retry
                    raise

            # All retries exhausted
            if last_exception:
                raise last_exception
            raise RuntimeError("Retry logic error")  # Should never reach here

        return wrapper

    return decorator


class S3StorageService:
    """
    Service for handling file operations with S3-compatible storage.

    Supports AWS S3 and S3-compatible systems like MinIO, LocalStack, etc.
    Provides async operations for upload, download, delete, and presigned URLs.
    """

    def __init__(self):
        self.backend = settings.FILE_STORAGE_BACKEND.lower()
        self.local_root = Path(settings.LOCAL_STORAGE_ROOT)
        self.local_public_base_url = (settings.LOCAL_PUBLIC_BASE_URL or "").rstrip("/")

        self.bucket_name = settings.S3_BUCKET_NAME
        self.region = settings.S3_REGION
        self.endpoint_url = settings.S3_ENDPOINT_URL
        self.external_endpoint_url = settings.S3_EXTERNAL_ENDPOINT_URL

        # Session configuration for S3-compatible storage
        self.session_config = {
            "aws_access_key_id": settings.S3_ACCESS_KEY_ID,
            "aws_secret_access_key": settings.S3_SECRET_ACCESS_KEY.get_secret_value(),
            "region_name": self.region,
        }

        if self.backend == "local":
            self.local_root.mkdir(parents=True, exist_ok=True)

    async def _get_client(self, endpoint_url: str | None = None):
        """Get async S3 client with proper configuration."""
        session = aioboto3.Session(**self.session_config)

        # Client configuration - endpoint_url should be passed here, not to Session
        client_config = {}
        resolved_endpoint = endpoint_url if endpoint_url else self.endpoint_url
        if resolved_endpoint:
            client_config["endpoint_url"] = resolved_endpoint
            client_config["use_ssl"] = settings.S3_USE_SSL

            addressing_style = (settings.S3_ADDRESSING_STYLE or "path").lower()
            signature_version = settings.S3_SIGNATURE_VERSION or "s3v4"

            client_config["config"] = Config(
                s3={
                    "addressing_style": addressing_style,
                },
                signature_version=signature_version,
                # https://github.com/boto/boto3/issues/4400#issuecomment-2600742103
                request_checksum_calculation="when_required",
                response_checksum_validation="when_required",
            )

        return session.client("s3", **client_config)

    def _local_path(self, file_key: str) -> Path:
        # Prevent path traversal attacks
        normalized = Path(file_key).parts
        if ".." in normalized or file_key.startswith("/"):
            raise ValueError(f"Invalid file_key: {file_key}")
        path = self.local_root / file_key
        resolved = path.resolve()
        if not str(resolved).startswith(str(self.local_root.resolve())):
            raise ValueError(f"Path traversal detected: {file_key}")
        return resolved

    def _generate_file_key(self, file_type: str, file_id: UUID, filename: str) -> str:
        """
        Generate S3 object key for file storage.

        Format: {file_type}/{year}/{month}/{day}/{file_id}.{ext}
        This provides organized storage with date-based partitioning.
        """
        now = datetime.now(UTC)
        year = now.strftime("%Y")
        month = now.strftime("%m")
        day = now.strftime("%d")

        # Extract file extension from original filename
        file_ext = filename.split(".")[-1] if "." in filename else ""
        file_name = f"{file_id}.{file_ext}" if file_ext else str(file_id)

        return f"{file_type}/{year}/{month}/{day}/{file_name}"

    async def upload_file(
        self,
        file_data: BinaryIO,
        file_type: str,
        file_id: UUID,
        filename: str,
        content_type: str,
        file_size: int,
    ) -> str:
        """
        Upload file to S3-compatible storage.

        Args:
            file_data: Binary file data
            file_type: Type of file (avatar, document, etc.)
            file_id: Unique file identifier
            filename: Original filename
            content_type: MIME type of the file
            file_size: Size of the file in bytes

        Returns:
            S3 object key of uploaded file

        Raises:
            ClientError: If S3 operation fails
            NoCredentialsError: If S3 credentials are invalid
        """
        file_key = self._generate_file_key(file_type, file_id, filename)

        # Local filesystem backend
        if self.backend == "local":
            file_path = self._local_path(file_key)
            file_path.parent.mkdir(parents=True, exist_ok=True)

            # Normalize data to bytes
            if isinstance(file_data, (bytes, bytearray)):
                data_bytes = bytes(file_data)
            else:
                if hasattr(file_data, "seek"):
                    file_data.seek(0)
                data_bytes = file_data.read()

            try:
                with open(file_path, "wb") as dst:
                    dst.write(data_bytes)
                logger.info(f"File saved locally: {file_path}")
                return file_key
            except Exception as e:
                logger.error(f"Failed to save local file {filename}: {e}")
                raise

        # S3-compatible backend
        try:
            async with await self._get_client() as s3_client:
                # Upload file with metadata
                await s3_client.put_object(
                    Bucket=self.bucket_name,
                    Key=file_key,
                    Body=file_data,
                    ContentType=content_type,
                    ContentLength=file_size,
                    Metadata={
                        "file-id": str(file_id),
                        "file-type": file_type,
                        "original-filename": filename,
                        "upload-timestamp": datetime.now(UTC).isoformat(),
                    },
                )

                logger.info(f"File uploaded successfully: {file_key}")
                return file_key

        except ClientError as e:
            logger.error(f"Failed to upload file {filename}: {e}")
            raise
        except NoCredentialsError as e:
            logger.error(f"S3 credentials error: {e}")
            raise

    async def upload_public_file(
        self,
        file_data: BinaryIO,
        file_type: str,
        file_id: UUID,
        filename: str,
        content_type: str,
        file_size: int,
    ) -> str:
        """
        Upload file to storage and return the storage key.

        Args:
            file_data: Binary file data
            file_type: Type of file (avatar, document, etc.)
            file_id: Unique file identifier
            filename: Original filename
            content_type: MIME type of the file
            file_size: Size of the file in bytes

        Returns:
            Storage key/path of the uploaded file

        Raises:
            ClientError: If S3 operation fails
            NoCredentialsError: If S3 credentials are invalid
        """
        file_key = await self.upload_file(
            file_data, file_type, file_id, filename, content_type, file_size
        )

        return file_key

    async def download_file(self, file_key: str) -> tuple[BytesIO, str]:
        """
        Download file from S3-compatible storage.

        Args:
            file_key: S3 object key

        Returns:
            Tuple of (file_data, content_type)

        Raises:
            ClientError: If file not found or S3 operation fails
        """
        if self.backend == "local":
            file_path = self._local_path(file_key)
            if not file_path.exists():
                logger.warning(f"Local file not found: {file_key}")
                raise FileNotFoundError(file_key)

            data = BytesIO(file_path.read_bytes())
            data.seek(0)
            # Detect content type from file extension
            content_type, _ = mimetypes.guess_type(file_key)
            return data, content_type or "application/octet-stream"

        try:
            async with await self._get_client() as s3_client:
                response = await s3_client.get_object(
                    Bucket=self.bucket_name, Key=file_key
                )

                # Read file data
                file_data = BytesIO()
                async for chunk in response["Body"]:
                    file_data.write(chunk)
                file_data.seek(0)

                content_type = response.get("ContentType", "application/octet-stream")

                logger.info(f"File downloaded successfully: {file_key}")
                return file_data, content_type

        except ClientError as e:
            if e.response["Error"]["Code"] == "NoSuchKey":
                logger.warning(f"File not found: {file_key}")
            else:
                logger.error(f"Failed to download file {file_key}: {e}")
            raise

    async def delete_file(self, file_key: str) -> bool:
        """
        Delete file from S3-compatible storage.

        Args:
            file_key: S3 object key

        Returns:
            True if deletion successful, False otherwise
        """
        if self.backend == "local":
            file_path = self._local_path(file_key)
            try:
                if file_path.exists():
                    file_path.unlink()
                logger.info(f"Local file deleted: {file_key}")
                return True
            except Exception as e:
                logger.error(f"Failed to delete local file {file_key}: {e}")
                return False

        try:
            async with await self._get_client() as s3_client:
                await s3_client.delete_object(Bucket=self.bucket_name, Key=file_key)

                logger.info(f"File deleted successfully: {file_key}")
                return True

        except ClientError as e:
            logger.error(f"Failed to delete file {file_key}: {e}")
            return False

    async def file_exists(self, file_key: str) -> bool:
        """
        Check if file exists in S3-compatible storage.

        Args:
            file_key: S3 object key

        Returns:
            True if file exists, False otherwise
        """
        if self.backend == "local":
            return self._local_path(file_key).exists()

        try:
            async with await self._get_client() as s3_client:
                await s3_client.head_object(Bucket=self.bucket_name, Key=file_key)
                return True

        except ClientError as e:
            if e.response["Error"]["Code"] == "404":
                return False
            logger.error(f"Error checking file existence {file_key}: {e}")
            return False

    async def get_public_url(self, file_key: str) -> str:
        """
        Generate public URL for file access (requires bucket to have public read access).

        Args:
            file_key: S3 object key

        Returns:
            Public URL string
        """
        if self.backend == "local":
            if self.local_public_base_url:
                return f"{self.local_public_base_url}/{file_key}"
            # Return API download endpoint URL for local files
            return f"/api/v1/files/download/{file_key}"

        base_url = (
            self.external_endpoint_url
            if self.external_endpoint_url
            else self.endpoint_url
        )
        base_url = base_url.rstrip("/")
        return f"{base_url}/{file_key}"

    async def generate_presigned_url(
        self, file_key: str, expiration: int = 3600, method: str = "get_object"
    ) -> str | None:
        """
        Generate presigned URL for file access.

        Args:
            file_key: S3 object key
            expiration: URL expiration time in seconds (default: 1 hour)
            method: S3 method (get_object, put_object, etc.)

        Returns:
            Presigned URL string or None if generation fails
        """
        if self.backend == "local":
            # Presigned URLs are not applicable for local storage
            return None

        try:
            async with await self._get_client(
                endpoint_url=self.external_endpoint_url
            ) as s3_client:
                url = await s3_client.generate_presigned_url(
                    method,
                    Params={"Bucket": self.bucket_name, "Key": file_key},
                    ExpiresIn=expiration,
                )

                logger.info(f"Presigned URL generated for: {file_key}")
                return url

        except ClientError as e:
            logger.error(f"Failed to generate presigned URL for {file_key}: {e}")
            return None

    async def get_file_metadata(self, file_key: str) -> dict | None:
        """
        Get file metadata from S3-compatible storage.

        Args:
            file_key: S3 object key

        Returns:
            Dictionary containing file metadata or None if file not found
        """
        if self.backend == "local":
            file_path = self._local_path(file_key)
            if not file_path.exists():
                logger.warning(f"File not found: {file_key}")
                return None

            stat = file_path.stat()
            return {
                "size": stat.st_size,
                "content_type": "",
                "last_modified": stat.st_mtime,
                "etag": "",
                "metadata": {},
            }

        try:
            async with await self._get_client() as s3_client:
                response = await s3_client.head_object(
                    Bucket=self.bucket_name, Key=file_key
                )

                return {
                    "size": response.get("ContentLength", 0),
                    "content_type": response.get("ContentType", ""),
                    "last_modified": response.get("LastModified"),
                    "etag": response.get("ETag", "").strip('"'),
                    "metadata": response.get("Metadata", {}),
                }

        except ClientError as e:
            if e.response["Error"]["Code"] == "404":
                logger.warning(f"File not found: {file_key}")
            else:
                logger.error(f"Failed to get metadata for {file_key}: {e}")
            return None

    async def create_bucket_if_not_exists(self) -> bool:
        """
        Create S3 bucket if it doesn't exist.

        Returns:
            True if bucket exists or was created successfully, False otherwise
        """
        if self.backend == "local":
            try:
                self.local_root.mkdir(parents=True, exist_ok=True)
                return True
            except Exception as e:
                logger.error(
                    f"Failed to create local storage root {self.local_root}: {e}"
                )
                return False

        try:
            async with await self._get_client() as s3_client:
                # Check if bucket exists
                try:
                    await s3_client.head_bucket(Bucket=self.bucket_name)
                    logger.info(f"Bucket {self.bucket_name} already exists")
                    return True
                except ClientError as e:
                    if e.response["Error"]["Code"] != "404":
                        raise

                # Create bucket
                create_params = {"Bucket": self.bucket_name}

                # Add location constraint for regions other than us-east-1
                if self.region and self.region != "us-east-1":
                    create_params["CreateBucketConfiguration"] = {
                        "LocationConstraint": self.region
                    }

                await s3_client.create_bucket(**create_params)
                logger.info(f"Bucket {self.bucket_name} created successfully")
                return True

        except ClientError as e:
            logger.error(f"Failed to create bucket {self.bucket_name}: {e}")
            return False

    async def health_check(self) -> dict[str, Any]:
        """
        Check storage backend health.

        Returns:
            Dictionary with health status and details
        """
        result = {
            "backend": self.backend,
            "healthy": False,
            "details": {},
        }

        if self.backend == "local":
            try:
                # Check if storage root exists and is writable
                if self.local_root.exists() and self.local_root.is_dir():
                    # Try to write a test file
                    test_file = self.local_root / ".health_check"
                    test_file.write_text("ok")
                    test_file.unlink()
                    result["healthy"] = True
                    result["details"] = {
                        "storage_root": str(self.local_root),
                        "writable": True,
                    }
                else:
                    result["details"] = {
                        "error": "Storage root does not exist or is not a directory"
                    }
            except Exception as e:
                result["details"] = {"error": str(e)}
            return result

        # S3 health check
        try:
            async with await self._get_client() as s3_client:
                # Try to list bucket (lightweight operation)
                await s3_client.head_bucket(Bucket=self.bucket_name)
                result["healthy"] = True
                result["details"] = {
                    "bucket": self.bucket_name,
                    "endpoint": self.endpoint_url,
                    "region": self.region,
                }
        except ClientError as e:
            error_code = e.response.get("Error", {}).get("Code", "Unknown")
            result["details"] = {
                "error": f"S3 error: {error_code}",
                "bucket": self.bucket_name,
                "endpoint": self.endpoint_url,
            }
        except Exception as e:
            result["details"] = {"error": str(e)}

        return result

    @with_retry()
    async def upload_file_with_retry(
        self,
        file_data: BinaryIO,
        file_type: str,
        file_id: UUID,
        filename: str,
        content_type: str,
        file_size: int,
    ) -> str:
        """Upload file with automatic retry on transient failures."""
        return await self.upload_file(
            file_data, file_type, file_id, filename, content_type, file_size
        )

    @with_retry()
    async def download_file_with_retry(self, file_key: str) -> tuple[BytesIO, str]:
        """Download file with automatic retry on transient failures."""
        return await self.download_file(file_key)


# Global storage service instance
storage_service = S3StorageService()


async def init_storage() -> bool:
    """
    Initialize storage backend on application startup.

    - Creates bucket if configured (S3_AUTO_CREATE_BUCKET=true)
    - Verifies storage is accessible

    Returns:
        True if initialization successful, False otherwise
    """
    if settings.FILE_STORAGE_BACKEND.lower() == "s3":
        if settings.S3_AUTO_CREATE_BUCKET:
            logger.info("Initializing S3 storage...")
            success = await storage_service.create_bucket_if_not_exists()
            if not success:
                logger.warning(
                    "Failed to create/verify S3 bucket. Storage operations may fail."
                )
                return False
            logger.info("S3 storage initialized successfully")
    else:
        # Local storage - ensure directory exists
        await storage_service.create_bucket_if_not_exists()
        logger.info(f"Local storage initialized at {storage_service.local_root}")

    return True
