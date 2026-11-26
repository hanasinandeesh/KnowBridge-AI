"""
Deterministic Automated Tests for Task 06D — Conversation History & Context Builder.

Covers:
1. Empty conversation history deterministic bypass (zero LLM calls).
2. No conversation ID provided (standalone resolution without DB lookup).
3. Normal follow-up question resolution (e.g., annual leave carry-forward).
4. Pronoun resolution from context (e.g., "Does it apply to personal devices?").
5. Unrelated new question detection without context contamination.
6. Ambiguous follow-up requiring clarification.
7. Context window bounding and chronological ordering (oldest to newest).
8. Missing conversation handling (ConversationNotFoundError).
9. Preservation of original question verbatim.
10. Anti-hallucination / no unsupported policy facts introduced.
11. LLM timeout and provider failure graceful fallback.
12. LLM malformed JSON graceful fallback.
13. Seamless compatibility with Task 05A QueryUnderstandingRequest.
14. Database session absence validation when conversation_id is requested.
15. Empty/whitespace query validation.
"""

import json
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional
from unittest.mock import MagicMock

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base
from app.models.conversation import Conversation
from app.models.message import Message
from app.schemas.context_builder import ContextBuilderRequest, ContextBuilderResult
from app.schemas.query_understanding import ConversationTurn, QueryUnderstandingRequest
from app.services.context_builder_service import (
    ContextBuilderError,
    ContextBuilderService,
    InvalidContextBuilderInputError,
)
from app.services.llm_client import LLMClient, LLMProviderError
from app.services.message_service import ConversationNotFoundError


# ---------------------------------------------------------------------------
# Test Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def isolated_db_session():
    """Isolated in-memory SQLite database session for context builder tests."""
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


class MockLLMClient:
    """Configurable mock LLMClient for deterministic context resolution tests."""

    def __init__(self, response_payload: Optional[dict] = None, raise_error: Optional[Exception] = None):
        self.response_payload = response_payload or {
            "standalone_query": "Resolved standalone query",
            "is_follow_up": True,
            "requires_clarification": False,
            "clarification_reason": None,
        }
        self.raise_error = raise_error
        self.call_count = 0
        self.last_messages = None

    @property
    def default_model(self) -> str:
        return "mock-resolver-model"

    def complete_json(self, messages, *, model=None, temperature=0.0, max_tokens=512):
        self.call_count += 1
        self.last_messages = messages
        if self.raise_error:
            raise self.raise_error
        return json.dumps(self.response_payload), "mock-resolver-model"


# ---------------------------------------------------------------------------
# 1. Deterministic Bypass & Basic Tests
# ---------------------------------------------------------------------------


def test_empty_conversation_history_deterministic(isolated_db_session: Session):
    """Empty conversation history skips LLM and returns standalone_query == original_query."""
    conv_id = uuid.uuid4()
    conv = Conversation(id=conv_id, title="Empty Conversation")
    isolated_db_session.add(conv)
    isolated_db_session.commit()

    mock_llm = MockLLMClient()
    service = ContextBuilderService(db=isolated_db_session, llm_client=mock_llm)

    result = service.build_context(
        ContextBuilderRequest(
            query="What is the travel meal allowance?",
            conversation_id=conv_id,
        )
    )

    assert result.original_query == "What is the travel meal allowance?"
    assert result.standalone_query == "What is the travel meal allowance?"
    assert result.history_message_count == 0
    assert result.conversation_history == []
    assert result.is_follow_up is False
    assert result.requires_clarification is False
    assert result.model_used is None
    assert mock_llm.call_count == 0  # Zero LLM calls!


def test_no_conversation_id_provided():
    """When conversation_id is None, returns standalone_query == original_query without DB lookup."""
    mock_llm = MockLLMClient()
    service = ContextBuilderService(db=None, llm_client=mock_llm)

    result = service.build_context(
        ContextBuilderRequest(
            query="What is the remote work equipment stipend?",
            conversation_id=None,
        )
    )

    assert result.original_query == "What is the remote work equipment stipend?"
    assert result.standalone_query == "What is the remote work equipment stipend?"
    assert result.history_message_count == 0
    assert result.model_used is None
    assert mock_llm.call_count == 0


def test_raw_query_string_input():
    """ContextBuilderService accepts a raw string query directly."""
    service = ContextBuilderService(db=None, llm_client=MockLLMClient())
    result = service.build_context("How do I submit an expense report?")

    assert result.original_query == "How do I submit an expense report?"
    assert result.standalone_query == "How do I submit an expense report?"
    assert result.is_follow_up is False


def test_empty_query_string_validation():
    """Empty or whitespace-only query raises InvalidContextBuilderInputError."""
    service = ContextBuilderService()
    with pytest.raises(InvalidContextBuilderInputError):
        service.build_context("   \n\t   ")


# ---------------------------------------------------------------------------
# 2. Contextual Follow-up Resolution Tests
# ---------------------------------------------------------------------------


def test_normal_follow_up_resolution(isolated_db_session: Session):
    """Normal follow-up question resolves using conversation context while preserving original query."""
    conv_id = uuid.uuid4()
    conv = Conversation(id=conv_id, title="Leave Policy")
    isolated_db_session.add(conv)

    t0 = datetime(2026, 11, 26, 10, 0, 0, tzinfo=timezone.utc)
    msg1 = Message(
        id=uuid.uuid4(),
        conversation_id=conv_id,
        role="user",
        content="What is the annual leave policy?",
        created_at=t0,
    )
    msg2 = Message(
        id=uuid.uuid4(),
        conversation_id=conv_id,
        role="assistant",
        content="Full-time employees receive 20 days of paid annual leave per year.",
        created_at=t0 + timedelta(seconds=5),
    )
    isolated_db_session.add_all([msg1, msg2])
    isolated_db_session.commit()

    mock_llm = MockLLMClient(
        response_payload={
            "standalone_query": "What does the annual leave policy say about carrying forward unused annual leave?",
            "is_follow_up": True,
            "requires_clarification": False,
            "clarification_reason": None,
        }
    )
    service = ContextBuilderService(db=isolated_db_session, llm_client=mock_llm)

    result = service.build_context(
        ContextBuilderRequest(
            query="How many can I carry forward?",
            conversation_id=conv_id,
        )
    )

    assert result.original_query == "How many can I carry forward?"
    assert result.standalone_query == "What does the annual leave policy say about carrying forward unused annual leave?"
    assert result.history_message_count == 2
    assert result.is_follow_up is True
    assert result.requires_clarification is False
    assert result.model_used == "mock-resolver-model"
    assert mock_llm.call_count == 1


def test_pronoun_resolution(isolated_db_session: Session):
    """Resolves pronoun 'it' against the active policy entity in history."""
    conv_id = uuid.uuid4()
    conv = Conversation(id=conv_id, title="Security Policy")
    isolated_db_session.add(conv)

    msg1 = Message(id=uuid.uuid4(), conversation_id=conv_id, role="user", content="What is IT-SEC-001 Information Security Policy?")
    msg2 = Message(id=uuid.uuid4(), conversation_id=conv_id, role="assistant", content="IT-SEC-001 defines data handling, encryption, and password requirements.")
    isolated_db_session.add_all([msg1, msg2])
    isolated_db_session.commit()

    mock_llm = MockLLMClient(
        response_payload={
            "standalone_query": "Does IT-SEC-001 Information Security Policy apply to personal mobile devices?",
            "is_follow_up": True,
            "requires_clarification": False,
            "clarification_reason": None,
        }
    )
    service = ContextBuilderService(db=isolated_db_session, llm_client=mock_llm)

    result = service.build_context(
        ContextBuilderRequest(
            query="Does it apply to personal mobile devices?",
            conversation_id=conv_id,
        )
    )

    assert result.original_query == "Does it apply to personal mobile devices?"
    assert "IT-SEC-001 Information Security Policy" in result.standalone_query
    assert result.is_follow_up is True


def test_unrelated_new_question_not_contaminated(isolated_db_session: Session):
    """When employee switches topic, the standalone query does not inject prior context."""
    conv_id = uuid.uuid4()
    conv = Conversation(id=conv_id, title="Travel")
    isolated_db_session.add(conv)

    msg1 = Message(id=uuid.uuid4(), conversation_id=conv_id, role="user", content="What is the domestic hotel reimbursement limit?")
    msg2 = Message(id=uuid.uuid4(), conversation_id=conv_id, role="assistant", content="The standard hotel allowance is $250 per night.")
    isolated_db_session.add_all([msg1, msg2])
    isolated_db_session.commit()

    mock_llm = MockLLMClient(
        response_payload={
            "standalone_query": "What is the parental leave policy duration?",
            "is_follow_up": False,
            "requires_clarification": False,
            "clarification_reason": None,
        }
    )
    service = ContextBuilderService(db=isolated_db_session, llm_client=mock_llm)

    result = service.build_context(
        ContextBuilderRequest(
            query="What is the parental leave policy duration?",
            conversation_id=conv_id,
        )
    )

    assert result.original_query == "What is the parental leave policy duration?"
    assert result.standalone_query == "What is the parental leave policy duration?"
    assert result.is_follow_up is False


def test_ambiguous_follow_up_requires_clarification(isolated_db_session: Session):
    """Ambiguous follow-up that cannot be resolved sets requires_clarification=True."""
    conv_id = uuid.uuid4()
    conv = Conversation(id=conv_id, title="Multi-Topic Thread")
    isolated_db_session.add(conv)

    msg1 = Message(id=uuid.uuid4(), conversation_id=conv_id, role="user", content="Tell me about travel reimbursement and remote work.")
    msg2 = Message(id=uuid.uuid4(), conversation_id=conv_id, role="assistant", content="Travel reimbursement covers meals and hotels, while remote work provides equipment stipends.")
    isolated_db_session.add_all([msg1, msg2])
    isolated_db_session.commit()

    mock_llm = MockLLMClient(
        response_payload={
            "standalone_query": "Can you explain that again?",
            "is_follow_up": True,
            "requires_clarification": True,
            "clarification_reason": "Reference 'that' is ambiguous as both travel reimbursement and remote work policies were discussed.",
        }
    )
    service = ContextBuilderService(db=isolated_db_session, llm_client=mock_llm)

    result = service.build_context(
        ContextBuilderRequest(
            query="Can you explain that again?",
            conversation_id=conv_id,
        )
    )

    assert result.requires_clarification is True
    assert "ambiguous" in result.clarification_reason.lower()


# ---------------------------------------------------------------------------
# 3. Context Window Bounding & Ordering Tests
# ---------------------------------------------------------------------------


def test_context_window_bounded_and_chronological(isolated_db_session: Session):
    """Context window selects bounded tail of recent messages and returns them chronologically."""
    conv_id = uuid.uuid4()
    conv = Conversation(id=conv_id, title="Long Conversation")
    isolated_db_session.add(conv)

    base_time = datetime(2026, 11, 26, 10, 0, 0, tzinfo=timezone.utc)
    messages = []
    for i in range(12):
        role = "user" if i % 2 == 0 else "assistant"
        msg = Message(
            id=uuid.uuid4(),
            conversation_id=conv_id,
            role=role,
            content=f"Message {i:02d}",
            created_at=base_time + timedelta(minutes=i),
        )
        messages.append(msg)
    isolated_db_session.add_all(messages)
    isolated_db_session.commit()

    mock_llm = MockLLMClient()
    service = ContextBuilderService(db=isolated_db_session, llm_client=mock_llm)

    # Request window of 4 turns
    result = service.build_context(
        ContextBuilderRequest(
            query="Follow-up question",
            conversation_id=conv_id,
            max_history_turns=4,
        )
    )

    assert result.history_message_count == 4
    assert len(result.conversation_history) == 4

    # Verify chronological order (oldest to newest among the last 4)
    expected_contents = ["Message 08", "Message 09", "Message 10", "Message 11"]
    actual_contents = [turn.content for turn in result.conversation_history]
    assert actual_contents == expected_contents


def test_system_messages_filtered_from_history(isolated_db_session: Session):
    """System role messages are excluded from history passed to LLM."""
    conv_id = uuid.uuid4()
    conv = Conversation(id=conv_id, title="System Filter Test")
    isolated_db_session.add(conv)

    t0 = datetime(2026, 11, 26, 10, 0, 0, tzinfo=timezone.utc)
    m_sys = Message(id=uuid.uuid4(), conversation_id=conv_id, role="system", content="System instruction", created_at=t0)
    m_user = Message(id=uuid.uuid4(), conversation_id=conv_id, role="user", content="User prompt", created_at=t0 + timedelta(seconds=1))
    m_asst = Message(id=uuid.uuid4(), conversation_id=conv_id, role="assistant", content="Assistant reply", created_at=t0 + timedelta(seconds=2))
    isolated_db_session.add_all([m_sys, m_user, m_asst])
    isolated_db_session.commit()

    mock_llm = MockLLMClient()
    service = ContextBuilderService(db=isolated_db_session, llm_client=mock_llm)

    history = service.load_history(conv_id, max_turns=6)
    assert len(history) == 2
    assert all(turn.role in ["user", "assistant"] for turn in history)


# ---------------------------------------------------------------------------
# 4. Error Handling & Fallback Tests
# ---------------------------------------------------------------------------


def test_missing_conversation_raises_404(isolated_db_session: Session):
    """Requesting nonexistent conversation ID raises ConversationNotFoundError."""
    random_id = uuid.uuid4()
    service = ContextBuilderService(db=isolated_db_session, llm_client=MockLLMClient())

    with pytest.raises(ConversationNotFoundError) as exc_info:
        service.build_context(
            ContextBuilderRequest(
                query="Any question",
                conversation_id=random_id,
            )
        )
    assert f"'{random_id}' not found" in str(exc_info.value)


def test_no_database_provided_raises_error_if_conv_id_requested():
    """ContextBuilderService without db raises ContextBuilderError if conversation_id is passed."""
    service = ContextBuilderService(db=None, llm_client=MockLLMClient())
    with pytest.raises(ContextBuilderError) as exc_info:
        service.build_context(
            ContextBuilderRequest(
                query="Any question",
                conversation_id=uuid.uuid4(),
            )
        )
    assert "Database session is required" in str(exc_info.value)


def test_llm_provider_failure_graceful_fallback(isolated_db_session: Session):
    """LLM provider failure falls back gracefully to original query without crashing."""
    conv_id = uuid.uuid4()
    conv = Conversation(id=conv_id, title="Failure Test")
    isolated_db_session.add(conv)

    msg = Message(id=uuid.uuid4(), conversation_id=conv_id, role="user", content="Hello")
    isolated_db_session.add(msg)
    isolated_db_session.commit()

    mock_llm = MockLLMClient(raise_error=LLMProviderError("Groq upstream connection timeout"))
    service = ContextBuilderService(db=isolated_db_session, llm_client=mock_llm)

    result = service.build_context(
        ContextBuilderRequest(
            query="How many days?",
            conversation_id=conv_id,
        )
    )

    assert result.original_query == "How many days?"
    assert result.standalone_query == "How many days?"  # Safe fallback
    assert result.is_follow_up is False
    assert result.model_used == "fallback-original"


def test_llm_malformed_json_graceful_fallback(isolated_db_session: Session):
    """Malformed LLM JSON output falls back gracefully to original query."""
    conv_id = uuid.uuid4()
    conv = Conversation(id=conv_id, title="Malformed Test")
    isolated_db_session.add(conv)

    msg = Message(id=uuid.uuid4(), conversation_id=conv_id, role="user", content="Hello")
    isolated_db_session.add(msg)
    isolated_db_session.commit()

    mock_llm = MagicMock()
    mock_llm.complete_json.return_value = ("Non-JSON error response from LLM", "mock-model")
    service = ContextBuilderService(db=isolated_db_session, llm_client=mock_llm)

    result = service.build_context(
        ContextBuilderRequest(
            query="Can I carry over?",
            conversation_id=conv_id,
        )
    )

    assert result.original_query == "Can I carry over?"
    assert result.standalone_query == "Can I carry over?"
    assert result.model_used == "fallback-original"


# ---------------------------------------------------------------------------
# 5. Integration with Task 05A Query Understanding
# ---------------------------------------------------------------------------


def test_compatibility_with_task_05a_request():
    """ContextBuilderResult converts cleanly into Task 05A QueryUnderstandingRequest."""
    history_turns = [
        ConversationTurn(role="user", content="What is the travel meal allowance?"),
        ConversationTurn(role="assistant", content="The domestic meal allowance is $75 per day."),
    ]

    result = ContextBuilderResult(
        original_query="What about international?",
        standalone_query="What is the travel meal allowance for international travel?",
        conversation_id=uuid.uuid4(),
        history_message_count=2,
        conversation_history=history_turns,
        is_follow_up=True,
        requires_clarification=False,
    )

    qu_req = result.to_query_understanding_request()
    assert isinstance(qu_req, QueryUnderstandingRequest)
    assert qu_req.query == "What is the travel meal allowance for international travel?"
    assert len(qu_req.conversation_history) == 2
    assert qu_req.conversation_history[0].role == "user"
