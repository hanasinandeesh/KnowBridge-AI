import os
from functools import lru_cache
from pathlib import Path
from urllib.parse import quote_plus, urlparse, urlunparse

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# Locate backend root directory and .env file
BACKEND_DIR = Path(__file__).resolve().parent.parent.parent
ENV_FILE = BACKEND_DIR / ".env"


class Settings(BaseSettings):
    """Application and database configuration settings."""

    # Application settings
    PROJECT_NAME: str = "KnowBridge AI Backend"
    ENVIRONMENT: str = "development"
    API_V1_STR: str = "/api/v1"

    # Database connection parameters (Supabase PostgreSQL Session Pooler)
    DB_HOST: str = Field(
        default="aws-1-ap-southeast-2.pooler.supabase.com",
        description="Database host address",
    )
    DB_PORT: int = Field(
        default=5432,
        description="Database port (5432 for session pooler, 6543 for transaction pooler)",
    )
    DB_NAME: str = Field(
        default="postgres",
        description="Database name",
    )
    DB_USER: str = Field(
        default="postgres.iwwleppesznhdecsickr",
        description="Database user identifier",
    )
    DB_PASSWORD: str = Field(
        default="",
        description="Database password",
    )
    DATABASE_URL: str = Field(
        default="",
        description="PostgreSQL connection string (preferred single source of truth for SQLAlchemy)",
    )

    # SQLAlchemy Engine Connection Pooling Settings
    # Configured for cloud PostgreSQL / Supabase connection poolers
    DB_POOL_SIZE: int = Field(
        default=5,
        description="Number of persistent connections to keep in the pool",
    )
    DB_MAX_OVERFLOW: int = Field(
        default=10,
        description="Maximum temporary connections allowed beyond pool_size",
    )
    DB_POOL_TIMEOUT: int = Field(
        default=30,
        description="Timeout in seconds to wait before giving up on a connection from pool",
    )
    DB_CONNECT_TIMEOUT: int = Field(
        default=5,
        description="Timeout in seconds for socket/network connection establishment",
    )
    DB_POOL_RECYCLE: int = Field(
        default=1800,
        description="Recycle connections older than N seconds (prevents stale TCP timeouts)",
    )
    DB_ECHO: bool = Field(
        default=False,
        description="SQLAlchemy SQL query statement logging (set False in production)",
    )

    # Supabase Storage & Future Capabilities (Task 04)
    SUPABASE_URL: str = ""
    SUPABASE_SERVICE_ROLE_KEY: str = ""
    STORAGE_BUCKET_NAME: str = "knowledge-documents"

    # Embedding Model Settings
    EMBEDDING_MODEL_NAME: str = "sentence-transformers/all-MiniLM-L6-v2"
    EMBEDDING_DIMENSION: int = 384

    model_config = SettingsConfigDict(
        env_file=str(ENV_FILE) if ENV_FILE.exists() else ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @property
    def sqlalchemy_database_uri(self) -> str:
        """
        Converts standard PostgreSQL URIs to SQLAlchemy + psycopg dialect.
        e.g., 'postgresql://...' or 'postgres://...' -> 'postgresql+psycopg://...'
        Prefers DATABASE_URL as single source of truth; falls back to granular components.
        """
        raw_url = self.DATABASE_URL.strip()
        # If DATABASE_URL still has placeholder text but DB_PASSWORD has been set, fall back to granular
        placeholder_tokens = ("YOUR_ACTUAL_PASSWORD", "[YOUR-DATABASE-PASSWORD]", "<existing")
        has_url_placeholder = any(token in raw_url for token in placeholder_tokens)
        has_granular_password = bool(
            self.DB_PASSWORD and not any(token in self.DB_PASSWORD for token in placeholder_tokens)
        )

        if raw_url and not (has_url_placeholder and has_granular_password):
            if raw_url.startswith("postgres://"):
                return raw_url.replace("postgres://", "postgresql+psycopg://", 1)
            if raw_url.startswith("postgresql://") and not raw_url.startswith("postgresql+"):
                return raw_url.replace("postgresql://", "postgresql+psycopg://", 1)
            return raw_url

        # Fall back to granular connection components if DATABASE_URL is not set or holds placeholder
        if self.DB_HOST and self.DB_USER:
            user_encoded = quote_plus(self.DB_USER)
            pass_encoded = quote_plus(self.DB_PASSWORD) if self.DB_PASSWORD else ""
            auth = f"{user_encoded}:{pass_encoded}" if pass_encoded else user_encoded
            return f"postgresql+psycopg://{auth}@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"

        return ""

    @property
    def masked_database_url(self) -> str:
        """Returns the database URL with the password masked for safe logging and telemetry."""
        url = self.sqlalchemy_database_uri
        if not url:
            return "<not configured>"
        try:
            parsed = urlparse(url)
            if parsed.password:
                netloc = f"{parsed.username or ''}:*****@{parsed.hostname or ''}"
                if parsed.port:
                    netloc += f":{parsed.port}"
                return urlunparse(parsed._replace(netloc=netloc))
            return url
        except Exception:
            return "<masked database url>"


@lru_cache()
def get_settings() -> Settings:
    """Returns cached settings instance."""
    return Settings()


settings = get_settings()
