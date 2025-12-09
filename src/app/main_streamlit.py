from __future__ import annotations

import json
from typing import Dict, List

import streamlit as st

from graph.graph_builder import stream_graph

st.set_page_config(page_title="Fab Data Analysis Agent", layout="wide")
st.title("Fab Data Analysis Agent")

# ----- Initialize session states -----
if "messages" not in st.session_state:
    st.session_state.messages = []
if "clarification_answers" not in st.session_state:
    st.session_state.clarification_answers: Dict[str, str] = {}
if "pending_clarification" not in st.session_state:
    st.session_state.pending_clarification = None
if "last_user_query" not in st.session_state:
    st.session_state.last_user_query = ""


# ----- Dynamic node construction & rendering -----

def build_pipeline_nodes(
    step_results: List[Dict],
    final_answer: str | None,
    pending_clarification: Dict | None,
) -> List[Dict[str, str]]:
    """
    Dynamically build a sequence of nodes based on the current state,
    including step_results / final_answer / pending_clarification.

    Example:
      Plan / Supervisor
      → SQL Analysis #1
      → Domain Explain #1
      → SQL Analysis #2
      → Final Answer
    """
    nodes: List[Dict[str, str]] = []

    # Always start with a "Plan / Supervisor" node
    nodes.append({"id": "plan", "label": "Plan / Supervisor"})

    # Append nodes according to step_results, preserving order,
    # and automatically numbering nodes of the same step_type.
    type_counts: Dict[str, int] = {
        "sql_analysis": 0,
        "python_analysis": 0,
        "domain_explain": 0,
    }

    for idx, step in enumerate(step_results):
        stype = step.get("step_type")
        if stype not in ("sql_analysis", "python_analysis", "domain_explain", "finish"):
            continue

        if stype in type_counts:
            type_counts[stype] += 1
            num = type_counts[stype]
        else:
            num = 1

        if stype == "sql_analysis":
            label = f"SQL Analysis #{num}"
        elif stype == "python_analysis":
            label = f"Python Analysis #{num}"
        elif stype == "domain_explain":
            label = f"Domain Explain #{num}"
        elif stype == "finish":
            label = "Finish"
        else:
            label = stype

        nodes.append({"id": f"{stype}_{idx}", "label": label})

    # If the graph execution ends with an ask_user step (pending_clarification exists and no final_answer yet)
    if pending_clarification and not final_answer:
        nodes.append({"id": "clarify", "label": "Clarification Needed"})

    # If a final answer exists, add a Final Answer node
    if final_answer:
        nodes.append({"id": "aggregator", "label": "Final Answer"})

    return nodes


def infer_dynamic_status(nodes: List[Dict[str, str]]) -> Dict[str, str]:
    """
    Assign status to each node:
    - All nodes except the last: done
    - Last node: current

    We do NOT draw "future todo nodes" because Supervisor's decisions are dynamic.
    """
    status: Dict[str, str] = {}
    if not nodes:
        return status

    last_index = len(nodes) - 1
    for idx, node in enumerate(nodes):
        nid = node["id"]
        if idx < last_index:
            status[nid] = "done"
        else:
            status[nid] = "current"
    return status


def render_pipeline(nodes: List[Dict[str, str]], status: Dict[str, str]) -> str:
    """
    Render nodes + status into a horizontal HTML progress bar.
    done = green, current = blue.
    """
    css = """
    <style>
    .pipeline-container {
        display: flex;
        align-items: center;
        margin-bottom: 1rem;
        font-size: 0.9rem;
        flex-wrap: wrap;
        row-gap: 0.5rem;
    }
    .pipeline-step {
        display: flex;
        flex-direction: column;
        align-items: center;
        min-width: 120px;
    }
    .pipeline-circle {
        width: 20px;
        height: 20px;
        border-radius: 999px;
        border: 2px solid #999999;
        margin-bottom: 4px;
    }
    .pipeline-label {
        text-align: center;
        max-width: 160px;
        white-space: normal;
    }
    .pipeline-connector {
        flex: 0 0 40px;
        height: 2px;
        background-color: #e0e0e0;
        margin: 0 8px;
    }
    .pipeline-circle.done {
        background-color: #34a853;
        border-color: #34a853;
    }
    .pipeline-circle.current {
        background-color: #4285f4;
        border-color: #4285f4;
    }
    .pipeline-label.done {
        color: #34a853;
        font-weight: 600;
    }
    .pipeline-label.current {
        color: #4285f4;
        font-weight: 600;
    }
    .pipeline-circle.todo {
        background-color: #f5f5f5;
        border-color: #999999;
    }
    .pipeline-label.todo {
        color: #999999;
    }
    </style>
    """

    parts = [css, '<div class="pipeline-container">']
    for idx, node in enumerate(nodes):
        nid = node["id"]
        label = node["label"]
        s = status.get(nid, "todo")

        circle_class = f"pipeline-circle {s}"
        label_class = f"pipeline-label {s}"

        parts.append('<div class="pipeline-step">')
        parts.append(f'<div class="{circle_class}"></div>')
        parts.append(f'<div class="{label_class}">{label}</div>')
        parts.append("</div>")

        # Draw connector lines between nodes
        if idx < len(nodes) - 1:
            prev_status = status.get(nid, "todo")
            connector_color = "#e0e0e0"
            if prev_status in ("done", "current"):
                connector_color = "#34a853"
            parts.append(
                f'<div class="pipeline-connector" style="background-color:{connector_color};"></div>'
            )

    parts.append("</div>")
    return "".join(parts)


# ----- Render conversation history -----

def render_history():
    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])
            if msg.get("debug"):
                with st.expander("Debug details"):
                    st.write(msg["debug"])


render_history()

# ----- Input box -----
prompt = st.chat_input("Ask about fab inspection data or equipment insights")

if prompt:
    user_query = prompt
    clarification_payload = dict(st.session_state.clarification_answers)

    # If currently answering a clarification question
    if st.session_state.pending_clarification:
        clar_id = st.session_state.pending_clarification.get("id")
        if clar_id:
            clarification_payload[clar_id] = prompt
            st.session_state.clarification_answers[clar_id] = prompt
        user_query = st.session_state.last_user_query or prompt
        st.session_state.pending_clarification = None
    else:
        # New user query
        st.session_state.last_user_query = user_query

    # Store user message
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    try:
        final_state = None
        final_debug_info = None

        # Assistant message: live-updating pipeline + answer
        with st.chat_message("assistant"):
            pipeline_placeholder = st.empty()
            answer_placeholder = st.empty()

            # ★ Stream graph execution and update UI nodes at each step
            for state in stream_graph(
                user_query, clarification_answers=clarification_payload
            ):
                final_state = state

                step_results = state.get("step_results", [])
                final_answer = state.get("final_answer")
                pending = state.get("pending_clarification")

                nodes = build_pipeline_nodes(step_results, final_answer, pending)
                node_status = infer_dynamic_status(nodes)
                pipeline_html = render_pipeline(nodes, node_status)
                pipeline_placeholder.markdown(pipeline_html, unsafe_allow_html=True)

                if final_answer:
                    answer_placeholder.markdown(final_answer)

            # Final state after graph execution completes
            if final_state is None:
                final_answer = "No answer generated."
                step_results = []
                datasets = {}
                pending = None
            else:
                final_answer = final_state.get("final_answer")
                step_results = final_state.get("step_results", [])
                datasets = final_state.get("data_artifacts", {})
                pending = final_state.get("pending_clarification")

            final_debug_info = {
                "actions": [step.get("step_type") for step in step_results],
                "steps": step_results,
                "datasets": datasets,
            }

            # If this round requires clarification, show the clarification question instead of the final answer
            if pending and not final_answer:
                question = pending.get("question", "Please provide more detail.")
                answer_placeholder.markdown(question)
            elif final_answer:
                answer_placeholder.markdown(final_answer)
            else:
                answer_placeholder.markdown("No answer generated.")

            with st.expander("Debug details"):
                # st.write(json.dumps(final_debug_info, indent=2))
                st.json(final_debug_info, expanded=2)

        # ----- Update stored assistant messages -----
        if final_state is None:
            st.session_state.pending_clarification = None
            st.session_state.last_user_query = user_query
        else:
            pending = final_state.get("pending_clarification")
            if pending and not final_answer:
                st.session_state.pending_clarification = pending
                content_to_store = pending.get("question", "Please provide more detail.")
            else:
                st.session_state.pending_clarification = None
                content_to_store = final_answer or "No answer generated."

            msg = {
                "role": "assistant",
                "content": content_to_store,
                "debug": (
                    json.dumps(final_debug_info, indent=2) if final_debug_info else None
                ),
            }
            st.session_state.messages.append(msg)

    except Exception as exc:
        error_text = (
            "An error occurred while processing your request. "
            "Please try again.\n\n"
            f"Error: {exc}"
        )
        st.session_state.messages.append({"role": "assistant", "content": error_text})
        with st.chat_message("assistant"):
            st.markdown(error_text)
        st.session_state.pending_clarification = None
        st.session_state.last_user_query = user_query
        st.stop()
