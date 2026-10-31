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


class AchievementCompactRowIdentityTests(unittest.TestCase):
    def test_locked_builder_repairs_positive_count_but_missing_offset_sidecar(self):
        from app.modules.encyclopedia.providers import memory_bound_achievement_provider as mod

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "success.jsonl"
            path.write_text('{"kind":"meta"}\n', encoding="utf-8")
            mod._achievement_compact_index_path(path).write_text(
                '{"achievement_count":99}', encoding="utf-8",
            )
            with (
                patch.object(mod, "_achievement_compact_cache_valid", return_value=True),
                patch.object(mod, "_build_compact_cache_unlocked", return_value=0) as rebuild,
                redirect_stdout(io.StringIO()),
            ):
                self.assertEqual(mod._build_compact_cache(path), 0)
                rebuild.assert_called_once_with(path)

    def test_locked_builder_reuses_complete_valid_offset_sidecar(self):
        from app.modules.encyclopedia.providers import memory_bound_achievement_provider as mod

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "success.jsonl"
            path.write_text('{"kind":"meta"}\n', encoding="utf-8")
            mod._achievement_compact_index_path(path).write_text(json.dumps({
                "achievement_count": 3, "retained_count": 2,
                "retained_ids": [10, 11],
                "offsets": {"10": [30, 40], "11": [70, 50]},
            }), encoding="utf-8")
            with (
                patch.object(mod, "_achievement_compact_cache_valid", return_value=True),
                patch.object(mod, "_build_compact_cache_unlocked",
                             side_effect=AssertionError("complete cache must be reused")),
                redirect_stdout(io.StringIO()),
            ):
                self.assertEqual(mod._build_compact_cache(path), 0)

    def test_preload_rejects_same_count_wrong_offset_ids_or_negative_lengths(self):
        from app.modules.encyclopedia.providers import memory_bound_achievement_provider as mod

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "success.jsonl"
            path.write_text('{"kind":"meta"}\n', encoding="utf-8")
            sidecar = mod._achievement_compact_index_path(path)
            worker_result = subprocess.CompletedProcess(
                args=[], returncode=0,
                stdout='{"achievement_count":2}\n', stderr="",
            )
            for offsets in ({"99": [10, 20]}, {"10": [10, -1]},
                            {"10": [-1, 20]}, {"10": [0, True]}):
                with self.subTest(offsets=offsets):
                    sidecar.write_text(json.dumps({
                        "achievement_count": 2, "retained_count": 1,
                        "retained_ids": [10], "offsets": offsets,
                    }), encoding="utf-8")
                    with (
                        patch.object(mod, "_achievement_compact_cache_valid", return_value=True),
                        patch.object(mod.sys, "frozen", False, create=True),
                        patch.object(mod.subprocess, "run",
                                     return_value=worker_result) as worker,
                    ):
                        self.assertEqual(mod.ensure_achievement_compact_cache(path=path), 2)
                        worker.assert_called_once()
                    with (
                        patch.object(mod, "_achievement_compact_cache_valid", return_value=True),
                        patch.object(mod, "_build_compact_cache_unlocked",
                                     return_value=0) as repair,
                        redirect_stdout(io.StringIO()),
                    ):
                        self.assertEqual(mod._build_compact_cache(path), 0)
                        repair.assert_called_once_with(path)

    def test_ensure_success_preload_rebuilds_invalid_existing_sidecar(self):
        from app.modules.encyclopedia.providers import memory_bound_achievement_provider as mod

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "success.jsonl"
            path.write_text('{"kind":"meta"}\n', encoding="utf-8")
            sidecar = mod._achievement_compact_index_path(path)
            sidecar.write_text('{"achievement_count":100}', encoding="utf-8")
            completed = subprocess.CompletedProcess(
                args=[], returncode=0,
                stdout='{"achievement_count":100}\n', stderr="",
            )
            with (
                patch.object(mod, "_achievement_compact_cache_valid", return_value=True),
                patch.object(mod.sys, "frozen", False, create=True),
                patch.object(mod.subprocess, "run", return_value=completed) as worker,
            ):
                self.assertEqual(mod.ensure_achievement_compact_cache(path=path), 100)
                worker.assert_called_once()

    def test_ensure_success_preload_reuses_valid_sidecar_without_worker(self):
        from app.modules.encyclopedia.providers import memory_bound_achievement_provider as mod

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "success.jsonl"
            path.write_text('{"kind":"meta"}\n', encoding="utf-8")
            sidecar = mod._achievement_compact_index_path(path)
            sidecar.write_text(json.dumps({
                "achievement_count": 3, "retained_count": 2,
                "retained_ids": [10, 11],
                "offsets": {"10": [30, 40], "11": [70, 50]},
            }), encoding="utf-8")
            with (
                patch.object(mod, "_achievement_compact_cache_valid", return_value=True),
                patch.object(mod.subprocess, "run",
                             side_effect=AssertionError("must reuse cache")),
            ):
                self.assertEqual(mod.ensure_achievement_compact_cache(path=path), 3)

    def test_success_cache_rejects_replaced_source_with_identical_mtime(self):
        from app.modules.encyclopedia.providers import memory_bound_achievement_provider as mod

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "achievements.json"
            source.write_text("{}", encoding="utf-8")
            compact = root / "success.jsonl"
            sidecar = mod._achievement_compact_index_path(compact)
            sidecar.write_text("{}", encoding="utf-8")
            signature = mod._achievement_compact_source_signature(root)
            self.assertEqual(len(signature[0]), 5)
            compact.write_text(json.dumps({
                "kind": "meta",
                "schema_version": mod._ACHIEVEMENT_COMPACT_SCHEMA,
                "source_signature": signature,
            }) + "\n", encoding="utf-8")
            self.assertTrue(mod._achievement_compact_cache_valid(compact, data_dir=root))
            previous = source.stat()
            replacement = root / "replacement.json"
            replacement.write_text("[]", encoding="utf-8")
            os.utime(replacement, ns=(previous.st_atime_ns, previous.st_mtime_ns))
            self.assertEqual(replacement.stat().st_size, previous.st_size)
            replacement.replace(source)
            self.assertFalse(mod._achievement_compact_cache_valid(compact, data_dir=root))

    def test_stable_mismatched_compact_generation_is_not_loaded(self):
        from app.modules.encyclopedia.providers import memory_bound_achievement_provider as mod

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "catalog.jsonl"
            sidecar = mod._achievement_compact_index_path(path)
            path.write_text(
                "\n".join(json.dumps(row) for row in (
                    {"kind": "meta", "cache_generation": "new-catalog"},
                    {"kind": "category", "value": {"id": 8, "name": "Group"}},
                    {"kind": "achievement", "value": {"id": 10}},
                )) + "\n", encoding="utf-8",
            )
            sidecar.write_text(json.dumps({
                "cache_generation": "old-index",
                "achievement_count": 1, "retained_count": 1,
                "retained_ids": [10], "offsets": {"10": [5, 6]},
            }), encoding="utf-8")
            provider = MemoryBoundAchievementProvider()
            with (
                patch.object(mod, "ACHIEVEMENT_COMPACT_CACHE", path),
                patch.object(mod, "_achievement_compact_cache_valid", return_value=True),
            ):
                with self.assertRaisesRegex(RuntimeError, "générations différentes"):
                    provider._load_from_compact_cache()
                with patch.object(mod.subprocess, "run", return_value=subprocess.CompletedProcess(
                    args=[], returncode=0,
                    stdout='{"achievement_count":1}\n', stderr="",
                )) as rebuild:
                    self.assertEqual(mod.ensure_achievement_compact_cache(path=path), 1)
                    rebuild.assert_called_once()

    def test_compact_sidecar_swap_during_read_cannot_install_mixed_catalogue(self):
        from app.modules.encyclopedia.providers import memory_bound_achievement_provider as mod

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            compact = root / "catalog.jsonl"
            sidecar = mod._achievement_compact_index_path(compact)
            compact.write_text(
                "\n".join(json.dumps(row) for row in (
                    {"kind": "meta"},
                    {"kind": "category", "value": {"id": 8, "name": "Test"}},
                    {"kind": "achievement", "value": {"id": 10}},
                )) + "\n", encoding="utf-8",
            )
            sidecar.write_text(json.dumps({
                "retained_ids": [10], "offsets": {},
            }), encoding="utf-8")
            provider = MemoryBoundAchievementProvider()
            initial = tuple(provider._compact_retained_ids)
            real_stat = Path.stat
            checks = []

            def concurrent_replace(path, *args, **kwargs):
                value = real_stat(path, *args, **kwargs)
                if path == sidecar:
                    checks.append(True)
                    if len(checks) == 2:
                        return type("ChangedStat", (), {
                            "st_size": value.st_size,
                            "st_mtime_ns": value.st_mtime_ns,
                            "st_ctime_ns": value.st_ctime_ns + 1,
                            "st_ino": value.st_ino,
                        })()
                return value

            with (
                patch.object(mod, "ACHIEVEMENT_COMPACT_CACHE", compact),
                patch.object(mod, "_achievement_compact_cache_valid", return_value=True),
                patch.object(Path, "stat", concurrent_replace),
            ):
                with self.assertRaisesRegex(RuntimeError, "remplacé"):
                    provider._load_from_compact_cache()
            self.assertEqual(tuple(provider._compact_retained_ids), initial)
            self.assertEqual(len(checks), 2)

    def test_corrupt_compact_sidecar_falls_back_to_existing_worker(self):
        from app.modules.encyclopedia.providers import memory_bound_achievement_provider as mod

        provider = MemoryBoundAchievementProvider.__new__(MemoryBoundAchievementProvider)
        provider.data_dir = mod.RAW_QUEST_DATA_DIR
        with (
            patch.object(mod, "_achievement_compact_cache_valid", return_value=True),
            patch.object(provider, "_load_from_compact_cache",
                         side_effect=RuntimeError("invalid offsets")),
            patch.object(provider, "_load_from_compact_subprocess") as fallback,
        ):
            provider._load()
            fallback.assert_called_once_with()

    def test_quest_link_truncation_is_not_cached_and_repairs_on_next_lookup(self):
        from app.modules.encyclopedia.providers import memory_bound_achievement_provider as mod

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "success.jsonl"
            provider = MemoryBoundAchievementProvider()
            provider._compact_retained_ids = (10, 20)
            rows = [
                {"kind": "meta"},
                {"kind": "achievement", "value": {
                    "id": 10, "linked_quests": [{"entity_id": 42}],
                }},
                {"kind": "achievement", "value": {
                    "id": 20, "linked_quests": [],
                }},
                {"kind": "external_start"},
            ]

            def publish(records):
                path.write_text(
                    "\n".join(json.dumps(row, separators=(",", ":"))
                              for row in records) + "\n", encoding="utf-8",
                )

            with patch.object(mod, "ACHIEVEMENT_COMPACT_CACHE", path):
                publish(rows[:2])
                self.assertEqual(provider._compact_achievement_ids_for_quest(99), ())
                self.assertEqual(len(provider._compact_quest_link_cache), 0)
                publish(rows)
                self.assertEqual(provider._compact_achievement_ids_for_quest(42), (10,))
                self.assertEqual(provider._compact_achievement_ids_for_quest(99), ())
                self.assertIn(99, provider._compact_quest_link_cache)

    def test_quest_link_cache_invalidates_atomic_same_mtime_replacement(self):
        from app.modules.encyclopedia.providers import memory_bound_achievement_provider as mod

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "success.jsonl"
            provider = MemoryBoundAchievementProvider()
            provider._compact_retained_ids = (10,)

            def publish(target, quest):
                target.write_text(
                    "\n".join(json.dumps(row, separators=(",", ":")) for row in (
                        {"kind": "meta"},
                        {"kind": "achievement", "value": {
                            "id": 10, "linked_quests": [{"entity_id": quest}],
                        }},
                        {"kind": "external_start"},
                    )) + "\n", encoding="utf-8",
                )

            with patch.object(mod, "ACHIEVEMENT_COMPACT_CACHE", path):
                publish(path, 42)
                self.assertEqual(provider._compact_achievement_ids_for_quest(42), (10,))
                previous = path.stat()
                candidate = root / "candidate.jsonl"
                publish(candidate, 99)
                os.utime(candidate, ns=(previous.st_atime_ns, previous.st_mtime_ns))
                self.assertEqual(candidate.stat().st_size, previous.st_size)
                candidate.replace(path)
                self.assertEqual(path.stat().st_mtime_ns, previous.st_mtime_ns)
                self.assertEqual(provider._compact_achievement_ids_for_quest(42), ())
                self.assertEqual(provider._compact_achievement_ids_for_quest(99), (10,))

    def test_bad_compact_offsets_never_read_entire_file_and_recover_retained_id(self):
        from app.modules.encyclopedia.providers import memory_bound_achievement_provider as mod

        with tempfile.TemporaryDirectory() as directory:
            cache = Path(directory) / "success.jsonl"
            cache.write_text(
                "\n".join(json.dumps(row) for row in (
                    {"kind": "meta"},
                    {"kind": "achievement", "value": {"id": 10, "name": "Retained"}},
                    {"kind": "external_start"},
                )) + "\n", encoding="utf-8",
            )
            provider = MemoryBoundAchievementProvider()
            provider._compact_retained_set = frozenset({10})
            with patch.object(mod, "ACHIEVEMENT_COMPACT_CACHE", cache):
                for span in ((0, -1), (-2, 3), (0, 999999)):
                    with self.subTest(span=span):
                        provider._compact_external_index = {10: span}
                        self.assertEqual(
                            provider._compact_value_by_id(10)["name"], "Retained",
                        )
                # A genuinely external ID still uses the external section.
                self.assertIsNone(provider._compact_value_by_id(99))

    def test_retained_offset_must_point_to_matching_success(self) -> None:
        from app.modules.encyclopedia.providers import memory_bound_achievement_provider as mod

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "success.jsonl"
            provider = MemoryBoundAchievementProvider.__new__(MemoryBoundAchievementProvider)
            provider._compact_external_index = {10: (0, 0)}
            with patch.object(mod, "ACHIEVEMENT_COMPACT_CACHE", path):
                for payload in (
                    {"kind": "achievement", "value": {"id": 20}},
                    {"kind": "guide", "value": {"id": 10}},
                    {"kind": "achievement", "value": {"id": True}},
                    {"kind": "achievement", "value": {"id": 10}},
                ):
                    raw = (json.dumps(payload) + "\n").encode("utf-8")
                    path.write_bytes(raw)
                    provider._compact_external_index = {10: (0, len(raw))}
                    with self.subTest(payload=payload):
                        value = provider._compact_value_by_id(10)
                        if payload["kind"] == "achievement" and payload["value"]["id"] == 10 and type(payload["value"]["id"]) is int:
                            self.assertEqual(value, {"id": 10})
                        else:
                            self.assertIsNone(value)


class AchievementDetailColdTimingTests(unittest.TestCase):
    def test_cold_subprocess_reports_real_blocking_and_decode_phases(self) -> None:
        from threading import current_thread
        from app.modules.encyclopedia.providers.memory_bound_achievement_provider import (
            RAW_QUEST_DATA_DIR,
        )

        provider = MemoryBoundAchievementProvider(data_dir=RAW_QUEST_DATA_DIR)
        completed = subprocess.CompletedProcess(
            args=[], returncode=0,
            stdout='{"id":123,"name":"Succès témoin","category_id":8}\n',
            stderr="",
        )
        with (
            patch.object(MemoryBoundAchievementProvider, "_ensure_loaded"),
            patch.object(
                __import__("sys"), "frozen", False, create=True
            ),
            patch(
                "app.modules.encyclopedia.providers.memory_bound_achievement_provider.subprocess.run",
                return_value=completed,
            ) as child,
        ):
            detail = provider.get_detail_by_id(123)
            self.assertEqual(detail.id, 123)
            child.assert_called_once()
            self.assertEqual(child.call_args.kwargs["timeout"], 90)
            self.assertEqual(
                child.call_args.kwargs["creationflags"],
                getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0,
            )
            timing = provider.last_detail_breakdown_ms
            self.assertEqual(timing["thread"], current_thread().name)
            self.assertTrue(timing["subprocess_path_used"])
            self.assertGreaterEqual(timing["synchronous_subprocess_ms"], 0.0)
            self.assertGreaterEqual(timing["decode_ms"], 0.0)
            self.assertGreaterEqual(timing["total_ms"], timing["decode_ms"])
            # Returning to the same detail remains a cheap cache hit.
            self.assertIs(provider.get_detail_by_id(123), detail)
            child.assert_called_once()

    def test_recent_success_details_reuse_small_bounded_cache(self) -> None:
        from app.modules.encyclopedia.providers.memory_bound_achievement_provider import (
            RAW_QUEST_DATA_DIR,
        )
        provider = MemoryBoundAchievementProvider(data_dir=RAW_QUEST_DATA_DIR)
        opened: list[int] = []

        def worker(argv, **_kwargs):
            ident = int(argv[-1])
            opened.append(ident)
            return subprocess.CompletedProcess(
                args=argv, returncode=0,
                stdout=json.dumps({"id": ident, "category_id": 8,
                                   "name": f"Achievement {ident}"}) + "\n",
                stderr="",
            )

        with (
            patch.object(MemoryBoundAchievementProvider, "_ensure_loaded"),
            patch.object(__import__("sys"), "frozen", False, create=True),
            patch(
                "app.modules.encyclopedia.providers.memory_bound_achievement_provider.subprocess.run",
                side_effect=worker,
            ),
        ):
            first = provider.get_detail_by_id(1)
            provider.get_detail_by_id(2)
            self.assertIs(provider.get_detail_by_id(1), first)
            self.assertEqual(opened, [1, 2])
            self.assertEqual(provider.last_detail_breakdown_ms["cache_source"], "recent")
            self.assertEqual(provider.last_detail_breakdown_ms["synchronous_subprocess_ms"], 0.0)
            self.assertFalse(provider.last_detail_breakdown_ms["subprocess_path_used"])

            self.assertIs(provider.get_detail_by_id(1), first)
            self.assertEqual(provider.last_detail_breakdown_ms["cache_source"], "hot")
            provider.get_detail_by_id(3)
            provider.get_detail_by_id(4)
            self.assertEqual(len(provider._recent_rich_details), 2)
            self.assertEqual(opened, [1, 2, 3, 4])
            # ID 2 was evicted on the fourth distinct detail.
            provider.get_detail_by_id(2)
            self.assertEqual(opened, [1, 2, 3, 4, 2])
            self.assertEqual(provider.last_detail_breakdown_ms["cache_source"], "cold")

        provider.release_catalogue()
        self.assertEqual(len(provider._recent_rich_details), 0)
        self.assertIsNone(provider._detail_cache)
        self.assertIsNone(provider._detail_cache_id)

    def test_cold_worker_cost_survives_hot_hit_then_clears_on_release(self) -> None:
        from threading import Thread
        from app.modules.encyclopedia.providers.memory_bound_achievement_provider import (
            RAW_QUEST_DATA_DIR,
        )
        provider = MemoryBoundAchievementProvider(data_dir=RAW_QUEST_DATA_DIR)
        output = subprocess.CompletedProcess(
            args=[], returncode=0,
            stdout=json.dumps({"id": 123, "category_id": 8,
                               "name": "Warmup success"}) + "\n",
            stderr="",
        )
        errors = []

        def warm_one():
            try:
                provider.get_detail_by_id(123)
            except Exception as exc:
                errors.append(exc)

        with (
            patch.object(MemoryBoundAchievementProvider, "_ensure_loaded"),
            patch.object(__import__("sys"), "frozen", False, create=True),
            patch(
                "app.modules.encyclopedia.providers.memory_bound_achievement_provider.subprocess.run",
                return_value=output,
            ) as child,
        ):
            worker = Thread(target=warm_one, name="DofusAtlasAchievementStage")
            worker.start()
            worker.join(timeout=5)
            self.assertFalse(worker.is_alive())
            self.assertEqual(errors, [])
            child.assert_called_once()
            cold = provider.last_cold_detail_breakdown_ms
            self.assertEqual(cold["achievement_id"], 123)
            self.assertEqual(cold["status"], "OBSERVED")
            self.assertEqual(cold["thread"], "DofusAtlasAchievementStage")
            self.assertTrue(cold["subprocess_path_used"])
            self.assertGreaterEqual(cold["total_ms"], 0)
            self.assertIs(provider.get_detail_by_id(123), provider._detail_cache)
            self.assertEqual(provider.last_detail_breakdown_ms["cache_source"], "hot")
            self.assertEqual(provider.last_detail_breakdown_ms["total_ms"], 0.0)
            self.assertEqual(provider.last_cold_detail_breakdown_ms, cold)
            child.assert_called_once()

        provider.release_catalogue()
        self.assertEqual(provider.last_cold_detail_breakdown_ms, {})

    def test_failed_subprocess_still_records_blocking_phase(self) -> None:
        from app.modules.encyclopedia.providers.memory_bound_achievement_provider import (
            RAW_QUEST_DATA_DIR,
        )
        provider = MemoryBoundAchievementProvider(data_dir=RAW_QUEST_DATA_DIR)
        with (
            patch.object(MemoryBoundAchievementProvider, "_ensure_loaded"),
            patch.object(__import__("sys"), "frozen", False, create=True),
            patch(
                "app.modules.encyclopedia.providers.memory_bound_achievement_provider.subprocess.run",
                side_effect=subprocess.TimeoutExpired(cmd="detail", timeout=90),
            ),
        ):
            with self.assertRaises(subprocess.TimeoutExpired):
                provider.get_detail_by_id(123)
        timing = provider.last_detail_breakdown_ms
        self.assertTrue(timing["subprocess_path_used"])
        self.assertGreaterEqual(timing["synchronous_subprocess_ms"], 0.0)


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


class AchievementNameIndexIntegrityTests(unittest.TestCase):
    def test_name_index_rejects_bad_rows_and_duplicate_success_ids(self):
        from app.modules.encyclopedia.services import achievement_index_warmup as warm

        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "success.jsonl"
            valid = [
                {"kind": "meta", "schema_version": 5},
                {"kind": "achievement", "value": {"id": 10, "name": "Un"}},
                {"kind": "external_start"},
                {"kind": "achievement", "value": {"id": 20, "name": "Deux"}},
            ]
            with patch.object(warm, "_ACHIEVEMENT_COMPACT_CACHE", source):
                source.write_text(
                    "\n".join(json.dumps(row) for row in valid) + "\n",
                    encoding="utf-8",
                )
                self.assertEqual(warm.achievement_name_index(), {10: "Un", 20: "Deux"})
                for broken in (
                    {"kind": "achievement", "value": {"id": 10, "name": "Duplicate"}},
                    {"kind": "achievement", "value": {"id": True}},
                    {"kind": "achievement", "value": {"id": "30"}},
                    {"kind": "achievement", "value": None},
                ):
                    with self.subTest(broken=broken):
                        source.write_text(
                            "\n".join(json.dumps(row) for row in [*valid, broken]) + "\n",
                            encoding="utf-8",
                        )
                        self.assertEqual(warm.achievement_name_index(), {})

    def test_names_builder_rejects_mid_scan_replaced_catalogue(self):
        from app.modules.encyclopedia.services import achievement_index_warmup as warm

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            catalogue = root / "success.jsonl"
            destination = root / "names.json"
            catalogue.write_text(
                "\n".join(json.dumps(row) for row in (
                    {"kind": "meta"},
                    {"kind": "achievement", "value": {"id": 10, "name": "New"}},
                )) + "\n", encoding="utf-8",
            )
            destination.write_text('{"10":"Previous"}', encoding="utf-8")
            real_stat = Path.stat
            hits = []

            def changed_generation(path, *args, **kwargs):
                value = real_stat(path, *args, **kwargs)
                if path == catalogue:
                    hits.append(True)
                    if len(hits) % 2 == 0:
                        # Both the direct read and the later write's read
                        # observe a concurrent source change at their end.
                        return type("NewStat", (), {
                            "st_size": value.st_size,
                            "st_mtime_ns": value.st_mtime_ns,
                            "st_ctime_ns": value.st_ctime_ns + 1,
                            "st_ino": value.st_ino,
                        })()
                return value

            with (
                patch.object(warm, "_ACHIEVEMENT_COMPACT_CACHE", catalogue),
                patch.object(warm, "_ACHIEVEMENT_NAMES_FILE", destination),
                patch.object(Path, "stat", changed_generation),
            ):
                self.assertEqual(warm.achievement_name_index(), {})
                with self.assertRaisesRegex(RuntimeError, "empty or corrupt"):
                    warm.write_achievement_name_index()
            self.assertEqual(destination.read_text(encoding="utf-8"), '{"10":"Previous"}')
            self.assertEqual(len(hits), 4)
            self.assertFalse(list(root.glob(".*.tmp")))

    def test_identical_names_reuse_existing_cache_without_republication(self):
        from app.modules.encyclopedia.services import achievement_index_warmup as warm

        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "achievement_names.json"
            target.write_text('{"17":"Succès"}', encoding="utf-8")
            before = target.stat().st_mtime_ns
            with (
                patch.object(warm, "_ACHIEVEMENT_NAMES_FILE", target),
                patch.object(warm, "achievement_name_index",
                             return_value={17: "Succès"}),
                patch.object(Path, "replace",
                             side_effect=AssertionError("same cache must not replace")),
            ):
                self.assertEqual(warm.write_achievement_name_index(), 1)
            self.assertEqual(target.stat().st_mtime_ns, before)
            self.assertEqual(target.read_text(encoding="utf-8"), '{"17":"Succès"}')
            self.assertFalse(list(target.parent.glob("*.tmp")))

    def test_name_index_writer_keeps_previous_version_on_failed_serialization(self):
        from app.modules.encyclopedia.services import achievement_index_warmup as warm

        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "achievement_names.json"
            target.write_text('{"17":"Old"}', encoding="utf-8")
            with (
                patch.object(warm, "_ACHIEVEMENT_NAMES_FILE", target),
                patch.object(warm, "achievement_name_index", return_value={17: "New"}),
                patch.object(warm.json, "dump", side_effect=OSError("disk full")),
            ):
                with self.assertRaisesRegex(OSError, "disk full"):
                    warm.write_achievement_name_index()
            self.assertEqual(target.read_text(encoding="utf-8"), '{"17":"Old"}')
            self.assertFalse(list(target.parent.glob(".*.tmp")))

    def test_invalid_names_do_not_overwrite_previous_atomic_index(self):
        from app.modules.encyclopedia.services import achievement_index_warmup as warm

        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "names.json"
            target.write_text('{"10":"previous"}', encoding="utf-8")
            with (
                patch.object(warm, "_ACHIEVEMENT_NAMES_FILE", target),
                patch.object(warm, "achievement_name_index", return_value={}),
            ):
                with self.assertRaisesRegex(RuntimeError, "empty or corrupt"):
                    warm.write_achievement_name_index()
            self.assertEqual(target.read_text(encoding="utf-8"), '{"10":"previous"}')
            self.assertFalse(list(target.parent.glob("*.tmp")))


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


    def test_independent_name_index_workers_publish_without_collision(self):
        # Real subprocesses exercise the OS lock, not only Python thread timing.
        worker = r"""
import sys, time
from pathlib import Path
from app.modules.encyclopedia.services import achievement_index_warmup as warm
root, ident = Path(sys.argv[1]), sys.argv[2]
warm._ACHIEVEMENT_NAMES_FILE = root / 'achievement_names.json'
warm.achievement_name_index = lambda: {17: 'Success'}
(root / ('ready_' + ident)).write_text('1', encoding='utf-8')
deadline = time.monotonic() + 15
while len(list(root.glob('ready_*'))) < 3:
    if time.monotonic() >= deadline:
        raise SystemExit('name index barrier timeout')
    time.sleep(0.01)
assert warm.write_achievement_name_index() == 1
"""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            processes = []
            try:
                for number in range(3):
                    processes.append(subprocess.Popen(
                        [os.sys.executable, "-c", worker, str(root), str(number)],
                        cwd=Path(__file__).resolve().parents[1],
                        env={**os.environ, "PYTHONUTF8": "1"},
                        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                    ))
                for process in processes:
                    try:
                        output, error = process.communicate(timeout=30)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.communicate(timeout=5)
                        self.fail("Name index writer deadlock")
                    self.assertEqual(process.returncode, 0, error or output)
                self.assertEqual(
                    json.loads((root / "achievement_names.json").read_text(encoding="utf-8")),
                    {"17": "Success"},
                )
                self.assertFalse(list(root.glob("*.tmp")))
            finally:
                for process in processes:
                    if process.poll() is None:
                        process.kill()
                        process.communicate(timeout=5)


if __name__ == "__main__":
    unittest.main()
