from __future__ import annotations

import io
import json
import subprocess
import unittest
from contextlib import redirect_stdout
from unittest.mock import Mock, patch

from app.modules.encyclopedia.providers.memory_bound_achievement_provider import (
    MemoryBoundAchievementProvider,
    _achievement_from_dict,
    _dump_default_detail,
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


class AchievementDetailWorkerFastPathTests(unittest.TestCase):
    def test_disposable_detail_uses_existing_fast_loader_and_preserves_data(self) -> None:
        detail = _achievement_from_dict({
            "id": 123,
            "category_id": 8,
            "name": "Succès de contrôle",
            "objective_ids": [7],
            "reward_ids": [21],
        })
        provider = Mock()
        provider._get_detail_in_process.return_value = detail
        output = io.StringIO()
        with (
            patch(
                "app.modules.encyclopedia.providers.memory_bound_achievement_provider.MemoryBoundAchievementProvider",
                return_value=provider,
            ) as ctor,
            redirect_stdout(output),
        ):
            self.assertEqual(_dump_default_detail(123), 0)

        ctor.assert_called_once()
        provider._load_disposable_worker_fast.assert_called_once_with()
        provider._load_in_process.assert_not_called()
        self.assertTrue(provider._loaded)
        provider.prepare_detail_sources.assert_called_once_with()
        provider._get_detail_in_process.assert_called_once_with(123)
        payload = json.loads(output.getvalue().strip())
        self.assertEqual(payload["id"], 123)
        self.assertEqual(payload["name"], "Succès de contrôle")
        self.assertEqual(payload["objective_ids"], [7])
        self.assertEqual(payload["reward_ids"], [21])

    def test_missing_detail_reports_failure_instead_of_fake_success(self) -> None:
        provider = Mock()
        provider._get_detail_in_process.return_value = None
        output = io.StringIO()
        with (
            patch(
                "app.modules.encyclopedia.providers.memory_bound_achievement_provider.MemoryBoundAchievementProvider",
                return_value=provider,
            ),
            redirect_stdout(output),
        ):
            self.assertEqual(_dump_default_detail(999), 2)
        provider._load_disposable_worker_fast.assert_called_once_with()
        provider.prepare_detail_sources.assert_called_once_with()
        self.assertEqual(output.getvalue(), "")


if __name__ == "__main__":
    unittest.main()
