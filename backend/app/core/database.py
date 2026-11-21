import logging
import re
import time
from typing import Generator

from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import declarative_base, sessionmaker, Session

from app.core.config import settings

# Configure logger for database operations
logger = logging.getLogger("app.core.database")
if not logger.handlers:
    handler = logging.StreamHandler()
    formatter = logging.Formatter(
        "[%(asctime)s] [%(levelname)s] [%(name)s]: %(message)s"
    )
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)


def sanitize_error_message(message: str) -> str:
    """
    Sanitizes database error messages by redacting passwords,
    host IP credentials, or sensitive connection parameters.
    """
    # Redact :password@ patterns from connection URLs
    sanitized = re.sub(r":([^@/: ]+)@", ":*****@", message)
    # Redact password='...' or password="..." parameters
    sanitized = re.sub(
        r"(password\s*=\s*['\"])[^'\"]+(['\"])",
        r"\1*****\2",
        sanitized,
        flags=re.IGNORECASE,
    )
    return sanitized


def get_engine_args(uri: str) -> dict:
    """Determines appropriate engine arguments based on dialect."""
    if "sqlite" in uri:
        return {"connect_args": {"check_same_thread": False}}
    connect_args = {
        "connect_timeout": settings.DB_CONNECT_TIMEOUT,
    }
    if "supabase" in uri and "sslmode" not in uri:
        connect_args["sslmode"] = "require"
    return {
        "pool_pre_ping": True,
        "pool_size": settings.DB_POOL_SIZE,
        "max_overflow": settings.DB_MAX_OVERFLOW,
        "pool_recycle": settings.DB_POOL_RECYCLE,
        "pool_timeout": settings.DB_POOL_TIMEOUT,
        "echo": settings.DB_ECHO,
        "connect_args": connect_args,
    }


# Initialize engine if DATABASE_URL is configured
engine = None
SessionLocal = None

db_uri = settings.sqlalchemy_database_uri
if db_uri:
    try:
        engine = create_engine(db_uri, **get_engine_args(db_uri))
        SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
        logger.info(
            "SQLAlchemy engine initialized for dialect '%s' (driver '%s') at %s",
            engine.dialect.name,
            engine.dialect.driver,
            settings.masked_database_url,
        )
    except Exception as exc:
        logger.error(
            "Failed to initialize SQLAlchemy engine: %s",
            sanitize_error_message(str(exc)),
        )
        engine = None
        SessionLocal = None
else:
    logger.warning(
        "DATABASE_URL is not set. Engine initialization deferred until configured in backend/.env"
    )

Base = declarative_base()


def get_db() -> Generator[Session, None, None]:
    """
    FastAPI reusable dependency providing a transactional database session.
    Ensures sessions are closed deterministically after request completion.
    """
    if SessionLocal is None or engine is None:
        raise SQLAlchemyError(
            "Database engine is not initialized. Ensure DATABASE_URL is set in backend/.env"
        )
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def check_db_connected(timeout_seconds: float = 5.0) -> tuple[bool, str, float]:
    """
    Lightweight PostgreSQL connectivity health check.
    Executes 'SELECT 1' and returns (is_healthy, message, latency_ms).
    Safely handles errors without leaking credentials.
    """
    if engine is None:
        return (
            False,
            "DATABASE_URL is not configured in backend/.env",
            0.0,
        )

    start_time = time.perf_counter()
    try:
        # Open connection and execute SELECT 1
        with engine.connect() as conn:
            result = conn.execute(text("SELECT 1"))
            val = result.scalar()
            latency_ms = round((time.perf_counter() - start_time) * 1000, 2)
            if val == 1:
                return True, "Database connection verified successfully.", latency_ms
            return False, f"Unexpected query scalar: {val}", latency_ms
    except SQLAlchemyError as exc:
        latency_ms = round((time.perf_counter() - start_time) * 1000, 2)
        sanitized = sanitize_error_message(str(exc))
        logger.error("Database connectivity check failed (%sms): %s", latency_ms, sanitized)
        # Return sanitized top-level error summary
        err_line = sanitized.splitlines()[0] if sanitized.splitlines() else "Connection error"
        return False, f"Database connection failed: {err_line}", latency_ms
    except Exception as exc:
        latency_ms = round((time.perf_counter() - start_time) * 1000, 2)
        sanitized = sanitize_error_message(str(exc))
        logger.error("Unexpected database check error (%sms): %s", latency_ms, sanitized)
        return False, f"Unexpected error: {sanitized}", latency_ms


def close_db_connection() -> None:
    """Disposes the SQLAlchemy engine connection pool on application shutdown."""
    global engine
    if engine is not None:
        logger.info("Disposing SQLAlchemy engine connection pool...")
        engine.dispose()
        logger.info("SQLAlchemy engine disposed successfully.")
