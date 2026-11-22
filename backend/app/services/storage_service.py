import logging
import os
import re
import uuid
from functools import lru_cache
from typing import Optional

import httpx

from app.core.config import settings
from app.core.database import sanitize_error_message

logger = logging.getLogger("app.services.storage")

# Canonical MIME types for allowed document extensions
CONTENT_TYPE_MAPPINGS: dict[str, str] = {
    "pdf": "application/pdf",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "txt": "text/plain; charset=utf-8",
}


class StorageError(Exception):
    """Base exception for Supabase Storage operations."""
    pass


class StorageConfigurationError(StorageError):
    """Raised when Supabase Storage credentials or settings are missing or unconfigured."""
    pass


class StorageUploadError(StorageError):
    """Raised when an object upload to Supabase Storage fails."""
    pass


class StorageDeleteError(StorageError):
    """Raised when object deletion from Supabase Storage fails."""
    pass


def generate_storage_path(document_id: uuid.UUID | str, safe_filename: str) -> str:
    """
    Generates a deterministic, unique, and safe storage object path.
    Structure: documents/{document_id}/{safe_filename}

    Args:
        document_id: UUID identifier of the document.
        safe_filename: Sanitized original filename.

    Returns:
        Structured storage object path string.

    Raises:
        ValueError: If document_id is not a valid UUID string or safe_filename is empty.
    """
    # Guarantee document_id is a valid UUID
    doc_uuid = uuid.UUID(str(document_id))

    # Strip any directory separators or path traversal components
    normalized = safe_filename.replace("\\", "/")
    base_name = os.path.basename(normalized)
    cleaned = re.sub(r"[^\w\s\.\-\(\)\[\]]", "", base_name).strip()
    cleaned = cleaned.lstrip("./\\")

    if not cleaned or cleaned.replace(".", "") == "":
        cleaned = f"document_{doc_uuid.hex[:8]}"

    return f"documents/{doc_uuid}/{cleaned}"


def get_content_type(file_type: str, client_content_type: Optional[str] = None) -> str:
    """
    Determines the appropriate Content-Type header for storage upload.
    Prefers validated canonical type for the recognized file format.

    Args:
        file_type: Normalized file extension ('pdf', 'docx', 'txt').
        client_content_type: Optional Content-Type header sent by client.

    Returns:
        MIME type string for storage upload headers.
    """
    normalized_type = file_type.lower().strip()
    if normalized_type in CONTENT_TYPE_MAPPINGS:
        return CONTENT_TYPE_MAPPINGS[normalized_type]

    if client_content_type and client_content_type.strip():
        return client_content_type.strip()

    return "application/octet-stream"


class StorageService:
    """
    Server-side integration service for Supabase Storage.
    Manages secure uploads, deletions, and existence checks for enterprise documents
    in the private 'knowledge-documents' bucket.
    """

    def __init__(
        self,
        supabase_url: Optional[str] = None,
        service_role_key: Optional[str] = None,
        bucket_name: Optional[str] = None,
        timeout: Optional[float] = None,
    ) -> None:
        self.supabase_url = (supabase_url if supabase_url is not None else settings.SUPABASE_URL).rstrip("/")
        self.service_role_key = (service_role_key if service_role_key is not None else settings.SUPABASE_SERVICE_ROLE_KEY).strip()
        self.bucket_name = (bucket_name if bucket_name is not None else settings.STORAGE_BUCKET_NAME).strip()
        self.timeout = timeout if timeout is not None else settings.STORAGE_TIMEOUT

    @property
    def is_configured(self) -> bool:
        """
        Validates whether Supabase storage credentials and endpoint are configured.
        Returns False if any required setting is missing or contains placeholder markers.
        """
        if not self.supabase_url or not self.service_role_key or not self.bucket_name:
            return False
        placeholder_indicators = ("[YOUR-", "YOUR_ACTUAL_", "<project-ref>")
        if any(token in self.supabase_url for token in placeholder_indicators):
            return False
        if any(token in self.service_role_key for token in placeholder_indicators):
            return False
        return True

    def _validate_configuration(self) -> None:
        """Raises StorageConfigurationError if credentials are not configured."""
        if not self.is_configured:
            raise StorageConfigurationError(
                "Supabase storage service is not configured. Missing required credentials."
            )

    def _get_headers(self, content_type: Optional[str] = None) -> dict[str, str]:
        """
        Builds authenticated headers for Supabase Storage REST API requests.
        Never logs or exposes the service-role key.
        """
        headers = {
            "Authorization": f"Bearer {self.service_role_key}",
            "apiKey": self.service_role_key,
        }
        if content_type:
            headers["Content-Type"] = content_type
        return headers

    def _build_object_url(self, object_path: str) -> str:
        """Constructs target REST API URL for an object within the bucket."""
        cleaned_path = object_path.lstrip("/")
        return f"{self.supabase_url}/storage/v1/object/{self.bucket_name}/{cleaned_path}"

    async def upload_file(
        self,
        object_path: str,
        content: bytes,
        content_type: str = "application/octet-stream",
        upsert: bool = False,
    ) -> str:
        """
        Uploads file binary bytes to the private Supabase Storage bucket.

        Args:
            object_path: Target object path inside the bucket (e.g. documents/{id}/{filename}).
            content: Raw binary content of the file.
            content_type: MIME Content-Type header.
            upsert: Whether to overwrite existing object if already present (default: False).

        Returns:
            The confirmed object_path on success.

        Raises:
            StorageConfigurationError: If storage credentials are unconfigured.
            StorageUploadError: If upload fails due to network, server error, or conflict.
        """
        self._validate_configuration()

        url = self._build_object_url(object_path)
        headers = self._get_headers(content_type)
        if upsert:
            headers["x-upsert"] = "true"

        logger.info(
            "Uploading file binary to Supabase Storage: bucket='%s', path='%s', size=%d bytes",
            self.bucket_name,
            object_path,
            len(content),
        )

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(url, content=content, headers=headers)

            if response.status_code in (200, 201):
                logger.info(
                    "Successfully uploaded object to Supabase Storage: bucket='%s', path='%s'",
                    self.bucket_name,
                    object_path,
                )
                return object_path

            sanitized_body = sanitize_error_message(response.text)
            if response.status_code in (400, 409) and "already exists" in sanitized_body.lower():
                logger.warning(
                    "Storage upload conflict: Object already exists at '%s' in bucket '%s'",
                    object_path,
                    self.bucket_name,
                )
                raise StorageUploadError(
                    f"Storage object already exists at '{object_path}' in bucket '{self.bucket_name}'."
                )

            logger.error(
                "Supabase Storage upload failed with HTTP %d for path '%s': %s",
                response.status_code,
                object_path,
                sanitized_body,
            )
            raise StorageUploadError(
                f"Storage upload failed with HTTP status {response.status_code}."
            )

        except httpx.TimeoutException as exc:
            logger.error(
                "Timeout connecting to Supabase Storage during upload of '%s' (%ss timeout)",
                object_path,
                self.timeout,
            )
            raise StorageUploadError(
                "Storage service request timed out during document upload."
            ) from exc

        except httpx.RequestError as exc:
            sanitized_err = sanitize_error_message(str(exc))
            logger.error(
                "Network connection error uploading '%s' to Supabase Storage: %s",
                object_path,
                sanitized_err,
            )
            raise StorageUploadError(
                "Network error connecting to Supabase Storage service."
            ) from exc

    async def delete_file(self, object_path: str) -> bool:
        """
        Deletes an object from the private Supabase Storage bucket.
        Used for compensating cleanup when database transactions fail.

        Args:
            object_path: Path of the object to delete.

        Returns:
            True if deletion succeeded or object was already absent; False on failure.

        Raises:
            StorageConfigurationError: If storage credentials are unconfigured.
            StorageDeleteError: If deletion fails with an unexpected error.
        """
        self._validate_configuration()

        cleaned_path = object_path.lstrip("/")
        # Standard Supabase Storage multi/single delete endpoint
        url = f"{self.supabase_url}/storage/v1/object/{self.bucket_name}"
        headers = self._get_headers("application/json")
        payload = {"prefixes": [cleaned_path]}

        logger.info(
            "Deleting object from Supabase Storage: bucket='%s', path='%s'",
            self.bucket_name,
            cleaned_path,
        )

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.request("DELETE", url, json=payload, headers=headers)

            if response.status_code in (200, 204):
                logger.info(
                    "Successfully deleted object from Supabase Storage: '%s'",
                    cleaned_path,
                )
                return True

            if response.status_code == 404:
                logger.info(
                    "Object '%s' not found in bucket '%s' (already deleted or absent)",
                    cleaned_path,
                    self.bucket_name,
                )
                return True

            sanitized_body = sanitize_error_message(response.text)
            logger.error(
                "Supabase Storage delete failed with HTTP %d for path '%s': %s",
                response.status_code,
                cleaned_path,
                sanitized_body,
            )
            raise StorageDeleteError(
                f"Storage delete failed with HTTP status {response.status_code}."
            )

        except httpx.TimeoutException as exc:
            logger.error("Timeout during deletion of storage object '%s'", cleaned_path)
            raise StorageDeleteError("Storage deletion request timed out.") from exc

        except httpx.RequestError as exc:
            sanitized_err = sanitize_error_message(str(exc))
            logger.error("Network error during deletion of '%s': %s", cleaned_path, sanitized_err)
            raise StorageDeleteError("Network error during storage object deletion.") from exc

    async def file_exists(self, object_path: str) -> bool:
        """
        Checks whether an object exists in the Supabase Storage bucket.

        Args:
            object_path: Path of the object to check.

        Returns:
            True if object exists in the bucket, False otherwise.
        """
        self._validate_configuration()

        cleaned_path = object_path.lstrip("/")
        prefix = os.path.dirname(cleaned_path)
        filename = os.path.basename(cleaned_path)

        url = f"{self.supabase_url}/storage/v1/object/list/{self.bucket_name}"
        headers = self._get_headers("application/json")
        payload = {"prefix": prefix, "search": filename, "limit": 1}

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(url, json=payload, headers=headers)

            if response.status_code == 200:
                items = response.json()
                if isinstance(items, list):
                    return any(item.get("name") == filename for item in items)
            return False

        except Exception as exc:
            logger.warning(
                "Error checking existence of '%s' in Supabase Storage: %s",
                cleaned_path,
                sanitize_error_message(str(exc)),
            )
            return False

    def upload_file_sync(
        self,
        object_path: str,
        content: bytes,
        content_type: str = "application/octet-stream",
        upsert: bool = False,
    ) -> str:
        """Synchronous version of upload_file for scripts and testing."""
        self._validate_configuration()
        url = self._build_object_url(object_path)
        headers = self._get_headers(content_type)
        if upsert:
            headers["x-upsert"] = "true"

        with httpx.Client(timeout=self.timeout) as client:
            response = client.post(url, content=content, headers=headers)

        if response.status_code in (200, 201):
            return object_path

        sanitized_body = sanitize_error_message(response.text)
        raise StorageUploadError(
            f"Storage upload failed with HTTP status {response.status_code}: {sanitized_body}"
        )

    def delete_file_sync(self, object_path: str) -> bool:
        """Synchronous version of delete_file for scripts and testing."""
        self._validate_configuration()
        cleaned_path = object_path.lstrip("/")
        url = f"{self.supabase_url}/storage/v1/object/{self.bucket_name}"
        headers = self._get_headers("application/json")
        payload = {"prefixes": [cleaned_path]}

        with httpx.Client(timeout=self.timeout) as client:
            response = client.request("DELETE", url, json=payload, headers=headers)

        if response.status_code in (200, 204, 404):
            return True

        sanitized_body = sanitize_error_message(response.text)
        raise StorageDeleteError(
            f"Storage delete failed with HTTP status {response.status_code}: {sanitized_body}"
        )

    def file_exists_sync(self, object_path: str) -> bool:
        """Synchronous version of file_exists for scripts and manual integration testing."""
        self._validate_configuration()
        cleaned_path = object_path.lstrip("/")
        prefix = os.path.dirname(cleaned_path)
        filename = os.path.basename(cleaned_path)

        url = f"{self.supabase_url}/storage/v1/object/list/{self.bucket_name}"
        headers = self._get_headers("application/json")
        payload = {"prefix": prefix, "search": filename, "limit": 1}

        try:
            with httpx.Client(timeout=self.timeout) as client:
                response = client.post(url, json=payload, headers=headers)

            if response.status_code == 200:
                items = response.json()
                if isinstance(items, list):
                    return any(item.get("name") == filename for item in items)
            return False

        except Exception as exc:
            logger.warning(
                "Error checking existence of '%s' in Supabase Storage: %s",
                cleaned_path,
                sanitize_error_message(str(exc)),
            )
            return False


@lru_cache
def get_storage_service() -> StorageService:
    """
    FastAPI reusable dependency returning the configured StorageService instance.
    Cached singleton pattern; can be overridden in automated test suites via
    app.dependency_overrides[get_storage_service].
    """
    return StorageService(
        supabase_url=settings.SUPABASE_URL,
        service_role_key=settings.SUPABASE_SERVICE_ROLE_KEY,
        bucket_name=settings.STORAGE_BUCKET_NAME,
        timeout=settings.STORAGE_TIMEOUT,
    )
