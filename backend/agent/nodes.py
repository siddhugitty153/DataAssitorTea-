"""
Multi-Agent Graph Nodes with Token Optimization and Hierarchical Memory Palace.
Implements Supervisor, Analyst, Sandbox Observer, QA Reviewer, Visualizer, and Responder.

Reforms applied (audit 2026-10-13):
  • B1: QA auto-pass hardened with expanded heuristics + min-length check
  • B2: token_usage preserved on every QA code-path
  • B4: Supervisor uses LLM for ambiguous queries (fast-path kept for obvious routing)
  • B5: Removed deprecated asyncio.get_event_loop() usage
  • B6: Responder writes to 'final_answer' key instead of overwriting 'execution_result'
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

# Lazy singletons — created on first use, not at import time
_llm: object | None = None
_sandbox: object | None = None


def _get_llm():
    """Lazy-create the LLM provider on first use (not at import time)."""
    global _llm
    if _llm is None:
        _llm = create_llm()
    return _llm


def _get_sandbox():
    """Lazy-create the sandbox provider on first use (not at import time)."""
    global _sandbox
    if _sandbox is None:
        _sandbox = create_sandbox()
    return _sandbox


def _get_tokens(state: AgentState) -> dict[str, int]:
    """Safely get the current token usage from state, never None."""
    return dict(
        state.get("token_usage")
        or {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
    )


def _add_tokens(state: AgentState, usage: dict[str, int]) -> dict[str, int]:
    """Accumulate token counts across all agent steps."""
    current = _get_tokens(state)
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
# SUPERVISOR NODE — Hybrid: Fast-Path + LLM for Ambiguous Queries
# ────────────────────────────────────────────────────────────────

async def supervisor(state: AgentState) -> dict:
    """
    Routes the query to the appropriate specialized agent.

    Strategy:
      1. Fast-path: deterministic keyword matching for obvious cases
         (greetings, explicit chart requests) — saves an LLM call.
      2. Fallback: LLM-based classification for ambiguous or complex
         queries where keywords alone aren't reliable.
    """
    query = state["query"].strip()
    query_lower = query.lower()
    tokens = _get_tokens(state)

    # ── Fast-path: greetings (≤ 3 words, obvious salutations) ──
    greeting_keywords = ["hello", "hi", "hey", "who are you", "what can you do", "thanks", "thank you"]
    words = query_lower.split()
    if len(words) <= 3 and any(k in query_lower for k in greeting_keywords):
        thought = "👔 **Supervisor:** General inquiry → Routing directly to Responder. *(fast-path)*"
        return {
            "next_agent": "responder",
            "visualize_required": False,
            "status": "routing",
            "thought_log": _log(state, "supervisor", thought),
            "token_usage": tokens,
        }

    # ── Fast-path: explicit visualization keywords ──
    visual_keywords = [
        "plot", "chart", "graph", "histogram", "scatter", "bar chart",
        "visualize", "draw", "heatmap", "pie chart", "line chart",
        "box plot", "boxplot",
    ]
    if any(k in query_lower for k in visual_keywords):
        thought = "👔 **Supervisor:** Visual request detected → Routing to Analyst & Visualizer. *(fast-path)*"
        return {
            "next_agent": "analyst",
            "visualize_required": True,
            "status": "routing",
            "thought_log": _log(state, "supervisor", thought),
            "token_usage": tokens,
        }

    # ── LLM-based classification for ambiguous queries ──
    llm = _get_llm()
    prompt = SUPERVISOR_PROMPT.format(query=query)

    try:
        response = await llm.generate(
            [{"role": "user", "content": prompt}],
            max_tokens=80,
            temperature=0.0,
        )
        tokens = _add_tokens(state, response.usage)

        # Parse the JSON response
        raw = response.content.strip()
        # Strip markdown code fences if present
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)

        decision = json.loads(raw)
        next_agent = decision.get("next_agent", "analyst")
        visualize_required = decision.get("visualize_required", False)

        # Validate the decision
        if next_agent not in ("analyst", "visualizer", "responder"):
            next_agent = "analyst"

        # If LLM says visualizer directly, route through analyst first
        if next_agent == "visualizer":
            next_agent = "analyst"
            visualize_required = True

        thought = f"👔 **Supervisor:** LLM classified query → Routing to `{next_agent}` (visualize={visualize_required}). *(LLM-routed)*"

    except Exception:
        # Fallback: if LLM call fails, route to analyst (safe default)
        next_agent = "analyst"
        visualize_required = False
        thought = "👔 **Supervisor:** LLM routing failed → Defaulting to Analyst. *(fallback)*"

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
    llm = _get_llm()
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

    response = await llm.generate([
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": prompt}
    ], max_tokens=2000)

    code = _extract_code(response.content)
    n_lines = len(code.splitlines())

    tokens = _add_tokens(state, response.usage)

    thought = f"🧮 **Analyst:** Wrote {n_lines} lines of code using Memory Palace context."
    if state.get("qa_feedback"):
        thought = f"🧮 **Analyst:** Refined code based on QA Feedback (iteration {state.get('iteration', 0) + 1})."

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
    sandbox = _get_sandbox()
    code = state["generated_code"]
    result = await sandbox.execute(code, dataset_path=state["dataset_path"])

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
# QA REVIEWER NODE (Hardened Verification)
# ────────────────────────────────────────────────────────────────

# Suspicious patterns in stdout that should trigger an LLM review
_QA_SUSPICIOUS_PATTERNS = [
    "exception", "traceback", "error:", "keyerror", "valueerror",
    "indexerror", "typeerror", "attributeerror", "nameerror",
    "zerodivisionerror", "filenotfounderror",
    "empty dataframe", "0 rows", "no data", "nan",
    "warning:", "deprecationwarning", "futurewarning",
    "none", "null",
]


async def qa_reviewer(state: AgentState) -> dict:
    """
    Reviews the Analyst's code and sandbox output.

    Hardened verification strategy:
      1. Crash fast-reject: if sandbox stderr is non-empty, reject immediately.
      2. Suspicious-output check: if stdout contains known error/warning patterns,
         fall through to LLM review.
      3. Minimum-length check: if stdout is too short (< 20 chars), trigger LLM review.
      4. Auto-pass: only if stdout is clean, substantial, and contains no suspicious patterns.
      5. LLM review: for all ambiguous cases.
    """
    tokens = _get_tokens(state)

    # ── 1. Crash fast-reject ──
    if state.get("execution_error"):
        feedback = f"Your code crashed in the sandbox. Fix this error:\n{state['execution_error']}"
        thought = "🧐 **QA Reviewer:** Code crashed. Sending back to Analyst with error trace."
        return {
            "qa_feedback": feedback,
            "next_agent": "analyst",
            "thought_log": _log(state, "qa_reviewer", thought),
            "token_usage": tokens,  # B2: preserve token count
        }

    # ── 2. Evaluate stdout quality ──
    res_str = state.get("execution_result", "").strip()
    is_suspicious = any(pat in res_str.lower() for pat in _QA_SUSPICIOUS_PATTERNS)
    is_too_short = len(res_str) < 20
    is_clean = res_str and not is_suspicious and not is_too_short

    # ── 3. Auto-pass: only for clean, substantial output ──
    if is_clean:
        thought = "🧐 **QA Reviewer:** Sandbox output verified successfully. Approved! ✅ *(auto-pass)*"
        next_agent = "visualizer" if state.get("visualize_required") else "responder"
        return {
            "qa_feedback": "",
            "next_agent": next_agent,
            "thought_log": _log(state, "qa_reviewer", thought),
            "token_usage": tokens,  # B2: preserve token count
        }

    # ── 4. LLM review for ambiguous or suspicious output ──
    llm = _get_llm()
    reason = "suspicious patterns in output" if is_suspicious else "output too short or empty"
    prompt = QA_REVIEWER_PROMPT.format(
        query=state["query"],
        code=state["generated_code"],
        result=state["execution_result"],
    )

    response = await llm.generate([
        {"role": "system", "content": "You are a strict QA engineer reviewing data analysis code."},
        {"role": "user", "content": prompt}
    ], max_tokens=400)

    tokens = _add_tokens(state, response.usage)
    feedback = response.content.strip()

    if "PASS" in feedback.upper():
        thought = f"🧐 **QA Reviewer:** LLM review triggered ({reason}). Verdict: Approved ✅"
        next_agent = "visualizer" if state.get("visualize_required") else "responder"
        return {
            "qa_feedback": "",
            "next_agent": next_agent,
            "thought_log": _log(state, "qa_reviewer", thought),
            "token_usage": tokens,
        }

    thought = f"🧐 **QA Reviewer:** LLM review triggered ({reason}). Verdict: Rejected ❌"
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
    llm = _get_llm()
    sandbox = _get_sandbox()
    manager = MemoryManager(state["thread_id"], state["dataset_id"])
    schema_context = await manager.get_schema_context(state["query"], top_k=5)

    prompt = VISUALIZER_PROMPT.format(
        query=state["query"],
        execution_result=state["execution_result"],
        schema_context=schema_context,
    )

    response = await llm.generate([
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": prompt}
    ], max_tokens=800)

    tokens = _add_tokens(state, response.usage)
    code = _extract_code(response.content)
    thought = f"🎨 **Visualizer:** Generated chart plotting code."

    result = await sandbox.execute(code, dataset_path=state["dataset_path"])

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
    """
    Summarises the final data output into a concise response.

    B6 fix: writes the final answer to 'final_answer' instead of
    overwriting 'execution_result', so the raw sandbox output is preserved.
    """
    tokens = _get_tokens(state)

    if not state.get("execution_result"):
        final_answer = "The analysis could not be completed with valid data. Please try rephrasing your query or check if the dataset was uploaded correctly."
    else:
        llm = _get_llm()
        prompt = RESPONDER_PROMPT.format(
            query=state["query"],
            execution_result=state["execution_result"],
        )
        response = await llm.generate([{"role": "user", "content": prompt}], max_tokens=800)
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
        "final_answer": final_answer,
        "status": "completed",
        "thought_log": _log(state, "responder", thought),
        "token_usage": tokens,
    }
