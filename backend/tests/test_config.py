import pytest
from app.core.config import Settings


def test_default_settings():
    """Validates default configuration parameters and pool sizes."""
    config = Settings(DATABASE_URL="")
    assert config.PROJECT_NAME == "KnowBridge AI Backend"
    assert config.ENVIRONMENT in ("development", "testing")
    assert config.DB_POOL_SIZE == 5
    assert config.DB_MAX_OVERFLOW == 10
    assert config.DB_POOL_TIMEOUT == 30
    assert config.DB_POOL_RECYCLE == 1800
    assert config.DB_ECHO is False
    assert config.CHUNK_SIZE == 1000
    assert config.CHUNK_OVERLAP == 150
    assert config.EMBEDDING_MODEL_NAME == "sentence-transformers/all-MiniLM-L6-v2"
    assert config.EMBEDDING_DIMENSION == 384
    assert config.EMBEDDING_BATCH_SIZE == 32
    assert config.EMBEDDING_NORMALIZE is True
    assert config.EMBEDDING_DEVICE is None


@pytest.mark.parametrize(
    "input_url,expected_uri",
    [
        (
            "postgresql://postgres:secret123@db.supabase.co:5432/postgres",
            "postgresql+psycopg://postgres:secret123@db.supabase.co:5432/postgres",
        ),
        (
            "postgres://postgres:secret123@db.supabase.co:5432/postgres",
            "postgresql+psycopg://postgres:secret123@db.supabase.co:5432/postgres",
        ),
        (
            "postgresql+psycopg://postgres:secret123@db.supabase.co:5432/postgres",
            "postgresql+psycopg://postgres:secret123@db.supabase.co:5432/postgres",
        ),
        ("", ""),
    ],
)
def test_sqlalchemy_database_uri_dialect_conversion(input_url, expected_uri):
    """Ensures raw PostgreSQL URIs are automatically mapped to the psycopg driver dialect."""
    if input_url == "":
        config = Settings(DATABASE_URL="", DB_HOST="", DB_USER="")
    else:
        config = Settings(DATABASE_URL=input_url)
    assert config.sqlalchemy_database_uri == expected_uri


def test_masked_database_url_redacts_password():
    """Ensures database credentials are never exposed in plaintext representations."""
    raw_url = "postgresql://my_user:super_secret_password@db.xyz.supabase.co:5432/postgres"
    config = Settings(DATABASE_URL=raw_url)
    masked = config.masked_database_url

    assert "super_secret_password" not in masked
    assert "*****" in masked
    assert "my_user" in masked
    assert "db.xyz.supabase.co" in masked
    assert "5432" in masked


def test_masked_database_url_empty():
    """Ensures empty database URL is represented safely without error."""
    config = Settings(DATABASE_URL="", DB_HOST="", DB_USER="")
    assert config.masked_database_url == "<not configured>"


def test_granular_db_settings_constructs_url_with_encoding():
    """Validates that special characters in passwords are safely URL-encoded when building from components."""
    config = Settings(
        DATABASE_URL="",
        DB_HOST="aws-1-ap-southeast-2.pooler.supabase.com",
        DB_PORT=5432,
        DB_NAME="postgres",
        DB_USER="postgres.iwwleppesznhdecsickr",
        DB_PASSWORD="p@ssword/with#special?chars",
    )
    uri = config.sqlalchemy_database_uri
    assert "p%40ssword%2Fwith%23special%3Fchars" in uri
    assert "postgresql+psycopg://postgres.iwwleppesznhdecsickr:" in uri
    assert config.masked_database_url.endswith("@aws-1-ap-southeast-2.pooler.supabase.com:5432/postgres")
    assert "special" not in config.masked_database_url
    assert "*****" in config.masked_database_url


def test_database_url_takes_precedence_over_granular_settings():
    """Validates that DATABASE_URL remains the preferred single source of truth."""
    config = Settings(
        DATABASE_URL="postgresql+psycopg://user:pass@customhost:5432/customdb",
        DB_HOST="otherhost",
    )
    assert "customhost" in config.sqlalchemy_database_uri
    assert "otherhost" not in config.sqlalchemy_database_uri


def test_database_url_placeholder_falls_back_to_granular():
    """Validates that if DATABASE_URL contains default placeholder text, real granular password takes precedence."""
    config = Settings(
        DATABASE_URL="postgresql+psycopg://postgres.iwwleppesznhdecsickr:YOUR_ACTUAL_PASSWORD@aws-1-ap-southeast-2.pooler.supabase.com:5432/postgres",
        DB_HOST="aws-1-ap-southeast-2.pooler.supabase.com",
        DB_PORT=5432,
        DB_NAME="postgres",
        DB_USER="postgres.iwwleppesznhdecsickr",
        DB_PASSWORD="real_secret_password",
    )
    uri = config.sqlalchemy_database_uri
    assert "real_secret_password" in uri
    assert "YOUR_ACTUAL_PASSWORD" not in uri
