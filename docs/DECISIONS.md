# KnowBridge AI — Architecture Decision Records (ADRs)

**Document Version:** 1.0.0  
**Status:** Approved Baseline (Task 02 Specification)  
**Author:** Senior Software Architect & AI Engineer  
**Target Systems:** Enterprise Knowledge Intelligence Platform  

---

## Index of Architecture Decision Records

- [ADR-001: Monolithic FastAPI Service Topology](#adr-001-monolithic-fastapi-service-topology)
- [ADR-002: Supabase PostgreSQL with pgvector as Unified Data & Vector Store](#adr-002-supabase-postgresql-with-pgvector-as-unified-data--vector-store)
- [ADR-003: LangGraph for Stateful RAG Orchestration](#adr-003-langgraph-for-stateful-rag-orchestration)
- [ADR-004: Groq Cloud API for High-Speed Inference](#adr-004-groq-cloud-api-for-high-speed-inference)
- [ADR-005: Local Hugging Face Sentence-Transformers Embeddings](#adr-005-local-hugging-face-sentence-transformers-embeddings)
- [ADR-006: PostgreSQL Checkpointing & Session Memory over Redis](#adr-006-postgresql-checkpointing--session-memory-over-redis)
- [ADR-007: Explicit Exclusion of Authentication and Authorization for MVP](#adr-007-explicit-exclusion-of-authentication-and-authorization-for-mvp)
- [ADR-008: PyMuPDF for Page-Preserving Document Processing](#adr-008-pymupdf-for-page-preserving-document-processing)
- [ADR-009: RAGAS and Pytest Dual-Layer Quality Assurance](#adr-009-ragas-and-pytest-dual-layer-quality-assurance)
- [ADR-010: Langfuse for Full-Stack LLM Observability & Tracing](#adr-010-langfuse-for-full-stack-llm-observability--tracing)

---

### ADR-001: Monolithic FastAPI Service Topology
- **Status:** Accepted (Finalized for MVP)
- **Context:** Enterprise RAG applications often face premature architectural complexity when split across multiple microservices (e.g., ingestion service, retrieval service, LLM proxy, memory service). For a focused 10-hour MVP build, microservices introduce cross-service network latency, complex serialization, Docker orchestrator overhead, and distributed debugging challenges.
- **Decision:** Implement the KnowBridge AI backend as a single, modular **FastAPI** monolith. Modules are logically separated into discrete directories (`app/services/ingestion.py`, `app/graph/`, `app/api/v1/`), maintaining strict internal interface boundaries.
- **Consequences:**
  - *Positive:* Drastically simplifies local development, eliminates inter-service RPC overhead, enables single-container deployment to Render, and accelerates development velocity.
  - *Trade-off:* All backend capabilities scale together rather than independently; heavy PDF parsing could momentarily compete with query processing on a single CPU core (mitigated via background tasks).

---

### ADR-002: Supabase PostgreSQL with pgvector as Unified Data & Vector Store
- **Status:** Accepted (Finalized for MVP)
- **Context:** RAG platforms require both relational metadata storage (document hierarchies, versions, dates, conversation history) and vector similarity indexing. Using separate databases (e.g., PostgreSQL for data and Pinecone/Qdrant/Weaviate for vectors) introduces dual-database consistency issues, distributed transactions, and two billing accounts.
- **Decision:** Utilize **Supabase PostgreSQL** with the **`pgvector`** extension as the single datastore for relational entities, binary storage pointers, and high-dimensional vector embeddings with HNSW indexing.
- **Consequences:**
  - *Positive:* Enables single-query hybrid joins (`JOIN document_versions ON ... WHERE effective_date <= ... ORDER BY embedding <=> query`), transactional atomic inserts for chunks and versions, and zero synchronization drift.
  - *Trade-off:* pgvector HNSW memory usage resides in PostgreSQL shared buffers. For an MVP scale ($<100{,}000$ chunks), this is exceptionally lightweight ($<1\text{ GB RAM}$).

---

### ADR-003: LangGraph for Stateful RAG Orchestration
- **Status:** Accepted (Finalized for MVP)
- **Context:** Standard naive RAG pipelines utilize linear execution chains (e.g., LangChain `RetrievalQA` or LlamaIndex query engines). However, enterprise policy retrieval requires non-linear control flow: conditional branches for safe abstention, pairwise contradiction detection loops, multi-turn query reformulation, and citation post-validation.
- **Decision:** Orchestrate the RAG lifecycle using **LangGraph** (`StateGraph`). All state is typed using a centralized `AgentState` schema, and execution routes through conditional edges based on evidence sufficiency and contradiction flags.
- **Consequences:**
  - *Positive:* Provides a transparent state machine where each node has a single responsibility. Natively integrates with Postgres state checkpointers.
  - *Trade-off:* Requires learning LangGraph's state manipulation paradigms compared to basic sequential prompt templates.

---

### ADR-004: Groq Cloud API for High-Speed Inference
- **Status:** Accepted (Finalized for MVP)
- **Context:** RAG systems with multiple reasoning steps (query rewrite, NLI contradiction check, generation) can suffer from compounding latency if standard LLM APIs (15–30 tokens/second) are used. P95 latency must remain under 3.0 seconds.
- **Decision:** Use **Groq Cloud API** running `llama-3.3-70b-versatile` (or `llama-3.1-8b-instant` for query reformulation). Groq's LPU hardware delivers sustained inference speeds $>250\text{ tokens/second}$.
- **Consequences:**
  - *Positive:* Slashes LLM generation latency to $<800\text{ ms}$, ensuring snappy conversational turns and responsive multi-step NLI evaluations.
  - *Trade-off:* Dependence on Groq Cloud availability and rate limits; mitigated by abstracting the LLM client via standard LangChain ChatGroq interfaces for easy fallback.

---

### ADR-005: Local Hugging Face Sentence-Transformers Embeddings
- **Status:** Accepted (Finalized for MVP)
- **Context:** Generating embeddings via cloud APIs (e.g., OpenAI or Cohere) introduces external network round-trips for every ingested chunk and every user query, in addition to recurring API costs.
- **Decision:** Run **`sentence-transformers/all-MiniLM-L6-v2`** (384 dimensions) locally in-process on CPU within the FastAPI backend container.
- **Consequences:**
  - *Positive:* Zero embedding API costs, zero network latency for vectorization, complete offline determinism, and instant embeddings ($<15\text{ ms}$ on CPU for standard queries).
  - *Trade-off:* Adds ~120MB model weight footprint to the backend container memory and slightly lower semantic capacity compared to massive 1536d or 3072d models (well-compensated by cross-encoder and exact filtering).

---

### ADR-006: PostgreSQL Checkpointing & Session Memory over Redis
- **Status:** Accepted (Finalized for MVP)
- **Context:** The initial high-level PRD mentioned Redis as a conceptual session cache. However, running a Redis cluster alongside Supabase PostgreSQL introduces an additional infrastructure component, connection pooling logic, and maintenance overhead for a 10-hour MVP build.
- **Decision:** Consolidate conversational session checkpointing into **Supabase PostgreSQL** using LangGraph's native PostgreSQL checkpointer (`PostgresSaver`) and store long-term user memories in a relational `user_memories` table.
- **Consequences:**
  - *Positive:* Eliminates Redis dependency completely from the MVP. Simplifies local and cloud deployment.
  - *Trade-off:* In-database checkpoint reads add minimal SQL overhead ($\sim 5\text{ ms}$), well within our 150ms memory latency budget.

---

### ADR-007: Explicit Exclusion of Authentication and Authorization for MVP
- **Status:** Accepted (Finalized for MVP)
- **Context:** Implementing robust enterprise authentication (SSO, OAuth2, JWTs) and fine-grained authorization (Supabase RLS, RBAC, tenant isolation) consumes significant engineering time without contributing to core RAG grounding, conflict detection, or temporal retrieval capabilities.
- **Decision:** Explicitly exclude all authentication, registration, login, JWT validation, and Supabase RLS from the MVP. The system operates as a single-workspace development platform. The database schema maintains future-compatible foreign keys (e.g., `organizations`), but no auth gates are enforced.
- **Consequences:**
  - *Positive:* Frees 100% of engineering bandwidth to perfect document intelligence, citation accuracy, conflict resolution, and evaluation.
  - *Trade-off:* System must not be exposed to open public networks without basic HTTP auth or VPN encapsulation until Phase 2.

---

### ADR-008: PyMuPDF for Page-Preserving Document Processing
- **Status:** Accepted (Finalized for MVP)
- **Context:** Accurate, page-level citation anchors require the ingestion parser to accurately detect and associate physical PDF page numbers with every extracted text block and table. Many high-level PDF libraries scramble text order or discard page indices during parsing.
- **Decision:** Standardize on **PyMuPDF (`fitz`)** for native PDF extraction, table linearization, and physical page tracking.
- **Consequences:**
  - *Positive:* Extremely fast C-based parsing engine, zero external cloud service dependencies, precise physical page mapping, and robust table extraction.
  - *Trade-off:* Does not perform optical character recognition (OCR) on pure scanned bitmap images (deferred to Phase 2).

---

### ADR-009: RAGAS and Pytest Dual-Layer Quality Assurance
- **Status:** Accepted (Finalized for MVP)
- **Context:** Generative AI systems require continuous validation against regressions in faithfulness and relevance. Traditional unit tests alone cannot assess LLM semantic fidelity, while LLM evaluation frameworks can be non-deterministic and slow.
- **Decision:** Implement a two-tiered testing strategy:
  1. **Deterministic Pytest Suite:** Asserts API response contracts, citation regex formatting, chunk page boundaries, and safe abstention status flags.
  2. **RAGAS Benchmark Harness:** Evaluates a 50-pair golden enterprise dataset on **Faithfulness**, **Answer Relevance**, **Context Precision**, and **Context Recall**, failing CI/CD if thresholds are breached.
- **Consequences:**
  - *Positive:* High-confidence deployments, automated detection of prompt drift or retrieval degradation, and compliance-grade auditability.
  - *Trade-off:* Running full RAGAS evaluation suites incurs Groq LLM token usage (run in CI/CD on pull requests and nightly builds).

---

### ADR-010: Langfuse for Full-Stack LLM Observability & Tracing
- **Status:** Accepted (Finalized for MVP)
- **Context:** Production RAG pipelines involve multiple asynchronous operations (retrieval, re-ranking, NLI, generation). When an answer fails or latency spikes, engineers need immediate introspection into every intermediate step without grepping raw container logs.
- **Decision:** Integrate **Langfuse Cloud** via its Python SDK. Every user query spawns a root trace with nested child spans for query rewriting, pgvector retrieval, NLI assessment, and LLM synthesis, capturing token counts, USD cost, latency, and user feedback attribution.
- **Consequences:**
  - *Positive:* Production-grade observability out of the box, open-source compatibility, granular cost and latency analytics, and zero-overhead asynchronous telemetry.
  - *Trade-off:* Requires outbound HTTPS network egress from the backend container to Langfuse Cloud.
