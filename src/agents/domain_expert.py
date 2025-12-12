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
- If subsystem_mode is true: subsystem health is decided by calibration overdue and wafer-center abnormality only (not defects_daily).

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
        subsystem_mode = bool(state.get("subsystem_mode"))

        # Provide only relevant recent steps + real rows
        payload: Dict[str, Any] = {
            "user_query": state.get("user_query", ""),
            "clarifications": state.get("clarification_answers", {}),
            "defect_drift_weekly": _find_step(findings, "defect_drift_weekly"),
            "calibration_overdue": _find_step(findings, "calibration_overdue"),
            "stage_wc_weekly": _find_step(findings, "stage_wc_weekly"),
            "markdown": markdown[:6000],
            "subsystem_mode": subsystem_mode,
        }

        # Subsystem-specific deterministic formatter
        if subsystem_mode:
            cal_step = payload.get("calibration_overdue") or {}
            wc_step = payload.get("stage_wc_weekly") or {}

            def _rows(step: StepResult | None) -> List[Dict[str, Any]]:
                if not step:
                    return []
                return step.get("rows") or step.get("preview_rows") or []

            cal_rows = _rows(cal_step)  # type: ignore[arg-type]
            wc_rows = _rows(wc_step)  # type: ignore[arg-type]

            overdue_by_sub: Dict[str, List[str]] = {}
            for row in cal_rows:
                try:
                    is_overdue = int(row.get("is_overdue", 0)) == 1  # type: ignore[arg-type]
                except Exception:
                    is_overdue = False
                if not is_overdue:
                    continue
                sub = str(row.get("subsystem", "Unknown"))
                overdue_by_sub.setdefault(sub, []).append(str(row.get("cal_name", "")))

            stage_wc_ratio = 0.0
            stage_wc_seen = False
            for row in wc_rows:
                try:
                    r = float(row.get("wc_abnormal_ratio", 0.0))  # type: ignore[arg-type]
                except Exception:
                    r = 0.0
                stage_wc_ratio = max(stage_wc_ratio, r)
                stage_wc_seen = True

            subsystems = sorted(set(overdue_by_sub.keys()) | {"Stage", "Camera", "Focus", "Illumination"})
            rows_out: List[Dict[str, Any]] = []
            overall_unhealthy = False
            for subsys in subsystems:
                overdue_list = overdue_by_sub.get(subsys, [])
                status = "Healthy"
                notes: List[str] = []
                if overdue_list:
                    status = "Unhealthy"
                    overall_unhealthy = True
                    notes.append(f"Overdue: {', '.join(overdue_list[:3])}" + ("..." if len(overdue_list) > 3 else ""))
                if subsys.lower() == "stage":
                    if stage_wc_seen:
                        notes.append(f"wc_abnormal_ratio={stage_wc_ratio:.4f}")
                    if stage_wc_seen and stage_wc_ratio > 0.05:
                        status = "Unhealthy"
                        overall_unhealthy = True
                        notes.append("Stage wafer-center out-of-spec >5%")
                rows_out.append(
                    {
                        "subsystem": subsys,
                        "status": status,
                        "overdue_count": len(overdue_list),
                        "notes": "; ".join(notes) if notes else "-",
                    }
                )

            status_text = "Unhealthy" if overall_unhealthy else "Healthy"
            tool_guess = ""
            if cal_rows:
                tool_guess = str(cal_rows[0].get("tool", ""))
            elif wc_rows:
                tool_guess = str(wc_rows[0].get("tool", ""))

            table_lines = ["| Subsystem | Status | Overdue Calibrations | Notes |", "|---|---|---|---|"]
            for r in rows_out:
                table_lines.append(
                    f"| {r['subsystem']} | {r['status']} | {r['overdue_count']} | {r['notes']} |"
                )
            table_md = "\n".join(table_lines)
            missing_wc = "" if stage_wc_seen else "\n- No wafer-center data available this week for Stage."
            missing_cal = "" if cal_rows else "\n- No calibration records found for this tool in the window."

            content = (
                f"The subsystem health of tool {tool_guess or '(unknown tool)'} is **{status_text}** "
                f"based on calibration overdue and Stage wafer-center signals.\n\n"
                f"{table_md}\n"
                f"{missing_cal}{missing_wc}"
            )

            step_result: StepResult = {
                "step_id": state.get("next_action", {}).get("id", "domain_explain"),
                "step_type": "domain_explain",
                "summary": content,
                "raw_llm": content,
            }
            state.setdefault("step_results", []).append(step_result)
            state["next_action"] = None

            if logger:
                logger.info("[domain_expert][subsystem] summary_len=%s", len(content))
            return state

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
