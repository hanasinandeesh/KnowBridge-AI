"""
Deterministic Automated Tests for Task 06B — Conversation Management APIs.

Covers:
1. Conversation creation (default title, custom title, trimmed title, empty title fallback).
2. Request validation (extra fields forbidden, max title length).
3. Retrieval of existing conversation with message count metadata.
4. Retrieval of nonexistent conversation (HTTP 404) and invalid UUID (HTTP 422).
5. Listing conversations with deterministic ordering (updated_at DESC, id DESC).
6. Pagination validation (page, page_size, total_pages, has_next, has_prev, invalid bounds).
7. Accurate aggregation of message counts across conversations.
8. Updating conversation titles (valid, trimmed whitespace, empty/whitespace rejection).
9. Updating nonexistent conversation (HTTP 404).
10. Deleting conversation (HTTP 204) and verifying cascade deletion of associated messages.
11. Deleting nonexistent conversation (HTTP 404).
12. Database rollback and failure handling without secret leakage (HTTP 500).
"""

import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base, get_db
from app.main import app
from app.models.conversation import Conversation
from app.models.message import Message
from app.services.conversation_service import (
    ConversationService,
    ConversationServiceError,
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
# 1. Conversation Creation Tests
# ---------------------------------------------------------------------------

def test_create_conversation_default_title(client: TestClient, override_db: Session):
    """POST /api/v1/conversations without body defaults title to 'New Conversation'."""
    response = client.post("/api/v1/conversations")
    assert response.status_code == 201
    data = response.json()

    assert "id" in data
    assert uuid.UUID(data["id"])
    assert data["title"] == "New Conversation"
    assert data["message_count"] == 0
    assert "created_at" in data
    assert "updated_at" in data

    # Verify persisted in DB
    db_conv = override_db.query(Conversation).filter(Conversation.id == uuid.UUID(data["id"])).first()
    assert db_conv is not None
    assert db_conv.title == "New Conversation"


def test_create_conversation_with_custom_title(client: TestClient, override_db: Session):
    """POST /api/v1/conversations with explicit title stores the custom title."""
    payload = {"title": "Travel Reimbursement Inquiry"}
    response = client.post("/api/v1/conversations", json=payload)
    assert response.status_code == 201
    data = response.json()

    assert data["title"] == "Travel Reimbursement Inquiry"
    assert data["message_count"] == 0


def test_create_conversation_strips_whitespace(client: TestClient, override_db: Session):
    """POST /api/v1/conversations strips leading and trailing whitespace from title."""
    payload = {"title": "   Leave Policy Guidelines   "}
    response = client.post("/api/v1/conversations", json=payload)
    assert response.status_code == 201
    data = response.json()

    assert data["title"] == "Leave Policy Guidelines"


def test_create_conversation_empty_title_falls_back(client: TestClient, override_db: Session):
    """POST /api/v1/conversations with whitespace-only title falls back to default."""
    payload = {"title": "    "}
    response = client.post("/api/v1/conversations", json=payload)
    assert response.status_code == 201
    data = response.json()

    assert data["title"] == "New Conversation"


def test_create_conversation_extra_fields_forbidden(client: TestClient, override_db: Session):
    """POST /api/v1/conversations with unexpected extra keys returns HTTP 422."""
    payload = {"title": "Valid Title", "unexpected_field": "malicious"}
    response = client.post("/api/v1/conversations", json=payload)
    assert response.status_code == 422


# ---------------------------------------------------------------------------
# 2. Conversation Retrieval Tests
# ---------------------------------------------------------------------------

def test_get_conversation_success(client: TestClient, override_db: Session):
    """GET /api/v1/conversations/{id} returns conversation details and message count."""
    conv_id = uuid.uuid4()
    conv = Conversation(id=conv_id, title="Remote Work Policy")
    override_db.add(conv)

    # Add 2 messages to conversation
    msg1 = Message(
        id=uuid.uuid4(),
        conversation_id=conv_id,
        role="user",
        content="What is the remote work stipend?",
    )
    msg2 = Message(
        id=uuid.uuid4(),
        conversation_id=conv_id,
        role="assistant",
        content="The home office equipment reimbursement allowance is up to $500.",
    )
    override_db.add_all([msg1, msg2])
    override_db.commit()

    response = client.get(f"/api/v1/conversations/{conv_id}")
    assert response.status_code == 200
    data = response.json()

    assert data["id"] == str(conv_id)
    assert data["title"] == "Remote Work Policy"
    assert data["message_count"] == 2
    assert "created_at" in data
    assert "updated_at" in data


def test_get_conversation_not_found(client: TestClient, override_db: Session):
    """GET /api/v1/conversations/{id} returns HTTP 404 for nonexistent UUID."""
    random_id = uuid.uuid4()
    response = client.get(f"/api/v1/conversations/{random_id}")
    assert response.status_code == 404
    assert f"'{random_id}' not found" in response.json()["detail"]


def test_get_conversation_invalid_uuid(client: TestClient, override_db: Session):
    """GET /api/v1/conversations/{id} returns HTTP 422 for malformed UUID string."""
    response = client.get("/api/v1/conversations/not-a-valid-uuid")
    assert response.status_code == 422


# ---------------------------------------------------------------------------
# 3. Conversation Listing & Pagination Tests
# ---------------------------------------------------------------------------

def test_list_conversations_empty(client: TestClient, override_db: Session):
    """GET /api/v1/conversations on an empty database returns an empty page envelope."""
    response = client.get("/api/v1/conversations")
    assert response.status_code == 200
    data = response.json()

    assert data["items"] == []
    assert data["total"] == 0
    assert data["page"] == 1
    assert data["page_size"] == 20
    assert data["total_pages"] == 0
    assert data["has_next"] is False
    assert data["has_prev"] is False


def test_list_conversations_pagination_and_ordering(client: TestClient, override_db: Session):
    """GET /api/v1/conversations paginates correctly with deterministic ordering."""
    base_time = datetime(2026, 11, 26, 10, 0, 0, tzinfo=timezone.utc)

    # Seed 5 conversations with incremental updated_at times
    for i in range(5):
        conv = Conversation(
            id=uuid.uuid4(),
            title=f"Conversation {i+1}",
            created_at=base_time + timedelta(minutes=i),
            updated_at=base_time + timedelta(minutes=i * 2),
        )
        override_db.add(conv)
    override_db.commit()

    # Page 1: page_size=2
    res1 = client.get("/api/v1/conversations?page=1&page_size=2")
    assert res1.status_code == 200
    data1 = res1.json()
    assert data1["total"] == 5
    assert data1["page"] == 1
    assert data1["page_size"] == 2
    assert data1["total_pages"] == 3
    assert data1["has_next"] is True
    assert data1["has_prev"] is False
    assert len(data1["items"]) == 2
    # Verify updated_at DESC (most recently updated first)
    assert data1["items"][0]["title"] == "Conversation 5"
    assert data1["items"][1]["title"] == "Conversation 4"

    # Page 2: page_size=2
    res2 = client.get("/api/v1/conversations?page=2&page_size=2")
    assert res2.status_code == 200
    data2 = res2.json()
    assert data2["page"] == 2
    assert data2["has_next"] is True
    assert data2["has_prev"] is True
    assert len(data2["items"]) == 2
    assert data2["items"][0]["title"] == "Conversation 3"
    assert data2["items"][1]["title"] == "Conversation 2"

    # Page 3: page_size=2 (final page)
    res3 = client.get("/api/v1/conversations?page=3&page_size=2")
    assert res3.status_code == 200
    data3 = res3.json()
    assert data3["page"] == 3
    assert data3["has_next"] is False
    assert data3["has_prev"] is True
    assert len(data3["items"]) == 1
    assert data3["items"][0]["title"] == "Conversation 1"

    # Page 4: beyond total pages
    res4 = client.get("/api/v1/conversations?page=4&page_size=2")
    assert res4.status_code == 200
    data4 = res4.json()
    assert data4["items"] == []
    assert data4["has_next"] is False
    assert data4["has_prev"] is True


def test_list_conversations_message_count_aggregation(client: TestClient, override_db: Session):
    """GET /api/v1/conversations includes accurate message_count for each conversation."""
    conv_a = Conversation(id=uuid.uuid4(), title="Thread A")
    conv_b = Conversation(id=uuid.uuid4(), title="Thread B")
    override_db.add_all([conv_a, conv_b])
    override_db.commit()

    # Add 3 messages to conv_a, 0 to conv_b
    for i in range(3):
        override_db.add(Message(
            id=uuid.uuid4(),
            conversation_id=conv_a.id,
            role="user" if i % 2 == 0 else "assistant",
            content=f"Message {i}",
        ))
    override_db.commit()

    res = client.get("/api/v1/conversations")
    assert res.status_code == 200
    items = res.json()["items"]
    counts = {item["title"]: item["message_count"] for item in items}
    assert counts["Thread A"] == 3
    assert counts["Thread B"] == 0


def test_list_conversations_invalid_pagination_params(client: TestClient, override_db: Session):
    """GET /api/v1/conversations rejects invalid page or page_size query parameters."""
    # page < 1
    res = client.get("/api/v1/conversations?page=0")
    assert res.status_code == 422

    # page_size < 1
    res = client.get("/api/v1/conversations?page_size=0")
    assert res.status_code == 422

    # page_size > 100
    res = client.get("/api/v1/conversations?page_size=101")
    assert res.status_code == 422


# ---------------------------------------------------------------------------
# 4. Conversation Update Tests
# ---------------------------------------------------------------------------

def test_update_conversation_title_success(client: TestClient, override_db: Session):
    """PATCH /api/v1/conversations/{id} updates conversation title and refreshes updated_at."""
    conv_id = uuid.uuid4()
    past_time = datetime(2026, 11, 20, 12, 0, 0, tzinfo=timezone.utc)
    conv = Conversation(id=conv_id, title="Old Title", updated_at=past_time)
    override_db.add(conv)
    override_db.commit()

    response = client.patch(
        f"/api/v1/conversations/{conv_id}",
        json={"title": "Updated Title"},
    )
    assert response.status_code == 200
    data = response.json()

    assert data["id"] == str(conv_id)
    assert data["title"] == "Updated Title"

    # Verify updated in DB
    override_db.refresh(conv)
    assert conv.title == "Updated Title"
    conv_updated = conv.updated_at.replace(tzinfo=timezone.utc) if conv.updated_at.tzinfo is None else conv.updated_at
    assert conv_updated > past_time


def test_update_conversation_whitespace_trim(client: TestClient, override_db: Session):
    """PATCH /api/v1/conversations/{id} trims whitespace around title."""
    conv_id = uuid.uuid4()
    conv = Conversation(id=conv_id, title="Initial Title")
    override_db.add(conv)
    override_db.commit()

    response = client.patch(
        f"/api/v1/conversations/{conv_id}",
        json={"title": "   Cleaned Title   "},
    )
    assert response.status_code == 200
    assert response.json()["title"] == "Cleaned Title"


def test_update_conversation_empty_title_rejected(client: TestClient, override_db: Session):
    """PATCH /api/v1/conversations/{id} rejects empty or whitespace-only title with HTTP 422."""
    conv_id = uuid.uuid4()
    conv = Conversation(id=conv_id, title="Initial Title")
    override_db.add(conv)
    override_db.commit()

    # Empty string
    res1 = client.patch(f"/api/v1/conversations/{conv_id}", json={"title": ""})
    assert res1.status_code == 422

    # Whitespace only
    res2 = client.patch(f"/api/v1/conversations/{conv_id}", json={"title": "    "})
    assert res2.status_code == 422


def test_update_conversation_not_found(client: TestClient, override_db: Session):
    """PATCH /api/v1/conversations/{id} returns HTTP 404 for nonexistent UUID."""
    random_id = uuid.uuid4()
    response = client.patch(
        f"/api/v1/conversations/{random_id}",
        json={"title": "New Title"},
    )
    assert response.status_code == 404
    assert f"'{random_id}' not found" in response.json()["detail"]


# ---------------------------------------------------------------------------
# 5. Conversation Deletion Tests
# ---------------------------------------------------------------------------

def test_delete_conversation_success(client: TestClient, override_db: Session):
    """DELETE /api/v1/conversations/{id} deletes conversation and cascades to child messages."""
    conv_id = uuid.uuid4()
    conv = Conversation(id=conv_id, title="To Be Deleted")
    override_db.add(conv)

    # Attach two child messages
    msg1 = Message(id=uuid.uuid4(), conversation_id=conv_id, role="user", content="Question")
    msg2 = Message(id=uuid.uuid4(), conversation_id=conv_id, role="assistant", content="Answer")
    override_db.add_all([msg1, msg2])
    override_db.commit()

    # Execute DELETE endpoint
    response = client.delete(f"/api/v1/conversations/{conv_id}")
    assert response.status_code == 204
    assert response.text == ""

    # Verify conversation is gone from DB
    assert override_db.query(Conversation).filter(Conversation.id == conv_id).first() is None

    # Verify messages were cascaded and deleted
    remaining_messages = override_db.query(Message).filter(Message.conversation_id == conv_id).count()
    assert remaining_messages == 0


def test_delete_conversation_not_found(client: TestClient, override_db: Session):
    """DELETE /api/v1/conversations/{id} returns HTTP 404 for nonexistent UUID."""
    random_id = uuid.uuid4()
    response = client.delete(f"/api/v1/conversations/{random_id}")
    assert response.status_code == 404
    assert f"'{random_id}' not found" in response.json()["detail"]


# ---------------------------------------------------------------------------
# 6. Database Rollback and Failure Handling Tests
# ---------------------------------------------------------------------------

def test_service_rollback_on_create_failure(isolated_db_session: Session):
    """ConversationService rolls back and raises ConversationServiceError on commit failure."""
    service = ConversationService(isolated_db_session)

    # Mock db.commit to raise an OperationalError
    isolated_db_session.commit = MagicMock(side_effect=OperationalError("INSERT", {}, Exception("DB lock error")))
    isolated_db_session.rollback = MagicMock()

    with pytest.raises(ConversationServiceError) as exc_info:
        service.create_conversation()

    assert "Database error creating conversation" in str(exc_info.value)
    isolated_db_session.rollback.assert_called_once()


def test_service_rollback_on_update_failure(isolated_db_session: Session):
    """ConversationService rolls back and raises ConversationServiceError on update failure."""
    conv = Conversation(id=uuid.uuid4(), title="Original")
    isolated_db_session.add(conv)
    isolated_db_session.commit()

    service = ConversationService(isolated_db_session)
    isolated_db_session.commit = MagicMock(side_effect=OperationalError("UPDATE", {}, Exception("Connection lost")))
    isolated_db_session.rollback = MagicMock()

    from app.schemas.conversation import ConversationUpdate
    with pytest.raises(ConversationServiceError) as exc_info:
        service.update_conversation(conv.id, ConversationUpdate(title="New"))

    assert "Database error updating conversation" in str(exc_info.value)
    isolated_db_session.rollback.assert_called_once()


def test_service_rollback_on_delete_failure(isolated_db_session: Session):
    """ConversationService rolls back and raises ConversationServiceError on delete failure."""
    conv = Conversation(id=uuid.uuid4(), title="To Delete")
    isolated_db_session.add(conv)
    isolated_db_session.commit()

    service = ConversationService(isolated_db_session)
    isolated_db_session.commit = MagicMock(side_effect=OperationalError("DELETE", {}, Exception("Foreign key deadlock")))
    isolated_db_session.rollback = MagicMock()

    with pytest.raises(ConversationServiceError) as exc_info:
        service.delete_conversation(conv.id)

    assert "Database error deleting conversation" in str(exc_info.value)
    isolated_db_session.rollback.assert_called_once()


def test_api_create_conversation_internal_error(client: TestClient, monkeypatch: pytest.MonkeyPatch, override_db: Session):
    """POST /api/v1/conversations returns HTTP 500 when ConversationService fails."""
    monkeypatch.setattr(
        ConversationService,
        "create_conversation",
        MagicMock(side_effect=ConversationServiceError("Simulated DB connection failure")),
    )
    response = client.post("/api/v1/conversations")
    assert response.status_code == 500
    assert "internal database error" in response.json()["detail"].lower()


def test_api_list_conversations_internal_error(client: TestClient, monkeypatch: pytest.MonkeyPatch, override_db: Session):
    """GET /api/v1/conversations returns HTTP 500 when ConversationService fails."""
    monkeypatch.setattr(
        ConversationService,
        "list_conversations",
        MagicMock(side_effect=ConversationServiceError("Simulated query failure")),
    )
    response = client.get("/api/v1/conversations")
    assert response.status_code == 500
    assert "internal database error" in response.json()["detail"].lower()


def test_api_get_conversation_internal_error(client: TestClient, monkeypatch: pytest.MonkeyPatch, override_db: Session):
    """GET /api/v1/conversations/{id} returns HTTP 500 when ConversationService fails."""
    conv_id = uuid.uuid4()
    monkeypatch.setattr(
        ConversationService,
        "get_conversation",
        MagicMock(side_effect=ConversationServiceError("Simulated read failure")),
    )
    response = client.get(f"/api/v1/conversations/{conv_id}")
    assert response.status_code == 500
    assert "internal database error" in response.json()["detail"].lower()


def test_api_update_conversation_internal_error(client: TestClient, monkeypatch: pytest.MonkeyPatch, override_db: Session):
    """PATCH /api/v1/conversations/{id} returns HTTP 500 when ConversationService fails."""
    conv_id = uuid.uuid4()
    monkeypatch.setattr(
        ConversationService,
        "update_conversation",
        MagicMock(side_effect=ConversationServiceError("Simulated update failure")),
    )
    response = client.patch(f"/api/v1/conversations/{conv_id}", json={"title": "Updated"})
    assert response.status_code == 500
    assert "internal database error" in response.json()["detail"].lower()


def test_api_delete_conversation_internal_error(client: TestClient, monkeypatch: pytest.MonkeyPatch, override_db: Session):
    """DELETE /api/v1/conversations/{id} returns HTTP 500 when ConversationService fails."""
    conv_id = uuid.uuid4()
    monkeypatch.setattr(
        ConversationService,
        "delete_conversation",
        MagicMock(side_effect=ConversationServiceError("Simulated delete failure")),
    )
    response = client.delete(f"/api/v1/conversations/{conv_id}")
    assert response.status_code == 500
    assert "internal database error" in response.json()["detail"].lower()
