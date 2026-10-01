"""
Pydantic request / response schemas for the REST API.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


# ── Enums ──

class AnalysisStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    REASONING = "reasoning"
    ACTING = "acting"
    OBSERVING = "observing"
    COMPLETED = "completed"
    FAILED = "failed"


# ── Dataset ──

class UploadResponse(BaseModel):
    dataset_id: str
    filename: str
    columns: list[str]
    row_count: int
    message: str


# ── Analysis ──

class AnalyzeRequest(BaseModel):
    dataset_id: str = Field(..., description="ID returned by /upload")
    query: str = Field(..., min_length=3, description="Natural-language analysis query")
    thread_id: str | None = Field(default=None, description="Optional client session or thread ID")


class AnalyzeResponse(BaseModel):
    thread_id: str
    status: AnalysisStatus
    message: str


# ── Thread / Thought ──

class ThoughtStep(BaseModel):
    step: str
    type: str  # reason | act | observe | respond
    content: str
    timestamp: str


class ThreadStatus(BaseModel):
    thread_id: str
    dataset_id: str
    query: str
    status: str
    thoughts: list[ThoughtStep] = []
    result: str | None = None
    generated_code: str | None = None
    error: str | None = None
