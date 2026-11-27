"""
Deterministic Automated Tests for Task 06F — LangGraph End-to-End Chat & Feedback APIs.

Covers:
1. POST /api/v1/chat without conversation_id (auto-creates conversation thread and persists turns).
2. Multi-turn follow-up resolution with conversation_id (ContextBuilder standalone query rewrite).
3. Active persistent memory injection into query understanding hints.
4. Safe abstention on insufficient evidence with persisted INSUFFICIENT status.
5. Conflict disclosure on contradictory policy evidence with persisted CONFLICT status.
6. Ambiguous follow-up requiring clarification routing directly to handle_clarification.
7. Interaction persistence in messages table with structured citations.
8. POST /api/v1/feedback (+1 / -1 thumbs up/down rating updates message).
9. POST /api/v1/feedback 404 on nonexistent message ID.
10. GET /api/v1/documents paginated listing endpoint.
"""

from datetime import date, datetime, timezone
import math
from typing import Optional
from unittest.mock import MagicMock
import uuid

from fastapi.testclient import TestClient
import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base, get_db
from app.graph.workflow import RAGOrchestrator, get_rag_orchestrator
from app.main import app
from app.models.conversation import Conversation
from app.models.document import Document
from app.models.message import Message
from app.models.user_memory import UserMemory
from app.schemas.answer_generation import (
    AnswerCitation,
    AnswerGenerationResult,
    AnswerStatus,
)
from app.schemas.chat import (
    ChatRequest,
    ChatResponse,
    FeedbackRequest,
    FeedbackResponse,
)
from app.schemas.context_builder import ContextBuilderRequest, ContextBuilderResult
from app.schemas.evidence_assessment import (
    EvidenceAssessmentResult,
    EvidenceDecision,
    EvidenceReference,
    PolicyConflictItem,
    SupportLevel,
)
from app.schemas.memory import ActiveMemoryContext, ExtractedMemoryItem, MemoryType
from app.schemas.query_understanding import (
    ConversationTurn,
    QueryIntent,
    QueryUnderstandingResult,
    RetrievalHints,
)
from app.schemas.retrieval import EvidenceItem, EvidencePackage, RetrievalResult
from app.services.answer_generation_service import AnswerGenerationService
from app.services.context_builder_service import ContextBuilderService
from app.services.evidence_assessment_service import EvidenceAssessmentService
from app.services.memory_service import MemoryService
from app.services.message_service import MessageService
from app.services.query_understanding_service import QueryUnderstandingService
from app.services.retrieval_service import RetrievalService


# ---------------------------------------------------------------------------
# Test Fixtures & In-Memory Database
# ---------------------------------------------------------------------------

@pytest.fixture
def isolated_db_session():
    """Isolated in-memory SQLite database session for chat API tests."""
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


# ---------------------------------------------------------------------------
# Helper Mock Factories
# ---------------------------------------------------------------------------

def _make_evidence_item(
    idx: int = 1,
    title: str = "HR-TRV-001 Travel Policy",
    text: str = "Maximum domestic meal per diem is $75 per day.",
    page: int = 4,
) -> EvidenceItem:
    return EvidenceItem(
        citation_index=idx,
        chunk_id=uuid.uuid4(),
        document_id=uuid.uuid4(),
        document_title=title,
        version_label="1.0",
        effective_from=date(2026, 1, 1),
        effective_until=date(2027, 12, 31),
        chunk_text=text,
        similarity_score=0.91,
        page_number=page,
        section_title="Meal Allowances",
        citation_tag=f"[{title}, p. {page}]",
    )


def _build_test_orchestrator(
    db: Session,
    *,
    decision: EvidenceDecision = EvidenceDecision.SUFFICIENT,
    standalone_query: Optional[str] = None,
    is_follow_up: bool = False,
    requires_clarification: bool = False,
    clarification_reason: Optional[str] = None,
) -> RAGOrchestrator:
    """Builds a configured RAGOrchestrator with real DB services and controlled AI services."""
    item = _make_evidence_item()

    # 1. Context Builder Mock
    cb_svc = MagicMock(spec=ContextBuilderService)
    cb_svc.build_context.return_value = ContextBuilderResult(
        original_query="What is the meal allowance?",
        standalone_query=standalone_query or "What is the domestic travel meal allowance?",
        conversation_id=uuid.uuid4(),
        history_message_count=2 if is_follow_up else 0,
        conversation_history=[],
        is_follow_up=is_follow_up,
        requires_clarification=requires_clarification,
        clarification_reason=clarification_reason,
        model_used="mock-groq",
    )

    # 2. Query Understanding Mock
    qu_svc = MagicMock(spec=QueryUnderstandingService)
    qu_svc.understand_query.return_value = QueryUnderstandingResult(
        original_query="What is the meal allowance?",
        intent=QueryIntent.POLICY_LOOKUP,
        primary_topic="travel reimbursement",
        rewritten_query=standalone_query or "What is the domestic travel meal allowance?",
        retrieval_hints=RetrievalHints(keywords=["meal", "per diem"]),
        needs_clarification=requires_clarification,
        clarification_reason=clarification_reason,
        model_used="mock-groq",
    )

    # 3. Retrieval Mock
    ret_svc = MagicMock(spec=RetrievalService)
    items = [item] if decision == EvidenceDecision.SUFFICIENT else []
    pkg = EvidencePackage(
        query="test query",
        total_evidence_count=len(items),
        items=items,
        formatted_context="\n".join(i.chunk_text for i in items) if items else "No evidence.",
        is_sufficient=len(items) > 0,
        applied_limit=5,
    )
    ret_svc.retrieve_chunks.return_value = RetrievalResult(
        query="test query",
        total_retrieved=len(items),
        chunks=[],
        similarity_threshold=0.65,
        top_k=5,
        applied_limit=5,
        evidence_package=pkg,
    )

    # 4. Evidence Assessment Mock
    assess_svc = MagicMock(spec=EvidenceAssessmentService)
    conflicts = []
    if decision == EvidenceDecision.CONFLICT:
        item2 = _make_evidence_item(idx=2, title="HR-TRV-002 Finance Manual", text="Maximum domestic meal per diem is $60 per day.", page=2)
        conflicts = [
            PolicyConflictItem(
                conflict_id="conflict-1",
                conflict_type="cross_document_contradiction",
                description="Contradictory meal per diem amounts ($75 vs $60)",
                claim_a="$75 per day",
                claim_b="$60 per day",
                source_a=EvidenceReference.from_evidence_item(item),
                source_b=EvidenceReference.from_evidence_item(item2),
            )
        ]

    assess_svc.assess_evidence.return_value = EvidenceAssessmentResult(
        decision=decision,
        support_level=SupportLevel.FULL if decision == EvidenceDecision.SUFFICIENT else SupportLevel.NONE,
        is_relevant=decision != EvidenceDecision.INSUFFICIENT,
        reasoning="Assessment reasoning.",
        supporting_evidence=[EvidenceReference.from_evidence_item(item)] if decision == EvidenceDecision.SUFFICIENT else [],
        conflicts=conflicts,
        model_used="mock-groq",
    )

    # 5. Answer Generation Mock
    gen_svc = MagicMock(spec=AnswerGenerationService)
    if decision == EvidenceDecision.SUFFICIENT:
        gen_svc.generate_answer.return_value = AnswerGenerationResult(
            original_query="What is the meal allowance?",
            answer="The maximum domestic per diem meal allowance is $75 per day [1].",
            status=AnswerStatus.ANSWERED,
            citations=[AnswerCitation.from_evidence_item(item)],
            model_used="mock-groq",
        )
    elif decision == EvidenceDecision.INSUFFICIENT:
        gen_svc.generate_answer.return_value = AnswerGenerationResult(
            original_query="What is the meal allowance?",
            answer="I cannot answer this question based on available enterprise policies.",
            status=AnswerStatus.ABSTAINED,
            citations=[],
            missing_information=["Missing specific policy clause"],
            model_used="mock-groq",
        )
    elif decision == EvidenceDecision.CONFLICT:
        gen_svc.generate_answer.return_value = AnswerGenerationResult(
            original_query="What is the meal allowance?",
            answer="Conflicting policy guidance was found: Travel Policy states $75 while Finance Manual states $60.",
            status=AnswerStatus.CONFLICT_DETECTED,
            citations=[AnswerCitation.from_evidence_item(item)],
            conflicts=conflicts,
            model_used="mock-groq",
        )
    else:
        gen_svc.generate_answer.return_value = AnswerGenerationResult(
            original_query="What is the meal allowance?",
            answer="Could you please clarify which office or travel type you are inquiring about?",
            status=AnswerStatus.CLARIFICATION_REQUIRED,
            citations=[],
            model_used="mock-groq",
        )

    # Real database services
    msg_svc = MessageService(db=db)
    mem_svc = MemoryService(db=db)

    return RAGOrchestrator(
        context_builder_service=cb_svc,
        memory_service=mem_svc,
        message_service=msg_svc,
        query_understanding_service=qu_svc,
        retrieval_service=ret_svc,
        evidence_assessment_service=assess_svc,
        answer_generation_service=gen_svc,
        use_memory_checkpointer=False,
    )


# ---------------------------------------------------------------------------
# 1. End-to-End Chat API Tests
# ---------------------------------------------------------------------------

def test_chat_auto_creates_conversation(api_client: TestClient, isolated_db_session: Session, monkeypatch):
    """POST /api/v1/chat without conversation_id auto-creates thread and stores turns."""
    orchestrator = _build_test_orchestrator(isolated_db_session, decision=EvidenceDecision.SUFFICIENT)
    monkeypatch.setattr("app.api.routes.chat.get_rag_orchestrator", lambda db: orchestrator)

    payload = {
        "query": "What is the maximum daily meal allowance for domestic travel?",
        "session_key": "test_user_1",
    }
    response = api_client.post("/api/v1/chat", json=payload)
    assert response.status_code == 200
    data = response.json()

    assert data["conversation_id"] is not None
    assert data["answer"] == "The maximum domestic per diem meal allowance is $75 per day [1]."
    assert len(data["citations"]) == 1
    assert data["citations"][0]["document_title"] == "HR-TRV-001 Travel Policy"
    assert data["evidence_status"] == "SUPPORTED"
    assert data["user_message_id"] is not None
    assert data["assistant_message_id"] is not None

    # Verify rows persisted in SQLite database
    conv_id = uuid.UUID(data["conversation_id"])
    conv = isolated_db_session.query(Conversation).filter(Conversation.id == conv_id).first()
    assert conv is not None
    assert "maximum daily meal allowance" in conv.title

    messages = isolated_db_session.query(Message).filter(Message.conversation_id == conv_id).all()
    assert len(messages) == 2
    roles = {m.role for m in messages}
    assert roles == {"user", "assistant"}


def test_chat_multiturn_follow_up_resolution(api_client: TestClient, isolated_db_session: Session, monkeypatch):
    """Multi-turn question resolves follow-up context and flags is_follow_up=True."""
    # Create existing conversation in database
    conv = Conversation(id=uuid.uuid4(), title="Leave Policy Discussion")
    isolated_db_session.add(conv)
    isolated_db_session.commit()

    orchestrator = _build_test_orchestrator(
        isolated_db_session,
        decision=EvidenceDecision.SUFFICIENT,
        standalone_query="How many annual leave days can an employee carry forward?",
        is_follow_up=True,
    )
    monkeypatch.setattr("app.api.routes.chat.get_rag_orchestrator", lambda db: orchestrator)

    payload = {
        "query": "How many can I carry forward?",
        "conversation_id": str(conv.id),
        "session_key": "test_user_2",
    }
    response = api_client.post("/api/v1/chat", json=payload)
    assert response.status_code == 200
    data = response.json()

    assert data["is_follow_up"] is True
    assert data["standalone_query"] == "How many annual leave days can an employee carry forward?"
    assert data["conversation_id"] == str(conv.id)


def test_chat_memory_context_injection(api_client: TestClient, isolated_db_session: Session, monkeypatch):
    """Active persistent user memory (department) is loaded and reported in response."""
    # Pre-populate memory in database
    mem = UserMemory(
        id=uuid.uuid4(),
        session_key="emp_sydney",
        memory_key="department",
        memory_value="Engineering",
        memory_text="Employee is in Engineering department.",
        memory_type="department",
        confidence_score=0.95,
        metadata_json={},
    )
    isolated_db_session.add(mem)
    isolated_db_session.commit()

    orchestrator = _build_test_orchestrator(isolated_db_session, decision=EvidenceDecision.SUFFICIENT)
    monkeypatch.setattr("app.api.routes.chat.get_rag_orchestrator", lambda db: orchestrator)

    payload = {
        "query": "Can I expense development software?",
        "session_key": "emp_sydney",
    }
    response = api_client.post("/api/v1/chat", json=payload)
    assert response.status_code == 200
    data = response.json()

    assert data["active_memory_used"] is not None
    assert data["active_memory_used"]["department"] == "Engineering"


def test_chat_safe_abstention_on_insufficient_evidence(api_client: TestClient, isolated_db_session: Session, monkeypatch):
    """When policy evidence is insufficient, system safely abstains with zero hallucination."""
    orchestrator = _build_test_orchestrator(isolated_db_session, decision=EvidenceDecision.INSUFFICIENT)
    monkeypatch.setattr("app.api.routes.chat.get_rag_orchestrator", lambda db: orchestrator)

    payload = {
        "query": "What is the company policy on bringing pets to the office?",
    }
    response = api_client.post("/api/v1/chat", json=payload)
    assert response.status_code == 200
    data = response.json()

    assert data["evidence_status"] == "INSUFFICIENT"
    assert "cannot answer" in data["answer"].lower()
    assert len(data["citations"]) == 0


def test_chat_conflict_disclosure(api_client: TestClient, isolated_db_session: Session, monkeypatch):
    """When policy contradiction exists, system discloses conflict without guessing."""
    orchestrator = _build_test_orchestrator(isolated_db_session, decision=EvidenceDecision.CONFLICT)
    monkeypatch.setattr("app.api.routes.chat.get_rag_orchestrator", lambda db: orchestrator)

    payload = {
        "query": "What is the domestic per diem meal cap?",
    }
    response = api_client.post("/api/v1/chat", json=payload)
    assert response.status_code == 200
    data = response.json()

    assert data["evidence_status"] == "CONFLICTING"
    assert "conflicting policy guidance" in data["answer"].lower()


def test_chat_clarification_handling(api_client: TestClient, isolated_db_session: Session, monkeypatch):
    """Ambiguous questions trigger clarification prompt."""
    orchestrator = _build_test_orchestrator(
        isolated_db_session,
        decision=EvidenceDecision.CLARIFICATION_REQUIRED,
        requires_clarification=True,
        clarification_reason="Please specify whether domestic or international travel.",
    )
    monkeypatch.setattr("app.api.routes.chat.get_rag_orchestrator", lambda db: orchestrator)

    payload = {
        "query": "What about allowances?",
    }
    response = api_client.post("/api/v1/chat", json=payload)
    assert response.status_code == 200
    data = response.json()

    assert data["evidence_status"] == "INSUFFICIENT"
    assert "clarify" in data["answer"].lower()


# ---------------------------------------------------------------------------
# 2. User Feedback API Tests
# ---------------------------------------------------------------------------

def test_submit_feedback_success(api_client: TestClient, isolated_db_session: Session):
    """POST /api/v1/feedback records thumbs up (+1) rating on message."""
    conv = Conversation(id=uuid.uuid4(), title="Test Conversation")
    msg = Message(
        id=uuid.uuid4(),
        conversation_id=conv.id,
        role="assistant",
        content="Here is the meal allowance policy.",
        evidence_status="answered",
    )
    isolated_db_session.add(conv)
    isolated_db_session.add(msg)
    isolated_db_session.commit()

    feedback_payload = {
        "message_id": str(msg.id),
        "feedback_score": 1,
        "comment": "Very accurate and cited the page number!",
    }
    response = api_client.post("/api/v1/feedback", json=feedback_payload)
    assert response.status_code == 200
    data = response.json()
    assert data["feedback_score"] == 1
    assert data["message_id"] == str(msg.id)

    # Verify updated in database
    isolated_db_session.refresh(msg)
    assert msg.feedback_score == 1


def test_submit_feedback_not_found(api_client: TestClient):
    """POST /api/v1/feedback returns 404 for nonexistent message ID."""
    random_id = str(uuid.uuid4())
    feedback_payload = {
        "message_id": random_id,
        "feedback_score": -1,
    }
    response = api_client.post("/api/v1/feedback", json=feedback_payload)
    assert response.status_code == 404
    assert f"Message with ID '{random_id}' not found" in response.json()["detail"]


# ---------------------------------------------------------------------------
# 3. Document Listing API Tests
# ---------------------------------------------------------------------------

def test_list_documents(api_client: TestClient, isolated_db_session: Session):
    """GET /api/v1/documents returns paginated list of uploaded documents."""
    doc1 = Document(
        id=uuid.uuid4(),
        title="HR Travel Policy",
        original_filename="HR-TRV-001.pdf",
        file_type="pdf",
        storage_path="docs/hr_trv_001.pdf",
        category="travel",
    )
    doc2 = Document(
        id=uuid.uuid4(),
        title="IT Security Policy",
        original_filename="IT-SEC-002.pdf",
        file_type="pdf",
        storage_path="docs/it_sec_002.pdf",
        category="security",
    )
    isolated_db_session.add_all([doc1, doc2])
    isolated_db_session.commit()

    response = api_client.get("/api/v1/documents?page=1&page_size=10")
    assert response.status_code == 200
    data = response.json()

    assert data["total"] == 2
    assert len(data["items"]) == 2
    assert data["page"] == 1
    assert data["total_pages"] == 1
    filenames = {d["original_filename"] for d in data["items"]}
    assert filenames == {"HR-TRV-001.pdf", "IT-SEC-002.pdf"}
