-- ============================================================================
-- Migration: 004_user_memories_harmonization.sql
-- Project: KnowBridge AI — Policy-Aware Enterprise Knowledge Platform
-- Target: Supabase PostgreSQL
-- Description: Harmonizes public.user_memories table schema across migrations,
--              adding memory_key, memory_value, confidence_score, and performance
--              indexes for session and type filtering.
-- ============================================================================

-- Ensure memory_key and memory_value columns exist
ALTER TABLE public.user_memories ADD COLUMN IF NOT EXISTS memory_key VARCHAR(100);
ALTER TABLE public.user_memories ADD COLUMN IF NOT EXISTS memory_value TEXT;
ALTER TABLE public.user_memories ADD COLUMN IF NOT EXISTS confidence_score FLOAT DEFAULT 1.0;

-- Ensure confidence_score check constraint
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'user_memories_confidence_score_check'
    ) THEN
        ALTER TABLE public.user_memories
        ADD CONSTRAINT user_memories_confidence_score_check
        CHECK (confidence_score >= 0.0 AND confidence_score <= 1.0);
    END IF;
END $$;

-- Indexes for fast query retrieval and session scoping
CREATE INDEX IF NOT EXISTS idx_user_memories_key ON public.user_memories(memory_key);
CREATE INDEX IF NOT EXISTS idx_user_memories_session ON public.user_memories(session_key);
CREATE INDEX IF NOT EXISTS idx_user_memories_type ON public.user_memories(memory_type);
CREATE INDEX IF NOT EXISTS idx_user_memories_conversation ON public.user_memories(source_conversation_id);
CREATE INDEX IF NOT EXISTS idx_user_memories_expires ON public.user_memories(expires_at);
