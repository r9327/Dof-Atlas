"""Cold quest->Guide relation should read only an already validated compact cache."""
from __future__ import annotations

import json
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
            {"kind": "meta", "schema_version": 2,
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


if __name__ == "__main__":
    unittest.main()
