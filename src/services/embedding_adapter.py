"""Local ONNX embeddings shared by FAQ ingestion and retrieval."""

from typing import Any

from src.config import settings


class EmbeddingAdapter:
    """Embed documents and queries in the same, explicitly described vector space."""

    def __init__(
        self,
        provider: str | None = None,
        model: str | None = None,
        dimensions: int | None = None,
    ):
        configured_provider = provider or settings.EMBEDDING_PROVIDER or "onnx"
        self.provider = "onnx" if configured_provider.lower() in {
            "onnx", "local", "chroma", "default"
        } else configured_provider.lower()
        self.model = model or settings.EMBEDDING_MODEL or "all-MiniLM-L6-v2"
        self.dimensions = dimensions or settings.EMBEDDING_DIMENSIONS or 384
        self._embedding_function: Any = None

    def get_manifest(self) -> dict[str, Any]:
        return {
            "embedding_provider": self.provider,
            "embedding_model": self.model,
            "embedding_dimensions": self.dimensions,
            "embedding_schema": "parrotgo-faq-v2",
            "embedding_metric": "cosine",
        }

    def _get_embedding_function(self):
        if self.provider != "onnx":
            raise ValueError("FAQ embedding provider must be 'onnx' (local CPU model)")
        if self.model != "all-MiniLM-L6-v2" or self.dimensions != 384:
            raise ValueError("ONNX FAQ embeddings require all-MiniLM-L6-v2 with 384 dimensions")
        if self._embedding_function is None:
            from chromadb.utils.embedding_functions import ONNXMiniLM_L6_V2

            self._embedding_function = ONNXMiniLM_L6_V2(
                preferred_providers=["CPUExecutionProvider"]
            )
        return self._embedding_function

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        """Produce real vectors, including when RAG is disabled during data ingestion."""
        if not texts:
            return []
        if any(not isinstance(text, str) or not text.strip() for text in texts):
            raise ValueError("Embedding input must contain non-empty text")
        vectors = self._get_embedding_function()(texts)
        result = [[float(value) for value in vector] for vector in vectors]
        if any(len(vector) != self.dimensions for vector in result):
            raise ValueError("Embedding dimensions do not match the configured manifest")
        return result


embedding_adapter = EmbeddingAdapter()
