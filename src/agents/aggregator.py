from __future__ import annotations

import json
import logging

from langchain_openai import ChatOpenAI

from core.models import GraphState


AGGREGATOR_PROMPT = """
You are the final responder for a fab data analysis agent.

Hard rules:
- Health verdict (Healthy/Unhealthy) and drift labels must come ONLY from defects_daily-based analysis steps.
- calibrations and wc_points are supporting evidence only; do not override the verdict.

Output style:
- Keep it compact; preserve markdown tables if present (do NOT rewrite tables into plain bullets).
- If a "domain_explain" step exists, use it as the main body and lightly edit for clarity.
- Otherwise, answer the user question directly using the available step_results (sql_analysis/python_analysis/visualize/rag_qa):
  - Summarize the key numbers/rows/plots; include a short markdown table when helpful.
  - Do NOT force a health/drift verdict for generic data questions.
  - Mention important errors if a step failed.
- Do not include raw SQL or debug.
"""


def aggregator_node(llm: ChatOpenAI, logger: logging.Logger | None = None):
    def _node(state: GraphState) -> GraphState:
        steps = state.get("step_results", [])
        messages = [
            {"role": "system", "content": AGGREGATOR_PROMPT},
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "user_query": state.get("user_query", ""),
                        "clarifications": state.get("clarification_answers", {}),
                        "steps": steps,
                        # ★ include markdown so aggregator can align with your latest rules
                        "markdown": (state.get("markdown_knowledge", "") or "")[:4000],
                    }
                ),
            },
        ]

        response = llm.invoke(messages)
        content = response.content if hasattr(response, "content") else ""
        state["final_answer"] = content

        if logger:
            logger.info("[aggregator] steps=%s answer_len=%s", len(steps), len(content))
        return state

    return _node
