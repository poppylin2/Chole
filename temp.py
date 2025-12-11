import sqlite3
from pathlib import Path
from textwrap import indent

DB_PATH = Path("/Users/yz/Projects/GitHub/Chole/data.sqlite")


def main():
    if not DB_PATH.exists():
        raise FileNotFoundError(f"数据库不存在: {DB_PATH}")

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row  # Allow row access by column name
    cur = conn.cursor()

    # 1. Find all user tables (exclude system tables starting with sqlite_)
    cur.execute(
        """
        SELECT name
        FROM sqlite_master
        WHERE type='table'
          AND name NOT LIKE 'sqlite_%'
        ORDER BY name;
    """
    )
    tables = [row[0] for row in cur.fetchall()]

    if not tables:
        print("这个数据库里没有用户表。")
        return

    for table in tables:
        print("=" * 80)
        print(f"TABLE: {table}")
        print("-" * 80)

        # 2. Print schema using PRAGMA table_info
        cur.execute(f"PRAGMA table_info('{table}')")
        cols = cur.fetchall()
        if not cols:
            print("  (无法获取表结构，可能是视图或特殊对象)")
        else:
            print("Schema (column_name | type | notnull | default | pk):")
            for cid, name, col_type, notnull, dflt_value, pk in cols:
                print(f"  {name} | {col_type} | {notnull} | {dflt_value} | {pk}")

        print("-" * 80)

        # 3. Print one row of sample data
        try:
            cur.execute(f"SELECT * FROM '{table}' LIMIT 1")
            row = cur.fetchone()
        except Exception as e:
            print(f"查询 sample data 出错: {e}")
            continue

        if row is None:
            print("Sample row: <表中没有数据行>")
        else:
            print("Sample row:")
            # row is sqlite3.Row, so column names are available
            for col in row.keys():
                print(f"  {col} = {row[col]}")

        print()  # Blank line between tables

    conn.close()


if __name__ == "__main__":
    main()
