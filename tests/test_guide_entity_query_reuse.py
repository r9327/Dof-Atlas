from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from app.modules.encyclopedia.models.entity_ref import EntityRef
from app.modules.encyclopedia.providers.memory_bound_guide_provider import MemoryBoundGuideProvider


class GuideEntityQueryReuseTests(unittest.TestCase):
    def provider(self):
        provider = object.__new__(MemoryBoundGuideProvider)
        provider._loaded = True
        provider.guides_dir = Path(".")
        provider._by_entity = defaultdict(list)
        provider._by_id = {"one": SimpleNamespace(id="one", title="Guide", order=1)}
        provider.get_by_id = Mock(return_value=SimpleNamespace(
            linked_entities=[EntityRef("quest", 42, "Quête")]))
        return provider

    def test_repeated_positive_and_negative_queries_do_not_reload_guide_details(self):
        provider = self.provider()
        with patch("app.modules.encyclopedia.providers.memory_bound_guide_provider._guide_compact_cache_valid",
                   return_value=False):
            first = provider.get_guides_for_entity("quest", 42)
            first.clear()
            self.assertEqual([guide.id for guide in provider.get_guides_for_entity("quest", 42)], ["one"])
            self.assertEqual(provider.get_by_id.call_count, 1)
            self.assertEqual(provider.get_guides_for_entity("quest", 99), [])
            self.assertEqual(provider.get_guides_for_entity("quest", 99), [])
            self.assertEqual(provider.get_by_id.call_count, 2)

    def test_disappearing_compact_index_falls_back_to_source_lookup(self):
        provider = self.provider()
        with (
            patch("app.modules.encyclopedia.providers.memory_bound_guide_provider._guide_compact_cache_valid",
                  return_value=True),
            patch("app.modules.encyclopedia.providers.memory_bound_guide_provider.GUIDE_COMPACT_CACHE",
                  Path("nonexistent_guide_cache_repair_test.jsonl")),
        ):
            self.assertEqual(
                [guide.id for guide in provider.get_guides_for_entity("quest", 42)],
                ["one"],
            )
            self.assertEqual(
                [guide.id for guide in provider.get_guides_for_entity("quest", 42)],
                ["one"],
            )
            provider.get_by_id.assert_called_once()

    def test_truncated_entity_index_uses_canonical_detail_fallback(self):
        from app.modules.encyclopedia.providers import memory_bound_guide_provider as mod
        import json
        import tempfile

        with tempfile.TemporaryDirectory() as directory:
            cache = Path(directory) / "compact.jsonl"
            cache.write_text(
                "\n".join(json.dumps(row, separators=(",", ":")) for row in (
                    {"kind": "meta", "entity_index_count": 2},
                    {"kind": "guide", "value": {"id": "one"}},
                    {"kind": "entity_index", "value": {
                        "guide_id": "one", "entity_keys": [["quest", 42]],
                    }},
                )) + "\n", encoding="utf-8",
            )
            provider = self.provider()
            with (
                patch.object(mod, "GUIDE_COMPACT_CACHE", cache),
                patch.object(mod, "_guide_compact_cache_valid", return_value=True),
            ):
                self.assertEqual(
                    [g.id for g in provider.get_guides_for_entity("quest", 99)], [],
                )
                self.assertEqual(provider.get_by_id.call_count, 1)
                # A complete index is allowed to resolve a positive relation
                # without reconstructing a heavyweight Guide detail.
                provider = self.provider()
                cache.write_text(cache.read_text().replace(
                    '"entity_index_count":2', '"entity_index_count":1'
                ), encoding="utf-8")
                self.assertEqual(
                    [g.id for g in provider.get_guides_for_entity("quest", 42)], ["one"],
                )
                provider.get_by_id.assert_not_called()

    def test_entity_lookup_rechecks_generation_before_caching(self):
        from app.modules.encyclopedia.providers import memory_bound_guide_provider as mod
        import json
        import tempfile

        with tempfile.TemporaryDirectory() as directory:
            cache = Path(directory) / "guide.jsonl"
            cache.write_text(
                "\n".join(json.dumps(row, separators=(",", ":")) for row in (
                    {"kind": "meta", "entity_index_count": 1},
                    {"kind": "entity_index", "value": {
                        "guide_id": "one", "entity_keys": [["quest", 999]],
                    }},
                )) + "\n",
                encoding="utf-8",
            )
            provider = self.provider()
            original_stat = Path.stat
            checks = []

            def changed_stat(path, *args, **kwargs):
                stat = original_stat(path, *args, **kwargs)
                if path == cache:
                    checks.append(True)
                    if len(checks) == 2:
                        return SimpleNamespace(
                            st_size=stat.st_size,
                            st_mtime_ns=stat.st_mtime_ns,
                            st_ctime_ns=stat.st_ctime_ns + 1,
                            st_ino=stat.st_ino,
                        )
                return stat

            with (
                patch.object(mod, "GUIDE_COMPACT_CACHE", cache),
                patch.object(mod, "_guide_compact_cache_valid", return_value=True),
                patch.object(Path, "stat", changed_stat),
            ):
                found = provider.get_guides_for_entity("quest", 42)
            # Source details must win over any partial/stale compact lookup.
            self.assertEqual([g.id for g in found], ["one"])
            self.assertEqual(provider.get_by_id.call_count, 1)
            self.assertGreaterEqual(len(checks), 2)

    def test_draft_catalogue_entity_lookup_never_uses_published_only_index(self):
        provider = self.provider()
        provider.include_drafts = True
        with (
            patch(
                "app.modules.encyclopedia.providers.memory_bound_guide_provider._guide_compact_cache_valid",
                side_effect=AssertionError("draft relations cannot use compact index"),
            ),
            patch.object(provider, "get_by_id", return_value=SimpleNamespace(
                linked_entities=[EntityRef("quest", 42, "Quête")]
            )) as source,
        ):
            self.assertEqual(
                [guide.id for guide in provider.get_guides_for_entity("quest", 42)],
                ["one"],
            )
            self.assertEqual(
                [guide.id for guide in provider.get_guides_for_entity("quest", 42)],
                ["one"],
            )
            source.assert_called_once_with("one")

    def test_cached_entity_relation_is_invalidated_on_same_mtime_atomic_replace(self):
        from app.modules.encyclopedia.providers import memory_bound_guide_provider as mod
        import json
        import os
        import tempfile

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            cache = root / "compact.jsonl"

            def write_cache(path, wanted):
                rows = [
                    {"kind": "meta", "entity_index_count": 1},
                    {"kind": "entity_index", "value": {
                        "guide_id": "one", "entity_keys": [["quest", wanted]],
                    }},
                ]
                path.write_text(
                    "\n".join(json.dumps(row, separators=(",", ":"))
                              for row in rows) + "\n", encoding="utf-8",
                )

            write_cache(cache, 42)
            provider = self.provider()
            with (
                patch.object(mod, "GUIDE_COMPACT_CACHE", cache),
                patch.object(mod, "_guide_compact_cache_valid", return_value=True),
            ):
                self.assertEqual(
                    [guide.id for guide in provider.get_guides_for_entity("quest", 42)],
                    ["one"],
                )
                # Cached result can be returned without rescanning the JSONL.
                self.assertEqual(provider.get_guides_for_entity("quest", 42)[0].id, "one")
                initial = cache.stat()
                candidate = root / "replacement.jsonl"
                write_cache(candidate, 99)
                os.utime(candidate, ns=(initial.st_atime_ns, initial.st_mtime_ns))
                self.assertEqual(candidate.stat().st_size, initial.st_size)
                candidate.replace(cache)
                self.assertEqual(cache.stat().st_mtime_ns, initial.st_mtime_ns)
                self.assertEqual(provider.get_guides_for_entity("quest", 42), [])
                self.assertEqual(
                    [guide.id for guide in provider.get_guides_for_entity("quest", 99)],
                    ["one"],
                )

    def test_catalogue_release_invalidates_the_same_existing_relation_owner(self):
        provider = self.provider()
        with patch("app.modules.encyclopedia.providers.memory_bound_guide_provider._guide_compact_cache_valid",
                   return_value=False):
            self.assertEqual(provider.get_guides_for_entity("quest", 42)[0].id, "one")
            provider.release_catalogue()
            self.assertFalse(provider._by_entity)
            provider._loaded = True
            provider._by_id = {"two": SimpleNamespace(id="two", title="New Guide", order=1)}
            self.assertEqual(provider.get_guides_for_entity("quest", 42)[0].id, "two")
            self.assertEqual(provider.get_by_id.call_count, 2)

    def test_recent_entity_cache_is_lru_including_negative_results(self):
        provider = self.provider()
        with patch(
            "app.modules.encyclopedia.providers.memory_bound_guide_provider._guide_compact_cache_valid",
            return_value=False,
        ):
            for ident in range(64):
                provider.get_guides_for_entity("quest", ident)
            self.assertIn(("quest", 0), provider._by_entity)
            provider.get_guides_for_entity("quest", 0)
            provider.get_guides_for_entity("quest", 64)
            self.assertEqual(len(provider._by_entity), 64)
            self.assertIn(("quest", 0), provider._by_entity)
            self.assertNotIn(("quest", 1), provider._by_entity)

    def test_only_a_bounded_set_of_explicit_queries_is_retained(self):
        provider = self.provider()
        with patch("app.modules.encyclopedia.providers.memory_bound_guide_provider._guide_compact_cache_valid",
                   return_value=False):
            for ident in range(80):
                provider.get_guides_for_entity("quest", ident)
        self.assertLessEqual(len(provider._by_entity), 64)
        self.assertNotIn(("quest", 0), provider._by_entity)
        self.assertIsNone(getattr(provider, "_detail_cache", None))
