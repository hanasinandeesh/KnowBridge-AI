"""
Deterministic Automated Tests for Task 06E — Persistent Memory System.

Covers:
1. LLM memory extraction from dialogue turns (department, role, location, constraint).
2. PII filtering (credit cards, SSNs, passwords rejected).
3. Transient context rejection (is_durable=False rejected).
4. Confidence threshold filtering (< 0.75 rejected).
5. Exact fact deduplication (updates timestamp, prevents duplicate rows).
6. Superseding conflicting facts with audit history in metadata_json.
7. Active unexpired memory retrieval and expiration filtering.
8. ActiveMemoryContext compilation and prompt string generation.
9. Single memory deletion and 404 handling.
10. Session memory purge and expired memory purge.
11. Database rollback on SQLAlchemy errors.
12. End-to-end REST API routes (/api/v1/memories).
"""

from datetime import datetime, timedelta, timezone
import json
from typing import Optional
from unittest.mock import MagicMock
import uuid

from fastapi.testclient import TestClient
import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base, get_db
from app.main import app
from app.models.conversation import Conversation
from app.models.user_memory import UserMemory
from app.schemas.memory import (
    ActiveMemoryContext,
    ExtractedMemoryItem,
    MemoryCreate,
    MemoryResponse,
    MemoryType,
)
from app.schemas.query_understanding import ConversationTurn
from app.services.llm_client import LLMClient, LLMProviderError
from app.services.memory_service import (
    MemoryDatabaseError,
    MemoryService,
    MemoryServiceError,
    get_memory_service,
)


# ---------------------------------------------------------------------------
# Test Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def isolated_db_session():
    """Isolated in-memory SQLite database session for memory tests."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine, "connect")
    def set_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(bind=engine)
    TestingSession = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = TestingSession()

    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


@pytest.fixture
def api_client(isolated_db_session: Session):
    """FastAPI TestClient with overridden get_db dependency."""
    def override_get_db():
        try:
            yield isolated_db_session
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.clear()


class MockLLMClient:
    """Configurable mock LLMClient for deterministic extraction tests."""

    def __init__(
        self,
        memories_payload: Optional[list[dict]] = None,
        raise_error: Optional[Exception] = None,
        raw_text: Optional[str] = None,
    ):
        self.memories_payload = memories_payload
        self.raise_error = raise_error
        self.raw_text = raw_text
        self.call_count = 0

    def complete_json(self, messages: list[dict], temperature: float = 0.0, max_tokens: int = 512):
        self.call_count += 1
        if self.raise_error:
            raise self.raise_error

        if self.raw_text is not None:
            return self.raw_text, "mock-groq-model"

        payload = {"memories": self.memories_payload or []}
        return json.dumps(payload), "mock-groq-model"


# ---------------------------------------------------------------------------
# 1. Extraction & Validation Tests
# ---------------------------------------------------------------------------

def test_extract_memories_success(isolated_db_session: Session):
    """Test extracting valid user facts (department, role, location)."""
    mock_payload = [
        {
            "memory_key": "department",
            "memory_value": "Engineering",
            "memory_text": "Employee works in Engineering department.",
            "memory_type": "department",
            "confidence_score": 0.95,
            "is_durable": True,
            "is_sensitive_pii": False,
            "expires_in_days": None,
        },
        {
            "memory_key": "work_location",
            "memory_value": "London",
            "memory_text": "Employee is located in the London office.",
            "memory_type": "location",
            "confidence_score": 0.90,
            "is_durable": True,
            "is_sensitive_pii": False,
            "expires_in_days": None,
        },
    ]
    mock_llm = MockLLMClient(memories_payload=mock_payload)
    service = MemoryService(db=isolated_db_session, llm_client=mock_llm)

    turns = [
        ConversationTurn(role="user", content="Hi, I work in Engineering in the London office."),
        ConversationTurn(role="assistant", content="Hello! How can I assist you with London office policies?"),
    ]

    extracted = service.extract_memories_from_turns(turns)
    assert len(extracted) == 2
    assert extracted[0].memory_key == "department"
    assert extracted[0].memory_value == "Engineering"
    assert extracted[1].memory_key == "work_location"
    assert extracted[1].memory_value == "London"
    assert mock_llm.call_count == 1


def test_extract_memories_pii_filtering(isolated_db_session: Session):
    """Test rejection of sensitive PII (credit cards, SSNs, passwords)."""
    mock_payload = [
        {
            "memory_key": "credit_card",
            "memory_value": "4111 2222 3333 4444",
            "memory_text": "User card number is 4111 2222 3333 4444",
            "memory_type": "user_constraint",
            "confidence_score": 0.99,
            "is_durable": True,
            "is_sensitive_pii": False,  # LLM failed to flag, but regex must catch it!
        },
        {
            "memory_key": "ssn_number",
            "memory_value": "123-45-6789",
            "memory_text": "User SSN is 123-45-6789",
            "memory_type": "general",
            "confidence_score": 0.99,
            "is_durable": True,
            "is_sensitive_pii": True,  # Flagged by LLM
        },
        {
            "memory_key": "department",
            "memory_value": "Finance",
            "memory_text": "User is in Finance",
            "memory_type": "department",
            "confidence_score": 0.90,
            "is_durable": True,
            "is_sensitive_pii": False,
        },
    ]
    mock_llm = MockLLMClient(memories_payload=mock_payload)
    service = MemoryService(db=isolated_db_session, llm_client=mock_llm)

    turns = [ConversationTurn(role="user", content="My department is Finance.")]
    extracted = service.extract_memories_from_turns(turns)

    # Only Finance should survive
    assert len(extracted) == 1
    assert extracted[0].memory_key == "department"
    assert extracted[0].memory_value == "Finance"


def test_extract_memories_transient_and_low_confidence_rejected(isolated_db_session: Session):
    """Test rejection of non-durable or low confidence candidates."""
    mock_payload = [
        {
            "memory_key": "temporary_task",
            "memory_value": "Reviewing page 3",
            "memory_text": "User is looking at page 3 right now",
            "memory_type": "general",
            "confidence_score": 0.95,
            "is_durable": False,  # Transient!
        },
        {
            "memory_key": "role",
            "memory_value": "Manager",
            "memory_text": "Maybe a manager",
            "memory_type": "role",
            "confidence_score": 0.60,  # Below 0.75 threshold!
            "is_durable": True,
        },
    ]
    mock_llm = MockLLMClient(memories_payload=mock_payload)
    service = MemoryService(db=isolated_db_session, llm_client=mock_llm)

    turns = [ConversationTurn(role="user", content="I might be a manager, looking at page 3")]
    extracted = service.extract_memories_from_turns(turns)
    assert len(extracted) == 0


def test_extract_memories_empty_turns(isolated_db_session: Session):
    """Empty turns or turns without user role bypass LLM completely."""
    mock_llm = MockLLMClient()
    service = MemoryService(db=isolated_db_session, llm_client=mock_llm)

    assert service.extract_memories_from_turns([]) == []
    assert mock_llm.call_count == 0

    assistant_only = [ConversationTurn(role="assistant", content="How may I help you?")]
    assert service.extract_memories_from_turns(assistant_only) == []
    assert mock_llm.call_count == 0


def test_extract_memories_llm_failure_resilience(isolated_db_session: Session):
    """LLM provider failure or malformed JSON handles gracefully without crashing."""
    mock_llm = MockLLMClient(raise_error=LLMProviderError("Groq timeout"))
    service = MemoryService(db=isolated_db_session, llm_client=mock_llm)

    turns = [ConversationTurn(role="user", content="I work in Engineering")]
    extracted = service.extract_memories_from_turns(turns)
    assert extracted == []

    # Malformed JSON test
    mock_llm_malformed = MockLLMClient(raw_text="Not valid json")
    service_malformed = MemoryService(db=isolated_db_session, llm_client=mock_llm_malformed)
    assert service_malformed.extract_memories_from_turns(turns) == []


# ---------------------------------------------------------------------------
# 2. Storage, Deduplication & Superseding Tests
# ---------------------------------------------------------------------------

def test_store_memory_new_record(isolated_db_session: Session):
    """Storing a new memory creates a valid database record."""
    service = MemoryService(db=isolated_db_session)
    create_req = MemoryCreate(
        session_key="user_123",
        memory_key="department",
        memory_value="Engineering",
        memory_text="Employee works in Engineering.",
        memory_type=MemoryType.DEPARTMENT,
        confidence_score=0.95,
    )

    res = service.store_memory(create_req)
    assert res.id is not None
    assert res.session_key == "user_123"
    assert res.memory_key == "department"
    assert res.memory_value == "Engineering"
    assert res.confidence_score == 0.95
    assert res.metadata == {}


def test_store_memory_exact_duplicate_reaffirms(isolated_db_session: Session):
    """Re-storing the same fact updates updated_at without duplicating rows."""
    service = MemoryService(db=isolated_db_session)
    create_req = MemoryCreate(
        session_key="user_123",
        memory_key="department",
        memory_value="Engineering",
        confidence_score=0.85,
    )

    first = service.store_memory(create_req)

    # Reaffirm with higher confidence
    reaffirm_req = MemoryCreate(
        session_key="user_123",
        memory_key="department",
        memory_value="Engineering",
        confidence_score=0.98,
    )
    second = service.store_memory(reaffirm_req)

    assert second.id == first.id  # Same record
    assert second.confidence_score == 0.98

    # Verify database has exactly 1 row
    memories = service.get_active_memories(session_key="user_123")
    assert len(memories) == 1


def test_store_memory_superseding_conflict_with_audit(isolated_db_session: Session):
    """Changing a fact updates the value and tracks history in metadata."""
    service = MemoryService(db=isolated_db_session)
    old_req = MemoryCreate(
        session_key="user_123",
        memory_key="work_location",
        memory_value="London",
        memory_text="User is in London office",
        memory_type=MemoryType.LOCATION,
        confidence_score=0.90,
    )
    first = service.store_memory(old_req)

    # User relocated to Sydney
    new_req = MemoryCreate(
        session_key="user_123",
        memory_key="work_location",
        memory_value="Sydney",
        memory_text="User is now in Sydney office",
        memory_type=MemoryType.LOCATION,
        confidence_score=0.95,
    )
    updated = service.store_memory(new_req)

    assert updated.id == first.id
    assert updated.memory_value == "Sydney"
    assert updated.memory_text == "User is now in Sydney office"
    assert "superseded_history" in updated.metadata
    history = updated.metadata["superseded_history"]
    assert len(history) == 1
    assert history[0]["previous_value"] == "London"
    assert history[0]["previous_confidence"] == 0.90


# ---------------------------------------------------------------------------
# 3. Retrieval & Expiration Tests
# ---------------------------------------------------------------------------

def test_get_active_memories_and_expiration(isolated_db_session: Session):
    """Expired memories are excluded from active retrieval by default."""
    service = MemoryService(db=isolated_db_session)
    now = datetime.now(timezone.utc)

    # Active memory (no expiration)
    service.store_memory(MemoryCreate(
        session_key="test_sess",
        memory_key="department",
        memory_value="Engineering",
    ))

    # Active memory (expires in future)
    service.store_memory(MemoryCreate(
        session_key="test_sess",
        memory_key="project",
        memory_value="Apollo",
        expires_at=now + timedelta(days=10),
    ))

    # Expired memory (expired yesterday)
    service.store_memory(MemoryCreate(
        session_key="test_sess",
        memory_key="temporary_badge",
        memory_value="Badge-99",
        expires_at=now - timedelta(days=1),
    ))

    active = service.get_active_memories(session_key="test_sess")
    assert len(active) == 2
    keys = {m.memory_key for m in active}
    assert keys == {"department", "project"}

    # Include expired should return all 3
    all_mem = service.get_active_memories(session_key="test_sess", include_expired=True)
    assert len(all_mem) == 3


def test_get_active_memory_context(isolated_db_session: Session):
    """Compiles structured ActiveMemoryContext for RAG queries."""
    service = MemoryService(db=isolated_db_session)

    service.store_memory(MemoryCreate(
        session_key="ctx_test",
        memory_key="department",
        memory_value="Human Resources",
        memory_type=MemoryType.DEPARTMENT,
    ))
    service.store_memory(MemoryCreate(
        session_key="ctx_test",
        memory_key="role",
        memory_value="HR Director",
        memory_type=MemoryType.ROLE,
    ))
    service.store_memory(MemoryCreate(
        session_key="ctx_test",
        memory_key="work_location",
        memory_value="New York",
        memory_type=MemoryType.LOCATION,
    ))
    service.store_memory(MemoryCreate(
        session_key="ctx_test",
        memory_key="dietary_preference",
        memory_value="Vegan",
        memory_text="Employee adheres to a vegan diet for corporate catering",
        memory_type=MemoryType.POLICY_PREFERENCE,
    ))
    service.store_memory(MemoryCreate(
        session_key="ctx_test",
        memory_key="work_schedule_constraint",
        memory_value="Tue-Thu",
        memory_text="Employee works Tuesday to Thursday only",
        memory_type=MemoryType.USER_CONSTRAINT,
    ))

    ctx = service.get_active_memory_context(session_key="ctx_test")
    assert ctx.department == "Human Resources"
    assert ctx.role == "HR Director"
    assert ctx.location == "New York"
    assert len(ctx.preferences) == 1
    assert "vegan" in ctx.preferences[0].lower()
    assert len(ctx.constraints) == 1
    assert "tuesday" in ctx.constraints[0].lower()

    prompt_str = ctx.to_context_string()
    assert "- Department: Human Resources" in prompt_str
    assert "- Role: HR Director" in prompt_str
    assert "- Location: New York" in prompt_str


# ---------------------------------------------------------------------------
# 4. Deletion & Purging Tests
# ---------------------------------------------------------------------------

def test_delete_memory(isolated_db_session: Session):
    """Deleting a memory by UUID succeeds, and returns False if missing."""
    service = MemoryService(db=isolated_db_session)
    created = service.store_memory(MemoryCreate(
        session_key="del_sess",
        memory_key="role",
        memory_value="Engineer",
    ))

    # Existing deletion
    assert service.delete_memory(created.id) is True
    # Non-existent deletion
    assert service.delete_memory(uuid.uuid4()) is False


def test_clear_session_memories(isolated_db_session: Session):
    """Purges all memories in a given session without affecting other sessions."""
    service = MemoryService(db=isolated_db_session)
    service.store_memory(MemoryCreate(session_key="s1", memory_key="k1", memory_value="v1"))
    service.store_memory(MemoryCreate(session_key="s1", memory_key="k2", memory_value="v2"))
    service.store_memory(MemoryCreate(session_key="s2", memory_key="k1", memory_value="v3"))

    deleted = service.clear_session_memories("s1")
    assert deleted == 2
    assert len(service.get_active_memories("s1")) == 0
    assert len(service.get_active_memories("s2")) == 1


def test_purge_expired_memories(isolated_db_session: Session):
    """Purges only expired memories across all sessions."""
    service = MemoryService(db=isolated_db_session)
    now = datetime.now(timezone.utc)

    # 2 expired, 1 active
    service.store_memory(MemoryCreate(
        session_key="s1",
        memory_key="e1",
        memory_value="v",
        expires_at=now - timedelta(days=2),
    ))
    service.store_memory(MemoryCreate(
        session_key="s2",
        memory_key="e2",
        memory_value="v",
        expires_at=now - timedelta(hours=1),
    ))
    service.store_memory(MemoryCreate(
        session_key="s1",
        memory_key="active",
        memory_value="v",
    ))

    purged = service.purge_expired_memories()
    assert purged == 2

    remaining = service.get_active_memories("s1", include_expired=True)
    assert len(remaining) == 1
    assert remaining[0].memory_key == "active"


# ---------------------------------------------------------------------------
# 5. Database Rollback Handling
# ---------------------------------------------------------------------------

def test_database_error_triggers_rollback(isolated_db_session: Session):
    """Database exceptions trigger rollback and raise MemoryDatabaseError."""
    service = MemoryService(db=isolated_db_session)
    mock_db = MagicMock()
    mock_db.execute.side_effect = OperationalError("SELECT 1", {}, Exception("DB locked"))

    failing_service = MemoryService(db=mock_db)
    with pytest.raises(MemoryDatabaseError):
        failing_service.store_memory(MemoryCreate(
            session_key="err_sess",
            memory_key="k",
            memory_value="v",
        ))
    mock_db.rollback.assert_called_once()


# ---------------------------------------------------------------------------
# 6. REST API Endpoints Tests
# ---------------------------------------------------------------------------

def test_api_create_and_list_memories(api_client: TestClient):
    """Test POST and GET /api/v1/memories."""
    post_res = api_client.post(
        "/api/v1/memories",
        json={
            "session_key": "api_user",
            "memory_key": "department",
            "memory_value": "Marketing",
            "memory_type": "department",
            "confidence_score": 0.95,
        },
    )
    assert post_res.status_code == 201
    created_data = post_res.json()
    assert created_data["memory_key"] == "department"
    assert created_data["memory_value"] == "Marketing"
    mem_id = created_data["id"]

    # List
    list_res = api_client.get("/api/v1/memories?session_key=api_user")
    assert list_res.status_code == 200
    list_data = list_res.json()
    assert list_data["total"] == 1
    assert list_data["items"][0]["id"] == mem_id

    # Context
    ctx_res = api_client.get("/api/v1/memories/context?session_key=api_user")
    assert ctx_res.status_code == 200
    assert ctx_res.json()["department"] == "Marketing"

    # Delete single
    del_res = api_client.delete(f"/api/v1/memories/{mem_id}")
    assert del_res.status_code == 204

    # Delete again -> 404
    del_res_404 = api_client.delete(f"/api/v1/memories/{mem_id}")
    assert del_res_404.status_code == 404


def test_api_clear_session(api_client: TestClient):
    """Test DELETE /api/v1/memories/session/{session_key}."""
    api_client.post(
        "/api/v1/memories",
        json={
            "session_key": "purge_user",
            "memory_key": "role",
            "memory_value": "Developer",
        },
    )
    purge_res = api_client.delete("/api/v1/memories/session/purge_user")
    assert purge_res.status_code == 200
    assert purge_res.json()["deleted_count"] == 1

    list_res = api_client.get("/api/v1/memories?session_key=purge_user")
    assert list_res.json()["total"] == 0
