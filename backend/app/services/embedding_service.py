import os
import hashlib
import math
import logging
import asyncio
from abc import ABC, abstractmethod
from typing import List, Optional, Dict, Any
from openai import AsyncOpenAI
from app.core.config import settings
from app.schemas.bidder import DocumentChunkItem

logger = logging.getLogger(__name__)


class BaseEmbeddingProvider(ABC):
    """Abstract base class for embedding providers."""

    @property
    @abstractmethod
    def model_name(self) -> str:
        pass

    @property
    @abstractmethod
    def dimension(self) -> int:
        pass

    @abstractmethod
    async def embed_texts(self, texts: List[str]) -> List[List[float]]:
        """Embed a list of text strings into vectors."""
        pass

    @abstractmethod
    async def embed_query(self, query: str) -> List[float]:
        """Embed a single search query into a vector."""
        pass


class NvidiaEmbeddingProvider(BaseEmbeddingProvider):
    """NVIDIA NIM OpenAI-compatible embedding provider.

    Target model: nvidia/nemotron-3.5-embed-1b (native dimension 2048).
    Asymmetric retrieval contract:
    - input_type="passage" for document indexing
    - input_type="query" for search retrieval queries
    Supports batching, bounded retries, timeouts, and strict dimension verification.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model_name: Optional[str] = None,
        expected_dim: Optional[int] = None,
    ):
        self.api_key = api_key or settings.NVIDIA_API_KEY
        self.base_url = base_url or settings.NVIDIA_BASE_URL
        self._model_name = model_name or settings.NVIDIA_EMBEDDING_MODEL
        self._dimension = expected_dim or settings.EMBEDDING_DIM
        self._client: Optional[AsyncOpenAI] = None

        if not self.api_key:
            raise ValueError("NVIDIA_API_KEY is not configured for NvidiaEmbeddingProvider.")

        try:
            self._client = AsyncOpenAI(
                base_url=self.base_url,
                api_key=self.api_key,
                timeout=60.0,
                max_retries=1,
            )
        except TypeError:
            import httpx
            self._client = AsyncOpenAI(
                base_url=self.base_url,
                api_key=self.api_key,
                timeout=60.0,
                max_retries=1,
                http_client=httpx.AsyncClient(),
            )

    @property
    def model_name(self) -> str:
        return self._model_name

    @property
    def dimension(self) -> int:
        return self._dimension

    async def _embed_batch_with_retry(
        self,
        batch_texts: List[str],
        input_type: str = "passage",
        max_attempts: int = 2,
    ) -> List[List[float]]:
        """Call NVIDIA embeddings endpoint with retry and asymmetric input_type."""
        if input_type not in ("passage", "query"):
            raise ValueError(f"Invalid input_type '{input_type}'. Expected 'passage' or 'query'.")

        last_err = None
        for attempt in range(1, max_attempts + 1):
            try:
                response = await self._client.embeddings.create(
                    model=self._model_name,
                    input=batch_texts,
                    extra_body={"input_type": input_type},
                )
                embeddings = [item.embedding for item in response.data]

                # Strict dimension verification
                for emb in embeddings:
                    actual_dim = len(emb)
                    if actual_dim != self._dimension:
                        raise ValueError(
                            f"Embedding dimension mismatch: expected {self._dimension} from config/pgvector, "
                            f"but NVIDIA endpoint returned {actual_dim} for model '{self._model_name}'."
                        )

                return embeddings
            except Exception as e:
                last_err = e
                if "Embedding dimension mismatch" in str(e):
                    # Do not retry on fundamental dimension mismatch
                    raise
                logger.warning(f"Embedding attempt {attempt} failed for {len(batch_texts)} texts: {e}")
                if attempt < max_attempts:
                    await asyncio.sleep(1.0 * attempt)

        raise RuntimeError(f"NVIDIA embedding failed after {max_attempts} attempts: {last_err}")

    async def embed_texts(self, texts: List[str], batch_size: int = 16) -> List[List[float]]:
        """Embed list of document passages in batches using input_type='passage'."""
        if not texts:
            return []

        all_embeddings: List[List[float]] = []
        for i in range(0, len(texts), batch_size):
            batch = texts[i:i + batch_size]
            batch_emb = await self._embed_batch_with_retry(batch, input_type="passage")
            all_embeddings.extend(batch_emb)

        return all_embeddings

    async def embed_query(self, query: str) -> List[float]:
        """Embed a single retrieval query using input_type='query'."""
        results = await self._embed_batch_with_retry([query], input_type="query")
        if not results:
            raise RuntimeError("Empty embedding returned for query.")
        return results[0]


class StubEmbeddingProvider(BaseEmbeddingProvider):
    """Deterministic, zero-network stub embedding provider.

    Generates normalized pseudo-embeddings of exact dimension matching settings.EMBEDDING_DIM
    from text tokens. Permitted ONLY in explicit test/development configurations.
    """

    def __init__(
        self,
        model_name: str = "stub-deterministic-2048",
        dimension: Optional[int] = None,
    ):
        self._model_name = model_name
        self._dimension = dimension or settings.EMBEDDING_DIM

    @property
    def model_name(self) -> str:
        return self._model_name

    @property
    def dimension(self) -> int:
        return self._dimension

    def _generate_vector(self, text: str) -> List[float]:
        """Deterministically map text tokens into a unit-normalized vector of size self._dimension."""
        vec = [0.0] * self._dimension
        tokens = text.lower().replace("-", " ").replace("_", " ").split()
        if not tokens:
            tokens = ["<empty>"]

        for idx, token in enumerate(tokens):
            h = int(hashlib.sha256(token.encode("utf-8")).hexdigest(), 16)
            pos = h % self._dimension
            sign = 1.0 if ((h >> 8) & 1) == 0 else -1.0
            vec[pos] += sign * (1.0 / math.sqrt(idx + 1.0))

        full_hash = int(hashlib.md5(text.encode("utf-8")).hexdigest(), 16)
        for offset in range(min(32, self._dimension)):
            vec[offset] += 0.05 * (1.0 if ((full_hash >> offset) & 1) else -1.0)

        norm = math.sqrt(sum(x * x for x in vec))
        if norm > 0.0:
            vec = [x / norm for x in vec]
        else:
            vec[0] = 1.0

        if len(vec) != self._dimension:
            raise ValueError(
                f"Embedding dimension mismatch in Stub: expected {self._dimension}, got {len(vec)}"
            )

        return vec

    async def embed_texts(self, texts: List[str]) -> List[List[float]]:
        return [self._generate_vector(t) for t in texts]

    async def embed_query(self, query: str) -> List[float]:
        return self._generate_vector(query)


def _is_explicit_test_or_mock_dev_allowed() -> bool:
    """Determine if StubEmbeddingProvider is explicitly permitted.

    CRITICAL: AUTH_DEV_MODE is strictly decoupled and NEVER authorizes StubEmbeddingProvider.
    Production mode unconditionally forbids StubEmbeddingProvider.
    """
    env = getattr(settings, "ENVIRONMENT", "development").lower()
    if env == "production":
        return False
    if os.environ.get("PYTEST_CURRENT_TEST") or os.environ.get("TESTING"):
        return True
    return bool(getattr(settings, "ALLOW_MOCK_EMBEDDINGS", False))


class EmbeddingService:
    """Unified Embedding Service managing provider selection, validation, and chunk embedding."""

    def __init__(self, provider: Optional[BaseEmbeddingProvider] = None):
        if provider:
            self._provider = provider
        else:
            if settings.NVIDIA_API_KEY:
                try:
                    self._provider = NvidiaEmbeddingProvider()
                    logger.info(
                        f"Initialized NvidiaEmbeddingProvider using model '{self._provider.model_name}' "
                        f"(dimension={self._provider.dimension})."
                    )
                except Exception as e:
                    if not _is_explicit_test_or_mock_dev_allowed():
                        logger.error(
                            f"FATAL: NvidiaEmbeddingProvider failed to initialize ({e}). "
                            "Silent stub fallback is strictly forbidden."
                        )
                        raise RuntimeError(
                            f"Embedding service initialization failed ({e}). "
                            "Production mode forbids silent fallback to StubEmbeddingProvider."
                        )
                    logger.warning(
                        f"Could not initialize NvidiaEmbeddingProvider ({e}). "
                        "Semantic retrieval operating in MOCK mode (StubEmbeddingProvider)."
                    )
                    self._provider = StubEmbeddingProvider()
            else:
                if not _is_explicit_test_or_mock_dev_allowed():
                    raise RuntimeError(
                        "NVIDIA_API_KEY is not configured and StubEmbeddingProvider is forbidden "
                        "(set ALLOW_MOCK_EMBEDDINGS=true only in non-production dev/test)."
                    )
                logger.warning(
                    "No NVIDIA_API_KEY set. Semantic retrieval operating in MOCK mode (StubEmbeddingProvider)."
                )
                self._provider = StubEmbeddingProvider()

    @property
    def provider(self) -> BaseEmbeddingProvider:
        return self._provider

    @property
    def dimension(self) -> int:
        return self._provider.dimension

    @property
    def model_name(self) -> str:
        return self._provider.model_name

    def validate_embedding_space(self, chunk_embedding_model: Optional[str]) -> bool:
        """Verify that stored chunk vectors belong to the active embedding model space.

        Prevents mixing incompatible spaces (e.g., stub-deterministic-2048 or nemotron-3-embed-1b
        with nvidia/nemotron-3.5-embed-1b) even if dimensions match (2048).
        """
        if not chunk_embedding_model:
            return False
        return chunk_embedding_model == self.model_name

    async def embed_chunks(
        self,
        chunks: List[DocumentChunkItem],
        batch_size: int = 16,
    ) -> List[DocumentChunkItem]:
        """Embed a list of DocumentChunkItem objects and attach the embedding vector to each."""
        if not chunks:
            return []

        texts = [c.chunk_text for c in chunks]
        embeddings = await self._provider.embed_texts(texts)

        if len(embeddings) != len(chunks):
            raise RuntimeError(f"Embedding count mismatch: received {len(embeddings)} vectors for {len(chunks)} chunks.")

        for chunk_item, emb in zip(chunks, embeddings):
            if len(emb) != settings.EMBEDDING_DIM:
                raise ValueError(
                    f"Embedding dimension mismatch: expected {settings.EMBEDDING_DIM} from config/pgvector, "
                    f"but received {len(emb)} for chunk {chunk_item.chunk_id}."
                )
            chunk_item.embedding = emb

        return chunks

    async def embed_query(self, query: str) -> List[float]:
        """Generate normalized embedding for a single query text."""
        vec = await self._provider.embed_query(query)
        if len(vec) != settings.EMBEDDING_DIM:
            raise ValueError(
                f"Embedding dimension mismatch: expected {settings.EMBEDDING_DIM} from config/pgvector, "
                f"but received {len(vec)} for query."
            )
        return vec


def get_embedding_service(force_stub: bool = False) -> EmbeddingService:
    """Factory returning an initialized EmbeddingService instance."""
    if force_stub:
        if not _is_explicit_test_or_mock_dev_allowed():
            raise RuntimeError("force_stub=True is strictly forbidden in production.")
        return EmbeddingService(provider=StubEmbeddingProvider())
    return EmbeddingService()
