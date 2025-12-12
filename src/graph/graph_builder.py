from __future__ import annotations

from typing import Dict, Iterator, Optional

from langchain_openai import ChatOpenAI
from langgraph.graph import END, StateGraph

from agents.aggregator import aggregator_node
from agents.data_analyst import data_analyst_node
from agents.domain_expert import domain_expert_node
from agents.supervisor import supervisor_node
from core.config import AppConfig, load_config
from core.context_loader import load_database_schema, load_markdown_knowledge
from core.logging_utils import setup_logging
from core.models import DatabaseSchema, GraphState
from agents.rag_qa import rag_qa_node
from agents.visualizer import visualizer_node

from tools.rag_tool import RagTool, RagToolConfig


def build_graph(
    config: AppConfig,
    schema: DatabaseSchema,
    markdown_knowledge: str,
    table_markdown_index: Dict[str, str],
    logger=None,
):
    llm = ChatOpenAI(model=config.model, temperature=0)

    graph = StateGraph(GraphState)

    rag_tool = RagTool(
        RagToolConfig(
            chroma_dir=config.chroma_dir or (config.runtime_cache / "chroma"),
            embedding_model=config.rag_embedding_model,
            collection_name="manual",
        )
    )

    graph.add_node("supervisor", supervisor_node(llm, logger=logger))
    graph.add_node(
        "data_analyst",
        data_analyst_node(
            llm,
            db_path=config.db_path,
            runtime_cache=config.runtime_cache,
            table_markdown_index=table_markdown_index,
            max_rows=config.max_sql_rows,
        ),
    )
    graph.add_node("domain_expert", domain_expert_node(llm, logger=logger))
    graph.add_node("aggregator", aggregator_node(llm, logger=logger))
    graph.add_node(
        "visualizer", visualizer_node(llm, runtime_cache=config.runtime_cache)
    )
    graph.add_node("rag_qa", rag_qa_node(rag_tool=rag_tool, logger=logger))

    def ask_user_node(state: GraphState) -> GraphState:
        return state

    graph.add_node("ask_user", ask_user_node)

    def route_supervisor(state: GraphState) -> str:
        action = state.get("next_action") or {}
        action_type = action.get("action_type")
        if action_type in {"sql_analysis", "python_analysis"}:
            return "data_analyst"
        if action_type == "domain_explain":
            return "domain_expert"
        if action_type == "rag_qa":
            return "rag_qa"
        if action_type == "visualize":
            return "visualizer"
        if action_type == "ask_user":
            return "ask_user"
        return "aggregator"

    graph.set_entry_point("supervisor")
    graph.add_conditional_edges(
        "supervisor",
        route_supervisor,
        {
            "data_analyst": "data_analyst",
            "domain_expert": "domain_expert",
            "rag_qa": "rag_qa",
            "visualizer": "visualizer",
            "ask_user": "ask_user",
            "aggregator": "aggregator",
        },
    )
    graph.add_edge("data_analyst", "supervisor")
    graph.add_edge("domain_expert", "supervisor")
    graph.add_edge("rag_qa", "supervisor")
    graph.add_edge("visualizer", "supervisor")
    graph.add_edge("aggregator", END)
    graph.add_edge("ask_user", END)

    return graph.compile()


def _init_app_and_state(
    user_query: str,
    clarification_answers: Optional[Dict[str, str]] = None,
):
    config = load_config()
    logger = setup_logging(config.runtime_cache / "agent.log")
    schema = load_database_schema(config.db_path)
    markdown_knowledge, table_markdown_index = load_markdown_knowledge(config.docs_path)

    initial_state: GraphState = {
        "user_query": user_query,
        "database_schema": schema,
        "markdown_knowledge": markdown_knowledge,
        "table_markdown_index": table_markdown_index,
        "clarification_answers": clarification_answers or {},
        "step_results": [],
        "data_artifacts": {},
        "next_action": None,
        "action_queue": [],  # ★ new
        "pending_clarification": None,
        "final_answer": None,
        "loop_count": 0,
    }

    app = build_graph(
        config, schema, markdown_knowledge, table_markdown_index, logger=logger
    )
    return app, initial_state


def run_graph_once(
    user_query: str,
    clarification_answers: Optional[Dict[str, str]] = None,
) -> GraphState:
    app, initial_state = _init_app_and_state(user_query, clarification_answers)
    return app.invoke(initial_state, config={"recursion_limit": 60})


def stream_graph(
    user_query: str,
    clarification_answers: Optional[Dict[str, str]] = None,
) -> Iterator[GraphState]:
    app, initial_state = _init_app_and_state(user_query, clarification_answers)
    for state in app.stream(
        initial_state,
        config={"recursion_limit": 60},
        stream_mode="values",
    ):
        yield state
