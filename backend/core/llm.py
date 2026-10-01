"""
LLM Provider Abstraction.

Defines the interface every LLM backend must implement. The engine talks
to this interface — never to a specific provider directly.

Usage:
    from backend.core import create_llm

    llm = create_llm("gemini")
    response = await llm.generate([
        {"role": "system", "content": "You are a data scientist."},
        {"role": "user", "content": "Write code to compute mean of column X."},
    ])
    print(response.content)
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import AsyncIterator


# ────────────────────────────────────────────────────────────────
# Data classes
# ────────────────────────────────────────────────────────────────

@dataclass
class LLMResponse:
    """Standardised response from any LLM provider."""

    content: str
    model: str = ""
    usage: dict[str, int] = field(default_factory=dict)
    finish_reason: str = ""


# ────────────────────────────────────────────────────────────────
# Abstract base
# ────────────────────────────────────────────────────────────────

class LLMProvider(ABC):
    """
    Provider-agnostic interface for large language models.

    Every concrete provider (Gemini, OpenAI, Anthropic, local, …)
    must implement ``generate`` and optionally ``generate_stream``.

    Messages use the standard OpenAI chat format — a list of dicts
    with ``role`` (system | user | assistant) and ``content`` keys.
    This is the lingua franca that every provider can translate from.
    """

    @abstractmethod
    async def generate(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float = 0.0,
        max_tokens: int = 4096,
    ) -> LLMResponse:
        """
        Send a chat completion request and return the full response.

        Args:
            messages:    List of {"role": ..., "content": ...} dicts.
            temperature: Sampling temperature (0 = deterministic).
            max_tokens:  Maximum tokens in the response.

        Returns:
            LLMResponse with the generated content.
        """

    async def generate_stream(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float = 0.0,
        max_tokens: int = 4096,
    ) -> AsyncIterator[str]:
        """
        Stream content token-by-token.

        Default implementation falls back to ``generate`` and yields
        the full content at once.  Providers should override this
        with a true streaming implementation.
        """
        response = await self.generate(
            messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        yield response.content

    @property
    @abstractmethod
    def model_name(self) -> str:
        """Return the model identifier (e.g. 'gemini-1.5-flash')."""


# ────────────────────────────────────────────────────────────────
# Factory
# ────────────────────────────────────────────────────────────────

def create_llm(provider: str | None = None) -> LLMProvider:
    """
    Create an LLM provider instance.

    Args:
        provider: One of 'gemini', 'openai'.
                  If None, reads from ``settings.llm_provider``.

    Returns:
        A concrete LLMProvider.

    Raises:
        ValueError: If the provider is unknown.
    """
    if provider is None:
        from backend.config import settings
        provider = settings.llm_provider

    if provider == "gemini":
        from backend.providers.gemini import GeminiLLM
        return GeminiLLM()

    if provider == "ollama":
        from backend.providers.ollama_provider import OllamaLLM
        return OllamaLLM()

    if provider == "openai":
        from backend.providers.openai_provider import OpenAILLM
        return OpenAILLM()

    raise ValueError(
        f"Unknown LLM provider '{provider}'. "
        f"Supported: 'gemini', 'ollama', 'openai'."
    )
