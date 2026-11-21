-- ============================================================================
-- Validation Script: validate_schema.sql
-- Project: KnowBridge AI — Policy-Aware Enterprise Knowledge Platform
-- Description: Validates extensions, tables, column types, vector dimensions,
--              foreign key cascades, check constraints, HNSW index, and
--              the match_policy_chunks function.
-- Guarantee: Transient test data is fully cleaned up. Leaves NO fake data.
-- ============================================================================

DO $$
DECLARE
    v_ext_count INTEGER;
    v_table_count INTEGER;
    v_vec_dim INTEGER;
    v_test_doc_id UUID;
    v_test_ver_id UUID;
    v_test_chunk_id UUID;
    v_test_conv_id UUID;
    v_test_msg_id UUID;
    v_test_mem_id UUID;
    v_test_job_id UUID;
    v_search_results_count INTEGER;
    v_zero_vector VECTOR(384);
BEGIN
    RAISE NOTICE '=======================================================';
    RAISE NOTICE 'Starting KnowBridge AI Database Schema Validation...';
    RAISE NOTICE '=======================================================';

    -- ------------------------------------------------------------------------
    -- 1. Validate Extensions
    -- ------------------------------------------------------------------------
    SELECT COUNT(*) INTO v_ext_count 
    FROM pg_extension 
    WHERE extname IN ('vector', 'uuid-ossp');
    
    IF v_ext_count < 2 THEN
        RAISE EXCEPTION 'Validation Failed: Required extensions (vector, uuid-ossp) are missing. Found: %', v_ext_count;
    END IF;
    RAISE NOTICE '[OK] Extensions "vector" and "uuid-ossp" are installed and active.';

    -- ------------------------------------------------------------------------
    -- 2. Validate 7 Core MVP Tables
    -- ------------------------------------------------------------------------
    SELECT COUNT(*) INTO v_table_count 
    FROM information_schema.tables 
    WHERE table_schema = 'public' 
      AND table_name IN (
          'documents', 
          'document_versions', 
          'document_chunks', 
          'conversations', 
          'messages', 
          'user_memories', 
          'ingestion_jobs'
      );
      
    IF v_table_count < 7 THEN
        RAISE EXCEPTION 'Validation Failed: Expected 7 MVP tables, found %', v_table_count;
    END IF;
    RAISE NOTICE '[OK] All 7 MVP tables exist in public schema.';

    -- ------------------------------------------------------------------------
    -- 3. Validate Vector Column Dimension on document_chunks
    -- ------------------------------------------------------------------------
    SELECT atttypmod INTO v_vec_dim
    FROM pg_attribute
    WHERE attrelid = 'document_chunks'::regclass
      AND attname = 'embedding';
      
    IF v_vec_dim <> 384 THEN
        RAISE EXCEPTION 'Validation Failed: document_chunks.embedding dimension is %, expected 384', v_vec_dim;
    END IF;
    RAISE NOTICE '[OK] document_chunks.embedding is confirmed as vector(384).';

    -- ------------------------------------------------------------------------
    -- 4. Validate HNSW Vector Index Existence
    -- ------------------------------------------------------------------------
    IF NOT EXISTS (
        SELECT 1 FROM pg_indexes 
        WHERE tablename = 'document_chunks' 
          AND indexname = 'idx_chunks_embedding_hnsw'
    ) THEN
        RAISE EXCEPTION 'Validation Failed: HNSW vector index idx_chunks_embedding_hnsw is missing.';
    END IF;
    RAISE NOTICE '[OK] HNSW index idx_chunks_embedding_hnsw is present.';

    -- ------------------------------------------------------------------------
    -- 5. Validate Stored Function match_policy_chunks
    -- ------------------------------------------------------------------------
    IF NOT EXISTS (
        SELECT 1 FROM pg_proc 
        WHERE proname = 'match_policy_chunks'
    ) THEN
        RAISE EXCEPTION 'Validation Failed: Stored procedure match_policy_chunks is missing.';
    END IF;
    RAISE NOTICE '[OK] Stored function match_policy_chunks is registered.';

    -- ------------------------------------------------------------------------
    -- 6. Functional End-to-End Test (Transient, Cleaned up afterwards)
    -- ------------------------------------------------------------------------
    RAISE NOTICE 'Executing transient functional CRUD & search test...';

    -- Build test 384d unit vector
    SELECT array_to_string(array_agg(0.05), ',')::vector(384) INTO v_zero_vector
    FROM generate_series(1, 384);

    -- Insert Document
    INSERT INTO documents (title, category)
    VALUES ('__SCHEMA_TEST_DOC__', 'testing')
    RETURNING id INTO v_test_doc_id;

    -- Insert Document Version
    INSERT INTO document_versions (
        document_id, version_number, effective_date, sunset_date,
        status, storage_path, file_hash, file_size_bytes, total_pages
    ) VALUES (
        v_test_doc_id, 'v1.0', CURRENT_DATE - INTERVAL '10 days', NULL,
        'ACTIVE', 'test/path/test.pdf', 'dummy_hash_0123456789abcdef0123456789abcdef',
        1024, 5
    ) RETURNING id INTO v_test_ver_id;

    -- Insert Document Chunk with Vector
    INSERT INTO document_chunks (
        document_version_id, chunk_index, page_number, content, token_count, embedding, metadata
    ) VALUES (
        v_test_ver_id, 0, 1, 'This is validation chunk test content.', 7, v_zero_vector, '{"test": true}'::jsonb
    ) RETURNING id INTO v_test_chunk_id;

    -- Insert Conversation & Message
    INSERT INTO conversations (title)
    VALUES ('__SCHEMA_TEST_CONVERSATION__')
    RETURNING id INTO v_test_conv_id;

    INSERT INTO messages (conversation_id, role, content, evidence_status)
    VALUES (v_test_conv_id, 'user', 'Test query message', 'SUPPORTED')
    RETURNING id INTO v_test_msg_id;

    -- Insert User Memory
    INSERT INTO user_memories (memory_key, memory_value, source_conversation_id)
    VALUES ('test_key', 'test_value', v_test_conv_id)
    RETURNING id INTO v_test_mem_id;

    -- Insert Ingestion Job
    INSERT INTO ingestion_jobs (document_version_id, status, processed_pages, total_pages)
    VALUES (v_test_ver_id, 'COMPLETED', 5, 5)
    RETURNING id INTO v_test_job_id;

    -- Execute Vector Search Stored Procedure
    SELECT COUNT(*) INTO v_search_results_count
    FROM match_policy_chunks(
        query_embedding => v_zero_vector,
        target_date => CURRENT_DATE,
        match_threshold => 0.50,
        match_count => 1
    );

    IF v_search_results_count <> 1 THEN
        RAISE EXCEPTION 'Validation Failed: match_policy_chunks failed to retrieve test chunk. Returned % rows', v_search_results_count;
    END IF;
    RAISE NOTICE '[OK] match_policy_chunks executed successfully with vector similarity.';

    -- Validate Foreign Key Cascade on Document Deletion
    DELETE FROM documents WHERE id = v_test_doc_id;

    -- Verify that document_versions, document_chunks, and ingestion_jobs cascaded
    IF EXISTS (SELECT 1 FROM document_versions WHERE id = v_test_ver_id) THEN
        RAISE EXCEPTION 'Validation Failed: Cascade delete failed for document_versions.';
    END IF;
    IF EXISTS (SELECT 1 FROM document_chunks WHERE id = v_test_chunk_id) THEN
        RAISE EXCEPTION 'Validation Failed: Cascade delete failed for document_chunks.';
    END IF;
    IF EXISTS (SELECT 1 FROM ingestion_jobs WHERE id = v_test_job_id) THEN
        RAISE EXCEPTION 'Validation Failed: Cascade delete failed for ingestion_jobs.';
    END IF;
    RAISE NOTICE '[OK] ON DELETE CASCADE correctly purged versions, chunks, and ingestion jobs.';

    -- Clean up conversation & user memory
    DELETE FROM conversations WHERE id = v_test_conv_id;
    IF EXISTS (SELECT 1 FROM messages WHERE id = v_test_msg_id) THEN
        RAISE EXCEPTION 'Validation Failed: Cascade delete failed for messages.';
    END IF;
    
    -- user_memories foreign key has ON DELETE SET NULL
    IF (SELECT source_conversation_id FROM user_memories WHERE id = v_test_mem_id) IS NOT NULL THEN
        RAISE EXCEPTION 'Validation Failed: ON DELETE SET NULL failed for user_memories.';
    END IF;
    DELETE FROM user_memories WHERE id = v_test_mem_id;
    RAISE NOTICE '[OK] ON DELETE SET NULL and cleanup confirmed for conversations & memories.';

    RAISE NOTICE '=======================================================';
    RAISE NOTICE 'KNOWBRIDGE AI DATABASE VALIDATION: ALL CHECKS PASSED!';
    RAISE NOTICE 'Zero test rows remain in the database.';
    RAISE NOTICE '=======================================================';
END $$;
