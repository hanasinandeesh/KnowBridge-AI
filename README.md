# KnowBridge AI — Policy-Aware Enterprise Knowledge Intelligence Platform

[![Python](https://img.shields.io/badge/Python-3.11+-blue.svg)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.111.0-009688.svg)](https://fastapi.tiangolo.com/)
[![SQLAlchemy](https://img.shields.io/badge/SQLAlchemy-2.0-red.svg)](https://www.sqlalchemy.org/)
[![PostgreSQL](https://img.shields.io/badge/Supabase-PostgreSQL%2015+-336791.svg)](https://supabase.com/)
[![pgvector](https://img.shields.io/badge/pgvector-0.8.2-green.svg)](https://github.com/pgvector/pgvector)
[![License](https://img.shields.io/badge/License-Proprietary-yellow.svg)]()

KnowBridge AI is an enterprise-grade, policy-aware retrieval-augmented generation (RAG) platform designed to eliminate hallucinations, obsolete policy retrieval, and unverified assertions across complex organizational document corpora (handbooks, travel policies, benefits catalogs, IT security guidelines, and compliance SOPs).

---

## 🌟 Core Architectural Pillars

1. **Deterministic Temporal Validity:** Active policies take absolute operational precedence over superseded or draft revisions without manual deletion of historical documents.
2. **Mathematical Grounding & Strict Citations:** All generated statements are anchored to explicit physical page citations (`[Document Title, Page X]`).
3. **Cross-Document Contradiction Detection:** Pairwise Natural Language Inference (NLI) identifies and alerts users to conflicting clauses across retrieved policies.
4. **Autonomous Abstention:** The system politely and safely refuses to speculate when evidence is absent, insufficient, or below confidence thresholds ($< 0.65$).
5. **Session & Fact Memory:** Multi-turn conversation state persistence via PostgreSQL checkpointers and fact extraction.

---

## 🏗️ System Architecture

```
┌────────────────────────────────────────────────────────────────────────┐
│                              FRONTEND SPA                              │
│                React 18 + TypeScript + Vite + Tailwind CSS             │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │ HTTPS / REST
┌───────────────────────────────────▼────────────────────────────────────┐
│                          FASTAPI BACKEND CORE                          │
│  app/api/v1/ (Upload, Ingestion Poll, Chat, Feedback, Health)          │
├────────────────────────────────────────────────────────────────────────┤
│                         ORCHESTRATION & GRAPH                          │
│             LangGraph Stateful Agent Pipeline (8 Nodes)                │
├───────────────────────────────────┬────────────────────────────────────┤
│         LOCAL EMBEDDING           │          HIGH-SPEED LLM            │
│ sentence-transformers/all-MiniLM  │       Groq Cloud API               │
│           (384 dimensions)        │   (Llama 3.3 70B & 3.1 8B)         │
└───────────────────────────────────┴────────────────────────────────────┘
                                    │ SQLAlchemy 2.0 (psycopg v3)
┌───────────────────────────────────▼────────────────────────────────────┐
│                       SUPABASE POSTGRESQL + PGVECTOR                   │
│   • 7 Core MVP Tables                                                  │
│   • pgvector (384d) with HNSW Index (Cosine Distance)                  │
│   • Stored Procedure: match_policy_chunks                              │
│   • Supabase Storage: knowledge-documents                              │
└────────────────────────────────────────────────────────────────────────┘
```

---

## 🚀 Quickstart & Setup

### 1. Prerequisites
- Python 3.11+
- Git
- Access to Supabase PostgreSQL database

### 2. Installation
```bash
# Clone the repository
git clone https://github.com/hanasinandeesh/KnowBridge-AI.git
cd KnowBridge-AI

# Create and activate virtual environment
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install backend dependencies
pip install -r backend/requirements.txt
```

### 3. Environment Configuration
Copy `backend/.env.example` to `backend/.env` and configure your credentials:
```bash
cp backend/.env.example backend/.env
```

Configure `backend/.env`:
```env
# Application Settings
PROJECT_NAME="KnowBridge AI Backend"
ENVIRONMENT="development"
API_V1_STR="/api/v1"

# Database Configuration (Supabase PostgreSQL Session Pooler)
DB_HOST="aws-1-ap-southeast-2.pooler.supabase.com"
DB_PORT=5432
DB_NAME="postgres"
DB_USER="postgres.iwwleppesznhdecsickr"
DB_PASSWORD="[YOUR_DATABASE_PASSWORD]"

# Single Source of Truth URL
DATABASE_URL="postgresql+psycopg://postgres.iwwleppesznhdecsickr:[YOUR_PASSWORD]@aws-1-ap-southeast-2.pooler.supabase.com:5432/postgres"

# Connection Pooling
DB_POOL_SIZE=5
DB_MAX_OVERFLOW=10
DB_POOL_TIMEOUT=30
DB_CONNECT_TIMEOUT=5
DB_POOL_RECYCLE=1800
DB_ECHO=false

# Supabase Storage Configuration (Task 003B)
SUPABASE_URL="https://[YOUR-PROJECT-REF].supabase.co"
SUPABASE_SERVICE_ROLE_KEY="[YOUR-SUPABASE-SERVICE-ROLE-KEY]"
STORAGE_BUCKET_NAME="knowledge-documents"
STORAGE_TIMEOUT=15.0
```

### 4. Running the Backend Server
```bash
# Run FastAPI with live reload (bound to 127.0.0.1 for local browser access)
cd backend
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

---

## 📡 API Endpoints

| Method | Endpoint | Description | Status Code |
|---|---|---|---|
| `GET` | `/health` | Core application health probe | `200 OK` |
| `GET` | `/health/db` | Database connectivity verification (`SELECT 1`) | `200 OK` / `503 Unavailable` |
| `GET` | `/api/v1/health` | Versioned API health check | `200 OK` |
| `POST` | `/api/v1/documents/upload` | Multipart document upload, validation (PDF, DOCX, TXT) & Supabase Storage persistence | `201 Created` |
| `POST` | `/api/v1/documents/{document_id}/extract` | Retrieves binary from Supabase Storage & extracts structured text, 1-based PDF pages & DOCX/TXT units | `200 OK` |
| `GET` | `/docs` | Interactive Swagger API documentation | `200 OK` |
| `GET` | `/redoc` | Interactive ReDoc documentation | `200 OK` |

---

## 🧪 Testing Suite

Execute the automated test suite using `pytest`:
```bash
# Run all tests
python -m pytest backend/tests -v
```

Test coverage includes 90 passing automated tests across 92 test cases (100% pass rate):
- Pydantic v2 application settings validation and credential redaction.
- Dynamic URI dialect conversion (`postgresql://` $\to$ `postgresql+psycopg://`).
- Password URL-encoding for complex symbols.
- Database connectivity probe and scalar verification (`SELECT 1`).
- Error message sanitization preventing credential leakage.
- Transactional session dependency (`get_db`) lifecycle verification.
- Safe filename sanitization and path traversal defense (`../../`, `..\..\`, control chars).
- Magic-byte validation for PDF (`%PDF-`), DOCX (`PK\x03\x04`), and TXT.
- Supabase Storage async and sync uploads, downloads, deletions, and existence checks.
- Deterministic storage object naming: `documents/{document_id}/{safe_filename}`.
- Compensating cleanup ensuring zero orphaned storage objects upon database rollback.
- Double-fault handling logging orphaned paths without leaking credentials.
- Multi-page PDF extraction with PyMuPDF preserving 1-based page numbers and boundaries.
- Scanned PDF detection with zero extractable text (`ocr_supported=False`, `empty_content`).
- Password-protected PDF detection and `EncryptedDocumentError` handling.
- Blank and corrupt PDF handling (`CorruptedDocumentError`).
- DOCX paragraph order preservation and heading hierarchy extraction.
- DOCX structured table extraction with Markdown grid generation and `page_number=None`.
- Plain text UTF-8 extraction, BOM handling (`utf-8-sig`), and line break preservation.
- Document extraction REST API endpoint (`POST /api/v1/documents/{document_id}/extract`).

---

## 📂 Project Structure

```
KnowBridge-AI/
├── backend/
│   ├── app/
│   │   ├── api/
│   │   │   └── routes/
│   │   │       ├── health.py             # Health check routes
│   │   │       └── documents.py          # Document upload & extraction routes
│   │   ├── core/
│   │   │   ├── config.py                 # Pydantic v2 Settings & URI logic
│   │   │   └── database.py               # SQLAlchemy engine, session & lifecycle
│   │   ├── models/
│   │   │   └── document.py               # SQLAlchemy Document model
│   │   ├── parsers/                      # Format-specific document text parsers
│   │   │   ├── base.py                   # Parser base class & typed exceptions
│   │   │   ├── pdf_parser.py             # PyMuPDF 1-based page extractor
│   │   │   ├── docx_parser.py            # python-docx document-order extractor
│   │   │   └── txt_parser.py             # UTF-8 BOM text block extractor
│   │   ├── schemas/
│   │   │   ├── document.py               # Pydantic upload request & response schemas
│   │   │   └── extraction.py             # Pydantic ContentUnit & ExtractionResult schemas
│   │   ├── services/
│   │   │   ├── document_service.py       # Validation & metadata persistence
│   │   │   ├── storage_service.py        # Supabase Storage client & cleanup
│   │   │   └── document_extractor.py     # Extraction service orchestrator
│   │   └── main.py                       # FastAPI application entrypoint
│   ├── migrations/                       # PostgreSQL DDL, HNSW index & functions
│   ├── scripts/                          # Live integration verification scripts
│   │   ├── verify_storage_integration.py # Live storage verification
│   │   └── verify_extraction_integration.py # Live extraction verification
│   ├── tests/                            # Automated test suite (92 tests)
│   │   ├── test_config.py
│   │   ├── test_health.py
│   │   ├── test_document_upload.py
│   │   ├── test_storage_service.py
│   │   └── test_document_extractor.py
│   ├── requirements.txt                  # Python dependencies
│   ├── .env.example                      # Configuration template
│   └── .gitignore
├── docs/                                 # Architecture, DB design & data flows
├── scripts/                              # Synthetic policy dataset generation
├── synthetic-data/                       # Synthetic policy files (PDF, DOCX, TXT)
├── PRD.md                                # Product Requirements Document
├── TASKS.md                              # Implementation roadmap
├── current_status.md                     # Current system health & progress report
├── backlog.md                            # Product and engineering backlog
├── .gitignore                            # Root Git ignore rules
└── README.md                             # Project documentation
```

---

## 📑 Completed Milestones

- [x] **Task 01:** Product Discovery, PRD, Functional & Non-Functional Specifications
- [x] **Task 02:** System Design, Low-Level Architecture & ADRs (001–010)
- [x] **Task 02A:** Supabase PostgreSQL DDL, 7 MVP Tables, HNSW Index, Stored Procedure
- [x] **Task 02B:** FastAPI & Supabase PostgreSQL Integration with SQLAlchemy 2.0 & psycopg 3
- [x] **Task 003A:** Document Upload API, Multi-Tier Validation & Metadata Persistence
- [x] **Task 003B:** Supabase Storage Integration, Deterministic Paths & Compensating Cleanup
- [x] **Task 003C:** Document Text Extraction Service (PyMuPDF, python-docx, UTF-8 BOM, Supabase Download)
- [ ] **Task 04 / 003D:** Ingestion Engine: Chunking & Embeddings *(Pending)*
