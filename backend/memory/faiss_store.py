"""
FAISS Vector Store — The Palace (Hierarchical Memory)

Maintains a per-dataset FAISS index of column-level metadata embeddings.
At query time, only the most relevant column descriptions are retrieved
and injected into the LLM prompt, keeping the context window lean.

Index type: IndexFlatIP (inner-product on L2-normalised vectors = cosine sim).
Persistence: index + texts saved to disk under `data/faiss_indexes/<dataset_id>/`.
"""

from __future__ import annotations

import json
from pathlib import Path

import faiss
import numpy as np
from openai import OpenAI

from backend.config import settings


class FAISSStore:
    """Build, persist, load, and query a per-dataset FAISS index."""

    def __init__(self, dataset_id: str) -> None:
        self.dataset_id = dataset_id
        self.index_dir: Path = settings.faiss_dir / dataset_id
        self.index_path: Path = self.index_dir / "index.faiss"
        self.texts_path: Path = self.index_dir / "texts.json"

        self._client = OpenAI(
            api_key=settings.openai_api_key,
            base_url=settings.openai_base_url,
        )
        self._index: faiss.IndexFlatIP | None = None
        self._texts: list[str] | None = None

    # ── Build ──────────────────────────────────────────────────

    def build_index(
        self,
        texts: list[str],
        embeddings: list[list[float]],
    ) -> None:
        """Create a new FAISS index, normalise vectors, and persist."""
        self.index_dir.mkdir(parents=True, exist_ok=True)

        vectors = np.array(embeddings, dtype=np.float32)
        faiss.normalize_L2(vectors)  # cosine similarity via inner product

        dimension = vectors.shape[1]
        index = faiss.IndexFlatIP(dimension)
        index.add(vectors)

        faiss.write_index(index, str(self.index_path))
        self.texts_path.write_text(json.dumps(texts, ensure_ascii=False))

        self._index = index
        self._texts = texts

    # ── Search ─────────────────────────────────────────────────

    def search(self, query: str, top_k: int = 5) -> str:
        """Embed the query and return the top-k most relevant text chunks."""
        self._load()

        # Embed the natural-language query
        resp = self._client.embeddings.create(
            model=settings.embedding_model,
            input=[query],
        )
        q_vec = np.array([resp.data[0].embedding], dtype=np.float32)
        faiss.normalize_L2(q_vec)

        k = min(top_k, len(self._texts))  # type: ignore[arg-type]
        scores, indices = self._index.search(q_vec, k)  # type: ignore[union-attr]

        results: list[str] = []
        for score, idx in zip(scores[0], indices[0]):
            if idx >= 0:
                results.append(self._texts[idx])  # type: ignore[index]

        return "\n\n".join(results) if results else "No schema context found."

    # ── Internals ──────────────────────────────────────────────

    def _load(self) -> None:
        """Lazy-load index and texts from disk."""
        if self._index is not None:
            return
        if not self.index_path.exists():
            raise FileNotFoundError(
                f"No FAISS index found for dataset '{self.dataset_id}'. "
                f"Expected path: {self.index_path}"
            )
        self._index = faiss.read_index(str(self.index_path))
        self._texts = json.loads(self.texts_path.read_text())
