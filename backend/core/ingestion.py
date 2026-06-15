"""
core/ingestion.py — PDF Text Extraction and Chunking

This is Step 1 of the RAG pipeline.

THE FULL PIPELINE:
  1. [THIS FILE] Extract text from PDF → split into chunks
  2. [embeddings.py] Convert each chunk to a vector embedding
  3. [vectorstore.py] Store the chunks + embeddings in Chroma
  4. [llm.py] At query time: embed the question, find similar chunks, generate answer

WHY CHUNK AT ALL?
  LLMs have a "context window" — a maximum amount of text they can process
  at once. For Llama 3.3 70B it's ~128,000 tokens (~96,000 words).
  That sounds like a lot, but:
    1. Sending a 300-page PDF in every request would be slow and expensive.
    2. More text = more distraction. Focused, relevant chunks give better answers.
    3. Embedding the whole doc as one vector loses precision.
       A 300-page doc has one "average" meaning; 600 chunks each have specific meanings.

  So we: split the doc into small chunks → embed each chunk → at query time,
  only retrieve the 4 most relevant chunks → send JUST those to the LLM.
  This is the core idea of Retrieval-Augmented Generation (RAG).

WHY OVERLAPPING CHUNKS?
  If we split with zero overlap, a sentence that spans a chunk boundary gets cut:
    Chunk 1: "...The main finding was that elevated cortisol levels"
    Chunk 2: "correlate strongly with poor sleep outcomes..."
  Neither chunk contains the complete thought. With overlap, the boundary
  sentence appears in BOTH chunks, so it's always retrievable in full.
"""

import os
import tempfile
from pathlib import Path
from typing import IO

import pdfplumber
from langchain_text_splitters import RecursiveCharacterTextSplitter

# ── Configuration (from .env) ─────────────────────────────────────────────────
CHUNK_SIZE = int(os.getenv("CHUNK_SIZE", 1500))
CHUNK_OVERLAP = int(os.getenv("CHUNK_OVERLAP", 200))


def extract_text_from_pdf(file: IO[bytes]) -> tuple[str, int]:
    """
    Extracts all text from a PDF file object.

    Uses pdfplumber which is the best open-source PDF text extractor.
    It handles:
      - Multi-column layouts
      - Tables (extracts cells in reading order)
      - Scanned PDFs (though quality depends on the scan)
      - PDFs with embedded fonts

    Args:
        file: A file-like object (from FastAPI's UploadFile)

    Returns:
        tuple of (full_text, page_count)
        full_text: All text joined with page separators
        page_count: Number of pages in the PDF
    """
    pages_text = []

    with pdfplumber.open(file) as pdf:
        page_count = len(pdf.pages)

        for page_num, page in enumerate(pdf.pages, start=1):
            # extract_text() returns None if the page has no extractable text
            # (e.g. a page that's just an image with no OCR)
            text = page.extract_text()

            if text and text.strip():
                # Add a page marker so we can track which chunk came from which page
                pages_text.append(f"[Page {page_num}]\n{text.strip()}")

    full_text = "\n\n".join(pages_text)
    return full_text, page_count


def chunk_text(full_text: str) -> list[dict]:
    """
    Splits extracted PDF text into overlapping chunks.

    We use LangChain's RecursiveCharacterTextSplitter, which is smarter
    than a simple fixed-size split. It tries to split at natural boundaries
    in this order of preference:
      1. Double newlines (paragraph breaks) — best, preserves full thoughts
      2. Single newlines (line breaks)
      3. Spaces (word boundaries)
      4. Individual characters (last resort, should rarely happen)

    This means chunks respect paragraph structure when possible.

    Args:
        full_text: The full extracted text from extract_text_from_pdf()

    Returns:
        List of dicts: [{"content": str, "page": int}, ...]
        Each dict is one chunk with its source page number.
    """
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=CHUNK_SIZE,
        chunk_overlap=CHUNK_OVERLAP,
        # These separators are tried in order. The splitter prefers the first one.
        separators=["\n\n", "\n", " ", ""],
        # `length_function` tells the splitter how to measure "size".
        # We use len() (character count) not token count because it's faster.
        # 1 token ≈ 4 characters in English, so 1500 chars ≈ 375 tokens.
        length_function=len,
    )

    raw_chunks = splitter.split_text(full_text)

    chunks = []
    for chunk in raw_chunks:
        # Try to detect which page this chunk came from by looking for
        # the [Page N] marker we inserted during extraction.
        page = _extract_page_number(chunk)
        chunks.append({
            "content": chunk,
            "page": page,
        })

    return chunks


def _extract_page_number(chunk_text: str) -> int:
    """
    Extracts the page number from a chunk by scanning for '[Page N]' markers.
    Returns the LAST page marker found in the chunk (since chunks can span pages).
    Returns 1 as a fallback if no marker is found.
    """
    import re
    # Find all [Page N] patterns in the chunk
    matches = re.findall(r'\[Page (\d+)\]', chunk_text)
    if matches:
        # Return the last page number found (most recent page in this chunk)
        return int(matches[-1])
    return 1  # Fallback


def process_pdf(file: IO[bytes]) -> tuple[list[dict], int]:
    """
    Full ingestion pipeline: extract → chunk.
    This is the function called by the upload router.

    Args:
        file: File-like object from FastAPI UploadFile

    Returns:
        tuple of (chunks, page_count)
        chunks: list of {"content": str, "page": int}
        page_count: total pages in the original PDF
    """
    # Step 1: Extract all text
    full_text, page_count = extract_text_from_pdf(file)

    if not full_text.strip():
        raise ValueError(
            "Could not extract any text from this PDF. "
            "It may be a scanned image PDF without OCR. "
            "Try a text-based PDF."
        )

    # Step 2: Split into chunks
    chunks = chunk_text(full_text)

    if not chunks:
        raise ValueError("Failed to create chunks from the extracted text.")

    return chunks, page_count
