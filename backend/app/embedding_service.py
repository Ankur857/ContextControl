import math
import time
import hashlib
import logging
from typing import List
from abc import ABC, abstractmethod
from app.config import (
    GEMINI_API_KEY,
    EMBEDDING_MODEL,
    EMBEDDING_DIMENSION,
    MAX_EMBEDDING_BATCH_SIZE,
)

logger = logging.getLogger("contextcontrol.embeddings")


class BaseEmbeddingProvider(ABC):
    @abstractmethod
    def embed_texts(self, texts: List[str]) -> List[List[float]]:
        """Generates embedding vectors for a batch of text chunks."""
        pass

    @abstractmethod
    def embed_query(self, query: str) -> List[float]:
        """Generates an embedding vector for a search query."""
        pass

    @abstractmethod
    def get_model_name(self) -> str:
        """Returns the model identifier string."""
        pass

    @abstractmethod
    def get_dimension(self) -> int:
        """Returns the embedding vector dimension."""
        pass


class DeterministicMockEmbeddingProvider(BaseEmbeddingProvider):
    """
    Deterministic pseudo-embedding provider for testing, offline development,
    and reproducible benchmarks. Generates unit-normalized 768-dim vectors
    derived from token hashes so text relevance produces meaningful cosine scores.
    """

    def __init__(self, dimension: int = EMBEDDING_DIMENSION):
        self.dimension = dimension
        self.model_name = "mock-embedding-v1"

    def get_model_name(self) -> str:
        return self.model_name

    def get_dimension(self) -> int:
        return self.dimension

    def _embed_single(self, text: str) -> List[float]:
        if not text:
            return [0.0] * self.dimension

        vec = [0.0] * self.dimension
        # Tokenize into word tokens
        import re

        words = re.findall(r"[a-zA-Z0-9_]+", text.lower())

        if not words:
            # Fall back to character bigrams
            words = [text[i : i + 2].lower() for i in range(len(text) - 1)] or ["empty"]

        for word in words:
            h = hashlib.sha256(word.encode("utf-8")).digest()
            # Map word to multiple feature dimensions
            for i in range(0, min(16, len(h) - 4), 4):
                idx = int.from_bytes(h[i : i + 2], "big") % self.dimension
                sign = 1.0 if h[i + 2] % 2 == 0 else -1.0
                weight = 1.0 + (h[i + 3] / 255.0)
                vec[idx] += sign * weight

        # Normalize to L2 unit length
        norm = math.sqrt(sum(x * x for x in vec))
        if norm > 1e-9:
            vec = [x / norm for x in vec]
        else:
            vec[0] = 1.0

        return vec

    def embed_texts(self, texts: List[str]) -> List[List[float]]:
        return [self._embed_single(t) for t in texts]

    def embed_query(self, query: str) -> List[float]:
        return self._embed_single(query)


class GeminiEmbeddingProvider(BaseEmbeddingProvider):
    """
    Official Google Gen AI SDK embedding provider using models like 'text-embedding-004'.
    Handles batching, timeouts, and safe retries for transient errors.
    """

    def __init__(
        self,
        api_key: str = GEMINI_API_KEY,
        model_name: str = EMBEDDING_MODEL,
        dimension: int = EMBEDDING_DIMENSION,
        batch_size: int = MAX_EMBEDDING_BATCH_SIZE,
    ):
        self.api_key = api_key.strip() if api_key else ""
        self.model_name = model_name.strip()
        self.dimension = dimension
        self.batch_size = max(1, min(batch_size, 50))
        self._client = None

    def _get_client(self):
        if not self.api_key:
            raise ValueError(
                "GEMINI_API_KEY is not configured. Please set GEMINI_API_KEY in backend/.env "
                "or enable mock mode for testing."
            )
        if self._client is None:
            from google import genai

            self._client = genai.Client(api_key=self.api_key)
        return self._client

    def get_model_name(self) -> str:
        return self.model_name

    def get_dimension(self) -> int:
        return self.dimension

    def _call_with_retry(self, client, contents: List[str], max_retries: int = 3):
        for attempt in range(1, max_retries + 1):
            try:
                response = client.models.embed_content(
                    model=self.model_name,
                    contents=contents,
                )
                return response
            except Exception as e:
                err_msg = str(e)
                # Check for rate limit or transient service error
                if attempt < max_retries and any(
                    code in err_msg for code in ("429", "503", "ResourceExhausted", "DeadlineExceeded")
                ):
                    backoff = attempt * 1.5
                    logger.warning(
                        f"Transient Gemini embedding error (attempt {attempt}/{max_retries}): {err_msg}. "
                        f"Retrying in {backoff:.1f}s..."
                    )
                    time.sleep(backoff)
                else:
                    # Sanitize message to ensure API key is never in logs or exceptions
                    sanitized = err_msg.replace(self.api_key, "[REDACTED]") if self.api_key else err_msg
                    raise RuntimeError(f"Gemini embedding API failed: {sanitized}") from None

    def embed_texts(self, texts: List[str]) -> List[List[float]]:
        if not texts:
            return []

        client = self._get_client()
        all_embeddings: List[List[float]] = []

        # Process in batches
        for i in range(0, len(texts), self.batch_size):
            batch = texts[i : i + self.batch_size]
            response = self._call_with_retry(client, batch)

            # Response contains embeddings list
            if hasattr(response, "embeddings") and response.embeddings:
                for item in response.embeddings:
                    if hasattr(item, "values"):
                        all_embeddings.append(list(item.values))
                    else:
                        all_embeddings.append(list(item))
            elif hasattr(response, "embedding") and response.embedding:
                vals = getattr(response.embedding, "values", response.embedding)
                all_embeddings.append(list(vals))
            else:
                raise ValueError("Unexpected response format from Gemini embedding API")

        # Validate dimensions
        for vec in all_embeddings:
            if len(vec) != self.dimension:
                # If model dimension differs from configured default, update detected dimension
                self.dimension = len(vec)
                break

        return all_embeddings

    def embed_query(self, query: str) -> List[float]:
        results = self.embed_texts([query])
        if not results:
            return [0.0] * self.dimension
        return results[0]


def get_embedding_provider(
    provider_name: str = None, use_mock: bool = False
) -> BaseEmbeddingProvider:
    """Factory returning the requested embedding provider."""
    if use_mock:
        return DeterministicMockEmbeddingProvider()

    from app.config import EMBEDDING_PROVIDER

    name = (provider_name or EMBEDDING_PROVIDER).lower()
    if name == "mock":
        return DeterministicMockEmbeddingProvider()
    elif name == "gemini":
        return GeminiEmbeddingProvider()
    else:
        # Default fallback
        return GeminiEmbeddingProvider()

