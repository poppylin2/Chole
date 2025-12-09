from __future__ import annotations

import glob
import re
import sqlite3
from pathlib import Path
from typing import Dict, Tuple

from .models import ColumnSchema, DatabaseSchema, TableSchema


def load_database_schema(db_path: Path) -> DatabaseSchema:
    """Introspect SQLite database schema and return structured metadata."""

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
                    default_value=str(col["dflt_value"]) if col["dflt_value"] is not None else None,
                )
            )
        table_schemas.append(TableSchema(name=table, columns=cols))

    conn.close()
    return DatabaseSchema(tables=table_schemas)


def load_markdown_knowledge(docs_path: Path) -> Tuple[str, Dict[str, str]]:
    """Load all Markdown files and build a naive table index."""

    all_md_paths = sorted(Path(p) for p in glob.glob(str(docs_path / "*.md")))
    contents: list[str] = []
    table_index: Dict[str, str] = {}

    for path in all_md_paths:
        text = path.read_text(encoding="utf-8")
        contents.append(f"# File: {path.name}\n{text}")

        # Simple pattern: headings like "## Table: table_name"
        for match in re.finditer(r"^##\s+Table:\s*(.+)$", text, flags=re.MULTILINE):
            table_name = match.group(1).strip()
            snippet = extract_table_section(text, match.start())
            table_index[table_name] = snippet

    return "\n\n".join(contents), table_index


def extract_table_section(text: str, start_idx: int) -> str:
    """Extract section text starting from a heading until the next heading."""

    rest = text[start_idx:]
    lines = rest.splitlines()
    captured: list[str] = []
    for line in lines[1:]:
        if line.startswith("#"):
            break
        captured.append(line)
    return "\n".join(captured).strip()
