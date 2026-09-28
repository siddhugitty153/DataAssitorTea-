"""
Agentic Data Assistant — Configuration
Loads settings from environment variables / .env file.
"""

from pydantic_settings import BaseSettings
from pydantic import Field
from pathlib import Path


class Settings(BaseSettings):
    """Application-wide configuration, loaded from .env or environment."""

    # ── LLM Provider (Using GitHub Codespace Token) ──
    openai_api_key: str = Field(default_factory=lambda: __import__("os").environ.get("GITHUB_TOKEN", ""))
    openai_base_url: str = "https://models.inference.ai.azure.com"
    openai_model: str = "gpt-4o"
    embedding_model: str = "text-embedding-3-small"

    # ── Sandbox ──
    sandbox_image: str = "data-sandbox"
    sandbox_timeout: int = 30
    sandbox_mem_limit: str = "512m"

    # ── Agent ──
    max_iterations: int = 3

    # ── Paths ──
    data_dir: Path = Path("data")
    faiss_dir: Path = Path("data/faiss_indexes")

    model_config = {"env_file": ".env", "extra": "ignore"}


settings = Settings()
