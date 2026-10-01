"""
LangGraph agent state schema.

Every node in the ReAct graph reads from and writes to this TypedDict.
LangGraph manages state immutably between nodes — each node returns
only the keys it wants to update.
"""

from __future__ import annotations

from typing import Annotated, TypedDict

from langgraph.graph.message import add_messages


class AgentState(TypedDict):
    """Shared state flowing through the ReAct graph."""

    # ── LangChain message history (auto-appended via add_messages) ──
    messages: Annotated[list, add_messages]

    # ── Dataset context ──
    dataset_id: str
    dataset_path: str
    
    # ── Session context ──
    thread_id: str

    # ── User query ──
    query: str

    # ── Retrieved schema metadata from FAISS ──
    schema_context: str

    # ── LLM-generated Python code ──
    generated_code: str

    # ── Sandbox execution output ──
    execution_result: str
    execution_error: str

    # ── Multi-Agent Routing & QA ──
    next_agent: str           # e.g., 'analyst', 'visualizer', 'profiler', 'responder'
    qa_feedback: str          # Critique from the QA Reviewer
    visualize_required: bool  # Flag if the supervisor wants a chart

    # ── Loop control ──
    iteration: int
    max_iterations: int

    # ── Current node label ──
    status: str

    # ── Accumulated thought trace (streamed to frontend) ──
    thought_log: list[dict]

    # ── Token usage accumulator ──
    token_usage: dict[str, int]
