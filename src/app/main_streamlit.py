from __future__ import annotations

import json
from typing import Dict

import streamlit as st

from graph.graph_builder import stream_graph

st.set_page_config(page_title="Fab Data Analysis Agent", layout="wide")
st.title("Fab Data Analysis Agent")

# ----- Initialize session state -----
if "messages" not in st.session_state:
    st.session_state.messages = []
if "clarification_answers" not in st.session_state:
    st.session_state.clarification_answers: Dict[str, str] = {}
if "pending_clarification" not in st.session_state:
    st.session_state.pending_clarification = None
if "last_user_query" not in st.session_state:
    st.session_state.last_user_query = ""

# ----- Define pipeline node model for progress bar -----
PIPELINE_NODES = [
    {"id": "supervisor", "label": "1. Plan / Route"},
    {"id": "data_analyst", "label": "2. Data Analysis"},
    {"id": "domain_expert", "label": "3. Domain Expert"},
    {"id": "aggregator", "label": "4. Final Answer"},
]


def infer_pipeline_status(step_results, final_answer: str | None):
    """
    Infer each node's status based on step_results and final_answer:
    - 'done'
    - 'current'
    - 'todo'
    """
    status = {node["id"]: "todo" for node in PIPELINE_NODES}

    has_sql_or_py = any(
        s.get("step_type") in ("sql_analysis", "python_analysis") for s in step_results
    )
    has_domain = any(s.get("step_type") == "domain_explain" for s in step_results)

    # As long as execution has started, consider Supervisor as done
    if step_results or final_answer or has_sql_or_py or has_domain:
        status["supervisor"] = "done"

    if has_sql_or_py:
        status["data_analyst"] = "done"

    if has_domain:
        status["domain_expert"] = "done"

    if final_answer:
        status["aggregator"] = "done"

    ordered_ids = [n["id"] for n in PIPELINE_NODES]
    done_indices = [i for i, nid in enumerate(ordered_ids) if status[nid] == "done"]

    if not done_indices:
        # Before starting, the current node is supervisor
        status["supervisor"] = "current"
    else:
        last_done_idx = max(done_indices)
        # If there is no final answer yet, the next node is current
        if last_done_idx < len(ordered_ids) - 1 and not final_answer:
            next_id = ordered_ids[last_done_idx + 1]
            status[next_id] = "current"
        else:
            # Already at the last done node
            status[ordered_ids[last_done_idx]] = "current"

    return status


def render_pipeline(status: Dict[str, str]) -> str:
    """
    Render node status as a horizontal HTML progress bar.
    done = green, current = blue, todo = gray.
    """
    css = """
    <style>
    .pipeline-container {
        display: flex;
        align-items: center;
        margin-bottom: 1rem;
        font-size: 0.9rem;
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
        max-width: 140px;
        white-space: normal;
    }
    .pipeline-connector {
        flex: 1;
        height: 2px;
        background-color: #e0e0e0;
        margin: 0 8px;
    }
    .pipeline-circle.done {
        background-color: #34a853;  /* green */
        border-color: #34a853;
    }
    .pipeline-circle.current {
        background-color: #4285f4;  /* blue */
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
    for idx, node in enumerate(PIPELINE_NODES):
        nid = node["id"]
        label = node["label"]
        s = status.get(nid, "todo")

        circle_class = f"pipeline-circle {s}"
        label_class = f"pipeline-label {s}"

        parts.append('<div class="pipeline-step">')
        parts.append(f'<div class="{circle_class}"></div>')
        parts.append(f'<div class="{label_class}">{label}</div>')
        parts.append("</div>")

        # Connector between nodes
        if idx < len(PIPELINE_NODES) - 1:
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
    # Bring in previously recorded clarification answers
    clarification_payload = dict(st.session_state.clarification_answers)

    # If we are currently answering a clarification question, record this input under the corresponding clar_id
    if st.session_state.pending_clarification:
        clar_id = st.session_state.pending_clarification.get("id")
        if clar_id:
            clarification_payload[clar_id] = prompt
            # Sync back to global clarification_answers for multi-round clarification
            st.session_state.clarification_answers[clar_id] = prompt
        # The actual query for this run is the original user_query
        user_query = st.session_state.last_user_query or prompt
        st.session_state.pending_clarification = None
    else:
        # For a new question, record it for later reuse in multi-round clarifications
        st.session_state.last_user_query = user_query

    # First append the user's message to history
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    try:
        final_state = None
        final_debug_info = None

        # Assistant message: contains "pipeline progress bar + answer + debug"
        with st.chat_message("assistant"):
            pipeline_placeholder = st.empty()
            answer_placeholder = st.empty()

            # Core: stream the graph; after each step update the progress bar
            for state in stream_graph(
                user_query, clarification_answers=clarification_payload
            ):
                final_state = state

                step_results = state.get("step_results", [])
                final_answer = state.get("final_answer")
                pipeline_status = infer_pipeline_status(step_results, final_answer)
                pipeline_html = render_pipeline(pipeline_status)
                pipeline_placeholder.markdown(pipeline_html, unsafe_allow_html=True)

                # If a final answer is already available, show it early
                if final_answer:
                    answer_placeholder.markdown(final_answer)

            # Final state after the graph finishes
            if final_state is None:
                final_answer = "No answer generated."
                step_results = []
                datasets = {}
            else:
                final_answer = final_state.get("final_answer")
                step_results = final_state.get("step_results", [])
                datasets = final_state.get("data_artifacts", {})

            final_debug_info = {
                "actions": [step.get("step_type") for step in step_results],
                "steps": step_results,
                "datasets": datasets,
            }

            pending = final_state.get("pending_clarification") if final_state else None
            if pending and not final_answer:
                # This round is asking a clarification question
                question = pending.get("question", "Please provide more detail.")
                answer_placeholder.markdown(question)
            elif final_answer:
                answer_placeholder.markdown(final_answer)
            else:
                answer_placeholder.markdown("No answer generated.")

            # Debug info for this round
            with st.expander("Debug details"):
                st.write(json.dumps(final_debug_info, indent=2))

        # ----- After graph execution, update st.session_state.messages -----
        if final_state is None:
            # Should not normally happen, just a fallback
            st.session_state.pending_clarification = None
            st.session_state.last_user_query = user_query
        else:
            pending = final_state.get("pending_clarification")
            if pending and not final_answer:
                # Next round will need user's clarification
                st.session_state.pending_clarification = pending
                content_to_store = pending.get(
                    "question", "Please provide more detail."
                )
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

    except Exception as exc:  # noqa: BLE001
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
