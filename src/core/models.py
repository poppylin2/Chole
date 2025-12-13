from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Dict, List, Literal, NotRequired, Optional, TypedDict


@dataclass
class ColumnSchema:
    name: str
    data_type: str
    not_null: bool
    primary_key: bool
    default_value: Optional[str] = None


@dataclass
class TableSchema:
    name: str
    columns: List[ColumnSchema]


@dataclass
class DatabaseSchema:
    tables: List[TableSchema]

    def to_dict(self) -> Dict[str, Any]:
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

    # ★ Key fix: put small, real query rows here so LLM can cite evidence.
    preview_rows: Optional[List[Dict[str, Any]]]
    # If dataset is small, we can include more rows (capped).
    rows: Optional[List[Dict[str, Any]]]

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

    # ★ Custom payload for deterministic SQL templates
    tool: Optional[str]
    date_from: Optional[str]  # YYYY-MM-DD
    date_to: Optional[str]  # YYYY-MM-DD
    chart_type_hint: Optional[str]


class GraphState(TypedDict, total=False):
    user_query: str
    database_schema: DatabaseSchema
    markdown_knowledge: str
    table_markdown_index: Dict[str, str]
    # ★ optional recent chat history for multi-turn context (role/content only)
    chat_history: List[Dict[str, str]]
    # ★ remember last confirmed tool to avoid repeated clarifications
    last_tool: str

    next_action: Optional[NextAction]
    # ★ deterministic plan queue
    action_queue: List[NextAction]

    step_results: List[StepResult]
    data_artifacts: Dict[str, DatasetArtifact]

    pending_clarification: Optional[ClarificationRequest]
    clarification_answers: Dict[str, str]

    final_answer: Optional[str]
    loop_count: int
