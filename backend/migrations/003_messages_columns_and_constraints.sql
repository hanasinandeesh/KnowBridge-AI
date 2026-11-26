-- ============================================================================
-- Migration: 003_messages_columns_and_constraints.sql
-- Project: KnowBridge AI — Policy-Aware Enterprise Knowledge Platform
-- Target: Supabase PostgreSQL
-- Description: Ensures trace_id, feedback_score, and updated evidence_status
--              check constraints exist on public.messages table.
-- ============================================================================

-- Ensure trace_id and feedback_score columns exist
ALTER TABLE public.messages ADD COLUMN IF NOT EXISTS trace_id VARCHAR(100);
ALTER TABLE public.messages ADD COLUMN IF NOT EXISTS feedback_score SMALLINT;

-- Ensure trace_id index exists
CREATE INDEX IF NOT EXISTS idx_messages_trace_id ON public.messages(trace_id);

-- Ensure evidence_status check constraint supports both uppercase and legacy lowercase
ALTER TABLE public.messages DROP CONSTRAINT IF EXISTS messages_evidence_status_check;
ALTER TABLE public.messages
ADD CONSTRAINT messages_evidence_status_check
CHECK (
    evidence_status IS NULL OR
    evidence_status IN (
        'SUPPORTED', 'INSUFFICIENT', 'CONFLICTING',
        'supported', 'insufficient_evidence', 'conflicting_evidence'
    )
);

-- Ensure feedback_score check constraint exists
ALTER TABLE public.messages DROP CONSTRAINT IF EXISTS messages_feedback_score_check;
ALTER TABLE public.messages
ADD CONSTRAINT messages_feedback_score_check
CHECK (feedback_score IN (-1, 0, 1, NULL));
