"""
LangGraph state-machine definition for the ReAct agent.

                ┌──────────┐
                │  reason   │ ← entry point
                └────┬─────┘
                     │
                ┌────▼─────┐
                │   act     │ (LLM generates code)
                └────┬─────┘
                     │
                ┌────▼─────┐
                │  observe  │ (Docker sandbox runs code)
                └────┬─────┘
                     │
            ┌────────┼────────┐
            │ error  │        │ success
            │ retry  │        │
            ▼        │        ▼
         reason      │     respond  → END
         (if < max)  │
                     │ error, max retries
                     ▼
                  respond  → END
"""

from __future__ import annotations

from langgraph.graph import END, StateGraph

from backend.agent.nodes import act, observe, reason, respond
from backend.agent.state import AgentState


def _route_after_observe(state: AgentState) -> str:
    """Decide the next node after sandbox execution."""
    if state.get("execution_error") and state["iteration"] < state["max_iterations"]:
        return "retry"
    if state.get("execution_error"):
        return "fail"
    return "success"


def build_agent_graph():
    """Compile the LangGraph ReAct state-machine."""
    graph = StateGraph(AgentState)

    # ── Nodes ──
    graph.add_node("reason", reason)
    graph.add_node("act", act)
    graph.add_node("observe", observe)
    graph.add_node("respond", respond)

    # ── Edges ──
    graph.set_entry_point("reason")
    graph.add_edge("reason", "act")
    graph.add_edge("act", "observe")
    graph.add_conditional_edges(
        "observe",
        _route_after_observe,
        {
            "retry": "reason",   # Self-correction loop
            "success": "respond",
            "fail": "respond",
        },
    )
    graph.add_edge("respond", END)

    return graph.compile()


# Module-level compiled graph — import this from other modules
agent = build_agent_graph()
