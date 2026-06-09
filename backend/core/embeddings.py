from __future__ import annotations

"""
core/embeddings.py — Vector Embeddings using FastEmbed (ONNX-based)

WHY WE SWITCHED FROM sentence-transformers TO fastembed:
  sentence-transformers requires PyTorch, which alone uses ~400-500MB RAM.
  On Render's free tier (512MB limit), loading PyTorch + the model = OOM crash.

  fastembed uses ONNX Runtime instead of PyTorch.
  ONNX is a lightweight inference engine — it runs the same models
  but with a fraction of the memory footprint (~80MB total).

WHAT IS AN EMBEDDING?
  An embedding is a list of numbers (a vector) that represents the MEANING
  of a piece of text in a mathematical space.

  The magic: texts with similar MEANINGS end up with similar vectors,
  regardless of the exact words used.

  Examples:
    embed("The dog ran fast")       → [0.12, -0.34, 0.89, ...]
    embed("The puppy sprinted")     → [0.13, -0.33, 0.90, ...]  ← very similar!
    embed("The stock market fell")  → [-0.45, 0.12, -0.23, ...]  ← very different

  We use BAAI/bge-small-en-v1.5 which produces 384-dimensional vectors.

HOW WE USE THIS IN RAG:
  Ingestion time:
    chunk_text → embed() → [0.12, -0.34, ...] → stored in Chroma

  Query time:
    "What is the main finding?" → embed() → [0.11, -0.35, ...] → search Chroma
    → Chroma finds the chunks whose vectors are CLOSEST to the question vector
    → Returns top 4 chunks → those become the LLM's context
"""

from fastembed import TextEmbedding

EMBEDDING_MODEL_NAME = "BAAI/bge-small-en-v1.5"

# Module-level singleton — loaded once, reused forever
_model: TextEmbedding | None = None


def get_embedding_model() -> TextEmbedding:
    """
    Returns the embedding model, loading it on first call.
    fastembed downloads the ONNX model (~40MB) on first use
    and caches it at ~/.cache/fastembed/
    """
    global _model

    if _model is None:
        print(f"Loading embedding model: {EMBEDDING_MODEL_NAME}")
        _model = TextEmbedding(EMBEDDING_MODEL_NAME)
        print("Embedding model loaded (ONNX, 384-dim).")

    return _model


def embed_texts(texts: list[str]) -> list[list[float]]:
    """
    Converts a list of text strings into embedding vectors.

    fastembed's embed() returns a generator of numpy arrays.
    We collect them all into a list and convert to plain Python lists
    (Chroma expects plain Python lists, not numpy arrays).

    Args:
        texts: List of strings to embed

    Returns:
        List of vectors. Each vector is a list of 384 floats.
    """
    model = get_embedding_model()
    embeddings = list(model.embed(texts))
    return [e.tolist() for e in embeddings]


def embed_query(query: str) -> list[float]:
    """
    Embeds a single query string.
    Used at search time when the user asks a question.

    Returns:
        A single vector (list of 384 floats)
    """
    return embed_texts([query])[0]
