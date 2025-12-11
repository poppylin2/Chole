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
- "visualize": plot datasets (line/bar/scatter) using matplotlib via the python tool.
- "rag_qa": run RAG search over equipment manuals / PDFs and prepare context for answering.
- "ask_user": request a clarification question and stop the loop.
- "finish": finalize and hand off to result aggregator.

RAG vs data rules:
- Use "rag_qa" when the user is asking about manuals, troubleshooting steps, how-to
  procedures, parameter meanings, configuration options, or conceptual questions that
  are likely answered by documentation (PDF manuals).
- Use "sql_analysis" / "python_analysis" when the question clearly requires looking at
  recent inspection_runs, drift patterns, defect/align ratios, or other numeric analytics.
- RAG and database analytics are independent; do NOT try to mix them in the same step.
- For visualization/trend/compare questions ("趋势", "trend", "chart", "plot", "对比"):
  - If no dataset exists yet → pick "sql_analysis" first to fetch data.
  - If a dataset exists and no plot has been created → pick "visualize" with
    target_dataset_id set to the dataset you want to plot.
  - Do not keep repeating visualize once a plot step exists; then move to "finish" or "domain_explain".

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

        # If we already have RAG results, don't loop endlessly—go straight to finish.
        rag_steps = [
            s for s in state.get("step_results", []) if s.get("step_type") == "rag_qa"
        ]
        if rag_steps:
            state["next_action"] = {
                "action_type": "finish",
                "id": "finish_rag",
                "description": "RAG search completed; aggregate the manual snippets for the user.",
            }
            state["pending_clarification"] = None
            if logger:
                logger.info(
                    "[supervisor] rag_qa already ran (%s steps); finishing to avoid loops.",
                    len(rag_steps),
                )
            return state

        def _has_visualization_step() -> bool:
            return any(s.get("step_type") == "visualize" for s in state.get("step_results", []))

        def _needs_visualization(query: str) -> bool:
            if _has_visualization_step():
                return False
            q = (query or "").lower()
            keywords = [
                "trend",
                "over time",
                "time series",
                "chart",
                "plot",
                "graph",
                "compare",
                "comparison",
                "bar",
                "line",
                "折线",
                "柱状",
                "趋势",
                "对比",
                "变化",
            ]
            return any(k in q for k in keywords)

        # If user intent is visualization and data already exists, route to visualizer once.
        if _needs_visualization(state.get("user_query", "")):
            data_artifacts = state.get("data_artifacts", {})
            if data_artifacts:
                # Pick the most recent dataset_id
                target_dataset_id = next(reversed(data_artifacts.keys()))
                state["next_action"] = {
                    "action_type": "visualize",
                    "id": "visualize",
                    "description": "Create plots for the latest dataset to answer the question.",
                    "target_dataset_id": target_dataset_id,
                }
                state["pending_clarification"] = None
                if logger:
                    logger.info(
                        "[supervisor] visualization intent detected; routing to visualizer with dataset=%s",
                        target_dataset_id,
                    )
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
            # Fallback: default to finish with note.
            next_action = {
                "action_type": "finish",
                "id": "finish",
                "description": f"Could not parse action, finish. Raw response: {content}",
            }

        state["next_action"] = next_action
        # Avoid repeated visualize loops; if we already attempted visualize, finish instead.
        if next_action.get("action_type") == "visualize" and _has_visualization_step():
            next_action = {
                "action_type": "finish",
                "id": "finish_after_visualize",
                "description": "Visualization already attempted; proceed to final answer.",
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
