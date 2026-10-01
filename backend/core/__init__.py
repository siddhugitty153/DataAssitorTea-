"""
Core abstractions package.

Provides provider-agnostic interfaces for LLM, Embedding, and Sandbox
so the engine can swap backends without touching agent code.
"""

from backend.core.llm import LLMProvider, LLMResponse, create_llm
from backend.core.embedder import EmbeddingProvider, create_embedder
from backend.core.sandbox import SandboxProvider, ExecutionResult, create_sandbox

__all__ = [
    "LLMProvider",
    "LLMResponse",
    "create_llm",
    "EmbeddingProvider",
    "create_embedder",
    "SandboxProvider",
    "ExecutionResult",
    "create_sandbox",
]
