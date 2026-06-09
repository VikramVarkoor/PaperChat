from __future__ import annotations

"""
core/vectorstore.py — Chroma Vector Database Operations

This is the "memory" of PaperChat. After a PDF is chunked and embedded,
we store everything here. When a user asks a question, we search here.

WHAT IS A VECTOR DATABASE?
  A regular database (like PostgreSQL) stores data and lets you search by
  exact values: WHERE name = 'John' or WHERE age > 25.

  A vector database stores data AND its embedding vectors, and lets you search
  by SEMANTIC SIMILARITY: "find me the 4 records most similar in meaning to X."

  This is fundamentally different — you're searching by meaning, not by keywords.
  That's what makes RAG smart: it finds relevant chunks even if the question
  uses completely different words than the document.

CHROMA CONCEPTS:
  Collection: like a database table — stores chunks for ONE document.
              We create one collection per uploaded document.

  Document:   in Chroma's terminology, a "document" is one chunk of text.
              Confusing naming (they call chunks "documents"), but that's Chroma's API.

  Embedding:  the vector representation of each chunk, stored alongside the text.

  Metadata:   extra info stored with each chunk (page number, chunk index, etc.)
              Retrieved alongside the text so we can show citations.

  ID:         a unique string identifier for each chunk within a collection.

  Query:      search the collection with an embedding vector.
              Returns the N most similar chunks (cosine similarity).
"""

import os
import uuid
import chromadb
from chromadb.config import Settings

from core.embeddings import embed_texts, embed_query

# ── Chroma Client (Singleton) ─────────────────────────────────────────────────

CHROMA_PERSIST_DIR = os.getenv("CHROMA_PERSIST_DIR", "./chroma_data")
TOP_K_RESULTS = int(os.getenv("TOP_K_RESULTS", 4))

# The Chroma client is the connection to the vector database.
# PersistentClient saves data to disk — it survives server restarts.
# (Without persistence, all indexed documents disappear on restart.)
_chroma_client: chromadb.PersistentClient | None = None


def get_chroma_client() -> chromadb.PersistentClient:
    """Returns the Chroma client, creating it on first call (singleton)."""
    global _chroma_client
    if _chroma_client is None:
        os.makedirs(CHROMA_PERSIST_DIR, exist_ok=True)
        _chroma_client = chromadb.PersistentClient(
            path=CHROMA_PERSIST_DIR,
            settings=Settings(anonymized_telemetry=False),  # No usage tracking
        )
    return _chroma_client


# ── Core Operations ───────────────────────────────────────────────────────────

def create_collection(document_id: str) -> chromadb.Collection:
    """
    Creates a new Chroma collection for a document.

    Each document gets its own collection, identified by the document_id.
    This makes it easy to:
      - Search within a specific document
      - Delete a document (just delete its collection)
      - Support multiple simultaneous documents in the future

    Args:
        document_id: Unique ID for the document (becomes collection name)

    Returns:
        The newly created Chroma collection object
    """
    client = get_chroma_client()

    # Delete existing collection if it exists (handles re-uploads of same doc)
    try:
        client.delete_collection(document_id)
    except Exception:
        pass  # Collection didn't exist, that's fine

    # `get_or_create_collection` is idempotent — safe to call multiple times.
    # cosine distance = 1 - cosine_similarity.
    # We use cosine because we normalized our embeddings in embed_texts().
    collection = client.get_or_create_collection(
        name=document_id,
        metadata={"hnsw:space": "cosine"},  # Tell Chroma to use cosine distance
    )
    return collection


def index_chunks(document_id: str, chunks: list[dict]) -> None:
    """
    Embeds all chunks and stores them in the Chroma collection.

    This is the most compute-intensive part of ingestion.
    For a 50-page PDF (~200 chunks), this takes about 5-10 seconds on CPU.

    Args:
        document_id: The document's collection name in Chroma
        chunks: List of {"content": str, "page": int} from ingestion.py
    """
    collection = create_collection(document_id)

    # Extract just the text for batch embedding
    texts = [chunk["content"] for chunk in chunks]

    # Embed all chunks at once (batch processing)
    print(f"Embedding {len(texts)} chunks...")
    embeddings = embed_texts(texts)
    print("Embedding complete.")

    # Generate unique IDs for each chunk
    # We use f-strings with chunk index: "doc_abc123_chunk_0", "doc_abc123_chunk_1", etc.
    ids = [f"{document_id}_chunk_{i}" for i in range(len(chunks))]

    # Metadata stored alongside each chunk — retrieved with search results
    # This is what powers the source citation feature
    metadatas = [
        {
            "page": chunk["page"],
            "chunk_index": i,
            "document_id": document_id,
        }
        for i, chunk in enumerate(chunks)
    ]

    # Chroma's add() stores everything at once.
    # `documents` = the text (what gets returned in results)
    # `embeddings` = the vectors (what gets searched)
    # `metadatas` = the extra info (page numbers, etc.)
    # `ids` = unique identifiers (required by Chroma)
    collection.add(
        documents=texts,
        embeddings=embeddings,
        metadatas=metadatas,
        ids=ids,
    )
    print(f"Indexed {len(chunks)} chunks into collection '{document_id}'")


def search_similar_chunks(document_id: str, query: str) -> list[dict]:
    """
    Finds the most semantically similar chunks to the user's query.

    This is the "R" in RAG — Retrieval.

    How it works:
      1. Embed the query into a vector
      2. Chroma computes cosine distance between the query vector
         and every chunk vector in the collection
      3. Returns the TOP_K_RESULTS closest chunks
      4. "Closest" in cosine space = most similar in meaning

    Args:
        document_id: Which document's collection to search
        query: The user's question as a plain string

    Returns:
        List of dicts: [{"content": str, "page": int, "score": float}, ...]
        Sorted by relevance (most relevant first).
    """
    client = get_chroma_client()

    # Get the collection for this document
    try:
        collection = client.get_collection(document_id)
    except Exception:
        raise ValueError(f"Document '{document_id}' not found. Please re-upload it.")

    # Embed the query
    query_embedding = embed_query(query)

    # Search! Chroma returns the n_results most similar chunks.
    results = collection.query(
        query_embeddings=[query_embedding],  # Must be a list of embeddings
        n_results=min(TOP_K_RESULTS, collection.count()),  # Can't request more than exist
        include=["documents", "metadatas", "distances"],
    )

    # Chroma returns nested lists (one per query — we only query once)
    # So we take [0] to get results for our single query
    documents = results["documents"][0]
    metadatas = results["metadatas"][0]
    distances = results["distances"][0]

    # Convert distance to similarity score
    # Chroma returns cosine DISTANCE (0 = identical, 2 = opposite)
    # We convert to cosine SIMILARITY (1 = identical, -1 = opposite)
    # by: similarity = 1 - distance
    chunks = []
    for doc, meta, distance in zip(documents, metadatas, distances):
        similarity_score = round(1 - distance, 4)
        chunks.append({
            "content": doc,
            "page": meta.get("page", 1),
            "score": max(0.0, similarity_score),  # Clamp to [0, 1]
        })

    return chunks


def delete_collection(document_id: str) -> bool:
    """
    Deletes a document's collection from Chroma.
    Called when the user clicks "New doc" in the frontend.

    Returns True if deleted, False if collection didn't exist.
    """
    client = get_chroma_client()
    try:
        client.delete_collection(document_id)
        print(f"Deleted collection '{document_id}'")
        return True
    except Exception:
        return False


def collection_exists(document_id: str) -> bool:
    """Checks if a collection exists (used for health checks)."""
    client = get_chroma_client()
    try:
        client.get_collection(document_id)
        return True
    except Exception:
        return False
