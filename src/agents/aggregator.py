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

For questions answered via documentation search (RAG), you may see steps with
step_type "rag_qa" and a "rag_hits" field containing text snippets from manuals.
Use those snippets as primary evidence when forming your answer, but still keep
the reply compact and user-friendly.

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
