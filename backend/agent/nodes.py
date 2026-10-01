"""
Multi-Agent Graph Nodes with Token Optimization and Hierarchical Memory Palace.
Implements Supervisor, Analyst, Sandbox Observer, QA Reviewer, Visualizer, and Responder.
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


def _add_tokens(state: AgentState, usage: dict[str, int]) -> dict[str, int]:
    """Accumulate token counts across all agent steps."""
    current = dict(state.get("token_usage") or {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0})
    if usage:
        current["prompt_tokens"] += usage.get("prompt_tokens", 0)
        current["completion_tokens"] += usage.get("completion_tokens", 0)
        current["total_tokens"] += usage.get("total_tokens", 0)
    return current


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
# SUPERVISOR NODE (Token-Optimized with Fast Routing)
# ────────────────────────────────────────────────────────────────

async def supervisor(state: AgentState) -> dict:
    """Routes the query to the appropriate specialized agent."""
    query = state["query"].lower().strip()
    tokens = state.get("token_usage") or {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}

    # Fast deterministic routing to save tokens & latency
    visual_keywords = ["plot", "chart", "graph", "histogram", "scatter", "bar chart", "visualize", "draw"]
    greeting_keywords = ["hello", "hi", "hey", "who are you", "what can you do"]

    if any(k in query for k in visual_keywords):
        next_agent = "analyst"
        visualize_required = True
        thought = "👔 **Supervisor:** Visual request detected → Routing to Analyst & Visualizer."
    elif query in greeting_keywords or len(query.split()) <= 2 and any(k in query for k in greeting_keywords):
        next_agent = "responder"
        visualize_required = False
        thought = "👔 **Supervisor:** General inquiry → Routing directly to Responder."
    else:
        # Standard analytical query
        next_agent = "analyst"
        visualize_required = False
        thought = f"👔 **Supervisor:** Analytical query → Routing to Analyst."

    log = _log(state, "supervisor", thought)

    return {
        "next_agent": next_agent,
        "visualize_required": visualize_required,
        "status": "routing",
        "thought_log": log,
        "token_usage": tokens,
    }


# ────────────────────────────────────────────────────────────────
# ANALYST NODE (Hierarchical Memory Palace Retrieval)
# ────────────────────────────────────────────────────────────────

async def analyst(state: AgentState) -> dict:
    """Generates analytical pandas code based on the query and Memory Palace."""
    manager = MemoryManager(state["thread_id"], state["dataset_id"])
    
    # 1-Pass retrieval: embeds query once and retrieves Schema + Episodic + Working memory
    mem_bundle = await manager.get_memory_bundle(state["query"])

    prompt = ANALYST_PROMPT.format(
        query=state["query"],
        schema_context=mem_bundle["schema_context"],
        working_memory=mem_bundle["working_memory"],
        episodic_memory=mem_bundle["episodic_memory"],
        qa_feedback=state.get("qa_feedback", "None"),
    )

    response = await _llm.generate([
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": prompt}
    ], max_tokens=1500)

    code = _extract_code(response.content)
    n_lines = len(code.splitlines())

    tokens = _add_tokens(state, response.usage)

    thought = f"🧮 **Analyst:** Wrote {n_lines} lines of code using Memory Palace context."
    if state.get("qa_feedback"):
        thought = f"🧮 **Analyst:** Refined code based on QA Feedback."

    log = _log(state, "analyst", thought)

    return {
        "generated_code": code,
        "status": "coding",
        "thought_log": log,
        "iteration": state.get("iteration", 0) + 1,
        "token_usage": tokens,
    }


# ────────────────────────────────────────────────────────────────
# OBSERVE NODE (Sandbox Executor)
# ────────────────────────────────────────────────────────────────

async def observe(state: AgentState) -> dict:
    """Executes code in the sandbox."""
    code = state["generated_code"]
    result = await _sandbox.execute(code, dataset_path=state["dataset_path"])

    if not result.success:
        thought = f"❌ **Sandbox:** Execution failed.\n```\n{result.stderr[:300]}\n```"
        return {
            "execution_result": "",
            "execution_error": result.stderr,
            "status": "error",
            "thought_log": _log(state, "observe", thought),
        }

    thought = f"✅ **Sandbox:** Execution succeeded ({result.execution_time:.2f}s).\n```\n{result.stdout[:300]}\n```"
    return {
        "execution_result": result.stdout,
        "execution_error": "",
        "status": "executed",
        "thought_log": _log(state, "observe", thought),
    }


# ────────────────────────────────────────────────────────────────
# QA REVIEWER NODE (Fast-Path Auto Verification)
# ────────────────────────────────────────────────────────────────

async def qa_reviewer(state: AgentState) -> dict:
    """Reviews the Analyst's code and sandbox output."""
    if state.get("execution_error"):
        feedback = f"Your code crashed in the sandbox. Fix this error:\n{state['execution_error']}"
        thought = "🧐 **QA Reviewer:** Code crashed. Sending back to Analyst with error trace."
        return {
            "qa_feedback": feedback,
            "next_agent": "analyst",
            "thought_log": _log(state, "qa_reviewer", thought),
        }

    # Fast-path verification if sandbox execution succeeded cleanly with output
    res_str = state.get("execution_result", "").strip()
    if res_str and not any(err in res_str.lower() for err in ["exception", "traceback", "error:", "none", "empty dataframe"]):
        thought = "🧐 **QA Reviewer:** Sandbox output verified successfully. Approved! ✅"
        next_agent = "visualizer" if state.get("visualize_required") else "responder"
        return {
            "qa_feedback": "",
            "next_agent": next_agent,
            "thought_log": _log(state, "qa_reviewer", thought),
        }

    # Full LLM check only if ambiguous or empty output
    prompt = QA_REVIEWER_PROMPT.format(
        query=state["query"],
        code=state["generated_code"],
        result=state["execution_result"],
    )

    response = await _llm.generate([
        {"role": "system", "content": "You are a strict QA engineer."},
        {"role": "user", "content": prompt}
    ], max_tokens=300)

    tokens = _add_tokens(state, response.usage)
    feedback = response.content.strip()

    if "PASS" in feedback:
        thought = "🧐 **QA Reviewer:** Output looks solid. Approved! ✅"
        next_agent = "visualizer" if state.get("visualize_required") else "responder"
        return {
            "qa_feedback": "",
            "next_agent": next_agent,
            "thought_log": _log(state, "qa_reviewer", thought),
            "token_usage": tokens,
        }

    thought = f"🧐 **QA Reviewer:** Logic error detected. Rejecting code."
    return {
        "qa_feedback": feedback,
        "next_agent": "analyst",
        "thought_log": _log(state, "qa_reviewer", thought),
        "token_usage": tokens,
    }


# ────────────────────────────────────────────────────────────────
# VISUALIZER NODE
# ────────────────────────────────────────────────────────────────

async def visualizer(state: AgentState) -> dict:
    """Generates plotting code based on the previous output."""
    manager = MemoryManager(state["thread_id"], state["dataset_id"])
    schema_context = await manager.get_schema_context(state["query"], top_k=5)

    prompt = VISUALIZER_PROMPT.format(
        query=state["query"],
        execution_result=state["execution_result"],
        schema_context=schema_context,
    )

    response = await _llm.generate([
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": prompt}
    ], max_tokens=800)

    tokens = _add_tokens(state, response.usage)
    code = _extract_code(response.content)
    thought = f"🎨 **Visualizer:** Generated chart plotting code."

    result = await _sandbox.execute(code, dataset_path=state["dataset_path"])

    if not result.success:
        thought_err = f"❌ **Visualizer Sandbox:** Failed to generate plot.\n{result.stderr[:200]}"
        return {
            "execution_error": result.stderr,
            "next_agent": "responder",
            "thought_log": _log(state, "visualizer", thought + "\n" + thought_err),
            "token_usage": tokens,
        }

    return {
        "execution_result": state["execution_result"] + "\n\nPlot Summary:\n" + result.stdout,
        "next_agent": "responder",
        "thought_log": _log(state, "visualizer", thought),
        "token_usage": tokens,
    }


# ────────────────────────────────────────────────────────────────
# RESPONDER NODE
# ────────────────────────────────────────────────────────────────

async def responder(state: AgentState) -> dict:
    """Summarises the final data output into a concise response."""
    tokens = state.get("token_usage") or {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}

    if not state.get("execution_result"):
        final_answer = "The analysis could not be completed with valid data."
    else:
        prompt = RESPONDER_PROMPT.format(
            query=state["query"],
            execution_result=state["execution_result"],
        )
        response = await _llm.generate([{"role": "user", "content": prompt}], max_tokens=600)
        final_answer = response.content
        tokens = _add_tokens(state, response.usage)

        # Save to Memory Palace on success
        manager = MemoryManager(state["thread_id"], state["dataset_id"])
        await manager.save_analysis(
            query=state["query"],
            code=state.get("generated_code", ""),
            result=state["execution_result"],
        )
        manager.add_message("assistant", final_answer)

    thought = f"🗣️ **Responder:** Formatted response. (Tokens used: {tokens.get('total_tokens', 0):,})"
    return {
        "execution_result": final_answer,
        "status": "completed",
        "thought_log": _log(state, "responder", thought),
        "token_usage": tokens,
    }
