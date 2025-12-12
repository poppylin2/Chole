from __future__ import annotations

import glob
import re
import sqlite3
from pathlib import Path
from typing import Dict, Tuple

from .models import ColumnSchema, DatabaseSchema, TableSchema


def load_database_schema(db_path: Path) -> DatabaseSchema:
    if not db_path.exists():
        return DatabaseSchema(tables=[])

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%';"
    )
    tables = [row["name"] for row in cursor.fetchall()]

    table_schemas: list[TableSchema] = []
    for table in tables:
        cursor.execute(f"PRAGMA table_info('{table}')")
        cols = []
        for col in cursor.fetchall():
            cols.append(
                ColumnSchema(
                    name=col["name"],
                    data_type=col["type"] or "",
                    not_null=bool(col["notnull"]),
                    primary_key=bool(col["pk"]),
                    default_value=(
                        str(col["dflt_value"])
                        if col["dflt_value"] is not None
                        else None
                    ),
                )
            )
        table_schemas.append(TableSchema(name=table, columns=cols))

    conn.close()
    return DatabaseSchema(tables=table_schemas)


def load_markdown_knowledge(docs_path: Path) -> Tuple[str, Dict[str, str]]:
    """
    Load all Markdown files and build a naive table index.

    Supports headings like:
      - "## Table: defects_daily"
      - "## 1. `defects_daily`"
      - "## `defects_daily`"
    """
    all_md_paths = sorted(Path(p) for p in glob.glob(str(docs_path / "*.md")))
    contents: list[str] = []
    table_index: Dict[str, str] = {}

    # Matches:
    #  - ## Table: defects_daily
    #  - ## 1. `defects_daily`
    #  - ## `defects_daily`
    heading_pat = re.compile(
        r"^##\s+(?:Table:\s*)?(?:\d+\.\s*)?`?([A-Za-z0-9_]+)`?\s*$",
        flags=re.MULTILINE,
    )

    for path in all_md_paths:
        text = path.read_text(encoding="utf-8")
        contents.append(f"# File: {path.name}\n{text}")

        for match in heading_pat.finditer(text):
            name = match.group(1).strip()
            # Heuristic: only index if the section looks like a table glossary section
            # (you can remove this if you want to index all headings)
            snippet = extract_table_section(text, match.start())
            if snippet:
                table_index[name] = snippet

    return "\n\n".join(contents), table_index


def extract_table_section(text: str, start_idx: int) -> str:
    rest = text[start_idx:]
    lines = rest.splitlines()
    captured: list[str] = []
    for line in lines[1:]:
        if line.startswith("#"):
            break
        captured.append(line)
    return "\n".join(captured).strip()
