from __future__ import annotations

import subprocess
import sqlite3
import tempfile
from pathlib import Path
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from app import startup_cache_warmup as warmup


class StartupWorkerSubprocessFlagsTests(unittest.TestCase):

    def test_domain_progress_is_atomic_and_quest_is_published_first(self) -> None:
        order = []
        publications = []
        payloads = {
            "quest": {"quest_count": 1976},
            "guide": {"tasks": {"guide": {"ok": True}, "guide_items": {"ok": True}}},
            "success": {"tasks": {"success": {"ok": True}, "success_names": {"ok": True}}},
        }

        def fake_domain(name, _manifest):
            order.append(name)
            return payloads[name], "reused", 1.0

        with (
            patch.object(warmup, "_write_result", side_effect=lambda payload: publications.append(dict(payload))),
            patch.object(warmup, "_load_manifest", return_value={}),
            patch.object(warmup, "_run_or_reuse_domain", side_effect=fake_domain),
            patch.dict(warmup.os.environ, {"DOFUS_ATLAS_WARMUP_GO_FILE": ""}),
        ):
            final = warmup.run_warmup("exact-session")

        self.assertEqual(order, ["quest", "guide", "success"])
        self.assertEqual(publications[0]["status"], "running")
        self.assertEqual(publications[1]["completed_domains"], ["quest"])
        self.assertEqual(publications[1]["quest_count"], 1976)
        self.assertFalse(publications[1]["encyclopedia_ready"])
        self.assertEqual(publications[-1]["completed_domains"], ["quest", "guide", "success"])
        self.assertTrue(publications[-1]["encyclopedia_ready"])
        self.assertEqual(final["status"], "ready")
        self.assertEqual(final["completed_domains"], order)

    def test_source_stamp_includes_enrichment_for_quest_and_guide(self) -> None:
        enriched = warmup._QUEST_ENRICHED_SOURCE
        self.assertIn(enriched, warmup._source_paths("quest"))
        self.assertIn(enriched, warmup._source_paths("guide"))
        self.assertNotIn(enriched, warmup._source_paths("success"))

    def test_quest_cache_reuse_rejects_missing_or_incomplete_detail_indexes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory)
            catalog = source / "catalog.sqlite3"
            offset = source / "source_offset.sqlite3"
            catalog.write_bytes(b"catalog")
            with sqlite3.connect(offset) as connection:
                connection.execute(
                    "CREATE TABLE offsets (key TEXT PRIMARY KEY, start INTEGER, end INTEGER)"
                )
                connection.execute("INSERT INTO offsets VALUES ('42', 10, 20)")
            lookup = {"catalog": catalog, "offset": offset}
            result = {
                "domain": "quest",
                "quest_count": 1976,
                "detail_source_index_count": 1,
                "detail_index_artifact_count": 1,
                "cache_files": ["catalog", "offset"],
            }
            sources = [["stamp_version", 2, 0]]
            with (
                patch.object(warmup, "_safe_artifact_path", side_effect=lambda name: lookup[name]),
                patch.object(warmup, "_quest_artifact_stamp", return_value=["catalog", 1976, 1]),
            ):
                stamp = warmup._artifact_stamp("quest", result["cache_files"])
                manifest = {"domains": {"quest": {
                    "source_stamp": sources, "artifact_stamp": stamp,
                    "result": result,
                }}}
                self.assertEqual(
                    warmup._cached_domain_result("quest", manifest, sources),
                    result,
                )
                # This is the regression: a valid catalogue must not mask
                # an absent prepared detail-offset index.
                offset.unlink()
                self.assertIsNone(
                    warmup._cached_domain_result("quest", manifest, sources)
                )
                offset.write_bytes(b"offset")
                broken = {**result, "cache_files": ["catalog"]}
                manifest["domains"]["quest"]["result"] = broken
                self.assertIsNone(
                    warmup._cached_domain_result("quest", manifest, sources)
                )
                legacy = {**result}
                legacy.pop("detail_index_artifact_count")
                manifest["domains"]["quest"]["result"] = legacy
                self.assertIsNone(
                    warmup._cached_domain_result("quest", manifest, sources)
                )

    def test_quest_source_offset_stamp_rejects_invalid_and_corrupt_databases(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "offset.sqlite3"
            path.write_bytes(b"not a SQLite source-offset index")
            invalid = warmup._quest_offset_artifact_stamp(path)
            self.assertEqual(invalid[1:], [-1, -1])
            path.unlink()

            with sqlite3.connect(path) as connection:
                connection.execute("CREATE TABLE something_else(id INTEGER)")
            missing_table = warmup._quest_offset_artifact_stamp(path)
            self.assertEqual(missing_table[1:], [-1, -1])
            path.unlink()

            with sqlite3.connect(path) as connection:
                connection.execute(
                    "CREATE TABLE offsets (key TEXT PRIMARY KEY, start INTEGER, end INTEGER)"
                )
                connection.execute("INSERT INTO offsets VALUES ('bad', 30, 10)")
            bad_span = warmup._quest_offset_artifact_stamp(path)
            self.assertEqual(bad_span[1:], [-1, -1])
            path.unlink()

            with sqlite3.connect(path) as connection:
                connection.execute(
                    "CREATE TABLE offsets (key TEXT PRIMARY KEY, start INTEGER, end INTEGER)"
                )
                connection.execute("INSERT INTO offsets VALUES ('42', 10, 20)")
            valid = warmup._quest_offset_artifact_stamp(path)
            self.assertGreater(valid[1], 0)
            self.assertGreater(valid[2], 0)
            self.assertEqual(valid[0], warmup._path_label(path))

    def test_cold_warmup_wait_requires_real_sampler_signal(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            go_file = Path(temp_dir) / "memory-sampler.ready"
            with self.assertRaisesRegex(TimeoutError, "sampler"):
                warmup._wait_for_memory_sampler(str(go_file), timeout=0.0)
            go_file.touch()
            warmup._wait_for_memory_sampler(str(go_file), timeout=0.0)

    def test_windows_worker_does_not_create_a_hidden_console(self) -> None:
        completed = SimpleNamespace(returncode=0, stdout='{"ok":true}', stderr="")
        with (
            patch.object(warmup.os, "name", "nt"),
            patch.object(warmup.subprocess, "DETACHED_PROCESS", 0x00000008, create=True),
            patch.object(warmup.subprocess, "run", return_value=completed) as run,
        ):
            self.assertEqual(warmup._run_module("fake.worker", "--example"), '{"ok":true}')
        command, = run.call_args.args
        self.assertEqual(command[1:], ["-m", "fake.worker", "--example"])
        options = run.call_args.kwargs
        self.assertEqual(options["creationflags"], 0x00000008)
        self.assertEqual(options["stdin"], subprocess.DEVNULL)
        self.assertEqual(options["stdout"], subprocess.PIPE)
        self.assertEqual(options["stderr"], subprocess.PIPE)
        self.assertEqual(options["timeout"], 180)

    def test_non_windows_worker_keeps_standard_child_flags(self) -> None:
        completed = SimpleNamespace(returncode=0, stdout="done", stderr="")
        with (
            patch.object(warmup.os, "name", "posix"),
            patch.object(warmup.subprocess, "run", return_value=completed) as run,
        ):
            self.assertEqual(warmup._run_module("fake.worker"), "done")
        self.assertNotIn("creationflags", run.call_args.kwargs)


if __name__ == "__main__":
    unittest.main()
