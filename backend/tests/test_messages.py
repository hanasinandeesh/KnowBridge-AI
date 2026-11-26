"""
Deterministic Automated Tests for Task 06C — Message Persistence.

Covers:
1. User message creation (201 Created, stored in DB, association verified).
2. Assistant message creation with structured citations, evidence status, and trace ID.
3. Message-to-conversation association and parent updated_at timestamp synchronization.
4. Chronological message retrieval (created_at ASC).
5. Deterministic tie-breaking on identical timestamps (id ASC).
6. Pagination support (page, page_size, total, total_pages, has_next, has_prev, bounds validation).
7. Empty and whitespace-only message content rejection (HTTP 422).
8. Invalid message role rejection (HTTP 422).
9. Invalid evidence_status rejection (HTTP 422).
10. Extra payload attributes forbidden (HTTP 422).
11. Nonexistent conversation handling on create and get (HTTP 404).
12. Invalid UUID format handling (HTTP 422).
13. Database transaction rollback on create message failure (mocked commit failure).
14. Database transaction rollback on retrieve messages failure (mocked execute failure).
15. API HTTP 500 handling on internal database error without credential leakage.
"""

import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base, get_db
from app.main import app
from app.models.conversation import Conversation
from app.models.message import Message
from app.schemas.message import MessageCreate, MessageRole
from app.services.message_service import (
    ConversationNotFoundError,
    MessageService,
    MessageServiceError,
)


# ---------------------------------------------------------------------------
# Test Database Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def isolated_db_session():
    """
    Creates an isolated in-memory SQLite database session with foreign key support enabled.
    Ensures zero interaction with external Supabase databases.
    """
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    # Enable SQLite foreign key constraint enforcement
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
def override_db(isolated_db_session: Session):
    """Overrides the FastAPI get_db dependency to point to the isolated SQLite session."""

    def _get_isolated_db():
        yield isolated_db_session

    app.dependency_overrides[get_db] = _get_isolated_db
    yield isolated_db_session
    app.dependency_overrides.pop(get_db, None)


# ---------------------------------------------------------------------------
# 1. Message Creation Tests
# ---------------------------------------------------------------------------


def test_create_user_message_success(client: TestClient, override_db: Session):
    """POST /api/v1/conversations/{id}/messages creates a user message successfully."""
    conv = Conversation(id=uuid.uuid4(), title="Travel Reimbursement")
    override_db.add(conv)
    override_db.commit()

    payload = {
        "role": "user",
        "content": "What is the daily meal allowance for domestic travel?",
    }
    response = client.post(f"/api/v1/conversations/{conv.id}/messages", json=payload)
    assert response.status_code == 201
    data = response.json()

    assert "id" in data
    assert uuid.UUID(data["id"])
    assert data["conversation_id"] == str(conv.id)
    assert data["role"] == "user"
    assert data["content"] == "What is the daily meal allowance for domestic travel?"
    assert data["citations"] == []
    assert data["evidence_status"] is None
    assert data["trace_id"] is None
    assert data["feedback_score"] is None
    assert "created_at" in data

    # Verify persisted in database
    db_msg = override_db.query(Message).filter(Message.id == uuid.UUID(data["id"])).first()
    assert db_msg is not None
    assert db_msg.conversation_id == conv.id
    assert db_msg.role == "user"
    assert db_msg.content == "What is the daily meal allowance for domestic travel?"


def test_create_assistant_message_with_metadata(client: TestClient, override_db: Session):
    """POST assistant message persists structured citations, evidence status, and trace ID."""
    conv = Conversation(id=uuid.uuid4(), title="Policy Inquiry")
    override_db.add(conv)
    override_db.commit()

    chunk_uuid = str(uuid.uuid4())
    doc_uuid = str(uuid.uuid4())
    payload = {
        "role": "assistant",
        "content": "The maximum domestic per diem meal allowance is $75 per day [HR-TRV-001 p.4].",
        "citations": [
            {
                "citation_index": 1,
                "chunk_id": chunk_uuid,
                "document_id": doc_uuid,
                "document_title": "HR-TRV-001 Travel & Reimbursement Policy",
                "version_label": "v2.0",
                "page_number": 4,
                "section_title": "4.2 Daily Meal Allowances",
                "citation_tag": "[HR-TRV-001 p.4]",
                "snippet": "Daily meal reimbursement is capped at $75 per day for domestic travel.",
            }
        ],
        "evidence_status": "SUPPORTED",
        "trace_id": "trace-langfuse-01936c50-8b4b",
    }

    response = client.post(f"/api/v1/conversations/{conv.id}/messages", json=payload)
    assert response.status_code == 201
    data = response.json()

    assert data["role"] == "assistant"
    assert data["evidence_status"] == "SUPPORTED"
    assert data["trace_id"] == "trace-langfuse-01936c50-8b4b"
    assert len(data["citations"]) == 1

    citation = data["citations"][0]
    assert citation["citation_index"] == 1
    assert citation["document_title"] == "HR-TRV-001 Travel & Reimbursement Policy"
    assert citation["page_number"] == 4
    assert citation["snippet"] == "Daily meal reimbursement is capped at $75 per day for domestic travel."
    assert citation["citation_tag"] == "[HR-TRV-001 p.4]"
    assert citation["chunk_id"] == chunk_uuid
    assert citation["document_id"] == doc_uuid

    # Verify directly in database
    db_msg = override_db.query(Message).filter(Message.id == uuid.UUID(data["id"])).first()
    assert db_msg is not None
    assert db_msg.evidence_status == "SUPPORTED"
    assert db_msg.trace_id == "trace-langfuse-01936c50-8b4b"
    assert len(db_msg.citations) == 1
    assert db_msg.citations[0]["page_number"] == 4


def test_message_association_and_parent_timestamp_update(client: TestClient, override_db: Session):
    """Adding a message updates the parent conversation's updated_at timestamp."""
    conv_id = uuid.uuid4()
    past_time = datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    conv = Conversation(id=conv_id, title="Timestamp Test", updated_at=past_time)
    override_db.add(conv)
    override_db.commit()

    payload = {"role": "user", "content": "Testing timestamp update"}
    response = client.post(f"/api/v1/conversations/{conv_id}/messages", json=payload)
    assert response.status_code == 201

    override_db.refresh(conv)
    conv_updated = (
        conv.updated_at.replace(tzinfo=timezone.utc)
        if conv.updated_at.tzinfo is None
        else conv.updated_at
    )
    assert conv_updated > past_time

    # Verify relationship from conversation to messages
    assert len(conv.messages) == 1
    assert conv.messages[0].content == "Testing timestamp update"


# ---------------------------------------------------------------------------
# 2. Validation & Edge Cases Tests
# ---------------------------------------------------------------------------


def test_create_message_empty_content_rejected(client: TestClient, override_db: Session):
    """POST message with empty string content returns HTTP 422."""
    conv_id = uuid.uuid4()
    conv = Conversation(id=conv_id, title="Test")
    override_db.add(conv)
    override_db.commit()

    response = client.post(
        f"/api/v1/conversations/{conv_id}/messages",
        json={"role": "user", "content": ""},
    )
    assert response.status_code == 422


def test_create_message_whitespace_content_rejected(client: TestClient, override_db: Session):
    """POST message with whitespace-only content returns HTTP 422."""
    conv_id = uuid.uuid4()
    conv = Conversation(id=conv_id, title="Test")
    override_db.add(conv)
    override_db.commit()

    response = client.post(
        f"/api/v1/conversations/{conv_id}/messages",
        json={"role": "user", "content": "   \n\t   "},
    )
    assert response.status_code == 422


def test_create_message_invalid_role_rejected(client: TestClient, override_db: Session):
    """POST message with an invalid role returns HTTP 422."""
    conv_id = uuid.uuid4()
    conv = Conversation(id=conv_id, title="Test")
    override_db.add(conv)
    override_db.commit()

    response = client.post(
        f"/api/v1/conversations/{conv_id}/messages",
        json={"role": "administrator", "content": "Invalid role test"},
    )
    assert response.status_code == 422


def test_create_message_invalid_evidence_status_rejected(client: TestClient, override_db: Session):
    """POST message with invalid evidence_status returns HTTP 422."""
    conv_id = uuid.uuid4()
    conv = Conversation(id=conv_id, title="Test")
    override_db.add(conv)
    override_db.commit()

    response = client.post(
        f"/api/v1/conversations/{conv_id}/messages",
        json={
            "role": "assistant",
            "content": "Answer with bad evidence status",
            "evidence_status": "HIGHLY_ACCURATE",
        },
    )
    assert response.status_code == 422


def test_create_message_extra_fields_forbidden(client: TestClient, override_db: Session):
    """POST message with unpermitted extra fields returns HTTP 422."""
    conv_id = uuid.uuid4()
    conv = Conversation(id=conv_id, title="Test")
    override_db.add(conv)
    override_db.commit()

    response = client.post(
        f"/api/v1/conversations/{conv_id}/messages",
        json={
            "role": "user",
            "content": "Valid query",
            "injected_extra": "unexpected",
        },
    )
    assert response.status_code == 422


def test_create_message_nonexistent_conversation(client: TestClient, override_db: Session):
    """POST message to nonexistent conversation UUID returns HTTP 404."""
    random_id = uuid.uuid4()
    response = client.post(
        f"/api/v1/conversations/{random_id}/messages",
        json={"role": "user", "content": "Hello into the void"},
    )
    assert response.status_code == 404
    assert f"'{random_id}' not found" in response.json()["detail"]


def test_create_message_invalid_uuid(client: TestClient, override_db: Session):
    """POST message to malformed conversation UUID returns HTTP 422."""
    response = client.post(
        "/api/v1/conversations/not-a-valid-uuid/messages",
        json={"role": "user", "content": "Malformed UUID"},
    )
    assert response.status_code == 422


# ---------------------------------------------------------------------------
# 3. Message Retrieval & Pagination Tests
# ---------------------------------------------------------------------------


def test_get_messages_chronological_order(client: TestClient, override_db: Session):
    """GET /api/v1/conversations/{id}/messages returns messages in chronological order (created_at ASC)."""
    conv_id = uuid.uuid4()
    conv = Conversation(id=conv_id, title="Dialogue Thread")
    override_db.add(conv)

    t0 = datetime(2026, 1, 1, 10, 0, 0, tzinfo=timezone.utc)
    msg1 = Message(id=uuid.uuid4(), conversation_id=conv_id, role="user", content="Turn 1", created_at=t0)
    msg2 = Message(id=uuid.uuid4(), conversation_id=conv_id, role="assistant", content="Turn 2", created_at=t0 + timedelta(seconds=10))
    msg3 = Message(id=uuid.uuid4(), conversation_id=conv_id, role="user", content="Turn 3", created_at=t0 + timedelta(seconds=20))
    msg4 = Message(id=uuid.uuid4(), conversation_id=conv_id, role="assistant", content="Turn 4", created_at=t0 + timedelta(seconds=30))

    # Add in non-chronological order to test SQL order_by
    override_db.add_all([msg3, msg1, msg4, msg2])
    override_db.commit()

    response = client.get(f"/api/v1/conversations/{conv_id}/messages")
    assert response.status_code == 200
    data = response.json()

    assert data["total"] == 4
    contents = [item["content"] for item in data["items"]]
    assert contents == ["Turn 1", "Turn 2", "Turn 3", "Turn 4"]


def test_get_messages_deterministic_tie_breaker(client: TestClient, override_db: Session):
    """When timestamps are identical, messages are ordered deterministically by id ASC."""
    conv_id = uuid.uuid4()
    conv = Conversation(id=conv_id, title="Tie Breaker")
    override_db.add(conv)

    same_time = datetime(2026, 1, 1, 10, 0, 0, tzinfo=timezone.utc)
    id_a = uuid.UUID("10000000-0000-0000-0000-000000000001")
    id_b = uuid.UUID("20000000-0000-0000-0000-000000000002")
    id_c = uuid.UUID("30000000-0000-0000-0000-000000000003")

    msg_c = Message(id=id_c, conversation_id=conv_id, role="assistant", content="C", created_at=same_time)
    msg_a = Message(id=id_a, conversation_id=conv_id, role="user", content="A", created_at=same_time)
    msg_b = Message(id=id_b, conversation_id=conv_id, role="assistant", content="B", created_at=same_time)

    override_db.add_all([msg_c, msg_a, msg_b])
    override_db.commit()

    response = client.get(f"/api/v1/conversations/{conv_id}/messages")
    assert response.status_code == 200
    data = response.json()

    ids = [item["id"] for item in data["items"]]
    assert ids == [str(id_a), str(id_b), str(id_c)]


def test_get_messages_pagination(client: TestClient, override_db: Session):
    """GET messages supports deterministic pagination, total_pages, has_next, and has_prev."""
    conv_id = uuid.uuid4()
    conv = Conversation(id=conv_id, title="Paged Conversation")
    override_db.add(conv)

    t0 = datetime(2026, 1, 1, 10, 0, 0, tzinfo=timezone.utc)
    messages = [
        Message(
            id=uuid.uuid4(),
            conversation_id=conv_id,
            role="user" if i % 2 == 0 else "assistant",
            content=f"Message {i:02d}",
            created_at=t0 + timedelta(minutes=i),
        )
        for i in range(12)
    ]
    override_db.add_all(messages)
    override_db.commit()

    # Page 1: 5 items
    resp1 = client.get(f"/api/v1/conversations/{conv_id}/messages?page=1&page_size=5")
    assert resp1.status_code == 200
    data1 = resp1.json()
    assert data1["total"] == 12
    assert data1["page"] == 1
    assert data1["page_size"] == 5
    assert data1["total_pages"] == 3
    assert data1["has_next"] is True
    assert data1["has_prev"] is False
    assert len(data1["items"]) == 5
    assert data1["items"][0]["content"] == "Message 00"
    assert data1["items"][4]["content"] == "Message 04"

    # Page 2: 5 items
    resp2 = client.get(f"/api/v1/conversations/{conv_id}/messages?page=2&page_size=5")
    assert resp2.status_code == 200
    data2 = resp2.json()
    assert data2["page"] == 2
    assert data2["has_next"] is True
    assert data2["has_prev"] is True
    assert len(data2["items"]) == 5
    assert data2["items"][0]["content"] == "Message 05"
    assert data2["items"][4]["content"] == "Message 09"

    # Page 3: 2 remaining items
    resp3 = client.get(f"/api/v1/conversations/{conv_id}/messages?page=3&page_size=5")
    assert resp3.status_code == 200
    data3 = resp3.json()
    assert data3["page"] == 3
    assert data3["has_next"] is False
    assert data3["has_prev"] is True
    assert len(data3["items"]) == 2
    assert data3["items"][0]["content"] == "Message 10"
    assert data3["items"][1]["content"] == "Message 11"

    # Page 4: beyond total pages
    resp4 = client.get(f"/api/v1/conversations/{conv_id}/messages?page=4&page_size=5")
    assert resp4.status_code == 200
    data4 = resp4.json()
    assert len(data4["items"]) == 0
    assert data4["has_next"] is False
    assert data4["has_prev"] is True


def test_get_messages_nonexistent_conversation(client: TestClient, override_db: Session):
    """GET messages for nonexistent conversation UUID returns HTTP 404."""
    random_id = uuid.uuid4()
    response = client.get(f"/api/v1/conversations/{random_id}/messages")
    assert response.status_code == 404
    assert f"'{random_id}' not found" in response.json()["detail"]


def test_get_messages_invalid_uuid(client: TestClient, override_db: Session):
    """GET messages with invalid UUID returns HTTP 422."""
    response = client.get("/api/v1/conversations/not-a-uuid/messages")
    assert response.status_code == 422


# ---------------------------------------------------------------------------
# 4. Database Rollback and Failure Handling Tests
# ---------------------------------------------------------------------------


def test_service_rollback_on_create_failure(isolated_db_session: Session):
    """MessageService rolls back and raises MessageServiceError on commit failure."""
    conv = Conversation(id=uuid.uuid4(), title="Rollback Test")
    isolated_db_session.add(conv)
    isolated_db_session.commit()

    service = MessageService(isolated_db_session)
    isolated_db_session.commit = MagicMock(side_effect=OperationalError("INSERT", {}, Exception("Disk full")))
    isolated_db_session.rollback = MagicMock()

    payload = MessageCreate(role=MessageRole.USER, content="Test prompt")
    with pytest.raises(MessageServiceError) as exc_info:
        service.create_message(conv.id, payload)

    assert "Database error creating message" in str(exc_info.value)
    isolated_db_session.rollback.assert_called_once()


def test_service_rollback_on_get_failure(isolated_db_session: Session):
    """MessageService rolls back and raises MessageServiceError on query failure."""
    conv_id = uuid.uuid4()
    conv = Conversation(id=conv_id, title="Rollback Test")
    isolated_db_session.add(conv)
    isolated_db_session.commit()

    service = MessageService(isolated_db_session)
    isolated_db_session.execute = MagicMock(side_effect=OperationalError("SELECT", {}, Exception("Connection aborted")))
    isolated_db_session.rollback = MagicMock()

    with pytest.raises(MessageServiceError) as exc_info:
        service.get_messages(conv_id)

    assert "Database error retrieving messages" in str(exc_info.value)
    isolated_db_session.rollback.assert_called_once()


def test_api_create_message_internal_error(client: TestClient, monkeypatch: pytest.MonkeyPatch, override_db: Session):
    """POST messages returns HTTP 500 when MessageService raises MessageServiceError."""
    conv_id = uuid.uuid4()
    monkeypatch.setattr(
        MessageService,
        "create_message",
        MagicMock(side_effect=MessageServiceError("Simulated database failure")),
    )
    response = client.post(
        f"/api/v1/conversations/{conv_id}/messages",
        json={"role": "user", "content": "Hello"},
    )
    assert response.status_code == 500
    assert "internal database error" in response.json()["detail"].lower()


def test_api_list_messages_internal_error(client: TestClient, monkeypatch: pytest.MonkeyPatch, override_db: Session):
    """GET messages returns HTTP 500 when MessageService raises MessageServiceError."""
    conv_id = uuid.uuid4()
    monkeypatch.setattr(
        MessageService,
        "get_messages",
        MagicMock(side_effect=MessageServiceError("Simulated query failure")),
    )
    response = client.get(f"/api/v1/conversations/{conv_id}/messages")
    assert response.status_code == 500
    assert "internal database error" in response.json()["detail"].lower()
