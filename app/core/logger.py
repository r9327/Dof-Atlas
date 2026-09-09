from __future__ import annotations

import logging

from app.constants import LOG_DIR

RUNTIME_LOG_FILE = LOG_DIR / "session_runtime.log"
MAX_RUNTIME_LOG_BYTES = 1024 * 1024
NORMAL_FORMAT = "[PYRUNTIME] %(asctime)s - %(levelname)s - %(message)s"
DEBUG_FORMAT = (
    "[PYRUNTIME] %(asctime)s - %(levelname)s - "
    "%(threadName)s - %(module)s.%(funcName)s:%(lineno)d - %(message)s"
)


def _runtime_formatter(debug_enabled: bool) -> logging.Formatter:
    return logging.Formatter(DEBUG_FORMAT if debug_enabled else NORMAL_FORMAT)


def get_runtime_logger() -> logging.Logger:
    logger = logging.getLogger("dofus_atlas_runtime")
    if logger.handlers:
        return logger

    LOG_DIR.mkdir(parents=True, exist_ok=True)
    if RUNTIME_LOG_FILE.exists() and RUNTIME_LOG_FILE.stat().st_size > MAX_RUNTIME_LOG_BYTES:
        try:
            RUNTIME_LOG_FILE.replace(LOG_DIR / "session_runtime.log.old")
        except OSError:
            pass

    handler = logging.FileHandler(RUNTIME_LOG_FILE, encoding="utf-8")
    handler.setLevel(logging.INFO)
    handler.setFormatter(_runtime_formatter(False))
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False
    return logger


def set_debug_logging(enabled: bool) -> None:
    logger = get_runtime_logger()
    level = logging.DEBUG if enabled else logging.INFO
    logger.setLevel(level)
    for handler in logger.handlers:
        handler.setLevel(level)
        handler.setFormatter(_runtime_formatter(enabled))
