"""API routes package."""
from app.api.routes.chat import (
    feedback_router,
    router as chat_router,
)
from app.api.routes.conversations import router as conversations_router
from app.api.routes.documents import router as documents_router
from app.api.routes.health import router as health_router
from app.api.routes.ingestion import router as ingestion_router
from app.api.routes.memories import router as memories_router

__all__ = [
    "chat_router",
    "feedback_router",
    "conversations_router",
    "documents_router",
    "health_router",
    "ingestion_router",
    "memories_router",
]
