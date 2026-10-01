"""
Memory Manager — The Orchestrator of the Memory Palace

This class manages the three tiers of memory:
1. Working Memory (Foyer) - SQLite: The last N messages.
2. Episodic Memory (Library) - FAISS + SQLite: Past analyses and code executions.
3. Schema Memory (Vault) - FAISS: The column metadata (existing FAISSStore).
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import numpy as np
import faiss

from backend.config import settings
from backend.core import create_embedder
from backend.memory.faiss_store import FAISSStore


class MemoryManager:
    """Unified interface for all memory operations."""

    def __init__(self, session_id: str, dataset_id: str) -> None:
        self.session_id = session_id
        self.dataset_id = dataset_id
        self.db_path = settings.data_dir / "memory.db"
        self._init_db()

        # Schema Memory (Existing FAISS Store)
        self.schema_store = FAISSStore(dataset_id)

        # Episodic Memory (FAISS Index for past analyses)
        self.episodic_dir = settings.faiss_dir / f"episodic_{dataset_id}"
        self.episodic_index_path = self.episodic_dir / "index.faiss"
        self.episodic_texts_path = self.episodic_dir / "texts.json"
        
        self.embedder = create_embedder()

        # Lazy load episodic index
        self._episodic_index: faiss.IndexFlatIP | None = None
        self._episodic_texts: list[str] = []

    # ── Database Initialization ─────────────────────────────────

    def _init_db(self) -> None:
        """Initialize SQLite tables for working memory and episodic metadata."""
        settings.data_dir.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS analyses (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    dataset_id TEXT NOT NULL,
                    query TEXT NOT NULL,
                    generated_code TEXT NOT NULL,
                    execution_result TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """
            )

    # ── Tier 1: Working Memory (Foyer) ──────────────────────────

    def add_message(self, role: str, content: str) -> None:
        """Add a message to the short-term working memory."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "INSERT INTO messages (session_id, role, content) VALUES (?, ?, ?)",
                (self.session_id, role, content),
            )

    def get_working_memory(self, limit: int = 4) -> list[dict[str, str]]:
        """Retrieve the last N messages for immediate context."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(
                """
                SELECT role, content FROM messages 
                WHERE session_id = ? 
                ORDER BY created_at DESC 
                LIMIT ?
                """,
                (self.session_id, limit),
            )
            rows = cursor.fetchall()
            
        # Return in chronological order
        return [{"role": row["role"], "content": row["content"]} for row in reversed(rows)]

    def clear_working_memory(self) -> None:
        """Clear the working memory for this session."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("DELETE FROM messages WHERE session_id = ?", (self.session_id,))

    # ── Tier 2: Episodic Memory (Library) ───────────────────────

    def _load_episodic(self) -> None:
        """Lazy load the FAISS index for episodic memory."""
        if self._episodic_index is not None:
            return

        if self.episodic_index_path.exists():
            self._episodic_index = faiss.read_index(str(self.episodic_index_path))
            self._episodic_texts = json.loads(self.episodic_texts_path.read_text())
        else:
            # Initialize empty episodic index. We don't know the exact dimension
            # until we embed something, but typical models are 768 or 1536. 
            # We'll delay creation until the first add() operation.
            pass

    async def save_analysis(self, query: str, code: str, result: str) -> None:
        """Save a completed analysis to both SQLite and FAISS."""
        # 1. Save to SQLite for structured lookup
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO analyses (session_id, dataset_id, query, generated_code, execution_result)
                VALUES (?, ?, ?, ?, ?)
                """,
                (self.session_id, self.dataset_id, query, code, result),
            )

        # 2. Save to FAISS for semantic lookup
        text_chunk = (
            f"Query: {query}\n"
            f"Code:\n```python\n{code}\n```\n"
            f"Result:\n{result}"
        )

        embeddings = await self.embedder.embed([text_chunk])
        vector = np.array(embeddings, dtype=np.float32)
        faiss.normalize_L2(vector)

        self._load_episodic()
        self.episodic_dir.mkdir(parents=True, exist_ok=True)

        if self._episodic_index is None:
            # First time creating the index
            dimension = vector.shape[1]
            self._episodic_index = faiss.IndexFlatIP(dimension)

        self._episodic_index.add(vector)
        self._episodic_texts.append(text_chunk)

        # Persist to disk
        faiss.write_index(self._episodic_index, str(self.episodic_index_path))
        self.episodic_texts_path.write_text(json.dumps(self._episodic_texts, ensure_ascii=False))

    async def get_memory_bundle(self, query: str) -> dict[str, str]:
        """
        Unified single-pass retrieval for all memory tiers.
        Embeds the query once and queries Schema + Episodic + Working memory.
        """
        # 1. Embed query once
        q_vec_list = await self.embedder.embed([query])
        q_vec = np.array(q_vec_list, dtype=np.float32)
        faiss.normalize_L2(q_vec)

        # 2. Tier 3: Schema Memory (Vault) - top 5 most relevant columns
        schema_context = await self.schema_store.search(q_vec=q_vec, top_k=5)

        # 3. Tier 2: Episodic Memory (Library)
        self._load_episodic()
        episodic_memory = "No past analyses found."
        if self._episodic_index is not None and self._episodic_index.ntotal > 0:
            k = min(2, len(self._episodic_texts))
            scores, indices = self._episodic_index.search(q_vec, k)
            matched = [
                self._episodic_texts[idx]
                for score, idx in zip(scores[0], indices[0])
                if idx >= 0 and score > 0.5
            ]
            if matched:
                episodic_memory = "\n\n---\n\n".join(matched)

        # 4. Tier 1: Working Memory (Foyer) - last 2 turns
        wm_messages = self.get_working_memory(limit=3)
        working_memory = "\n".join([f"{m['role'].title()}: {m['content'][:300]}" for m in wm_messages]) or "None"

        return {
            "schema_context": schema_context,
            "episodic_memory": episodic_memory,
            "working_memory": working_memory,
        }

    async def recall_past_analyses(self, query: str, top_k: int = 2) -> str:
        """Semantically search past analyses."""
        self._load_episodic()
        if self._episodic_index is None or self._episodic_index.ntotal == 0:
            return "No past analyses found."

        q_vec_list = await self.embedder.embed([query])
        q_vec = np.array(q_vec_list, dtype=np.float32)
        faiss.normalize_L2(q_vec)

        k = min(top_k, len(self._episodic_texts))
        scores, indices = self._episodic_index.search(q_vec, k)

        results: list[str] = []
        for score, idx in zip(scores[0], indices[0]):
            if idx >= 0 and score > 0.5:
                results.append(self._episodic_texts[idx])

        return "\n\n---\n\n".join(results) if results else "No past analyses found."

    # ── Tier 3: Schema Memory (Vault) ───────────────────────────

    async def get_schema_context(self, query: str, top_k: int = 5) -> str:
        """Pass-through to the FAISS schema store."""
        return await self.schema_store.search(query=query, top_k=top_k)
