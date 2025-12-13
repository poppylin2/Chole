from __future__ import annotations

import json
import logging
import re
from typing import Dict, List, Optional

from langchain_openai import ChatOpenAI

from core.models import DatabaseSchema, GraphState, NextAction, StepResult


SUPERVISOR_SYSTEM_PROMPT = """
You are the Supervisor for a fab data analysis agent.

Database (current project):
- defects_daily(date, tool, recipe, pre_defectwise_count, post_defectwise_count)
- calibrations(tool, subsystem, cal_name, last_cal_date, freq_days)
- wc_points(tool, date, timestamp, x, y, recipe)

Rules (must follow):
- Healthy vs Unhealthy AND Tool Drift vs Process Drift are decided ONLY by defects_daily
  using weekly sums (this week vs last week) and diff_pct > 0.10.
- calibrations and wc_points are supporting evidence ONLY and must not override
  the defects_daily-based verdict.
- For any "system/tool health" question, you must know which tool (e.g., 8950XR-P2).
  If tool is missing, ask the user to choose one.
- For other data questions, propose a JSON next action that lets the data_analyst run
  a SQL query on the relevant tables.
Return JSON next action.
"""


TOOL_RE = re.compile(r"\b8950XR-P[1-4]\b", flags=re.IGNORECASE)

# Minimal keyword-to-table mapping to auto-route ad-hoc data lookups
TABLE_KEYWORDS = {
    "defect": "defects_daily",
    "drift": "defects_daily",
    "recipe": "defects_daily",
    "calibration": "calibrations",
    "wafer": "wc_points",
    "wc_": "wc_points",
    "stage": "wc_points",
}


def _infer_tables(user_query: str, schema: DatabaseSchema) -> List[str]:
    ql = (user_query or "").lower()
    seen = set()
    for kw, tbl in TABLE_KEYWORDS.items():
        if kw in ql:
            seen.add(tbl)
    if seen:
        return sorted(seen)
    # Fallback: expose all tables if no keyword matches
    return sorted([t.name for t in schema.tables]) if schema and schema.tables else []


def summarize_results(results: List[StepResult]) -> str:
    parts: List[str] = []
    for res in results[-5:]:
        summary = res.get("summary") or ""
        parts.append(f"{res.get('step_type')}: {summary[:400]}")
    return "\n".join(parts)


def _extract_tool(
    user_query: str,
    clarifications: Dict[str, str],
    last_tool: Optional[str],
    chat_history: Optional[List[Dict[str, str]]] = None,
) -> Optional[str]:
    # 1) prefer explicit tool mention in the current user query
    m = TOOL_RE.search(user_query or "")
    if m:
        return m.group(0).upper()

    # 2) clarification wins (from current pending question)
    for k in ("tool", "tool_id"):
        if k in clarifications:
            v = (clarifications.get(k) or "").strip()
            m = TOOL_RE.search(v)
            if m:
                return m.group(0).upper()

    # 3) fall back to remembered last_tool for follow-up questions
    if last_tool:
        m = TOOL_RE.search(last_tool)
        if m:
            return m.group(0).upper()

    # 4) scan recent chat history for the most recent tool mention
    if chat_history:
        for msg in reversed(chat_history):
            m = TOOL_RE.search(msg.get("content", ""))
            if m:
                return m.group(0).upper()

    return None


def _parse_yyyymmdd(s: str) -> Optional[str]:
    s = (s or "").strip()
    if not re.fullmatch(r"\d{8}", s):
        return None
    return f"{s[0:4]}-{s[4:6]}-{s[6:8]}"


def _extract_date_range(user_query: str) -> Optional[tuple[str, str]]:
    q = user_query or ""
    m = re.search(r"(\d{8})\s*(?:to|\-|~)\s*(\d{8})", q, flags=re.IGNORECASE)
    if not m:
        m = re.search(r"from\s+(\d{8})\s+to\s+(\d{8})", q, flags=re.IGNORECASE)
    if not m:
        return None
    d1 = _parse_yyyymmdd(m.group(1))
    d2 = _parse_yyyymmdd(m.group(2))
    if not d1 or not d2:
        return None
    return d1, d2


def _has_successful_step(state: GraphState, step_id: str) -> bool:
    for s in state.get("step_results", []):
        if s.get("step_id") == step_id and not s.get("error"):
            return True
    return False


def supervisor_node(llm: ChatOpenAI, logger: logging.Logger | None = None):
    def _node(state: GraphState) -> GraphState:
        state["loop_count"] = state.get("loop_count", 0) + 1
        if state["loop_count"] > 20:
            state["next_action"] = {
                "action_type": "finish",
                "id": "auto_finish",
                "description": "Loop guard triggered; finalize.",
            }
            state["pending_clarification"] = None
            return state

        user_query = state.get("user_query", "") or ""
        clarifications = state.get("clarification_answers", {}) or {}
        last_tool = state.get("last_tool", "")
        chat_history = state.get("chat_history", [])

        # ---------------------------------------------------------
        # 0) If there is a deterministic action queue, pop next.
        # ---------------------------------------------------------
        q = state.get("action_queue") or []
        if q:
            nxt = q.pop(0)
            state["action_queue"] = q
            state["next_action"] = nxt
            state["pending_clarification"] = None
            if logger:
                logger.info(
                    "[supervisor][queue] next=%s remaining=%s", nxt.get("id"), len(q)
                )
            return state

        # If ad-hoc SQL already succeeded once, finalize instead of re-running it 20 times.
        if _has_successful_step(state, "ad_hoc_sql"):
            state["next_action"] = {
                "action_type": "finish",
                "id": "finish",
                "description": "Summarize existing SQL result.",
            }
            state["pending_clarification"] = None
            return state

        # ---------------------------------------------------------
        # 1) Deterministic routing for system/tool health flows
        # ---------------------------------------------------------
        ql = user_query.lower()
        is_health = any(
            k in ql
            for k in [
                "system health",
                "tool health",
                "how's the system",
                "health",
                "drift",
            ]
        )
        is_reason = any(
            k in ql
            for k in [
                "why",
                "reason",
                "root cause",
                "calibration",
                "overdue",
                "wafer",
                "wc_",
                "stage",
                "subsystem",
            ]
        )
        is_trend = any(
            k in ql for k in ["trend", "line chart", "plot", "graph", "折线", "趋势"]
        )
        is_subsystem = any(
            k in ql
            for k in [
                "subsystem",
                "sub-system",
                "stage health",
                "wafer center",
                "wc_points",
            ]
        )

        tool = _extract_tool(user_query, clarifications, last_tool, chat_history)

        # Health queries must have tool
        if is_health:
            if not tool:
                state["next_action"] = {
                    "action_type": "ask_user",
                    "id": "tool",
                    "description": "Need tool to answer system health.",
                    "clarification_question": "Which tool do you want me to check? (8950XR-P1, 8950XR-P2, 8950XR-P3, 8950XR-P4)",
                }
                state["pending_clarification"] = {
                    "id": "tool",
                    "question": state["next_action"]["clarification_question"],  # type: ignore[index]
                }
                state["subsystem_mode"] = False
                return state

            # Subsystem-only health path: focus on calibrations + wafer-center
            if is_subsystem:
                queue: List[NextAction] = [
                    {
                        "action_type": "sql_analysis",
                        "id": "calibration_overdue",
                        "description": "Check overdue calibrations (subsystem health).",
                        "tables": ["calibrations"],
                        "tool": tool,
                    },
                    {
                        "action_type": "sql_analysis",
                        "id": "stage_wc_weekly",
                        "description": "Summarize wafer-center abnormal ratio for Stage subsystem.",
                        "tables": ["wc_points"],
                        "tool": tool,
                    },
                    {
                        "action_type": "domain_explain",
                        "id": "domain_explain",
                        "description": "Explain subsystem health using calibration and wafer-center only.",
                    },
                    {
                        "action_type": "finish",
                        "id": "finish",
                        "description": "Wrap up subsystem health answer.",
                    },
                ]
                state["action_queue"] = queue
                state["next_action"] = state["action_queue"].pop(0)
                state["pending_clarification"] = None
                state["subsystem_mode"] = True
                state["last_tool"] = tool
                if logger:
                    logger.info("[supervisor][subsystem] tool=%s queued=%s", tool, len(queue))
                return state

            # Build deterministic plan:
            queue: List[NextAction] = [
                {
                    "action_type": "sql_analysis",
                    "id": "defect_drift_weekly",
                    "description": "Compute weekly defect sums and drift classification (defects_daily only).",
                    "tables": ["defects_daily"],
                    "tool": tool,
                }
            ]
            if is_reason:
                queue.extend(
                    [
                        {
                            "action_type": "sql_analysis",
                            "id": "calibration_overdue",
                            "description": "Check overdue calibrations (supporting evidence only).",
                            "tables": ["calibrations"],
                            "tool": tool,
                        },
                        {
                            "action_type": "sql_analysis",
                            "id": "stage_wc_weekly",
                            "description": "Summarize wafer-center abnormal ratio for this week (supporting evidence only).",
                            "tables": ["wc_points"],
                            "tool": tool,
                        },
                    ]
                )
            queue.append(
                {
                    "action_type": "domain_explain",
                    "id": "domain_explain",
                    "description": "Explain findings and format the answer per rules (verdict + evidence table).",
                }
            )
            queue.append(
                {
                    "action_type": "finish",
                    "id": "finish",
                    "description": "Summarize and return final answer.",
                }
            )

            state["action_queue"] = queue
            state["next_action"] = state["action_queue"].pop(0)
            state["pending_clarification"] = None
            state["subsystem_mode"] = False
            state["last_tool"] = tool
            if logger:
                logger.info(
                    "[supervisor][health] tool=%s reason=%s queued=%s",
                    tool,
                    is_reason,
                    len(queue),
                )
            return state

        # ---------------------------------------------------------
        # 2) Deterministic routing for defect-rate trend chart requests
        #    (optional but useful for your README examples)
        # ---------------------------------------------------------
        if is_trend and tool:
            dr = _extract_date_range(user_query)
            if dr:
                dfrom, dto = dr
                queue2: List[NextAction] = [
                    {
                        "action_type": "sql_analysis",
                        "id": "defect_trend_range",
                        "description": "Fetch daily defect totals in date range for plotting defect_rate.",
                        "tables": ["defects_daily"],
                        "tool": tool,
                        "date_from": dfrom,
                        "date_to": dto,
                    },
                    {
                        "action_type": "visualize",
                        "id": "visualize",
                        "description": "Create a line chart for defect_rate over time.",
                        "chart_type_hint": "line",
                    },
                    {
                        "action_type": "finish",
                        "id": "finish",
                        "description": "Finalize with plot and short summary.",
                    },
                ]
                state["action_queue"] = queue2
                state["next_action"] = state["action_queue"].pop(0)
                state["pending_clarification"] = None
                state["last_tool"] = tool
                return state

        # ---------------------------------------------------------
        # 2b) Manual / how-to style questions → go straight to RAG
        # ---------------------------------------------------------
        rag_intent_tokens = [
            "install",
            "setup",
            "open",
            "launch",
            "start",
            "how to",
            "manual",
            "guide",
            "operate",
            "troubleshoot",
        ]
        if any(tok in ql for tok in rag_intent_tokens):
            rag_action: NextAction = {
                "action_type": "rag_qa",
                "id": "rag_manual",
                "description": "Search manuals for instructions.",
                "top_k": 6,
            }
            state["action_queue"] = [
                rag_action,
                {
                    "action_type": "finish",
                    "id": "finish",
                    "description": "Summarize RAG findings.",
                },
            ]
            state["next_action"] = state["action_queue"].pop(0)
            state["pending_clarification"] = None
            return state

        # ---------------------------------------------------------
        # 3) Generic ad-hoc data lookup: give the data analyst a shot
        # ---------------------------------------------------------
        schema: DatabaseSchema = state.get("database_schema", DatabaseSchema(tables=[]))  # type: ignore
        inferred_tables = _infer_tables(user_query, schema)
        # A lightweight heuristic: if the query mentions data-ish keywords or we can infer tables,
        # let the SQL agent try first before the generic LLM handoff.
        dataish = any(
            k in ql
            for k in [
                "defect",
                "calibration",
                "wafer",
                "table",
                "count",
                "sum",
                "date",
                "recipe",
                "trend",
            ]
        )
        if dataish and inferred_tables:
            state["action_queue"] = []
            state["next_action"] = {
                "action_type": "sql_analysis",
                "id": "ad_hoc_sql",
                "description": "Ad-hoc SQL lookup based on user question.",
                "tables": inferred_tables,
                # pass through tool hint if present; SQL agent can choose to use it
                "tool": tool,
            }
            state["pending_clarification"] = None
            return state

        # ---------------------------------------------------------
        # 4) Otherwise fall back to the LLM supervisor (generic questions, RAG, etc.)
        # ---------------------------------------------------------
        schema: DatabaseSchema = state.get("database_schema", DatabaseSchema(tables=[]))  # type: ignore
        schema_text = json.dumps(schema.to_dict())
        markdown = state.get("markdown_knowledge", "")
        previous = summarize_results(state.get("step_results", []))
        chat_history = state.get("chat_history") or []
        history_text = "\n".join(
            f"{m.get('role', '')}: {m.get('content', '')}" for m in chat_history[-12:]
        )

        messages = [
            {"role": "system", "content": SUPERVISOR_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": (
                    f"User query:\n{user_query}\n\n"
                    f"Clarification answers:\n{json.dumps(clarifications)}\n\n"
                    f"Conversation history (oldest→newest, capped):\n{history_text}\n\n"
                    f"Database schema:\n{schema_text}\n\n"
                    f"Markdown knowledge:\n{markdown[:4000]}\n\n"
                    f"Recent results:\n{previous}"
                ),
            },
        ]

        response = llm.invoke(messages)
        content = response.content if hasattr(response, "content") else ""

        next_action: NextAction = {
            "action_type": "finish",
            "id": "finish",
            "description": "Provide final answer.",
        }
        try:
            parsed = json.loads(content)
            if isinstance(parsed, dict) and "action_type" in parsed:
                next_action = parsed  # type: ignore
        except json.JSONDecodeError:
            next_action = {
                "action_type": "finish",
                "id": "finish",
                "description": f"Could not parse action. Raw: {content[:300]}",
            }

        state["next_action"] = next_action

        if next_action.get("action_type") == "ask_user":
            state["pending_clarification"] = {
                "id": next_action.get("id", "clarify"),
                "question": next_action.get(
                    "clarification_question", "Please provide more detail."
                ),
            }
        else:
            state["pending_clarification"] = None

        return state

    return _node
