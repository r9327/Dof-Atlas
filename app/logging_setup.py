from __future__ import annotations

import logging
from pathlib import Path

from app.constants import LOGGER, PYSIDE_LOG_FILE


DEFAULT_MAX_LOG_BYTES = 512 * 1024


def configure_logging(
    path: Path = PYSIDE_LOG_FILE,
    *,
    logger: logging.Logger = LOGGER,
    max_bytes: int = DEFAULT_MAX_LOG_BYTES,
) -> bool:
    """Install the application file logger explicitly during bootstrap."""

    target = Path(path)
    limit = int(max_bytes)
    if limit <= 0:
        raise ValueError("max_bytes must be positive")

    resolved = target.resolve()
    for existing in logger.handlers:
        if (
            isinstance(existing, logging.FileHandler)
            and Path(existing.baseFilename).resolve() == resolved
        ):
            return True

    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists() and target.stat().st_size > limit:
            target.replace(target.with_suffix(target.suffix + ".old"))
        handler = logging.FileHandler(target, encoding="utf-8")
    except OSError:
        logger.warning(
            "Journal fichier indisponible: path=%s",
            target,
            exc_info=True,
        )
        return False

    handler.setFormatter(
        logging.Formatter("[PYSIDE] %(asctime)s - %(levelname)s - %(message)s")
    )
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    return True


__all__ = ["DEFAULT_MAX_LOG_BYTES", "configure_logging"]
