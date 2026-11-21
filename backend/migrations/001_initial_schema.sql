-- ============================================================================
-- Migration: 001_initial_schema.sql
-- Project: KnowBridge AI — Policy-Aware Enterprise Knowledge Platform
-- Target: Supabase PostgreSQL
-- Description: Enables required extensions, creates the 7 core MVP tables,
--              establishes foreign keys, check constraints, defaults,
--              and automatic timestamp update triggers.
-- Scope: MVP Single-Workspace (No Auth, No RLS).
-- ============================================================================

-- ----------------------------------------------------------------------------
-- 1. Enable Required Extensions
-- ----------------------------------------------------------------------------
-- Enables pgvector for high-dimensional vector embeddings
CREATE EXTENSION IF NOT EXISTS vector;

-- Enables UUID generation utilities
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ----------------------------------------------------------------------------
-- 2. Trigger Function: Automated updated_at Maintenance
-- ----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- ----------------------------------------------------------------------------
-- 3. Table: documents
-- Represents core enterprise document entities across revisions and categories.
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS documents (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    title VARCHAR(255) NOT NULL,
    description TEXT,
    category VARCHAR(100) NOT NULL DEFAULT 'general',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Trigger to maintain updated_at on documents
DROP TRIGGER IF EXISTS trg_documents_updated_at ON documents;
CREATE TRIGGER trg_documents_updated_at
BEFORE UPDATE ON documents
FOR EACH ROW
EXECUTE FUNCTION update_updated_at_column();

-- ----------------------------------------------------------------------------
-- 4. Table: document_versions
-- Tracks document releases, versions, active/sunset dates, and storage references.
-- Original PDF binaries reside in Supabase Storage; storage_path stores the key.
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS document_versions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    version_number VARCHAR(50) NOT NULL,
    effective_date DATE NOT NULL,
    sunset_date DATE,
    status VARCHAR(50) NOT NULL DEFAULT 'ACTIVE' 
        CHECK (status IN ('DRAFT', 'ACTIVE', 'SUPERSEDED', 'DEPRECATED')),
    storage_path TEXT NOT NULL,
    file_hash VARCHAR(64) NOT NULL,
    file_size_bytes BIGINT NOT NULL CHECK (file_size_bytes > 0),
    total_pages INTEGER NOT NULL DEFAULT 0 CHECK (total_pages >= 0),
    supersedes_version_id UUID REFERENCES document_versions(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT check_dates CHECK (sunset_date IS NULL OR sunset_date >= effective_date)
);

-- ----------------------------------------------------------------------------
-- 5. Table: document_chunks
-- Stores text passages, physical page provenance, token counts, and dense vector embeddings.
-- Vector dimension is fixed to 384 matching sentence-transformers/all-MiniLM-L6-v2.
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS document_chunks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_version_id UUID NOT NULL REFERENCES document_versions(id) ON DELETE CASCADE,
    chunk_index INTEGER NOT NULL CHECK (chunk_index >= 0),
    page_number INTEGER NOT NULL CHECK (page_number >= 1),
    content TEXT NOT NULL,
    token_count INTEGER NOT NULL CHECK (token_count > 0),
    embedding VECTOR(384) NOT NULL,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ----------------------------------------------------------------------------
-- 6. Table: conversations
-- Manages conversational sessions and chat threads.
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS conversations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    title VARCHAR(255) NOT NULL DEFAULT 'New Conversation',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Trigger to maintain updated_at on conversations
DROP TRIGGER IF EXISTS trg_conversations_updated_at ON conversations;
CREATE TRIGGER trg_conversations_updated_at
BEFORE UPDATE ON conversations
FOR EACH ROW
EXECUTE FUNCTION update_updated_at_column();

-- ----------------------------------------------------------------------------
-- 7. Table: messages
-- Stores multi-turn dialogue, verified page citations, evidence status, and feedback.
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS messages (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    conversation_id UUID NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    role VARCHAR(20) NOT NULL CHECK (role IN ('user', 'assistant', 'system')),
    content TEXT NOT NULL,
    citations JSONB DEFAULT '[]'::jsonb,
    evidence_status VARCHAR(50) CHECK (evidence_status IN ('SUPPORTED', 'INSUFFICIENT', 'CONFLICTING', NULL)),
    trace_id VARCHAR(100),
    feedback_score SMALLINT CHECK (feedback_score IN (-1, 0, 1, NULL)),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ----------------------------------------------------------------------------
-- 8. Table: user_memories
-- Stores persistent facts, department context, and user constraints across sessions.
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS user_memories (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    memory_key VARCHAR(100) NOT NULL,
    memory_value TEXT NOT NULL,
    source_conversation_id UUID REFERENCES conversations(id) ON DELETE SET NULL,
    confidence_score FLOAT NOT NULL DEFAULT 1.0 CHECK (confidence_score >= 0.0 AND confidence_score <= 1.0),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Trigger to maintain updated_at on user_memories
DROP TRIGGER IF EXISTS trg_user_memories_updated_at ON user_memories;
CREATE TRIGGER trg_user_memories_updated_at
BEFORE UPDATE ON user_memories
FOR EACH ROW
EXECUTE FUNCTION update_updated_at_column();

-- ----------------------------------------------------------------------------
-- 9. Table: ingestion_jobs
-- Asynchronous tracking of PDF layout extraction, chunking, and vector indexing.
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS ingestion_jobs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_version_id UUID NOT NULL REFERENCES document_versions(id) ON DELETE CASCADE,
    status VARCHAR(50) NOT NULL DEFAULT 'PENDING'
        CHECK (status IN ('PENDING', 'PROCESSING', 'COMPLETED', 'FAILED')),
    error_message TEXT,
    processed_pages INTEGER NOT NULL DEFAULT 0 CHECK (processed_pages >= 0),
    total_pages INTEGER NOT NULL DEFAULT 0 CHECK (total_pages >= 0),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at TIMESTAMPTZ
);
