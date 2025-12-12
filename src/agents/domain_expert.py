from __future__ import annotations

import json
import logging
from typing import List, Dict, Any

from langchain_openai import ChatOpenAI

from core.models import GraphState, StepResult


DOMAIN_EXPERT_PROMPT = """
You are a fab domain expert. Follow the project's MUST-FOLLOW rules:

- Healthy vs Unhealthy AND Tool Drift vs Process Drift are decided ONLY by defects_daily results.
- calibrations and wc_points are supporting evidence only and must not override the verdict.

Answer format for system health / drift:
1) Verdict (1–2 sentences)
2) Defect-based evidence in a MARKDOWN TABLE (few rows; focus on the target tool's key recipes)
3) Optional next steps (0–2 bullets)

If the user asked about reasons / subsystem:
- Keep the same defect-based verdict unchanged
- Add a short section summarizing:
  - overdue calibrations (if any)
  - wafer-center abnormal ratio (Stage) if > 0.05

Do not dump raw SQL. Do not invent columns/tables.
"""


def _find_step(steps: List[StepResult], step_id: str) -> StepResult | None:
    for s in steps:
        if s.get("step_id") == step_id:
            return s
    return None


def domain_expert_node(llm: ChatOpenAI, logger: logging.Logger | None = None):
    def _node(state: GraphState) -> GraphState:
        findings: List[StepResult] = state.get("step_results", [])
        markdown = state.get("markdown_knowledge", "")

        # Provide only relevant recent steps + real rows
        payload: Dict[str, Any] = {
            "user_query": state.get("user_query", ""),
            "clarifications": state.get("clarification_answers", {}),
            "defect_drift_weekly": _find_step(findings, "defect_drift_weekly"),
            "calibration_overdue": _find_step(findings, "calibration_overdue"),
            "stage_wc_weekly": _find_step(findings, "stage_wc_weekly"),
            "markdown": markdown[:6000],
        }

        messages = [
            {"role": "system", "content": DOMAIN_EXPERT_PROMPT},
            {"role": "user", "content": json.dumps(payload)},
        ]

        response = llm.invoke(messages)
        content = response.content if hasattr(response, "content") else ""

        step_result: StepResult = {
            "step_id": state.get("next_action", {}).get("id", "domain_explain"),
            "step_type": "domain_explain",
            "summary": content,
            "raw_llm": content,
        }
        state.setdefault("step_results", []).append(step_result)

        # Supervisor will decide next; do not force finish here.
        state["next_action"] = None

        if logger:
            logger.info("[domain_expert] summary_len=%s", len(content))
        return state

    return _node
