from __future__ import annotations

import json
import logging
from typing import List

from langchain_openai import ChatOpenAI

from core.models import GraphState, StepResult


DOMAIN_EXPERT_PROMPT = """
You are a fab domain expert. Interpret analysis findings using provided Markdown knowledge.
Explain possible root causes, link to equipment or defect rules, and suggest next steps.
Return concise paragraphs and bullets. Avoid fabricating table names.
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
