# KnowBridge AI — Product & Engineering Backlog

**Project:** KnowBridge AI — Policy-Aware Enterprise Knowledge Intelligence Platform  
**Document Version:** 1.0.0  
**Status:** Active  
**Priority Legend:**  
- **P0:** Critical Path MVP (Tasks 04–09)  
- **P1:** Phase 2 Fast-Follows (Enterprise Integrations, OCR, RBAC)  
- **P2:** Phase 3 Future Scope (Autonomous Harmonization, Vision Multi-Modal, GraphRAG)  

---

## 1. MVP Active Sprints (Phase 1 — 10-Hour Build)

---

### Epic 1: Document Ingestion Engine & Processing Pipeline (Task 04)
**Priority:** P0 | **Status:** Ready to Implement | **Dependency:** Task 02B

- [x] **STORY-401: Multi-Format Document Text Extraction Service (PDF, DOCX, TXT) [Task 003C Completed]**
  - **Description:** Implement `backend/app/parsers/` and `backend/app/services/document_extractor.py` extracting structured text, physical 1-based page numbers for PDFs (PyMuPDF), document-order paragraphs and Markdown tables for DOCX (python-docx), and UTF-8 plain text with BOM support (`utf-8-sig`).
  - **Acceptance Criteria:**
    - Every extracted PDF page carries an explicit 1-indexed `page_number` and boundary markers.
    - DOCX extracts paragraphs and tables in exact document order with `page_number=None`.
    - TXT preserves double-newline paragraph blocks with `page_number=None`.
    - Scanned/empty documents detect zero text and report `ocr_supported=False` without silent failures.
    - Password-protected PDFs raise `EncryptedDocumentError`.
    - Endpoint `POST /api/v1/documents/{document_id}/extract` exposes structured extraction.
    - 17 unit tests and live Supabase Storage integration verification script passing.
  - **Estimated Effort:** Completed

- [ ] **STORY-402: Hierarchical Semantic Chunker**
  - **Description:** Implement `backend/app/services/chunker.py` decomposing parsed pages into 400–600 token windows with a 50-token semantic overlap, strictly preserving page metadata.
  - **Acceptance Criteria:**
    - Chunks must never cross document-version boundaries.
    - Each chunk record must output: `content`, `token_count`, `page_number`, `chunk_index`, and `metadata` (JSONB).
  - **Estimated Effort:** 45 mins

- [ ] **STORY-403: Local Sentence-Transformers Embedding Pipeline**
  - **Description:** Implement `backend/app/services/embedding.py` wrapping Hugging Face `sentence-transformers/all-MiniLM-L6-v2` running in-process on CPU.
  - **Acceptance Criteria:**
    - Embeddings must match `vector(384)` float dimension.
    - Supports batch generation (batch size = 32) for high-throughput ingestion.
    - Zero external API cost or network dependencies for embedding.
  - **Estimated Effort:** 30 mins

- [x] **STORY-404: Supabase Storage Integration & File Paths [Task 003B Completed]**
  - **Description:** Implement server-side Supabase Storage client uploading original PDF, DOCX, and TXT binaries to `knowledge-documents` bucket.
  - **Acceptance Criteria:**
    - Generates unique deterministic storage path `documents/{document_id}/{safe_filename}`.
    - Prevents path traversal and validates UUIDs.
    - Persists confirmed storage path in `documents.storage_path`.
    - Implements compensating cleanup to delete uploaded objects if database transactions fail.
    - Sanitizes logs preventing secret token exposure.
  - **Estimated Effort:** Completed

- [ ] **STORY-405: Asynchronous Ingestion Job Coordinator**
  - **Description:** Implement background worker inserting chunks into `document_chunks` and updating `ingestion_jobs` status (`PENDING` -> `PROCESSING` -> `COMPLETED`/`FAILED`).
  - **Acceptance Criteria:**
    - Tracks `processed_pages` against `total_pages`.
    - Captures detailed sanitized error messages upon ingestion failure.
  - **Estimated Effort:** 45 mins

---

### Epic 2: LangGraph Stateful RAG Orchestrator (Task 05)
**Priority:** P0 | **Status:** Backlog | **Dependency:** Task 04

- [ ] **STORY-501: Agent State Schema Definition**
  - **Description:** Define `AgentState` TypedDict in `backend/app/graph/state.py` containing message history, current query, rewritten query, retrieved candidate chunks, evidence status, citations, and conflict banners.
  - **Estimated Effort:** 30 mins

- [ ] **STORY-502: Query Understanding & History Reformulation Node**
  - **Description:** Implement `node_query_understanding` using Groq (`llama-3.1-8b-instant`) to rewrite multi-turn follow-up queries into standalone search strings.
  - **Estimated Effort:** 45 mins

- [ ] **STORY-503: Policy-Aware Hybrid Vector Retrieval Node**
  - **Description:** Implement `node_retrieve` invoking stored function `match_policy_chunks` to query dense vectors via pgvector HNSW filtered strictly by document active status and validity dates.
  - **Estimated Effort:** 45 mins

- [ ] **STORY-504: Groq NLI Evidence Assessment & Conflict Detection Node**
  - **Description:** Implement `node_assess_evidence` using Groq (`llama-3.3-70b-versatile`) to evaluate retrieved chunks for factual sufficiency and cross-document contradictions.
  - **Estimated Effort:** 60 mins

- [ ] **STORY-505: Grounded Answer Synthesis & Strict Refusal Nodes**
  - **Description:** Implement `node_generate_answer` (grounded synthesis with inline citations `[Document, Page X]`) and `node_abstain` (polite refusal on insufficient evidence).
  - **Estimated Effort:** 45 mins

- [ ] **STORY-506: Deterministic Citation Page Verifier Node**
  - **Description:** Implement `node_validate_citations` regex-parsing generated inline citations and validating cited page numbers against actual retrieved context chunks.
  - **Estimated Effort:** 30 mins

- [ ] **STORY-507: PostgreSQL Checkpointer for Conversational Memory**
  - **Description:** Configure LangGraph `PostgresSaver` backed by Supabase PostgreSQL for persistent conversational state across sessions.
  - **Estimated Effort:** 45 mins

---

### Epic 3: FastAPI Application & Endpoints (Task 06)
**Priority:** P0 | **Status:** Backlog | **Dependency:** Task 05

- [x] **STORY-601: Document Upload Multipart Endpoint (`POST /api/v1/documents/upload`) [Task 003A & 003B Completed]**
  - **Acceptance Criteria:** Accepts multipart PDF, DOCX, and TXT files, performs safe filename sanitization, extension validation, MIME validation, file signature validation, uploads binary to private Supabase Storage bucket `knowledge-documents`, creates initial document record with status `'uploaded'` and real `storage_path`, and executes compensating cleanup on database failure.
  - **Estimated Effort:** Completed

- [ ] **STORY-602: Ingestion Job Polling Endpoint (`GET /api/v1/ingestion/{job_id}`)**
  - **Acceptance Criteria:** Returns real-time status (`PENDING`, `PROCESSING`, `COMPLETED`, `FAILED`) and percentage progress.
  - **Estimated Effort:** 30 mins

- [ ] **STORY-603: Document Catalog Endpoint (`GET /api/v1/documents`)**
  - **Acceptance Criteria:** Lists active documents, current version numbers, categories, and page counts.
  - **Estimated Effort:** 30 mins

- [ ] **STORY-604: Conversational Chat Endpoint (`POST /api/v1/chat`)**
  - **Acceptance Criteria:** Accepts query, optional `conversation_id`, and `as_of_date`; executes LangGraph pipeline; returns answer, citations array, and evidence status.
  - **Estimated Effort:** 60 mins

- [ ] **STORY-605: User Feedback Endpoint (`POST /api/v1/feedback`)**
  - **Acceptance Criteria:** Records binary score (+1 / -1) on `messages` table and forwards attribution span to Langfuse.
  - **Estimated Effort:** 30 mins

---

### Epic 4: Frontend Single Page Application (Task 07)
**Priority:** P0 | **Status:** Backlog | **Dependency:** Task 06

- [ ] **STORY-701: React + Vite + Tailwind SPA Initialization**
  - **Description:** Setup clean modular React 18+ shell with Tailwind CSS, Lucide icons, and Axios API client.
  - **Estimated Effort:** 45 mins

- [ ] **STORY-702: Document Management View**
  - **Description:** Document upload modal, metadata input form (title, effective date, version), and ingestion progress indicator.
  - **Estimated Effort:** 60 mins

- [ ] **STORY-703: Conversational Policy Assistant Interface**
  - **Description:** Modern chat interface supporting message history, loading states, and markdown rendering.
  - **Estimated Effort:** 60 mins

- [ ] **STORY-704: Interactive Citation Anchors & Popover**
  - **Description:** Render clickable `[Doc, Page X]` badges opening page previews and source text snippets.
  - **Estimated Effort:** 45 mins

- [ ] **STORY-705: Conflict Banners & Safe Abstention Notices**
  - **Description:** Distinct visual warning banners when conflicting policies are retrieved or when the assistant abstains.
  - **Estimated Effort:** 30 mins

---

### Epic 5: Quality Assurance, Evaluation & Observability (Task 08)
**Priority:** P0 | **Status:** Backlog | **Dependency:** Task 06

- [ ] **STORY-801: Langfuse Observability Instrumentation**
  - **Description:** Wrap all Groq LLM invocations and pgvector retrieval queries in Langfuse spans with token and latency tracking.
  - **Estimated Effort:** 45 mins

- [ ] **STORY-802: 50-Pair Golden Evaluation Dataset**
  - **Description:** Author `tests/eval_dataset.json` with 50 enterprise policy questions, ground truths, citation requirements, and expected abstentions.
  - **Estimated Effort:** 60 mins

- [ ] **STORY-803: Automated RAGAS Metric Suite**
  - **Description:** Automated evaluation runner measuring Faithfulness (>0.90), Answer Relevance (>0.85), and Context Precision (>0.80).
  - **Estimated Effort:** 60 mins

- [ ] **STORY-804: Deterministic Pytest Integration Suite**
  - **Description:** Pytest suite verifying regex citations, refusal triggers, and cascade constraints.
  - **Estimated Effort:** 45 mins

---

### Epic 6: Deployment & Runbook (Task 09)
**Priority:** P0 | **Status:** Backlog | **Dependency:** Task 07 & 08

- [ ] **STORY-901: Backend Containerization & Render Deployment**
  - **Description:** Author optimized multi-stage `Dockerfile` and deploy backend service to Render.
  - **Estimated Effort:** 45 mins

- [ ] **STORY-902: Frontend Vercel Deployment**
  - **Description:** Deploy SPA to Vercel with environment variable mapping to backend production URL.
  - **Estimated Effort:** 30 mins

- [ ] **STORY-903: Production Runbook & Smoke Test**
  - **Description:** Author operational runbook covering database backup, secrets rotation, and smoke testing.
  - **Estimated Effort:** 30 mins

---

## 2. Phase 2 Backlog (Enterprise Hardening & Connectors)

**Priority:** P1 | **Target Timeline:** Post-MVP Milestone 1

| Ticket ID | Feature Title | Technical Scope | Target Benefit |
|---|---|---|---|
| **FEAT-201** | OCR Ingestion Engine | Integrate Tesseract or cloud vision OCR for scanned bitmap documents. | Enables legacy non-digital PDF support. |
| **FEAT-202** | Google Drive / SharePoint Sync | OAuth2 connectors with webhook polling for auto-ingesting policy updates. | Eliminates manual upload workflows. |
| **FEAT-203** | Granular RBAC & Document ACLs | Organization and team-level document access trees enforced at vector query time. | Multi-department policy separation. |
| **FEAT-204** | Cross-Encoder Re-Ranking | Integrate BAAI/bge-reranker-large to re-rank Top-30 candidates down to Top-5. | +12% retrieval precision on dense corpora. |
| **FEAT-205** | Multilingual Query & Ingestion | Support policy documents and employee queries in Spanish, French, and German. | Global workforce support. |

---

## 3. Phase 3 Backlog (Autonomous Intelligence & GraphRAG)

**Priority:** P2 | **Target Timeline:** Post-MVP Milestone 2

| Ticket ID | Feature Title | Technical Scope | Target Benefit |
|---|---|---|---|
| **FEAT-301** | Multi-Modal Diagram Reasoning | Vision LLM extraction of organization charts, policy flowcharts, and diagrams. | Comprehensive visual policy comprehension. |
| **FEAT-302** | Autonomous Policy Reconciliation | Agentic workflow proposing redlines to reconcile contradictions across documents. | Proactive compliance maintenance. |
| **FEAT-303** | GraphRAG Knowledge Graph | Entity-relationship graph connecting policies, roles, regulations, and departments. | Multi-hop cross-policy reasoning. |
| **FEAT-304** | Slack & MS Teams Conversational Bots | Enterprise bot integrations allowing employees to query policies in chat channels. | Seamless workflow adoption. |
