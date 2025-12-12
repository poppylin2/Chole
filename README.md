# Fab Data Analysis Agent

Local, data-centric AI agent for fab inspection and equipment analytics using LangGraph, SQLite, and Streamlit.

## Setup

1) Install uv (https://docs.astral.sh/uv/).
2) Install dependencies (if uv crashes on macOS SystemConfiguration, use local cache or pip fallback):
```bash
UV_CACHE_DIR=.uv_cache uv sync
# Fallback if uv panics:
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
```

## Running

1) Place your SQLite database at `data.sqlite` in the project root (or set `DB_PATH` env var).
2) Put Markdown knowledge files under `docs/` (any `*.md`).
3) Launch the app:
```bash
uv run streamlit run src/app/main_streamlit.py
```

## Architecture (Text Tree)

```
Fab Data Analysis Agent
├─ User / Streamlit UI: src/app/main_streamlit.py
│  └─ Calls run_graph(); manages chat session and clarifications
├─ Config & Context
│  ├─ Config load: src/core/config.py (DB/docs/runtime_cache paths)
│  ├─ Logging: src/core/logging_utils.py (runtime_cache/agent.log)
│  └─ Context load: src/core/context_loader.py
│     ├─ SQLite schema introspection → DatabaseSchema
│     └─ Markdown knowledge merge + table index
├─ LangGraph Assembly: src/graph/graph_builder.py
│  ├─ Entry: supervisor
│  ├─ Conditional routing: next_action → data_analyst / domain_expert / ask_user / aggregator
│  └─ End: END (aggregator or ask_user)
├─ Supervisor (LLM): src/agents/supervisor.py
│  └─ Chooses next_action (sql_analysis / python_analysis / domain_explain / ask_user / finish)
├─ Data Analyst (LLM): src/agents/data_analyst.py
│  ├─ SQL planning → SQLite tool
│  │  └─ SQLite tool: src/tools/sqlite_tool.py (read-only; results to runtime_cache/*.csv)
│  └─ Python planning → Python tool
│     └─ Python tool: src/tools/python_tool.py (pandas/numpy/matplotlib; plots to runtime_cache/*.png)
├─ Domain Expert (LLM): src/agents/domain_expert.py
│  └─ Explains numeric findings using Markdown knowledge
├─ Aggregator (LLM): src/agents/aggregator.py
│  └─ Produces final answer
├─ Data & Knowledge
│  ├─ SQLite DB: data.sqlite
│  └─ Knowledge base: docs/*.md
└─ Runtime artifacts: runtime_cache/
   ├─ Query CSVs: query_result_*.csv
   └─ Plots: plot_*.png
```

## Notes

- Tools write intermediate CSVs and plots to `runtime_cache/`.
- OpenAI API key should be available via `OPENAI_API_KEY`.
- Dockerfile is left as a TODO stub.


uv run python -m tools.ingest_manuals

How’s the system health for 8950XR-P2 over the last 7 days?

How to open KTGem Deep View 2.0 Application?

What is the defect rate trend for the 8950XR-P1 from 20251201 to 20251207? Create a line chart.