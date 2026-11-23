"""
Targeted Unit Tests for Query Embedding Generation.
Task 04B — KnowBridge AI Enterprise RAG Knowledge Platform.

Validates:
1. Valid question embedding returns 384-dimensional float vector.
2. Correct vector dimension enforcement (384) & mismatch rejection.
3. Unit L2 vector normalization (Euclidean norm == 1.0).
4. Rejection of empty, whitespace-only, and non-string questions.
5. Error handling and credential/secret sanitization on model failures.
6. Reuse of existing cached SentenceTransformer singleton model instance.
7. Structured QueryEmbedding schema validation.
8. Compatibility with pgvector VECTOR(384) requirements.
"""

import math
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from app.core.config import settings
from app.schemas.embedding import QueryEmbedding
from app.services.embedding_service import (
    EmbeddingDimensionMismatchError,
    EmbeddingError,
    EmbeddingGenerationError,
    EmbeddingService,
    InvalidChunkError,
    InvalidQueryError,
    NonFiniteVectorError,
    get_embedding_service,
)


# ---------------------------------------------------------------------------
# Test Helpers
# ---------------------------------------------------------------------------

def create_mock_transformer(
    dim: int = 384,
    normalize: bool = True,
    fail_with_secret: bool = False,
    return_nan: bool = False,
):
    """
    Creates a lightweight mock SentenceTransformer producing deterministic
    L2-normalized 384-dimensional vectors without real neural network overhead.
    """
    mock_model = MagicMock()
    mock_model.get_sentence_embedding_dimension.return_value = dim
    mock_model.get_embedding_dimension.return_value = dim

    def _encode(sentences, batch_size=1, normalize_embeddings=True, show_progress_bar=False):
        if fail_with_secret:
            raise RuntimeError(
                "Upstream provider failure at https://user:super_secret_db_pass_12345@huggingface.co/api?token=eyJhbGciOi"
            )

        vectors = []
        for s in sentences:
            rng = np.random.RandomState(abs(hash(s)) % (2**31))
            vec = rng.randn(dim).astype(np.float32)
            if return_nan:
                vec[0] = np.nan
            elif normalize and normalize_embeddings:
                norm = np.linalg.norm(vec)
                if norm > 0:
                    vec = vec / norm
            vectors.append(vec)
        return np.array(vectors)

    mock_model.encode.side_effect = _encode
    return mock_model


# ---------------------------------------------------------------------------
# Focused Test Scenarios for Task 04B
# ---------------------------------------------------------------------------

def test_01_valid_question_embedding_success():
    """
    Scenario 1: Validates that a natural-language question generates a 384-dimensional
    float vector where all values are finite.
    """
    mock_model = create_mock_transformer(dim=384)
    service = EmbeddingService(model_instance=mock_model)

    question = "What is the policy for international travel reimbursement and per diem allowances?"
    vector = service.embed_query(question)

    assert isinstance(vector, list)
    assert len(vector) == 384
    assert all(isinstance(x, float) for x in vector)
    assert all(math.isfinite(x) for x in vector)
    mock_model.encode.assert_called_once()


def test_02_correct_384_vector_dimension():
    """
    Scenario 2: Validates strict enforcement of 384 dimensions and rejection of mismatch.
    """
    # 1. Correct 384 dimensions succeeds
    mock_model_384 = create_mock_transformer(dim=384)
    service_384 = EmbeddingService(model_instance=mock_model_384, dimension=384)
    vec = service_384.embed_query("Can I expense business meals?")
    assert len(vec) == 384

    # 2. Unexpected dimension (e.g. 512 or 768) raises EmbeddingDimensionMismatchError
    mock_model_512 = create_mock_transformer(dim=512)
    service_512 = EmbeddingService(model_instance=mock_model_512, dimension=384)
    with pytest.raises(EmbeddingDimensionMismatchError) as exc_info:
        service_512.embed_query("Can I expense business meals?")
    assert "384" in str(exc_info.value) and "512" in str(exc_info.value)


def test_03_l2_normalization_applied():
    """
    Scenario 3: Validates that query embeddings have unit Euclidean norm (L2 norm == 1.0).
    Matches the normalization applied to stored document chunks.
    """
    mock_model = create_mock_transformer(dim=384, normalize=True)
    service = EmbeddingService(model_instance=mock_model, normalize_embeddings=True)

    test_queries = [
        "What is the maximum carry-over for annual leave?",
        "How do I submit vendor procurement invoices?",
        "Who is authorized to sign non-disclosure agreements?",
    ]

    for q in test_queries:
        vector = service.embed_query(q)
        arr = np.array(vector)
        norm = np.linalg.norm(arr)
        assert math.isclose(norm, 1.0, rel_tol=1e-4), f"L2 norm {norm} is not 1.0 for query: {q}"


def test_04_empty_and_whitespace_only_questions_rejected():
    """
    Scenario 4: Validates rejection of empty string, whitespace-only, and non-string inputs.
    Verifies that InvalidQueryError is raised (which also inherits from InvalidChunkError).
    """
    mock_model = create_mock_transformer(dim=384)
    service = EmbeddingService(model_instance=mock_model)

    # Empty string
    with pytest.raises(InvalidQueryError) as exc_empty:
        service.embed_query("")
    assert "cannot be empty" in str(exc_empty.value).lower()
    assert isinstance(exc_empty.value, InvalidChunkError)
    assert isinstance(exc_empty.value, EmbeddingError)

    # Whitespace only
    with pytest.raises(InvalidQueryError):
        service.embed_query("    ")
    with pytest.raises(InvalidQueryError):
        service.embed_query("\n\t  \r")

    # Non-string input
    with pytest.raises(InvalidQueryError):
        service.embed_query(None)  # type: ignore
    with pytest.raises(InvalidQueryError):
        service.embed_query(12345)  # type: ignore


def test_05_model_error_handling_sanitizes_secrets():
    """
    Scenario 5: Validates that downstream model inference errors are caught and sanitized,
    guaranteeing passwords, bearer tokens, or connection strings are never leaked.
    """
    mock_model = create_mock_transformer(dim=384, fail_with_secret=True)
    service = EmbeddingService(model_instance=mock_model)

    with pytest.raises(EmbeddingGenerationError) as exc_info:
        service.embed_query("Sensitive inquiry about executive compensation")

    err_text = str(exc_info.value)
    # Ensure sensitive credentials are redacted
    assert "super_secret_db_pass_12345" not in err_text
    assert "*****" in err_text
    assert "embedding generation failed" in err_text.lower()


def test_06_non_finite_vector_values_rejected():
    """
    Scenario 6: Validates that NaN or Inf in generated query vectors is rejected.
    """
    mock_model_nan = create_mock_transformer(dim=384, return_nan=True)
    service = EmbeddingService(model_instance=mock_model_nan)

    with pytest.raises(NonFiniteVectorError) as exc_info:
        service.embed_query("Any valid question text")
    assert "non-finite" in str(exc_info.value).lower() or "nan" in str(exc_info.value).lower()


def test_07_reuse_of_existing_cached_model_instance():
    """
    Scenario 7: Validates that multiple calls and multiple EmbeddingService instances
    reuse the shared class-level cached model instead of re-instantiating.
    """
    EmbeddingService.reset_cached_model()
    mock_transformer = create_mock_transformer(dim=384)

    with patch("sentence_transformers.SentenceTransformer", return_value=mock_transformer) as mock_cls:
        # First service instance
        service_a = EmbeddingService()
        vec_a = service_a.embed_query("First question?")
        assert len(vec_a) == 384

        # Second service instance (e.g. from a separate request or dependency injection)
        service_b = EmbeddingService()
        vec_b = service_b.embed_query("Second question?")
        assert len(vec_b) == 384

        # Global dependency provider
        service_singleton = get_embedding_service()
        vec_c = service_singleton.embed_query("Third question?")
        assert len(vec_c) == 384

        # SentenceTransformer must have been initialized exactly once
        assert mock_cls.call_count == 1

    EmbeddingService.reset_cached_model()


def test_08_structured_query_embedding_model():
    """
    Scenario 8: Validates the structured QueryEmbedding schema representation.
    """
    mock_model = create_mock_transformer(dim=384)
    service = EmbeddingService(model_instance=mock_model)

    question = "What are the core working hours for remote employees?"
    result = service.embed_query_structured(question)

    assert isinstance(result, QueryEmbedding)
    assert result.query == question
    assert len(result.embedding) == 384
    assert result.embedding_model == settings.EMBEDDING_MODEL_NAME
    assert result.dimension == 384
    assert result.is_normalized is True


def test_09_pgvector_compatibility():
    """
    Scenario 9: Validates that the returned embedding vector format meets all
    requirements for pgvector VECTOR(384) storage and query parameter binding.
    """
    mock_model = create_mock_transformer(dim=384)
    service = EmbeddingService(model_instance=mock_model)

    vector = service.embed_query("What is the equipment allowance policy?")

    # 1. Plain Python list
    assert type(vector) is list
    # 2. Exactly 384 elements
    assert len(vector) == 384
    # 3. All items are Python standard floats
    assert all(type(x) is float for x in vector)
    # 4. Serializable to pgvector string format '[x1,x2,...]'
    pgvector_str = f"[{','.join(str(x) for x in vector)}]"
    assert pgvector_str.startswith("[") and pgvector_str.endswith("]")
    assert len(pgvector_str.split(",")) == 384
