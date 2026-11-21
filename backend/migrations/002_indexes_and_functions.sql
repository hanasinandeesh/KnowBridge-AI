-- ============================================================================
-- Migration: 002_indexes_and_functions.sql
-- Project: KnowBridge AI — Policy-Aware Enterprise Knowledge Platform
-- Target: Supabase PostgreSQL
-- Description: Establishes HNSW vector index, B-tree indexes for foreign keys
--              and temporal filters, GIN index for JSONB metadata, and the
--              match_policy_chunks vector similarity search function.
-- ============================================================================

-- ----------------------------------------------------------------------------
-- 1. Vector Search Index (HNSW)
-- Uses cosine distance operator (vector_cosine_ops).
-- Parameters:
--   m = 16: Max bidirectional links per node in HNSW graph.
--   ef_construction = 64: Size of dynamic candidate list during graph build.
-- ----------------------------------------------------------------------------
CREATE INDEX IF NOT EXISTS idx_chunks_embedding_hnsw 
ON document_chunks 
USING hnsw (embedding vector_cosine_ops)
WITH (m = 16, ef_construction = 64);

-- ----------------------------------------------------------------------------
-- 2. Document & Version Indexes
-- ----------------------------------------------------------------------------
-- Accelerates category-based document filtering
CREATE INDEX IF NOT EXISTS idx_documents_category 
ON documents(category);

-- Composite index for resolving active versions by document
CREATE INDEX IF NOT EXISTS idx_doc_versions_doc_status 
ON document_versions(document_id, status);

-- Composite index for temporal range filtering (active policy window)
CREATE INDEX IF NOT EXISTS idx_doc_versions_temporal 
ON document_versions(effective_date, sunset_date);

-- Index for SHA-256 deduplication lookups during upload
CREATE INDEX IF NOT EXISTS idx_doc_versions_hash 
ON document_versions(file_hash);

-- Foreign key lookup index on supersedes_version_id
CREATE INDEX IF NOT EXISTS idx_doc_versions_supersedes 
ON document_versions(supersedes_version_id);

-- ----------------------------------------------------------------------------
-- 3. Document Chunk Indexes
-- ----------------------------------------------------------------------------
-- Accelerates page-level citation lookups and chunk retrieval by version
CREATE INDEX IF NOT EXISTS idx_chunks_version_page 
ON document_chunks(document_version_id, page_number);

-- GIN index for querying structured chunk metadata (e.g., section headings, tags)
CREATE INDEX IF NOT EXISTS idx_chunks_metadata_gin 
ON document_chunks 
USING gin (metadata);

-- ----------------------------------------------------------------------------
-- 4. Conversation & Message Indexes
-- ----------------------------------------------------------------------------
-- Indexes conversation sorting by activity
CREATE INDEX IF NOT EXISTS idx_conversations_updated 
ON conversations(updated_at DESC);

-- Composite index for retrieving chronological conversation message history
CREATE INDEX IF NOT EXISTS idx_messages_conversation_created 
ON messages(conversation_id, created_at ASC);

-- Index for tracing and attributing Langfuse spans to messages
CREATE INDEX IF NOT EXISTS idx_messages_trace_id 
ON messages(trace_id);

-- ----------------------------------------------------------------------------
-- 5. User Memories Indexes
-- ----------------------------------------------------------------------------
-- Accelerates key-based user memory lookups (e.g., department, preferred_region)
CREATE INDEX IF NOT EXISTS idx_user_memories_key 
ON user_memories(memory_key);

-- Foreign key lookup index on source conversation
CREATE INDEX IF NOT EXISTS idx_user_memories_conversation 
ON user_memories(source_conversation_id);

-- ----------------------------------------------------------------------------
-- 6. Ingestion Job Indexes
-- ----------------------------------------------------------------------------
-- Accelerates polling and job tracking by document version
CREATE INDEX IF NOT EXISTS idx_ingestion_jobs_version 
ON ingestion_jobs(document_version_id);

-- Accelerates status filtering for pending/active background jobs
CREATE INDEX IF NOT EXISTS idx_ingestion_jobs_status 
ON ingestion_jobs(status);

-- ----------------------------------------------------------------------------
-- 7. Policy-Aware Vector Search Stored Procedure: match_policy_chunks
-- Executes cosine similarity search filtered strictly by document active status
-- and temporal effective/sunset date validity.
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
