"""
Embedding Provider Abstraction.

Defines the interface for text embedding backends.  Used by the memory
system to vectorise schema metadata, queries, and past analyses.

Usage:
    from backend.core import create_embedder

    embedder = create_embedder("gemini")
    vectors = await embedder.embed(["Column 'revenue' — dtype: float64"])
"""

from __future__ import annotations

from abc import ABC, abstractmethod


class EmbeddingProvider(ABC):
    """
    Provider-agnostic interface for text embeddings.

    Concrete providers (Gemini, OpenAI, local sentence-transformers, …)
    must implement ``embed`` and expose ``dimension``.
    """

    @abstractmethod
    async def embed(self, texts: list[str]) -> list[list[float]]:
        """
        Embed a batch of texts into dense vectors.

        Args:
            texts: List of strings to embed.

        Returns:
            List of embedding vectors, one per input text.
            Each vector has length == ``self.dimension``.
        """

    @property
    @abstractmethod
    def dimension(self) -> int:
        """Dimensionality of the embedding vectors produced by this provider."""

    async def embed_single(self, text: str) -> list[float]:
        """Convenience method — embed a single text string."""
        results = await self.embed([text])
        return results[0]


# ────────────────────────────────────────────────────────────────
# Factory
# ────────────────────────────────────────────────────────────────

def create_embedder(provider: str | None = None) -> EmbeddingProvider:
    """
    Create an embedding provider instance.

    Args:
        provider: One of 'gemini', 'openai'.
                  If None, reads from ``settings.embedding_provider``.

    Returns:
        A concrete EmbeddingProvider.

    Raises:
        ValueError: If the provider is unknown.
    """
    if provider is None:
        from backend.config import settings
        provider = settings.embedding_provider

    if provider == "gemini":
        from backend.providers.gemini import GeminiEmbedder
        return GeminiEmbedder()

    if provider == "ollama":
        from backend.providers.ollama_provider import OllamaEmbedder
        return OllamaEmbedder()

    if provider == "openai":
        from backend.providers.openai_provider import OpenAIEmbedder
        return OpenAIEmbedder()

    raise ValueError(
        f"Unknown embedding provider '{provider}'. "
        f"Supported: 'gemini', 'ollama', 'openai'."
    )
