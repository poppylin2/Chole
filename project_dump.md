# Project Source Dump

Generated at: 2025-12-09 03:10:26 -08:00


==============================
FILE: docs\eqp_knowledge.md
==============================

```markdown
# Equipment Knowledge (Compact)

## 1. Tools

- Four tools: `8950XR-P1`, `8950XR-P2`, `8950XR-P3`, `8950XR-P4`.
- Same platform, same recipes; health can differ per tool.

### System vs Tool

- In this agent, **one physical tool = one "system"**.
- When a user asks "How's the system health?", it should be interpreted as
  "How is the health of a specific tool (e.g. `8950XR-P2`)?"
- The agent **must not** silently aggregate across all tools when answering
  a "system health" question.
- If the user does **not** specify which tool (tool_id) they mean, the agent
  should first ask:
  > Which tool do you want me to check? (8950XR-P1, 8950XR-P2, 8950XR-P3, 8950XR-P4)

## 2. Subsystems

Each tool has 4 subsystems:

1. `STAGE`  
   - Wafer handling & positioning (X/Y, rotation).
   - Metrics: `STAGE_POS_X`, `STAGE_POS_Y` in `subsystem_health_metrics`.
   - Spec: `spec_low`, `spec_high` (e.g. [-150, 150]).
   - Status: `OK` / `WARN` / `ALERT`.
   - Out-of-spec values or `WARN/ALERT` = sign of mechanical/position issues.

2. `CAMERA`  
   - Image acquisition.
   - Issues → false defects, missed defects (conceptual, not explicitly modeled).

3. `FOCUS`  
   - Controls focal plane.
   - Poor focus → blur → defect misclassification (conceptual).

4. `ILLUMINATION`  
   - Light source / illumination control.
   - Calibrated via `Illumination` calibration type.

## 3. Calibration Types

From `calibration_runs.calib_type`:

- `PrealignerToStage`  
  - Aligns prealigner to stage coordinates.  
  - Overdue + tool anomalies → strong tool-drift evidence.

- `GantryOffset`  
  - Aligns optics/gantry to stage.

- `ChuckCenterTheta`  
  - Calibrates chuck center and rotation.

- `Illumination`  
  - Calibrates illumination system.

Each record has:
- `next_due_time`: overdue if `< now`.
- `status`: `PASSED` / `FAILED`.

## 4. Linking Behavior to Drift

- **Tool Drift pattern**:
  - One tool shows high anomaly ratio on recipe R.
  - Other tools on R look normal.
  - Often combined with overdue calibration and/or STAGE metrics out-of-spec.

- **Process Drift pattern**:
  - Many tools show anomalies on the same recipe R.
  - Calibrations and STAGE metrics mostly healthy.
  - Suggests recipe/process-level issue.

The dataset is synthetic but encodes:
- Tool drift: `8950XR-P2` on `S13Layer` (high defect, STAGE issues).
- Process drift: `WadiLayer` across multiple tools (align issues).


```


==============================
FILE: docs\fab_defect_rules.md
==============================

```markdown
# Defect & Drift Rules (Compact)

## 1. Time Window
- Use latest `inspection_runs.start_time` as `window_end`.
- `window_start = window_end - 24h` (or other configured window).
- All analysis only uses runs in `[window_start, window_end]`.

## 2. Run-Level Anomaly

### High Defect
A run is high-defect if:
- `defect_count_total > DEFECT_HIGH_THRESHOLD` (default 50), OR
- `run_result = 'HIGH_DEFECT'`.

### Alignment Failure
A run has align fail if:
- `run_time_align_fail > 0`, OR
- `run_result = 'ALIGN_FAIL'`.

## 3. Per (tool, recipe) Aggregation

For each `(tool_id, recipe_id)` in the window:

- `total_runs`
- `abnormal_defect_runs` = count of high-defect runs
- `abnormal_align_runs` = count of align-fail runs

Ratios:

- `defect_anomaly_ratio = abnormal_defect_runs / total_runs`
- `align_anomaly_ratio  = abnormal_align_runs / total_runs`
- If `total_runs = 0` → ratios = 0.

## 4. Status Threshold

Global ratio threshold:

- `ANOMALY_RATIO_THRESHOLD = 0.05` (5%)

Status:

- `DEFECT_STATUS = HIGH` if `defect_anomaly_ratio > threshold`, else `NORMAL`.
- `ALIGN_STATUS = HIGH` if `align_anomaly_ratio  > threshold`, else `NORMAL`.

A **problem pair** is any `(tool, recipe)` where
- `DEFECT_STATUS = HIGH` OR `ALIGN_STATUS = HIGH`.

If all pairs are NORMAL → system is overall healthy (in this dimension).

## 5. Drift Type (Tool vs Process)

For a problem pair `(tool = T*, recipe = R)`:

1. Compute status for all tools on recipe `R`.
2. Mark each tool abnormal on `R` if:
   - `DEFECT_STATUS = HIGH` OR `ALIGN_STATUS = HIGH`.

Let `current_tool = T*`, `other_tools = all tools ≠ T*`:

- If current is NOT abnormal → `drift_type = UNKNOWN`.
- If current is abnormal and:
  - `other_abnormal_count = 0` → `TOOL_DRIFT`.
  - `other_abnormal_count = len(other_tools)` → `PROCESS_DRIFT`.
  - else → `MIXED`.

This drift label is only about **pattern of anomalies across tools**,
not about root cause by itself.


```


==============================
FILE: docs\misc_notes.md
==============================

```markdown
# Misc Notes (Compact)

## 1. Time & Window

- Default analysis window: last 24h of `inspection_runs.start_time`.
- Derived as:
  - `window_end = max(start_time)`
  - `window_start = window_end - 24h`

Can be tuned (e.g., 8h / 72h) depending on use case.

## 2. Thresholds

- `DEFECT_HIGH_THRESHOLD = 50` for high-defect runs.
- `ANOMALY_RATIO_THRESHOLD = 0.05` for status HIGH vs NORMAL.

In a real fab, thresholds may:
- Differ per recipe/tool.
- Be based on historical statistics.

## 3. Status Fields

### `inspection_runs.run_result`
- Convenience label like `NORMAL`, `HIGH_DEFECT`, `ALIGN_FAIL`.
- Numeric fields (`defect_count_total`, `run_time_align_fail`) are primary.

### `calibration_runs.status`
- `PASSED` / `FAILED`.  
- Overdue is inferred via `next_due_time < now`, not via status string.

### `subsystem_health_metrics.status`
- `OK` / `WARN` / `ALERT`.  
- `WARN`/`ALERT` treated as problematic even if numeric value is near spec.

## 4. Interpretation Pattern

When investigating a (tool, recipe) problem:

1. Check outcome anomalies:
   - defect / align anomaly ratios.
2. Check calibration:
   - overdue or FAILED?
3. Check subsystem metrics:
   - STAGE_POS_X/Y out-of-spec, `WARN`/`ALERT`?
4. Compare tools:
   - Only one tool abnormal → likely **TOOL_DRIFT**.
   - Many tools on same recipe abnormal → likely **PROCESS_DRIFT**.
   - Mixed → **MIXED**; need deeper investigation.

## 5. Synthetic Data Reminder

- `data.sqlite` is synthetic.
- Encodes:
  - One clear tool drift example: `P2` + `S13Layer`.
  - One clear process drift example: `WadiLayer` across tools.
- Intended for agent reasoning / demo, not real fab production data.

## 6. System Health Questions

- Treat each tool as a separate "system".
- If no tool_id is provided, ask the user to choose one.


```


==============================
FILE: docs\tables.md
==============================

```markdown
# Data Dictionary: Fab Inspection Demo Database

This document describes the schema of the `data.sqlite` database used for fab
inspection and equipment health analysis. It focuses on tables, columns, and
logical relationships rather than any specific agent implementation.

---

## Overview

The database models a simplified fab inspection environment with:

- Four inspection tools (8950XR-P1, P2, P3, P4)
- Four subsystems per tool (STAGE, CAMERA, FOCUS, ILLUMINATION)
- Five inspection recipes (SIPLayer, S13Layer, S14Layer, S15Layer, WadiLayer)
- Run-level inspection data (defects, alignment failures)
- Calibration history per subsystem
- Stage-position health metrics (X/Y position vs spec)

Core tables:

1. `tools`
2. `subsystems`
3. `recipes`
4. `inspection_runs`
5. `calibration_runs`
6. `subsystem_health_metrics`

---

## Table: `tools`

**Purpose:** Master list of inspection tools.

| Column   | Type | Description                          |
|----------|------|--------------------------------------|
| tool_id  | TEXT | Primary key. Identifier for a tool. |

**Notes:**

- Example values: `8950XR-P1`, `8950XR-P2`, `8950XR-P3`, `8950XR-P4`.
- Referenced by multiple tables (`subsystems`, `inspection_runs`, `calibration_runs`).

---

## Table: `subsystems`

**Purpose:** Enumerates subsystems for each tool.

| Column       | Type    | Description                                             |
|--------------|---------|---------------------------------------------------------|
| subsystem_id | INTEGER | Primary key (AUTOINCREMENT).                            |
| tool_id      | TEXT    | FK → `tools.tool_id`.                                   |
| name         | TEXT    | Subsystem name: `STAGE`, `CAMERA`, `FOCUS`, `ILLUMINATION`. |

**Logical relations:**

- Each tool has four subsystems (one per name).
- `subsystem_id` is used by:
  - `calibration_runs` to store calibration history.
  - `subsystem_health_metrics` to store health metrics.

---

## Table: `recipes`

**Purpose:** Master list of inspection recipes.

| Column      | Type    | Description                           |
|-------------|---------|---------------------------------------|
| recipe_id   | INTEGER | Primary key (AUTOINCREMENT).          |
| recipe_name | TEXT    | Unique recipe name (e.g., `S13Layer`). |

**Notes:**

- Example values: `SIPLayer`, `S13Layer`, `S14Layer`, `S15Layer`, `WadiLayer`.
- `recipe_id` is referenced by `inspection_runs`.

---

## Table: `inspection_runs`

**Purpose:** Run-level inspection data. This is the primary source for “system
health” from the product/inspection outcome perspective.

| Column             | Type    | Description                                                                 |
|--------------------|---------|-----------------------------------------------------------------------------|
| run_id             | INTEGER | Primary key (AUTOINCREMENT).                                               |
| tool_id            | TEXT    | FK → `tools.tool_id`.                                                       |
| recipe_id          | INTEGER | FK → `recipes.recipe_id`.                                                   |
| start_time         | DATETIME| Run start timestamp (ISO-8601 string).                                     |
| end_time           | DATETIME| Run end timestamp (ISO-8601 string).                                       |
| defect_count_total | INTEGER | Total defect count observed in this run.                                   |
| run_time_align_fail| INTEGER | Alignment failure flag/count (0 = no align fail, >0 = alignment issue).    |
| run_result         | TEXT    | Categorical summary: `NORMAL`, `HIGH_DEFECT`, `ALIGN_FAIL`, etc.           |

**Typical usage:**

- Grouped by `(tool_id, recipe_id)` over a time window to compute:
  - `total_runs`
  - `abnormal_defect_runs`
  - `abnormal_align_runs`
- Used to derive:
  - `defect_anomaly_ratio`
  - `align_anomaly_ratio`
- Serves as the first-layer health filter.

**Index:**

- `idx_inspection_runs_tool_recipe_time` on `(tool_id, recipe_id, start_time)`
  for efficient time-window queries.

---

## Table: `calibration_runs`

**Purpose:** Records calibration history per tool and subsystem, for different
calibration types.

| Column       | Type    | Description                                                       |
|--------------|---------|-------------------------------------------------------------------|
| calib_id     | INTEGER | Primary key (AUTOINCREMENT).                                      |
| tool_id      | TEXT    | FK → `tools.tool_id`.                                             |
| subsystem_id | INTEGER | FK → `subsystems.subsystem_id`.                                   |
| calib_type   | TEXT    | Calibration type (e.g., `PrealignerToStage`, `GantryOffset`).     |
| start_time   | DATETIME| Calibration start time.                                           |
| end_time     | DATETIME| Calibration end time.                                             |
| next_due_time| DATETIME| Next due time; if in the past, the calibration is considered overdue. |
| status       | TEXT    | Calibration result, typically `PASSED` or `FAILED`.              |

**Typical calibration types:**

- `PrealignerToStage`
- `GantryOffset`
- `ChuckCenterTheta`
- `Illumination`

**Logical usage:**

- For each `(tool, subsystem, calib_type)`, the most recent calibration record
  (by `end_time`) is used to determine:
  - Whether the calibration is **overdue** (`next_due_time` < reference time).
  - Whether the last calibration **failed** (`status = 'FAILED'`).

**Index:**

- `idx_calibration_runs_tool_subsystem` on `(tool_id, subsystem_id, next_due_time)`.

---

## Table: `subsystem_health_metrics`

**Purpose:** Numeric health metrics per subsystem over time. In this demo, it
captures STAGE X/Y position values for each tool.

| Column       | Type    | Description                                                           |
|--------------|---------|-----------------------------------------------------------------------|
| metric_id    | INTEGER | Primary key (AUTOINCREMENT).                                          |
| subsystem_id | INTEGER | FK → `subsystems.subsystem_id`.                                       |
| ts           | DATETIME| Timestamp of the measurement.                                         |
| metric_name  | TEXT    | Metric name, e.g.: `STAGE_POS_X`, `STAGE_POS_Y`.                      |
| metric_value | REAL    | Numeric value of the metric (e.g., position in µm or equivalent units). |
| spec_low     | REAL    | Lower spec limit for the metric (e.g., -150).                         |
| spec_high    | REAL    | Upper spec limit for the metric (e.g., 150).                          |
| status       | TEXT    | Health status: `OK`, `WARN`, or `ALERT`.                              |

**Typical usage:**

- For STAGE subsystem of each tool:
  - Check if any `metric_value` is outside `[spec_low, spec_high]`.
  - Check if any `status` is `WARN` or `ALERT`.
- Used as evidence for mechanical / positional issues contributing to tool drift.

**Index:**

- `idx_subsys_metrics_subsystem_ts` on `(subsystem_id, ts)`.

---

## Key Relationships Summary

- `tools (1) — (N) subsystems`
- `tools (1) — (N) inspection_runs`
- `recipes (1) — (N) inspection_runs`
- `subsystems (1) — (N) calibration_runs`
- `subsystems (1) — (N) subsystem_health_metrics`

These relationships enable multi-layer reasoning:

1. **Outcome-level**: `inspection_runs` → detect abnormal defect / alignment behavior.
2. **Maintenance-level**: `calibration_runs` → detect overdue or failed calibrations.
3. **Hardware-level**: `subsystem_health_metrics` → detect out-of-spec or ALERT metrics.

```


==============================
FILE: README.md
==============================

```markdown
# Fab Data Analysis Agent

Local, data-centric AI agent for fab inspection and equipment analytics using LangGraph, SQLite, and Streamlit.

## Setup

1) Install uv (https://docs.astral.sh/uv/).
2) Install dependencies (if uv crashes on macOS SystemConfiguration, use local cache or pip fallback):
```bash
UV_CACHE_DIR=.uv_cache uv sync
# Fallback if uv panics:
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
```

## Running

1) Place your SQLite database at `data.sqlite` in the project root (or set `DB_PATH` env var).
2) Put Markdown knowledge files under `docs/` (any `*.md`).
3) Launch the app:
```bash
uv run streamlit run src/app/main_streamlit.py
```

## Architecture (Text Tree)

```
Fab Data Analysis Agent
├─ User / Streamlit UI: src/app/main_streamlit.py
│  └─ Calls run_graph(); manages chat session and clarifications
├─ Config & Context
│  ├─ Config load: src/core/config.py (DB/docs/runtime_cache paths)
│  ├─ Logging: src/core/logging_utils.py (runtime_cache/agent.log)
│  └─ Context load: src/core/context_loader.py
│     ├─ SQLite schema introspection → DatabaseSchema
│     └─ Markdown knowledge merge + table index
├─ LangGraph Assembly: src/graph/graph_builder.py
│  ├─ Entry: supervisor
│  ├─ Conditional routing: next_action → data_analyst / domain_expert / ask_user / aggregator
│  └─ End: END (aggregator or ask_user)
├─ Supervisor (LLM): src/agents/supervisor.py
│  └─ Chooses next_action (sql_analysis / python_analysis / domain_explain / ask_user / finish)
├─ Data Analyst (LLM): src/agents/data_analyst.py
│  ├─ SQL planning → SQLite tool
│  │  └─ SQLite tool: src/tools/sqlite_tool.py (read-only; results to runtime_cache/*.csv)
│  └─ Python planning → Python tool
│     └─ Python tool: src/tools/python_tool.py (pandas/numpy/matplotlib; plots to runtime_cache/*.png)
├─ Domain Expert (LLM): src/agents/domain_expert.py
│  └─ Explains numeric findings using Markdown knowledge
├─ Aggregator (LLM): src/agents/aggregator.py
│  └─ Produces final answer
├─ Data & Knowledge
│  ├─ SQLite DB: data.sqlite
│  └─ Knowledge base: docs/*.md
└─ Runtime artifacts: runtime_cache/
   ├─ Query CSVs: query_result_*.csv
   └─ Plots: plot_*.png
```

## Notes

- Tools write intermediate CSVs and plots to `runtime_cache/`.
- OpenAI API key should be available via `OPENAI_API_KEY`.
- Dockerfile is left as a TODO stub.


```


==============================
FILE: requirements.txt
==============================

```
langgraph>=0.0.70
langchain-openai>=0.3.0
openai>=1.57.0
pandas>=2.1.0
numpy>=1.26.0
matplotlib>=3.8.0
streamlit>=1.29.0
pydantic>=2.5.0
typing-extensions>=4.8.0
pytest>=7.4.0
ruff>=0.6.0


```


==============================
FILE: src\agents\__init__.py
==============================

```python
# Agent node implementations.


```


==============================
FILE: src\agents\aggregator.py
==============================

```python
from __future__ import annotations

import json
import logging

from langchain_openai import ChatOpenAI

from core.models import GraphState


AGGREGATOR_PROMPT = """
You are the final responder for a fab data analysis agent.

General style:
- Always give a short summary first.
- Then provide only the most important supporting evidence.
- Keep answers compact and avoid repeating internal debug details, SQL, or long tables.

For questions about system health, tool health, or drift:
1) Start with an **Overall health** statement (1–2 short sentences), clearly saying whether the
   tool/system is:
   - Healthy / within normal range, OR
   - Degraded but still acceptable, OR
   - Unhealthy / at-risk.

2) Then give an **Evidence** section with 3–5 bullet points maximum, picking only the strongest
   signals, for example:
   - defect/align anomaly ratios vs threshold (just approximate levels, not every number)
   - overdue or failed calibrations
   - STAGE_POS_X/Y WARN or ALERT occurrences
   - clear patterns across tools/recipes (tool drift vs process drift)

3) Optionally add a **Next steps** section with 2–3 concrete recommendations.

Constraints:
- Do NOT dump raw SQL, column lists, or per-run tables.
- Do NOT repeat the entire step history; use it only as background.
- Keep the whole answer roughly within 150–250 words.

For non-health questions, still follow:
- Short summary first
- Then a few key bullets or short paragraphs with the most relevant details only.
"""



def aggregator_node(llm: ChatOpenAI, logger: logging.Logger | None = None):
    """Build result aggregator node callable."""

    def _node(state: GraphState) -> GraphState:
        messages = [
            {"role": "system", "content": AGGREGATOR_PROMPT},
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "user_query": state.get("user_query", ""),
                        "steps": state.get("step_results", []),
                        "clarifications": state.get("clarification_answers", {}),
                    }
                ),
            },
        ]

        response = llm.invoke(messages)
        content = response.content if hasattr(response, "content") else ""
        state["final_answer"] = content
        if logger:
            logger.info(
                "[aggregator] steps=%s answer_len=%s llm=%s",
                len(state.get("step_results", [])),
                len(content),
                content[:300].replace("\n", " "),
            )
        return state

    return _node


```


==============================
FILE: src\agents\data_analyst.py
==============================

```python
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


```


==============================
FILE: src\agents\domain_expert.py
==============================

```python
from __future__ import annotations

import json
import logging
from typing import List

from langchain_openai import ChatOpenAI

from core.models import GraphState, StepResult


DOMAIN_EXPERT_PROMPT = """
You are a fab domain expert. Interpret analysis findings using provided Markdown knowledge.

Goals:
- Explain possible root causes and link them to equipment / defect rules.
- Suggest practical next steps for engineers.
- Stay concise.

Style rules:
- First, give 1-2 short sentences summarizing what the data suggests
  (e.g., "P2 on S13Layer shows clear tool drift" or "WadiLayer issues look like process drift").
- Then provide at most 3-5 bullet points of key evidence
  (e.g., high anomaly ratios, overdue calibration, STAGE_WARN/ALERT signals, cross-tool pattern).
- Optionally add 1-3 bullet points of recommended next actions.
- Do NOT list raw SQL, every metric, or long tables.
- Avoid fabricating table names or fields; only refer to concepts that clearly exist
  in the findings or Markdown knowledge.

Return concise paragraphs and bullets only, no debug or tool-internal details.
"""



def domain_expert_node(llm: ChatOpenAI, logger: logging.Logger | None = None):
    """Build domain expert node callable."""

    def _node(state: GraphState) -> GraphState:
        findings: List[StepResult] = state.get("step_results", [])
        markdown = state.get("markdown_knowledge", "")
        messages = [
            {"role": "system", "content": DOMAIN_EXPERT_PROMPT},
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "findings": findings[-5:],
                        "markdown": markdown[:4000],
                        "user_query": state.get("user_query", ""),
                    }
                ),
            },
        ]

        response = llm.invoke(messages)
        content = response.content if hasattr(response, "content") else ""

        step_result: StepResult = {
            "step_id": state.get("next_action", {}).get("id", "domain"),
            "step_type": "domain_explain",
            "summary": content,
            "raw_llm": content,
        }
        state.setdefault("step_results", []).append(step_result)
        # Suggest finishing after domain explanation.
        state["next_action"] = {
            "action_type": "finish",
            "id": "finish",
            "description": "Aggregate results for the user.",
        }
        if logger:
            logger.info(
                "[domain_expert] step_id=%s summary_len=%s llm=%s",
                step_result["step_id"],
                len(content),
                content[:300].replace("\n", " "),
            )
        return state

    return _node


```


==============================
FILE: src\agents\supervisor.py
==============================

```python
from __future__ import annotations

import json
import logging
from typing import Dict, List

from langchain_openai import ChatOpenAI

from core.models import DatabaseSchema, GraphState, NextAction, StepResult


SUPERVISOR_SYSTEM_PROMPT = """
You are the Supervisor for a fab data analysis agent. Decide the next action based on:
- User question.
- Database schema (tables, columns).
- Markdown knowledge (domain notes).
- Prior step results and any clarification answers.

You must pick one next action:
- "sql_analysis": ask data analyst to create SQL for the database.
- "python_analysis": ask data analyst to run python on existing datasets.
- "domain_explain": ask domain expert to interpret numeric findings with domain knowledge.
- "ask_user": request a clarification question and stop the loop.
- "finish": finalize and hand off to result aggregator.

Return JSON with keys: action_type, id, description, and optional tables, target_dataset_id, clarification_question.
If clarification is needed, use action_type "ask_user" with a concise clarification_question.

Additional rules about "system health":
- In this agent, **one physical tool (tool_id) is one "system"**.
- For any question about "system health" or "tool health" you MUST know which tool_id
  the user is asking about (e.g. "8950XR-P2").
- If the tool_id is not clearly specified in the current user query or in the
  clarification_answers, you MUST:
  - return action_type = "ask_user"
  - set id = "tool_id"
  - set clarification_question to something like:
    "Which tool do you want me to check? (8950XR-P1, 8950XR-P2, 8950XR-P3, 8950XR-P4)"
- Only after tool_id is known should you choose "sql_analysis" or "python_analysis".
- Do NOT assume a default tool_id.
"""


def summarize_results(results: List[StepResult]) -> str:
    """Create a compact textual summary of prior steps."""
    parts: List[str] = []
    for res in results[-5:]:
        summary = res.get("summary") or ""
        parts.append(f"{res.get('step_type')}: {summary}")
    return "\n".join(parts)


def supervisor_node(llm: ChatOpenAI, logger: logging.Logger | None = None):
    """Build supervisor node callable."""

    def _node(state: GraphState) -> GraphState:
        state["loop_count"] = state.get("loop_count", 0) + 1
        if state["loop_count"] > 20:
            if logger:
                logger.info(
                    "[supervisor] loop guard hit at %s; forcing finish. steps=%s",
                    state["loop_count"],
                    len(state.get("step_results", [])),
                )
            state["next_action"] = {
                "action_type": "finish",
                "id": "auto_finish",
                "description": "Loop guard triggered; aggregate findings for the user.",
            }
            state["pending_clarification"] = None
            return state

        schema: DatabaseSchema = state.get("database_schema", DatabaseSchema(tables=[]))  # type: ignore
        schema_text = json.dumps(schema.to_dict())
        markdown = state.get("markdown_knowledge", "")
        previous = summarize_results(state.get("step_results", []))
        clarifications = state.get("clarification_answers", {})

        messages = [
            {"role": "system", "content": SUPERVISOR_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": (
                    f"User query:\n{state.get('user_query','')}\n\n"
                    f"Clarification answers:\n{json.dumps(clarifications)}\n\n"
                    f"Database schema:\n{schema_text}\n\n"
                    f"Markdown knowledge:\n{markdown[:4000]}\n\n"
                    f"Recent results:\n{previous}"
                ),
            },
        ]

        response = llm.invoke(messages)
        content = response.content if hasattr(response, "content") else ""
        next_action: NextAction = {"action_type": "finish", "id": "finish", "description": "Provide final answer."}
        try:
            parsed = json.loads(content)
            if isinstance(parsed, dict) and "action_type" in parsed:
                next_action = parsed  # type: ignore
        except json.JSONDecodeError:
            # Fallback: default to finish with note.
            next_action = {
                "action_type": "finish",
                "id": "finish",
                "description": f"Could not parse action, finish. Raw response: {content}",
            }

        state["next_action"] = next_action
        if next_action.get("action_type") == "ask_user":
            state["pending_clarification"] = {
                "id": next_action.get("id", "clarify"),
                "question": next_action.get("clarification_question", "Please provide more detail."),
            }
        else:
            state["pending_clarification"] = None

        if logger:
            logger.info(
                "[supervisor] loop=%s action=%s desc=%s pending_clarification=%s steps=%s clarifications=%s",
                state["loop_count"],
                next_action.get("action_type"),
                next_action.get("description"),
                bool(state.get("pending_clarification")),
                len(state.get("step_results", [])),
                list(clarifications.keys()),
            )
        return state

    return _node


```


==============================
FILE: src\app\__init__.py
==============================

```python
# Application package marker.


```


==============================
FILE: src\app\main_streamlit.py
==============================

```python
from __future__ import annotations

import json
from typing import Dict, List

import streamlit as st

from graph.graph_builder import stream_graph

st.set_page_config(page_title="Fab Data Analysis Agent", layout="wide")
st.title("Fab Data Analysis Agent")

# ----- Initialize session states -----
if "messages" not in st.session_state:
    st.session_state.messages = []
if "clarification_answers" not in st.session_state:
    st.session_state.clarification_answers: Dict[str, str] = {}
if "pending_clarification" not in st.session_state:
    st.session_state.pending_clarification = None
if "last_user_query" not in st.session_state:
    st.session_state.last_user_query = ""


# ----- Dynamic node construction & rendering -----

def build_pipeline_nodes(
    step_results: List[Dict],
    final_answer: str | None,
    pending_clarification: Dict | None,
) -> List[Dict[str, str]]:
    """
    Dynamically build a sequence of nodes based on the current state,
    including step_results / final_answer / pending_clarification.

    Example:
      Plan / Supervisor
      → SQL Analysis #1
      → Domain Explain #1
      → SQL Analysis #2
      → Final Answer
    """
    nodes: List[Dict[str, str]] = []

    # Always start with a "Plan / Supervisor" node
    nodes.append({"id": "plan", "label": "Plan / Supervisor"})

    # Append nodes according to step_results, preserving order,
    # and automatically numbering nodes of the same step_type.
    type_counts: Dict[str, int] = {
        "sql_analysis": 0,
        "python_analysis": 0,
        "domain_explain": 0,
    }

    for idx, step in enumerate(step_results):
        stype = step.get("step_type")
        if stype not in ("sql_analysis", "python_analysis", "domain_explain", "finish"):
            continue

        if stype in type_counts:
            type_counts[stype] += 1
            num = type_counts[stype]
        else:
            num = 1

        if stype == "sql_analysis":
            label = f"SQL Analysis #{num}"
        elif stype == "python_analysis":
            label = f"Python Analysis #{num}"
        elif stype == "domain_explain":
            label = f"Domain Explain #{num}"
        elif stype == "finish":
            label = "Finish"
        else:
            label = stype

        nodes.append({"id": f"{stype}_{idx}", "label": label})

    # If the graph execution ends with an ask_user step (pending_clarification exists and no final_answer yet)
    if pending_clarification and not final_answer:
        nodes.append({"id": "clarify", "label": "Clarification Needed"})

    # If a final answer exists, add a Final Answer node
    if final_answer:
        nodes.append({"id": "aggregator", "label": "Final Answer"})

    return nodes


def infer_dynamic_status(nodes: List[Dict[str, str]]) -> Dict[str, str]:
    """
    Assign status to each node:
    - All nodes except the last: done
    - Last node: current

    We do NOT draw "future todo nodes" because Supervisor's decisions are dynamic.
    """
    status: Dict[str, str] = {}
    if not nodes:
        return status

    last_index = len(nodes) - 1
    for idx, node in enumerate(nodes):
        nid = node["id"]
        if idx < last_index:
            status[nid] = "done"
        else:
            status[nid] = "current"
    return status


def render_pipeline(nodes: List[Dict[str, str]], status: Dict[str, str]) -> str:
    """
    Render nodes + status into a horizontal HTML progress bar.
    done = green, current = blue.
    """
    css = """
    <style>
    .pipeline-container {
        display: flex;
        align-items: center;
        margin-bottom: 1rem;
        font-size: 0.9rem;
        flex-wrap: wrap;
        row-gap: 0.5rem;
    }
    .pipeline-step {
        display: flex;
        flex-direction: column;
        align-items: center;
        min-width: 120px;
    }
    .pipeline-circle {
        width: 20px;
        height: 20px;
        border-radius: 999px;
        border: 2px solid #999999;
        margin-bottom: 4px;
    }
    .pipeline-label {
        text-align: center;
        max-width: 160px;
        white-space: normal;
    }
    .pipeline-connector {
        flex: 0 0 40px;
        height: 2px;
        background-color: #e0e0e0;
        margin: 0 8px;
    }
    .pipeline-circle.done {
        background-color: #34a853;
        border-color: #34a853;
    }
    .pipeline-circle.current {
        background-color: #4285f4;
        border-color: #4285f4;
    }
    .pipeline-label.done {
        color: #34a853;
        font-weight: 600;
    }
    .pipeline-label.current {
        color: #4285f4;
        font-weight: 600;
    }
    .pipeline-circle.todo {
        background-color: #f5f5f5;
        border-color: #999999;
    }
    .pipeline-label.todo {
        color: #999999;
    }
    </style>
    """

    parts = [css, '<div class="pipeline-container">']
    for idx, node in enumerate(nodes):
        nid = node["id"]
        label = node["label"]
        s = status.get(nid, "todo")

        circle_class = f"pipeline-circle {s}"
        label_class = f"pipeline-label {s}"

        parts.append('<div class="pipeline-step">')
        parts.append(f'<div class="{circle_class}"></div>')
        parts.append(f'<div class="{label_class}">{label}</div>')
        parts.append("</div>")

        # Draw connector lines between nodes
        if idx < len(nodes) - 1:
            prev_status = status.get(nid, "todo")
            connector_color = "#e0e0e0"
            if prev_status in ("done", "current"):
                connector_color = "#34a853"
            parts.append(
                f'<div class="pipeline-connector" style="background-color:{connector_color};"></div>'
            )

    parts.append("</div>")
    return "".join(parts)


# ----- Render conversation history -----

def render_history():
    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])
            if msg.get("debug"):
                with st.expander("Debug details"):
                    st.write(msg["debug"])


render_history()

# ----- Input box -----
prompt = st.chat_input("Ask about fab inspection data or equipment insights")

if prompt:
    user_query = prompt
    clarification_payload = dict(st.session_state.clarification_answers)

    # If currently answering a clarification question
    if st.session_state.pending_clarification:
        clar_id = st.session_state.pending_clarification.get("id")
        if clar_id:
            clarification_payload[clar_id] = prompt
            st.session_state.clarification_answers[clar_id] = prompt
        user_query = st.session_state.last_user_query or prompt
        st.session_state.pending_clarification = None
    else:
        # New user query
        st.session_state.last_user_query = user_query

    # Store user message
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    try:
        final_state = None
        final_debug_info = None

        # Assistant message: live-updating pipeline + answer
        with st.chat_message("assistant"):
            pipeline_placeholder = st.empty()
            answer_placeholder = st.empty()

            # ★ Stream graph execution and update UI nodes at each step
            for state in stream_graph(
                user_query, clarification_answers=clarification_payload
            ):
                final_state = state

                step_results = state.get("step_results", [])
                final_answer = state.get("final_answer")
                pending = state.get("pending_clarification")

                nodes = build_pipeline_nodes(step_results, final_answer, pending)
                node_status = infer_dynamic_status(nodes)
                pipeline_html = render_pipeline(nodes, node_status)
                pipeline_placeholder.markdown(pipeline_html, unsafe_allow_html=True)

                if final_answer:
                    answer_placeholder.markdown(final_answer)

            # Final state after graph execution completes
            if final_state is None:
                final_answer = "No answer generated."
                step_results = []
                datasets = {}
                pending = None
            else:
                final_answer = final_state.get("final_answer")
                step_results = final_state.get("step_results", [])
                datasets = final_state.get("data_artifacts", {})
                pending = final_state.get("pending_clarification")

            final_debug_info = {
                "actions": [step.get("step_type") for step in step_results],
                "steps": step_results,
                "datasets": datasets,
            }

            # If this round requires clarification, show the clarification question instead of the final answer
            if pending and not final_answer:
                question = pending.get("question", "Please provide more detail.")
                answer_placeholder.markdown(question)
            elif final_answer:
                answer_placeholder.markdown(final_answer)
            else:
                answer_placeholder.markdown("No answer generated.")

            with st.expander("Debug details"):
                st.write(json.dumps(final_debug_info, indent=2))

        # ----- Update stored assistant messages -----
        if final_state is None:
            st.session_state.pending_clarification = None
            st.session_state.last_user_query = user_query
        else:
            pending = final_state.get("pending_clarification")
            if pending and not final_answer:
                st.session_state.pending_clarification = pending
                content_to_store = pending.get("question", "Please provide more detail.")
            else:
                st.session_state.pending_clarification = None
                content_to_store = final_answer or "No answer generated."

            msg = {
                "role": "assistant",
                "content": content_to_store,
                "debug": (
                    json.dumps(final_debug_info, indent=2) if final_debug_info else None
                ),
            }
            st.session_state.messages.append(msg)

    except Exception as exc:
        error_text = (
            "An error occurred while processing your request. "
            "Please try again.\n\n"
            f"Error: {exc}"
        )
        st.session_state.messages.append({"role": "assistant", "content": error_text})
        with st.chat_message("assistant"):
            st.markdown(error_text)
        st.session_state.pending_clarification = None
        st.session_state.last_user_query = user_query
        st.stop()


```


==============================
FILE: src\core\__init__.py
==============================

```python
# Core utilities and data models.


```


==============================
FILE: src\core\config.py
==============================

```python
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass
class AppConfig:
    """Runtime configuration loaded from environment variables."""

    db_path: Path
    docs_path: Path
    runtime_cache: Path
    model: str
    max_sql_rows: int = 1000


def load_config() -> AppConfig:
    """Load configuration from environment variables with safe defaults."""

    root = Path(__file__).resolve().parents[2]
    db_path = Path(os.getenv("DB_PATH", root / "data.sqlite"))
    docs_path = Path(os.getenv("DOCS_PATH", root / "docs"))
    runtime_cache = Path(os.getenv("RUNTIME_CACHE", root / "runtime_cache"))
    model = os.getenv("OPENAI_MODEL", "gpt-4.1")

    runtime_cache.mkdir(parents=True, exist_ok=True)

    return AppConfig(
        db_path=db_path,
        docs_path=docs_path,
        runtime_cache=runtime_cache,
        model=model,
    )


```


==============================
FILE: src\core\context_loader.py
==============================

```python
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


```


==============================
FILE: src\core\logging_utils.py
==============================

```python
from __future__ import annotations

import logging
from pathlib import Path


def setup_logging(log_path: Path) -> logging.Logger:
    """Configure a simple file logger under runtime_cache for agent loops."""

    log_path.parent.mkdir(parents=True, exist_ok=True)

    logger = logging.getLogger("fab_agent")
    logger.setLevel(logging.INFO)

    if not any(isinstance(h, logging.FileHandler) and getattr(h, "baseFilename", "") == str(log_path) for h in logger.handlers):
        handler = logging.FileHandler(log_path, encoding="utf-8")
        formatter = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
        handler.setFormatter(formatter)
        logger.addHandler(handler)

    return logger


```


==============================
FILE: src\core\models.py
==============================

```python
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
    step_type: Literal["sql_analysis", "python_analysis", "domain_explain", "ask_user", "finish"]
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
    action_type: Literal["sql_analysis", "python_analysis", "domain_explain", "ask_user", "finish"]
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


```


==============================
FILE: src\graph\__init__.py
==============================

```python
# LangGraph assembly.


```


==============================
FILE: src\graph\graph_builder.py
==============================

```python
from __future__ import annotations

from typing import Dict, Iterator, Optional

from langchain_openai import ChatOpenAI
from langgraph.graph import END, StateGraph

from agents.aggregator import aggregator_node
from agents.data_analyst import data_analyst_node
from agents.domain_expert import domain_expert_node
from agents.supervisor import supervisor_node
from core.config import AppConfig, load_config
from core.context_loader import load_database_schema, load_markdown_knowledge
from core.logging_utils import setup_logging
from core.models import DatabaseSchema, GraphState


def build_graph(
    config: AppConfig,
    schema: DatabaseSchema,
    markdown_knowledge: str,
    table_markdown_index: Dict[str, str],
    logger=None,
):
    """Construct and compile the LangGraph workflow."""

    llm = ChatOpenAI(model=config.model, temperature=0)

    graph = StateGraph(GraphState)

    # Nodes
    graph.add_node("supervisor", supervisor_node(llm, logger=logger))
    graph.add_node(
        "data_analyst",
        data_analyst_node(
            llm,
            db_path=config.db_path,
            runtime_cache=config.runtime_cache,
            table_markdown_index=table_markdown_index,
            max_rows=config.max_sql_rows,
        ),
    )
    graph.add_node("domain_expert", domain_expert_node(llm, logger=logger))
    graph.add_node("aggregator", aggregator_node(llm, logger=logger))

    def ask_user_node(state: GraphState) -> GraphState:
        # Supervisor already set pending clarification; nothing else to do.
        return state

    graph.add_node("ask_user", ask_user_node)

    # Routing
    def route_supervisor(state: GraphState) -> str:
        action = state.get("next_action") or {}
        action_type = action.get("action_type")
        if action_type in {"sql_analysis", "python_analysis"}:
            return "data_analyst"
        if action_type == "domain_explain":
            return "domain_expert"
        if action_type == "ask_user":
            return "ask_user"
        return "aggregator"

    graph.set_entry_point("supervisor")
    graph.add_conditional_edges(
        "supervisor",
        route_supervisor,
        {
            "data_analyst": "data_analyst",
            "domain_expert": "domain_expert",
            "ask_user": "ask_user",
            "aggregator": "aggregator",
        },
    )
    graph.add_edge("data_analyst", "supervisor")
    graph.add_edge("domain_expert", "supervisor")
    graph.add_edge("aggregator", END)
    graph.add_edge("ask_user", END)

    return graph.compile()


def _init_app_and_state(
    user_query: str,
    clarification_answers: Optional[Dict[str, str]] = None,
):
    """
    Initialize config / logger / schema / markdown / graph / initial state in one place.
    Shared by run_graph_once and stream_graph.
    """
    config = load_config()
    logger = setup_logging(config.runtime_cache / "agent.log")
    schema = load_database_schema(config.db_path)
    markdown_knowledge, table_markdown_index = load_markdown_knowledge(config.docs_path)

    initial_state: GraphState = {
        "user_query": user_query,
        "database_schema": schema,
        "markdown_knowledge": markdown_knowledge,
        "table_markdown_index": table_markdown_index,
        "clarification_answers": clarification_answers or {},
        "step_results": [],
        "data_artifacts": {},
        "next_action": None,
        "pending_clarification": None,
        "final_answer": None,
        "loop_count": 0,
    }

    app = build_graph(
        config, schema, markdown_knowledge, table_markdown_index, logger=logger
    )
    return app, initial_state


def run_graph_once(
    user_query: str,
    clarification_answers: Optional[Dict[str, str]] = None,
) -> GraphState:
    """Execute the whole graph once and return the final GraphState (no streaming for UI)."""
    app, initial_state = _init_app_and_state(user_query, clarification_answers)
    return app.invoke(initial_state, config={"recursion_limit": 60})


def stream_graph(
    user_query: str,
    clarification_answers: Optional[Dict[str, str]] = None,
) -> Iterator[GraphState]:
    """
    Execute the graph in a streaming fashion: after each node finishes, yield the current GraphState.

    On the frontend you can do:
      for state in stream_graph(...):
          # update progress bar / debug info / partial answers
    """
    app, initial_state = _init_app_and_state(user_query, clarification_answers)
    for state in app.stream(
        initial_state,
        config={"recursion_limit": 60},
        stream_mode="values",  # Key: directly get GraphState instead of event dicts
    ):
        yield state


def run_graph(
    user_query: str,
    clarification_answers: Optional[Dict[str, str]] = None,
    stream: bool = False,
) -> GraphState:
    """
    Keep the original interface for use in other places:
    - stream=False → equivalent to run_graph_once
    - stream=True  → run stream_graph to completion and return the last state
    """
    if stream:
        last_state: Optional[GraphState] = None
        for state in stream_graph(user_query, clarification_answers):
            last_state = state
        if last_state is None:
            # Should not normally happen; just a safety fallback
            return run_graph_once(user_query, clarification_answers)
        return last_state
    else:
        return run_graph_once(user_query, clarification_answers)


```


==============================
FILE: src\tools\__init__.py
==============================

```python
# Tool adapters for database and Python execution.


```


==============================
FILE: src\tools\python_tool.py
==============================

```python
from __future__ import annotations

import io
import uuid
from contextlib import redirect_stdout
from pathlib import Path
from typing import Any, Dict

import matplotlib
import numpy as np
import pandas as pd

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402


SAFE_BUILTINS = {
    "print": print,
    "len": len,
    "range": range,
    "min": min,
    "max": max,
    "sum": sum,
    "abs": abs,
    "float": float,
    "int": int,
    "enumerate": enumerate,
    "zip": zip,
}


def run_python_analysis(
    code: str, datasets: Dict[str, str], runtime_cache: Path
) -> Dict[str, Any]:
    """Execute analysis code against cached CSV datasets in a constrained namespace."""

    runtime_cache.mkdir(parents=True, exist_ok=True)

    local_ctx: Dict[str, Any] = {}
    global_ctx: Dict[str, Any] = {
        "__builtins__": SAFE_BUILTINS,
        "pd": pd,
        "np": np,
        "plt": plt,
        "datasets": datasets,
        "runtime_cache": runtime_cache,
    }

    def save_plot(name: str | None = None) -> str:
        plot_id = name or f"plot_{uuid.uuid4().hex[:8]}"
        path = runtime_cache / f"{plot_id}.png"
        plt.savefig(path)
        return str(path)

    global_ctx["save_plot"] = save_plot

    stdout_buffer = io.StringIO()
    try:
        with redirect_stdout(stdout_buffer):
            exec(code, global_ctx, local_ctx)
    except Exception as exc:
        return {"status": "error", "error_message": str(exc)}

    output_text = stdout_buffer.getvalue().strip()
    result_obj = local_ctx.get("result")
    metrics = local_ctx.get("metrics", {})
    plots = local_ctx.get("plots", [])
    if isinstance(plots, str):
        plots = [plots]

    summary_text_parts = []
    if output_text:
        summary_text_parts.append(output_text)
    if result_obj is not None and not isinstance(result_obj, (str, int, float)):
        summary_text_parts.append(str(result_obj))

    summary_text = "\n".join(summary_text_parts) if summary_text_parts else "Analysis code executed."

    return {
        "status": "ok",
        "summary_text": summary_text,
        "metrics": metrics if isinstance(metrics, dict) else {},
        "plot_paths": plots,
    }


```


==============================
FILE: src\tools\sqlite_tool.py
==============================

```python
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


```


==============================
FILE: tests\test_context_loader.py
==============================

```python
from pathlib import Path

from core.context_loader import load_database_schema, load_markdown_knowledge


def test_load_schema_missing_db(tmp_path: Path):
    schema = load_database_schema(tmp_path / "missing.sqlite")
    assert schema.tables == []


def test_load_markdown_empty(tmp_path: Path):
    knowledge, index = load_markdown_knowledge(tmp_path)
    assert knowledge == ""
    assert index == {}


```

