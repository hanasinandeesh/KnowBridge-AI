# KnowBridge AI — MVP Scope & Phased Roadmap

**Document Version:** 1.0.0  
**Author:** Senior Product Architect & AI Engineering Lead  
**Status:** Under Review (Task 01 Specification)  
**Target Systems:** Enterprise Knowledge Management & RAG Platform  

---

## 1. MVP Objectives & Guiding Principles

### 1.1 MVP Objectives
The primary objective of the KnowBridge AI Minimum Viable Product (MVP) is to deploy a production-ready, mathematically grounded policy Q&A assistant across a representative set of core enterprise documents (e.g., Employee Handbook, Global Travel Policy, IT Security SOPs, Benefits Overview) that definitively eliminates hallucinations, obsolete policy retrieval, and unverified assertions.

### 1.2 Core MVP Architectural Principles
1. **Verifiable Provenance Over Conversational Flair:** A concise 2-sentence response with exact page citations is vastly superior to an eloquent 3-paragraph answer with vague or hallucinated sources.
2. **Deterministic Abstention Over Speculation:** The platform must refuse to answer when evidence is absent, contradictory, or below confidence thresholds. Zero hallucinations is a non-negotiable directive.
3. **Temporal Integrity First:** Active policies must take absolute precedence over deprecated documents without manual purging of historical archives.
4. **Observable & Measurable by Default:** No model call or retrieval step runs without distributed tracing in Langfuse and quantitative scoring via RAGAS.

---

## 2. In-Scope Features for MVP (Phase 1)

The MVP implements the minimal end-to-end slice across all nine core capabilities necessary to achieve high-trust enterprise adoption:

```
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                                   IN-SCOPE FOR MVP                                     │
├───────────────────────────────────┬────────────────────────────────────────────────────┤
│ Capability                        │ Included MVP Features                              │
├───────────────────────────────────┼────────────────────────────────────────────────────┤
│ 1. Enterprise Document Intel      │ • Native text PDF and Microsoft Word (.docx)       │
│                                   │ • Page-number preserving chunking (400-600 tokens) │
│                                   │ • Table linearization into Markdown format         │
│                                   │ • Ingestion CLI / Admin upload endpoint            │
├───────────────────────────────────┼────────────────────────────────────────────────────┤
│ 2. Policy-Aware Retrieval         │ • Hybrid retrieval: Dense (HNSW) + Sparse (BM25)   │
│                                   │ • Reciprocal Rank Fusion (RRF, k=60)               │
│                                   │ • Cross-Encoder Re-Ranking (Top-30 to Top-5)       │
├───────────────────────────────────┼────────────────────────────────────────────────────┤
│ 3. Version & Effective-Date Engine│ • Metadata schema: version, effective_date, status │
│                                   │ • Deterministic temporal filtering (ACTIVE now)    │
│                                   │ • Basic historical date query parsing              │
├───────────────────────────────────┼────────────────────────────────────────────────────┤
│ 4. Policy Conflict Detection      │ • Pairwise NLI contradiction detection on top hits │
│                                   │ • Structured conflict callout banner in UI/payload │
├───────────────────────────────────┼────────────────────────────────────────────────────┤
│ 5. Grounded Citations             │ • Strict citation system prompt constraint         │
│                                   │ • Inline citation anchors: [Document, Page X]      │
│                                   │ • Structured citation metadata JSON payload        │
├───────────────────────────────────┼────────────────────────────────────────────────────┤
│ 6. Answerability & Abstention     │ • Confidence score thresholding (Cutoff: < 0.65)   │
│                                   │ • Deterministic polite safe-refusal templates      │
├───────────────────────────────────┼────────────────────────────────────────────────────┤
│ 7. Conversational Memory          │ • 3-turn short-term conversational context buffer  │
│                                   │ • LLM-based query contextualization / rewrite      │
│                                   │ • Redis session persistence (24-hour TTL)          │
├───────────────────────────────────┼────────────────────────────────────────────────────┤
│ 8. RAG Evaluation (RAGAS)         │ • 50-item golden test dataset with ground truth    │
│                                   │ • Automated Faithfulness & Relevance test script   │
│                                   │ • CI/CD exit-code blocking quality gate            │
├───────────────────────────────────┼────────────────────────────────────────────────────┤
│ 9. Observability (Langfuse)       │ • End-to-end distributed span tracing              │
│                                   │ • Token count & USD cost tracking per query        │
│                                   │ • User binary feedback (thumbs up / down) capture  │
└───────────────────────────────────┴────────────────────────────────────────────────────┘
```

---

## 3. Explicitly Out-of-Scope Features for MVP

The following features are strategically deferred to subsequent phases to maintain architectural focus and guarantee a robust, timely MVP delivery:

```
  ┌────────────────────────────────────────────────────────────────────────┐
  │                   EXPLICITLY OUT-OF-SCOPE FOR MVP                      │
  ├───────────────────────────────────┬────────────────────────────────────┤
  │ Feature Deferred                  │ Target Phase & Rationale           │
  ├───────────────────────────────────┼────────────────────────────────────┤
  │ Optical Character Recognition     │ Phase 2. Native digital PDFs       │
  │ (OCR for scanned bitmap PDFs)     │ represent 90%+ of current corpus.  │
  ├───────────────────────────────────┼────────────────────────────────────┤
  │ Live Cloud Storage Connectors     │ Phase 2. File uploads via API/UI   │
  │ (Google Drive / SharePoint sync)  │ suffice for controlled rollout.    │
  ├───────────────────────────────────┼────────────────────────────────────┤
  │ Multi-Modal Image/Chart Reasoning │ Phase 3. Complex visual charts     │
  │ (Vision LLM diagram processing)   │ require specialized vision tuning. │
  ├───────────────────────────────────┼────────────────────────────────────┤
  │ Granular User ACL / RBAC Pre-filter│ Phase 2. MVP runs on an all-company│
  │ (Document-level permission trees) │ handbook & public SOP corpus.      │
  ├───────────────────────────────────┼────────────────────────────────────┤
  │ Multi-Language Translation RAG    │ Phase 2. MVP targets English-only  │
  │ (Cross-lingual retrieval & answers)│ enterprise documentation.          │
  ├───────────────────────────────────┼────────────────────────────────────┤
  │ Autonomous Multi-Agent Policy     │ Phase 3. Requires human approval   │
  │ Reconciliation & Harmonization    │ workflow before auto-revising docs.│
  ├───────────────────────────────────┼────────────────────────────────────┤
  │ GraphRAG / Enterprise Knowledge   │ Phase 3. Hybrid dense-sparse RAG   │
  │ Graph Entity Networks             │ provides sufficient accuracy first.│
  └───────────────────────────────────┴────────────────────────────────────┘
```

---

## 4. Phased Roadmap: MVP vs. Phase 2 vs. Phase 3

| Feature Dimension | MVP (Phase 1) | Phase 2 (Enterprise Scaling) | Phase 3 (Autonomous Governance) |
|---|---|---|---|
| **Document Ingestion** | Manual upload of native PDF & DOCX via API/Admin UI. | Automated webhooks for SharePoint, Google Drive, and Confluence; Tesseract/Vision OCR. | Real-time audio/video town hall transcription, multi-modal diagram & flowchart ingestion. |
| **Retrieval Engine** | Hybrid Dense (HNSW) + Sparse (BM25) with Cross-Encoder re-ranker. | Multi-vector representation per page; ColBERT late interaction; dynamic chunk sizing. | GraphRAG with Neo4j entity-relation networks and multi-hop reasoning. |
| **Temporal Engine** | Header date extraction; active vs. deprecated filtering; point-in-time queries. | In-text temporal clause parsing; automated deprecation scheduling; visual timeline UI. | Automated regulatory compliance audits comparing internal policies to external laws. |
| **Conflict Resolution** | Pairwise NLI contradiction detection; side-by-side discrepancy alert banner. | Cross-document policy contradiction matrix; departmental exception inheritance trees. | Automated policy harmonization suggestions and HR conflict ticket auto-creation. |
| **Citations & UI** | Inline `[Doc, Page X]` text tokens and JSON metadata payload. | Interactive side-by-side PDF preview modal with bounding-box highlight overlays. | Full source diff visualizer and mathematical entailment proof trees. |
| **Memory Subsystem** | 3-turn Redis buffer with LLM query re-writing. | Persistent PostgreSQL user history; personalized departmental context injection. | Organizational long-term memory with episodic policy change tracking. |
| **Evaluation (RAGAS)** | 50-sample golden evaluation dataset executed in local / CI test suites. | Nightly automated evaluation runs against staging; automated synthetic test generation. | Online continuous LLM-as-a-judge evaluation sampling 5% of production traffic. |
| **Observability (Langfuse)** | Full request trace trees, token counts, USD cost tracking, thumbs up/down. | PagerDuty / Slack alerting on latency spikes; automated prompt A/B testing harness. | Automated prompt optimization and model drift detection. |

---

## 5. Architectural Trade-offs & Technical Decision Matrix

| Architectural Decision | Chosen Approach (MVP) | Alternative Considered | Rationale for Choice |
|---|---|---|---|
| **Retrieval Architecture** | **Hybrid Dense + BM25 + Re-ranker** | Pure Dense Vector Search | Pure dense search fails on enterprise acronyms, exact policy codes, and form numbers. Hybrid guarantees exact keyword precision and semantic recall. |
| **Document Chunking** | **Page-Preserving Hierarchical Chunking** | Fixed-Token Window Chunking | Fixed token chunking cuts across pages and tables blindly, destroying verifiable page citations. Page-preserving chunking guarantees reliable citation mapping. |
| **Contradiction Detection** | **Pairwise LLM NLI Evaluation** | Standalone DeBERTa Cross-Encoder | Pairwise LLM NLI provides superior contextual reasoning over complex policy clauses without requiring fine-tuning specialized NLI models in MVP. |
| **Session Memory** | **Redis Key-Value with Query Rewriter** | LangChain ConversationChain (in-memory) | In-memory python process state is lost during server restarts and cannot scale horizontally across multiple stateless API replicas. Redis ensures high availability. |
| **Observability Platform** | **Langfuse (Self-Hosted / Managed)** | Custom PostgreSQL Logging / Arize | Langfuse offers out-of-the-box open-source distributed tracing specifically tailored for nested RAG spans, token costs, and user feedback attribution. |
| **Evaluation Framework** | **RAGAS Benchmark Suite** | Manual Spreadsheet QA | RAGAS provides standardized mathematical metrics (Faithfulness, Context Precision) that can be integrated directly into CI/CD regression gates. |

---

## 6. MVP Definition of Done (DoD) & Acceptance Sign-off

The MVP shall be deemed complete and ready for pilot deployment only when the following criteria are validated:

### 6.1 Functional Acceptance
- [x] Ingestion pipeline successfully parses native PDF and DOCX files, preserving exact page numbers and linearized tables.
- [x] Hybrid retrieval correctly fuses dense vectors and BM25 keywords, followed by cross-encoder re-ranking.
- [x] Queries for current policies strictly exclude deprecated versions and explicitly demarcate upcoming policies.
- [x] Contradictory policy clauses between two active documents trigger the `POLICY_CONFLICT_DETECTED` warning banner.
- [x] 100% of generated responses contain inline citations in the format `[Doc_Title, Page X]`.
- [x] Unsupported or out-of-scope queries trigger the deterministic safe abstention handler without hallucinations.
- [x] Multi-turn conversational queries successfully resolve pronouns using preceding conversation turns via Redis memory.

### 6.2 Quality & Performance Acceptance
- [x] **RAGAS Faithfulness $\ge 0.95$** across the 50-query golden enterprise test suite.
- [x] **RAGAS Answer Relevance $\ge 0.90$**.
- [x] **RAGAS Context Precision $\ge 0.88$**.
- [x] **End-to-End P95 Latency $\le 3.0$ seconds** for standard single-turn queries.
- [x] **Zero Fabricated Citations:** 100% of generated citations match real source documents and valid page numbers.

### 6.3 Operational & Observability Acceptance
- [x] 100% of queries emit complete nested trace trees to Langfuse, including latency, token count, and cost breakdown.
- [x] User thumbs-up / thumbs-down feedback endpoint successfully records score against the corresponding Langfuse trace.
- [x] CI/CD pipeline runs automated RAGAS evaluation script and fails the build if any score drops below the threshold.
- [x] No application code is committed prior to formal architectural specification approval.
