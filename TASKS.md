# KnowBridge AI — Project Task Roadmap & Implementation Plan

**Project:** KnowBridge AI — Policy-Aware Enterprise Knowledge Intelligence Platform  
**Architecture Lead:** Senior Software Architect & AI Engineer  
**Status:** Task 003A Completed — Ready for Task 003B / Task 04 (Document Ingestion Engine)  

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

- [ ] **TASK 04 — Ingestion Engine & Document Processing Service (Pending Approval)**
  - [ ] Implement PyMuPDF (`fitz`) parser for layout, text, tables, and page tracking
  - [ ] Implement token-aware hierarchical chunking preserving page-level metadata (400-600 tokens)
  - [ ] Integrate local Hugging Face `sentence-transformers/all-MiniLM-L6-v2` embedder (384d)
  - [ ] Implement Supabase Storage file upload integration (`knowbridge-documents` bucket)
  - [ ] Implement batch insertion of chunks into `document_chunks` table
  - [ ] Implement background task queue / status tracking in `ingestion_jobs`

- [ ] **TASK 05 — LangGraph RAG Orchestrator & State Graph**
  - [ ] Define `AgentState` TypedDict schema
  - [ ] Implement `node_query_understanding` (query re-writing with conversational history)
  - [ ] Implement `node_retrieve` (pgvector cosine similarity + temporal filtering)
  - [ ] Implement `node_assess_evidence` (Groq NLI sufficiency & conflict detection)
  - [ ] Implement `node_generate_answer` (Groq Llama 3.3 70B strict grounded prompt)
  - [ ] Implement `node_abstain` (safe refusal templates on insufficient evidence)
  - [ ] Implement `node_resolve_conflict` (discrepancy formatting banner)
  - [ ] Implement `node_validate_citations` (deterministic page-number verification)
  - [ ] Configure LangGraph Postgres checkpointer for conversation memory

- [ ] **TASK 06 — FastAPI Application & API Endpoints**
  - [x] Implement `/api/v1/documents/upload` endpoint (multipart PDF, DOCX, TXT upload - Completed in Task 003A)
  - [ ] Implement `/api/v1/ingestion/{job_id}` status polling endpoint
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
