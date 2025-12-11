from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass
class AppConfig:
    """Runtime configuration loaded from environment variables."""

    db_path: Path
    docs_path: Path
    runtime_cache: Path
    model: str
    max_sql_rows: int = 1000

    # ★ Added: RAG settings
    chroma_dir: Path | None = None
    rag_embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"


def load_config() -> AppConfig:
    """Load configuration from environment variables with safe defaults."""

    root = Path(__file__).resolve().parents[2]
    db_path = Path(os.getenv("DB_PATH", root / "data.sqlite"))
    docs_path = Path(os.getenv("DOCS_PATH", root / "docs"))
    runtime_cache = Path(os.getenv("RUNTIME_CACHE", root / "runtime_cache"))
    model = os.getenv("OPENAI_MODEL", "gpt-4.1-mini")

    runtime_cache.mkdir(parents=True, exist_ok=True)

    # ★ Added: RAG chroma path & model
    chroma_dir = Path(os.getenv("CHROMA_DIR", runtime_cache / "chroma"))
    chroma_dir.mkdir(parents=True, exist_ok=True)
    rag_embedding_model = os.getenv(
        "RAG_EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2"
    )

    return AppConfig(
        db_path=db_path,
        docs_path=docs_path,
        runtime_cache=runtime_cache,
        model=model,
        max_sql_rows=1000,
        chroma_dir=chroma_dir,
        rag_embedding_model=rag_embedding_model,
    )
