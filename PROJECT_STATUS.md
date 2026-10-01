# 📋 Project Status — Agentic Data Assistant

> **Last Updated:** 2026-09-29 (Session 2)  
> **Current Branch:** `main`  
> **Latest Commit:** `58c7f57` — Switch to Gemini API via OpenAI compatibility layer

---

## 🎯 Current Stage: BACKEND SCAFFOLD DONE — UI & ARCHITECTURE NEED REWORK

The backend logic is scaffolded but **not yet tested end-to-end**. The project has a **single agent** (not multi-agent), a **basic FAISS memory** (not hierarchical/conversational), and a **basic Streamlit UI** that needs a full rebuild.

---

## 📜 Project Rules (AI Instructions)
1. **Always list pros and cons:** Whenever presented with a decision, the AI must always lay out the pros and cons of all available options *before* committing to a path.

---

## 🧠 Decision Log

### Decision 1: Open-Source LLM Provider Integration
**Context:** We wanted an open-source option for the LLM and Embeddings, with the ability to run in a GitHub Codespace but remain switchable.
**Options Considered:**
- **Option A: Ollama (Local)**
  - *Pros:* 100% free, offline capability, complete data privacy, provides an OpenAI-compatible API out of the box, extremely easy to install.
  - *Cons:* Requires the host machine (or Codespace) to have enough RAM/compute to run the model, slower than cloud APIs on CPU-only hosts.
- **Option B: HuggingFace Inference API (Cloud)**
  - *Pros:* No local compute required, fast, free tiers available for many models.
  - *Cons:* Subject to rate limits, data leaves the local machine, some models require paid Pro tier.
- **Option C: Sentence-Transformers (Local) + Cloud LLM**
  - *Pros:* Decouples memory (local) from reasoning (cloud), ensuring no API costs for heavy indexing.
  - *Cons:* Adds heavy Python dependencies (PyTorch) to the project just for embeddings, complicating the Docker image.

**Decision:** We chose **Option A (Ollama)** because it provides a unified, zero-dependency (via the OpenAI SDK) solution for both LLMs and Embeddings, ensuring complete data privacy. We automated its installation in the GitHub Codespace (`.devcontainer/setup.sh`) to eliminate the setup friction.

### Decision 2: Multi-Agent System (MAS) Framework
**Context:** Moving from a single ReAct loop to a multi-agent hierarchy to split the workload.
**Options Considered:**
- **Option A: CrewAI / AutoGen**
  - *Pros:* High-level, very fast to prototype. Agents figure out their own interactions.
  - *Cons:* Black-box logic. Hard to strictly control the flow to prevent infinite loops, and difficult to enforce absolute security bounds (like our Docker sandbox).
- **Option B: LangGraph (Current)**
  - *Pros:* Explicit control flow (DAG). Natively supports our custom Docker sandbox, streaming, and Memory Palace. 
  - *Cons:* Requires more boilerplate (state dicts, routing nodes).
**Decision:** We chose **Option B (LangGraph)** to ensure we maintain absolute control over the code execution sandbox and prevent endless conversational loops.

### Decision 3: Quality Assurance (QA) Sub-Agent
**Context:** The Analyst agent often gets "tunnel vision" when trying to self-correct sandbox errors.
**Options Considered:**
- **Option A: Solo Analyst (Self-Correction)**
  - *Pros:* Faster execution, uses fewer tokens per turn.
  - *Cons:* Prone to patching the code without fixing the underlying logical/statistical error.
- **Option B: Analyst + QA Reviewer Sub-Loop**
  - *Pros:* A dedicated QA agent reviews the Analyst's code/output before moving on. Massively reduces logic errors and catches edge cases.
  - *Cons:* Costs more tokens per iteration and slows down the total response time.
**Decision:** We chose **Option B (QA Reviewer)**. Combined with the Memory Palace (which isolates context and prevents token explosion), the QA loop is highly efficient and guarantees a production-grade, statistically sound output.

---

## 🏗️ Architecture (Current — Single Agent)

```
Streamlit UI  →  FastAPI Gateway  →  LangGraph ReAct Loop (1 AGENT)
                                         ├─→ FAISS Memory (schema retrieval only)
                                         ├─→ Gemini 1.5 Flash (code generation)
                                         └─→ Docker Sandbox (secure execution)
```

### How Many Agents? → **ONE**

There is only **1 agent** — a single LangGraph ReAct loop with 4 nodes:
- `reason` — retrieves schema context from FAISS, builds LLM prompt
- `act` — calls Gemini to generate Python code
- `observe` — executes code in Docker sandbox
- `respond` — summarizes output for the user

This is **NOT** a multi-agent system. There is no:
- ❌ Planner agent (decides what analysis approach to take)
- ❌ Researcher agent (explores the data before writing code)
- ❌ Validator agent (checks code quality/results before returning)
- ❌ Supervisor/orchestrator coordinating multiple agents

### Memory System Status → **BASIC (Schema RAG Only)**

The current memory system is **minimal** — it only does schema retrieval:
- `schema_embedder.py` — extracts column-level metadata (dtype, stats, sample values) from CSV
- `faiss_store.py` — stores embeddings in FAISS, retrieves top-k relevant columns at query time

What's **MISSING** from a real memory system:
- ❌ **Conversation memory** — no chat history persistence between queries
- ❌ **Learning memory** — doesn't remember past successful analyses
- ❌ **Cross-session memory** — everything is lost on server restart
- ❌ **Data profiling cache** — re-embeds on every upload, no caching
- ❌ **Result memory** — doesn't store past results for follow-up questions

---

## 🖥️ UI Status → **NEEDS FULL REBUILD**

### Current Problems with the Streamlit UI:
1. **Ugly default Streamlit look** — CSS overrides are limited, still looks like a Streamlit app
2. **No real-time streaming** — uses `time.sleep(1)` polling, not true SSE/WebSocket
3. **No data preview** — can't see the uploaded CSV data
4. **No interactive charts** — plots saved inside Docker sandbox are not retrievable
5. **No conversation persistence** — chat history lost on page refresh
6. **No loading animations** — just a basic spinner
7. **No error UX** — errors shown as raw text
8. **No dataset management** — can't switch between uploaded datasets
9. **Mobile-unfriendly** — no responsive design
10. **No dark/light toggle** — hardcoded dark theme that fights with Streamlit defaults

### Options for UI Rebuild:
- **Option A:** Rebuild with **Next.js** (WebSocket endpoint already exists in `backend/api/websocket.py`)
- **Option B:** Rebuild as a **standalone HTML/CSS/JS** SPA (lightweight, no framework needed)
- **Option C:** Heavily improve the **Streamlit** version (limited by Streamlit's constraints)

---

## ✅ What's Actually Built & Working (Code-Complete)

| # | Component | Files | Reality Check |
|---|-----------|-------|---------------|
| 1 | FastAPI backend scaffold | `backend/main.py`, `config.py` | ✅ Code complete, not tested |
| 2 | CSV upload + FAISS indexing | `routes.py`, `schema_embedder.py`, `faiss_store.py` | ✅ Code complete, not tested |
| 3 | Single ReAct agent (1 agent, 4 nodes) | `graph.py`, `nodes.py`, `state.py`, `prompts.py` | ✅ Code complete, not tested |
| 4 | Docker sandbox executor | `executor.py` | ✅ Code complete, not tested |
| 5 | Streamlit frontend | `frontend/app.py` | ⚠️ Functional but ugly |
| 6 | SSE streaming endpoint | `routes.py` | ✅ Code complete, not tested |
| 7 | WebSocket endpoint | `websocket.py` | ✅ Code complete, not tested |
| 8 | Pydantic schemas | `schemas.py` | ✅ Done |
| 9 | Docker Compose | `docker-compose.yml` | ✅ Done |
| 10 | Sandbox image | `sandbox/Dockerfile` | ✅ Done, not built |

---

## 🔧 Issues Encountered & Resolved

### Issue 1: GitHub Models API Retired  
- **Commit:** `6d34e91` → `3c936c6`  
- **Problem:** Switched to free GitHub Models API for `gpt-4o` + `text-embedding-3-small`, but service was retired.  
- **Fix:** Reverted, then switched to Gemini API.

### Issue 2: GitHub Models Base URL Incorrect  
- **Commit:** `7bdfad4`  
- **Problem:** Wrong base URL for GitHub Models.  
- **Fix:** Corrected URL (but abandoned approach — see Issue 1).

### Issue 3: Switched to Gemini API (Current Solution)  
- **Commit:** `58c7f57` (LATEST)  
- **Solution:** Google Gemini API via OpenAI compatibility layer.  
- `openai_base_url` → `https://generativelanguage.googleapis.com/v1beta/openai/`  
- `openai_model` → `gemini-1.5-flash`  
- `embedding_model` → `text-embedding-004`

---

## 🔴 Blocking Issues

| # | Issue | Details |
|---|-------|---------|
| 1 | **No `.env` file** | Backend will crash — needs `OPENAI_API_KEY` (Gemini key) |
| 2 | **Sandbox image not built** | Must run `docker build -t data-sandbox ./sandbox` |
| 3 | **`.env.example` outdated** | Still shows OpenAI config, not Gemini |
| 4 | **Never tested end-to-end** | No verification that the full pipeline works |

---

## 📁 File Map

```
e:\Data Assister\
├── .devcontainer/              # GitHub Codespace config
├── .env.example                # ⚠️ Outdated — shows OpenAI, not Gemini
├── Dockerfile                  # Main app container
├── README.md                   # Project docs
├── PROJECT_STATUS.md           # ← THIS FILE (session tracker)
├── docker-compose.yml
├── requirements.txt            # 32 deps
│
├── backend/
│   ├── main.py                 # FastAPI entry point
│   ├── config.py               # Pydantic Settings → Gemini config
│   ├── api/
│   │   ├── routes.py           # REST: upload, analyze, stream, datasets
│   │   └── websocket.py        # WS endpoint (for future Next.js)
│   ├── agent/                  # ← SINGLE AGENT, NOT MULTI-AGENT
│   │   ├── graph.py            # LangGraph ReAct (reason→act→observe→respond)
│   │   ├── nodes.py            # 4 node functions
│   │   ├── prompts.py          # System + task prompts
│   │   └── state.py            # AgentState TypedDict
│   ├── memory/                 # ← BASIC SCHEMA RAG ONLY
│   │   ├── faiss_store.py      # FAISS cosine search
│   │   └── schema_embedder.py  # CSV column metadata → embeddings
│   ├── models/
│   │   └── schemas.py          # Pydantic request/response models
│   └── sandbox/
│       └── executor.py         # Docker sandbox (ephemeral, no network)
│
├── frontend/                   # ← NEEDS REBUILD
│   └── app.py                  # Streamlit (326 lines, ugly)
│
└── sandbox/
    ├── Dockerfile              # Python sandbox image
    └── requirements.txt        # pandas, numpy, scipy, matplotlib, etc.
```

---

## 📝 Session Log

### Session 1: 2026-09-28
- Scaffolded full project structure
- Built single-agent backend: FastAPI + LangGraph + FAISS + Docker sandbox
- Built basic Streamlit frontend
- Tried GitHub Models API → retired → switched to Gemini API
- **Last issue:** GitHub Models API retired, switched to Gemini

### Session 2: 2026-09-29
- Created PROJECT_STATUS.md for session continuity
- Assessed current state: single agent, basic memory, basic UI
- Decided: engine-first rebuild, provider-agnostic, no Docker Desktop needed
- **Phase 1 COMPLETED ✅ — Foundation layer:**
  - Built `backend/core/` — LLM, Embedder, Sandbox abstract interfaces
  - Built `backend/providers/gemini.py` — Gemini via AsyncOpenAI compat
  - Built `backend/sandbox/subprocess_executor.py` — local dev sandbox
  - Built `backend/sandbox/docker_executor.py` — refactored Docker sandbox
  - Refactored `backend/config.py` — provider-agnostic settings
  - Updated `.env.example` — Gemini config with provider selection
  - All Phase 1 tests passing: config ✅, factories ✅, subprocess sandbox ✅, artifact collection ✅
- **Phase 1.5 COMPLETED ✅ — Local Open Source (Ollama):**
  - Built `backend/providers/ollama_provider.py` (LLM + Embeddings)
  - Registered Ollama in factories (`core/llm.py`, `core/embedder.py`)
  - Updated config and `.env.example` to make Ollama the default (100% free, no API key)
  - Refactored `agent/nodes.py` to use `create_llm()` and `create_sandbox()` (removed hardcoded `ChatOpenAI`)
- **Next:** Phase 2 — Memory system (conversation + analysis memory)

---

## 🚀 Roadmap

### Phase 1: Foundation ✅ DONE
- [x] Provider-agnostic LLM abstraction (`backend/core/llm.py`)
- [x] Provider-agnostic Embedding abstraction (`backend/core/embedder.py`)
- [x] Provider-agnostic Sandbox abstraction (`backend/core/sandbox.py`)
- [x] Gemini provider implementation (`backend/providers/gemini.py`)
- [x] Subprocess sandbox for local dev (`backend/sandbox/subprocess_executor.py`)
- [x] Docker sandbox refactored (`backend/sandbox/docker_executor.py`)
- [x] Config refactored for provider selection (`backend/config.py`)
- [x] Updated `.env.example`
- [x] Verification tests passing

### Phase 2: Memory System ✅ DONE
- [x] Schema memory (refactor existing FAISS store to use new abstractions)
- [x] Conversation memory (SQLite — chat history per session)
- [x] Analysis memory (FAISS + SQLite — past query/code/results)
- [x] Memory manager (unified interface for agents)

### Phase 3: Multi-Agent System ✅ DONE
- [x] BaseAgent class / Nodes implementation
- [x] Supervisor agent (orchestrator + intent classifier)
- [x] Profiler agent (auto-profile on upload - basic version integrated in memory)
- [x] Analyst agent (statistical code gen + execution)
- [x] Visualizer agent (chart generation)
- [x] LangGraph multi-agent workflow

### Phase 4: API + UI (NEXT)
- [ ] Clean REST API + WebSocket streaming
- [ ] Premium frontend (Next.js or standalone)
- [ ] Dashboard layout, data preview, charts

### Phase 5: Production
- [ ] Authentication
- [ ] Persistent storage
- [ ] CI/CD + tests
- [ ] Documentation

