"""
Agentic Data Assistant — FastAPI Application Entry Point
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.api.routes import router
from backend.api.websocket import ws_router
from backend.config import settings


# ── Ensure data directories exist ──
settings.data_dir.mkdir(parents=True, exist_ok=True)
settings.faiss_dir.mkdir(parents=True, exist_ok=True)
settings.uploads_dir.mkdir(parents=True, exist_ok=True)


# ── Application ──
app = FastAPI(
    title="Agentic Data Assistant",
    description="Autonomous AI-powered data analysis engine with ReAct orchestration",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# CORS — allow Streamlit and future Next.js frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Routers ──
app.include_router(router)
app.include_router(ws_router)


@app.get("/health", tags=["system"])
async def health():
    """Liveness probe."""
    return {"status": "healthy", "version": "1.0.0"}


@app.get("/", tags=["system"])
async def root():
    return {
        "service": "Agentic Data Assistant",
        "docs": "/docs",
        "health": "/health",
    }
