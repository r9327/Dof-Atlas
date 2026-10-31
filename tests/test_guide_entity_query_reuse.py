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

    def test_only_a_bounded_set_of_explicit_queries_is_retained(self):
        provider = self.provider()
        with patch("app.modules.encyclopedia.providers.memory_bound_guide_provider._guide_compact_cache_valid",
                   return_value=False):
            for ident in range(80):
                provider.get_guides_for_entity("quest", ident)
        self.assertLessEqual(len(provider._by_entity), 64)
        self.assertNotIn(("quest", 0), provider._by_entity)
        self.assertIsNone(getattr(provider, "_detail_cache", None))
