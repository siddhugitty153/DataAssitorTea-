# 🧠 Agentic Data Assistant

An autonomous, production-grade AI multi-agent data analysis engine. Upload any CSV dataset, ask analytical questions in plain English, and watch the multi-agent system write code, execute it in a sandboxed environment, self-heal runtime errors, and present verified statistical insights in real time.

---

## 🏛️ Architecture

```
Next.js UI (Port 3000) ──HTTP / SSE / WS──► FastAPI Gateway (Port 8000)
                                                    │
                      ┌─────────────────────────────┼─────────────────────────────┐
                      ▼                             ▼                             ▼
            Hierarchical Memory Palace    LangGraph Multi-Agent System       Execution Sandbox
            • Schema Vault (FAISS)        • Supervisor (Fast Router)         • Subprocess (Local Dev)
            • Episodic Library (FAISS)    • Analyst (Code Generator)         • Docker (Isolated Prod)
            • Working Foyer (SQLite)      • QA Reviewer (Auto-Pass/Retry)    • Read-Only Data Mounts
                                          • Responder (Insight Synthesis)    • 30s Timeout & Resource Caps
```

---

## 🔑 API Keys & Provider Setup

The system supports 3 LLM and embedding backends configured in your `.env` file:

### Option A: Google Gemini (Recommended — Cloud & Free Tier Available)
1. Get a free API key at [Google AI Studio](https://aistudio.google.com/apikey).
2. Set in your `.env`:
   ```env
   LLM_PROVIDER=gemini
   EMBEDDING_PROVIDER=gemini
   GEMINI_API_KEY=AIzaSy...your-gemini-key-here
   GEMINI_MODEL=gemini-2.5-flash
   GEMINI_EMBEDDING_MODEL=gemini-embedding-2
   ```

### Option B: Ollama (100% Local, Offline & Free — No API Key Required)
1. Download and install [Ollama](https://ollama.com/download).
2. Pull the required models in your terminal:
   ```bash
   ollama pull llama3.2
   ollama pull nomic-embed-text
   ```
3. Set in your `.env`:
   ```env
   LLM_PROVIDER=ollama
   EMBEDDING_PROVIDER=ollama
   OLLAMA_BASE_URL=http://localhost:11434/v1/
   OLLAMA_MODEL=llama3.2
   OLLAMA_EMBEDDING_MODEL=nomic-embed-text
   ```

### Option C: OpenAI (Cloud)
1. Get an API key from [platform.openai.com](https://platform.openai.com/api-keys).
2. Set in your `.env`:
   ```env
   LLM_PROVIDER=openai
   EMBEDDING_PROVIDER=openai
   OPENAI_API_KEY=sk-...your-openai-key-here
   OPENAI_MODEL=gpt-4o
   OPENAI_EMBEDDING_MODEL=text-embedding-3-small
   ```

---

## 🚀 Quick Start & How to Run

### Step 1: Clone and Configure Environment
```bash
# 1. Clone repository
git clone https://github.com/siddhugitty153/techvruk-data-assistant.git
cd techvruk-data-assistant

# 2. Copy environment file and add your key
cp .env.example .env
# Edit .env and paste your GEMINI_API_KEY (or configure Ollama/OpenAI)
```

### Step 2: Set up Backend (Python 3.12+)
```bash
# Create and activate virtual environment (optional but recommended)
python -m venv venv
# Windows:
.\venv\Scripts\activate
# Linux/macOS:
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Start FastAPI server (Terminal 1)
uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000
```
*The backend will be live at `http://localhost:8000` (Swagger docs at `http://localhost:8000/docs`).*

### Step 3: Set up Frontend (Next.js)
```bash
# In a new terminal (Terminal 2)
cd frontend
npm install
npm run dev
```
*Open [http://localhost:3000](http://localhost:3000) in your browser.*

---

## 📖 How to Use the App

1. **Upload Dataset:** Drag and drop any CSV file into the sidebar or click to select (e.g. `sample_sales_data.csv`).
2. **Schema Indexing:** The engine automatically extracts statistical summaries, data types, and null distributions, storing them into the FAISS Schema Vault.
3. **Ask Questions:** In the chat interface, ask analytical queries such as:
   - *"What are the top 3 selling product categories by total revenue?"*
   - *"Is there a correlation between discount percentages and unit profit?"*
   - *"Identify any anomalies or outliers in quarterly shipping costs."*
4. **Inspect Live Agent Execution:**
   - Watch the live **ReAct Thought Trace** accordion show column retrieval, Python code generation, sandbox output, and verification passes.
   - Inspect the exact Pandas code written and executed.
   - Monitor the real-time **Token Usage Meter** on each query.

---

## ⚡ Token Economics & Quantified Efficiency

Traditional tabular AI dumps raw CSV rows directly into LLM prompts, leading to million-token bills, slow execution, and context overflow. **Data Assister uses an execution-based ReAct sandbox architecture + a 3-tier Memory Palace to reduce token consumption by >99.9%**:

| Metric (e.g. 60,000-Row Dataset Query) | Standard Tabular RAG | Data Assister Sandbox Engine | Savings |
| :--- | :--- | :--- | :--- |
| **Ingestion Token Overhead** | ~1,200,000 tokens | **~450 tokens** (Column statistics in FAISS) | **99.96%** |
| **Code Generation Prompt** | N/A (Fails context limit) | **~350 tokens** (Targeted top-k columns) | — |
| **Data Processing Execution** | LLM Hallucination | **0 tokens** (Local C-speed NumPy/Pandas) | **100% Free** |
| **Result Synthesis** | ~5,000 tokens | **~150 tokens** (Aggregated results) | **97.00%** |
| **Total Query Cost** | **$3.00 - $12.00 / query** | **<$0.0005 / query** | **>99.9%** |

---

## 🛡️ Security & Sandbox Execution

- **Zero Host Risk:** Code executes within isolated sandbox environments (Docker with no-network policy or isolated subprocess).
- **Read-Only Data Mounts:** Uploaded datasets cannot be modified or overwritten by generated scripts.
- **Resource Constraints:** Strict 30-second execution timeouts and memory caps (512MB) protect against infinite loops and memory leaks.
- **Self-Correction:** If code fails at runtime, stdout/traceback errors are routed back to the Analyst agent to heal the script (up to 3 retries).

---

## 📁 Project Structure

```
├── backend/
│   ├── main.py             # FastAPI entry point & lifespan
│   ├── config.py           # Provider settings & env loader
│   ├── api/
│   │   ├── routes.py       # REST endpoints (upload, analyze, streaming)
│   │   └── websocket.py    # WebSocket real-time thought stream
│   ├── agent/
│   │   ├── graph.py        # LangGraph ReAct state machine
│   │   ├── nodes.py        # Supervisor, Analyst, Sandbox, QA, Responder
│   │   └── prompts.py      # System prompts & few-shot instructions
│   ├── memory/
│   │   ├── manager.py      # 3-Tier Hierarchical Memory Palace
│   │   ├── faiss_store.py  # FAISS vector store
│   │   └── schema_embedder.py # CSV metadata & embedding generator
│   └── sandbox/
│       ├── subprocess_executor.py # Local isolated execution
│       └── executor.py     # Docker container execution
├── frontend/               # Next.js 16 + React 19 reactive dashboard
├── data/                   # Local uploads and FAISS index cache
├── sample_sales_data.csv   # Sample dataset for testing
├── requirements.txt        # Python backend dependencies
└── .env.example            # Environment template with provider options
```
