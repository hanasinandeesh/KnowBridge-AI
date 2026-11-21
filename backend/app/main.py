import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes.documents import router as documents_router
from app.api.routes.health import router as health_router
from app.core.config import settings
from app.core.database import check_db_connected, close_db_connection

# Configure root application logging
logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] [%(levelname)s] [%(name)s]: %(message)s",
)
logger = logging.getLogger("app.main")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application connection lifecycle manager.
    Initializes database pool on startup and gracefully disposes connections on shutdown.
    """
    logger.info("Starting up %s (Environment: %s)", settings.PROJECT_NAME, settings.ENVIRONMENT)
    logger.info("Database Target: %s", settings.masked_database_url)

    # Non-blocking connectivity verification on startup (skip in test environment)
    if os.getenv("TESTING") == "1":
        logger.info("TESTING=1 detected: skipping startup database network check.")
    else:
        is_connected, msg, latency = check_db_connected()
        if is_connected:
            logger.info("Database connection established successfully (%sms)", latency)
        else:
            logger.warning(
                "Initial database connection check did not succeed: %s. Application running in degraded state.",
                msg,
            )

    yield

    # Clean shutdown of database pool
    logger.info("Shutting down %s...", settings.PROJECT_NAME)
    close_db_connection()
    logger.info("Shutdown complete.")


app = FastAPI(
    title=settings.PROJECT_NAME,
    version="1.0.0",
    description="KnowBridge AI — Policy-Aware Enterprise Knowledge Intelligence Platform Backend",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

# Enable CORS for local and web development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount health routes directly at root for GET /health and GET /health/db
app.include_router(health_router)

# Also mount under /api/v1 for API versioning consistency
app.include_router(health_router, prefix=settings.API_V1_STR)
app.include_router(documents_router, prefix=f"{settings.API_V1_STR}/documents")


@app.get("/", tags=["root"])
def root() -> dict:
    """Root entrypoint returning basic service information."""
    return {
        "service": settings.PROJECT_NAME,
        "status": "online",
        "docs": "/docs",
        "health": "/health",
        "health_db": "/health/db",
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
