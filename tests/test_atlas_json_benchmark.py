from __future__ import annotations

import json
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
                       return_value=SimpleNamespace(loads=json.loads)):
                result = compare_json_parsers(source, repeats=2)
            self.assertEqual(result["status"], "COMPARE_COMPLETE")
            self.assertEqual([x["name"] for x in result["results"]],
                             ["stdlib", "orjson", "msgspec"])
            self.assertTrue(all(x["status"] == "PARITY_PASS" for x in result["results"]))
            self.assertTrue(all(len(x["measurements_ms"]) == 2 for x in result["results"]))
            self.assertFalse(result["runtime_consumer_changed"])
            self.assertEqual(source.read_text(encoding="utf-8"), original)

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
                       return_value=SimpleNamespace(loads=lambda _: {"id": 8})):
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
                               return_value=SimpleNamespace(loads=lambda _: replacement)):
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

    def test_invalid_sample_sizes_fail_closed(self) -> None:
        with self.assertRaises(ValueError):
            benchmark(Path("unused"), Path("unused"), sample_count=0)
        with self.assertRaises(ValueError):
            benchmark(Path("unused"), Path("unused"), sample_count=1001)


if __name__ == "__main__":
    unittest.main()
