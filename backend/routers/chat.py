from __future__ import annotations

"""
routers/chat.py — Chat and Health Check Endpoints

POST /chat
  The main endpoint. Receives a question + document ID, retrieves
  relevant chunks from Chroma, streams the LLM's answer back.

GET /health
  Simple health check. The frontend pings this to verify the backend is up.

THE STREAMING RESPONSE EXPLAINED:

  Normal HTTP: Client → Request → Server processes → Response (all at once)
  Streaming:   Client → Request → Server sends chunks → ... → Server sends final chunk

  FastAPI implements streaming via StreamingResponse + an async generator.
  The generator `yield`s strings one at a time, and FastAPI sends each
  one immediately over the same HTTP connection.

  We format each yield as SSE (Server-Sent Events):
    "data: {\"token\": \"The\"}\n\n"
    "data: {\"token\": \" answer\"}\n\n"
    "data: {\"sources\": [...]}\n\n"
    "data: [DONE]\n\n"

  The \n\n at the end is required by the SSE spec — it signals "end of event."
  The frontend's ReadableStream reader splits on \n and looks for "data: " prefix.

  WHY SSE over WebSockets?
    SSE is simpler — it's one-directional (server → client) which is all we need.
    WebSockets are bidirectional and require more setup.
    For streaming text responses, SSE is the right tool.
"""

import json
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from core.vectorstore import search_similar_chunks
from core.llm import stream_answer
from models.schemas import ChatRequest, HealthResponse
import os

router = APIRouter()


@router.post("/chat")
async def chat(request: ChatRequest):
    """
    Handles a chat message using the RAG pipeline.

    Steps:
      1. Validate the request
      2. Search Chroma for relevant chunks
      3. Stream the LLM response back as SSE
    """

    # ── Retrieve Relevant Chunks ──────────────────────────────────────────────
    try:
        chunks = search_similar_chunks(
            document_id=request.document_id,
            query=request.question,
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        print(f"ERROR during retrieval: {e}")
        raise HTTPException(status_code=500, detail="Failed to search the document.")

    if not chunks:
        raise HTTPException(
            status_code=404,
            detail="No relevant content found for this question."
        )

    # ── Async Generator for SSE Stream ───────────────────────────────────────
    #
    # This is an async generator function — it yields values asynchronously.
    # StreamingResponse iterates over it and sends each yielded string to the client.
    #
    # The `async for ... in stream_answer(...)` loop is the key:
    # stream_answer() itself is an async generator (see llm.py).
    # We iterate over its tokens and re-yield them as SSE-formatted strings.

    async def event_stream():
        try:
            full_response = ""

            # Stream tokens from the LLM one by one
            async for token in stream_answer(
                question=request.question,
                chunks=chunks,
                history=[{"role": m.role, "content": m.content} for m in (request.history or [])],
            ):
                full_response += token

                # Format as SSE event and yield
                # json.dumps ensures special characters are properly escaped
                yield f"data: {json.dumps({'token': token})}\n\n"

            # After all tokens are sent, send the source chunks.
            # We send sources AFTER the text so the text starts appearing immediately.
            sources_payload = [
                {"content": c["content"], "page": c["page"], "score": c["score"]}
                for c in chunks
            ]
            yield f"data: {json.dumps({'sources': sources_payload})}\n\n"

            # Final [DONE] signal tells the frontend the stream is complete
            yield "data: [DONE]\n\n"

        except Exception as e:
            # If something goes wrong mid-stream, send an error event
            # The frontend handles this in the onError callback
            print(f"ERROR during streaming: {e}")
            yield f"data: {json.dumps({'error': str(e)})}\n\n"
            yield "data: [DONE]\n\n"

    # StreamingResponse takes the async generator and:
    #   - Keeps the HTTP connection open
    #   - Sends each yielded chunk immediately
    #   - Closes the connection when the generator is exhausted
    #
    # media_type="text/event-stream" is the MIME type for SSE.
    # The frontend's fetch() call sets Accept: text/event-stream to match.
    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            # These headers disable caching — important for streaming responses
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            # This header is sometimes needed to prevent nginx from buffering the stream
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/health", response_model=HealthResponse)
async def health_check():
    """
    Returns backend health status.
    The frontend pings this at startup to verify the backend is running.
    """
    from core.embeddings import get_embedding_model, EMBEDDING_MODEL_NAME
    from core.vectorstore import get_store_stats

    # Check embedding model
    try:
        get_embedding_model()
        embedding_status = f"{EMBEDDING_MODEL_NAME} (loaded)"
    except Exception as e:
        embedding_status = f"ERROR: {e}"

    # Check vector store
    try:
        stats = get_store_stats()
        chroma_status = f"OK ({stats['documents_loaded']} documents in memory)"
    except Exception as e:
        chroma_status = f"ERROR: {e}"

    return HealthResponse(
        status="ok",
        embedding_model=embedding_status,
        chroma_status=chroma_status,
    )
