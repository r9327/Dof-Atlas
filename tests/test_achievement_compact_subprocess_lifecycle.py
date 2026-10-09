from __future__ import annotations

import io
import json
import subprocess
import unittest
from unittest.mock import Mock, patch

from app.modules.encyclopedia.providers.memory_bound_achievement_provider import (
    MemoryBoundAchievementProvider,
)


class AchievementCompactSubprocessTests(unittest.TestCase):
    def test_malformed_stream_kills_child_and_closes_stdout(self) -> None:
        process = Mock()
        process.stdout = io.StringIO("not json\\n")
        process.poll.return_value = None

        with patch(
            "app.modules.encyclopedia.providers.memory_bound_achievement_provider.subprocess.Popen",
            return_value=process,
        ) as start:
            with self.assertRaises(json.JSONDecodeError):
                MemoryBoundAchievementProvider._load_from_compact_subprocess(object())

        self.assertNotEqual(start.call_args.kwargs["stderr"], subprocess.PIPE)
        self.assertTrue(process.stdout.closed)
        process.kill.assert_called_once()
        process.wait.assert_called_once_with(timeout=5)

    def test_error_output_is_file_backed_and_failure_keeps_diagnostic(self) -> None:
        process = Mock()
        process.stdout = io.StringIO("")
        process.poll.return_value = 2
        process.wait.return_value = 2

        def launch(*_args, **kwargs):
            errors = kwargs["stderr"]
            self.assertTrue(callable(getattr(errors, "fileno", None)))
            errors.write("synthetic subprocess failure\\n")
            errors.flush()
            return process

        with patch(
            "app.modules.encyclopedia.providers.memory_bound_achievement_provider.subprocess.Popen",
            side_effect=launch,
        ):
            with self.assertRaisesRegex(RuntimeError, "synthetic subprocess failure"):
                MemoryBoundAchievementProvider._load_from_compact_subprocess(object())

        self.assertTrue(process.stdout.closed)
        process.kill.assert_not_called()


if __name__ == "__main__":
    unittest.main()
