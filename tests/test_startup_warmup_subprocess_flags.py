from __future__ import annotations

import copy
import json
import subprocess
import sqlite3
from contextlib import closing
import tempfile
from pathlib import Path
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from app import startup_cache_warmup as warmup
from app import startup_cache_domain_worker as domain_worker


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

    def test_quest_and_guide_source_changes_trigger_windows_focused_proof(self):
        workflow = (
            Path(__file__).resolve().parents[1]
            / ".github" / "workflows" / "guides-focused-proof.yml"
        ).read_text(encoding="utf-8")
        for source in (
            "app/quest_source_index.py",
            "app/startup_cache_domain_worker.py",
            "app/startup_cache_warmup.py",
            "tests/test_quest_source_boundaries.py",
            "tests/test_startup_warmup_subprocess_flags.py",
        ):
            with self.subTest(source=source):
                self.assertIn("      - '" + source + "'", workflow)

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
            with closing(sqlite3.connect(offset)) as connection, connection:
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

            with closing(sqlite3.connect(path)) as connection, connection:
                connection.execute("CREATE TABLE something_else(id INTEGER)")
            missing_table = warmup._quest_offset_artifact_stamp(path)
            self.assertEqual(missing_table[1:], [-1, -1])
            path.unlink()

            with closing(sqlite3.connect(path)) as connection, connection:
                connection.execute(
                    "CREATE TABLE offsets (key TEXT PRIMARY KEY, start INTEGER, end INTEGER)"
                )
            self.assertEqual(
                warmup._quest_offset_artifact_stamp(path)[1:], [-1, -1],
                "An empty offsets table is not an initialized Quest source index",
            )
            path.unlink()

            with closing(sqlite3.connect(path)) as connection, connection:
                connection.execute(
                    "CREATE TABLE offsets (key TEXT PRIMARY KEY, start INTEGER, end INTEGER)"
                )
                connection.execute("INSERT INTO offsets VALUES ('bad', 30, 10)")
            bad_span = warmup._quest_offset_artifact_stamp(path)
            self.assertEqual(bad_span[1:], [-1, -1])
            path.unlink()

            with closing(sqlite3.connect(path)) as connection, connection:
                connection.execute(
                    "CREATE TABLE offsets (key TEXT PRIMARY KEY, start INTEGER, end INTEGER)"
                )
                connection.execute("INSERT INTO offsets VALUES ('42', 10, 20)")
            valid = warmup._quest_offset_artifact_stamp(path)
            self.assertGreater(valid[1], 0)
            self.assertGreater(valid[2], 0)
            self.assertEqual(valid[0], warmup._path_label(path))

    def test_duplicate_and_malformed_domain_artifacts_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            artifact = root / "cache.bin"
            artifact.write_bytes(b"valid cache fixture")
            with patch.object(warmup, "ROOT", root):
                self.assertEqual(
                    warmup._artifact_stamp("guide", ["cache.bin", "./cache.bin"]), [],
                )
                self.assertEqual(
                    warmup._artifact_stamp("guide", ["cache.bin", "cache.bin"]), [],
                )
                for invalid in (True, 1, None, " cache.bin ", ""):
                    with self.subTest(value=invalid):
                        self.assertIsNone(warmup._safe_artifact_path(invalid))
                        self.assertEqual(
                            warmup._artifact_stamp("guide", ["cache.bin", invalid]), [],
                        )
                self.assertGreater(
                    warmup._artifact_stamp("guide", ["cache.bin"])[0][1], 0,
                )

    def test_quest_catalogue_ready_marker_must_be_exactly_one(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "quest.sqlite3"
            with closing(sqlite3.connect(path)) as connection, connection:
                connection.execute("CREATE TABLE metadata (key TEXT PRIMARY KEY, value TEXT)")
                connection.execute("CREATE TABLE quests (id INTEGER PRIMARY KEY)")
                connection.execute("INSERT INTO quests VALUES (42)")
                connection.execute("INSERT INTO metadata VALUES ('ready', '0')")
            self.assertEqual(warmup._quest_artifact_stamp(path)[1:], [-1, 0])
            with closing(sqlite3.connect(path)) as connection, connection:
                connection.execute("UPDATE metadata SET value = 'true' WHERE key = 'ready'")
            self.assertEqual(warmup._quest_artifact_stamp(path)[1:], [-1, 0])
            with closing(sqlite3.connect(path)) as connection, connection:
                connection.execute("UPDATE metadata SET value = '1' WHERE key = 'ready'")
            self.assertEqual(warmup._quest_artifact_stamp(path)[1:], [1, 1])

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


    def test_relative_special_character_sqlite_stamps_are_read_only(self):
        # The bundle may use relative paths and Qt/Windows paths can include
        # spaces, accented letters and #. File URIs must encode them correctly.
        with tempfile.TemporaryDirectory(dir=".") as temporary:
            directory = Path(temporary).relative_to(Path.cwd())
            quest = directory / "cache été #1.sqlite3"
            offset = directory / "offset été #2.sqlite3"
            with closing(sqlite3.connect(quest)) as connection, connection:
                connection.execute("CREATE TABLE metadata (key TEXT PRIMARY KEY, value TEXT)")
                connection.execute("INSERT INTO metadata VALUES ('ready', '1')")
                connection.execute("CREATE TABLE quests (id INTEGER PRIMARY KEY)")
                connection.execute("INSERT INTO quests VALUES (42)")
            with closing(sqlite3.connect(offset)) as connection, connection:
                connection.execute("CREATE TABLE offsets (key TEXT PRIMARY KEY, start INTEGER, end INTEGER)")
                connection.execute("INSERT INTO offsets VALUES ('42', 10, 20)")
            self.assertFalse(quest.is_absolute())
            with patch.object(warmup.sqlite3, "connect", wraps=sqlite3.connect) as connect:
                quest_stamp = warmup._quest_artifact_stamp(quest)
                offset_stamp = warmup._quest_offset_artifact_stamp(offset)
            self.assertEqual(quest_stamp[1:], [1, 1])
            self.assertGreater(offset_stamp[1], 0)
            self.assertEqual(offset_stamp[0], warmup._path_label(offset))
            self.assertEqual(connect.call_count, 2)
            for call in connect.call_args_list:
                self.assertTrue(call.kwargs["uri"])
                self.assertEqual(call.kwargs["timeout"], 1)
                self.assertIn("mode=ro", call.args[0])
                self.assertIn("%23", call.args[0])

    def test_atomic_warmup_publication_preserves_old_result_on_failure(self):
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary) / "manifest.json"
            previous = '{"schema_version": 2, "status": "ready"}'
            target.write_text(previous, encoding="utf-8")
            for method in ("write_text", "replace"):
                with self.subTest(failing_method=method):
                    with patch.object(Path, method, side_effect=OSError("disk failure")):
                        with self.assertRaisesRegex(OSError, "disk failure"):
                            warmup._write_json_atomic(target, {"status": "new"})
                    self.assertEqual(target.read_text(encoding="utf-8"), previous)
                    self.assertEqual(list(target.parent.glob(".*.tmp")), [])


    def test_success_builder_forces_real_repair_when_sidecar_is_invalid(self):
        from contextlib import nullcontext
        from app.modules.encyclopedia.providers import (
            memory_bound_achievement_provider as provider,
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "success.jsonl"
            index = provider._achievement_compact_index_path(path)
            index.write_text('{"achievement_count":4}', encoding="utf-8")
            with (
                patch.object(provider, "_achievement_compact_cache_valid", return_value=True),
                patch.object(provider, "_achievement_compact_write_lock", side_effect=lambda _: nullcontext()),
                patch.object(provider, "_build_compact_cache_unlocked", return_value=0) as rebuild,
            ):
                self.assertEqual(provider._build_compact_cache(path), 0)
                rebuild.assert_not_called()
                self.assertEqual(provider._build_compact_cache(path, True), 0)
                rebuild.assert_called_once_with(path)

    def test_corrupt_success_index_counts_are_never_reused(self):
        with tempfile.TemporaryDirectory() as directory:
            index = Path(directory) / "success.idx.json"
            jsonl = Path(directory) / "success.jsonl"
            jsonl.write_bytes(b"x" * 100)
            valid = {
                "schema_version": 5,
                "achievement_count": 4,
                "retained_count": 2,
                "retained_ids": [10, 20],
                "offsets": {"10": [0, 4], "20": [4, 8]},
            }
            index.write_text(json.dumps(valid), encoding="utf-8")
            self.assertEqual(domain_worker._read_compact_success_counts(index, 5, jsonl), (4, 2))
            for changes in (
                {"schema_version": 4},
                {"achievement_count": "4"},
                {"retained_count": True},
                {"retained_count": 9},
                {"retained_ids": [10]},
                {"retained_ids": [10, "20"]},
                {"offsets": {"10": [0, 4]}},
                {"retained_ids": [10, 10]},
                {"offsets": {"10": [99, 4], "20": [4, 8]}},
                {"offsets": {"10": [0, 0], "20": [4, 8]}},
                {"offsets": {"10": [True, 4], "20": [4, 8]}},
                {"offsets": {"30": [0, 4], "20": [4, 8]}},
            ):
                with self.subTest(changes=changes):
                    index.write_text(json.dumps({**valid, **changes}), encoding="utf-8")
                    self.assertIsNone(domain_worker._read_compact_success_counts(index, 5, jsonl))
            index.write_text("{not valid json", encoding="utf-8")
            self.assertIsNone(domain_worker._read_compact_success_counts(index, 5, jsonl))
            index.write_text(json.dumps(valid), encoding="utf-8")
            jsonl.unlink()
            self.assertIsNone(domain_worker._read_compact_success_counts(index, 5, jsonl))

    def test_header_only_or_truncated_guide_compact_cache_rebuilds(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "guides.jsonl"
            meta = json.dumps({"kind": "meta", "schema_version": 1}) + "\n"
            guide = json.dumps({"kind": "guide", "value": {"id": "route-1"}}) + "\n"
            path.write_text(meta, encoding="utf-8")
            self.assertEqual(domain_worker._count_valid_compact_guides(path), 0)
            path.write_text(meta + guide + "{malformed", encoding="utf-8")
            self.assertEqual(domain_worker._count_valid_compact_guides(path), 0)
            path.write_text(meta + guide, encoding="utf-8")
            self.assertEqual(domain_worker._count_valid_compact_guides(path), 1)
            path.write_text(meta + '{"kind":"guide","value":null}\n', encoding="utf-8")
            self.assertEqual(domain_worker._count_valid_compact_guides(path), 0)

    def test_domain_builder_discarded_stdout_is_not_buffered(self):
        # Large build logs must not accumulate in a StringIO at the peak.
        class Printed(RuntimeError):
            pass

        def builder(label):
            for _ in range(50):
                print("verbose source record " * 200)
            return f"done:{label}"

        with patch("builtins.open", wraps=open) as opened:
            self.assertEqual(domain_worker._quiet_call(builder, "quest"), "done:quest")
        self.assertEqual(opened.call_count, 1)
        self.assertEqual(opened.call_args.args[0], domain_worker.os.devnull)

        def failing_builder():
            print("discarded error output")
            raise Printed("source corrupt")

        with self.assertRaisesRegex(Printed, "source corrupt"):
            domain_worker._quiet_call(failing_builder)


    def test_warmup_rejects_empty_domain_counts_in_new_and_reused_caches(self):
        payloads = {
            "quest": {
                "domain": "quest", "quest_count": 1976,
                "detail_source_index_count": 1, "detail_index_artifact_count": 1,
                "cache_files": ["catalog.sqlite3", "offset.sqlite3"],
            },
            "guide": {
                "domain": "guide", "cache_files": ["guide.jsonl"],
                "tasks": {
                    "guide": {"guide_count": 26, "manual_card_count": 267},
                    "guide_items": {"item_count": 120},
                },
            },
            "success": {
                "domain": "success", "cache_files": ["success.jsonl"],
                "tasks": {
                    "success": {"achievement_count": 1412, "retained_count": 1412},
                    "success_names": {"achievement_name_count": 1412},
                },
            },
        }
        for domain, payload in payloads.items():
            with self.subTest(domain=domain):
                self.assertTrue(warmup._domain_payload_complete(domain, payload))
                manifest = {"domains": {domain: {
                    "source_stamp": [["source", 1, 2]],
                    "artifact_stamp": [["cache", 99, 1]],
                    "result": payload,
                }}}
                with patch.object(warmup, "_artifact_stamp", return_value=[["cache", 99, 1]]):
                    self.assertEqual(
                        warmup._cached_domain_result(domain, manifest, [["source", 1, 2]]),
                        payload,
                    )
                damaged = copy.deepcopy(payload)
                if domain == "quest":
                    damaged["quest_count"] = 0
                elif domain == "guide":
                    damaged["tasks"]["guide"]["manual_card_count"] = 0
                else:
                    damaged["tasks"]["success_names"]["achievement_name_count"] = False
                self.assertFalse(warmup._domain_payload_complete(domain, damaged))
                manifest["domains"][domain]["result"] = damaged
                with patch.object(warmup, "_artifact_stamp", return_value=[["cache", 99, 1]]):
                    self.assertIsNone(
                        warmup._cached_domain_result(domain, manifest, [["source", 1, 2]])
                    )
                with patch.object(warmup, "_run_module", return_value=json.dumps(damaged)):
                    with self.assertRaisesRegex(RuntimeError, "incomplete counts"):
                        warmup._run_domain(domain)


if __name__ == "__main__":
    unittest.main()
