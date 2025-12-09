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


def load_config() -> AppConfig:
    """Load configuration from environment variables with safe defaults."""

    root = Path(__file__).resolve().parents[2]
    db_path = Path(os.getenv("DB_PATH", root / "data.sqlite"))
    docs_path = Path(os.getenv("DOCS_PATH", root / "docs"))
    runtime_cache = Path(os.getenv("RUNTIME_CACHE", root / "runtime_cache"))
    model = os.getenv("OPENAI_MODEL", "gpt-4.1")

    runtime_cache.mkdir(parents=True, exist_ok=True)

    return AppConfig(
        db_path=db_path,
        docs_path=docs_path,
        runtime_cache=runtime_cache,
        model=model,
    )
