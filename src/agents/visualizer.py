from __future__ import annotations

import json
import logging
import uuid
from typing import Dict, List

from langchain_openai import ChatOpenAI

from core.models import GraphState, StepResult
from tools.python_tool import run_python_analysis


VISUALIZER_PROMPT = """
You are a visualization specialist.
Inputs you will receive:
- target_dataset_id: dataset id to plot.
- datasets: mapping dataset_id -> csv_path.
- dataset_columns: list of column names for the target dataset.
- dataset_sample: small preview rows for the target dataset.
- user_question: original user query.
- chart_type_hint: optional hint like "line", "bar", "stacked", "scatter".

Hard rules:
- Use ONLY columns that exist in dataset_columns.
- Load CSV with pandas using datasets[target_dataset_id].
- If needed, create derived columns (e.g., defect_rate = total_defects / total_runs).
- Treat dates as strings or pandas datetime, not bare integers (avoid leading-zero numeric literals).
- Use simple filters consistent with available columns; do NOT invent columns (e.g., 'product', 'defect_rate' if absent).
- Make 1 plot unless multiple series warrant up to 2; avoid more than 3.
- Always call save_plot() for each figure and set plots = [path1, ...].
- Populate metrics with small summaries (min/max/mean) of plotted series.
- Keep code concise; only pandas/matplotlib; no network or external file writes.
- Return only JSON with keys: code (string), rationale (string).
"""


def strip_code_fence(text: str) -> str:
    """Remove leading/trailing fences like ```json ... ``` while keeping inner content."""
    t = text.strip()
    if t.startswith("```"):
        # Drop initial fence and optional language tag up to first newline
        parts = t.split("\n", 1)
        t = parts[1] if len(parts) > 1 else ""
    if t.endswith("```"):
        t = t[: t.rfind("```")]
    return t.strip()


def extract_code(text: str) -> str:
    """Extract Python code from JSON or fenced blocks."""
    cleaned = strip_code_fence(text)
    try:
        parsed = json.loads(cleaned)
        if isinstance(parsed, dict) and "code" in parsed:
            return parsed["code"]
    except Exception:
        pass
    return cleaned


def visualizer_node(llm: ChatOpenAI, runtime_cache) -> callable:
    """Build a visualizer node that generates plots using python_tool."""

    logger: logging.Logger | None = runtime_cache and logging.getLogger("fab_agent")

    def _node(state: GraphState) -> GraphState:
        action = state.get("next_action") or {}
        if action.get("action_type") != "visualize":
            return state

        datasets = {k: v["csv_path"] for k, v in state.get("data_artifacts", {}).items()}
        target_dataset_id = action.get("target_dataset_id") or next(
            iter(datasets.keys()), None
        )

        step_result: StepResult = {
            "step_id": action.get("id", "visualize"),
            "step_type": "visualize",
            "summary": action.get("description", "Create visualization."),
        }

        if not datasets or not target_dataset_id or target_dataset_id not in datasets:
            step_result["error"] = "No dataset available for visualization."
            state.setdefault("step_results", []).append(step_result)
            state["next_action"] = None
            if logger:
                logger.warning("[visualizer] missing dataset for plotting.")
            return state

        # Provide column info and a tiny sample to reduce hallucination
        artifacts = state.get("data_artifacts", {})
        target_artifact = artifacts.get(target_dataset_id, {})
        dataset_columns: List[str] = target_artifact.get("columns", [])
        dataset_sample: List[Dict] = target_artifact.get("sample_preview", [])  # type: ignore

        messages = [
            {"role": "system", "content": VISUALIZER_PROMPT},
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "target_dataset_id": target_dataset_id,
                        "datasets": datasets,
                        "dataset_columns": dataset_columns,
                        "dataset_sample": dataset_sample,
                        "user_question": state.get("user_query", ""),
                        "chart_type_hint": action.get("chart_type_hint"),
                    }
                ),
            },
        ]

        response = llm.invoke(messages)
        raw_llm = getattr(response, "content", "") or ""
        code = extract_code(raw_llm)
        rationale = "Generated plot code."
        try:
            parsed = json.loads(raw_llm)
            rationale = parsed.get("rationale", rationale)
        except Exception:
            pass

        code_path = None
        try:
            safe_id = str(action.get("id", "visualize")).replace(" ", "_")[:50]
            code_path = runtime_cache / f"plot_code_{safe_id}_{uuid.uuid4().hex[:8]}.py"
            code_path.write_text(code, encoding="utf-8")
        except Exception as exc:  # best-effort; don't break flow
            if logger:
                logger.warning("[visualizer] failed to write code file: %s", exc)

        result = run_python_analysis(code, datasets, runtime_cache)
        if result.get("status") == "ok":
            step_result["summary"] = f"{rationale}\n{result.get('summary_text','')}"
            step_result["metrics"] = result.get("metrics")
            step_result["plots"] = result.get("plot_paths")
        else:
            step_result["error"] = result.get("error_message", "Visualization failed.")
            step_result["summary"] = rationale

        step_result["raw_llm"] = raw_llm
        if code_path:
            step_result["code_path"] = str(code_path)

        state.setdefault("step_results", []).append(step_result)
        state["next_action"] = None

        if logger:
            logger.info(
                "[visualizer][llm] %s", raw_llm[:500].replace("\n", " ")
            )
            logger.info(
                "[visualizer] step_id=%s status=%s plots=%s error=%s code_path=%s",
                step_result["step_id"],
                result.get("status"),
                result.get("plot_paths"),
                result.get("error_message"),
                code_path,
            )
        return state

    return _node
