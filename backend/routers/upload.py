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

import io
import threading
import time
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, UploadFile, File, HTTPException

from core.ingestion import process_pdf
from core.vectorstore import index_chunks, delete_collection
from models.schemas import DocumentInfo

# APIRouter is like a mini-app. We register routes on it, then include it in main.py.
router = APIRouter()


# ── Background upload jobs ────────────────────────────────────────────────────
#
# Processing a long PDF (extract, chunk, embed) can take minutes on a small
# server. So POST /upload only validates the file, starts a background thread
# and returns a job id straight away. The frontend then polls
# GET /upload/status/{job_id} to show real progress.
#
# Jobs live in memory (like the vector store), so a server restart loses them.
_jobs: dict[str, dict] = {}
_MAX_JOBS = 20
_pipeline_lock = threading.Lock()  # one document at a time on a 512MB server


def _prune_jobs() -> None:
    """Keeps only the most recent jobs so memory doesn't grow."""
    while len(_jobs) >= _MAX_JOBS:
        oldest = min(_jobs, key=lambda j: _jobs[j]["created"])
        del _jobs[oldest]


def _run_job(job_id: str, file_bytes: bytes, filename: str) -> None:
    job = _jobs[job_id]

    def on_progress(stage: str, done: int, total: int) -> None:
        job.update(stage=stage, done=done, total=total)

    try:
        with _pipeline_lock:
            job.update(stage="extracting", done=0, total=0)
            chunks, page_count = process_pdf(io.BytesIO(file_bytes), on_progress)
            print(f"Processed '{filename}': {page_count} pages, {len(chunks)} chunks")

            job.update(stage="embedding", done=0, total=len(chunks))
            index_chunks(job["documentId"], chunks, on_progress=lambda d, t: on_progress("embedding", d, t))

        document = DocumentInfo(
            id=job["documentId"],
            name=filename or "document.pdf",
            pageCount=page_count,
            chunkCount=len(chunks),
            uploadedAt=datetime.now(timezone.utc).isoformat(),
        )
        job.update(stage="done", document=document.model_dump(by_alias=True))

    except ValueError as e:
        # Something was wrong with the PDF content
        job.update(stage="error", error=str(e))

    except Exception as e:
        print(f"ERROR during ingestion of '{filename}': {e}")
        job.update(stage="error", error="Failed to process the document. Please try again.")


@router.post("/upload")
async def upload_document(
    # `File(...)` tells FastAPI this is a required file upload field.
    file: UploadFile = File(...),
):
    """
    Starts ingesting a PDF and returns a job id.

    Flow:
      1. Validate file type and size
      2. Start a background job: extract text, chunk, embed, store in memory
      3. Return {"jobId": ...} immediately
      4. Frontend polls GET /upload/status/{jobId} until stage is "done"
    """

    # Check file type (content_type is set by the browser from the file's MIME type)
    if file.content_type not in ("application/pdf", "application/octet-stream"):
        raise HTTPException(
            status_code=400,
            detail=f"Invalid file type: {file.content_type}. Only PDFs are supported."
        )

    file_bytes = await file.read()
    max_size_mb = 20
    if len(file_bytes) > max_size_mb * 1024 * 1024:
        raise HTTPException(
            status_code=400,
            detail=f"File too large. Maximum size is {max_size_mb}MB."
        )

    job_id = f"job_{uuid.uuid4().hex[:12]}"
    _prune_jobs()
    _jobs[job_id] = {
        "created": time.time(),
        "documentId": f"doc_{uuid.uuid4().hex[:12]}",
        "stage": "queued",
        "done": 0,
        "total": 0,
    }

    threading.Thread(
        target=_run_job,
        args=(job_id, file_bytes, file.filename or "document.pdf"),
        daemon=True,
    ).start()

    return {"jobId": job_id}


@router.get("/upload/status/{job_id}")
async def upload_status(job_id: str):
    """
    Progress of an upload job.
    stage is one of: queued, extracting, chunking, embedding, done, error.
    done/total count pages while extracting and chunks while embedding.
    """
    job = _jobs.get(job_id)
    if job is None:
        raise HTTPException(
            status_code=404,
            detail="Upload job not found. The server may have restarted, please try again.",
        )
    return {k: v for k, v in job.items() if k not in ("created", "documentId")}


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
