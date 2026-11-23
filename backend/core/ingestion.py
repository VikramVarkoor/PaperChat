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

import bisect
import gc
import os
import re
import tempfile
from pathlib import Path
from typing import IO

import pdfplumber
from langchain_text_splitters import RecursiveCharacterTextSplitter

# ── Configuration (from .env) ─────────────────────────────────────────────────
CHUNK_SIZE = int(os.getenv("CHUNK_SIZE", 1500))
CHUNK_OVERLAP = int(os.getenv("CHUNK_OVERLAP", 200))

# Matches the "[Page N]" marker we insert in front of every page's text.
# Pages read per pass of the PDF. Small keeps peak memory low.
PAGES_PER_BATCH = 5

_PAGE_MARKER = re.compile(r"\[Page (\d+)\]")


def extract_text_from_pdf(file: IO[bytes], on_progress=None) -> tuple[str, int]:
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

    # Page count from a first, light open.
    with pdfplumber.open(file) as pdf:
        page_count = len(pdf.pages)

    # pdfplumber keeps every character and layout object of a page in memory
    # until the PDF is closed. On a long PDF that adds up to hundreds of MB
    # and gets a 512MB server killed. So read the PDF in small batches of
    # pages, closing and reopening between batches so memory is released.
    for start in range(1, page_count + 1, PAGES_PER_BATCH):
        batch = list(range(start, min(start + PAGES_PER_BATCH, page_count + 1)))
        file.seek(0)
        with pdfplumber.open(file, pages=batch) as pdf:
            for page_num, page in zip(batch, pdf.pages):
                # extract_text() returns None if the page has no extractable
                # text (e.g. an image-only page, we don't do OCR)
                text = page.extract_text()
                page.flush_cache()

                if text and text.strip():
                    # Page marker so we can track which chunk came from which page
                    pages_text.append(f"[Page {page_num}]\n{text.strip()}")

                if on_progress:
                    on_progress("extracting", page_num, page_count)
        gc.collect()

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
        # We measure size in characters, not tokens, because it's faster.
        # 1 token is roughly 4 characters in English, so 1500 chars is about 375 tokens.
        length_function=len,
        # Record where each chunk starts in full_text, so we can work out
        # its page exactly (see below).
        add_start_index=True,
    )

    docs = splitter.create_documents([full_text])

    # Position of every "[Page N]" marker in the full text, in order.
    marker_positions = []
    marker_pages = []
    for m in _PAGE_MARKER.finditer(full_text):
        marker_positions.append(m.start())
        marker_pages.append(int(m.group(1)))

    chunks = []
    for doc in docs:
        # A chunk's page is the page that was open where the chunk STARTS:
        # the last marker at or before its start offset. This also works for
        # chunks from the middle of a long page that contain no marker.
        start = doc.metadata.get("start_index", -1)
        if start >= 0 and marker_positions:
            idx = bisect.bisect_right(marker_positions, start) - 1
            page = marker_pages[idx] if idx >= 0 else marker_pages[0]
        else:
            # Offset unavailable: fall back to markers inside the chunk.
            page = _extract_page_number(doc.page_content)
        chunks.append({
            "content": doc.page_content,
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


def process_pdf(file: IO[bytes], on_progress=None) -> tuple[list[dict], int]:
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
    full_text, page_count = extract_text_from_pdf(file, on_progress)

    if not full_text.strip():
        raise ValueError(
            "Could not extract any text from this PDF. "
            "It may be a scanned image PDF without OCR. "
            "Try a text-based PDF."
        )

    # Step 2: Split into chunks
    if on_progress:
        on_progress("chunking", 0, 1)
    chunks = chunk_text(full_text)

    if not chunks:
        raise ValueError("Failed to create chunks from the extracted text.")

    return chunks, page_count
