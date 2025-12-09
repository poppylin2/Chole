from __future__ import annotations

import csv
import re
import sqlite3
import uuid
from pathlib import Path
from typing import Any, Dict, List


def is_read_only_sql(sql: str) -> bool:
    """Check whether SQL appears to be a safe read-only query (SELECT/CTE)."""

    cleaned = normalize_sql(sql).lower()
    return cleaned.startswith("select") or cleaned.startswith("with")


def normalize_sql(sql: str) -> str:
    """Strip fences/comments and whitespace to validate and execute safely."""

    # Remove code fences like ```sql ... ``` or ``` ... ```
    sql = re.sub(r"^```\\w*\\s*", "", sql.strip(), flags=re.IGNORECASE)
    sql = re.sub(r"```$", "", sql.strip())

    # Remove leading line comments
    sql = re.sub(r"(?m)^\\s*--.*?$", "", sql)
    return sql.strip()


def ensure_limit(sql: str, max_limit: int) -> str:
    """Append a LIMIT clause if none present."""
    pattern = re.compile(r"\blimit\b", re.IGNORECASE)
    if not pattern.search(sql):
        return f"{sql.rstrip().rstrip(';')} LIMIT {max_limit};"
    return sql


def execute_sqlite_query(
    sql: str, db_path: Path, runtime_cache: Path, max_rows: int = 1000
) -> Dict[str, Any]:
    """Execute a read-only SQLite query and persist results to CSV."""

    sql = normalize_sql(sql)
    if not is_read_only_sql(sql):
        return {"status": "error", "error_message": "Only SELECT statements are allowed."}

    runtime_cache.mkdir(parents=True, exist_ok=True)

    safe_sql = ensure_limit(sql, max_rows)

    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute(safe_sql)
        rows = cursor.fetchall()
        columns = [col[0] for col in cursor.description] if cursor.description else []
        dataset_id = f"query_result_{uuid.uuid4().hex[:8]}"
        csv_path = runtime_cache / f"{dataset_id}.csv"

        with csv_path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            if columns:
                writer.writerow(columns)
            writer.writerows(rows)

        sample_preview: List[dict[str, Any]] = []
        for row in rows[:5]:
            sample_preview.append({col: val for col, val in zip(columns, row)})

        return {
            "status": "ok",
            "dataset_id": dataset_id,
            "csv_path": str(csv_path),
            "row_count": len(rows),
            "columns": columns,
            "sample_preview": sample_preview,
        }
    except sqlite3.Error as exc:
        return {"status": "error", "error_message": str(exc)}
    finally:
        try:
            conn.close()
        except Exception:
            pass
