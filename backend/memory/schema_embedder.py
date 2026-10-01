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

    def extract_metadata(self, csv_path: str, total_rows: int | None = None) -> list[dict]:
        """
        Read the first 1 000 rows to compute per-column statistics,
        then count total rows separately (cheap streaming count).
        """
        # Try multiple encodings in case user uploaded Windows/Excel CSV
        df = None
        for enc in ["utf-8", "utf-8-sig", "latin1", "cp1252"]:
            try:
                df = pd.read_csv(csv_path, nrows=1_000, encoding=enc)
                break
            except Exception:
                continue
        
        if df is None:
            df = pd.read_csv(csv_path, nrows=1_000, encoding_errors="replace")

        metadata: list[dict] = []

        for col in df.columns:
            null_count = int(df[col].isnull().sum())
            null_pct = round(float(df[col].isnull().mean() * 100), 2)
            unique_count = int(df[col].nunique())
            sample_values = [str(v) for v in df[col].dropna().head(5).tolist()]

            entry: dict = {
                "column_name": str(col),
                "dtype": str(df[col].dtype),
                "null_count": null_count,
                "null_pct": null_pct,
                "unique_count": unique_count,
                "sample_values": sample_values,
            }

            if pd.api.types.is_numeric_dtype(df[col]):
                min_v = df[col].min()
                max_v = df[col].max()
                mean_v = df[col].mean()
                std_v = df[col].std()
                med_v = df[col].median()
                
                entry.update(
                    {
                        "min": None if pd.isna(min_v) else float(min_v),
                        "max": None if pd.isna(max_v) else float(max_v),
                        "mean": None if pd.isna(mean_v) else round(float(mean_v), 4),
                        "std": None if pd.isna(std_v) else round(float(std_v), 4),
                        "median": None if pd.isna(med_v) else float(med_v),
                    }
                )
            elif pd.api.types.is_string_dtype(df[col]) or pd.api.types.is_object_dtype(df[col]):
                try:
                    entry["top_values"] = {
                        str(k): int(v)
                        for k, v in df[col].value_counts().head(5).items()
                    }
                except Exception:
                    pass

            metadata.append(entry)

        # Dataset-level summary document
        if total_rows is None:
            with open(csv_path, "rb") as f:
                total_rows = sum(buf.count(b"\n") for buf in iter(lambda: f.read(1024 * 1024), b""))
            total_rows = max(0, total_rows - 1)

        metadata.append(
            {
                "column_name": "__DATASET__",
                "total_rows": total_rows,
                "total_columns": len(df.columns),
                "column_list": [str(c) for c in df.columns],
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
        if m.get("mean") is not None:
            lines.append(
                f"  Stats: min={m.get('min')}, max={m.get('max')}, "
                f"mean={m.get('mean')}, std={m.get('std')}, median={m.get('median')}"
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
