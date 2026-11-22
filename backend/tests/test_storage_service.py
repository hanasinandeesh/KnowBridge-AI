import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from app.services.storage_service import (
    CONTENT_TYPE_MAPPINGS,
    StorageConfigurationError,
    StorageDeleteError,
    StorageError,
    StorageService,
    StorageUploadError,
    generate_storage_path,
    get_content_type,
)


# ===========================================================================
# 1. Path Generation & Content Type Helper Tests
# ===========================================================================

def test_generate_storage_path_valid():
    """Validates standard storage object path generation with UUID."""
    doc_id = uuid.uuid4()
    filename = "HR-TRV-001_Travel_Reimbursement_v1.0.pdf"
    path = generate_storage_path(doc_id, filename)

    assert path == f"documents/{doc_id}/{filename}"
    assert path.startswith("documents/")
    assert str(doc_id) in path


def test_generate_storage_path_strips_traversal():
    """Validates that directory traversal sequences are stripped from the storage path."""
    doc_id = uuid.uuid4()
    raw_filename = "../../etc/passwd.pdf"
    path = generate_storage_path(doc_id, raw_filename)

    assert path == f"documents/{doc_id}/passwd.pdf"
    assert ".." not in path
    assert "/" not in path.split(f"documents/{doc_id}/")[1]


def test_generate_storage_path_windows_separators():
    """Validates that Windows backslash separators are stripped."""
    doc_id = uuid.uuid4()
    raw_filename = "..\\..\\windows\\system32\\calc.docx"
    path = generate_storage_path(doc_id, raw_filename)

    assert path == f"documents/{doc_id}/calc.docx"
    assert "\\" not in path


def test_generate_storage_path_invalid_uuid():
    """Validates that a non-UUID string raises ValueError."""
    with pytest.raises(ValueError):
        generate_storage_path("not-a-valid-uuid", "test.pdf")


def test_get_content_type_mappings():
    """Validates MIME type mappings for allowed file extensions."""
    assert get_content_type("pdf") == "application/pdf"
    assert "openxmlformats" in get_content_type("docx")
    assert "text/plain" in get_content_type("txt")
    assert get_content_type("unknown") == "application/octet-stream"


def test_get_content_type_preserves_valid_client_type():
    """Validates preservation of valid client-specified MIME type."""
    assert get_content_type("pdf", "application/pdf") == "application/pdf"
    assert get_content_type("txt", "text/plain; charset=utf-8") == "text/plain; charset=utf-8"


# ===========================================================================
# 2. StorageService Configuration Tests
# ===========================================================================

def test_storage_service_is_configured_true():
    """Validates is_configured returns True when valid credentials are set."""
    service = StorageService(
        supabase_url="https://xyzproject.supabase.co",
        service_role_key="valid-service-role-key-12345",
        bucket_name="knowledge-documents",
    )
    assert service.is_configured is True


@pytest.mark.parametrize(
    "url,key,bucket",
    [
        ("", "some-key", "knowledge-documents"),
        ("https://xyz.supabase.co", "", "knowledge-documents"),
        ("https://xyz.supabase.co", "some-key", ""),
        ("https://[YOUR-PROJECT-REF].supabase.co", "some-key", "knowledge-documents"),
        ("https://xyz.supabase.co", "[YOUR-SUPABASE-SERVICE-ROLE-KEY]", "knowledge-documents"),
    ],
)
def test_storage_service_is_configured_false_with_placeholders(url, key, bucket):
    """Validates is_configured returns False with empty or placeholder values."""
    service = StorageService(supabase_url=url, service_role_key=key, bucket_name=bucket)
    assert service.is_configured is False


@pytest.mark.anyio
async def test_unconfigured_service_raises_storage_configuration_error():
    """Validates that attempting storage operations with missing credentials raises StorageConfigurationError."""
    service = StorageService(supabase_url="", service_role_key="", bucket_name="")
    assert service.is_configured is False

    with pytest.raises(StorageConfigurationError) as exc_info:
        await service.upload_file("documents/test/test.pdf", b"data")
    assert "not configured" in str(exc_info.value).lower()

    with pytest.raises(StorageConfigurationError):
        await service.delete_file("documents/test/test.pdf")

    with pytest.raises(StorageConfigurationError):
        await service.file_exists("documents/test/test.pdf")


# ===========================================================================
# 3. StorageService Upload Tests (Async)
# ===========================================================================

@pytest.fixture
def configured_service():
    """Provides a StorageService configured with mock credentials."""
    return StorageService(
        supabase_url="https://mockproject.supabase.co",
        service_role_key="mock-service-role-key-12345",
        bucket_name="knowledge-documents",
        timeout=5.0,
    )


@pytest.mark.anyio
async def test_upload_file_success(configured_service: StorageService):
    """Validates successful file upload returns object path and sends correct headers."""
    mock_response = MagicMock(spec=httpx.Response)
    mock_response.status_code = 200
    mock_response.json.return_value = {"Key": "knowledge-documents/documents/uuid/test.pdf"}

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_response

        path = "documents/550e8400-e29b-41d4-a716-446655440000/test.pdf"
        result = await configured_service.upload_file(
            object_path=path,
            content=b"%PDF-1.4 mock content",
            content_type="application/pdf",
        )

        assert result == path
        mock_post.assert_called_once()
        call_kwargs = mock_post.call_args[1]
        assert call_kwargs["content"] == b"%PDF-1.4 mock content"
        assert call_kwargs["headers"]["Authorization"] == "Bearer mock-service-role-key-12345"
        assert call_kwargs["headers"]["apiKey"] == "mock-service-role-key-12345"
        assert call_kwargs["headers"]["Content-Type"] == "application/pdf"


@pytest.mark.anyio
async def test_upload_file_conflict_error(configured_service: StorageService):
    """Validates HTTP 409 Conflict raises StorageUploadError."""
    mock_response = MagicMock(spec=httpx.Response)
    mock_response.status_code = 409
    mock_response.text = '{"statusCode": "409", "error": "Duplicate", "message": "The resource already exists"}'

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_response

        with pytest.raises(StorageUploadError) as exc_info:
            await configured_service.upload_file("documents/test/test.pdf", b"bytes")

        assert "already exists" in str(exc_info.value).lower()


@pytest.mark.anyio
async def test_upload_file_http_500_error(configured_service: StorageService):
    """Validates HTTP 500 from Supabase Storage raises StorageUploadError."""
    mock_response = MagicMock(spec=httpx.Response)
    mock_response.status_code = 500
    mock_response.text = "Internal Server Error in Supabase Storage"

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_response

        with pytest.raises(StorageUploadError) as exc_info:
            await configured_service.upload_file("documents/test/test.pdf", b"bytes")

        assert "500" in str(exc_info.value)


@pytest.mark.anyio
async def test_upload_file_timeout(configured_service: StorageService):
    """Validates httpx.TimeoutException is caught and translated to StorageUploadError."""
    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.side_effect = httpx.TimeoutException("Upload timed out")

        with pytest.raises(StorageUploadError) as exc_info:
            await configured_service.upload_file("documents/test/test.pdf", b"bytes")

        assert "timed out" in str(exc_info.value).lower()


@pytest.mark.anyio
async def test_upload_file_network_error(configured_service: StorageService):
    """Validates httpx.RequestError (network failure) raises StorageUploadError."""
    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.side_effect = httpx.ConnectError("Failed to resolve host")

        with pytest.raises(StorageUploadError) as exc_info:
            await configured_service.upload_file("documents/test/test.pdf", b"bytes")

        assert "network error" in str(exc_info.value).lower()


# ===========================================================================
# 4. StorageService Delete Tests (Async)
# ===========================================================================

@pytest.mark.anyio
async def test_delete_file_success(configured_service: StorageService):
    """Validates successful deletion returns True."""
    mock_response = MagicMock(spec=httpx.Response)
    mock_response.status_code = 200
    mock_response.json.return_value = [{"name": "test.pdf"}]

    with patch("httpx.AsyncClient.request", new_callable=AsyncMock) as mock_req:
        mock_req.return_value = mock_response

        path = "documents/test-id/test.pdf"
        result = await configured_service.delete_file(path)

        assert result is True
        mock_req.assert_called_once()
        call_kwargs = mock_req.call_args[1]
        assert call_kwargs["json"] == {"prefixes": [path]}


@pytest.mark.anyio
async def test_delete_file_404_idempotent(configured_service: StorageService):
    """Validates 404 response on delete returns True (idempotent cleanup)."""
    mock_response = MagicMock(spec=httpx.Response)
    mock_response.status_code = 404
    mock_response.text = "Not Found"

    with patch("httpx.AsyncClient.request", new_callable=AsyncMock) as mock_req:
        mock_req.return_value = mock_response

        result = await configured_service.delete_file("documents/absent/test.pdf")
        assert result is True


@pytest.mark.anyio
async def test_delete_file_server_error(configured_service: StorageService):
    """Validates HTTP 500 on delete raises StorageDeleteError."""
    mock_response = MagicMock(spec=httpx.Response)
    mock_response.status_code = 500
    mock_response.text = "Storage cluster failure"

    with patch("httpx.AsyncClient.request", new_callable=AsyncMock) as mock_req:
        mock_req.return_value = mock_response

        with pytest.raises(StorageDeleteError):
            await configured_service.delete_file("documents/test/test.pdf")


# ===========================================================================
# 5. StorageService Existence Check (Async)
# ===========================================================================

@pytest.mark.anyio
async def test_file_exists_returns_true_when_present(configured_service: StorageService):
    """Validates file_exists returns True when object is listed in bucket."""
    mock_response = MagicMock(spec=httpx.Response)
    mock_response.status_code = 200
    mock_response.json.return_value = [
        {"name": "test.pdf", "id": "123", "metadata": {}}
    ]

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_response

        result = await configured_service.file_exists("documents/uuid/test.pdf")
        assert result is True


@pytest.mark.anyio
async def test_file_exists_returns_false_when_absent(configured_service: StorageService):
    """Validates file_exists returns False when object is not in bucket."""
    mock_response = MagicMock(spec=httpx.Response)
    mock_response.status_code = 200
    mock_response.json.return_value = []

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_response

        result = await configured_service.file_exists("documents/uuid/nonexistent.pdf")
        assert result is False


# ===========================================================================
# 6. Synchronous Methods Tests
# ===========================================================================

def test_sync_upload_and_delete_success(configured_service: StorageService):
    """Validates synchronous upload_file_sync and delete_file_sync."""
    mock_upload_resp = MagicMock(spec=httpx.Response)
    mock_upload_resp.status_code = 200

    mock_delete_resp = MagicMock(spec=httpx.Response)
    mock_delete_resp.status_code = 200

    with patch("httpx.Client.post") as mock_post, patch("httpx.Client.request") as mock_req:
        mock_post.return_value = mock_upload_resp
        mock_req.return_value = mock_delete_resp

        path = "documents/test-sync/file.txt"
        up_res = configured_service.upload_file_sync(path, b"content")
        assert up_res == path

        del_res = configured_service.delete_file_sync(path)
        assert del_res is True
