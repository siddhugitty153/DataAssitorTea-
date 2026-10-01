"""
LangGraph state-machine definition for the Multi-Agent System.

                  ┌─────────────┐
                  │ supervisor  │ ← entry point
                  └──────┬──────┘
                         │
      ┌──────────────────┼──────────────────┐
      ▼                  ▼                  ▼
┌──────────┐       ┌──────────┐       ┌──────────┐
│ analyst  │       │visualizer│       │responder │ → END
└────┬─────┘       └─────┬────┘       └────▲─────┘
     │                   │                 │
     ▼                   ▼                 │
┌──────────┐             │                 │
│ observe  │             │                 │
└────┬─────┘             │                 │
     │                   │                 │
     ▼                   │                 │
┌──────────┐             │                 │
│qa_reviewer│            │                 │
└────┬─────┘             │                 │
     │                   │                 │
     └─(reject)──────────┘                 │
     │                                     │
     └─(accept)────────────────────────────┘
"""

from __future__ import annotations

from langgraph.graph import END, StateGraph

from backend.agent.nodes import (
    supervisor,
    analyst,
    observe,
    qa_reviewer,
    visualizer,
    responder
)
from backend.agent.state import AgentState


def _route_after_supervisor(state: AgentState) -> str:
    """Decide where the supervisor routes the query."""
    return state.get("next_agent", "responder")


def _route_after_qa(state: AgentState) -> str:
    """Decide if QA approved the code or sent it back."""
    # Force quit if we hit max iterations
    if state.get("iteration", 0) >= state.get("max_iterations", 3):
        return "responder"
    
    return state.get("next_agent", "responder")


def build_agent_graph():
    """Compile the LangGraph MAS state-machine."""
    graph = StateGraph(AgentState)

    # ── Nodes ──
    graph.add_node("supervisor", supervisor)
    graph.add_node("analyst", analyst)
    graph.add_node("observe", observe)
    graph.add_node("qa_reviewer", qa_reviewer)
    graph.add_node("visualizer", visualizer)
    graph.add_node("responder", responder)

    # ── Edges ──
    graph.set_entry_point("supervisor")
    
    graph.add_conditional_edges(
        "supervisor",
        _route_after_supervisor,
        {
            "analyst": "analyst",
            "visualizer": "visualizer",
            "responder": "responder",
        },
    )

    # Analyst writes code, sandbox observes it, QA reviews it
    graph.add_edge("analyst", "observe")
    graph.add_edge("observe", "qa_reviewer")
    
    graph.add_conditional_edges(
        "qa_reviewer",
        _route_after_qa,
        {
            "analyst": "analyst",         # Rejected, try again
            "visualizer": "visualizer",   # Approved, now draw the chart
            "responder": "responder",     # Approved, skip chart
        },
    )

    # Visualizer executes its own sandbox code internally, then hands to responder
    graph.add_edge("visualizer", "responder")
    
    # Final output
    graph.add_edge("responder", END)

    return graph.compile()


# Module-level compiled graph — import this from other modules
agent = build_agent_graph()
