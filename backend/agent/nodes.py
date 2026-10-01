"""
ReAct graph nodes — each function is a node in the LangGraph state machine.

Flow:  reason  →  act  →  observe  ─┬─→  respond   (success / max retries)
                                     └──→  reason   (retry on error)
"""

from __future__ import annotations

import re
from datetime import datetime, timezone

from backend.core import create_llm, create_sandbox
from backend.memory.faiss_store import FAISSStore
from backend.agent.prompts import (
    ERROR_CORRECTION_PROMPT,
    REASON_PROMPT,
    SUMMARY_PROMPT,
    SYSTEM_PROMPT,
)
from backend.agent.state import AgentState

# ── Shared singletons (created once via the provider-agnostic factories) ──
_llm = create_llm()           # reads LLM_PROVIDER from .env
_sandbox = create_sandbox()   # reads SANDBOX_PROVIDER from .env


# ────────────────────────────────────────────────────────────────
# Helpers
# ────────────────────────────────────────────────────────────────

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
    # Try ```python ... ``` first
    match = re.search(r"```python\s*\n(.*?)```", text, re.DOTALL)
    if match:
        return match.group(1).strip()
    # Fallback: any ``` block
    match = re.search(r"```\s*\n(.*?)```", text, re.DOTALL)
    if match:
        return match.group(1).strip()
    # No fences — treat the whole response as code
    return text.strip()


# ────────────────────────────────────────────────────────────────
# Node: REASON  (search memory → build prompt)
# ────────────────────────────────────────────────────────────────

async def reason(state: AgentState) -> dict:
    """Retrieve relevant schema context from FAISS and build the LLM prompt."""
    query = state["query"]
    dataset_id = state["dataset_id"]

    # Retrieve relevant column metadata
    store = FAISSStore(dataset_id)
    schema_context = store.search(query, top_k=10)

    error = state.get("execution_error", "")
    iteration = state.get("iteration", 0)

    if error and iteration > 0:
        prompt_text = ERROR_CORRECTION_PROMPT.format(
            code=state.get("generated_code", ""),
            error=error,
            schema_context=schema_context,
        )
        thought = (
            f"🔄 **Retry #{iteration}** — analysing error and rewriting code.\n"
            f"Error snippet: `{error[:200]}…`"
        )
    else:
        prompt_text = REASON_PROMPT.format(
            query=query,
            schema_context=schema_context,
        )
        n_chunks = len(schema_context.strip().split("\n\n"))
        thought = (
            f"🔍 Analysing query: *\"{query}\"*\n"
            f"Retrieved **{n_chunks}** schema chunks from FAISS."
        )

    log = _log(state, "reason", thought)

    return {
        "schema_context": schema_context,
        "status": "reasoning",
        "thought_log": log,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt_text},
        ],
    }


# ────────────────────────────────────────────────────────────────
# Node: ACT  (call LLM → generate code)
# ────────────────────────────────────────────────────────────────

async def act(state: AgentState) -> dict:
    """Invoke the LLM to produce Python / Pandas code."""
    llm_response = await _llm.generate(state["messages"])
    code = _extract_code(llm_response.content)

    n_lines = len(code.splitlines())
    thought = f"💻 Generated **{n_lines}-line** Python script."
    log = _log(state, "act", thought)

    return {
        "generated_code": code,
        "status": "acting",
        "thought_log": log,
        "messages": [{"role": "assistant", "content": llm_response.content}],
    }


# ────────────────────────────────────────────────────────────────
# Node: OBSERVE  (execute in sandbox → capture output)
# ────────────────────────────────────────────────────────────────

async def observe(state: AgentState) -> dict:
    """Run the generated code in the configured sandbox."""
    code = state["generated_code"]
    dataset_path = state["dataset_path"]
    iteration = state.get("iteration", 0) + 1

    result = await _sandbox.execute(code, dataset_path=dataset_path)

    if not result.success:
        thought = (
            f"❌ Execution **failed** (attempt {iteration}/{state['max_iterations']})\n"
            f"```\n{result.stderr[:400]}\n```"
        )
        log = _log(state, "observe", thought)
        return {
            "execution_result": "",
            "execution_error": result.stderr,
            "iteration": iteration,
            "status": "error",
            "thought_log": log,
        }

    thought = (
        f"✅ Execution **succeeded** (attempt {iteration})\n"
        f"Output preview:\n```\n{result.stdout[:400]}\n```"
    )
    log = _log(state, "observe", thought)
    return {
        "execution_result": result.stdout,
        "execution_error": "",
        "iteration": iteration,
        "status": "completed",
        "thought_log": log,
    }


# ────────────────────────────────────────────────────────────────
# Node: RESPOND  (format final answer)
# ────────────────────────────────────────────────────────────────

async def respond(state: AgentState) -> dict:
    """Summarise raw execution output into a stakeholder-friendly answer."""
    if state.get("execution_result"):
        summary_prompt = SUMMARY_PROMPT.format(
            query=state["query"],
            result=state["execution_result"],
        )
        llm_response = await _llm.generate([
            {"role": "user", "content": summary_prompt},
        ])
        thought = "📊 Analysis complete — formatting results for the user."
        log = _log(state, "respond", thought)
        return {
            "execution_result": llm_response.content,
            "status": "completed",
            "thought_log": log,
        }

    # All retries exhausted
    thought = f"⚠️ Analysis **failed** after {state['iteration']} attempt(s)."
    log = _log(state, "respond", thought)
    return {
        "execution_result": (
            f"Analysis failed after {state['iteration']} attempts.\n"
            f"Last error: {state.get('execution_error', 'Unknown')}"
        ),
        "status": "failed",
        "thought_log": log,
    }
