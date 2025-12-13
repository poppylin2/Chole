# -*- coding: utf-8 -*-
"""
Export the defects_daily table to CSV.
- By default reads data.sqlite in the project root; override via DB_PATH.
- By default writes defects_daily_export.csv in the project root; override via OUT_PATH.
"""

from __future__ import annotations

import csv
import os
import sqlite3
from pathlib import Path


def export_defects_daily(db_path: Path, out_path: Path) -> None:
    conn = sqlite3.connect(str(db_path))
    try:
        cur = conn.execute("SELECT * FROM defects_daily")
        rows = cur.fetchall()
        headers = [col[0] for col in cur.description]
    finally:
        conn.close()

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(headers)
        writer.writerows(rows)


def main() -> None:
    root = Path(__file__).resolve().parent
    db_path = Path(os.getenv("DB_PATH", root / "data.sqlite"))
    out_path = Path(os.getenv("OUT_PATH", root / "defects_daily_export.csv"))

    print("Step 1: Prepare paths")
    print(f"- Database: {db_path}")
    print(f"- Output file: {out_path}")

    if not db_path.exists():
        print("Error: database file not found. Check DB_PATH or ensure data.sqlite exists.")
        return

    print("\nStep 2: Export defects_daily -> CSV")
    export_defects_daily(db_path, out_path)
    print("Done!")


if __name__ == "__main__":
    main()
