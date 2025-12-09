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
