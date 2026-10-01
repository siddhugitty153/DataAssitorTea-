"""
REST API routes — the FastAPI gateway.

Endpoints:
  POST /api/upload           Upload a CSV and build its FAISS index
  POST /api/analyze          Start an analysis thread (background)
  GET  /api/threads/{id}     Poll thread status + results
  GET  /api/threads/{id}/stream   SSE stream of agent thought steps
  GET  /api/datasets         List uploaded datasets
"""

from __future__ import annotations

import asyncio
import json
import uuid

import pandas as pd
from fastapi import APIRouter, BackgroundTasks, File, HTTPException, UploadFile
from fastapi.responses import StreamingResponse

from backend.agent.graph import agent
from backend.config import settings
from backend.memory.faiss_store import FAISSStore
from backend.memory.schema_embedder import SchemaEmbedder
from backend.models.schemas import AnalyzeRequest, UploadResponse

router = APIRouter(prefix="/api", tags=["api"])

# ── In-memory stores (swap for Redis / Postgres in production) ──
threads: dict[str, dict] = {}
datasets: dict[str, dict] = {}


# ────────────────────────────────────────────────────────────────
# POST /api/upload
# ────────────────────────────────────────────────────────────────

@router.post("/upload", response_model=UploadResponse)
async def upload_dataset(file: UploadFile = File(...)):
    """Upload a CSV, extract schema metadata, and build a FAISS index."""
    if not file.filename or not file.filename.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="Only .csv files are supported.")

    dataset_id = uuid.uuid4().hex[:8]
    save_dir = settings.data_dir / dataset_id
    save_dir.mkdir(parents=True, exist_ok=True)
    save_path = save_dir / "dataset.csv"

    # Persist file
    content = await file.read()
    save_path.write_bytes(content)

    # Quick peek
    df = pd.read_csv(save_path, nrows=5)
    row_count = sum(1 for _ in open(save_path, encoding="utf-8")) - 1

    # Build FAISS index
    embedder = SchemaEmbedder()
    metadata = embedder.extract_metadata(str(save_path))
    texts, embeddings = await embedder.create_embeddings(metadata)

    store = FAISSStore(dataset_id)
    store.build_index(texts, embeddings)

    datasets[dataset_id] = {
        "dataset_id": dataset_id,
        "filename": file.filename,
        "path": str(save_path),
        "columns": list(df.columns),
        "row_count": row_count,
    }

    return UploadResponse(
        dataset_id=dataset_id,
        filename=file.filename,
        columns=list(df.columns),
        row_count=row_count,
        message=f"Indexed {row_count:,} rows × {len(df.columns)} columns into FAISS.",
    )


# ────────────────────────────────────────────────────────────────
# POST /api/analyze
# ────────────────────────────────────────────────────────────────

@router.post("/analyze")
async def analyze_dataset(
    request: AnalyzeRequest,
    background_tasks: BackgroundTasks,
):
    """Kick off the ReAct agent in the background and return a thread_id."""
    if request.dataset_id not in datasets:
        raise HTTPException(status_code=404, detail="Dataset not found. Upload first.")

    thread_id = uuid.uuid4().hex[:8]
    ds = datasets[request.dataset_id]

    threads[thread_id] = {
        "thread_id": thread_id,
        "dataset_id": request.dataset_id,
        "query": request.query,
        "status": "pending",
        "thoughts": [],
        "result": None,
        "generated_code": None,
        "error": None,
    }

    # Add query to Working Memory
    from backend.memory.manager import MemoryManager
    manager = MemoryManager(thread_id, request.dataset_id)
    manager.add_message("user", request.query)

    background_tasks.add_task(
        _run_agent,
        thread_id,
        request.dataset_id,
        ds["path"],
        request.query,
    )

    return {"thread_id": thread_id, "status": "pending", "message": "Analysis started."}


# ────────────────────────────────────────────────────────────────
# GET /api/threads/{thread_id}
# ────────────────────────────────────────────────────────────────

@router.get("/threads/{thread_id}")
async def get_thread(thread_id: str):
    """Return the current state of an analysis thread."""
    if thread_id not in threads:
        raise HTTPException(status_code=404, detail="Thread not found.")
    return threads[thread_id]


# ────────────────────────────────────────────────────────────────
# GET /api/threads/{thread_id}/stream   (Server-Sent Events)
# ────────────────────────────────────────────────────────────────

@router.get("/threads/{thread_id}/stream")
async def stream_thread(thread_id: str):
    """Stream agent thoughts as Server-Sent Events (SSE)."""
    if thread_id not in threads:
        raise HTTPException(status_code=404, detail="Thread not found.")

    async def _generate():
        last_seen = 0
        while True:
            thread = threads.get(thread_id, {})
            thoughts = thread.get("thoughts", [])

            # Emit new thought steps
            for thought in thoughts[last_seen:]:
                yield f"data: {json.dumps(thought)}\n\n"
                last_seen += 1

            # Terminal state → send final event and close
            if thread.get("status") in ("completed", "failed"):
                final = {
                    "type": "done",
                    "status": thread["status"],
                    "result": thread.get("result", ""),
                    "generated_code": thread.get("generated_code", ""),
                }
                yield f"data: {json.dumps(final)}\n\n"
                break

            await asyncio.sleep(0.5)

    return StreamingResponse(_generate(), media_type="text/event-stream")


# ────────────────────────────────────────────────────────────────
# GET /api/datasets
# ────────────────────────────────────────────────────────────────

@router.get("/datasets")
async def list_datasets():
    """List all uploaded datasets."""
    return {"datasets": list(datasets.values())}


# ────────────────────────────────────────────────────────────────
# Background agent runner
# ────────────────────────────────────────────────────────────────

async def _run_agent(
    thread_id: str,
    dataset_id: str,
    dataset_path: str,
    query: str,
) -> None:
    """Stream-execute the LangGraph agent and update thread state in-place."""
    try:
        threads[thread_id]["status"] = "running"

        initial_state = {
            "messages": [],
            "dataset_id": dataset_id,
            "dataset_path": dataset_path,
            "thread_id": thread_id,
            "query": query,
            "schema_context": "",
            "generated_code": "",
            "execution_result": "",
            "execution_error": "",
            "iteration": 0,
            "max_iterations": settings.max_iterations,
            "status": "pending",
            "thought_log": [],
        }

        async for event in agent.astream(initial_state):
            for _node_name, node_output in event.items():
                if "thought_log" in node_output:
                    threads[thread_id]["thoughts"] = node_output["thought_log"]
                if "status" in node_output:
                    threads[thread_id]["status"] = node_output["status"]
                if "generated_code" in node_output:
                    threads[thread_id]["generated_code"] = node_output["generated_code"]
                if "execution_result" in node_output:
                    threads[thread_id]["result"] = node_output["execution_result"]
                if "execution_error" in node_output:
                    threads[thread_id]["error"] = node_output["execution_error"]

    except Exception as exc:
        threads[thread_id]["status"] = "failed"
        threads[thread_id]["error"] = str(exc)
