# KnowBridge AI — Project Task Roadmap & Implementation Plan

**Project:** KnowBridge AI — Policy-Aware Enterprise Knowledge Intelligence Platform  
**Architecture Lead:** Senior Software Architect & AI Engineer  
**Status:** Task 05 Completed — Ready for Task 06 (FastAPI Chat & Feedback API Endpoints)  

---

## Task Progress Checklist

- [x] **TASK 01 — Product Discovery & Engineering Specification**
  - [x] Author `PRD.md` (Product Requirements Document)
  - [x] Author `BUSINESS_CONTEXT.md` (Strategic Justification & ROI Model)
  - [x] Author `USER_JOURNEYS.md` (Personas, Journeys, User Stories, Gherkin Scenarios)
  - [x] Author `FUNCTIONAL_REQUIREMENTS.md` (9 Core Capabilities Detailed Specs)
  - [x] Author `NON_FUNCTIONAL_REQUIREMENTS.md` (Performance, Security, Reliability)
  - [x] Author `MVP_SCOPE.md` (Scope Boundaries & Phased Roadmap)

- [x] **TASK 02 — Comprehensive System Design & Architecture Documentation**
  - [x] Author `docs/SYSTEM_DESIGN.md` (14 Core Sections with Mermaid Diagrams)
  - [x] Author `docs/DATA_FLOW.md` (Ingestion, Query, Memory, Telemetry, Eval Flows)
  - [x] Author `docs/DATABASE_DESIGN.md` (Complete DDL, Schemas, HNSW Indexes, Functions)
  - [x] Author `docs/DECISIONS.md` (ADRs 001 through 010)
  - [x] Create and maintain `TASKS.md`

- [x] **TASK 02A — Design and Implement KnowBridge AI Database (Completed)**
  - [x] Generate SQL migration files in `backend/migrations/` (`001_initial_schema.sql`, `002_indexes_and_functions.sql`, `000_full_migration.sql`)
  - [x] Enable `vector` and `uuid-ossp` extensions
  - [x] Create 7 core MVP tables (`documents`, `document_versions`, `document_chunks`, `conversations`, `messages`, `user_memories`, `ingestion_jobs`)
  - [x] Configure `vector(384)` with HNSW index `idx_chunks_embedding_hnsw` (`m = 16`, `ef_construction = 64`)
  - [x] Create B-Tree indexes for foreign keys, temporal ranges, and job statuses
  - [x] Create GIN index for JSONB metadata querying
  - [x] Implement automated `updated_at` triggers
  - [x] Implement policy-aware vector search stored procedure `match_policy_chunks`
  - [x] Implement comprehensive validation script `backend/migrations/validate_schema.sql` (transient CRUD, HNSW query, cascade test, clean rollback)
  - [x] Update database design documentation and ER diagram in `docs/DATABASE_DESIGN.md` and `docs/SYSTEM_DESIGN.md`
  - [x] Verify zero fake production data inserted
  - [x] Verified schema in Supabase PostgreSQL

- [x] **TASK 02B — FastAPI and Supabase PostgreSQL Integration (Completed)**
  - [x] Configure SQLAlchemy 2.0 database engine with connection pooling (`pool_pre_ping=True`, `pool_size=5`, `max_overflow=10`, `pool_recycle=1800`, `connect_timeout=5s`)
  - [x] Integrate psycopg 3 driver (`postgresql+psycopg://` dialect)
  - [x] Load `DATABASE_URL` from `backend/.env` using Pydantic v2 `BaseSettings` (`backend/app/core/config.py`)
  - [x] Implement dynamic URI dialect translation (`postgresql://` & `postgres://` -> `postgresql+psycopg://`)
  - [x] Implement reusable transactional database session dependency `get_db` with guaranteed cleanup
  - [x] Implement application connection lifecycle management via FastAPI `lifespan` (startup connectivity probe, clean engine disposal on shutdown)
  - [x] Implement database connectivity health check `check_db_connected` executing lightweight `SELECT 1` and measuring latency in milliseconds
  - [x] Implement connection error handling with credential sanitization (redacting passwords in URLs, parameters, and error logs)
  - [x] Implement `GET /health` (application health status) and `GET /health/db` (PostgreSQL connectivity health check, returning 200 OK or 503 Service Unavailable)
  - [x] Exclude `.env` files in root `.gitignore` and `backend/.gitignore`
  - [x] Provide `backend/.env.example` template with clean placeholder values
  - [x] Author automated test suite in `backend/tests/` (14 passing tests across configuration, error sanitization, health endpoints, and database execution)
  - [x] Live endpoint testing verified via FastAPI TestClient

- [x] **TASK 003A — Document Upload API & Validation (Completed)**
  - [x] Configure configurable upload limits in `config.py` (`MAX_UPLOAD_SIZE_BYTES=10MB`, `ALLOWED_FILE_EXTENSIONS={"pdf", "docx", "txt"}`)
  - [x] Define SQLAlchemy `Document` model in `backend/app/models/document.py` matching existing Supabase schema
  - [x] Define Pydantic `DocumentUploadResponse` schema in `backend/app/schemas/document.py`
  - [x] Implement multi-tier validation service in `backend/app/services/document_service.py`:
    - [x] Path traversal and unsafe filename sanitization (preventing null bytes, control chars, directory navigation)
    - [x] Extension validation (.pdf, .docx, .txt)
    - [x] Preliminary MIME-type verification
    - [x] Empty file rejection (0 bytes) and configurable max size check (HTTP 413)
    - [x] Deep magic-byte signature validation (PDF `%PDF-`, DOCX OpenXML zip container & Word XML, TXT UTF-8/ASCII without null bytes)
  - [x] Implement transactional database persistence creating initial document record with status `'uploaded'` and unique `storage_path`
  - [x] Ensure temporary binary content is safely discarded from memory after validation (Supabase storage upload deferred to Task 003B)
  - [x] Implement `POST /api/v1/documents/upload` endpoint in `backend/app/api/routes/documents.py` returning HTTP 201 Created
  - [x] Add `python-multipart>=0.0.9` to `backend/requirements.txt`
  - [x] Author comprehensive automated test suite in `backend/tests/test_document_upload.py` (25 tests covering all 9 required scenarios with 100% pass rate)
  - [x] Live Swagger UI & database verification confirmed (PDF, DOCX, TXT files successfully uploaded and stored)
  - [x] Branch `feat/task-003a-document-upload-api` pushed to GitHub

- [x] **TASK 003B — Supabase Storage Integration (Completed)**
  - [x] Create server-side `StorageService` using `httpx` for private `knowledge-documents` bucket integration
  - [x] Implement deterministic object naming structure: `documents/{document_id}/{safe_filename}`
  - [x] Implement safe path traversal prevention and UUID validation
  - [x] Wire `POST /api/v1/documents/upload` to store binary in Supabase Storage before DB commit
  - [x] Implement compensating cleanup (deletes uploaded object if DB transaction fails)
  - [x] Enhance error sanitization preventing leakage of JWT tokens, service-role keys, or passwords
  - [x] Add standalone integration verification script `backend/scripts/verify_storage_integration.py`
  - [x] Add 24 comprehensive unit tests in `backend/tests/test_storage_service.py` (70 backend tests total, 100% pass)
  - [x] Live verification confirmed in Supabase Storage and PostgreSQL for PDF, DOCX, and TXT files

- [x] **TASK 003C — Document Text Extraction Service (Completed)**
  - [x] Implement PyMuPDF (`fitz`) parser extracting text page-by-page with exact 1-based page numbers and boundaries
  - [x] Detect empty and scanned pages without claiming OCR support (`ocr_supported=False`, `empty_content` status)
  - [x] Implement `python-docx` parser extracting paragraphs and tables in exact document order with Markdown table grids
  - [x] Preserve heading hierarchy without fabricating DOCX page numbers (`page_number=None`, `total_pages=None`)
  - [x] Implement UTF-8 plain text parser supporting BOM (`utf-8-sig`) and safe decoding without fabricating pages
  - [x] Extend `StorageService` with `download_file` (async) and `download_file_sync` (sync) from private Supabase Storage bucket
  - [x] Implement modular `DocumentExtractorService` with format routing, exception handling, and structured output
  - [x] Implement `POST /api/v1/documents/{document_id}/extract` test & inspection endpoint returning `DocumentExtractionResult`
  - [x] Add 17 comprehensive unit tests in `backend/tests/test_document_extractor.py` and 3 download unit tests in `test_storage_service.py` (90 backend tests total, 100% pass)
  - [x] Add live storage extraction verification script `backend/scripts/verify_extraction_integration.py` verified with live PDF, DOCX, TXT files

- [x] **TASK 003D — Intelligent Document Chunking Service (Completed)**
  - [x] Implement recursive character text splitter with configurable defaults (`CHUNK_SIZE=1000`, `CHUNK_OVERLAP=150`)
  - [x] Priority-based separator hierarchy: section boundaries -> paragraphs -> sentences -> words -> characters
  - [x] Preserves exact 1-based PDF page provenance without cross-page merging
  - [x] Preserves DOCX paragraph order, table order, unit indices, and strictly enforces `page_number=None`
  - [x] Preserves TXT logical text block order, unit indices, and strictly enforces `page_number=None`
  - [x] Section hierarchy tracking (`SectionHierarchyTracker`) with breadcrumbs and heading level inference
  - [x] Table-aware chunking (`TableSplitter`) repeating headers across splits and preserving rows
  - [x] Forward progress guarantee, word-boundary preservation, and prevention of duplicate-only chunks
  - [x] Implement `POST /api/v1/documents/{document_id}/chunk` endpoint returning `DocumentChunkingResult`
  - [x] Author 27 comprehensive automated tests in `backend/tests/test_document_chunker.py` (117 backend tests total, 100% pass)
  - [x] Validated against synthetic Northstar policies (Travel, Leave, Remote/Hybrid Work)

- [x] **TASK 003E — Embeddings Generation Engine (Completed)**
  - [x] Integrate local Hugging Face `sentence-transformers/all-MiniLM-L6-v2` embedder (384d, zero API key requirement)
  - [x] Configurable batch vector generation with thread-safe singleton model caching
  - [x] Consistent unit L2 normalization (`normalize_embeddings=True`) for chunks and queries
  - [x] Strict vector validation ensuring 384 finite numerical values (no NaN or Inf)
  - [x] Retention of complete chunk provenance, section hierarchy, and physical page numbers
  - [x] Implement `POST /api/v1/documents/{document_id}/embed` endpoint returning `DocumentEmbeddingResult`
  - [x] Author 19 automated unit & API tests in `backend/tests/test_embedding_service.py` and live integration test in `test_embedding_integration.py` (137 backend tests total, 100% pass)
  - [x] Author standalone verification script `backend/scripts/verify_embeddings.py` verified with real synthetic PDF, DOCX, TXT policies and live Swagger testing

- [x] **TASK 003F — PostgreSQL Chunk Persistence (Completed)**
  - [x] Define SQLAlchemy models for `DocumentVersion`, `DocumentChunk`, `IngestionJob` matching live Supabase schema
  - [x] Integrate `pgvector.sqlalchemy.Vector(384)` with native HNSW cosine distance support
  - [x] Implement `ChunkPersistenceService` (`backend/app/services/chunk_persistence.py`)
  - [x] Document version resolution: check existing `is_current`, safe extraction from filename/text, avoid duplicates
  - [x] Column mapping: `document_version_id`, `chunk_index`, `page_number` (1-based for PDF, NULL for DOCX/TXT), `section_title`, `chunk_text`, `embedding` (384d), `embedding_model`, `token_count`, `metadata` (JSONB)
  - [x] Idempotent reprocessing: single-transaction deletion and replacement of version chunks
  - [x] Ingestion job tracking: `pending` -> `processing` -> `completed` / `failed` with sanitized error redaction
  - [x] Implement `POST /api/v1/documents/{document_id}/persist` endpoint returning `DocumentPersistenceResponse`
  - [x] Author 22 automated tests in `backend/tests/test_chunk_persistence.py` (159 passing backend tests total, 100% pass)
  - [x] Live Supabase verification: processed 3 synthetic documents (PDF, DOCX, TXT), confirmed 56 chunks, 384d vectors, live idempotency, and rollback safety

- [x] **TASK 003G — End-to-End Ingestion Orchestration (Completed)**
  - [x] Implement asynchronous background coordinator `IngestionService` (`backend/app/services/ingestion_service.py`) orchestrating extraction, chunking, embedding generation, and atomic persistence
  - [x] Implement top-level standalone execution worker `run_background_ingestion` managing dedicated DB sessions via `SessionLocal()`
  - [x] Implement concurrency guards preventing duplicate simultaneous processing runs on the same document
  - [x] Implement sanitized error handling and credential redaction ensuring zero secret leakage in job logs or DB
  - [x] Implement REST polling endpoints:
    - `GET /api/v1/ingestion/{job_id}` returning job metrics, timings, and progress (200 OK / 404 Not Found)
    - `GET /api/v1/ingestion/document/{document_id}` returning latest job status for a document
  - [x] Implement asynchronous processing trigger:
    - `POST /api/v1/ingestion/{document_id}/process` returning HTTP 202 Accepted with `IngestionJobResponse`
  - [x] Wire optional `auto_process: bool = False` query parameter on `POST /api/v1/documents/upload` for seamless single-step upload & processing
  - [x] Author 16 comprehensive automated tests in `backend/tests/test_ingestion_orchestration.py` (175 passing backend tests total, 100% pass)
  - [x] Full regression test run: 175 passed, 0 failed, 2 skipped

- [x] **TASK 04 — Policy-Aware RAG Retrieval Engine (Completed)**
  - [x] Integrate `sentence-transformers/all-MiniLM-L6-v2` dense query embedding
  - [x] Implement policy version filtering (`is_current=True`, temporal validity date ranges)
  - [x] Multi-format provenance tracking (PDF 1-based page numbers, DOCX/TXT headings)
  - [x] Structured evidence package assembly (`EvidencePackage`, `RetrievedChunk`)
  - [x] Implement deterministic fallback caching for sentence transformer models
  - [x] Author 28 comprehensive automated tests in `backend/tests/test_retrieval_service.py` (100% pass)

- [x] **TASK 05 — LangGraph RAG Orchestrator & State Graph (Completed)**
  - [x] **Task 05A: Query Understanding**
    - [x] Define `QueryUnderstandingRequest`, `QueryUnderstandingResult`, `QueryIntent`, `RetrievalHints`
    - [x] Implement `QueryUnderstandingService` and `GroqLLMClient` with conversational history re-writing
    - [x] Author 23 automated tests in `backend/tests/test_query_understanding.py` (100% pass)
  - [x] **Task 05B: Evidence Assessment & Conflict Detection**
    - [x] Define `EvidenceAssessmentRequest`, `EvidenceAssessmentResult`, `EvidenceDecision`, `SupportLevel`, `PolicyConflictItem`
    - [x] Implement `EvidenceAssessmentService` with deterministic sufficiency heuristics and Groq NLI conflict detection
    - [x] Author 14 unit tests in `backend/tests/test_evidence_assessment.py` (100% pass)
  - [x] **Task 05C: Grounded LLM Answer Generation**
    - [x] Define `AnswerGenerationRequest`, `AnswerGenerationResult`, `AnswerStatus`, `AnswerCitation`
    - [x] Implement `AnswerGenerationService` with grounded synthesis, provenance citations, safe abstention formatting, and citation verification
    - [x] Author 11 unit tests in `backend/tests/test_answer_generation.py` (100% pass)
  - [x] **Task 05D: LangGraph Workflow & State Graph**
    - [x] Define typed `AgentState` schema in `backend/app/graph/state.py`
    - [x] Implement modular nodes (`node_query_understanding`, `node_retrieve`, `node_assess_evidence`, `node_generate_answer`, `node_abstain`, `node_handle_conflict`, `node_handle_clarification`, `node_handle_error`)
    - [x] Implement explicit conditional routing in `backend/app/graph/routing.py`
    - [x] Implement compiled workflow in `backend/app/graph/workflow.py` with `MemorySaver` checkpointer and `ALLOWED_CHECKPOINT_TYPES` serialization
    - [x] Author 11 unit & routing tests in `backend/tests/test_rag_graph.py` (100% pass)

- [ ] **TASK 06 — FastAPI Application & API Endpoints**
  - [x] Implement `/api/v1/documents/upload` endpoint (multipart PDF, DOCX, TXT upload - Completed in Task 003A)
  - [x] Implement `/api/v1/ingestion/{job_id}` status polling endpoint (Completed in Task 003G)
  - [x] **Task 06B: Conversation Management APIs**
    - [x] Define SQLAlchemy `Conversation` and `Message` models matching Supabase schema
    - [x] Implement `POST /api/v1/conversations` (create thread, default/custom title, UUID v4)
    - [x] Implement `GET /api/v1/conversations` (paginated listing, deterministic ordering, message count aggregation)
    - [x] Implement `GET /api/v1/conversations/{conversation_id}` (detail retrieval, 404 on missing, message count)
    - [x] Implement `PATCH /api/v1/conversations/{conversation_id}` (update title, whitespace validation, timestamp refresh)
    - [x] Implement `DELETE /api/v1/conversations/{conversation_id}` (cascade deletion, foreign key safety, HTTP 204)
    - [x] Author 26 unit, API, pagination, and rollback tests in `backend/tests/test_conversations.py` (100% pass)
  - [x] **Task 06C: Message Persistence**
    - [x] Define Pydantic v2 schemas (`MessageRole`, `EvidenceStatusEnum`, `CitationItem`, `MessageCreate`, `MessageResponse`, `MessageListResponse`) in `backend/app/schemas/message.py`
    - [x] Implement `MessageService` in `backend/app/services/message_service.py` with citation persistence, transactional rollback, and parent timestamp synchronization
    - [x] Implement `POST /api/v1/conversations/{conversation_id}/messages` (persist user or assistant message with structured citations & evidence status)
    - [x] Implement `GET /api/v1/conversations/{conversation_id}/messages` (deterministic chronological ordering `created_at ASC, id ASC`, pagination, 404 on nonexistent)
    - [x] Author 19 unit, validation, pagination, and rollback tests in `backend/tests/test_messages.py` (100% pass)
  - [x] **Task 06D: Conversation History & Context Builder**
    - [x] Define `ContextBuilderRequest` and `ContextBuilderResult` with Task 05A `QueryUnderstandingRequest` adapter in `backend/app/schemas/context_builder.py`
    - [x] Implement `ContextBuilderService` in `backend/app/services/context_builder_service.py` with efficient tail query, chronological window bounding, deterministic 0-turn bypass, and Groq LLM resolution
    - [x] Author 15 comprehensive unit, pronoun, ambiguity, boundary, and fallback tests in `backend/tests/test_context_builder.py` (100% pass)
  - [x] **Task 06E: Persistent Memory System**
    - [x] Model `UserMemory` in `backend/app/models/user_memory.py` harmonized with Supabase `user_memories` table
    - [x] Pydantic v2 schemas (`MemoryType`, `ExtractedMemoryItem`, `MemoryCreate`, `MemoryResponse`, `MemoryListResponse`, `ActiveMemoryContext`) in `backend/app/schemas/memory.py`
    - [x] Implement `MemoryService` in `backend/app/services/memory_service.py` with Groq LLM extraction, PII filtering regex, durability checking, confidence thresholding (>= 0.75), exact fact deduplication, and superseding update with audit history
    - [x] Implement REST API routes in `backend/app/api/routes/memories.py` mounted at `/api/v1/memories` (`GET /`, `GET /context`, `POST /`, `DELETE /{id}`, `DELETE /session/{session_key}`)
    - [x] Author 16 automated tests in `backend/tests/test_memory.py` covering extraction, PII, durability, superseding audit, expiration, rollback, and REST endpoints (100% pass)
  - [ ] Implement `/api/v1/documents` listing endpoint
  - [ ] Implement `/api/v1/chat` conversational query endpoint
  - [ ] Implement `/api/v1/feedback` user feedback endpoint (thumbs up/down)
  - [ ] Configure global exception handlers and response middleware

- [ ] **TASK 07 — Frontend SPA Implementation (React + Vite + Tailwind)**
  - [ ] Initialize React + TypeScript + Vite project
  - [ ] Configure Tailwind CSS and Lucide icons
  - [ ] Build Document Management view (upload, status badge, metadata display)
  - [ ] Build Conversational Chat interface (streaming text, message history)
  - [ ] Build Interactive Citation component (page number badge, snippet popover)
  - [ ] Build Policy Conflict Alert banner component
  - [ ] Build Safe Abstention notice component
  - [ ] Build Feedback action buttons (thumbs up/down)

- [ ] **TASK 08 — Evaluation (RAGAS & Pytest) & Observability (Langfuse)**
  - [ ] Instrument all FastAPI endpoints and LangGraph nodes with Langfuse spans
  - [ ] Construct 50-pair enterprise golden evaluation dataset (`tests/eval_dataset.json`)
  - [ ] Implement deterministic Pytest suite (citation regex, abstention triggers)
  - [ ] Implement automated RAGAS evaluation runner (Faithfulness, Relevance, Precision)

- [ ] **TASK 09 — Deployment & Final End-to-End Verification**
  - [ ] Containerize FastAPI backend for Render deployment
  - [ ] Deploy React frontend to Vercel
  - [ ] Validate end-to-end user journeys against deployed environment
  - [ ] Document final operating runbook
