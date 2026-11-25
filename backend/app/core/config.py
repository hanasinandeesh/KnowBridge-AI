import os
from functools import lru_cache
from pathlib import Path
from typing import Optional
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

    # Supabase Storage Configuration (Task 003B)
    SUPABASE_URL: str = Field(
        default="",
        description="Supabase project base URL (e.g. https://<project-ref>.supabase.co)",
    )
    SUPABASE_SERVICE_ROLE_KEY: str = Field(
        default="",
        description="Supabase service-role secret key (server-side only, never exposed to client)",
    )
    STORAGE_BUCKET_NAME: str = Field(
        default="knowledge-documents",
        description="Private Supabase Storage bucket for enterprise documents",
    )
    STORAGE_TIMEOUT: float = Field(
        default=15.0,
        description="HTTP request timeout in seconds for Supabase Storage API operations",
    )

    @property
    def is_storage_configured(self) -> bool:
        """
        Validates whether Supabase Storage credentials and bucket are configured.
        Returns False if any required setting is missing or contains placeholder tokens.
        """
        if not self.SUPABASE_URL or not self.SUPABASE_SERVICE_ROLE_KEY or not self.STORAGE_BUCKET_NAME:
            return False
        placeholder_indicators = ("[YOUR-", "YOUR_ACTUAL_", "<project-ref>")
        if any(token in self.SUPABASE_URL for token in placeholder_indicators):
            return False
        if any(token in self.SUPABASE_SERVICE_ROLE_KEY for token in placeholder_indicators):
            return False
        return True

    # Embedding Model Settings (Task 003E)
    EMBEDDING_MODEL_NAME: str = Field(
        default="sentence-transformers/all-MiniLM-L6-v2",
        description="Sentence Transformers model identifier for dense embeddings",
    )
    EMBEDDING_DIMENSION: int = Field(
        default=384,
        description="Expected embedding dimension vector length (fixed at 384)",
    )
    EMBEDDING_BATCH_SIZE: int = Field(
        default=32,
        description="Default batch size for generating vector embeddings",
    )
    EMBEDDING_NORMALIZE: bool = Field(
        default=True,
        description="Whether to normalize generated vector embeddings to unit length (L2 norm)",
    )
    EMBEDDING_DEVICE: Optional[str] = Field(
        default=None,
        description="Computation device for embeddings: 'cpu', 'cuda', or None (auto-detect)",
    )

    # Document Upload & Processing Settings (Task 003A)
    MAX_UPLOAD_SIZE_BYTES: int = Field(
        default=10 * 1024 * 1024,
        description="Maximum allowed upload file size in bytes (default: 10MB)",
    )
    ALLOWED_FILE_EXTENSIONS: set[str] = Field(
        default={"pdf", "docx", "txt"},
        description="Allowed file extensions for document upload",
    )

    # Document Chunking Settings (Task 003D)
    CHUNK_SIZE: int = Field(
        default=1000,
        description="Default document chunk size in characters",
    )
    CHUNK_OVERLAP: int = Field(
        default=150,
        description="Default document chunk overlap in characters",
    )

    # Groq LLM Settings (Task 05A)
    GROQ_API_KEY: str = Field(
        default="",
        description="Groq Cloud API key (server-side only, never exposed or hardcoded)",
    )
    GROQ_BASE_URL: str = Field(
        default="https://api.groq.com/openai/v1",
        description="Base URL for Groq OpenAI-compatible inference API",
    )
    GROQ_QUERY_MODEL: str = Field(
        default="openai/gpt-oss-20b",
        description="Fast free-tier Groq model for query understanding and rewriting",
    )
    GROQ_ASSESSMENT_MODEL: str = Field(
        default="openai/gpt-oss-120b",
        description="Groq reasoning model for evidence sufficiency and NLI conflict detection",
    )
    GROQ_GENERATION_MODEL: str = Field(
        default="openai/gpt-oss-120b",
        description="Groq model for grounded answer generation",
    )
    GENERATION_TEMPERATURE: float = Field(
        default=0.1,
        ge=0.0,
        le=1.0,
        description="Sampling temperature for grounded answer generation",
    )
    GENERATION_MAX_TOKENS: int = Field(
        default=2048,
        ge=64,
        le=8192,
        description="Maximum completion tokens for grounded answer generation (includes reasoning headroom)",
    )
    EVIDENCE_MIN_SIMILARITY: float = Field(
        default=0.65,
        ge=0.0,
        le=1.0,
        description="Minimum cosine similarity threshold for evidence sufficiency assessment",
    )
    GROQ_TIMEOUT: float = Field(
        default=15.0,
        description="HTTP request timeout in seconds for Groq API calls",
    )

    @property
    def is_llm_configured(self) -> bool:
        """
        Validates whether the Groq LLM API key and model are configured.
        Returns False if missing or containing placeholder tokens.
        """
        if not self.GROQ_API_KEY or not self.GROQ_API_KEY.strip():
            return False
        placeholder_indicators = ("[YOUR-", "YOUR_ACTUAL_", "<your-")
        if any(token in self.GROQ_API_KEY for token in placeholder_indicators):
            return False
        return bool(self.GROQ_QUERY_MODEL and self.GROQ_QUERY_MODEL.strip())

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
