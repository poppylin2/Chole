from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Dict, List, Literal, NotRequired, Optional, TypedDict


@dataclass
class ColumnSchema:
    """Column metadata captured from SQLite introspection."""

    name: str
    data_type: str
    not_null: bool
    primary_key: bool
    default_value: Optional[str] = None


@dataclass
class TableSchema:
    """Table metadata including column definitions."""

    name: str
    columns: List[ColumnSchema]


@dataclass
class DatabaseSchema:
    """Database schema container."""

    tables: List[TableSchema]

    def to_dict(self) -> Dict[str, Any]:
        """Convert schema to a JSON-serializable structure."""
        return {"tables": [asdict(table) for table in self.tables]}


class DatasetArtifact(TypedDict):
    csv_path: str
    row_count: int
    columns: List[str]
    sample_preview: NotRequired[List[Dict[str, Any]]]


class StepResult(TypedDict, total=False):
    step_id: str
    step_type: Literal[
        "sql_analysis",
        "python_analysis",
        "domain_explain",
        "rag_qa",
        "visualize",
        "ask_user",
        "finish",
    ]
    summary: str
    dataset_id: Optional[str]
    dataset_path: Optional[str]
    metrics: Optional[Dict[str, Any]]
    plots: Optional[List[str]]
    error: Optional[str]
    used_tables: Optional[List[str]]
    reasoning: Optional[str]
    raw_llm: Optional[str]


class ClarificationRequest(TypedDict):
    id: str
    question: str


class NextAction(TypedDict, total=False):
    action_type: Literal[
        "sql_analysis",
        "python_analysis",
        "domain_explain",
        "rag_qa",
        "visualize",
        "ask_user",
        "finish",
    ]
    id: str
    description: str
    tables: Optional[List[str]]
    target_dataset_id: Optional[str]
    clarification_question: Optional[str]


class GraphState(TypedDict, total=False):
    """Shared LangGraph state."""

    user_query: str
    database_schema: DatabaseSchema
    markdown_knowledge: str
    table_markdown_index: Dict[str, str]
    next_action: Optional[NextAction]
    step_results: List[StepResult]
    data_artifacts: Dict[str, DatasetArtifact]
    pending_clarification: Optional[ClarificationRequest]
    clarification_answers: Dict[str, str]
    final_answer: Optional[str]
    loop_count: int
