"""
Agentic Data Assistant — Configuration

Provider-agnostic settings loaded from environment variables / .env file.
Supports multiple LLM providers, embedding backends, and sandbox modes.
"""

from pydantic_settings import BaseSettings
from pydantic import Field
from pathlib import Path


class Settings(BaseSettings):
    """Application-wide configuration, loaded from .env or environment."""

    # ── Provider Selection ──────────────────────────────────────
    # Which backend to use for each capability.
    # Supported LLM/embedding: "gemini", "openai"
    # Supported sandbox: "subprocess" (dev), "docker" (production)
    llm_provider: str = "gemini"
    embedding_provider: str = "gemini"
    sandbox_provider: str = "subprocess"

    # ── Gemini (via OpenAI compatibility layer) ─────────────────
    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.5-flash"
    gemini_embedding_model: str = "gemini-embedding-2"
    gemini_base_url: str = "https://generativelanguage.googleapis.com/v1beta/openai/"

    # ── Ollama (local open-source) ──────────────────────────────
    # Install: https://ollama.com/download
    # Pull model: ollama pull llama3.2 && ollama pull nomic-embed-text
    ollama_base_url: str = "http://localhost:11434/v1/"
    ollama_model: str = "llama3.2"
    ollama_embedding_model: str = "nomic-embed-text"
    ollama_api_key: str = "ollama"  # dummy — Ollama doesn't need auth

    # ── OpenAI (future / alternative) ───────────────────────────
    openai_api_key: str = ""
    openai_model: str = "gpt-4o"
    openai_base_url: str = "https://api.openai.com/v1"
    openai_embedding_model: str = "text-embedding-3-small"

    # ── Sandbox ─────────────────────────────────────────────────
    sandbox_timeout: int = 30
    sandbox_mem_limit: str = "512m"
    sandbox_image: str = "data-sandbox"

    # ── Agent ───────────────────────────────────────────────────
    max_iterations: int = 3

    # ── Paths ───────────────────────────────────────────────────
    data_dir: Path = Path("data")
    faiss_dir: Path = Path("data/faiss_indexes")
    uploads_dir: Path = Path("data/uploads")

    model_config = {"env_file": ".env", "extra": "ignore"}


settings = Settings()
