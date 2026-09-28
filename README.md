# 🧠 Agentic Data Assistant

An autonomous, production-grade AI data analysis engine. Upload a CSV, ask a question in plain English, and the agent writes code, executes it in a secure Docker sandbox, self-corrects on errors, and delivers validated statistical insights.

## Architecture

```
Streamlit UI  →  FastAPI Gateway  →  LangGraph ReAct Loop
                                         ├─→ FAISS Memory (schema retrieval)
                                         ├─→ OpenAI GPT-4o (code generation)
                                         └─→ Docker Sandbox (secure execution)
```

## Quick Start (GitHub Codespaces)

```bash
# 1. Set your OpenAI API key
cp .env.example .env
# Edit .env → paste your OPENAI_API_KEY

# 2. Install Python dependencies
pip install -r requirements.txt

# 3. Build the sandbox Docker image
docker build -t data-sandbox ./sandbox

# 4. Start the FastAPI backend (Terminal 1)
uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000

# 5. Start the Streamlit frontend (Terminal 2)
streamlit run frontend/app.py --server.port 8501 --server.address 0.0.0.0
```

Then open the forwarded port **8501** in your browser.

## Alternative: Docker Compose

```bash
cp .env.example .env
# Edit .env → add OPENAI_API_KEY
docker compose up --build
```

## Project Structure

```
├── .devcontainer/          # Codespace configuration
├── backend/
│   ├── main.py             # FastAPI entry point
│   ├── config.py           # Pydantic Settings
│   ├── api/
│   │   ├── routes.py       # REST endpoints (upload, analyze, stream)
│   │   └── websocket.py    # WS endpoint (for Next.js frontend)
│   ├── agent/
│   │   ├── state.py        # LangGraph state schema
│   │   ├── graph.py        # ReAct state machine definition
│   │   ├── nodes.py        # reason → act → observe → respond
│   │   └── prompts.py      # System & task prompts
│   ├── memory/
│   │   ├── faiss_store.py  # FAISS index (build / search)
│   │   └── schema_embedder.py  # CSV metadata extraction + embedding
│   └── sandbox/
│       └── executor.py     # Docker sandbox execution engine
├── frontend/
│   └── app.py              # Streamlit dashboard
├── sandbox/
│   ├── Dockerfile          # Minimal Python image for code execution
│   └── requirements.txt    # pandas, numpy, scipy, matplotlib, etc.
├── docker-compose.yml
├── requirements.txt
└── .env.example
```

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/upload` | Upload CSV → build FAISS index |
| `POST` | `/api/analyze` | Start analysis thread (async) |
| `GET` | `/api/threads/{id}` | Poll thread status + results |
| `GET` | `/api/threads/{id}/stream` | SSE thought stream |
| `WS` | `/ws/{thread_id}` | WebSocket thought stream |
| `GET` | `/api/datasets` | List uploaded datasets |
| `GET` | `/health` | Liveness probe |

## How the ReAct Loop Works

1. **REASON** — Query FAISS for relevant column metadata, build a focused prompt
2. **ACT** — LLM generates Python/Pandas code using only known columns
3. **OBSERVE** — Code executes in a sandboxed Docker container (no network, 30s timeout, 512MB RAM)
4. **Self-Correct** — On error, traceback routes back to REASON (up to 3 retries)
5. **RESPOND** — Summarize raw output into a stakeholder-friendly answer

## Security

- LLM-generated code **never** runs on the host machine
- Sandbox containers have **no network access**
- Dataset is mounted **read-only**
- Containers are **destroyed** after each execution
- Memory and CPU are **capped**

## Requirements

- Python 3.12+
- Docker
- OpenAI API key (GPT-4o + text-embedding-3-small)
