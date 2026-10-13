"""
OpenAI provider — LLM and Embeddings via the official OpenAI API.

Uses the standard ``openai`` Python SDK directly against the OpenAI API.

Required env var:  OPENAI_API_KEY

Audit fix B8: This file was missing, causing ModuleNotFoundError when
selecting 'openai' as the LLM provider.
"""

from __future__ import annotations

import logging
from functools import lru_cache
from typing import AsyncIterator

from openai import AsyncOpenAI

from backend.core.llm import LLMProvider, LLMResponse
from backend.core.embedder import EmbeddingProvider

logger = logging.getLogger(__name__)


# ────────────────────────────────────────────────────────────────
# Shared client — one per process
# ────────────────────────────────────────────────────────────────

@lru_cache(maxsize=1)
def _get_openai_client() -> AsyncOpenAI:
    """Lazy-create a single AsyncOpenAI client pointing at OpenAI."""
    from backend.config import settings

    return AsyncOpenAI(
        api_key=settings.openai_api_key,
        base_url=settings.openai_base_url,
    )


# ────────────────────────────────────────────────────────────────
# LLM Provider
# ────────────────────────────────────────────────────────────────

class OpenAILLM(LLMProvider):
    """
    OpenAI chat completions via the official API.

    Supported models:
        - gpt-4o, gpt-4o-mini
        - gpt-4-turbo
        - o1, o1-mini

    Change the model in .env:  OPENAI_MODEL=gpt-4o
    """

    def __init__(self) -> None:
        from backend.config import settings
        self._model = settings.openai_model

    @property
    def model_name(self) -> str:
        return self._model

    async def generate(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float = 0.0,
        max_tokens: int = 4096,
    ) -> LLMResponse:
        client = _get_openai_client()

        response = await client.chat.completions.create(
            model=self._model,
            messages=messages,  # type: ignore[arg-type]
            temperature=temperature,
            max_tokens=max_tokens,
        )

        choice = response.choices[0]
        usage = {}
        if response.usage:
            usage = {
                "prompt_tokens": response.usage.prompt_tokens or 0,
                "completion_tokens": response.usage.completion_tokens or 0,
                "total_tokens": response.usage.total_tokens or 0,
            }

        return LLMResponse(
            content=choice.message.content or "",
            model=response.model or self._model,
            usage=usage,
            finish_reason=choice.finish_reason or "",
        )

    async def generate_stream(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float = 0.0,
        max_tokens: int = 4096,
    ) -> AsyncIterator[str]:
        client = _get_openai_client()

        stream = await client.chat.completions.create(
            model=self._model,
            messages=messages,  # type: ignore[arg-type]
            temperature=temperature,
            max_tokens=max_tokens,
            stream=True,
        )

        async for chunk in stream:
            if chunk.choices and chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content


# ────────────────────────────────────────────────────────────────
# Embedding Provider
# ────────────────────────────────────────────────────────────────

class OpenAIEmbedder(EmbeddingProvider):
    """
    OpenAI text embeddings via the official API.

    Recommended models:
        - text-embedding-3-small  (1536-dim, cost-effective)
        - text-embedding-3-large  (3072-dim, highest quality)
        - text-embedding-ada-002  (1536-dim, legacy)

    Change in .env:  OPENAI_EMBEDDING_MODEL=text-embedding-3-small

    Batch size: 100 texts per API call.
    """

    BATCH_SIZE = 100

    def __init__(self) -> None:
        from backend.config import settings
        self._model = settings.openai_embedding_model
        self._dimension: int | None = None

    @property
    def dimension(self) -> int:
        if self._dimension is not None:
            return self._dimension
        _defaults = {
            "text-embedding-3-small": 1536,
            "text-embedding-3-large": 3072,
            "text-embedding-ada-002": 1536,
        }
        return _defaults.get(self._model, 1536)

    async def embed(self, texts: list[str]) -> list[list[float]]:
        client = _get_openai_client()
        all_embeddings: list[list[float]] = []

        for i in range(0, len(texts), self.BATCH_SIZE):
            batch = texts[i : i + self.BATCH_SIZE]

            response = await client.embeddings.create(
                model=self._model,
                input=batch,
            )

            batch_embeddings = [item.embedding for item in response.data]
            all_embeddings.extend(batch_embeddings)

            # Auto-discover true dimension from first response
            if self._dimension is None and batch_embeddings:
                self._dimension = len(batch_embeddings[0])
                logger.info(
                    "OpenAI embedding dimension discovered: %d (model: %s)",
                    self._dimension,
                    self._model,
                )

        return all_embeddings
