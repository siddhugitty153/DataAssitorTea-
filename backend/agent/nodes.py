"""
Multi-Agent Graph Nodes.
Implements the Supervisor, Analyst, QA Reviewer, Visualizer, and Responder.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone

from backend.core import create_llm, create_sandbox
from backend.memory.manager import MemoryManager
from backend.agent.prompts import (
    SUPERVISOR_PROMPT,
    ANALYST_PROMPT,
    QA_REVIEWER_PROMPT,
    VISUALIZER_PROMPT,
    RESPONDER_PROMPT,
    SYSTEM_PROMPT,
)
from backend.agent.state import AgentState

_llm = create_llm()
_sandbox = create_sandbox()


def _log(state: AgentState, step_type: str, content: str) -> list[dict]:
    """Append a thought entry and return the updated log."""
    log = list(state.get("thought_log") or [])
    log.append(
        {
            "step": f"Step {len(log) + 1}",
            "type": step_type,
            "content": content,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    )
    return log


def _extract_code(text: str) -> str:
    """Pull the first Python code-fence out of an LLM response."""
    match = re.search(r"```python\s*\n(.*?)```", text, re.DOTALL)
    if match:
        return match.group(1).strip()
    match = re.search(r"```\s*\n(.*?)```", text, re.DOTALL)
    if match:
        return match.group(1).strip()
    return text.strip()


# ────────────────────────────────────────────────────────────────
# SUPERVISOR NODE
# ────────────────────────────────────────────────────────────────

async def supervisor(state: AgentState) -> dict:
    """Routes the query to the appropriate specialized agent."""
    query = state["query"]
    
    prompt = SUPERVISOR_PROMPT.format(query=query)
    
    response = await _llm.generate([
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": prompt}
    ])
    
    try:
        # Expecting JSON like {"next_agent": "analyst", "visualize_required": false}
        # Clean potential markdown wrapping
        clean_json = response.content.strip().strip("`").removeprefix("json").strip()
        decision = json.loads(clean_json)
        next_agent = decision.get("next_agent", "analyst")
        visualize_required = decision.get("visualize_required", False)
    except Exception:
        # Fallback to analyst on parse failure
        next_agent = "analyst"
        visualize_required = False

    thought = f"👔 **Supervisor:** Routing query to `{next_agent}`."
    log = _log(state, "supervisor", thought)
    
    return {
        "next_agent": next_agent,
        "visualize_required": visualize_required,
        "status": "routing",
        "thought_log": log,
    }


# ────────────────────────────────────────────────────────────────
# ANALYST NODE
# ────────────────────────────────────────────────────────────────

async def analyst(state: AgentState) -> dict:
    """Generates analytical pandas code based on the query."""
    manager = MemoryManager(state["thread_id"], state["dataset_id"])
    schema_context = await manager.get_schema_context(state["query"], top_k=10)
    
    wm_messages = manager.get_working_memory(limit=4)
    working_memory = "\n".join([f"{m['role'].title()}: {m['content']}" for m in wm_messages]) or "None"
    episodic_memory = await manager.recall_past_analyses(state["query"], top_k=2)

    prompt = ANALYST_PROMPT.format(
        query=state["query"],
        schema_context=schema_context,
        working_memory=working_memory,
        episodic_memory=episodic_memory,
        qa_feedback=state.get("qa_feedback", "None"),
    )

    response = await _llm.generate([
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": prompt}
    ])
    
    code = _extract_code(response.content)
    n_lines = len(code.splitlines())
    
    thought = f"🧮 **Analyst:** Wrote {n_lines} lines of data processing code."
    if state.get("qa_feedback"):
        thought = f"🧮 **Analyst:** Rewriting code based on QA Feedback."

    log = _log(state, "analyst", thought)
    
    return {
        "generated_code": code,
        "status": "coding",
        "thought_log": log,
        "iteration": state.get("iteration", 0) + 1,
    }


# ────────────────────────────────────────────────────────────────
# OBSERVE NODE (Sandbox Executor)
# ────────────────────────────────────────────────────────────────

async def observe(state: AgentState) -> dict:
    """Executes code in the sandbox."""
    code = state["generated_code"]
    result = await _sandbox.execute(code, dataset_path=state["dataset_path"])

    if not result.success:
        thought = f"❌ **Sandbox:** Execution failed.\n```\n{result.stderr[:400]}\n```"
        return {
            "execution_result": "",
            "execution_error": result.stderr,
            "status": "error",
            "thought_log": _log(state, "observe", thought),
        }

    thought = f"✅ **Sandbox:** Execution succeeded.\n```\n{result.stdout[:400]}\n```"
    return {
        "execution_result": result.stdout,
        "execution_error": "",
        "status": "executed",
        "thought_log": _log(state, "observe", thought),
    }


# ────────────────────────────────────────────────────────────────
# QA REVIEWER NODE
# ────────────────────────────────────────────────────────────────

async def qa_reviewer(state: AgentState) -> dict:
    """Reviews the Analyst's code and sandbox output."""
    if state.get("execution_error"):
        feedback = f"Your code crashed in the sandbox. Fix this error:\n{state['execution_error']}"
        thought = "🧐 **QA Reviewer:** Code crashed. Sending back to Analyst."
        return {
            "qa_feedback": feedback,
            "next_agent": "analyst",
            "thought_log": _log(state, "qa_reviewer", thought),
        }

    prompt = QA_REVIEWER_PROMPT.format(
        query=state["query"],
        code=state["generated_code"],
        result=state["execution_result"],
    )

    response = await _llm.generate([
        {"role": "system", "content": "You are a strict QA engineer."},
        {"role": "user", "content": prompt}
    ])
    
    feedback = response.content.strip()
    if feedback == "PASS" or "PASS" in feedback:
        thought = "🧐 **QA Reviewer:** Output looks solid. Approved! ✅"
        next_agent = "visualizer" if state.get("visualize_required") else "responder"
        return {
            "qa_feedback": "",
            "next_agent": next_agent,
            "thought_log": _log(state, "qa_reviewer", thought),
        }
    
    thought = f"🧐 **QA Reviewer:** Logic error detected. Rejecting code."
    return {
        "qa_feedback": feedback,
        "next_agent": "analyst",
        "thought_log": _log(state, "qa_reviewer", thought),
    }


# ────────────────────────────────────────────────────────────────
# VISUALIZER NODE
# ────────────────────────────────────────────────────────────────

async def visualizer(state: AgentState) -> dict:
    """Generates plotting code based on the previous output."""
    manager = MemoryManager(state["thread_id"], state["dataset_id"])
    schema_context = await manager.get_schema_context(state["query"], top_k=10)

    prompt = VISUALIZER_PROMPT.format(
        query=state["query"],
        execution_result=state["execution_result"],
        schema_context=schema_context,
    )

    response = await _llm.generate([
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": prompt}
    ])
    
    code = _extract_code(response.content)
    thought = f"🎨 **Visualizer:** Generated chart plotting code."
    
    # We execute the visualizer's code instantly here for the MVP
    # rather than passing it back through 'observe' to avoid infinite loops.
    result = await _sandbox.execute(code, dataset_path=state["dataset_path"])
    
    if not result.success:
        thought_err = f"❌ **Visualizer Sandbox:** Failed to generate plot.\n{result.stderr[:200]}"
        return {
            "execution_error": result.stderr,
            "next_agent": "responder",
            "thought_log": _log(state, "visualizer", thought + "\n" + thought_err),
        }

    return {
        "execution_result": state["execution_result"] + "\n\nPlot Summary:\n" + result.stdout,
        "next_agent": "responder",
        "thought_log": _log(state, "visualizer", thought),
    }


# ────────────────────────────────────────────────────────────────
# RESPONDER NODE
# ────────────────────────────────────────────────────────────────

async def responder(state: AgentState) -> dict:
    """Summarises the final data output into a human-readable response."""
    if not state.get("execution_result"):
        final_answer = "The analysis failed to produce a valid result."
    else:
        prompt = RESPONDER_PROMPT.format(
            query=state["query"],
            execution_result=state["execution_result"],
        )
        response = await _llm.generate([{"role": "user", "content": prompt}])
        final_answer = response.content

        # Save to Memory Palace on success
        manager = MemoryManager(state["thread_id"], state["dataset_id"])
        await manager.save_analysis(
            query=state["query"],
            code=state.get("generated_code", ""),
            result=state["execution_result"],
        )
        manager.add_message("assistant", final_answer)

    thought = "🗣️ **Responder:** Formatted final response."
    return {
        "execution_result": final_answer,
        "status": "completed",
        "thought_log": _log(state, "responder", thought),
    }
