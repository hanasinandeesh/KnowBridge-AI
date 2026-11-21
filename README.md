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
```

### 4. Running the Backend Server
```bash
# Run FastAPI with live reload
cd backend
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

---

## 📡 API Endpoints

| Method | Endpoint | Description | Status Code |
|---|---|---|---|
| `GET` | `/health` | Core application health probe | `200 OK` |
| `GET` | `/health/db` | Database connectivity verification (`SELECT 1`) | `200 OK` / `503 Unavailable` |
| `GET` | `/api/v1/health` | Versioned API health check | `200 OK` |
| `POST` | `/api/v1/documents/upload` | Multipart document upload & validation (PDF, DOCX, TXT) | `201 Created` |
| `GET` | `/docs` | Interactive Swagger API documentation | `200 OK` |
| `GET` | `/redoc` | Interactive ReDoc documentation | `200 OK` |

---

## 🧪 Testing Suite

Execute the automated test suite using `pytest`:
```bash
# Run all tests
python -m pytest backend/tests -v
```

Test coverage includes:
- Pydantic v2 application settings validation and credential redaction.
- Dynamic URI dialect conversion (`postgresql://` $\to$ `postgresql+psycopg://`).
- Password URL-encoding for complex symbols.
- Database connectivity probe and scalar verification (`SELECT 1`).
- Error message sanitization preventing credential leakage.
- Transactional session dependency (`get_db`) lifecycle verification.

---

## 📂 Project Structure

```
KnowBridge-AI/
├── backend/
│   ├── app/
│   │   ├── api/
│   │   │   └── routes/
│   │   │       ├── health.py       # Health check routes
│   │   │       └── documents.py    # Document upload & management routes
│   │   ├── core/
│   │   │   ├── config.py           # Pydantic v2 Settings & URI logic
│   │   │   └── database.py         # SQLAlchemy engine, session & lifecycle
│   │   ├── models/
│   │   │   └── document.py         # SQLAlchemy Document model
│   │   ├── schemas/
│   │   │   └── document.py         # Pydantic request & response schemas
│   │   ├── services/
│   │   │   └── document_service.py # Validation & upload business logic
│   │   └── main.py                 # FastAPI application entrypoint
│   ├── migrations/                 # PostgreSQL DDL, HNSW index & functions
│   ├── tests/                      # Automated test suite (42 tests)
│   ├── requirements.txt            # Python dependencies
│   ├── .env.example                # Configuration template
│   └── .gitignore
├── docs/                           # Architecture, DB design & data flows
├── scripts/                        # Synthetic policy dataset generation
├── synthetic-data/                 # Synthetic policy files (PDF, DOCX, TXT)
├── PRD.md                          # Product Requirements Document
├── TASKS.md                        # Implementation roadmap
├── current_status.md               # Current system health & progress report
├── backlog.md                      # Product and engineering backlog
├── .gitignore                      # Root Git ignore rules
└── README.md                       # Project documentation
```

---

## 📑 Completed Milestones

- [x] **Task 01:** Product Discovery, PRD, Functional & Non-Functional Specifications
- [x] **Task 02:** System Design, Low-Level Architecture & ADRs (001–010)
- [x] **Task 02A:** Supabase PostgreSQL DDL, 7 MVP Tables, HNSW Index, Stored Procedure
- [x] **Task 02B:** FastAPI & Supabase PostgreSQL Integration with SQLAlchemy 2.0 & psycopg 3
- [x] **Task 003A:** Document Upload API, Multi-Tier Validation & Metadata Persistence
- [ ] **Task 04:** Ingestion Engine & Document Processing Service *(Pending)*
