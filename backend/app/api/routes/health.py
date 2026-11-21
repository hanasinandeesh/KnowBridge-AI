import logging
from fastapi import APIRouter, status
from fastapi.responses import JSONResponse

from app.core.config import settings
from app.core.database import check_db_connected, engine

router = APIRouter(tags=["health"])
logger = logging.getLogger("app.api.health")


@router.get(
    "/health",
    summary="Application Health Check",
    description="Returns current operational status of the FastAPI backend application.",
    status_code=status.HTTP_200_OK,
)
def get_application_health() -> dict:
    """Returns general application health and environment information."""
    return {
        "status": "healthy",
        "service": settings.PROJECT_NAME,
        "environment": settings.ENVIRONMENT,
    }


@router.get(
    "/health/db",
    summary="Database Connectivity Health Check",
    description="Executes a lightweight 'SELECT 1' query against Supabase PostgreSQL and returns connectivity status.",
)
def get_database_health():
    """
    Verifies live database connectivity using SQLAlchemy and psycopg.
    Returns 200 OK with query latency if healthy, or 503 Service Unavailable if disconnected.
    """
    is_healthy, message, latency_ms = check_db_connected()

    if is_healthy:
        dialect_name = engine.dialect.name if engine else "unknown"
        driver_name = engine.dialect.driver if engine else "unknown"
        return {
            "status": "healthy",
            "database": "connected",
            "latency_ms": latency_ms,
            "details": {
                "dialect": dialect_name,
                "driver": driver_name,
                "target": settings.masked_database_url,
            },
        }

    logger.warning("Database health check returning 503: %s", message)
    return JSONResponse(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        content={
            "status": "unhealthy",
            "database": "disconnected",
            "error": message,
            "latency_ms": latency_ms,
        },
    )
