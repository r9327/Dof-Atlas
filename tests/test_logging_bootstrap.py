from __future__ import annotations

import logging
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from app.logging_setup import configure_logging


ROOT = Path(__file__).resolve().parents[1]


class LoggingBootstrapTests(unittest.TestCase):
    def test_importing_constants_opens_no_file_and_creates_no_directory(self) -> None:
        script = """
import logging
from pathlib import Path

def forbidden(*_args, **_kwargs):
    raise AssertionError("filesystem side effect during constants import")

Path.mkdir = forbidden
logging.FileHandler = forbidden
import app.constants as constants
assert constants.LOGGER.handlers == []
"""
        result = subprocess.run(
            [sys.executable, "-c", script],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=10,
        )
        self.assertEqual(result.returncode, 0, result.stderr or result.stdout)

    def test_explicit_bootstrap_rotates_once_and_is_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "atlas.log"
            original = b"previous-session"
            path.write_bytes(original)
            logger = logging.getLogger(f"dofus_atlas.test.{id(self)}")
            logger.handlers.clear()
            logger.propagate = False
            try:
                self.assertTrue(configure_logging(path, logger=logger, max_bytes=4))
                self.assertTrue(configure_logging(path, logger=logger, max_bytes=4))
                self.assertEqual(len(logger.handlers), 1)
                self.assertEqual(
                    path.with_suffix(".log.old").read_bytes(),
                    original,
                )

                logger.info("bootstrap ready")
                logger.handlers[0].flush()
                self.assertIn("bootstrap ready", path.read_text(encoding="utf-8"))
            finally:
                for handler in tuple(logger.handlers):
                    handler.close()
                    logger.removeHandler(handler)

    def test_invalid_rotation_limit_is_rejected_before_file_creation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "nested" / "atlas.log"
            with self.assertRaises(ValueError):
                configure_logging(path, max_bytes=0)
            self.assertFalse(path.parent.exists())


if __name__ == "__main__":
    unittest.main()
