import logging
import math
import threading
from typing import Any, Optional, Union

import numpy as np

from app.core.config import settings
from app.schemas.chunking import DocumentChunk, DocumentChunkingResult
from app.schemas.embedding import ChunkEmbedding, DocumentEmbeddingResult

logger = logging.getLogger("app.services.embedding")


# ---------------------------------------------------------------------------
# Custom Exceptions
# ---------------------------------------------------------------------------

class EmbeddingError(Exception):
    """Base exception for all embedding generation and validation operations."""
    pass


class ModelInitializationError(EmbeddingError):
    """Raised when the embedding model cannot be loaded, downloaded, or initialized."""
    pass


class InvalidChunkError(EmbeddingError):
    """Raised when an input chunk has invalid structure, empty text, or whitespace-only content."""
    pass


class EmbeddingDimensionMismatchError(EmbeddingError):
    """Raised when the generated embedding vector does not match the required dimension (384)."""
    pass


class NonFiniteVectorError(EmbeddingError):
    """Raised when an embedding vector contains non-finite numerical values (NaN or Inf)."""
    pass


class EmbeddingGenerationError(EmbeddingError):
    """Raised when an error occurs during model encoding or vector generation."""
    pass


# ---------------------------------------------------------------------------
# Embedding Service Implementation
# ---------------------------------------------------------------------------

class EmbeddingService:
    """
    Reusable, production-grade embedding generation service.
    
    Generates deterministic, 384-dimensional dense vector embeddings using Hugging Face
    Sentence Transformers (`sentence-transformers/all-MiniLM-L6-v2`) running locally on CPU or GPU.
    
    Responsibilities:
    1. Accept structured DocumentChunk objects from Task 003D.
    2. Validate inputs, rejecting empty or malformed chunks.
    3. Extract text while strictly preserving metadata association and chunk ordering.
    4. Generate embeddings in configurable batches without per-chunk model reinitialization.
    5. Apply consistent vector normalization (L2 norm) for cosine similarity indexing.
    6. Validate that every embedding contains strictly 384 finite numerical values.
    7. Return structured ChunkEmbedding and DocumentEmbeddingResult objects.
    8. Provide embed_query for unified document and query representations.
    """

    _cached_model = None
    _model_lock = threading.Lock()

    def __init__(
        self,
        model_name: Optional[str] = None,
        dimension: Optional[int] = None,
        batch_size: Optional[int] = None,
        normalize_embeddings: Optional[bool] = None,
        device: Optional[str] = None,
        model_instance: Optional[Any] = None,
    ) -> None:
        self.model_name = model_name or settings.EMBEDDING_MODEL_NAME
        self.dimension = dimension or settings.EMBEDDING_DIMENSION
        self.batch_size = batch_size or settings.EMBEDDING_BATCH_SIZE
        self.normalize_embeddings = (
            normalize_embeddings if normalize_embeddings is not None else settings.EMBEDDING_NORMALIZE
        )
        self.device = device or settings.EMBEDDING_DEVICE
        self._custom_model = model_instance

    def _get_model(self) -> Any:
        """
        Lazily loads and caches the Sentence Transformers model instance.
        Ensures thread-safe, single-instance initialization across requests.
        """
        if self._custom_model is not None:
            return self._custom_model

        if EmbeddingService._cached_model is None:
            with EmbeddingService._model_lock:
                if EmbeddingService._cached_model is None:
                    logger.info(
                        "Loading Sentence Transformers embedding model '%s' (device: %s)...",
                        self.model_name,
                        self.device or "auto-detect",
                    )
                    try:
                        from sentence_transformers import SentenceTransformer

                        loaded_model = SentenceTransformer(
                            self.model_name,
                            device=self.device,
                        )
                        # Verify that model output dimension matches configured dimension
                        if hasattr(loaded_model, "get_embedding_dimension"):
                            model_dim = loaded_model.get_embedding_dimension()
                        else:
                            model_dim = loaded_model.get_sentence_embedding_dimension()
                        if model_dim != self.dimension:
                            raise EmbeddingDimensionMismatchError(
                                f"Model '{self.model_name}' produces {model_dim}-dimensional vectors, "
                                f"expected {self.dimension} dimensions."
                            )
                        EmbeddingService._cached_model = loaded_model
                        logger.info(
                            "Sentence Transformers model '%s' initialized successfully (dim: %s).",
                            self.model_name,
                            self.dimension,
                        )
                    except EmbeddingDimensionMismatchError:
                        raise
                    except Exception as exc:
                        logger.error(
                            "Failed to initialize embedding model '%s': %s",
                            self.model_name,
                            exc,
                        )
                        raise ModelInitializationError(
                            f"Failed to initialize embedding model '{self.model_name}': {exc}"
                        ) from exc

        return EmbeddingService._cached_model

    @classmethod
    def reset_cached_model(cls) -> None:
        """Clears the shared cached model instance (useful for testing and teardown)."""
        with cls._model_lock:
            cls._cached_model = None

    def validate_chunk(self, chunk: Any, index: Optional[int] = None) -> None:
        """
        Validates an individual chunk for structure and content validity.
        
        Args:
            chunk: DocumentChunk instance or dict representing a chunk.
            index: Optional position index for error reporting.

        Raises:
            InvalidChunkError: If chunk structure is invalid or text is empty/whitespace.
        """
        loc = f"at index {index}" if index is not None else ""

        if chunk is None:
            raise InvalidChunkError(f"Chunk {loc} cannot be None.")

        # Extract chunk_text from DocumentChunk or dict
        if isinstance(chunk, DocumentChunk):
            chunk_text = chunk.chunk_text
        elif isinstance(chunk, dict):
            if "chunk_text" not in chunk:
                raise InvalidChunkError(f"Chunk dictionary {loc} missing required 'chunk_text' field.")
            chunk_text = chunk["chunk_text"]
        else:
            raise InvalidChunkError(
                f"Invalid chunk structure {loc}: expected DocumentChunk or dict, got {type(chunk).__name__}."
            )

        if not isinstance(chunk_text, str):
            raise InvalidChunkError(
                f"Chunk text {loc} must be a string, got {type(chunk_text).__name__}."
            )

        if not chunk_text.strip():
            raise InvalidChunkError(
                f"Chunk text {loc} cannot be empty or whitespace-only."
            )

    def validate_vector(self, vector: list[float], index: Optional[int] = None) -> None:
        """
        Validates that a generated vector contains strictly 384 finite numerical values.
        
        Args:
            vector: Embedding vector as list of floats.
            index: Optional index for error reporting.

        Raises:
            EmbeddingDimensionMismatchError: If vector length != 384.
            NonFiniteVectorError: If vector contains NaN or Inf values.
        """
        loc = f"at index {index}" if index is not None else ""

        if len(vector) != self.dimension:
            raise EmbeddingDimensionMismatchError(
                f"Vector dimension mismatch {loc}: expected {self.dimension}, got {len(vector)}."
            )

        for val_idx, val in enumerate(vector):
            if not isinstance(val, (int, float)) or not math.isfinite(val):
                raise NonFiniteVectorError(
                    f"Non-finite vector value {loc} at position {val_idx}: {val}."
                )

    def embed_texts(
        self,
        texts: list[str],
        batch_size: Optional[int] = None,
    ) -> list[list[float]]:
        """
        Encodes a list of raw strings into 384-dimensional normalized vector embeddings.
        Processes inputs in configurable batches preserving input order.
        
        Args:
            texts: List of non-empty text strings to embed.
            batch_size: Optional override for batch processing size.

        Returns:
            List of 384-dimensional vector float lists in exact input order.

        Raises:
            InvalidChunkError: If any input text is empty or non-string.
            EmbeddingGenerationError: If encoding fails.
            EmbeddingDimensionMismatchError: If output dimension is unexpected.
            NonFiniteVectorError: If non-finite values are detected.
        """
        if not texts:
            return []

        # Validate all texts
        for i, text in enumerate(texts):
            if not isinstance(text, str) or not text.strip():
                raise InvalidChunkError(
                    f"Text at index {i} cannot be empty or whitespace-only."
                )

        eff_batch_size = batch_size or self.batch_size
        if eff_batch_size <= 0:
            raise ValueError(f"batch_size must be positive, got {eff_batch_size}.")

        model = self._get_model()

        try:
            # model.encode supports batch_size, normalize_embeddings
            # Returns numpy ndarray of shape (len(texts), dimension)
            raw_embeddings = model.encode(
                texts,
                batch_size=eff_batch_size,
                normalize_embeddings=self.normalize_embeddings,
                show_progress_bar=False,
            )
        except Exception as exc:
            if isinstance(exc, EmbeddingError):
                raise
            logger.error("Error during embedding generation: %s", exc)
            raise EmbeddingGenerationError(f"Embedding generation failed: {exc}") from exc

        # Convert to numpy array if not already
        if not isinstance(raw_embeddings, np.ndarray):
            raw_embeddings = np.array(raw_embeddings)

        # Validate shape
        if len(raw_embeddings.shape) == 1:
            raw_embeddings = np.expand_dims(raw_embeddings, axis=0)

        if raw_embeddings.shape[0] != len(texts):
            raise EmbeddingGenerationError(
                f"Generated embedding count ({raw_embeddings.shape[0]}) does not match "
                f"input text count ({len(texts)})."
            )

        if raw_embeddings.shape[1] != self.dimension:
            raise EmbeddingDimensionMismatchError(
                f"Generated embedding dimension ({raw_embeddings.shape[1]}) does not match "
                f"expected dimension ({self.dimension})."
            )

        # Check for non-finite values across entire batch using numpy for speed
        if not np.all(np.isfinite(raw_embeddings)):
            raise NonFiniteVectorError(
                "Generated embeddings contain non-finite values (NaN or Inf)."
            )

        # Convert to list of python float lists
        result: list[list[float]] = raw_embeddings.tolist()

        return result

    def embed_chunks(
        self,
        chunks: list[Union[DocumentChunk, dict[str, Any]]],
        batch_size: Optional[int] = None,
    ) -> list[ChunkEmbedding]:
        """
        Generates 384-dimensional embeddings for structured DocumentChunk objects.
        Preserves all source metadata, provenance, and exact sequential ordering.
        
        Args:
            chunks: List of DocumentChunk objects or chunk dictionaries.
            batch_size: Optional batch size override.

        Returns:
            List of ChunkEmbedding objects with full metadata and vectors.
        """
        if not chunks:
            return []

        # 1. Validate all input chunks first
        for i, chunk in enumerate(chunks):
            self.validate_chunk(chunk, index=i)

        # 2. Extract texts while preserving 1:1 index mapping
        texts: list[str] = []
        for chunk in chunks:
            if isinstance(chunk, DocumentChunk):
                texts.append(chunk.chunk_text)
            else:
                texts.append(chunk["chunk_text"])

        # 3. Generate batch embeddings
        vectors = self.embed_texts(texts, batch_size=batch_size)

        if len(vectors) != len(chunks):
            raise EmbeddingGenerationError(
                f"Embedding count ({len(vectors)}) does not match input chunk count ({len(chunks)})."
            )

        # 4. Assemble ChunkEmbedding results retaining full provenance
        results: list[ChunkEmbedding] = []
        for i, (chunk, vector) in enumerate(zip(chunks, vectors)):
            if isinstance(chunk, DocumentChunk):
                chunk_id = chunk.chunk_id
                doc_id = chunk.document_id
                filename = chunk.filename
                chunk_idx = chunk.chunk_index
                chunk_text = chunk.chunk_text
                sec_title = chunk.section_title
                page_num = chunk.page_number
                meta = dict(chunk.metadata or {})
            else:
                chunk_id = chunk.get("chunk_id")
                doc_id = chunk.get("document_id")
                filename = chunk.get("filename")
                chunk_idx = chunk.get("chunk_index", i)
                chunk_text = chunk["chunk_text"]
                sec_title = chunk.get("section_title")
                page_num = chunk.get("page_number")
                meta = dict(chunk.get("metadata", {}) or {})

            # Double check individual vector finite and length constraint
            self.validate_vector(vector, index=i)

            emb = ChunkEmbedding(
                chunk_id=chunk_id,
                document_id=doc_id,
                filename=filename,
                chunk_index=chunk_idx,
                chunk_text=chunk_text,
                section_title=sec_title,
                page_number=page_num,
                metadata=meta,
                embedding=vector,
                embedding_model=self.model_name,
                dimension=self.dimension,
            )
            results.append(emb)

        return results

    def embed_document_result(
        self,
        chunking_result: DocumentChunkingResult,
        batch_size: Optional[int] = None,
    ) -> DocumentEmbeddingResult:
        """
        Embeds all chunks within a DocumentChunkingResult.
        
        Args:
            chunking_result: DocumentChunkingResult produced by Task 003D.
            batch_size: Optional batch size override.

        Returns:
            DocumentEmbeddingResult containing ordered ChunkEmbeddings and audit metadata.
        """
        eff_batch_size = batch_size or self.batch_size

        if not chunking_result.chunks:
            return DocumentEmbeddingResult(
                document_id=chunking_result.document_id,
                filename=chunking_result.filename,
                total_chunks=0,
                embedding_model=self.model_name,
                embedding_dimension=self.dimension,
                embeddings=[],
                metadata={
                    "normalized": self.normalize_embeddings,
                    "batch_size": eff_batch_size,
                    "note": "Document contained zero chunks to embed.",
                },
            )

        chunk_embeddings = self.embed_chunks(chunking_result.chunks, batch_size=eff_batch_size)

        return DocumentEmbeddingResult(
            document_id=chunking_result.document_id,
            filename=chunking_result.filename,
            total_chunks=len(chunk_embeddings),
            embedding_model=self.model_name,
            embedding_dimension=self.dimension,
            embeddings=chunk_embeddings,
            metadata={
                "normalized": self.normalize_embeddings,
                "batch_size": eff_batch_size,
                "source_chunks_count": chunking_result.total_chunks,
                "file_type": chunking_result.file_type,
            },
        )

    def embed_query(self, query: str) -> list[float]:
        """
        Embeds a single search query string into a 384-dimensional normalized vector.
        Ensures queries and document chunks use the identical model and normalization strategy.
        
        Args:
            query: User search query string.

        Returns:
            384-dimensional normalized float vector.

        Raises:
            InvalidChunkError: If query is empty or whitespace-only.
        """
        if not isinstance(query, str) or not query.strip():
            raise InvalidChunkError("Query cannot be empty or whitespace-only.")

        vectors = self.embed_texts([query], batch_size=1)
        return vectors[0]


# ---------------------------------------------------------------------------
# Dependency Provider
# ---------------------------------------------------------------------------

_global_embedding_service: Optional[EmbeddingService] = None


def get_embedding_service() -> EmbeddingService:
    """
    FastAPI dependency and application service provider returning the singleton
    EmbeddingService instance. Reuses cached model across requests.
    """
    global _global_embedding_service
    if _global_embedding_service is None:
        _global_embedding_service = EmbeddingService()
    return _global_embedding_service
