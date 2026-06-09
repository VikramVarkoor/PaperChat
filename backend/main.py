"""
main.py — FastAPI Application Entry Point

This is where the backend starts. When you run `uvicorn main:app --reload`,
Python imports this file and uvicorn runs the `app` object.

FastAPI is a modern Python web framework designed specifically for building APIs.
Key reasons we chose it over Flask or Django:
  - Built-in async support (critical for streaming responses)
  - Auto-generates interactive API docs at /docs (OpenAPI/Swagger)
  - Pydantic integration for automatic request/response validation
  - Much faster than Flask for I/O-heavy workloads like LLM calls

HOW AN API REQUEST FLOWS THROUGH THIS APP:
  Browser → Next.js (/api/py/upload) → next.config.js rewrite
  → FastAPI (localhost:8000/upload) → router → core logic → response
"""

import os
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Load .env file FIRST before importing anything else.
# This ensures all modules that read env vars at import time get the right values.
load_dotenv()

# Import our routers (defined in routers/ folder)
from routers import upload, chat
from core.embeddings import get_embedding_model

# ── Lifespan ──────────────────────────────────────────────────────────────────
#
# `lifespan` is FastAPI's way of running code at startup and shutdown.
# We use it to pre-load the embedding model when the server starts.
#
# WHY pre-load?
# The first time sentence-transformers loads a model, it downloads it (~80MB)
# and loads it into RAM. This takes 5-15 seconds.
# If we let this happen on the FIRST REQUEST, that user gets a 15-second delay.
# By pre-loading at startup, the model is warm and ready for the first request.

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Code here runs at STARTUP (before any requests are handled)
    print("🚀 PaperChat backend starting up...")
    print("📦 Loading embedding model (this may take a moment on first run)...")
    get_embedding_model()  # Warms the model cache
    print("✅ Embedding model ready")
    print(f"📖 API docs available at: http://localhost:{os.getenv('PORT', 8000)}/docs")

    yield  # The app runs while we're here

    # Code here runs at SHUTDOWN (after the server stops)
    print("👋 PaperChat backend shutting down...")


# ── App Instance ──────────────────────────────────────────────────────────────

app = FastAPI(
    title="PaperChat API",
    description="RAG-powered document Q&A backend. Upload PDFs, chat with them.",
    version="1.0.0",
    lifespan=lifespan,
    # This enables the auto-generated interactive docs at /docs
    # Go to http://localhost:8000/docs when the server is running —
    # you can test every endpoint directly from the browser. Very useful.
    docs_url="/docs",
    redoc_url="/redoc",
)

# ── CORS Middleware ───────────────────────────────────────────────────────────
#
# CORS = Cross-Origin Resource Sharing.
# Browsers block JavaScript from making requests to a different origin
# (different domain, port, or protocol) by default. This is a security feature.
#
# Our setup:
#   - Next.js frontend: localhost:3000
#   - FastAPI backend:  localhost:8000
# These are different origins → browser blocks requests by default.
#
# The CORS middleware adds HTTP headers that tell the browser:
# "It's okay for localhost:3000 to talk to this server."
#
# NOTE: In production, replace "*" with your actual deployed frontend URL
# to prevent other websites from calling your API.

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",   # Next.js dev server
        "http://localhost:3001",   # Alternative port
        "https://*.vercel.app",    # Vercel deployments
    ],
    allow_credentials=True,
    allow_methods=["*"],           # Allow GET, POST, DELETE, etc.
    allow_headers=["*"],           # Allow Content-Type, Authorization, etc.
)

# ── Routers ───────────────────────────────────────────────────────────────────
#
# Routers are FastAPI's way of splitting API endpoints across multiple files.
# Instead of defining all routes in main.py (which gets messy), we define
# them in separate files and "include" them here.
#
# The `prefix` argument adds a URL prefix to all routes in that router.
# So `upload.router` has a route `/upload` → it becomes `/upload` (no prefix).
# We could add prefix="/v1" to version the API: `/v1/upload`, `/v1/chat`, etc.

app.include_router(upload.router, tags=["Documents"])
app.include_router(chat.router, tags=["Chat"])


# ── Root Route ────────────────────────────────────────────────────────────────

@app.get("/")
async def root():
    """Quick sanity check — visit http://localhost:8000/ in your browser."""
    return {
        "service": "PaperChat API",
        "status": "running",
        "docs": "/docs",
    }


# ── Dev Server Entry Point ───────────────────────────────────────────────────
#
# This block only runs when you execute: python main.py
# When using uvicorn directly (uvicorn main:app), this block is ignored.
# The `--reload` flag makes uvicorn watch for file changes and restart automatically.

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host=os.getenv("HOST", "0.0.0.0"),
        port=int(os.getenv("PORT", 8000)),
        reload=True,   # Auto-restart when you save a file
        reload_dirs=["./"],
    )
