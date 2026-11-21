# KnowBridge AI — Functional Requirements Specification

**Document Version:** 1.0.0  
**Author:** Senior Product Architect & AI Engineering Lead  
**Status:** Under Review (Task 01 Specification)  
**Target Systems:** Enterprise Knowledge Management & RAG Platform  

---

## 1. Capability Matrix & Requirements Hierarchy

The functional architecture of KnowBridge AI is organized across nine core functional modules:

```
  ┌────────────────────────────────────────────────────────────────────────┐
  │                   FUNCTIONAL ARCHITECTURE MODULES                      │
  ├────────────────────────────────────┬───────────────────────────────────┤
  │ FR-1: Document Intelligence        │ FR-6: Answerability & Abstention  │
  │ FR-2: Semantic Hybrid Retrieval    │ FR-7: Conversational Memory       │
  │ FR-3: Version & Temporal Engine    │ FR-8: RAG Evaluation (RAGAS)      │
  │ FR-4: Policy Conflict Detection    │ FR-9: Observability (Langfuse)    │
  │ FR-5: Grounded Citation Engine     │                                   │
  └────────────────────────────────────┴───────────────────────────────────┘
```

---

## FR-1: Enterprise Document Intelligence & Ingestion

### FR-1.1: Multi-Format Document Parsing
- **Description:** The system shall ingest and extract structured text, metadata, headers, tables, and page boundaries from enterprise document formats.
- **Supported Formats:** PDF (native text and scanned), Microsoft Word (`.docx`), Markdown (`.md`), HTML.
- **Implementation Mechanism:** Layout-aware document parsing engine (e.g., PyMuPDF / unstructured / layoutlm) capable of retaining page numbers and physical document coordinates.
- **Inputs:** Raw binary document file + optional administrator metadata tags.
- **Outputs:** Standardized JSON Document Representation:
  ```json
  {
    "document_id": "doc_uuid_v4",
    "filename": "Travel_Policy_2024.pdf",
    "total_pages": 42,
    "pages": [
      {
        "page_number": 1,
        "text": "...",
        "tables": [{"headers": [], "rows": [[]]}],
        "headers": ["1. Introduction", "1.1 Scope"]
      }
    ]
  }
  ```
- **MVP Status:** Mandatory for Native PDF and DOCX. Scanned OCR is Phase 2.

### FR-1.2: Page-Preserving Hierarchical Chunking
- **Description:** The system shall partition documents into semantically coherent chunks while strictly preserving page-level provenance.
- **Chunking Rules:**
  - Target chunk size: $400 - 600$ tokens.
  - Chunk overlap: $50 - 100$ tokens.
  - Hard constraint: Chunks must never cross document boundaries; when a chunk spans across page boundaries, both page numbers must be stored (`page_start`, `page_end`).
  - Table Preservation: Tables must be linearized into Markdown format and kept intact within a single chunk whenever under 800 tokens.
- **User Story:** *As an engineer, I want chunks to retain their exact source page number so that retrieved snippets can be traced to a specific page.*
- **Acceptance Criteria:**
  ```gherkin
  Scenario: Page number preservation during chunking
    Given a 10-page PDF document
    When the document is chunked
    Then every chunk object must contain "page_number" matching its source page
    And no chunk may have a null or undefined "page_number"
  ```

---

## FR-2: Policy-Aware Semantic Retrieval

### FR-2.1: Hybrid Dense-Sparse Retrieval
- **Description:** The retrieval pipeline shall combine dense semantic vector embeddings with sparse lexical keyword matching (BM25) using Reciprocal Rank Fusion (RRF) to ensure both conceptual understanding and exact term matching (e.g., acronyms, section numbers).
- **Dense Vector Search:** High-dimensional dense embeddings (e.g., `text-embedding-3-large` or `bge-large-en-v1.5`), indexed via HNSW index with Cosine similarity.
- **Sparse Lexical Search:** BM25 inverted index for exact keyword matching (e.g., *"Form 1099-B"*, *"ISO-27001 Section 4.2"*).
- **RRF Formula:**
  $$\text{Score}(d) = \sum_{m \in \{\text{dense}, \text{sparse}\}} \frac{1}{k + r_m(d)} \quad (k = 60)$$
- **MVP Status:** Mandatory.

### FR-2.2: Cross-Encoder Re-Ranking
- **Description:** Following hybrid retrieval of the top $N = 30$ candidate chunks, a Cross-Encoder re-ranker (e.g., `bge-reranker-large` or `cohere-rerank-v3`) shall compute deep query-document relevance scores, outputting the top $K = 5$ chunks for synthesis.
- **Re-Ranking Cutoff:** Chunks with re-ranker score $< 0.50$ are discarded before generation.
- **Acceptance Criteria:**
  ```gherkin
  Scenario: Re-ranking retrieved candidates
    Given 30 candidate chunks retrieved via hybrid search
    When the cross-encoder re-ranker processes the candidates
    Then it must output the top 5 chunks sorted by joint semantic relevance
    And any chunk with a relevance score below 0.50 must be filtered out
  ```

---

## FR-3: Document Version & Effective-Date Awareness

### FR-3.1: Temporal Metadata Ingestion
- **Description:** Every ingested document must have an associated temporal schema:
  - `version_id`: Semantic version string (e.g., `"v3.2"`).
  - `effective_date`: ISO 8601 Date (`"YYYY-MM-DD"`) on which the policy becomes active.
  - `sunset_date`: Optional ISO 8601 Date (`"YYYY-MM-DD"`) on which the policy expires.
  - `status`: Enum (`"DRAFT"`, `"ACTIVE"`, `"SUPERSEDED"`, `"DEPRECATED"`).
  - `supersedes_doc_id`: UUID of the previous document version replaced by this document.
- **Extraction Logic:** Automatic regex and LLM extraction from cover pages and headers during ingestion; requires human confirmation in Admin UI if confidence $< 0.90$.

### FR-3.2: Temporal Query Filtering & Historical Auditing
- **Description:** The retrieval engine shall apply deterministic metadata filtering based on the query's temporal target.
- **Query Temporal Modes:**
  1. **Current Operational (Default):** Filter enforces:
     $$\text{effective\_date} \le \text{CURRENT\_DATE} \quad \land \quad (\text{sunset\_date} \text{ IS NULL} \lor \text{sunset\_date} \ge \text{CURRENT\_DATE})$$
  2. **Historical Point-in-Time:** When the user explicitly asks about a past date (e.g., *"What was the policy in June 2022?"*), the query parser extracts `target_date = 2022-06-01` and retrieves documents active at that specific instant.
  3. **Upcoming Changes:** Identifies policies where `effective_date > CURRENT_DATE` and appends a forward-looking advisory note to the user.
- **Acceptance Criteria:**
  ```gherkin
  Scenario: Filtering out superseded policies
    Given a superseded policy v1.0 (sunset 2023-12-31) and an active policy v2.0 (effective 2024-01-01)
    When an employee queries current maternity leave on 2024-11-21
    Then the retrieval query must strictly exclude chunks from v1.0
    And only chunks from v2.0 may be passed to the LLM generator
  ```

---

## FR-4: Policy Conflict & Contradiction Detection

### FR-4.1: Cross-Evidence Natural Language Inference (NLI)
- **Description:** Before generating a final answer, the retrieved top chunks shall be evaluated for mutual consistency to prevent synthesizing contradictory guidance into false consensus.
- **Contradiction Detection Algorithm:**
  - Extract factual assertions / policy rules from each retrieved chunk.
  - Run pairwise NLI classification:
    $$\text{NLI}(\text{Chunk}_A, \text{Chunk}_B) \in \{\text{Entailment}, \text{Contradiction}, \text{Neutral}\}$$
  - When $\text{Confidence}(\text{Contradiction}) \ge 0.75$, the contradiction flag `CONFLICT_DETECTED` is raised.
- **MVP Status:** Mandatory using LLM-based pairwise zero-shot NLI verification.

### FR-4.2: Structured Conflict Warning Output
- **Description:** When a policy conflict is detected, the system shall not pick one policy arbitrarily or merge them. Instead, it must return a structured response detailing:
  1. The specific conflicting clauses.
  2. The source document and page number for each clause.
  3. The differing jurisdictional, departmental, or temporal scopes if available.
  4. An escalation recommendation to HR/Legal.
- **Acceptance Criteria:**
  ```gherkin
  Scenario: Formatting conflicting policy output
    Given Chunk A specifies "$500 stipend" and Chunk B specifies "$1,200 stipend"
    When the conflict detector raises CONFLICT_DETECTED
    Then the final response must render a "Policy Conflict Alert"
    And the response must quote both "$500" from Chunk A and "$1,200" from Chunk B
    And both sources must be cited with document names and page numbers
  ```

---

## FR-5: Evidence-Grounded Responses with Page-Level Citations

### FR-5.1: Strict Provenance Generation Prompt
- **Description:** The system shall enforce a strict zero-hallucination prompt contract. The LLM must be instructed that:
  - It may only assert statements directly entailed by the provided context.
  - Every single assertion, rule, or numerical figure must be followed by an inline citation token: `[Doc_Title, Page X]`.
  - External pre-training knowledge must never be used to supplement missing facts.
- **Prompt Guardrail Contract:**
  ```
  SYSTEM: You are the KnowBridge AI Enterprise Policy Assistant. 
  Answer the question using ONLY the provided text snippets below. 
  For every fact or number you state, you MUST append an inline citation in the exact format: [Document_Title, Page X].
  If the text snippets do not explicitly contain the answer, you MUST state that you do not know. 
  Do NOT guess, extrapolate, or use outside knowledge.
  ```

### FR-5.2: Structured Citation Payload & Deep-Linking
- **Description:** Alongside the text stream, the API must return an array of structured citation metadata objects allowing the frontend UI to render interactive citation chips and deep-link directly into the PDF preview:
  ```json
  {
    "answer": "London hotel reimbursement is capped at £250/night [Global_Travel_Policy.pdf, Page 14].",
    "citations": [
      {
        "citation_id": 1,
        "document_id": "doc_104",
        "document_title": "Global_Travel_Policy.pdf",
        "page_number": 14,
        "chunk_text_snippet": "Tier 1 International Cities (London, Tokyo): Hotel cap £250...",
        "bounding_box": {"x1": 45.2, "y1": 112.0, "x2": 450.0, "y2": 160.5}
      }
    ]
  }
  ```
- **MVP Status:** Mandatory for page numbers. Bounding-box highlights are Phase 2.

---

## FR-6: Answerability Assessment & Safe Abstention

### FR-6.1: Dual-Stage Gating (Pre-Retrieval & Post-Retrieval)
- **Description:** The system shall determine whether an incoming query can be answered reliably before producing generative output.
- **Pre-Retrieval Gate:** Rejects gibberish, out-of-domain general chitchat, or explicit jailbreak attempts via a lightweight classifier.
- **Post-Retrieval Sufficiency Gate:** Evaluates whether the retrieved context contains sufficient semantic information to answer the user's intent.
  - Metric: $\text{Sufficiency\_Score} \in [0.0, 1.0]$.
  - If $\text{Sufficiency\_Score} < 0.65$, generation is aborted.

### FR-6.2: Deterministic Abstention Templates
- **Description:** When sufficiency fails, the system outputs a standardized, polite abstention response, never a hallucinated guess.
- **Standard Abstention Format:**
  > *"I am sorry, but the currently available enterprise documentation does not contain sufficient information to answer your question: '{user_query}'.*  
  > *Please contact your department administrator or the Knowledge Management team to request documentation on this topic."*
- **Acceptance Criteria:**
  ```gherkin
  Scenario: Safe abstention on missing topic
    Given a query asking about "Executive stock option vesting schedules"
    And no retrieved chunks exceed a re-ranking relevance score of 0.50
    When the answerability gate runs
    Then the status must be set to UNANSWERABLE
    And the system must return the standardized safe abstention message
    And no citations may be fabricated
  ```

---

## FR-7: Conversational & Persistent Session Memory

### FR-7.1: Multi-Turn Query Contextualization
- **Description:** The system shall support continuous multi-turn dialogue, allowing users to ask follow-up questions referencing previous concepts, pronouns, and constraints.
- **Core Algorithm:** Query Re-Writing / Contextualization:
  - Input: Current Turn $Q_t$ + Conversation History $\{Q_{t-1}, A_{t-1}, \dots, Q_{t-k}, A_{t-k}\}$ (last $k=3$ turns).
  - Transformation: A specialized LLM call rewrites $Q_t$ into a standalone, de-referenced query $Q'_t$ suitable for semantic retrieval without losing conversational intent.
  - Example:
    - History: *"What is the parental leave policy?"* $\to$ *"12 weeks."*
    - User Follow-up: *"Does it apply to adoptive parents?"*
    - Contextualized Query: *"Does the enterprise parental leave policy apply to adoptive parents?"*

### FR-7.2: Persistent Session Storage
- **Description:** Session state, message history, retrieved chunk IDs, and entity context shall persist across user browser sessions.
- **Storage Architecture:**
  - Active Session Cache: Redis (TTL: 24 hours).
  - Permanent Archive: PostgreSQL (Session and Message tables).
- **MVP Status:** Mandatory for Redis active session buffer; PostgreSQL historical query search is Phase 2.

---

## FR-8: Automated RAG Evaluation using RAGAS

### FR-8.1: Golden Dataset Ingestion & Synthetic Test Generation
- **Description:** The system shall include an automated evaluation harness powered by RAGAS (`ragas` Python library) to assess pipeline accuracy and detect regressions.
- **Harness Dataset:** A curated golden dataset of at least 50 representative enterprise Q&A pairs with ground-truth answers and ground-truth source page contexts.

### FR-8.2: Core RAGAS Metrics Evaluation
- **Description:** The harness shall compute the following four primary metrics:
  1. **Faithfulness:** Ratio of claims in the generated response that can be directly deduced from the retrieved context. (Threshold: $\ge 0.95$).
  2. **Answer Relevance:** Semantic alignment between generated answer and original query. (Threshold: $\ge 0.90$).
  3. **Context Precision:** Ratio of relevant chunks found in the top-K retrieved context. (Threshold: $\ge 0.88$).
  4. **Context Recall:** Ratio of ground-truth factual points captured within retrieved context. (Threshold: $\ge 0.85$).
- **CI/CD Quality Gate:** Evaluation script callable via CLI:
  ```bash
  ragas-eval --config eval_config.yaml --output report.json
  ```
  Returns exit code `1` if any metric falls below its specified threshold, blocking deployment.

---

## FR-9: LLM Observability & Tracing with Langfuse

### FR-9.1: Distributed Trace Instrumentation
- **Description:** Every query lifecycle must emit structured nested spans to Langfuse using the Langfuse SDK or OpenTelemetry exporter.
- **Span Hierarchy:**
  ```
  [Trace: user_query_request]
    ├── [Span: memory_contextualize_query] (inputs, outputs, latency, tokens)
    ├── [Span: hybrid_retrieval] (query, dense_k, sparse_k, returned_chunks)
    ├── [Span: cross_encoder_rerank] (input_chunks, scores, filtered_chunks)
    ├── [Span: temporal_filter] (active_date, filtered_count)
    ├── [Span: conflict_detection] (nli_pairs, classification, conflict_flag)
    ├── [Span: answerability_gate] (sufficiency_score, decision)
    └── [Generation: llm_answer_synthesis] (model, temperature, prompt, completion, token_cost)
  ```

### FR-9.2: Metadata, Cost & Feedback Attribution
- **Description:** Traces must record:
  - `user_id` (hashed/anonymized for privacy), `session_id`.
  - Model parameters (`model_name`, `temperature`, `max_tokens`).
  - Precise token counts (`prompt_tokens`, `completion_tokens`, `total_tokens`) and calculated USD financial cost.
  - End-to-end execution latency per step.
  - User Feedback Score: API endpoint to attach binary feedback (`thumbs_up: 1` or `thumbs_down: 0`) and optional user comments to the exact Langfuse trace ID.
- **MVP Status:** Mandatory.
