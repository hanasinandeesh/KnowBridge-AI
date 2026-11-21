-- ============================================================================
-- KnowBridge AI — Complete Consolidated Database Migration
-- Target: Supabase PostgreSQL (pgvector)
-- File: 000_full_migration.sql
-- Description: Executes all extensions, MVP tables, constraints, triggers,
--              HNSW vector index, B-tree indexes, GIN index, and the
--              match_policy_chunks stored procedure.
-- ============================================================================

-- ----------------------------------------------------------------------------
-- 1. Extensions
-- ----------------------------------------------------------------------------
CREATE EXTENSION IF NOT EXISTS vector;
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
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS documents (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    title VARCHAR(255) NOT NULL,
    description TEXT,
    category VARCHAR(100) NOT NULL DEFAULT 'general',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

DROP TRIGGER IF EXISTS trg_documents_updated_at ON documents;
CREATE TRIGGER trg_documents_updated_at
BEFORE UPDATE ON documents
FOR EACH ROW
EXECUTE FUNCTION update_updated_at_column();

-- ----------------------------------------------------------------------------
-- 4. Table: document_versions
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
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS conversations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    title VARCHAR(255) NOT NULL DEFAULT 'New Conversation',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

DROP TRIGGER IF EXISTS trg_conversations_updated_at ON conversations;
CREATE TRIGGER trg_conversations_updated_at
BEFORE UPDATE ON conversations
FOR EACH ROW
EXECUTE FUNCTION update_updated_at_column();

-- ----------------------------------------------------------------------------
-- 7. Table: messages
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

DROP TRIGGER IF EXISTS trg_user_memories_updated_at ON user_memories;
CREATE TRIGGER trg_user_memories_updated_at
BEFORE UPDATE ON user_memories
FOR EACH ROW
EXECUTE FUNCTION update_updated_at_column();

-- ----------------------------------------------------------------------------
-- 9. Table: ingestion_jobs
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

-- ----------------------------------------------------------------------------
-- 10. Indexes
-- ----------------------------------------------------------------------------
-- Vector Search HNSW Index
CREATE INDEX IF NOT EXISTS idx_chunks_embedding_hnsw 
ON document_chunks 
USING hnsw (embedding vector_cosine_ops)
WITH (m = 16, ef_construction = 64);

-- Document & Version Indexes
CREATE INDEX IF NOT EXISTS idx_documents_category ON documents(category);
CREATE INDEX IF NOT EXISTS idx_doc_versions_doc_status ON document_versions(document_id, status);
CREATE INDEX IF NOT EXISTS idx_doc_versions_temporal ON document_versions(effective_date, sunset_date);
CREATE INDEX IF NOT EXISTS idx_doc_versions_hash ON document_versions(file_hash);
CREATE INDEX IF NOT EXISTS idx_doc_versions_supersedes ON document_versions(supersedes_version_id);

-- Chunk Indexes
CREATE INDEX IF NOT EXISTS idx_chunks_version_page ON document_chunks(document_version_id, page_number);
CREATE INDEX IF NOT EXISTS idx_chunks_metadata_gin ON document_chunks USING gin (metadata);

-- Conversation & Message Indexes
CREATE INDEX IF NOT EXISTS idx_conversations_updated ON conversations(updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_messages_conversation_created ON messages(conversation_id, created_at ASC);
CREATE INDEX IF NOT EXISTS idx_messages_trace_id ON messages(trace_id);

-- User Memories Indexes
CREATE INDEX IF NOT EXISTS idx_user_memories_key ON user_memories(memory_key);
CREATE INDEX IF NOT EXISTS idx_user_memories_conversation ON user_memories(source_conversation_id);

-- Ingestion Job Indexes
CREATE INDEX IF NOT EXISTS idx_ingestion_jobs_version ON ingestion_jobs(document_version_id);
CREATE INDEX IF NOT EXISTS idx_ingestion_jobs_status ON ingestion_jobs(status);

-- ----------------------------------------------------------------------------
-- 11. Policy-Aware Vector Search Stored Procedure
-- ----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION match_policy_chunks(
    query_embedding VECTOR(384),
    target_date DATE DEFAULT CURRENT_DATE,
    match_threshold FLOAT DEFAULT 0.65,
    match_count INTEGER DEFAULT 5
)
RETURNS TABLE (
    chunk_id UUID,
    document_id UUID,
    document_title VARCHAR(255),
    version_id UUID,
    version_number VARCHAR(50),
    effective_date DATE,
    sunset_date DATE,
    page_number INTEGER,
    content TEXT,
    similarity FLOAT,
    chunk_metadata JSONB
)
LANGUAGE plpgsql
AS $$
BEGIN
    RETURN QUERY
    SELECT
        c.id AS chunk_id,
        d.id AS document_id,
        d.title AS document_title,
        v.id AS version_id,
        v.version_number,
        v.effective_date,
        v.sunset_date,
        c.page_number,
        c.content,
        (1 - (c.embedding <=> query_embedding))::FLOAT AS similarity,
        c.metadata AS chunk_metadata
    FROM document_chunks c
    JOIN document_versions v ON c.document_version_id = v.id
    JOIN documents d ON v.document_id = d.id
    WHERE v.status = 'ACTIVE'
      AND v.effective_date <= target_date
      AND (v.sunset_date IS NULL OR v.sunset_date >= target_date)
      AND (1 - (c.embedding <=> query_embedding)) >= match_threshold
    ORDER BY c.embedding <=> query_embedding ASC
    LIMIT match_count;
END;
$$;
