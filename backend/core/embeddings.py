from __future__ import annotations

"""
core/embeddings.py — Vector Embeddings using Sentence Transformers

This is the key to how RAG "understands" meaning.

WHAT IS AN EMBEDDING?
  An embedding is a list of numbers (a vector) that represents the MEANING
  of a piece of text in a mathematical space.

  The magic: texts with similar MEANINGS end up with similar vectors,
  regardless of the exact words used.

  Examples:
    embed("The dog ran fast")       → [0.12, -0.34, 0.89, ...]
    embed("The puppy sprinted")     → [0.13, -0.33, 0.90, ...]  ← very similar!
    embed("The stock market fell")  → [-0.45, 0.12, -0.23, ...]  ← very different

  "all-MiniLM-L6-v2" produces 384-dimensional vectors.
  That means each text becomes a point in a 384-dimensional space.
  Semantically similar texts are "nearby" in that space.

HOW WE USE THIS IN RAG:
  Ingestion time:
    chunk1_text → embed() → [0.12, -0.34, ...] → stored in Chroma with chunk text

  Query time:
    "What is the main finding?" → embed() → [0.11, -0.35, ...] → search Chroma
    → Chroma finds the chunks whose vectors are CLOSEST to the question vector
    → Returns top 4 chunks → those become the LLM's context

WHY SENTENCE-TRANSFORMERS OVER OPENAI EMBEDDINGS?
  - Free forever (runs locally, no API calls)
  - No rate limits
  - Works offline
  - all-MiniLM-L6-v2 is nearly as good as OpenAI's text-embedding-ada-002
    for most use cases, at 0% of the cost

SINGLETON PATTERN:
  The model (~80MB) takes a few seconds to load into RAM.
  We use a module-level variable (_model) to ensure we only load it once.
  Every time get_embedding_model() is called, it returns the same object.
  This is called the Singleton pattern.
"""

import os
from functools import lru_cache
from sentence_transformers import SentenceTransformer

EMBEDDING_MODEL_NAME = os.getenv("EMBEDDING_MODEL", "all-MiniLM-L6-v2")

# Module-level cache — holds the loaded model after first call
_model: SentenceTransformer | None = None


def get_embedding_model() -> SentenceTransformer:
    """
    Returns the embedding model, loading it from disk on first call.

    Uses a simple module-level singleton. The `global` keyword lets us
    modify the module-level variable from inside a function.
    (In Python, you can READ global variables without `global`,
     but you need `global` to REASSIGN them.)
    """
    global _model

    if _model is None:
        print(f"Loading embedding model: {EMBEDDING_MODEL_NAME}")
        # On first call, this downloads the model from HuggingFace (~80MB)
        # and caches it at ~/.cache/huggingface/hub/
        # Subsequent runs load from disk cache in ~1-2 seconds.
        _model = SentenceTransformer(EMBEDDING_MODEL_NAME)
        print(f"Embedding model loaded. Dimension: {_model.get_sentence_embedding_dimension()}")

    return _model


def embed_texts(texts: list[str]) -> list[list[float]]:
    """
    Converts a list of text strings into embedding vectors.

    Processes in batch — much faster than embedding one text at a time
    because the GPU/CPU can parallelize the computation.

    Args:
        texts: List of strings to embed

    Returns:
        List of vectors. Each vector is a list of 384 floats.
        Output[i] is the embedding for Input[i].
    """
    model = get_embedding_model()

    # encode() returns a numpy array of shape (len(texts), 384)
    # .tolist() converts it to a regular Python list of lists
    # (Chroma expects plain Python lists, not numpy arrays)
    embeddings = model.encode(
        texts,
        batch_size=32,           # Process 32 texts at a time
        show_progress_bar=False, # Suppress tqdm output in production
        normalize_embeddings=True,  # L2 normalize so cosine similarity = dot product
                                    # Makes similarity search faster in Chroma
    )

    return embeddings.tolist()


def embed_query(query: str) -> list[float]:
    """
    Embeds a single query string.
    Used at search time when the user asks a question.

    Returns:
        A single vector (list of 384 floats)
    """
    return embed_texts([query])[0]
