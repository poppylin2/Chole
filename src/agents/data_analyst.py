from __future__ import annotations

import json
import logging
import re
from dataclasses import asdict
from pathlib import Path
from typing import Dict, List, Optional

import pandas as pd
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
Save plots using save_plot() helper if needed and add paths to `plots` list.
Set `metrics` dict and optional `result` summary text.
Return only JSON with keys: code (string), rationale.
"""

TOOL_ID_RE = re.compile(r"^8950XR-P[1-4]$", flags=re.IGNORECASE)


def strip_code_fence(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```\w*\s*", "", text, flags=re.IGNORECASE)
    if text.endswith("```"):
        text = text[: text.rfind("```")]
    return text.strip()


def extract_sql(text: str) -> str:
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


def _sanitize_tool(tool: str) -> Optional[str]:
    t = (tool or "").strip()
    if TOOL_ID_RE.fullmatch(t):
        return t.upper()
    return None


def _sql_defect_drift_weekly(tool: str) -> str:
    # analysis_end_date now uses the current system date
    return f"""
WITH params AS (
  SELECT
    date('now', 'localtime') AS end_date,
    date('now', 'localtime', '-6 day') AS this_start,
    date('now', 'localtime', '-13 day') AS last_start,
    date('now', 'localtime', '-7 day') AS last_end
),
weekly AS (
  SELECT
    d.tool,
    d.recipe,
    SUM(CASE
          WHEN date(d.date) BETWEEN (SELECT this_start FROM params) AND (SELECT end_date FROM params)
          THEN d.pre_defectwise_count ELSE 0 END
    ) AS this_sum,
    SUM(CASE
          WHEN date(d.date) BETWEEN (SELECT last_start FROM params) AND (SELECT last_end FROM params)
          THEN d.pre_defectwise_count ELSE 0 END
    ) AS last_sum
  FROM defects_daily d
  GROUP BY d.tool, d.recipe
),
calc AS (
  SELECT
    tool, recipe, this_sum, last_sum,
    CASE
      WHEN last_sum > 0 THEN abs(this_sum - last_sum) * 1.0 / last_sum
      ELSE NULL
    END AS diff_pct,
    CASE
      WHEN last_sum > 0 AND abs(this_sum - last_sum) * 1.0 / last_sum > 0.10 THEN 1
      ELSE 0
    END AS is_anom
  FROM weekly
),
recipe_k AS (
  SELECT
    recipe,
    SUM(CASE WHEN is_anom = 1 THEN 1 ELSE 0 END) AS k_anom
  FROM calc
  GROUP BY recipe
),
labeled AS (
  SELECT
    c.tool,
    c.recipe,
    c.this_sum,
    c.last_sum,
    c.diff_pct,
    rk.k_anom,
    CASE
      WHEN c.last_sum = 0 THEN 'UNKNOWN_BASELINE'
      WHEN c.is_anom = 0 THEN 'STABLE'
      WHEN rk.k_anom = 1 THEN 'TOOL_DRIFT'
      ELSE 'PROCESS_DRIFT'
    END AS drift_label
  FROM calc c
  JOIN recipe_k rk USING (recipe)
),
tool_status AS (
  SELECT
    tool,
    CASE WHEN SUM(CASE WHEN drift_label='TOOL_DRIFT' THEN 1 ELSE 0 END) > 0
      THEN 'UNHEALTHY' ELSE 'HEALTHY' END AS tool_health,
    SUM(CASE WHEN drift_label='TOOL_DRIFT' THEN 1 ELSE 0 END) AS tool_drift_recipe_count,
    SUM(CASE WHEN drift_label='UNKNOWN_BASELINE' THEN 1 ELSE 0 END) AS unknown_baseline_recipe_count
  FROM labeled
  GROUP BY tool
)
SELECT
  (SELECT end_date FROM params) AS analysis_end_date,
  (SELECT this_start FROM params) AS this_week_start,
  (SELECT end_date FROM params) AS this_week_end,
  (SELECT last_start FROM params) AS last_week_start,
  (SELECT last_end FROM params) AS last_week_end,

  l.tool,
  l.recipe,
  l.this_sum AS s_this_week,
  l.last_sum AS s_last_week,
  ROUND(l.diff_pct, 4) AS diff_pct,
  l.k_anom,
  l.drift_label,

  ts.tool_health,
  ts.tool_drift_recipe_count,
  ts.unknown_baseline_recipe_count
FROM labeled l
JOIN tool_status ts ON ts.tool = l.tool
WHERE l.tool = '{tool}'
ORDER BY
  CASE l.drift_label
    WHEN 'TOOL_DRIFT' THEN 3
    WHEN 'PROCESS_DRIFT' THEN 2
    WHEN 'UNKNOWN_BASELINE' THEN 1
    ELSE 0
  END DESC,
  l.recipe ASC;
""".strip()


def _sql_calibration_overdue(tool: str) -> str:
    return f"""
WITH params AS (
  SELECT date('now', 'localtime') AS end_date
)
SELECT
  (SELECT end_date FROM params) AS analysis_end_date,
  c.tool,
  c.subsystem,
  c.cal_name,
  c.last_cal_date,
  c.freq_days,
  date(c.last_cal_date, printf('+%d day', c.freq_days)) AS due_date,
  CASE
    WHEN date((SELECT end_date FROM params)) > date(c.last_cal_date, printf('+%d day', c.freq_days))
    THEN 1 ELSE 0
  END AS is_overdue
FROM calibrations c
WHERE c.tool = '{tool}'
ORDER BY is_overdue DESC, due_date ASC;
""".strip()


def _sql_stage_wc_weekly(tool: str) -> str:
    return f"""
WITH params AS (
  SELECT
    date('now', 'localtime') AS end_date,
    date('now', 'localtime', '-6 day') AS this_start
)
SELECT
  (SELECT end_date FROM params) AS analysis_end_date,
  (SELECT this_start FROM params) AS this_week_start,
  (SELECT end_date FROM params) AS this_week_end,

  w.tool,
  w.recipe,
  COUNT(*) AS wc_total,
  SUM(CASE WHEN abs(w.x) > 150 OR abs(w.y) > 150 THEN 1 ELSE 0 END) AS wc_abnormal,
  ROUND(
    CASE WHEN COUNT(*) = 0 THEN 0 ELSE 1.0 * SUM(CASE WHEN abs(w.x) > 150 OR abs(w.y) > 150 THEN 1 ELSE 0 END) / COUNT(*) END,
    4
  ) AS wc_abnormal_ratio
FROM wc_points w
WHERE w.tool = '{tool}'
  AND date(w.date) BETWEEN (SELECT this_start FROM params) AND (SELECT end_date FROM params)
GROUP BY w.tool, w.recipe
ORDER BY wc_abnormal_ratio DESC, wc_total DESC, w.recipe ASC;
""".strip()


def _sql_defect_trend_range(tool: str, date_from: str, date_to: str) -> str:
    return f"""
SELECT
  date(d.date) AS run_date,
  d.tool,
  d.recipe,
  SUM(d.pre_defectwise_count) AS total_defects,
  COUNT(*) AS total_rows
FROM defects_daily d
WHERE d.tool = '{tool}'
  AND date(d.date) BETWEEN date('{date_from}') AND date('{date_to}')
GROUP BY date(d.date), d.tool, d.recipe
ORDER BY run_date ASC;
""".strip()


def _load_rows_if_small(
    csv_path: str, row_count: int, cap: int = 50
) -> Optional[List[Dict]]:
    if row_count <= 0:
        return []
    if row_count > cap:
        return None
    try:
        df = pd.read_csv(csv_path)
        return df.to_dict(orient="records")
    except Exception:
        return None


def data_analyst_node(
    llm: ChatOpenAI,
    db_path,
    runtime_cache: Path,
    table_markdown_index: Dict[str, str],
    max_rows: int,
):
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
            csv_path = summary["csv_path"]
            row_count = summary.get("row_count", 0)

            state.setdefault("data_artifacts", {})[dataset_id] = {
                "csv_path": csv_path,
                "row_count": row_count,
                "columns": summary.get("columns", []),
                "sample_preview": summary.get("sample_preview"),
            }

            step_result["dataset_id"] = dataset_id
            step_result["dataset_path"] = csv_path
            step_result["preview_rows"] = summary.get("sample_preview")

            # ★ If the dataset is small, attach full rows (capped) so LLM can format a correct table.
            rows = _load_rows_if_small(csv_path, row_count, cap=50)
            if rows is not None:
                step_result["rows"] = rows

            step_result["summary"] = (
                reasoning
                + f"\nRows: {row_count}, Columns: {summary.get('columns', [])}"
            )
        else:
            step_result["error"] = summary.get("error_message", "Unknown SQL error.")
            step_result["summary"] = reasoning or "SQL attempt failed."
            step_result["reasoning"] = f"SQL attempted: {sql[:500]}"

        if logger:
            logger.info(
                "[data_analyst][sql] step_id=%s status=%s rows=%s tables=%s error=%s",
                step_result["step_id"],
                summary.get("status"),
                summary.get("row_count"),
                step_result.get("used_tables"),
                summary.get("error_message"),
            )

        state.setdefault("step_results", []).append(step_result)
        state["next_action"] = None
        return state

    def _python_state_update(
        state: GraphState, code: str, rationale: str
    ) -> GraphState:
        datasets = {
            k: v["csv_path"] for k, v in state.get("data_artifacts", {}).items()
        }
        analysis_result = run_python_analysis(code, datasets, runtime_cache)

        step_result: StepResult = {
            "step_id": state.get("next_action", {}).get("id", "python"),
            "step_type": "python_analysis",
            "summary": rationale,
        }

        if analysis_result.get("status") == "ok":
            step_result["summary"] = (
                f"{rationale}\n{analysis_result.get('summary_text','')}"
            )
            step_result["metrics"] = analysis_result.get("metrics")
            step_result["plots"] = analysis_result.get("plot_paths")
        else:
            step_result["error"] = analysis_result.get(
                "error_message", "Python execution failed."
            )

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

        # ---------------------------------------------------------
        # Deterministic SQL templates for the new 3-table rules
        # ---------------------------------------------------------
        if action_type == "sql_analysis":
            action_id = action.get("id", "")
            tool = _sanitize_tool(action.get("tool", "") or "")
            if action_id in {
                "defect_drift_weekly",
                "calibration_overdue",
                "stage_wc_weekly",
                "defect_trend_range",
            }:
                if not tool:
                    step_result: StepResult = {
                        "step_id": action_id or "sql",
                        "step_type": "sql_analysis",
                        "summary": "Missing or invalid tool id for deterministic analysis.",
                        "error": "Tool must be one of: 8950XR-P1/P2/P3/P4",
                    }
                    state.setdefault("step_results", []).append(step_result)
                    state["next_action"] = None
                    return state

                if action_id == "defect_drift_weekly":
                    sql = _sql_defect_drift_weekly(tool)
                    return _sql_state_update(
                        state,
                        sql,
                        "Computed weekly defect sums and drift labels per rules (defects_daily only).",
                    )

                if action_id == "calibration_overdue":
                    sql = _sql_calibration_overdue(tool)
                    return _sql_state_update(
                        state,
                        sql,
                        "Checked calibration due dates (supporting evidence only).",
                    )

                if action_id == "stage_wc_weekly":
                    sql = _sql_stage_wc_weekly(tool)
                    return _sql_state_update(
                        state,
                        sql,
                        "Summarized wafer-center abnormal ratio for this week (supporting evidence only).",
                    )

                if action_id == "defect_trend_range":
                    dfrom = (action.get("date_from") or "").strip()
                    dto = (action.get("date_to") or "").strip()
                    if not re.fullmatch(
                        r"\d{4}-\d{2}-\d{2}", dfrom
                    ) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", dto):
                        return _sql_state_update(
                            state,
                            "SELECT 1 AS error;",
                            "Invalid date range format; expected YYYY-MM-DD.",
                        )
                    sql = _sql_defect_trend_range(tool, dfrom, dto)
                    return _sql_state_update(
                        state, sql, "Fetched daily defect totals for plotting."
                    )

        # ---------------------------------------------------------
        # Generic LLM-driven paths (kept for other queries)
        # ---------------------------------------------------------
        tables = action.get("tables") or []
        db_schema = state.get("database_schema", None)
        if hasattr(db_schema, "tables"):
            if tables:
                table_descriptions = [t for t in db_schema.tables if t.name in tables]  # type: ignore
            else:
                table_descriptions = list(db_schema.tables)  # type: ignore
        else:
            table_descriptions = []

        if tables:
            table_notes = "\n".join(
                table_markdown_index.get(t, "") for t in tables if t in table_markdown_index
            )
        else:
            table_notes = "\n".join(table_markdown_index.values())

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
            updated_state = _sql_state_update(state, sql, reasoning)
            if updated_state.get("step_results"):
                updated_state["step_results"][-1]["raw_llm"] = raw_llm
            return updated_state

        # python_analysis
        datasets = {
            k: v["csv_path"] for k, v in state.get("data_artifacts", {}).items()
        }
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
        return updated_state

    return _node
