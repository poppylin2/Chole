from pathlib import Path

from core.context_loader import load_database_schema, load_markdown_knowledge


def test_load_schema_missing_db(tmp_path: Path):
    schema = load_database_schema(tmp_path / "missing.sqlite")
    assert schema.tables == []


def test_load_markdown_empty(tmp_path: Path):
    knowledge, index = load_markdown_knowledge(tmp_path)
    assert knowledge == ""
    assert index == {}
