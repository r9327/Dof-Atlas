from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from app.modules.encyclopedia.services import related_data_service


class RelatedDataServiceContractTests(unittest.TestCase):
    def test_same_catalog_reuses_one_canonical_related_data_bundle(self) -> None:
        catalog = object()
        quest_provider = MagicMock(name="quest_provider")
        achievement_provider = MagicMock(name="achievement_provider")
        guide_provider = MagicMock(name="guide_provider")
        quest_graph = MagicMock(name="quest_graph")

        with (
            patch.object(related_data_service, "_CACHED_CATALOG", None),
            patch.object(related_data_service, "_CACHED_DATA", None),
            patch.object(related_data_service, "_BUILD_COUNT", 0),
            patch.object(
                related_data_service,
                "QuestProvider",
                return_value=quest_provider,
            ) as quest_provider_cls,
            patch.object(
                related_data_service,
                "AchievementProvider",
                return_value=achievement_provider,
            ) as achievement_provider_cls,
            patch.object(
                related_data_service,
                "GuideProvider",
                return_value=guide_provider,
            ) as guide_provider_cls,
            patch.object(
                related_data_service,
                "QuestGraphService",
                return_value=quest_graph,
            ) as quest_graph_cls,
        ):
            first = related_data_service.build_related_encyclopedia_data(catalog)
            second = related_data_service.build_related_encyclopedia_data(catalog)

            self.assertIs(first, second)
            self.assertIs(first.achievement_provider, achievement_provider)
            self.assertIs(first.guide_provider, guide_provider)
            self.assertIs(first.quest_graph, quest_graph)
            self.assertEqual(related_data_service.related_data_build_count(), 1)

            quest_provider_cls.assert_called_once_with(catalog=catalog)
            achievement_provider_cls.assert_called_once_with(
                quest_provider=quest_provider
            )
            guide_provider_cls.assert_called_once_with(
                quest_provider=quest_provider,
                achievement_provider=achievement_provider,
            )
            achievement_provider.load_all.assert_called_once_with()
            guide_provider.load_all.assert_called_once_with()
            quest_graph_cls.assert_called_once_with(
                quest_provider,
                guide_provider,
                achievement_provider,
            )

    def test_new_catalog_replaces_the_active_canonical_bundle(self) -> None:
        first_catalog = object()
        second_catalog = object()

        with (
            patch.object(related_data_service, "_CACHED_CATALOG", None),
            patch.object(related_data_service, "_CACHED_DATA", None),
            patch.object(related_data_service, "_BUILD_COUNT", 0),
            patch.object(related_data_service, "QuestProvider") as quest_provider_cls,
            patch.object(related_data_service, "AchievementProvider") as achievement_provider_cls,
            patch.object(related_data_service, "GuideProvider") as guide_provider_cls,
            patch.object(related_data_service, "QuestGraphService") as quest_graph_cls,
        ):
            first = related_data_service.build_related_encyclopedia_data(first_catalog)
            second = related_data_service.build_related_encyclopedia_data(second_catalog)

            self.assertIsNot(first, second)
            self.assertEqual(related_data_service.related_data_build_count(), 2)
            self.assertEqual(quest_provider_cls.call_count, 2)
            self.assertEqual(achievement_provider_cls.call_count, 2)
            self.assertEqual(guide_provider_cls.call_count, 2)
            self.assertEqual(quest_graph_cls.call_count, 2)


if __name__ == "__main__":
    unittest.main()
