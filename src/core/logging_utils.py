from __future__ import annotations

import logging
from pathlib import Path


def setup_logging(log_path: Path) -> logging.Logger:
    """Configure a simple file logger under runtime_cache for agent loops."""

    log_path.parent.mkdir(parents=True, exist_ok=True)

    logger = logging.getLogger("fab_agent")
    logger.setLevel(logging.INFO)

    if not any(isinstance(h, logging.FileHandler) and getattr(h, "baseFilename", "") == str(log_path) for h in logger.handlers):
        handler = logging.FileHandler(log_path, encoding="utf-8")
        formatter = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
        handler.setFormatter(formatter)
        logger.addHandler(handler)

    return logger
