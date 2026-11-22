import math
import uuid
import numpy as np
import pytest

from app.schemas.chunking import DocumentChunk
from app.services.embedding_service import EmbeddingService


@pytest.mark.integration
def test_real_model_embedding_generation():
    """
    Optional live integration test using the actual Sentence Transformers model.
    Skipped if model weights cannot be loaded (e.g., offline without cache).
    """
    try:
        service = EmbeddingService()
        # Attempt to load the real model
        model = service._get_model()
    except Exception as exc:
        pytest.skip(f"Live model unavailable (offline or not downloaded): {exc}")

    chunk = DocumentChunk(
        chunk_id=uuid.uuid4(),
        document_id=uuid.uuid4(),
        chunk_index=0,
        chunk_text="Employees traveling on official company business are entitled to reimbursement.",
        character_count=78,
        token_count=20,
        page_number=1,
        section_title="1.0 Travel Reimbursement Policy",
        section_hierarchy=["1.0 Travel Policy"],
        source_unit_indices=[0],
        source_unit_type="paragraph",
        filename="HR-TRV-001.pdf",
        file_type="pdf",
        metadata={"category": "HR"},
    )

    results = service.embed_chunks([chunk])
    assert len(results) == 1
    emb = results[0]

    # Verify 384 dimensions
    assert len(emb.embedding) == 384
    assert emb.dimension == 384

    # Verify finite numeric values
    vec = np.array(emb.embedding, dtype=np.float32)
    assert np.all(np.isfinite(vec))

    # Verify L2 normalization
    norm = np.linalg.norm(vec)
    assert math.isclose(norm, 1.0, rel_tol=1e-4)

    # Verify query embedding matches strategy
    query_vec = np.array(service.embed_query("What is the travel policy?"), dtype=np.float32)
    assert len(query_vec) == 384
    assert np.all(np.isfinite(query_vec))
    assert math.isclose(np.linalg.norm(query_vec), 1.0, rel_tol=1e-4)
