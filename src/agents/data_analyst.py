from __future__ import annotations

import json
import re
import logging
from typing import Dict, List, Optional

from dataclasses import asdict

from langchain_openai import ChatOpenAI

from core.models import GraphState, StepResult, TableSchema
from tools.python_tool import run_python_analysis
from tools.sqlite_tool import execute_sqlite_query


SQL_AGENT_PROMPT = """
You are a data analyst focused on fab inspection data. Generate a safe, read-only SQL SELECT query.
Use provided schema; do not guess columns that do not exist.
Return JSON with keys: sql, reasoning.
Do not include explanations outside JSON.
Ensure the query has explicit column selections when possible and respects read-only constraints.
If a LIMIT is not provided it will be auto-applied.
"""

PYTHON_AGENT_PROMPT = """
You are a data analyst running Python on cached CSV datasets (pandas, numpy available).
Use the provided dataset mapping to load files.
Create useful metrics: trends, anomalies, correlations.
Save plots using save_plot() helper if needed and add paths to `plots` list.
Set `metrics` dict and optional `result` summary text.
Return only JSON with keys: code (string), rationale.
"""


def strip_code_fence(text: str) -> str:
    """Remove leading/trailing code fences (```sql / ```json / ```)."""
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```\\w*\\s*", "", text)
    if text.endswith("```"):
        text = text[: text.rfind("```")]
    return text.strip()


def extract_sql(text: str) -> str:
    """Extract SQL from JSON payloads or fenced code blocks."""
    cleaned = strip_code_fence(text)
    try:
        parsed = json.loads(cleaned)
        if isinstance(parsed, dict) and "sql" in parsed:
            return parsed["sql"]
    except Exception:
        pass

    fence = re.search(r"```sql(.*?)```", text, re.DOTALL | re.IGNORECASE)
    if fence:
        return fence.group(1).strip()
    return cleaned


def extract_code(text: str) -> str:
    """Extract Python code from JSON or fenced blocks."""
    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict) and "code" in parsed:
            return parsed["code"]
    except Exception:
        pass
    fence = re.search(r"```python(.*?)```", text, re.DOTALL | re.IGNORECASE)
    if fence:
        return fence.group(1).strip()
    return text.strip()


def data_analyst_node(llm: ChatOpenAI, db_path, runtime_cache, table_markdown_index: Dict[str, str], max_rows: int):
    """Build data analyst node callable."""

    logger: logging.Logger | None = runtime_cache and logging.getLogger("fab_agent")

    def _sql_state_update(state: GraphState, sql: str, reasoning: str) -> GraphState:
        summary = execute_sqlite_query(sql, db_path, runtime_cache, max_rows=max_rows)
        step_result: StepResult = {
            "step_id": state.get("next_action", {}).get("id", "sql"),
            "step_type": "sql_analysis",
            "summary": reasoning,
            "used_tables": state.get("next_action", {}).get("tables"),
        }

        if summary.get("status") == "ok":
            dataset_id = summary["dataset_id"]
            state.setdefault("data_artifacts", {})[dataset_id] = {
                "csv_path": summary["csv_path"],
                "row_count": summary.get("row_count", 0),
                "columns": summary.get("columns", []),
                "sample_preview": summary.get("sample_preview"),
            }
            step_result["dataset_id"] = dataset_id
            step_result["dataset_path"] = summary["csv_path"]
            step_result["summary"] = (
                reasoning
                + f"\nRows: {summary.get('row_count', 0)}, Columns: {summary.get('columns', [])}"
            )
        else:
            step_result["error"] = summary.get("error_message", "Unknown SQL error.")
            step_result["summary"] = reasoning or "SQL attempt failed."
            step_result["reasoning"] = f"SQL attempted: {sql[:500]}"

        if logger:
            logger.info(
                "[data_analyst][sql] step_id=%s status=%s rows=%s tables=%s error=%s sql=%s",
                step_result["step_id"],
                summary.get("status"),
                summary.get("row_count"),
                step_result.get("used_tables"),
                summary.get("error_message"),
                sql[:200].replace("\n", " "),
            )
        state.setdefault("step_results", []).append(step_result)
        state["next_action"] = None
        return state

    def _python_state_update(state: GraphState, code: str, rationale: str) -> GraphState:
        datasets = {k: v["csv_path"] for k, v in state.get("data_artifacts", {}).items()}
        analysis_result = run_python_analysis(code, datasets, runtime_cache)

        step_result: StepResult = {
            "step_id": state.get("next_action", {}).get("id", "python"),
            "step_type": "python_analysis",
            "summary": rationale,
        }

        if analysis_result.get("status") == "ok":
            step_result["summary"] = f"{rationale}\n{analysis_result.get('summary_text','')}"
            step_result["metrics"] = analysis_result.get("metrics")
            step_result["plots"] = analysis_result.get("plot_paths")
        else:
            step_result["error"] = analysis_result.get("error_message", "Python execution failed.")

        if logger:
            logger.info(
                "[data_analyst][python] step_id=%s status=%s plots=%s error=%s",
                step_result["step_id"],
                analysis_result.get("status"),
                analysis_result.get("plot_paths"),
                analysis_result.get("error_message"),
            )
        state.setdefault("step_results", []).append(step_result)
        state["next_action"] = None
        return state

    def _node(state: GraphState) -> GraphState:
        action = state.get("next_action") or {}
        action_type = action.get("action_type")
        if action_type not in {"sql_analysis", "python_analysis"}:
            return state

        tables = action.get("tables") or []
        table_descriptions: List[TableSchema] = (
            [t for t in state.get("database_schema", {}).tables if t.name in tables]  # type: ignore
            if hasattr(state.get("database_schema", None), "tables")
            else []
        )

        table_notes = "\n".join(table_markdown_index.get(t, "") for t in tables if t in table_markdown_index)

        if action_type == "sql_analysis":
            messages = [
                {"role": "system", "content": SQL_AGENT_PROMPT},
                {
                    "role": "user",
                    "content": json.dumps(
                        {
                            "action": action,
                            "schema": [asdict(t) for t in table_descriptions],
                            "table_notes": table_notes,
                        }
                    ),
                },
            ]
            response = llm.invoke(messages)
            raw_llm = getattr(response, "content", "") or ""
            sql = extract_sql(raw_llm)
            reasoning = "SQL generated based on schema."
            try:
                parsed = json.loads(strip_code_fence(raw_llm))
                reasoning = parsed.get("reasoning", reasoning)
            except Exception:
                pass
            state.setdefault("step_results", [])
            # record raw llm content in the step result downstream
            updated_state = _sql_state_update(state, sql, reasoning)
            if updated_state.get("step_results"):
                updated_state["step_results"][-1]["raw_llm"] = raw_llm
            if logger:
                logger.info("[data_analyst][sql][llm] %s", raw_llm[:500].replace("\n", " "))
            return updated_state

        # python_analysis
        datasets = {k: v["csv_path"] for k, v in state.get("data_artifacts", {}).items()}
        messages = [
            {"role": "system", "content": PYTHON_AGENT_PROMPT},
            {
                "role": "user",
                "content": json.dumps({"action": action, "datasets": datasets}),
            },
        ]
        response = llm.invoke(messages)
        raw_llm = getattr(response, "content", "") or ""
        code = extract_code(raw_llm)
        rationale = "Python analysis generated."
        try:
            parsed = json.loads(strip_code_fence(raw_llm))
            rationale = parsed.get("rationale", rationale)
        except Exception:
            pass
        updated_state = _python_state_update(state, code, rationale)
        if updated_state.get("step_results"):
            updated_state["step_results"][-1]["raw_llm"] = raw_llm
        if logger:
            logger.info("[data_analyst][python][llm] %s", raw_llm[:500].replace("\n", " "))
        return updated_state

    return _node
