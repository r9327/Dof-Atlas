"""Cold quest->Guide relation should read only an already validated compact cache."""
from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch, Mock

from app.modules.encyclopedia.providers import memory_bound_guide_provider as mod
from app.modules.encyclopedia.services.quest_graph_service import QuestGraphService


class CompactGuideRelationTests(unittest.TestCase):
    @staticmethod
    def _write_cache(path: Path, guides_dir: Path, *, corrupt: bool = False) -> None:
        rows = [
            {"kind": "meta", "schema_version": 2, "guide_count": 2,
             "entity_index_count": 2,
             "source_signature": mod._guide_compact_source_signature(guides_dir)},
            {"kind": "guide", "value": {"id": "guide-b"}},
            {"kind": "entity_index", "value": {
                "guide_id": "guide-b", "entity_keys": [["quest", 2464], ["quest", 42]]
            }},
            {"kind": "guide", "value": {"id": "guide-a"}},
            {"kind": "entity_index", "value": {
                "guide_id": "guide-a", "entity_keys": [["quest", 2464]]
            }},
        ]
        path.write_text(
            "\n".join(json.dumps(row, separators=(",", ":")) for row in rows)
            + ("\n{invalid json" if corrupt else "") + "\n",
            encoding="utf-8",
        )

    @staticmethod
    def _provider(guides_dir: Path):
        provider = mod.MemoryBoundGuideProvider.__new__(mod.MemoryBoundGuideProvider)
        provider.guides_dir = guides_dir
        provider.include_drafts = False
        provider._loaded = False
        provider._ensure_loaded = Mock(side_effect=AssertionError("Cold lookup loaded catalogue"))
        return provider

    def test_valid_cache_avoids_catalogue_loading_and_has_exact_ids(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            guides = root / "guides"
            guides.mkdir()
            (guides / "first.json").write_text("{}", encoding="utf-8")
            cache = root / "compact.jsonl"
            self._write_cache(cache, guides)
            provider = self._provider(guides)
            graph = QuestGraphService.__new__(QuestGraphService)
            graph._built = False
            graph.guide_provider = provider
            with patch.object(mod, "GUIDE_COMPACT_CACHE", cache):
                self.assertEqual(graph.guide_ids(2464), ["guide-a", "guide-b"])
                self.assertEqual(graph.guide_ids(42), ["guide-b"])
                self.assertEqual(graph.guide_ids(99999), [])
                provider._ensure_loaded.assert_not_called()

    def test_repeat_cold_lookup_skips_full_jsonl_decode_and_bounds_memory(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            guides = root / "guides"
            guides.mkdir()
            (guides / "first.json").write_text("{}", encoding="utf-8")
            cache = root / "compact.jsonl"
            self._write_cache(cache, guides)
            provider = self._provider(guides)
            real_loads = json.loads
            with patch.object(mod, "GUIDE_COMPACT_CACHE", cache), patch.object(
                mod.json, "loads", wraps=real_loads
            ) as decode:
                self.assertEqual(provider.guide_ids_for_quest_fast(2464), ("guide-a", "guide-b"))
                first_decode_count = decode.call_count
                self.assertGreater(first_decode_count, 1)
                self.assertEqual(provider.guide_ids_for_quest_fast(2464), ("guide-a", "guide-b"))
                # One metadata decode is still required for source freshness.
                self.assertEqual(decode.call_count, first_decode_count + 1)
                for quest_id in range(1000, 1100):
                    provider.guide_ids_for_quest_fast(quest_id)
                self.assertLessEqual(len(provider._fast_quest_relation_cache), 64)
                self.assertNotIn(2464, provider._fast_quest_relation_cache)
            provider._ensure_loaded.assert_not_called()

    def test_cold_relation_cache_invalidates_when_index_replaced(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            guides = root / "guides"
            guides.mkdir()
            cache = root / "compact.jsonl"
            self._write_cache(cache, guides)
            provider = self._provider(guides)
            with patch.object(mod, "GUIDE_COMPACT_CACHE", cache):
                self.assertEqual(provider.guide_ids_for_quest_fast(42), ("guide-b",))
                content = cache.read_text(encoding="utf-8")
                cache.write_text(content.replace("[\"quest\",42]", "[\"quest\",99]"),
                                 encoding="utf-8")
                stat = cache.stat()
                os.utime(cache, ns=(stat.st_atime_ns, stat.st_mtime_ns + 1_000_000_000))
                self.assertEqual(provider.guide_ids_for_quest_fast(42), ())
                self.assertEqual(provider.guide_ids_for_quest_fast(99), ("guide-b",))
            provider._ensure_loaded.assert_not_called()

    def test_replaced_jsonl_same_size_and_mtime_invalidates_recent_relation(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            guides = root / "guides"
            guides.mkdir()
            cache = root / "compact.jsonl"
            self._write_cache(cache, guides)
            provider = self._provider(guides)
            with patch.object(mod, "GUIDE_COMPACT_CACHE", cache):
                self.assertEqual(provider.guide_ids_for_quest_fast(42), ("guide-b",))
                before = cache.stat()
                # A cross-process atomic writer can restore timestamps for an
                # otherwise changed cache; its inode/creation time differs.
                replacement = root / "replacement.jsonl"
                content = cache.read_text(encoding="utf-8")
                self.assertIn("42", content)
                replacement.write_text(content.replace("42", "99"), encoding="utf-8")
                os.utime(replacement, ns=(before.st_atime_ns, before.st_mtime_ns))
                self.assertEqual(replacement.stat().st_size, before.st_size)
                replacement.replace(cache)
                after = cache.stat()
                self.assertEqual(after.st_size, before.st_size)
                self.assertEqual(after.st_mtime_ns, before.st_mtime_ns)
                self.assertEqual(provider.guide_ids_for_quest_fast(42), ())
                self.assertEqual(provider.guide_ids_for_quest_fast(99), ("guide-b",))
            provider._ensure_loaded.assert_not_called()

    def test_parseable_but_incomplete_guide_index_does_not_claim_no_relations(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            guides = root / "guides"
            guides.mkdir()
            cache = root / "compact.jsonl"
            self._write_cache(cache, guides)
            rows = [json.loads(line) for line in cache.read_text().splitlines()]
            # Keep valid JSON and a valid header but remove an entire Guide.
            cache.write_text(
                "\n".join(json.dumps(row) for row in rows if
                          row.get("kind") == "meta" or
                          row.get("value", {}).get("id") != "guide-a" and
                          row.get("value", {}).get("guide_id") != "guide-a") + "\n",
                encoding="utf-8",
            )
            provider = self._provider(guides)
            with patch.object(mod, "GUIDE_COMPACT_CACHE", cache):
                self.assertIsNone(provider.guide_ids_for_quest_fast(2464))
            provider._ensure_loaded.assert_not_called()

    def test_duplicate_or_late_meta_row_is_not_a_valid_relation(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            guides = root / "guides"
            guides.mkdir()
            cache = root / "compact.jsonl"
            self._write_cache(cache, guides)
            rows = [json.loads(line) for line in cache.read_text().splitlines()]
            meta = dict(rows[0])
            meta.update(guide_count=1, entity_index_count=1)
            rows = [row for row in rows if not (
                row.get("kind") == "guide"
                and row.get("value", {}).get("id") == "guide-a"
                or row.get("kind") == "entity_index"
                and row.get("value", {}).get("guide_id") == "guide-a"
            )]
            rows.append(meta)
            cache.write_text("\n".join(json.dumps(row) for row in rows) + "\n",
                             encoding="utf-8")
            provider = self._provider(guides)
            with patch.object(mod, "GUIDE_COMPACT_CACHE", cache):
                self.assertIsNone(provider.guide_ids_for_quest_fast(99999))
            provider._ensure_loaded.assert_not_called()

    def test_legacy_metadata_without_cardinality_must_fall_back(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            guides = root / "guides"
            guides.mkdir()
            cache = root / "compact.jsonl"
            provider = self._provider(guides)
            for missing in ("guide_count", "entity_index_count"):
                self._write_cache(cache, guides)
                rows = [json.loads(line) for line in cache.read_text().splitlines()]
                rows[0].pop(missing)
                cache.write_text(
                    "\n".join(json.dumps(row, separators=(",", ":")) for row in rows)
                    + "\n",
                    encoding="utf-8",
                )
                with self.subTest(missing=missing), patch.object(mod, "GUIDE_COMPACT_CACHE", cache):
                    self.assertIsNone(provider.guide_ids_for_quest_fast(2464))
                    self.assertIsNone(provider.guide_ids_for_quest_fast(99999))
            provider._ensure_loaded.assert_not_called()

    def test_missing_index_row_requires_relation_fallback(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            guides = root / "guides"
            guides.mkdir()
            cache = root / "compact.jsonl"
            self._write_cache(cache, guides)
            rows = [json.loads(line) for line in cache.read_text().splitlines()]
            rows = [row for row in rows if not (
                row.get("kind") == "entity_index"
                and row.get("value", {}).get("guide_id") == "guide-b"
            )]
            cache.write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")
            provider = self._provider(guides)
            with patch.object(mod, "GUIDE_COMPACT_CACHE", cache):
                self.assertIsNone(provider.guide_ids_for_quest_fast(42))
            provider._ensure_loaded.assert_not_called()

    def test_stale_or_malformed_cache_defers_to_existing_provider(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            guides = root / "guides"
            guides.mkdir()
            source = guides / "first.json"
            source.write_text("{}", encoding="utf-8")
            cache = root / "compact.jsonl"
            self._write_cache(cache, guides, corrupt=True)
            provider = self._provider(guides)
            with patch.object(mod, "GUIDE_COMPACT_CACHE", cache):
                self.assertIsNone(provider.guide_ids_for_quest_fast(2464))
                self._write_cache(cache, guides)
                source.write_text('{"changed": true}', encoding="utf-8")
                self.assertIsNone(provider.guide_ids_for_quest_fast(2464))
                provider.include_drafts = True
                self.assertIsNone(provider.guide_ids_for_quest_fast(2464))

    def test_partial_compact_catalogue_falls_back_to_source_process(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            guides = root / "guides"
            guides.mkdir()
            source = guides / "first.json"
            source.write_text("{}", encoding="utf-8")
            cache = root / "compact.jsonl"
            cache.write_text(
                json.dumps({"kind": "meta", "guide_count": 2}) + "\n"
                + json.dumps({"kind": "guide", "value": {
                    "id": "guide-one", "source_file": "first.json",
                }}) + "\n",
                encoding="utf-8",
            )
            provider = self._provider(guides)
            with (
                patch.object(mod, "GUIDE_COMPACT_CACHE", cache),
                patch.object(provider, "_guide_entries", return_value=[(source, {})]),
                patch.object(provider, "_summary_from_compact_row",
                             return_value=SimpleNamespace(id="guide-one")),
            ):
                with self.assertRaisesRegex(RuntimeError, "tronqué"):
                    provider._load_from_compact_cache()
            with (
                patch.object(mod, "GUIDES_DIR", guides),
                patch.object(mod, "_guide_compact_cache_valid", return_value=True),
                patch.object(provider, "_load_from_compact_cache",
                             side_effect=RuntimeError("corrupt cache")),
                patch.object(provider, "_load_from_compact_subprocess") as fallback,
            ):
                provider._load()
                fallback.assert_called_once_with()

    def test_ensure_compact_cache_never_reuses_incomplete_guide_rows(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            guides = root / "guides"
            guides.mkdir()
            (guides / "sample.json").write_text("{}", encoding="utf-8")
            cache = root / "compact.jsonl"
            meta = json.dumps({
                "kind": "meta", "schema_version": 2,
                "source_signature": mod._guide_compact_source_signature(guides),
                "guide_count": 2, "entity_index_count": 1,
            }) + "\n"
            guide_one = json.dumps({"kind": "guide", "value": {"id": "a"}}) + "\n"
            guide_two = json.dumps({"kind": "guide", "value": {"id": "b"}}) + "\n"
            index = json.dumps({
                "kind": "entity_index",
                "value": {"guide_id": "a", "entity_keys": [["quest", 42]]},
            }) + "\n"
            with patch.object(mod.subprocess, "run",
                              return_value=SimpleNamespace(stdout='{"guide_count":2}\n')) as build:
                for payload in (
                    meta,
                    meta + guide_one,
                    meta + guide_one + guide_two,
                    meta + guide_one + guide_one + index,
                    meta + guide_one + guide_two + '{bad-json',
                    meta + guide_one + guide_two
                        + '{"kind":"entity_index","value":{"guide_id":"a","entity_keys":[["quest",true]]}}\n',
                    json.dumps({
                        "kind": "meta", "schema_version": 2,
                        "source_signature": mod._guide_compact_source_signature(guides),
                    }) + "\n" + guide_one,
                ):
                    with self.subTest(payload=payload[-70:]):
                        cache.write_text(payload, encoding="utf-8")
                        self.assertEqual(
                            mod.ensure_guide_compact_cache(guides_dir=guides, path=cache), 2,
                        )
                self.assertEqual(build.call_count, 7)
                cache.write_text(meta + guide_one + guide_two + index, encoding="utf-8")
                self.assertEqual(
                    mod.ensure_guide_compact_cache(guides_dir=guides, path=cache), 2,
                )
                self.assertEqual(build.call_count, 7)

    def test_ensure_cli_uses_verified_compact_cache_result(self):
        with (
            patch.object(mod, "ensure_guide_compact_cache", return_value=2) as ensure,
            patch.object(mod, "_build_manual_runtime_compact_cache_in_worker",
                         return_value=7),
            patch("builtins.print") as output,
        ):
            self.assertEqual(mod._ensure_compact_guide_cache_cli(), 0)
            ensure.assert_called_once_with()
            status = json.loads(output.call_args.args[0])
            self.assertEqual(status["guide_count"], 2)
            self.assertEqual(status["manual_card_count"], 7)
        with (
            patch.object(mod, "ensure_guide_compact_cache", return_value=0),
            patch.object(mod, "_build_manual_runtime_compact_cache_in_worker") as manual,
        ):
            with self.assertRaisesRegex(RuntimeError, "unavailable"):
                mod._ensure_compact_guide_cache_cli()
            manual.assert_not_called()

    def test_frozen_ensure_cli_keeps_in_process_repair(self):
        with (
            patch.object(mod.sys, "frozen", True, create=True),
            patch.object(mod, "ensure_guide_compact_cache", side_effect=[0, 2]) as ensure,
            patch.object(mod, "_build_compact_guide_cache", return_value=0) as rebuild,
            patch.object(mod, "_build_manual_runtime_compact_cache_in_worker",
                         return_value=7),
            patch("builtins.print"),
        ):
            self.assertEqual(mod._ensure_compact_guide_cache_cli(), 0)
            rebuild.assert_called_once_with(mod.GUIDE_COMPACT_CACHE)
            self.assertEqual(ensure.call_count, 2)

    def test_missing_cache_preserves_graph_fallback(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            guides = root / "guides"
            guides.mkdir()
            provider = self._provider(guides)
            provider.get_guides_for_entity = Mock(
                return_value=[SimpleNamespace(id="legacy-guide")]
            )
            graph = QuestGraphService.__new__(QuestGraphService)
            graph._built = False
            graph.guide_provider = provider
            with patch.object(mod, "GUIDE_COMPACT_CACHE", root / "missing.jsonl"):
                self.assertEqual(graph.guide_ids(2464), ["legacy-guide"])
                provider.get_guides_for_entity.assert_called_once_with("quest", 2464)

    def test_malformed_index_never_becomes_an_empty_valid_relation(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            guides = root / "guides"
            guides.mkdir()
            cache = root / "compact.jsonl"
            provider = self._provider(guides)
            variants = (
                {"guide_id": "guide-b", "entity_keys": [["quest"]]},
                {"guide_id": "guide-b", "entity_keys": [["quest", "2464"]]},
                {"guide_id": "guide-b", "entity_keys": [["quest", True]]},
                {"guide_id": "guide-b", "entity_keys": [["quest", 0]]},
                {"guide_id": "guide-b", "entity_keys": [[{}, 2464]]},
                {"guide_id": "foreign-guide", "entity_keys": [["quest", 42]]},
                {"guide_id": 123, "entity_keys": [["quest", 42]]},
            )
            for value in variants:
                self._write_cache(cache, guides)
                rows = [json.loads(line) for line in cache.read_text().splitlines()]
                rows[2]["value"] = value
                cache.write_text("\n".join(map(json.dumps, rows)) + "\n", encoding="utf-8")
                with self.subTest(value=value), patch.object(mod, "GUIDE_COMPACT_CACHE", cache):
                    self.assertIsNone(provider.guide_ids_for_quest_fast(2464))
                    self.assertIsNone(provider.guide_ids_for_quest_fast(99999))
            provider._ensure_loaded.assert_not_called()

    def test_duplicate_entity_index_requires_fallback(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            guides = root / "guides"
            guides.mkdir()
            cache = root / "compact.jsonl"
            self._write_cache(cache, guides)
            lines = cache.read_text().splitlines()
            cache.write_text("\n".join([*lines, lines[2]]) + "\n", encoding="utf-8")
            provider = self._provider(guides)
            with patch.object(mod, "GUIDE_COMPACT_CACHE", cache):
                self.assertIsNone(provider.guide_ids_for_quest_fast(2464))
            provider._ensure_loaded.assert_not_called()


    def test_compact_guide_writer_keeps_previous_generation_after_disk_failure(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            cache = root / "compact.jsonl"
            fake_provider = SimpleNamespace(
                _guides=[SimpleNamespace(id="synthetic-guide")],
                _by_entity={},
                _load_in_process=Mock(),
            )
            with (
                patch.object(mod, "MemoryBoundGuideProvider", return_value=fake_provider),
                patch.object(mod, "_CompactGuideNoopItemProvider", return_value=object()),
                patch.object(mod, "_guide_compact_source_signature", return_value=[]),
                patch.object(mod, "_summary_payload", return_value={"id": "synthetic-guide"}),
                patch("builtins.print"),
            ):
                self.assertEqual(mod._build_compact_guide_cache(cache), 0)
                old_bytes = cache.read_bytes()
                self.assertIn(b"synthetic-guide", old_bytes)
                for failing_method in ("open", "replace"):
                    with self.subTest(failing_method=failing_method):
                        with patch.object(Path, failing_method, side_effect=OSError("locked cache")):
                            with self.assertRaisesRegex(OSError, "locked cache"):
                                mod._build_compact_guide_cache(cache)
                        self.assertEqual(cache.read_bytes(), old_bytes)
                        self.assertEqual(list(root.glob(".compact.jsonl.*.tmp")), [])


if __name__ == "__main__":
    unittest.main()
