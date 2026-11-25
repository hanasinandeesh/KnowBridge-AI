# KnowBridge AI — Complete Project Context, Business Context, PRD, Tech Stack & Task History

> **Purpose of this document:** A single, self-contained reference containing the full Business Context, Product Requirements Document (PRD), MVP Scope, Architecture & Tech Stack (ADRs 001–010), Database Schema, Synthetic Dataset, Implemented APIs, and Complete Task Progress (Tasks 01 through 04 completed; Tasks 05–09 remaining) for sharing with another AI assistant (e.g., ChatGPT / GPT).

---

## 1. Executive Summary & Product Vision

**Project Name:** KnowBridge AI  
**Category:** Policy-Aware Enterprise Knowledge Intelligence & Retrieval-Augmented Generation (RAG) Platform  
**Repository / Workspace:** `KnowBridge AI`  
**Current Milestone:** **Task 04 Completed** (Ingestion + Policy-Aware Retrieval Engine complete). **Next Up:** **Task 05** (LangGraph Stateful RAG Orchestrator).

### 1.1 Executive Summary
Modern enterprises operate in high-velocity environments where institutional policies, standard operating procedures (SOPs), legal guidelines, and operational documentation are authored, updated, and fragmented across disparate silos (SharePoint, Google Drive, Confluence, internal intranets, and local storage). Knowledge workers spend up to 20% (19–28%) of their working hours searching for critical information, frequently relying on outdated documents or misinterpreting superseded policies.

**KnowBridge AI** is an enterprise-grade, policy-aware Knowledge Intelligence and RAG platform. It bridges the gap between fragmented organizational repositories and employee decision-making by delivering verified, evidence-grounded answers with exact page-level citations, temporal/version awareness, automated policy conflict detection, and deterministic safe abstention.

### 1.2 Vision Statement
> *"To establish the enterprise standard for trusted institutional memory, where every operational and policy inquiry receives an auditable, temporally verified, and mathematically grounded response—eliminating organizational hallucination and policy compliance risk."*

### 1.3 Core Architectural Pillars & Value Proposition
1. **Zero-Hallucination Policy Retrieval & Grounded Citations:** Every generated sentence is strictly bound to verifiable physical page-level source evidence (`[Document Title, Page X]`).
2. **Deterministic Temporal & Version Integrity:** Active policies take absolute operational precedence over superseded or draft revisions without deleting historical documents, while supporting point-in-time historical audits by effective date.
3. **Proactive Cross-Document Conflict Detection:** Identifies and highlights contradictions across concurrent or regional documentation via Natural Language Inference (NLI) rather than synthesizing conflicting guidance into a false consensus.
4. **Deterministic Safety Through Abstention:** Refuses to guess or speculate when evidence is absent, incomplete, ambiguous, or below confidence thresholds (`< 0.65`).
5. **Conversational & Persistent Memory:** Multi-turn session state persistence via PostgreSQL checkpointers (`PostgresSaver`) and fact extraction (`user_memories`).
6. **Production-Grade Observability & Continuous Evaluation:** Native distributed tracing via Langfuse and automated quality benchmarking via RAGAS + Pytest.

---

## 2. Detailed Business Context & Strategic Justification

### 2.1 The Enterprise Knowledge Crisis
Organizational documentation expands organically without unified governance across SharePoint, Google Drive, Confluence, and internal network drives, causing four compounding failures:
1. **Repository Fragmentation & Search Paralysis:** Keyword searches return dozens of unindexed PDFs/wikis, leaving employees guessing which file is canonical.
2. **Temporal Decay & "Zombie Policies":** Old versions (e.g., *Travel Policy v1.0* capping meals at \$50/day) remain accessible alongside newer versions (*Travel Policy v2.0* increasing it to \$85/day), causing employees to follow deprecated rules.
3. **Internal Cross-Departmental Contradictions:** E.g., an Engineering Remote Work Addendum states a \$1,000 home office budget while the Corporate HR Handbook states \$500. Naive search or chatbots blend these into legally contradictory guidance.
4. **The Generative AI "Hallucination Trap":** Generic LLM chatbots fabricate plausible-sounding answers without page provenance. A single high-profile hallucination about benefits, leave, or compliance destroys employee trust and exposes the enterprise to legal/financial liability.

### 2.2 Quantifying the Cost of Inefficiency & Risk
- **The Productivity Tax:** Per McKinsey & Gartner research, knowledge workers spend **19% to 28% of their workweek** (7.6–11.2 hours/week) searching for information.
  - Modeled for **5,000 employees** at **\$100,000/year** fully loaded compensation, spending just **2 hours/week** (100 hours/year) searching outdated docs:
    $$\text{Productivity Loss} = 5{,}000 \times \left(\frac{\$100{,}000}{2{,}000 \text{ hours}}\right) \times 100 \text{ hours/year} = \$25{,}000{,}000 \text{ annually}$$
- **Compliance, Legal & Financial Liabilities:**
  - *Labor Compliance & Wage Violations:* Misinterpreting overtime, parental leave, or PTO rollover rules.
  - *Financial Leakage:* Unauthorized procurement or travel spend.
  - *Contractual & SLA Breaches:* Outdated security/client SOPs causing SOC2/ISO audit failures.

### 2.3 Strategic Objectives & OKRs
- **Objective 1 — Eliminate Policy Retrieval Friction & Hallucinations:**
  - KR 1.1: RAGAS Faithfulness $\ge 95\%$.
  - KR 1.2: 100% of answers include clickable, page-level citations.
  - KR 1.3: Reduce average policy retrieval time from 18 minutes to under 15 seconds ($>90\%$ gain).
- **Objective 2 — Guarantee Temporal Accuracy & Version Integrity:**
  - KR 2.1: $0\%$ obsolete policy retrieval for current-rule queries.
  - KR 2.2: Point-in-time historical auditability as of any arbitrary past date with $100\%$ precision.
- **Objective 3 — Prevent False Consensus via Automated Conflict Detection:**
  - KR 3.1: Detect and flag $\ge 90\%$ of semantic contradictions between co-retrieved passages before synthesis.
  - KR 3.2: Display transparent side-by-side discrepancy callouts.
- **Objective 4 — Enterprise AI Governance & Cost-Effective Observability:**
  - KR 4.1: Capture 100% of retrieval traces, latency splits, and token costs in Langfuse.
  - KR 4.2: Keep average operational LLM cost below **\$0.015 per query**.

### 2.4 Stakeholder Matrix
| Stakeholder | Core Drivers | Operational Impact |
|---|---|---|
| **CHRO** | Consistent policy execution, employee satisfaction | Deflects 60–70% of repetitive HR tier-1 tickets; standardizes onboarding |
| **General Counsel & Compliance** | Legal exposure, defensible audit trails | Verifiable citations, point-in-time logs, policy conflict alerts |
| **CIO / VP IT** | System consolidation, cost efficiency | Replaces brittle scripts with production RAG architecture |
| **CISO** | Data governance, zero model training on IP | Zero-retention enterprise APIs, encrypted vectors, secure trace logs |
| **Frontline Knowledge Workers** | Fast, reliable answers without blockers | Immediate answers with page references & multi-turn context |
| **AI / Platform Engineering** | Observability, latency, regression testing | Langfuse trace introspection + automated RAGAS CI/CD benchmarks |

### 2.5 Architectural Comparison
| Dimension | Legacy Search (SharePoint / Lucene) | Naive RAG (Basic Vector Search) | KnowBridge AI (Policy RAG) |
|---|---|---|---|
| **Search** | Keyword match only | Dense vector retrieval only | Hybrid/Policy-aware vector search + metadata & temporal filtering |
| **Versioning** | Surfaces obsolete duplicates | Ignores effective dates | Deterministic Temporal & Effective-Date Engine |
| **Conflicts** | Returns raw 60-page PDFs | Merges conflicting text blindly | Pre-synthesis NLI Conflict Detection Engine |
| **Citations** | None | Fabricates plausible citations | Strict Page-Level Verified Anchors (`[Doc, Page X]`) |
| **Unknowns** | No synthesis | Guesses when info is absent | Deterministic Safe Abstention (`< 0.65` confidence) |
| **Ops / QA** | Zero LLM observability | No regression testing | Langfuse Traces + RAGAS & Pytest Baselines |

### 2.6 Business Case & ROI Financial Model
- **Modeled Organization:** 2,500 employees; 8,000 internal policy/SOP inquiries/month at \$18.50/manual ticket = **\$148,000/month** (\$1,776,000/year).
- **Projected Impact:** 65% ticket deflection (5,200 tickets/month) = **\$96,200/month gross savings** (**\$1,154,400/year**).
- **Modeled Operating Cost:** ~20,000 queries/month at \$0.012/query (\$240/month LLM spend) + \$1,400/month infra = **\$1,640/month** (**\$19,680/year**).
- **Net Annual Savings:** $\$1{,}154{,}400 - \$19{,}680 = \mathbf{\$1{,}134{,}720 / \text{year}}$ (**5,765% Projected ROI**).

---

## 3. Product Requirements Document (PRD) & MVP Scope

### 3.1 Nine Foundational Capabilities
1. **Enterprise Document Intelligence:** Layout-aware parsing of native PDF, DOCX, and TXT; hierarchical/structure-aware chunking; table linearization; structural metadata extraction.
2. **Policy-Aware Semantic Retrieval:** Dense embeddings (`pgvector` HNSW) + metadata filtering (category, department, status); planned hybrid BM25 + cross-encoder re-ranking in full vision.
3. **Version & Effective-Date Awareness:** Enforcing document release dates, effective dates, sunset dates, and version hierarchies (`ACTIVE`/`CURRENT` vs. `SUPERSEDED`/`DEPRECATED`) against query temporal context.
4. **Cross-Evidence Conflict Detection:** Pairwise NLI and counter-evidence analysis to flag contradictory policy statements before synthesis.
5. **Evidence-Grounded Citations:** Strict generative constraint restricting answers exclusively to retrieved chunks with inline `[Doc Title, Page X]` anchors and deterministic post-generation citation verification.
6. **Answerability & Safe Abstention:** Confidence threshold gating (`< 0.65` / `< 0.70`) and deterministic safe-refusal templates when evidence is missing or ambiguous.
7. **Conversational & Persistent Memory:** Session-state persistence, multi-turn query reformulation, and long-term user fact memory.
8. **RAG Evaluation using RAGAS:** Automated scoring of Faithfulness, Answer Relevance, Context Precision, and Context Recall against a 50-pair golden dataset.
9. **LLM Observability using Langfuse:** Full span tracing, token cost accounting, latency tracking, and thumbs up/down feedback attribution.

### 3.2 User Personas
- **Persona 1: Sarah — Frontline Knowledge Worker (Employee):** Needs fast, unambiguous answers on travel limits, remote work, and benefits with exact page links to verify rules herself.
- **Persona 2: Marcus — HR, Legal & Compliance Officer:** Needs assurance that obsolete policies are never surfaced and conflicting clauses across regional/parent policies are flagged.
- **Persona 3: Elena — Enterprise Knowledge Base Administrator:** Uploads PDFs/DOCX/TXT and expects automatic metadata/version handling and clean re-indexing without vector corruption.
- **Persona 4: Dev — AI Platform & MLOps Lead:** Needs end-to-end Langfuse trace visibility, token cost tracking, and automated RAGAS regression gates in CI/CD.

### 3.3 Target KPIs & Success Metrics
| Metric | MVP Target | Phase 2 Target |
|---|---|---|
| **Faithfulness (RAGAS)** | $\ge 95\%$ | $\ge 98\%$ |
| **Answer Relevance (RAGAS)** | $\ge 90\%$ | — |
| **Citation Precision** | $\ge 99\%$ (Zero hallucinated pages) | $100\%$ |
| **Abstention Precision** | $\ge 98\%$ | $\ge 99.5\%$ |
| **Conflict Detection Recall** | $\ge 90\%$ | $\ge 96\%$ |
| **Version Adherence** | $100\%$ | $100\%$ |
| **P50 / P95 Latency** | $\le 1.5\text{ s}$ / $\le 3.0\text{–}3.5\text{ s}$ | $\le 1.0\text{ s}$ / $\le 2.5\text{ s}$ |
| **CSAT / Helpful Rate** | $\ge 85\%$ | $\ge 92\%$ |

### 3.4 MVP Scope Boundaries
- **In-Scope (MVP / Phase 1):** Native PDF, DOCX, and TXT ingestion; page-preserving chunking; local 384d embeddings; Supabase PostgreSQL + `pgvector` HNSW; policy-aware & version-aware retrieval; LangGraph 8-node stateful RAG pipeline with Groq LLMs; PostgreSQL checkpointing; inline `[Doc, Page X]` citations; safe abstention; NLI conflict detection; React + Vite + Tailwind SPA; Langfuse tracing; 50-pair RAGAS + Pytest suite.
- **Explicitly Out-of-Scope for MVP (Deferred to Phase 2/3):**
  - OCR for scanned bitmap PDFs (Phase 2 — scanned PDFs are detected and flagged `ocr_supported=False`).
  - Live Google Drive / SharePoint / Confluence webhooks (Phase 2).
  - Authentication, Login, JWT, and granular RBAC / Supabase RLS (Phase 2 — ADR-007).
  - Multi-language translation RAG (Phase 2 — MVP is English-only).
  - Multi-modal image/diagram reasoning, autonomous policy redlining, GraphRAG (Phase 3).

---

## 4. Tech Stack & Architecture Decisions (ADRs 001–010)

### 4.1 Current & Planned Technology Stack
| Layer | Technology / Library | Version / Notes |
|---|---|---|
| **Backend Framework** | **FastAPI** + **Uvicorn** | `fastapi>=0.111.0`, `uvicorn[standard]>=0.30.0`, Python 3.11+ |
| **Validation & Config** | **Pydantic v2** + **pydantic-settings** | `pydantic>=2.7.0`, `pydantic-settings>=2.3.0` |
| **ORM & DB Driver** | **SQLAlchemy 2.0** + **psycopg 3** | `sqlalchemy>=2.0.30`, `psycopg[binary]>=3.1.0` (`postgresql+psycopg://`) |
| **Database & Vector Store** | **Supabase PostgreSQL 15+** + **pgvector** | `pgvector>=0.3.0` (extension `0.8.2`), `vector(384)`, HNSW index (`m=16`, `ef_construction=64`, cosine) |
| **Object Storage** | **Supabase Storage** via **httpx** | `httpx>=0.27.0`, private bucket `knowledge-documents` |
| **Document Parsing** | **PyMuPDF (`fitz`)**, **python-docx**, UTF-8 TXT | `pymupdf>=1.24.0`, `python-docx>=1.1.0` |
| **Embeddings (Local CPU)** | **sentence-transformers** | `sentence-transformers>=3.0.0`, `all-MiniLM-L6-v2` (384 dimensions, unit L2 normalized) |
| **RAG Orchestration (Task 05)** | **LangGraph** (`StateGraph`) + `PostgresSaver` | Stateful 8-node pipeline with PostgreSQL checkpointing |
| **LLM Inference (Task 05)** | **Groq Cloud API** | `llama-3.3-70b-versatile` (NLI & grounded synthesis) + `llama-3.1-8b-instant` (query rewrite) |
| **Frontend SPA (Task 07)** | **React 18 + TypeScript + Vite + Tailwind CSS** | Lucide icons, Axios API client |
| **Observability (Task 08)** | **Langfuse Cloud** (Python SDK) | Nested span tracing, token cost, latency, feedback attribution |
| **Testing & Eval (Task 08)** | **Pytest** (`pytest>=8.0.0`) + **RAGAS** | Deterministic unit/integration tests + 50-pair golden RAGAS suite |
| **Deployment (Task 09)** | **Render** (FastAPI Docker) + **Vercel** (React SPA) | Monolithic backend container + static SPA |

### 4.2 Summary of Architecture Decision Records (ADRs 001–010)
- **ADR-001:** *Monolithic FastAPI Service Topology* — Modular monolith (`app/services/`, `app/graph/`, `app/api/routes/`) instead of microservices to eliminate RPC overhead for the MVP.
- **ADR-002:** *Supabase PostgreSQL + pgvector as Unified Data & Vector Store* — Single datastore for relational metadata, vectors, and single-query temporal + cosine joins (`zero synchronization drift`).
- **ADR-003:** *LangGraph for Stateful RAG Orchestration* — Non-linear `StateGraph` for conditional abstention, conflict detection, query rewriting, and citation verification.
- **ADR-004:** *Groq Cloud API for High-Speed Inference* — LPU inference (>250 tok/s) to keep multi-step RAG P95 latency under 3.0s.
- **ADR-005:** *Local Hugging Face Sentence-Transformers Embeddings* — `all-MiniLM-L6-v2` (384d) in-process on CPU; zero API cost, <15ms query embedding, offline/local-cache capable.
- **ADR-006:** *PostgreSQL Checkpointing & Session Memory over Redis* — Consolidated session memory into Supabase PostgreSQL via LangGraph `PostgresSaver` + `user_memories` table, eliminating Redis from MVP.
- **ADR-007:** *Explicit Exclusion of Auth/RBAC for MVP* — Single-workspace development platform; schema retains future-compatible structure without auth gates.
- **ADR-008:** *PyMuPDF (`fitz`) for Page-Preserving Document Processing* — Exact 1-based physical page mapping for PDF citations; OCR deferred to Phase 2.
- **ADR-009:** *RAGAS and Pytest Dual-Layer Quality Assurance* — Deterministic Pytest contracts + semantic RAGAS CI/CD gates.
- **ADR-010:** *Langfuse for Full-Stack LLM Observability & Tracing* — Root traces + nested spans for every query.

---

## 5. Database Schema & Stored Procedure (Supabase PostgreSQL)

Migrations live in `backend/migrations/` (`000_full_migration.sql`, `001_initial_schema.sql`, `002_indexes_and_functions.sql`, `validate_schema.sql`).

### 5.1 Seven Core MVP Tables
1. `documents`: Top-level document metadata (`id`, `title`, `description`, `category`, `storage_path`, status, etc.).
2. `document_versions`: Revision history (`id`, `document_id`, `version_number`, `effective_date`, `sunset_date`, `status` in `DRAFT`/`ACTIVE`/`SUPERSEDED`/`DEPRECATED`, `storage_path`, `file_hash`, `file_size_bytes`, `total_pages`, `supersedes_version_id`).
3. `document_chunks`: Chunked text & vectors (`id`, `document_version_id`, `chunk_index`, `page_number`, `section_title`, `content`/`chunk_text`, `token_count`, `embedding VECTOR(384)`, `embedding_model`, `metadata JSONB`). Indexed via HNSW `idx_chunks_embedding_hnsw` (`m=16`, `ef_construction=64`, cosine distance) + GIN index on `metadata`.
4. `conversations`: Chat session threads (`id`, `title`, `created_at`, `updated_at`).
5. `messages`: User/assistant turns, structured citations, and binary feedback scores.
6. `user_memories`: Long-term extracted user facts.
7. `ingestion_jobs`: Async pipeline tracking (`pending` $\to$ `processing` $\to$ `completed` / `failed`, timings, chunk counts, sanitized `error_message`).

### 5.2 Policy-Aware Vector Search Function
- **`match_policy_chunks`**: PostgreSQL stored procedure performing cosine similarity search over `document_chunks` joined with `document_versions` and `documents`, supporting temporal effective-date filtering, active/superseded status filtering, and metadata filtering.

---

## 6. Synthetic Enterprise Policy Dataset (`synthetic-data/`)

A 13-document synthetic dataset for **"Northstar Technologies"** (`scripts/generate_dataset.py` + `synthetic-data/metadata/manifest.csv`) designed to test multi-format parsing, version supersession, and policy conflicts:
- **Versioned PDFs (v1.0 `SUPERSEDED` vs. v2.0 `CURRENT`):**
  - `HR-TRV-001_Travel_Reimbursement_v1.0.pdf` & `v2.0.pdf` (effective 01 Apr 2025–31 Mar 2026 vs. 01 Apr 2026–31 Mar 2027)
  - `HR-LVE-001_Employee_Leave_v1.0.pdf` & `v2.0.pdf`
  - `HR-WFH-001_Remote_Hybrid_Work_v1.0.pdf` & `v2.0.pdf`
- **Current PDFs:** `IT-SEC-001_Information_Security.pdf`, `HR-COC-001_Code_of_Conduct.pdf`
- **Current DOCX:** `FIN-EXP-001_Employee_Expense.docx`, `HR-ONB-001_Employee_Onboarding.docx`, `FIN-PROC-001_Procurement_Vendor.docx`
- **Current TXT:** `HR-PER-001_Performance_Appraisal.txt`, `IT-AUP-001_IT_Acceptable_Use.txt`

---

## 7. Complete Task History & Roadmap (Tasks 01 → 09)

### ✅ Completed Tasks

1. **TASK 01 — Product Discovery & Engineering Specification**
   - Authored `PRD.md`, `BUSINESS_CONTEXT.md`, `USER_JOURNEYS.md`, `FUNCTIONAL_REQUIREMENTS.md`, `NON_FUNCTIONAL_REQUIREMENTS.md`, `MVP_SCOPE.md`.
2. **TASK 02 — System Design & Architecture Documentation**
   - Authored `docs/SYSTEM_DESIGN.md`, `docs/DATA_FLOW.md`, `docs/DATABASE_DESIGN.md`, `docs/DECISIONS.md` (ADRs 001–010), and `TASKS.md`.
3. **TASK 02A — Supabase PostgreSQL Database Implementation**
   - Generated SQL migrations in `backend/migrations/`, enabled `vector` & `uuid-ossp`, created 7 core tables, HNSW & GIN indexes, `updated_at` triggers, `match_policy_chunks` stored procedure, and `validate_schema.sql`. Verified live in Supabase.
4. **TASK 02B — FastAPI & Supabase PostgreSQL Integration**
   - Configured SQLAlchemy 2.0 + `psycopg` 3 (`QueuePool`, `pool_pre_ping=True`, `pool_size=5`, `max_overflow=10`, `pool_recycle=1800`, `connect_timeout=5`).
   - Implemented `backend/app/core/config.py` (Pydantic v2 `BaseSettings`, dynamic `postgresql+psycopg://` dialect translation, password URL-encoding, credential redaction).
   - Implemented `get_db`, FastAPI `lifespan` probe, `check_db_connected`, `GET /health`, `GET /health/db`, and `GET /api/v1/health`.
5. **TASK 003A — Document Upload API & Multi-Tier Validation**
   - Implemented `POST /api/v1/documents/upload` (201 Created), `Document` SQLAlchemy model, path traversal & filename sanitization, extension/MIME/size checks (`MAX_UPLOAD_SIZE_BYTES=10MB`), and deep magic-byte signature validation (`%PDF-`, DOCX OpenXML zip, UTF-8 TXT without null bytes).
6. **TASK 003B — Supabase Storage Integration**
   - Implemented `StorageService` (`backend/app/services/storage_service.py`) using `httpx` against private `knowledge-documents` bucket with deterministic path `documents/{document_id}/{safe_filename}`, compensating cleanup on DB rollback, and secret/JWT redaction in logs.
7. **TASK 003C — Document Text Extraction Service**
   - Implemented `backend/app/parsers/` (`pdf_parser.py` via PyMuPDF with 1-based physical pages, `docx_parser.py` via `python-docx` preserving document order & Markdown tables with `page_number=None`, `txt_parser.py` with `utf-8-sig` BOM handling and `page_number=None`).
   - Added `download_file` / `download_file_sync` to `StorageService`, `DocumentExtractorService`, scanned/encrypted/corrupt PDF handling (`ocr_supported=False`, `EncryptedDocumentError`, `CorruptedDocumentError`), and `POST /api/v1/documents/{document_id}/extract`.
8. **TASK 003D — Intelligent Document Chunking Service**
   - Implemented `backend/app/services/document_chunker.py` (`CHUNK_SIZE=1000`, `CHUNK_OVERLAP=150`), priority separator hierarchy (headings $\to$ paragraphs $\to$ sentences $\to$ words $\to$ chars), `SectionHierarchyTracker` breadcrumbs, `TableSplitter` repeating headers across splits, strict 1-based PDF page provenance (no cross-page merging), `page_number=None` for DOCX/TXT, and `POST /api/v1/documents/{document_id}/chunk`.
9. **TASK 003E — Embeddings Generation Engine**
   - Implemented `backend/app/services/embedding_service.py` using local `sentence-transformers/all-MiniLM-L6-v2` (384d, `normalize_embeddings=True`, thread-safe singleton caching, `EMBEDDING_BATCH_SIZE=32`, NaN/Inf validation, symmetrical `embed_query`), and `POST /api/v1/documents/{document_id}/embed`.
10. **TASK 003F — PostgreSQL `pgvector` Chunk Persistence**
    - Defined `DocumentVersion`, `DocumentChunk` (`pgvector.sqlalchemy.Vector(384)`), `IngestionJob` models.
    - Implemented `ChunkPersistenceService` (`backend/app/services/chunk_persistence.py`) with version resolution (`is_current`), single-transaction idempotent chunk replacement, `IngestionJob` state machine, and `POST /api/v1/documents/{document_id}/persist`.
11. **TASK 003G — End-to-End Ingestion Orchestration**
    - Implemented `IngestionService` (`backend/app/services/ingestion_service.py`) and `run_background_ingestion` with dedicated `SessionLocal()` sessions, concurrency guards preventing overlapping runs on the same document, credential-sanitized error logging, `POST /api/v1/ingestion/{document_id}/process` (202 Accepted), `GET /api/v1/ingestion/{job_id}`, `GET /api/v1/ingestion/document/{document_id}`, and optional `auto_process=true` on `POST /api/v1/documents/upload`.
    - **Verified Test Suite (at Task 003G):** **175 passed, 0 failed, 2 opt-in live integration tests skipped** (100% pass rate).
12. **TASK 04 (04A–04F) — Policy-Aware RAG Retrieval Engine (Latest Commit `11eb52d`)**
    - **04A:** Evaluated vector search readiness, schema relationships, and `match_policy_chunks` signature.
    - **04B:** Normalized 384d query embedding generation with singleton reuse, input validation, and local-cache model fallback (`embedding_service.py`).
    - **04C:** Built `RetrievalService` (`backend/app/services/retrieval_service.py`) integrating `pgvector` semantic search, configurable `top_k`, similarity threshold cutoffs, and error sanitization.
    - **04D:** Implemented metadata filtering (`category`, `department`, `document status`) and version-aware selection (current active revision, historical effective-date lookups `effective_from <= date <= effective_until`, and overlap/ambiguity tracking).
    - **04E:** Implemented 5-tuple deterministic tie-breaking ranking, strict `chunk_id` deduplication, configurable result limits, and structured `EvidencePackage` formatting (`backend/app/schemas/retrieval.py`).
    - **04F:** Built ground-truth evaluation benchmark (`backend/tests/fixtures/retrieval_eval_dataset.py` + 5 retrieval test files totaling 47 retrieval tests) over the Northstar dataset: **100% Recall@5, 1.0000 MRR, 100% version accuracy, 100% irrelevant query rejection**. Added standalone verification script `backend/scripts/verify_retrieval.py`.

---

### ⏳ Remaining Tasks (Next to Build)

13. **TASK 05 — LangGraph RAG Orchestrator & State Graph (NEXT UP)**
    - Define `AgentState` TypedDict (`backend/app/graph/state.py`).
    - Implement 8 nodes: `node_query_understanding` (`llama-3.1-8b-instant`), `node_retrieve` (via `RetrievalService` / `match_policy_chunks`), `node_assess_evidence` (Groq `llama-3.3-70b-versatile` NLI sufficiency & conflict detection), `node_generate_answer` (strict grounded synthesis with `[Doc, Page X]`), `node_abstain` (safe refusal on insufficient evidence `< 0.65`), `node_resolve_conflict` (discrepancy banner), `node_validate_citations` (regex + page verification against retrieved chunks).
    - Configure LangGraph `PostgresSaver` checkpointer for multi-turn conversation memory.
14. **TASK 06 — Remaining FastAPI Endpoints**
    - `GET /api/v1/documents` (document catalog listing with active versions & page counts).
    - `POST /api/v1/chat` (executes LangGraph pipeline, returns answer, citations, conflict flags, evidence status).
    - `POST /api/v1/feedback` (records binary `+1`/`-1` on `messages` and forwards to Langfuse).
    - Global exception handlers & response middleware.
15. **TASK 07 — Frontend SPA (React 18 + TypeScript + Vite + Tailwind CSS)**
    - Document Management view (upload, status badge, metadata), Conversational Chat UI, Interactive Citation popover, Policy Conflict Alert banner, Safe Abstention notice, Feedback buttons.
16. **TASK 08 — Evaluation (RAGAS & Pytest) & Observability (Langfuse)**
    - Wrap Groq LLM & retrieval calls in Langfuse spans.
    - Build 50-pair enterprise golden evaluation dataset (`tests/eval_dataset.json`).
    - Automated RAGAS runner (Faithfulness $\ge 0.90\text{–}0.95$, Answer Relevance $\ge 0.85\text{–}0.90$, Context Precision $\ge 0.80\text{–}0.88$) + deterministic Pytest integration suite.
17. **TASK 09 — Deployment & Final E2E Verification**
    - Dockerize FastAPI backend for **Render**; deploy React SPA to **Vercel**; validate E2E journeys and write production runbook.

---

## 8. Currently Implemented API Endpoints

| Method | Endpoint | Description | Status |
|---|---|---|---|
| `GET` | `/` | Root service index | `200 OK` |
| `GET` | `/health` | Core app health probe | `200 OK` |
| `GET` | `/health/db` | PostgreSQL connectivity check (`SELECT 1` + latency) | `200` / `503` |
| `GET` | `/api/v1/health` | Versioned API health probe | `200 OK` |
| `POST` | `/api/v1/documents/upload` | Multipart upload (PDF/DOCX/TXT), magic-byte validation, Supabase Storage + DB metadata (optional `auto_process=true`) | `201 Created` |
| `POST` | `/api/v1/documents/{document_id}/extract` | Download from Storage & extract structured text / 1-based PDF pages | `200 OK` |
| `POST` | `/api/v1/documents/{document_id}/chunk` | Structure-aware chunking with section hierarchy & table splitting | `200 OK` |
| `POST` | `/api/v1/documents/{document_id}/embed` | Generate 384d L2-normalized MiniLM embeddings | `200 OK` |
| `POST` | `/api/v1/documents/{document_id}/persist` | Extract, chunk, embed, and atomically persist to `pgvector` | `200 OK` |
| `POST` | `/api/v1/ingestion/{document_id}/process` | Trigger async background ingestion coordinator (concurrency-guarded) | `202 Accepted` |
| `GET` | `/api/v1/ingestion/{job_id}` | Poll ingestion job status, metrics, and timings | `200` / `404` |
| `GET` | `/api/v1/ingestion/document/{document_id}` | Get latest ingestion job for a document | `200` / `404` |
| `GET` | `/docs` / `/redoc` | Interactive Swagger & ReDoc documentation | `200 OK` |

---

## 9. Repository Structure Overview

```text
KnowBridge AI/
├── backend/
│   ├── app/
│   │   ├── api/routes/          # health.py, documents.py, ingestion.py
│   │   ├── core/                # config.py (Pydantic BaseSettings), database.py (SQLAlchemy + psycopg3)
│   │   ├── models/              # document.py, document_version.py, document_chunk.py, ingestion_job.py
│   │   ├── parsers/             # base.py, pdf_parser.py, docx_parser.py, txt_parser.py
│   │   ├── schemas/             # document.py, extraction.py, chunking.py, embedding.py, persistence.py, ingestion.py, retrieval.py
│   │   ├── services/            # document_service.py, storage_service.py, document_extractor.py,
│   │   │                        # document_chunker.py, embedding_service.py, chunk_persistence.py,
│   │   │                        # ingestion_service.py, retrieval_service.py
│   │   └── main.py              # FastAPI entrypoint
│   ├── migrations/              # 000_full_migration.sql, 001_initial_schema.sql, 002_indexes_and_functions.sql, validate_schema.sql
│   ├── scripts/                 # verify_storage_integration.py, verify_extraction_integration.py, verify_chunking.py,
│   │                            # inspect_chunks.py, verify_embeddings.py, verify_live_persistence.py, verify_retrieval.py
│   ├── tests/                   # 15+ test modules + fixtures/retrieval_eval_dataset.py
│   ├── pytest.ini
│   ├── requirements.txt
│   └── .env.example
├── docs/                        # SYSTEM_DESIGN.md, DATA_FLOW.md, DATABASE_DESIGN.md, DECISIONS.md
├── scripts/                     # Synthetic Northstar policy dataset generators (PDF, DOCX, TXT)
├── synthetic-data/              # 13 synthetic policy files + metadata/manifest.csv
├── BUSINESS_CONTEXT.md
├── PRD.md
├── MVP_SCOPE.md
├── FUNCTIONAL_REQUIREMENTS.md
├── NON_FUNCTIONAL_REQUIREMENTS.md
├── USER_JOURNEYS.md
├── TASKS.md
├── backlog.md
├── current_status.md
└── README.md
```
