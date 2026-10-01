"""
Schema Embedder — extracts rich column-level metadata from a CSV,
then produces OpenAI embeddings ready for FAISS indexing.

This is the "ingestion" side of the Hierarchical Memory (The Palace).
Instead of dumping the full data dictionary into every prompt, we embed
each column's metadata as a standalone document so the agent can
retrieve *only* the columns relevant to the current query.
"""

from __future__ import annotations

import pandas as pd

from backend.config import settings
from backend.core import create_embedder


class SchemaEmbedder:
    """Parse a CSV → extract per-column metadata → embed with OpenAI."""

    def __init__(self) -> None:
        self.embedder = create_embedder()

    # ────────────────────────────────────────────────────────────
    # Step 1: Extract metadata
    # ────────────────────────────────────────────────────────────

    def extract_metadata(self, csv_path: str) -> list[dict]:
        """
        Read the first 1 000 rows to compute per-column statistics,
        then count total rows separately (cheap streaming count).
        """
        df = pd.read_csv(csv_path, nrows=1_000)

        metadata: list[dict] = []

        for col in df.columns:
            entry: dict = {
                "column_name": col,
                "dtype": str(df[col].dtype),
                "null_count": int(df[col].isnull().sum()),
                "null_pct": round(float(df[col].isnull().mean() * 100), 2),
                "unique_count": int(df[col].nunique()),
                "sample_values": [
                    str(v) for v in df[col].dropna().head(5).tolist()
                ],
            }

            if pd.api.types.is_numeric_dtype(df[col]):
                entry.update(
                    {
                        "min": float(df[col].min()),
                        "max": float(df[col].max()),
                        "mean": round(float(df[col].mean()), 4),
                        "std": round(float(df[col].std()), 4),
                        "median": float(df[col].median()),
                    }
                )
            elif pd.api.types.is_string_dtype(df[col]) or pd.api.types.is_object_dtype(df[col]):
                entry["top_values"] = {
                    str(k): int(v)
                    for k, v in df[col].value_counts().head(5).items()
                }

            metadata.append(entry)

        # Dataset-level summary document
        total_rows = sum(1 for _ in open(csv_path, encoding="utf-8")) - 1
        metadata.append(
            {
                "column_name": "__DATASET__",
                "total_rows": total_rows,
                "total_columns": len(df.columns),
                "column_list": list(df.columns),
                "dtypes_summary": {
                    str(k): int(v)
                    for k, v in df.dtypes.value_counts().items()
                },
            }
        )

        return metadata

    # ────────────────────────────────────────────────────────────
    # Step 2: Create embeddings
    # ────────────────────────────────────────────────────────────

    async def create_embeddings(
        self, metadata: list[dict]
    ) -> tuple[list[str], list[list[float]]]:
        """
        Turn each metadata dict into a human-readable text chunk,
        then embed them via the configured provider in batches.
        """
        texts = [
            self._format_dataset_summary(m)
            if m["column_name"] == "__DATASET__"
            else self._format_column(m)
            for m in metadata
        ]

        # The embedder abstraction handles its own batching (e.g. 100 for Ollama),
        # so we can just pass the whole list of texts directly to it.
        embeddings = await self.embedder.embed(texts)

        return texts, embeddings

    # ────────────────────────────────────────────────────────────
    # Formatting helpers
    # ────────────────────────────────────────────────────────────

    @staticmethod
    def _format_column(m: dict) -> str:
        lines = [
            f"Column '{m['column_name']}' — dtype: {m['dtype']}",
            f"  Nulls: {m['null_count']} ({m['null_pct']}%)",
            f"  Unique values: {m['unique_count']}",
            f"  Sample values: {m['sample_values']}",
        ]
        if "mean" in m:
            lines.append(
                f"  Stats: min={m['min']}, max={m['max']}, "
                f"mean={m['mean']}, std={m['std']}, median={m['median']}"
            )
        if "top_values" in m:
            lines.append(f"  Top values: {m['top_values']}")
        return "\n".join(lines)

    @staticmethod
    def _format_dataset_summary(m: dict) -> str:
        return (
            f"Dataset overview: {m['total_rows']} rows, "
            f"{m['total_columns']} columns.\n"
            f"Columns: {', '.join(m['column_list'])}\n"
            f"Dtype distribution: {m['dtypes_summary']}"
        )
