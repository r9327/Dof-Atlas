from __future__ import annotations

import contextlib
import io
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch
from pathlib import Path

from tools.atlas_json_benchmark import benchmark, compare_json_parsers, compare_json_streaming, compare_json_compression
from tools.atlas_json_shards import build


class AtlasJsonBenchmarkTests(unittest.TestCase):
    def test_json_trial_is_catalog_discoverable_without_runtime_import(self) -> None:
        from tools.tool_catalog import _validated_tool_spec
        path = Path(__file__).resolve().parents[1] / "tools/atlas_json_benchmark.py"
        spec, errors = _validated_tool_spec(
            path.read_text(encoding="utf-8"), "tools/atlas_json_benchmark.py")
        self.assertEqual(errors, [])
        self.assertEqual(spec["id"], "quest_json_benchmark")
        self.assertTrue(spec["canonical"])
        self.assertEqual(spec["side_effects"], "artifact_output")
        self.assertIn("compare_compression", spec["modes"])
        self.assertIn("tests.test_atlas_json_benchmark",
                      spec["recommended_tests"])

    def test_bounded_source_read_rejects_growth_without_unlimited_read(self) -> None:
        from tools.atlas_json_benchmark import _read_bounded_source

        class RecordingReader(io.BytesIO):
            def __init__(self, value: bytes):
                super().__init__(value)
                self.requested = []

            def read(self, size: int = -1) -> bytes:
                self.requested.append(size)
                if size < 0:
                    raise AssertionError("unbounded read attempted")
                return super().read(size)

        reader = RecordingReader(b"0123456789")
        with patch.object(Path, "open", return_value=reader):
            with self.assertRaisesRegex(ValueError, "size budget"):
                _read_bounded_source(Path("not-used.json"), 4)
        self.assertEqual(reader.requested, [5])

        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "sample.json"
            source.write_text('{"id":1}', encoding="utf-8")
            self.assertEqual(_read_bounded_source(source, 8), b'{"id":1}')
            with patch.object(Path, "read_bytes", side_effect=AssertionError(
                    "benchmark must not read an entire path without bound")):
                result = compare_json_parsers(
                    source, candidates=("stdlib",), repeats=1, max_bytes=8)
            self.assertEqual(result["status"], "COMPARE_COMPLETE")

    def test_compare_both_strategies_without_mutating_source(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "canonical" / "quests_enriched.json"
            source.parent.mkdir()
            rows = {
                str(i): {
                    "name": f"Quête {i}",
                    "details": ["{}[]\\\\\\\"" * 30, None, i],
                }
                for i in range(1, 77)
            }
            original = json.dumps({"quests": rows}, ensure_ascii=False)
            source.write_text(original, encoding="utf-8")
            shards = root / "derived"
            build(source, shards, ids_per_shard=12)
            result = benchmark(source, shards, sample_count=11)

            self.assertTrue(result["lookup_values_equal"])
            self.assertEqual(result["sample_count"], 11)
            self.assertEqual(result["record_count"], 76)
            self.assertEqual(result["shard_count"], 7)
            self.assertFalse(result["runtime_consumers_changed"])
            self.assertGreaterEqual(result["source_offset_lookup_seconds"], 0)
            self.assertGreaterEqual(result["derived_shard_lookup_seconds"], 0)
            self.assertEqual(source.read_text(encoding="utf-8"), original)

    def test_optional_parser_comparison_reuses_bytes_and_preserves_source(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "sample.json"
            original = '{"quests":{"7":{"name":"Étoile","n":8},"12":{"s":"\\\\u00e9"}}}'
            source.write_text(original, encoding="utf-8")
            with patch("tools.atlas_json_benchmark.importlib.import_module",
                       return_value=SimpleNamespace(loads=json.loads, decode=json.loads)):
                result = compare_json_parsers(source, repeats=2)
            self.assertEqual(result["status"], "COMPARE_COMPLETE")
            self.assertEqual([x["name"] for x in result["results"]],
                             ["stdlib", "orjson", "msgspec"])
            self.assertTrue(all(x["status"] == "PARITY_PASS" for x in result["results"]))
            self.assertTrue(all(len(x["measurements_ms"]) == 2 for x in result["results"]))
            self.assertFalse(result["runtime_consumer_changed"])
            self.assertEqual(source.read_text(encoding="utf-8"), original)

    def test_msgspec_uses_actual_json_decode_api_not_nonexistent_loads(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "quests.json"
            source.write_text('{"quests":{"1":{"name":"Etude","n":8}}}',
                              encoding="utf-8")
            calls = []
            def load(module_name):
                calls.append(module_name)
                if module_name != "msgspec.json":
                    raise AssertionError("Wrong optional parser import")
                return SimpleNamespace(decode=json.loads)

            with patch("tools.atlas_json_benchmark.importlib.import_module",
                       side_effect=load):
                result = compare_json_parsers(
                    source, candidates=("msgspec",), repeats=2)
            self.assertEqual(calls, ["msgspec.json"])
            self.assertEqual(result["status"], "COMPARE_COMPLETE")
            self.assertEqual(result["results"][0]["name"], "msgspec")
            self.assertEqual(result["results"][0]["status"], "PARITY_PASS")
            self.assertEqual(result["results"][0]["repeats"], 2)

    def test_msgspec_missing_decoder_or_uncallable_decoder_is_not_pass(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "s.json"
            source.write_text('{"id":7}', encoding="utf-8")
            for bad_module in (SimpleNamespace(loads=json.loads),
                               SimpleNamespace(decode=None)):
                with self.subTest(module=bad_module):
                    with patch("tools.atlas_json_benchmark.importlib.import_module",
                               return_value=bad_module):
                        result = compare_json_parsers(
                            source, candidates=("msgspec",))
                    self.assertEqual(result["status"], "REVIEW")
                    self.assertEqual(result["results"][0]["status"], "NOT_AVAILABLE")
                    self.assertFalse(result["results"][0]["executed"])

    def test_missing_and_incorrect_parser_cannot_claim_parity(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "s.json"
            source.write_text('{"id":7}', encoding="utf-8")
            with patch("tools.atlas_json_benchmark.importlib.import_module",
                       side_effect=ImportError("not installed")):
                result = compare_json_parsers(source, candidates=("stdlib", "orjson"))
            self.assertEqual([x["status"] for x in result["results"]],
                             ["PARITY_PASS", "NOT_AVAILABLE"])
            self.assertEqual(result["status"], "REVIEW")
            with patch("tools.atlas_json_benchmark.importlib.import_module",
                       return_value=SimpleNamespace(decode=lambda _: {"id": 8})):
                result = compare_json_parsers(source, candidates=("msgspec",))
            self.assertEqual(result["results"][0]["status"], "PARITY_FAIL")
            self.assertEqual(result["status"], "REVIEW")

    def test_parser_parity_requires_exact_json_scalar_types(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "quests.json"
            source.write_text(
                '{"quests":{"1":{"value":1,"ratio":1.0,"active":true}}}',
                encoding="utf-8")
            payload = json.loads(source.read_text(encoding="utf-8"))
            alternatives = [
                {"quests": {"1": {"value": True, "ratio": 1.0, "active": True}}},
                {"quests": {"1": {"value": 1, "ratio": 1, "active": True}}},
                {"quests": {"1": {"value": 1, "ratio": 1.0, "active": 1}}},
            ]
            self.assertEqual(payload["quests"]["1"]["value"], True)
            for replacement in alternatives:
                with self.subTest(replacement=replacement):
                    with patch("tools.atlas_json_benchmark.importlib.import_module",
                               return_value=SimpleNamespace(decode=lambda _: replacement)):
                        result = compare_json_parsers(source, candidates=("msgspec",))
                    self.assertEqual(result["status"], "REVIEW")
                    self.assertEqual(result["results"][0]["status"], "PARITY_FAIL")
            # Reordering JSON object keys is equivalent; array order is not.
            reordered = {"quests": {"1": {"active": True, "ratio": 1.0, "value": 1}}}
            with patch("tools.atlas_json_benchmark.importlib.import_module",
                       return_value=SimpleNamespace(loads=lambda _: reordered)):
                result = compare_json_parsers(source, candidates=("orjson",))
            self.assertEqual(result["results"][0]["status"], "PARITY_PASS")

    def test_streaming_rejects_numeric_type_coercion_in_quest_values(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "quests.json"
            source.write_text('{"quests":{"1":{"required":1,"active":true}}}',
                              encoding="utf-8")
            for wrong in ({"required": True, "active": True},
                          {"required": 1.0, "active": True},
                          {"required": 1, "active": 1}):
                with self.subTest(wrong=wrong):
                    fake = SimpleNamespace(
                        kvitems=lambda *_args, **_kwargs: iter([("1", wrong)]))
                    with patch("tools.atlas_json_benchmark.importlib.import_module",
                               return_value=fake):
                        report = compare_json_streaming(source)
                    self.assertEqual(report["status"], "PARITY_FAIL")

    def test_nested_json_arrays_keep_exact_types_and_order(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "quests.json"
            source.write_text(
                '{"quests":{"1":{"steps":[1,true,3],"meta":{"kind":"A"}}}}',
                encoding="utf-8")
            altered = (
                {"quests": {"1": {"steps": [1.0, True, 3],
                                   "meta": {"kind": "A"}}}},
                {"quests": {"1": {"steps": [3, True, 1],
                                   "meta": {"kind": "A"}}}},
                {"quests": {"1": {"steps": [1, True, 3],
                                   "meta": {"kind": "B"}}}},
            )
            for replacement in altered:
                with self.subTest(replacement=replacement):
                    with patch("tools.atlas_json_benchmark.importlib.import_module",
                               return_value=SimpleNamespace(loads=lambda _: replacement)):
                        result = compare_json_parsers(
                            source, candidates=("orjson",), repeats=1)
                    self.assertEqual(result["results"][0]["status"], "PARITY_FAIL")

    def test_parser_trials_reject_input_symlinks(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            original = Path(tmp) / "original.json"
            alias = Path(tmp) / "alias.json"
            original.write_text('{"quests":{"1":{}}}', encoding="utf-8")
            try:
                alias.symlink_to(original)
            except (OSError, NotImplementedError):
                self.skipTest("Symlinks unavailable in this environment")
            with self.assertRaises(ValueError):
                compare_json_parsers(alias)
            with self.assertRaises(ValueError):
                compare_json_streaming(alias)

    def test_parser_trial_rejects_unbounded_or_unknown_configuration(self) -> None:
        with self.assertRaises(ValueError):
            compare_json_parsers(Path("missing"), repeats=0)
        with self.assertRaises(ValueError):
            compare_json_parsers(Path("missing"), candidates=("stdlib", "stdlib"))
        with self.assertRaises(ValueError):
            compare_json_parsers(Path("missing"), candidates=("ijson",))

    def test_ijson_stream_checks_all_quest_ids_not_only_samples(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "quests.json"
            path.write_text(json.dumps({"quests": {"1": {"name": "Émeraude"},
                                                  "2": {"n": 2}}}), encoding="utf-8")
            def kvitems(stream, prefix, *, use_float):
                self.assertEqual(prefix, "quests")
                self.assertTrue(use_float)
                return iter(json.loads(stream.read())["quests"].items())
            with patch("tools.atlas_json_benchmark.importlib.import_module",
                       return_value=SimpleNamespace(kvitems=kvitems)):
                report = compare_json_streaming(path)
            self.assertEqual(report["status"], "PARITY_PASS")
            self.assertEqual(report["record_count"], 2)
            self.assertTrue(report["executed"])
            def broken(stream, prefix, *, use_float):
                return iter([("1", {"name": "incorrect"})])
            with patch("tools.atlas_json_benchmark.importlib.import_module",
                       return_value=SimpleNamespace(kvitems=broken)):
                failed = compare_json_streaming(path)
            self.assertEqual(failed["status"], "PARITY_FAIL")

    def test_ijson_missing_reports_not_available(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "quests.json"
            path.write_text('{"quests":{"1":{}}}', encoding="utf-8")
            with patch("tools.atlas_json_benchmark.importlib.import_module",
                       side_effect=ImportError("not installed")):
                report = compare_json_streaming(path)
            self.assertEqual(report["status"], "NOT_AVAILABLE")
            self.assertFalse(report["executed"])
            with self.assertRaises(ValueError):
                compare_json_streaming(path, max_bytes=1)

    def test_streaming_failure_paths_also_detect_source_mutation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "quests.json"
            original = '{"quests":{"1":{"required":1}}}'
            changed = '{"quests":{"1":{"required":2}}}'

            def unavailable(_name):
                path.write_text(changed, encoding="utf-8")
                raise ImportError("ijson absent after import side effect")

            def invalid_stream(_stream, _prefix, *, use_float):
                path.write_text(changed, encoding="utf-8")
                return iter([("1", {"required": 3})])

            def exploding_stream(_stream, _prefix, *, use_float):
                path.write_text(changed, encoding="utf-8")
                raise RuntimeError("backend failed after side effect")

            scenarios = (
                {"side_effect": unavailable},
                {"return_value": SimpleNamespace(kvitems=invalid_stream)},
                {"return_value": SimpleNamespace(kvitems=exploding_stream)},
            )
            for patched in scenarios:
                with self.subTest(scenario=list(patched)):
                    path.write_text(original, encoding="utf-8")
                    with patch("tools.atlas_json_benchmark.importlib.import_module",
                               **patched):
                        with self.assertRaisesRegex(ValueError, "Source changed"):
                            compare_json_streaming(path)

    def test_third_party_parser_crashes_are_explicit_errors(self) -> None:
        def crashed(_):
            raise RuntimeError("simulated third-party parser failure")
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "quests.json"
            source.write_text('{"quests":{"1":{}}}', encoding="utf-8")
            with patch("tools.atlas_json_benchmark.importlib.import_module",
                       return_value=SimpleNamespace(loads=crashed)):
                trial = compare_json_parsers(source, candidates=("orjson",))
            self.assertEqual(trial["status"], "REVIEW")
            self.assertEqual(trial["results"][0]["status"], "ERROR")
            def fail_stream(*_args, **_kwargs):
                raise RuntimeError("simulated broken backend")
            with patch("tools.atlas_json_benchmark.importlib.import_module",
                       return_value=SimpleNamespace(kvitems=fail_stream)):
                trial = compare_json_streaming(source)
            self.assertEqual(trial["status"], "ERROR")
            self.assertEqual(trial["error_type"], "RuntimeError")

    def test_lossless_compression_comparison_with_optional_zstandard(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "quests.json"
            original = json.dumps({"quests": {"1": {"name": "Émeraude"}}})
            source.write_text(original, encoding="utf-8")
            import zlib
            fake_zstd = SimpleNamespace(
                ZstdCompressor=lambda level: SimpleNamespace(compress=zlib.compress),
                ZstdDecompressor=lambda: SimpleNamespace(
                    decompress=lambda blob, max_output_size: zlib.decompress(blob)),
            )
            with patch("tools.atlas_json_benchmark.importlib.import_module",
                       return_value=fake_zstd):
                trial = compare_json_compression(source)
            self.assertEqual(trial["status"], "COMPARE_COMPLETE")
            self.assertEqual([row["name"] for row in trial["results"]],
                             ["zlib", "zstandard"])
            self.assertTrue(all(row["status"] == "PARITY_PASS"
                                for row in trial["results"]))
            self.assertEqual(source.read_text(encoding="utf-8"), original)
            self.assertFalse(trial["runtime_consumer_changed"])

    def test_missing_or_corrupt_compression_backend_is_not_success(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "s.json"
            path.write_text('{"quests":{}}', encoding="utf-8")
            with patch("tools.atlas_json_benchmark.importlib.import_module",
                       side_effect=ImportError("no zstd")):
                trial = compare_json_compression(path)
            self.assertEqual(trial["status"], "REVIEW")
            self.assertEqual(trial["results"][1]["status"], "NOT_AVAILABLE")
            bad = SimpleNamespace(
                ZstdCompressor=lambda level: SimpleNamespace(
                    compress=lambda data: b"invalid"),
                ZstdDecompressor=lambda: SimpleNamespace(
                    decompress=lambda blob, max_output_size: b"wrong"),
            )
            with patch("tools.atlas_json_benchmark.importlib.import_module",
                       return_value=bad):
                trial = compare_json_compression(path)
            self.assertEqual(trial["status"], "REVIEW")
            self.assertEqual(trial["results"][1]["status"], "ERROR")
            with self.assertRaises(ValueError):
                compare_json_compression(path, max_bytes=0)

    def test_optional_json_trials_refuse_changed_source_after_execution(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "canonical.json"
            original = '{"quests":{"1":{"required":1}}}'
            altered = '{"quests":{"1":{"required":2}}}'

            def mutating_parser(blob):
                path.write_text(altered, encoding="utf-8")
                return json.loads(blob)

            path.write_text(original, encoding="utf-8")
            with patch("tools.atlas_json_benchmark.importlib.import_module",
                       return_value=SimpleNamespace(loads=mutating_parser)):
                with self.assertRaisesRegex(ValueError, "Source changed"):
                    compare_json_parsers(path, candidates=("orjson",))

            def mutating_stream(stream, prefix, *, use_float):
                path.write_text(altered, encoding="utf-8")
                return iter(json.loads(stream.read())["quests"].items())

            path.write_text(original, encoding="utf-8")
            with patch("tools.atlas_json_benchmark.importlib.import_module",
                       return_value=SimpleNamespace(kvitems=mutating_stream)):
                with self.assertRaisesRegex(ValueError, "Source changed"):
                    compare_json_streaming(path)

            import zlib
            def mutating_compressor(data):
                path.write_text(altered, encoding="utf-8")
                return zlib.compress(data)

            fake_zstd = SimpleNamespace(
                ZstdCompressor=lambda level: SimpleNamespace(
                    compress=mutating_compressor),
                ZstdDecompressor=lambda: SimpleNamespace(
                    decompress=lambda data, max_output_size: zlib.decompress(data)),
            )
            path.write_text(original, encoding="utf-8")
            with patch("tools.atlas_json_benchmark.importlib.import_module",
                       return_value=fake_zstd):
                with self.assertRaisesRegex(ValueError, "Source changed"):
                    compare_json_compression(path)

    def test_comparison_cli_exit_codes_are_not_fake_success(self) -> None:
        from tools.atlas_json_benchmark import main
        scenarios = (
            ("--compare-parsers", "compare_json_parsers",
             {"status": "COMPARE_COMPLETE", "results": []}, 0),
            ("--compare-parsers", "compare_json_parsers",
             {"status": "REVIEW", "results": [
                 {"status": "NOT_AVAILABLE"}]}, 1),
            ("--compare-parsers", "compare_json_parsers",
             {"status": "REVIEW", "results": [
                 {"status": "PARITY_FAIL"}]}, 2),
            ("--compare-parsers", "compare_json_parsers",
             {"status": "REVIEW", "results": [
                 {"status": "ERROR"}]}, 2),
            ("--compare-streaming", "compare_json_streaming",
             {"status": "PARITY_PASS"}, 0),
            ("--compare-streaming", "compare_json_streaming",
             {"status": "NOT_AVAILABLE"}, 1),
            ("--compare-streaming", "compare_json_streaming",
             {"status": "PARITY_FAIL"}, 2),
            ("--compare-streaming", "compare_json_streaming",
             {"status": "ERROR"}, 2),
            ("--compare-compression", "compare_json_compression",
             {"status": "COMPARE_COMPLETE", "results": []}, 0),
            ("--compare-compression", "compare_json_compression",
             {"status": "REVIEW", "results": [
                 {"status": "NOT_AVAILABLE"}]}, 1),
            ("--compare-compression", "compare_json_compression",
             {"status": "REVIEW", "results": [
                 {"status": "ERROR"}]}, 2),
            ("--compare-parsers", "compare_json_parsers",
             {"status": "UNEXPECTED"}, 1),
        )
        for flag, function, response, expected in scenarios:
            with self.subTest(flag=flag, response=response):
                out = io.StringIO()
                with (patch("sys.argv", ["atlas_json_benchmark", flag]),
                      patch(f"tools.atlas_json_benchmark.{function}",
                            return_value=response) as trial,
                      contextlib.redirect_stdout(out)):
                    exit_code = main()
                self.assertEqual(exit_code, expected)
                self.assertEqual(json.loads(out.getvalue()), response)
                trial.assert_called_once()

    def test_json_cli_emits_error_report_file_even_on_failure(self) -> None:
        from tools.atlas_json_benchmark import main
        with tempfile.TemporaryDirectory() as tmp:
            report = Path(tmp) / "result.json"
            response = {"status": "REVIEW", "results": [
                {"name": "zstandard", "status": "NOT_AVAILABLE"}]}
            with (patch("sys.argv", [
                    "atlas_json_benchmark", "--compare-compression",
                    "--output", str(report)]),
                  patch("tools.atlas_json_benchmark.compare_json_compression",
                        return_value=response)):
                exit_code = main()
            self.assertEqual(exit_code, 1)
            self.assertEqual(json.loads(report.read_text(encoding="utf-8")),
                             response)

    def test_parser_worker_import_avoids_quest_index_and_shard_pipeline(self) -> None:
        root = Path(__file__).resolve().parents[1]
        command = [
            sys.executable, "-P", "-c",
            "import sys; import tools.atlas_json_benchmark; "
            "print(int('app.quest_source_index' in sys.modules)); "
            "print(int('tools.atlas_json_shards' in sys.modules))",
        ]
        env = os.environ.copy()
        env["PYTHONPATH"] = str(root)
        result = subprocess.run(command, cwd=root, env=env, capture_output=True,
                                text=True, timeout=20, check=False)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip().splitlines(), ["0", "0"])

    def test_process_trial_runs_real_stdlib_in_isolated_python(self) -> None:
        from tools.atlas_json_benchmark import compare_json_processes
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "quests.json"
            source.write_text(
                '{"quests":{"1":{"name":"Astuce","steps":[1,true,3]},'
                '"2":{"items":[]}}}', encoding="utf-8")
            report = compare_json_processes(
                source, candidates=("stdlib",), repeats=2, timeout_seconds=30)
        self.assertEqual(report["source"], "tools.atlas_json_benchmark.compare_json_processes")
        self.assertFalse(report["runtime_consumer_changed"])
        self.assertFalse(report["phase_certified"])
        self.assertFalse(report["cold_start_certified"])
        self.assertEqual(len(report["results"]), 1)
        entry = report["results"][0]
        self.assertEqual(entry["candidate"], "stdlib")
        self.assertEqual(entry["status"], "PARITY_PASS")
        self.assertTrue(entry["executed"])
        self.assertEqual(entry["repeats"], 2)
        self.assertGreaterEqual(entry["first_decode_ms"], 0)
        self.assertGreaterEqual(entry["warm_median_ms"], 0)
        self.assertIn(entry["rss_status"], ("OBSERVED", "NOT_AVAILABLE"))
        self.assertGreaterEqual(entry["total_child_wall_ms"], 0)
        if entry["rss_status"] == "OBSERVED":
            self.assertGreater(entry["rss_before_bytes"], 0)
            self.assertGreater(entry["rss_after_first_bytes"], 0)
            self.assertGreater(entry["rss_after_warm_bytes"], 0)
            self.assertEqual(report["status"], "COMPARE_COMPLETE")
        else:
            self.assertEqual(report["status"], "REVIEW")

    def test_process_worker_resolves_msgspec_json_decode_with_real_type_parity(self) -> None:
        from tools.atlas_json_benchmark import _parser_process_worker
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "sample.json"
            source.write_text('{"id":1,"active":true}', encoding="utf-8")
            calls = []
            def fake_import(name):
                calls.append(name)
                if name == "msgspec.json":
                    return SimpleNamespace(decode=json.loads)
                if name == "psutil":
                    return SimpleNamespace(Process=lambda: SimpleNamespace(
                        memory_info=lambda: SimpleNamespace(rss=123456)))
                raise ImportError(name)
            with patch("tools.atlas_json_benchmark.importlib.import_module",
                       side_effect=fake_import):
                result = _parser_process_worker(source, "msgspec", 2)
        self.assertEqual(calls, ["msgspec.json", "psutil"])
        self.assertEqual(result["status"], "PARITY_CANDIDATE")
        self.assertEqual(result["rss_status"], "OBSERVED")
        self.assertEqual(result["rss_before_bytes"], 123456)
        self.assertEqual(result["decoded_sha256"],
                         hashlib.sha256(
                             b'{"active":true,"id":1}').hexdigest())

    def test_process_relative_timings_and_rss_require_real_stdlib_baseline(self) -> None:
        from tools.atlas_json_benchmark import _compare_process_metrics
        baseline = {"candidate": "stdlib", "status": "PARITY_PASS",
                    "first_decode_ms": 10.0, "warm_median_ms": 4.0,
                    "rss_status": "OBSERVED", "rss_before_bytes": 100,
                    "rss_after_warm_bytes": 300}
        optimized = {"candidate": "orjson", "status": "PARITY_PASS",
                     "first_decode_ms": 2.5, "warm_median_ms": 1.0,
                     "rss_status": "OBSERVED", "rss_before_bytes": 80,
                     "rss_after_warm_bytes": 160}
        missing = {"candidate": "msgspec", "status": "NOT_AVAILABLE"}
        results = [baseline, optimized, missing]
        _compare_process_metrics(results)
        self.assertNotIn("relative_to_stdlib", baseline)
        self.assertNotIn("relative_to_stdlib", missing)
        self.assertEqual(optimized["relative_to_stdlib"], {
            "first_use_speedup": 4.0,
            "warm_decode_speedup": 4.0,
            "stdlib_rss_delta_bytes": 200,
            "candidate_rss_delta_bytes": 80,
        })
        no_baseline = [dict(optimized, relative_to_stdlib=None)]
        _compare_process_metrics(no_baseline)
        self.assertIsNone(no_baseline[0]["relative_to_stdlib"])
        invalid = [dict(baseline, first_decode_ms=0,
                        warm_median_ms=None, rss_status="NOT_AVAILABLE"),
                   {"candidate": "orjson", "status": "PARITY_PASS",
                    "first_decode_ms": 1.0, "warm_median_ms": 1.0,
                    "rss_status": "OBSERVED"}]
        _compare_process_metrics(invalid)
        self.assertNotIn("relative_to_stdlib", invalid[1])

    def test_process_relative_metrics_ignore_failed_or_unsafe_worker_numbers(self) -> None:
        from tools.atlas_json_benchmark import _compare_process_metrics
        for incorrect in (float("nan"), -3.0, 0.0, "9", True):
            with self.subTest(value=incorrect):
                rows = [
                    {"candidate": "stdlib", "status": "PARITY_PASS",
                     "first_decode_ms": 4.0, "warm_median_ms": 3.0},
                    {"candidate": "orjson", "status": "PARITY_PASS",
                     "first_decode_ms": incorrect,
                     "warm_median_ms": incorrect},
                ]
                _compare_process_metrics(rows)
                self.assertNotIn("relative_to_stdlib", rows[1])

    def test_process_worker_cannot_claim_pass_with_missing_or_fake_measurements(self) -> None:
        from tools.atlas_json_benchmark import compare_json_processes
        from subprocess import CompletedProcess
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "source.json"
            source.write_text('{"id":1}', encoding="utf-8")
            payload = source.read_bytes()
            canonical = hashlib.sha256(b'{"id":1}').hexdigest()
            valid = {
                "status": "PARITY_CANDIDATE", "candidate": "stdlib",
                "source_sha256": hashlib.sha256(payload).hexdigest(),
                "decoded_sha256": canonical, "executed": True,
                "repeats": 2, "first_decode_ms": 1.0,
                "warm_median_ms": 0.5, "rss_status": "OBSERVED",
                "rss_before_bytes": 100, "rss_after_first_bytes": 200,
                "rss_after_warm_bytes": 220,
            }
            malformed = (
                {"first_decode_ms": None}, {"first_decode_ms": float("nan")},
                {"first_decode_ms": True}, {"warm_median_ms": None},
                {"repeats": 1}, {"executed": False}, {"executed": "yes"},
                {"rss_status": "OBSERVED", "rss_after_warm_bytes": None},
                {"rss_status": "OBSERVED", "rss_before_bytes": 0},
                {"rss_status": "OBSERVED", "rss_before_bytes": True},
                {"rss_status": "UNAVAILABLE"},
                {"rss_status": "NOT_AVAILABLE", "rss_after_warm_bytes": 100},
            )
            cases = [valid, *(dict(valid, **override) for override in malformed)]
            for n, row in enumerate(cases):
                with self.subTest(case=n):
                    done = CompletedProcess([], 0, stdout=json.dumps(row),
                                            stderr="")
                    with patch("tools.atlas_json_benchmark.subprocess.run",
                               return_value=done):
                        result = compare_json_processes(
                            source, candidates=("stdlib",), repeats=2)
                    if n == 0:
                        self.assertEqual(result["status"], "COMPARE_COMPLETE")
                        self.assertEqual(result["results"][0]["status"], "PARITY_PASS")
                    else:
                        self.assertEqual(result["status"], "REVIEW")
                        self.assertEqual(result["results"][0]["status"], "ERROR")

    def test_isolated_parser_allows_parity_without_optional_rss_but_not_complete(self) -> None:
        from tools.atlas_json_benchmark import compare_json_processes
        from subprocess import CompletedProcess
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "sample.json"
            source.write_text('{"id":1}', encoding="utf-8")
            row = {
                "status": "PARITY_CANDIDATE", "candidate": "stdlib",
                "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
                "decoded_sha256": hashlib.sha256(b'{"id":1}').hexdigest(),
                "executed": True, "repeats": 1, "first_decode_ms": 1.0,
                "warm_median_ms": None, "rss_status": "NOT_AVAILABLE",
                "rss_before_bytes": None, "rss_after_first_bytes": None,
                "rss_after_warm_bytes": None,
            }
            done = CompletedProcess([], 0, stdout=json.dumps(row), stderr="")
            with patch("tools.atlas_json_benchmark.subprocess.run",
                       return_value=done):
                report = compare_json_processes(
                    source, candidates=("stdlib",), repeats=1)
            self.assertEqual(report["status"], "REVIEW")
            self.assertEqual(report["results"][0]["status"], "PARITY_PASS")
            self.assertEqual(report["results"][0]["rss_status"], "NOT_AVAILABLE")

    def test_process_comparison_fails_closed_on_worker_impersonation(self) -> None:
        from tools.atlas_json_benchmark import compare_json_processes
        from subprocess import CompletedProcess
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "source.json"
            source.write_text('{"id":1}', encoding="utf-8")
            raw_sha = hashlib.sha256(source.read_bytes()).hexdigest()
            def fake_worker(status, candidate, digest, code):
                return CompletedProcess([], code, stdout=json.dumps({
                    "status": status, "candidate": candidate,
                    "source_sha256": digest, "decoded_sha256": "invalid",
                    "rss_status": "OBSERVED"}), stderr="")
            for output in (
                fake_worker("PARITY_CANDIDATE", "orjson", raw_sha, 0),
                fake_worker("PARITY_CANDIDATE", "stdlib", "0" * 64, 0),
                fake_worker("PARITY_CANDIDATE", "stdlib", raw_sha, 2),
                fake_worker("UNRECOGNIZED", "stdlib", raw_sha, 0),
            ):
                with self.subTest(output=output.stdout):
                    with patch("tools.atlas_json_benchmark.subprocess.run",
                               return_value=output) as process:
                        report = compare_json_processes(
                            source, candidates=("stdlib",), repeats=1)
                    self.assertEqual(report["status"], "REVIEW")
                    self.assertIn(report["results"][0]["status"],
                                  ("ERROR", "PARITY_FAIL"))
                    self.assertNotIn("GITHUB_TOKEN", process.call_args.kwargs["env"])
                    self.assertNotIn("HTTP_PROXY", process.call_args.kwargs["env"])
                    self.assertEqual(process.call_args.args[0][1:4],
                                     ["-P", "-m", "tools.atlas_json_benchmark"])
                    self.assertIn("--worker-parser", process.call_args.args[0])
                    self.assertEqual(process.call_args.kwargs["check"], False)

    def test_process_comparison_timeout_or_modified_input_never_succeeds(self) -> None:
        from tools.atlas_json_benchmark import compare_json_processes
        from subprocess import TimeoutExpired
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "source.json"
            source.write_text('{"id":1}', encoding="utf-8")
            with patch("tools.atlas_json_benchmark.subprocess.run",
                       side_effect=TimeoutExpired("python", 5)):
                report = compare_json_processes(
                    source, candidates=("stdlib",), repeats=1,
                    timeout_seconds=5)
            self.assertEqual(report["status"], "REVIEW")
            self.assertEqual(report["results"][0]["status"], "TIMEOUT")
            def mutation(*_args, **_kwargs):
                source.write_text('{"id":2}', encoding="utf-8")
                return SimpleNamespace(returncode=1, stdout=json.dumps({
                    "status": "NOT_AVAILABLE", "candidate": "stdlib"
                }), stderr="")
            with patch("tools.atlas_json_benchmark.subprocess.run",
                       side_effect=mutation):
                with self.assertRaisesRegex(ValueError, "Source changed"):
                    compare_json_processes(source, candidates=("stdlib",),
                                           repeats=1)

    def test_process_trial_has_strict_budgets_and_safe_inputs(self) -> None:
        from tools.atlas_json_benchmark import compare_json_processes
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "source.json"
            source.write_text('{"id":1}', encoding="utf-8")
            for options in ({"repeats": 0}, {"repeats": 8},
                            {"timeout_seconds": 4}, {"timeout_seconds": 121},
                            {"max_bytes": 0}, {"max_bytes": 1},
                            {"candidates": ("stdlib", "stdlib")},
                            {"candidates": ("unknown",)}, {"candidates": ()}):
                with self.subTest(options=options):
                    with self.assertRaises(ValueError):
                        compare_json_processes(source, **options)
            alias = Path(tmp) / "alias.json"
            try:
                alias.symlink_to(source)
            except (OSError, NotImplementedError):
                pass
            else:
                with self.assertRaisesRegex(ValueError, "symlink"):
                    compare_json_processes(alias)

    def test_process_worker_reports_missing_optional_decoder_explicitly(self) -> None:
        from tools.atlas_json_benchmark import _parser_process_worker
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "sample.json"
            source.write_text('{"id":1}', encoding="utf-8")
            with patch("tools.atlas_json_benchmark.importlib.import_module",
                       side_effect=ImportError("msgspec not installed")):
                report = _parser_process_worker(source, "msgspec", 2)
            self.assertEqual(report["status"], "NOT_AVAILABLE")
            self.assertFalse(report["executed"])
            self.assertEqual(report["candidate"], "msgspec")
            self.assertEqual(report["source_sha256"],
                             hashlib.sha256(source.read_bytes()).hexdigest())

    def test_process_comparison_rejects_invalid_or_oversized_worker_output(self) -> None:
        from tools.atlas_json_benchmark import compare_json_processes
        from subprocess import CompletedProcess
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "sample.json"
            source.write_text('{"id":1}', encoding="utf-8")
            for value in ("not JSON", "a" * 16_385, "[]",
                          '{"status":"PARITY_CANDIDATE","candidate":"wrong"}'):
                with self.subTest(output=value[:25]):
                    fake = CompletedProcess([], 0, stdout=value, stderr="")
                    with patch("tools.atlas_json_benchmark.subprocess.run",
                               return_value=fake):
                        report = compare_json_processes(
                            source, candidates=("stdlib",), repeats=1)
                    self.assertEqual(report["status"], "REVIEW")
                    self.assertEqual(report["results"][0]["status"], "ERROR")

    def test_process_cli_preserves_report_and_failure_exit_codes(self) -> None:
        from tools.atlas_json_benchmark import main
        for status, expected_exit in (("COMPARE_COMPLETE", 0), ("REVIEW", 1)):
            with self.subTest(status=status):
                report = {"status": status, "results": [
                    {"status": "PARITY_PASS" if status == "COMPARE_COMPLETE"
                     else "NOT_AVAILABLE"}]}
                stream = io.StringIO()
                with (patch("sys.argv", [
                        "atlas_json_benchmark", "--compare-process"]),
                      patch("tools.atlas_json_benchmark.compare_json_processes",
                            return_value=report) as trial,
                      contextlib.redirect_stdout(stream)):
                    self.assertEqual(main(), expected_exit)
                self.assertEqual(json.loads(stream.getvalue()), report)
                trial.assert_called_once()

    def test_invalid_sample_sizes_fail_closed(self) -> None:
        with self.assertRaises(ValueError):
            benchmark(Path("unused"), Path("unused"), sample_count=0)
        with self.assertRaises(ValueError):
            benchmark(Path("unused"), Path("unused"), sample_count=1001)


if __name__ == "__main__":
    unittest.main()
