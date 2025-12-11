from __future__ import annotations

import logging
from typing import Any, Dict, List

from core.models import GraphState, StepResult
from tools.rag_tool import RagTool


def rag_qa_node(rag_tool: RagTool, logger: logging.Logger | None = None):
    """
    RAG node:
    - Use the current user_query to fetch top-k manual chunks from Chroma.
    - Store results in step_results for the Aggregator to craft the final answer.
    """

    def _node(state: GraphState) -> GraphState:
        query = state.get("user_query", "") or ""
        action = state.get("next_action") or {}
        top_k = int(action.get("top_k", 5))

        rag_result = rag_tool.search(query=query, top_k=top_k)
        hits: List[Dict[str, Any]] = rag_result.get("results", [])

        # Record into step_results; Aggregator will consume this structure
        step_result: StepResult = {
            "step_id": action.get("id", "rag_qa"),
            "step_type": "rag_qa",
            "summary": f"Retrieved {len(hits)} manual chunks for the question.",
            "metrics": {
                "top_scores": [h.get("score", 0.0) for h in hits],
            },
            "rag_hits": hits,  # type: ignore[typeddict-item]
        }

        state.setdefault("step_results", []).append(step_result)

        # After RAG we can usually finish and let Aggregator produce the final answer
        state["next_action"] = {
            "action_type": "finish",
            "id": "finish",
            "description": "Aggregate RAG results for the user.",
        }

        if logger:
            logger.info("[rag_qa] query=%r hits=%s", query, len(hits))

        return state

    return _node
