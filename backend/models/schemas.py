"""
models/schemas.py — Pydantic Data Models

Pydantic is a data validation library that FastAPI is built on.
You define the "shape" of data using Python classes with type hints,
and Pydantic automatically:
  - Validates incoming request data (wrong type → 422 error with a clear message)
  - Serializes outgoing response data to JSON
  - Generates the JSON schema used in /docs

Think of these as contracts between the frontend and backend.
If the frontend sends { "question": 123 } but we expect a string,
Pydantic rejects it with a clear error message before it hits our code.

These mirror the TypeScript types in lib/types.ts on the frontend.
"""

from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field


# ── Document Models ───────────────────────────────────────────────────────────

class DocumentInfo(BaseModel):
    """
    Metadata about an uploaded and processed document.
    Returned after a successful upload.
    Mirrors the `Document` interface in lib/types.ts.
    """
    id: str = Field(..., description="Unique document ID (used as Chroma collection name)")
    name: str = Field(..., description="Original filename e.g. 'report_2024.pdf'")
    page_count: int = Field(..., description="Total pages in the PDF", alias="pageCount")
    chunk_count: int = Field(..., description="Number of text chunks indexed", alias="chunkCount")
    uploaded_at: str = Field(..., description="ISO 8601 timestamp", alias="uploadedAt")

    # `model_config` lets us configure Pydantic's behaviour.
    # `populate_by_name=True` means we can set fields by either
    # the Python name (page_count) OR the alias (pageCount).
    # `from_attributes=True` allows creating from ORM objects (useful later).
    model_config = {"populate_by_name": True, "from_attributes": True}


class UploadResponse(BaseModel):
    """Response body for POST /upload"""
    success: bool
    document: DocumentInfo
    message: str


# ── Chat Models ───────────────────────────────────────────────────────────────

class HistoryMessage(BaseModel):
    """A single turn of conversation history."""
    # Literal type: only "user" or "assistant" are valid values.
    # Pydantic rejects anything else.
    role: str = Field(..., pattern="^(user|assistant)$")
    content: str


class ChatRequest(BaseModel):
    """
    Request body for POST /chat.
    The frontend sends this when the user submits a question.
    """
    question: str = Field(..., min_length=1, max_length=2000,
                          description="The user's question")
    document_id: str = Field(..., alias="documentId",
                             description="Which document to search in Chroma")
    history: Optional[list[HistoryMessage]] = Field(
        default=[],
        description="Previous conversation turns for context (last 3-6 messages)"
    )

    model_config = {"populate_by_name": True}


class SourceChunk(BaseModel):
    """
    A single retrieved chunk from the vector database.
    Sent back to the frontend so it can render source citations.
    """
    content: str = Field(..., description="The text content of this chunk")
    page: int = Field(..., description="Page number in the original PDF (1-indexed)")
    score: float = Field(..., ge=0.0, le=1.0,
                         description="Cosine similarity score: 0=unrelated, 1=identical meaning")


# ── Health Check ──────────────────────────────────────────────────────────────

class HealthResponse(BaseModel):
    """Response body for GET /health"""
    status: str
    embedding_model: str
    chroma_status: str
