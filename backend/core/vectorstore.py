from __future__ import annotations

"""
core/vectorstore.py — In-Memory Vector Store using NumPy

WHY WE DITCHED CHROMADB:
  ChromaDB is a full vector database with an HNSW index, persistence layer,
  telemetry, gRPC server, and many dependencies. That overhead consumed
  too much of Render's free 512MB RAM limit, causing OOM crashes.

  For our use case (one document, ~50-200 chunks, one user at a time),
  we don't need any of that complexity. NumPy is already installed as a
  fastembed dependency and is all we need.

HOW THIS WORKS:
  We keep a simple Python dict in memory:
    _store = {
      "doc_abc123": {
        "texts":      ["chunk 1 text", "chunk 2 text", ...],
        "embeddings": numpy array of shape (N, 384),
        "pages":      [1, 1, 2, 3, ...],
      }
    }

  To search, we:
    1. Embed the query → shape (384,)
    2. Compute cosine similarity between the query and every chunk embedding
       using matrix multiplication (fast, vectorized)
    3. Return the top-K chunks by similarity score

TRADE-OFFS vs ChromaDB:
  - No disk persistence: data disappears on server restart
    (acceptable since Render free tier restarts anyway)
  - No HNSW approximation: we do exact search (actually MORE accurate!)
    (fast enough for our scale — 200 chunks takes <1ms)
  - No overhead: ~0 extra memory beyond the embeddings themselves
"""

import numpy as np
from core.embeddings import embed_query
import os

TOP_K_RESULTS = int(os.getenv("TOP_K_RESULTS", "4"))

# In-memory store: document_id → stored data
_store: dict[str, dict] = {}


def index_chunks(document_id: str, chunks: list[dict]) -> None:
    """
    Embeds all chunks and stores them in memory.

    Args:
        document_id: Unique ID for this document (used as the key in _store)
        chunks: List of {"content": str, "page": int} dicts from ingestion.py
    """
    from core.embeddings import embed_texts

    texts = [chunk["content"] for chunk in chunks]
    pages = [chunk["page"] for chunk in chunks]

    print(f"Embedding {len(texts)} chunks...")
    embeddings = embed_texts(texts)
    print("Embedding complete.")

    # Store as numpy array for fast matrix ops during search
    embeddings_array = np.array(embeddings, dtype=np.float32)

    # L2-normalize so cosine similarity = dot product (faster search)
    norms = np.linalg.norm(embeddings_array, axis=1, keepdims=True)
    norms = np.where(norms == 0, 1.0, norms)  # Avoid division by zero
    embeddings_array = embeddings_array / norms

    _store[document_id] = {
        "texts": texts,
        "embeddings": embeddings_array,
        "pages": pages,
    }
    print(f"Indexed {len(chunks)} chunks for document '{document_id}'")


def search_similar_chunks(document_id: str, query: str) -> list[dict]:
    """
    Finds the most semantically similar chunks to the user's query.

    This is the "R" in RAG — Retrieval.

    How it works:
      1. Embed the query into a 384-dim vector
      2. Normalize it (so dot product = cosine similarity)
      3. Compute dot product with every chunk embedding (matrix multiply)
      4. Sort by score, return top K

    Args:
        document_id: Which document to search
        query: The user's question as a plain string

    Returns:
        List of dicts: [{"content": str, "page": int, "score": float}, ...]
        Sorted by relevance (most relevant first).
    """
    if document_id not in _store:
        raise ValueError(f"Document '{document_id}' not found. Please re-upload it.")

    data = _store[document_id]
    texts = data["texts"]
    embeddings = data["embeddings"]   # shape: (N, 384), already normalized
    pages = data["pages"]

    # Embed and normalize the query
    query_vec = np.array(embed_query(query), dtype=np.float32)
    query_norm = np.linalg.norm(query_vec)
    if query_norm > 0:
        query_vec = query_vec / query_norm

    # Cosine similarity = dot product (since vectors are already normalized)
    # Result shape: (N,) — one similarity score per chunk
    similarities = embeddings @ query_vec

    # Get top-K indices sorted by similarity (descending)
    k = min(TOP_K_RESULTS, len(texts))
    top_indices = np.argsort(similarities)[::-1][:k]

    results = []
    for idx in top_indices:
        results.append({
            "content": texts[idx],
            "page": pages[idx],
            "score": round(float(similarities[idx]), 4),
        })

    return results


def delete_collection(document_id: str) -> bool:
    """
    Removes a document from the in-memory store.
    Called when the user uploads a new document.

    Returns True if deleted, False if it didn't exist.
    """
    if document_id in _store:
        del _store[document_id]
        print(f"Deleted document '{document_id}' from store")
        return True
    return False


def collection_exists(document_id: str) -> bool:
    """Checks if a document is loaded in memory."""
    return document_id in _store


def get_store_stats() -> dict:
    """Returns stats about what's currently in memory (for health checks)."""
    return {
        "documents_loaded": len(_store),
        "document_ids": list(_store.keys()),
    }
