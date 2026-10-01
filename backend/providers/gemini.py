"""
Google Gemini provider — LLM and Embeddings via the OpenAI compatibility layer.

Gemini exposes an OpenAI-compatible REST API at:
    https://generativelanguage.googleapis.com/v1beta/openai/

This lets us use the standard ``openai`` Python SDK without any Gemini-
specific code, which means LangChain and other OpenAI-expecting tools
work out of the box.

Required env var:  GEMINI_API_KEY
"""

from __future__ import annotations

import asyncio
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
def _get_client() -> AsyncOpenAI:
    """Lazy-create a single AsyncOpenAI client pointing at Gemini."""
    from backend.config import settings

    return AsyncOpenAI(
        api_key=settings.gemini_api_key,
        base_url=settings.gemini_base_url,
    )


# ────────────────────────────────────────────────────────────────
# LLM Provider
# ────────────────────────────────────────────────────────────────

class GeminiLLM(LLMProvider):
    """
    Gemini chat completions via the OpenAI compatibility endpoint.

    Supports both synchronous (``generate``) and streaming
    (``generate_stream``) modes.
    """

    def __init__(self) -> None:
        from backend.config import settings
        self._model = settings.gemini_model

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
        client = _get_client()

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
        client = _get_client()

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

class GeminiEmbedder(EmbeddingProvider):
    """
    Gemini text embeddings via the OpenAI compatibility endpoint.

    Model: gemini-embedding-2  (3072-dimensional vectors).
    Batch size: 100 texts per API call.
    """

    BATCH_SIZE = 100

    def __init__(self) -> None:
        from backend.config import settings
        self._model = settings.gemini_embedding_model
        self._dimension: int | None = None

    @property
    def dimension(self) -> int:
        # gemini-embedding-2 produces 3072-dim vectors.
        # We'll discover the real dimension on first call if needed.
        if self._dimension is not None:
            return self._dimension
        return 3072  # default for gemini-embedding-2

    async def embed(self, texts: list[str]) -> list[list[float]]:
        client = _get_client()
        all_embeddings: list[list[float]] = []

        for i in range(0, len(texts), self.BATCH_SIZE):
            batch = texts[i : i + self.BATCH_SIZE]

            response = await client.embeddings.create(
                model=self._model,
                input=batch,
            )

            batch_embeddings = [item.embedding for item in response.data]
            all_embeddings.extend(batch_embeddings)

            # Discover true dimension from first response
            if self._dimension is None and batch_embeddings:
                self._dimension = len(batch_embeddings[0])

        return all_embeddings
