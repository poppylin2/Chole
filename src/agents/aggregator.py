from __future__ import annotations

import json
import logging

from langchain_openai import ChatOpenAI

from core.models import GraphState


AGGREGATOR_PROMPT = """
You are the final responder. Summarize the analysis for the user.
Provide a concise overview, key findings, and recommendations.
Mention datasets or tables used when helpful. Keep the tone clear and actionable.
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
