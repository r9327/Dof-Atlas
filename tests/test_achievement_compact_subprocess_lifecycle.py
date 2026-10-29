from __future__ import annotations

import io
import json
import os
import subprocess
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from contextlib import redirect_stdout
from unittest.mock import Mock, patch

from app.modules.encyclopedia.providers.memory_bound_achievement_provider import (
    MemoryBoundAchievementProvider,
    _achievement_from_dict,
    _dump_default_detail,
    _build_compact_cache,
    _unique_cache_temporary_path,
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
        self.assertEqual(start.call_args.kwargs["env"]["PYTHONUTF8"], "1")
        self.assertEqual(start.call_args.kwargs["env"]["PYTHONIOENCODING"], "utf-8")
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

    def test_worker_overrides_ambient_legacy_stdout_encoding(self) -> None:
        process = Mock()
        process.stdout = io.StringIO("")
        process.poll.return_value = 2
        process.wait.return_value = 2

        with (
            patch.dict(os.environ, {"PYTHONIOENCODING": "cp1252", "PYTHONUTF8": "0"}),
            patch(
                "app.modules.encyclopedia.providers.memory_bound_achievement_provider.subprocess.Popen",
                return_value=process,
            ) as start,
        ):
            with self.assertRaises(RuntimeError):
                MemoryBoundAchievementProvider._load_from_compact_subprocess(object())

        child_env = start.call_args.kwargs["env"]
        self.assertEqual(child_env["PYTHONIOENCODING"], "utf-8")
        self.assertEqual(child_env["PYTHONUTF8"], "1")


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


class AchievementParallelCacheBuilderTests(unittest.TestCase):
    def test_temporary_file_names_are_unique_for_a_shared_cache(self):
        dest = Path("cache") / "achievement_catalogue_v1.jsonl"
        paths = {_unique_cache_temporary_path(dest) for _ in range(20)}
        self.assertEqual(len(paths), 20)
        self.assertTrue(all(p.parent == dest.parent and p.name.endswith(".tmp") for p in paths))
        self.assertNotIn(dest.with_suffix(dest.suffix + ".tmp"), paths)

    def test_simultaneous_builders_publish_a_complete_cache(self):
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "achievement_catalogue_v1.jsonl"
            worker = Mock()
            worker._categories = {}
            worker._achievements = []
            with patch(
                "app.modules.encyclopedia.providers.memory_bound_achievement_provider.MemoryBoundAchievementProvider",
                return_value=worker,
            ), ThreadPoolExecutor(max_workers=4) as pool:
                completed = list(pool.map(_build_compact_cache, [destination] * 4))
            self.assertEqual(completed, [0] * 4)
            with destination.open(encoding="utf-8") as src:
                self.assertEqual(json.loads(src.readline())["kind"], "meta")
                self.assertEqual(json.loads(src.readline())["kind"], "external_start")
            index = destination.with_suffix(destination.suffix + ".idx.json")
            self.assertEqual(json.loads(index.read_text(encoding="utf-8"))["achievement_count"], 0)

    def test_parallel_achievement_names_dont_share_temporary_file(self):
        from app.modules.encyclopedia.services import achievement_index_warmup as warm
        with tempfile.TemporaryDirectory() as directory:
            dest = Path(directory) / "achievement_names.json"
            with (
                patch.object(warm, "_ACHIEVEMENT_NAMES_FILE", dest),
                patch.object(warm, "achievement_name_index", return_value={17: "Succès"}),
                ThreadPoolExecutor(max_workers=4) as pool,
            ):
                counts = list(pool.map(lambda _: warm.write_achievement_name_index(), range(4)))
            self.assertEqual(counts, [1] * 4)
            self.assertEqual(json.loads(dest.read_text(encoding="utf-8")), {"17": "Succès"})


if __name__ == "__main__":
    unittest.main()
