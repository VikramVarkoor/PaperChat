"""
routers/upload.py — Document Upload Endpoint

POST /upload
  - Receives a PDF file from the frontend
  - Runs the full ingestion pipeline:
      extract text → chunk → embed → store in Chroma
  - Returns DocumentInfo so the frontend can switch to chat mode

DELETE /documents/{document_id}
  - Removes a document's Chroma collection
  - Called when user clicks "New doc"

FASTAPI CONCEPTS USED HERE:

  @router.post("/upload") — Decorator that registers this function as the
  handler for POST requests to /upload. The function runs when that route is hit.

  UploadFile — FastAPI's special type for file uploads.
  When you annotate a parameter as `UploadFile`, FastAPI automatically reads
  the multipart form data and gives you a file-like object to work with.

  HTTPException — Raises an HTTP error response. FastAPI catches it and
  returns the appropriate status code + JSON error message.
  Common codes: 400 (bad request), 404 (not found), 500 (server error).

  async/await — Python's concurrency model. `async def` functions can
  be "paused" (awaited) to let other requests run while waiting for I/O.
  This means FastAPI can handle multiple simultaneous uploads without
  blocking — critical for a web server.
"""

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, UploadFile, File, HTTPException

from core.ingestion import process_pdf
from core.vectorstore import index_chunks, delete_collection
from models.schemas import DocumentInfo, UploadResponse

# APIRouter is like a mini-app. We register routes on it, then include it in main.py.
router = APIRouter()


@router.post("/upload", response_model=UploadResponse)
async def upload_document(
    # `File(...)` tells FastAPI this is a required file upload field.
    # The `...` means "required" in Pydantic/FastAPI syntax.
    file: UploadFile = File(...),
):
    """
    Ingests a PDF document into the RAG pipeline.

    Flow:
      1. Validate file type and size
      2. Extract text using pdfplumber
      3. Split into overlapping chunks
      4. Embed all chunks using sentence-transformers
      5. Store in Chroma vector database
      6. Return DocumentInfo to frontend

    Frontend calls this with FormData containing the PDF file.
    """

    # ── Validation ────────────────────────────────────────────────────────────

    # Check file type (content_type is set by the browser from the file's MIME type)
    if file.content_type not in ("application/pdf", "application/octet-stream"):
        raise HTTPException(
            status_code=400,
            detail=f"Invalid file type: {file.content_type}. Only PDFs are supported."
        )

    # Check file size (read into memory, validate, then reset for processing)
    file_bytes = await file.read()
    max_size_mb = 20
    if len(file_bytes) > max_size_mb * 1024 * 1024:
        raise HTTPException(
            status_code=400,
            detail=f"File too large. Maximum size is {max_size_mb}MB."
        )

    # Reset the file position to the beginning so pdfplumber can read it
    # (reading already consumed the stream — we need to rewind it)
    await file.seek(0)

    # ── Generate Document ID ──────────────────────────────────────────────────
    # uuid4() generates a random, universally unique identifier.
    # We prefix with "doc_" so it's clearly a document ID.
    # This becomes the Chroma collection name.
    # "doc_" prefix + 8 chars of UUID = e.g. "doc_a1b2c3d4"
    document_id = f"doc_{uuid.uuid4().hex[:12]}"

    # ── Run Ingestion Pipeline ────────────────────────────────────────────────
    try:
        # Step 1 + 2: Extract text and split into chunks
        # file.file is the underlying SpooledTemporaryFile that pdfplumber can read
        chunks, page_count = process_pdf(file.file)

        print(f"Processed '{file.filename}': {page_count} pages, {len(chunks)} chunks")

        # Steps 3 + 4: Embed chunks and store in Chroma
        index_chunks(document_id, chunks)

    except ValueError as e:
        # ValueError means something was wrong with the PDF content
        raise HTTPException(status_code=422, detail=str(e))

    except Exception as e:
        # Unexpected errors — log them and return a generic message
        print(f"ERROR during ingestion of '{file.filename}': {e}")
        raise HTTPException(
            status_code=500,
            detail="Failed to process the document. Please try again."
        )

    # ── Build Response ────────────────────────────────────────────────────────
    document = DocumentInfo(
        id=document_id,
        name=file.filename or "document.pdf",
        pageCount=page_count,
        chunkCount=len(chunks),
        uploadedAt=datetime.now(timezone.utc).isoformat(),
    )

    return UploadResponse(
        success=True,
        document=document,
        message=f"Successfully processed {page_count} pages into {len(chunks)} searchable chunks.",
    )


@router.delete("/documents/{document_id}")
async def delete_document(document_id: str):
    """
    Removes a document from the vector database.

    Path parameters: FastAPI extracts {document_id} from the URL automatically.
    DELETE /documents/doc_abc123 → document_id = "doc_abc123"
    """
    success = delete_collection(document_id)

    if not success:
        raise HTTPException(
            status_code=404,
            detail=f"Document '{document_id}' not found."
        )

    return {"success": True, "message": f"Document '{document_id}' deleted."}
