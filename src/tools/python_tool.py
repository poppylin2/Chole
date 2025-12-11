from __future__ import annotations

import io
import uuid
import traceback
from contextlib import redirect_stdout
from pathlib import Path
from typing import Any, Dict

import matplotlib
import numpy as np
import pandas as pd

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402


SAFE_BUILTINS = {
    "print": print,
    "len": len,
    "range": range,
    "min": min,
    "max": max,
    "sum": sum,
    "abs": abs,
    "float": float,
    "int": int,
    "enumerate": enumerate,
    "zip": zip,
    "__import__": __import__,
}


def run_python_analysis(
    code: str, datasets: Dict[str, str], runtime_cache: Path
) -> Dict[str, Any]:
    """Execute analysis code against cached CSV datasets in a constrained namespace."""

    runtime_cache.mkdir(parents=True, exist_ok=True)

    local_ctx: Dict[str, Any] = {}
    global_ctx: Dict[str, Any] = {
        "__builtins__": SAFE_BUILTINS,
        "pd": pd,
        "np": np,
        "plt": plt,
        "datasets": datasets,
        "runtime_cache": runtime_cache,
    }

    def save_plot(name: str | None = None) -> str:
        plot_id = name or f"plot_{uuid.uuid4().hex[:8]}"
        path = runtime_cache / f"{plot_id}.png"
        plt.savefig(path)
        return str(path)

    global_ctx["save_plot"] = save_plot

    stdout_buffer = io.StringIO()
    try:
        with redirect_stdout(stdout_buffer):
            exec(code, global_ctx, local_ctx)
    except Exception as exc:
        tb = traceback.format_exc()
        # Try to show the failing line in the generated code for easier debugging.
        snippet = ""
        try:
            tb_frames = traceback.extract_tb(exc.__traceback__) if exc.__traceback__ else []
            if tb_frames:
                lineno = tb_frames[-1].lineno or 0
                lines = code.splitlines()
                start = max(0, lineno - 3)
                end = min(len(lines), lineno + 2)
                snippet = "\n".join(f"{idx+1}: {lines[idx]}" for idx in range(start, end))
        except Exception:
            snippet = ""

        msg_parts = [str(exc)]
        if snippet:
            msg_parts.append(f"code_snippet:\n{snippet}")
        msg_parts.append(f"traceback:\n{tb}")
        error_text = "\n".join(msg_parts)
        # Truncate to keep the message manageable
        if len(error_text) > 4000:
            error_text = error_text[:4000] + "\n...truncated..."
        return {"status": "error", "error_message": error_text}

    output_text = stdout_buffer.getvalue().strip()
    result_obj = local_ctx.get("result")
    metrics = local_ctx.get("metrics", {})
    plots = local_ctx.get("plots", [])
    if isinstance(plots, str):
        plots = [plots]

    summary_text_parts = []
    if output_text:
        summary_text_parts.append(output_text)
    if result_obj is not None and not isinstance(result_obj, (str, int, float)):
        summary_text_parts.append(str(result_obj))

    summary_text = "\n".join(summary_text_parts) if summary_text_parts else "Analysis code executed."

    return {
        "status": "ok",
        "summary_text": summary_text,
        "metrics": metrics if isinstance(metrics, dict) else {},
        "plot_paths": plots,
    }
