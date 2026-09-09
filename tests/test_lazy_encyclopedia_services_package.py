from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

import app.modules.encyclopedia.services as services
import app.modules.encyclopedia.services.related_data_service as related


class LazyEncyclopediaServicesPackageTests(unittest.TestCase):
    def test_public_package_import_defers_unneeded_service_modules(self) -> None:
        root = Path(__file__).resolve().parents[1]
        code = r'''
import json, sys
from app.modules.encyclopedia.services import (
    QuestGraphService,
    QuestProgressService,
    build_related_encyclopedia_data,
    related_data_build_count,
)
print(json.dumps({
    "related": "app.modules.encyclopedia.services.related_data_service" in sys.modules,
    "hierarchy": "app.modules.encyclopedia.services.quest_hierarchy_service" in sys.modules,
    "encyclopedia": "app.modules.encyclopedia.services.encyclopedia_service" in sys.modules,
    "link": "app.modules.encyclopedia.services.link_service" in sys.modules,
    "builder_callable": callable(build_related_encyclopedia_data),
    "count_callable": callable(related_data_build_count),
}))
'''
        result = subprocess.run(
            [sys.executable, "-c", code],
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
        )
        payload = json.loads(result.stdout.strip().splitlines()[-1])
        self.assertFalse(payload["related"])
        self.assertFalse(payload["hierarchy"])
        self.assertFalse(payload["encyclopedia"])
        self.assertFalse(payload["link"])
        self.assertTrue(payload["builder_callable"])
        self.assertTrue(payload["count_callable"])

    def test_lazy_class_export_resolves_on_first_access(self) -> None:
        services.__dict__.pop("QuestHierarchyService", None)
        value = services.QuestHierarchyService
        from app.modules.encyclopedia.services.quest_hierarchy_service import (
            QuestHierarchyService as RealQuestHierarchyService,
        )

        self.assertIs(value, RealQuestHierarchyService)
        self.assertIs(services.QuestHierarchyService, RealQuestHierarchyService)

    def test_related_builder_wrapper_forwards_without_parallel_logic(self) -> None:
        sentinel = object()
        catalog = object()
        with patch.object(related, "build_related_encyclopedia_data", return_value=sentinel) as build:
            self.assertIs(services.build_related_encyclopedia_data(catalog), sentinel)
        build.assert_called_once_with(catalog)

    def test_related_data_cache_is_in_memory_only_and_reuses_same_catalog(self) -> None:
        class FakeQuestProvider:
            def __init__(self, *, catalog) -> None:
                self.catalog = catalog

        class FakeAchievementProvider:
            def __init__(self, *, quest_provider) -> None:
                self.quest_provider = quest_provider
                self.load_calls = 0

            def load_all(self):
                self.load_calls += 1
                return []

        class FakeGuideProvider:
            def __init__(self, *, quest_provider, achievement_provider) -> None:
                self.quest_provider = quest_provider
                self.achievement_provider = achievement_provider
                self.load_calls = 0

            def load_all(self):
                self.load_calls += 1
                return []

        class FakeQuestGraphService:
            def __init__(self, quest_provider, guide_provider, achievement_provider) -> None:
                self.quest_provider = quest_provider
                self.guide_provider = guide_provider
                self.achievement_provider = achievement_provider

        previous_catalog = related._CACHED_CATALOG
        previous_data = related._CACHED_DATA
        previous_count = related._BUILD_COUNT
        related._CACHED_CATALOG = None
        related._CACHED_DATA = None
        related._BUILD_COUNT = 0
        catalog = object()
        try:
            with (
                patch.object(related, "QuestProvider", FakeQuestProvider),
                patch.object(related, "AchievementProvider", FakeAchievementProvider),
                patch.object(related, "GuideProvider", FakeGuideProvider),
                patch.object(related, "QuestGraphService", FakeQuestGraphService),
            ):
                first = related.build_related_encyclopedia_data(catalog)
                second = related.build_related_encyclopedia_data(catalog)

            self.assertIs(first, second)
            self.assertEqual(related.related_data_build_count(), 1)
            self.assertEqual(first.achievement_provider.load_calls, 1)
            self.assertEqual(first.guide_provider.load_calls, 1)
            self.assertFalse(hasattr(related, "_CACHE_PATH"))
        finally:
            related._CACHED_CATALOG = previous_catalog
            related._CACHED_DATA = previous_data
            related._BUILD_COUNT = previous_count


if __name__ == "__main__":
    unittest.main()
