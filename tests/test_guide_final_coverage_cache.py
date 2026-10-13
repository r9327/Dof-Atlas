from __future__ import annotations

"""Regression checks for per-invocation Guide success coverage memoization."""

from functools import lru_cache
from types import SimpleNamespace
import unittest

from tools.audit_guide_ultime_manual_final_coverage import (
    classify, label_is_explicit, norm,
)


def _achievement():
    ref = lambda entity_id, label: SimpleNamespace(entity_id=entity_id, label=label)
    return SimpleNamespace(
        id=700, name="Example achievement", category_id=1,
        category_name="Adventure", subcategory_name="Example",
        level=100, points=10,
        resolved_linked_quests=[ref(101, "quest alpha")],
        resolved_linked_monsters=[ref(201, "dragon")],
        resolved_linked_dungeons=[ref(301, "unknown dungeon")],
    )


def _evidence():
    return {
        "quest_names": {"quest alpha"},
        "success_names": set(),
        "text_tokens": {"find a dragon in the forest"},
    }


class GuideFinalCoverageCacheTests(unittest.TestCase):
    def test_cached_and_uncached_full_classification_are_identical(self):
        evidence = _evidence()
        achievement = _achievement()
        calls = []

        @lru_cache(maxsize=32768)
        def cached(label):
            calls.append(label)
            return label_is_explicit(label, evidence)

        original = classify(achievement, evidence)
        self.assertEqual(original["state"], "partial")
        for _ in range(4):
            self.assertEqual(
                classify(achievement, evidence, explicit_check=cached),
                original,
            )
        self.assertEqual(set(calls), {"quest alpha", "dragon", "unknown dungeon"})
        self.assertEqual(len(calls), 3)
        self.assertGreaterEqual(cached.cache_info().hits, 9)

    def test_distinct_catalog_evidence_gets_an_independent_cache(self):
        achievement = _achievement()
        before = _evidence()
        after = _evidence()
        after["text_tokens"].add(norm("visit the unknown dungeon"))

        @lru_cache(maxsize=32768)
        def check_before(label):
            return label_is_explicit(label, before)

        @lru_cache(maxsize=32768)
        def check_after(label):
            return label_is_explicit(label, after)

        first = classify(achievement, before, explicit_check=check_before)
        second = classify(achievement, after, explicit_check=check_after)
        self.assertEqual(first["state"], "partial")
        self.assertEqual(second["state"], "covered_all_linked_entities")
        self.assertNotEqual(first["missing"], second["missing"])
        self.assertEqual(second, classify(achievement, after))


if __name__ == "__main__":
    unittest.main()
