# FILE: src/tools/ingest_manuals.py
from __future__ import annotations

import os
from pathlib import Path
from typing import List

import fitz  # PyMuPDF
import numpy as np
from sentence_transformers import SentenceTransformer

from tools.rag_store import ChromaStore, ChromaStoreConfig


def pdf_to_text(pdf_path: Path) -> List[str]:
    """Extract plain text from all pages of a PDF."""
    doc = fitz.open(str(pdf_path))
    pages: List[str] = []
    for page in doc:
        txt = page.get_text("text") or ""
        pages.append(txt)
    return pages


def simple_chunk(page_text: str, chunk_size: int = 800, overlap: int = 80) -> List[str]:
    """Simple character-based sliding window chunker."""
    chunks: List[str] = []
    i = 0
    n = len(page_text)
    while i < n:
        chunks.append(page_text[i : i + chunk_size])
        i += max(1, chunk_size - overlap)
    return chunks


def ingest_pdf(pdf_path: Path, model: SentenceTransformer, store: ChromaStore) -> int:
    """Ingest a single PDF into the Chroma collection."""
    pages = pdf_to_text(pdf_path)
    ids: List[str] = []
    texts: List[str] = []

    for pidx, ptxt in enumerate(pages, start=1):
        chunks = simple_chunk(ptxt)
        for cidx, chunk in enumerate(chunks, start=1):
            ids.append(f"{pdf_path.name}-p{pidx}-c{cidx}")
            texts.append(f"[p{pidx}] {chunk}")

    if not texts:
        print(f"[ingest_manuals] No text extracted from {pdf_path}")
        return 0

    embs = model.encode(texts, batch_size=32, convert_to_numpy=True)
    store.add(ids, texts, embs)
    print(f"[ingest_manuals] Ingested {len(texts)} chunks from {pdf_path.name}")
    return len(texts)


def main() -> None:
    # project root = src/..
    root = Path(__file__).resolve().parents[2]
    docs_dir = Path(os.getenv("RAG_DOCS_DIR", root / "docs" / "manuals"))
    chroma_dir = Path(os.getenv("CHROMA_DIR", root / "runtime_cache" / "chroma"))
    embedding_model = os.getenv(
        "RAG_EMBEDDING_MODEL",
        "sentence-transformers/all-MiniLM-L6-v2",
    )

    docs_dir.mkdir(parents=True, exist_ok=True)
    chroma_dir.mkdir(parents=True, exist_ok=True)

    print(f"[ingest_manuals] Using docs_dir={docs_dir}")
    print(f"[ingest_manuals] Using chroma_dir={chroma_dir}")
    print(f"[ingest_manuals] Using embedding_model={embedding_model}")

    model = SentenceTransformer(embedding_model)
    store = ChromaStore(
        ChromaStoreConfig(persist_dir=chroma_dir, collection_name="manual")
    )

    pdf_files = list(docs_dir.glob("*.pdf"))
    if not pdf_files:
        print(
            "[ingest_manuals] No PDF files found. Put manuals under docs/manuals/*.pdf"
        )
        return

    total = 0
    for pdf_path in pdf_files:
        total += ingest_pdf(pdf_path, model, store)

    print(f"[ingest_manuals] Total ingested chunks: {total}")


if __name__ == "__main__":
    main()
