"""
Ollama provider — LLM and Embeddings via local Ollama server.

Ollama runs open-source models (Llama 3, Mistral, Qwen, Phi, etc.)
locally and exposes an OpenAI-compatible REST API at:
    http://localhost:11434/v1/

This provider uses the standard ``openai`` Python SDK pointed at
the local Ollama endpoint — zero extra dependencies.

Setup:
    1. Install Ollama:  https://ollama.com/download
    2. Pull a model:    ollama pull llama3.2
    3. Pull embeddings: ollama pull nomic-embed-text
    4. Set in .env:     LLM_PROVIDER=ollama

No API keys required. Runs 100% offline.
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
def _get_ollama_client() -> AsyncOpenAI:
    """
    Lazy-create a single AsyncOpenAI client pointing at local Ollama.

    Ollama's OpenAI-compatible endpoint runs at:
        http://localhost:11434/v1/
    No API key needed — we pass a dummy one to satisfy the SDK.
    """
    from backend.config import settings

    return AsyncOpenAI(
        api_key=settings.ollama_api_key,      # "ollama" (dummy)
        base_url=settings.ollama_base_url,    # http://localhost:11434/v1/
    )


# ────────────────────────────────────────────────────────────────
# LLM Provider
# ────────────────────────────────────────────────────────────────

class OllamaLLM(LLMProvider):
    """
    Local LLM via Ollama's OpenAI-compatible chat completions.

    Supported models (examples):
        - llama3.2, llama3.1, llama3.2:1b
        - mistral, mixtral
        - qwen2.5, qwen2.5-coder
        - phi3, phi3.5
        - codellama, deepseek-coder-v2
        - gemma2

    Change the model in .env:  OLLAMA_MODEL=llama3.2
    """

    def __init__(self) -> None:
        from backend.config import settings
        self._model = settings.ollama_model

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
        client = _get_ollama_client()

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
        client = _get_ollama_client()

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

class OllamaEmbedder(EmbeddingProvider):
    """
    Local text embeddings via Ollama's OpenAI-compatible endpoint.

    Recommended models:
        - nomic-embed-text  (768-dim, best quality/speed)
        - all-minilm         (384-dim, very fast)
        - mxbai-embed-large  (1024-dim, highest quality)

    Change in .env:  OLLAMA_EMBEDDING_MODEL=nomic-embed-text

    Batch size is limited to 100 texts per call to avoid OOM on
    consumer hardware.
    """

    BATCH_SIZE = 100

    def __init__(self) -> None:
        from backend.config import settings
        self._model = settings.ollama_embedding_model
        self._dimension: int | None = None

    @property
    def dimension(self) -> int:
        if self._dimension is not None:
            return self._dimension
        # Defaults per popular model — will auto-correct on first call
        _defaults = {
            "nomic-embed-text": 768,
            "all-minilm": 384,
            "mxbai-embed-large": 1024,
        }
        return _defaults.get(self._model, 768)

    async def embed(self, texts: list[str]) -> list[list[float]]:
        client = _get_ollama_client()
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
                    "Ollama embedding dimension discovered: %d (model: %s)",
                    self._dimension,
                    self._model,
                )

        return all_embeddings
