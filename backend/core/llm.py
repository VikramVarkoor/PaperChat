from __future__ import annotations

"""
core/llm.py — LLM Integration with Groq (Streaming)

This is the "G" in RAG — Generation.
After retrieval gives us the relevant chunks, we send them + the question
to the LLM which generates a natural language answer.

WHY GROQ?
  Groq runs LLMs on custom hardware called LPUs (Language Processing Units)
  instead of GPUs. They're optimised specifically for the sequential token
  generation that LLMs do, and they're absurdly fast — 500-800 tokens/second
  vs ~50-100 tokens/second on a typical GPU cloud.
  The free tier is generous: 14,400 requests/day, 30 req/min.
  Go to https://console.groq.com to get your key.

THE PROMPT STRUCTURE:
  We use a two-part prompt:

  1. System prompt: Sets the AI's persona and rules.
     "You are PaperChat. Answer ONLY from the context provided. Be concise."

  2. User prompt: Contains the actual context + question.
     "Context: [chunk1] [chunk2] [chunk3]\n\nQuestion: What is the main finding?"

  This structure is called "prompt injection" — we're injecting the retrieved
  context into the prompt at runtime. It's the core technique of RAG.

  The system prompt's "only use the context" instruction is critical.
  Without it, the LLM will happily answer from its training data, defeating
  the purpose of RAG (grounding answers in the actual document).

STREAMING:
  Instead of waiting for the full response, we stream tokens as they're generated.
  The Groq SDK returns an async generator — a function that `yield`s values
  one by one. We iterate over it and yield each token to the FastAPI router,
  which formats it as SSE and sends it to the browser.
"""

import os
from typing import AsyncGenerator

from groq import AsyncGroq

# ── Configuration ─────────────────────────────────────────────────────────────
LLM_MODEL = os.getenv("LLM_MODEL", "llama-3.3-70b-versatile")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

# ── Groq Client (Singleton) ───────────────────────────────────────────────────
_groq_client: AsyncGroq | None = None


def get_groq_client() -> AsyncGroq:
    """Returns the Groq async client, creating it on first call."""
    global _groq_client
    if _groq_client is None:
        if not GROQ_API_KEY:
            raise ValueError(
                "GROQ_API_KEY is not set. "
                "Get a free key at https://console.groq.com and add it to .env"
            )
        _groq_client = AsyncGroq(api_key=GROQ_API_KEY)
    return _groq_client


# ── Prompt Builder ────────────────────────────────────────────────────────────

def build_system_prompt() -> str:
    """
    The system prompt defines the AI's personality and rules.
    It's sent at the start of every conversation.

    Key rules we enforce:
    1. Only use the provided context — prevents hallucination
    2. Cite page numbers — helps users verify answers
    3. Admit when you don't know — honesty over fabrication
    4. Be concise — don't pad answers
    """
    return """You are PaperChat, an AI assistant that answers questions about documents.

RULES (follow these strictly):
1. Answer ONLY based on the context provided below. Do not use outside knowledge.
2. When possible, mention the page number where the information was found.
   Example: "According to page 3, ..."
3. If the context does not contain enough information to answer the question,
   say: "I couldn't find information about that in this document."
   Do NOT make up an answer.
4. Be concise and direct. Don't repeat the question back.
5. If the question asks for a summary, provide a structured, readable summary.

Format your responses clearly. Use paragraphs or bullet points as appropriate."""


def build_user_prompt(question: str, chunks: list[dict]) -> str:
    """
    Builds the user message that includes the retrieved context + question.

    Args:
        question: The user's question
        chunks: List of {"content": str, "page": int, "score": float}
                from vectorstore.search_similar_chunks()

    Returns:
        A formatted string that will be sent as the user message to the LLM.
    """
    # Format each chunk with its page number
    # This is what enables the AI to cite page numbers in its answers
    context_parts = []
    for i, chunk in enumerate(chunks, start=1):
        context_parts.append(
            f"[Source {i} — Page {chunk['page']}]\n{chunk['content']}"
        )

    context = "\n\n---\n\n".join(context_parts)

    return f"""CONTEXT FROM DOCUMENT:
{context}

---

QUESTION: {question}

Please answer the question using only the context provided above."""


# ── Streaming Generation ──────────────────────────────────────────────────────

async def stream_answer(
    question: str,
    chunks: list[dict],
    history: list[dict] | None = None,
) -> AsyncGenerator[str, None]:
    """
    Streams the LLM's answer token by token.

    This is an `async generator` function — it uses `yield` to produce
    values one at a time, asynchronously. The `yield` pauses the function
    and returns the value to the caller. Next time the caller asks for a
    value, the function resumes from where it left off.

    The router iterates over this generator and formats each token as
    an SSE event to send to the browser.

    Args:
        question: The user's question
        chunks: Retrieved source chunks from Chroma
        history: Previous conversation turns (optional)

    Yields:
        Token strings one by one as the LLM generates them
    """
    client = get_groq_client()

    # Build the messages array
    # OpenAI-compatible chat format: list of {"role": ..., "content": ...}
    messages = [{"role": "system", "content": build_system_prompt()}]

    # Add conversation history for context (last few turns)
    if history:
        for turn in history[-6:]:  # Max 6 history messages (3 turns)
            messages.append({"role": turn["role"], "content": turn["content"]})

    # Add the current user message (with context injected)
    messages.append({
        "role": "user",
        "content": build_user_prompt(question, chunks),
    })

    # Create a streaming chat completion request
    # `stream=True` tells Groq to send tokens as they're generated
    stream = await client.chat.completions.create(
        model=LLM_MODEL,
        messages=messages,
        stream=True,
        temperature=0.1,    # Low temperature = more focused, less creative
                             # 0.0 = deterministic, 1.0 = very random
                             # For document Q&A, we want accuracy over creativity
        max_tokens=1024,     # Cap the response length (prevents runaway outputs)
    )

    # Iterate over the streaming response
    # Each `chunk` is a delta (small piece) of the response
    async for chunk in stream:
        # The token text is nested in: chunk.choices[0].delta.content
        # It can be None for the first/last chunks (role assignments, stop reason)
        token = chunk.choices[0].delta.content
        if token is not None:
            yield token
