from __future__ import annotations

import unittest
from unittest.mock import patch

from app.modules.encyclopedia.services import related_data_service


class RelatedDataServiceContractTests(unittest.TestCase):
    def _warm_patches(self):
        return (
            patch.object(
                related_data_service,
                "_warm_achievement_source_indexes",
                return_value=7,
            ),
            patch.object(
                related_data_service,
                "_warm_achievement_catalogue",
                return_value=1418,
            ),
            patch.object(
                related_data_service,
                "_warm_guide_files",
                return_value=3,
            ),
            patch.object(
                related_data_service,
                "_warm_guide_catalogue",
                return_value=20,
            ),
            patch.object(
                related_data_service,
                "_warm_guide_items_index",
                return_value=6,
            ),
        )

    def test_same_catalog_reuses_only_tiny_preload_metadata(self) -> None:
        catalog = object()
        warm_source, warm_success, warm_files, warm_guides, warm_items = self._warm_patches()

        with (
            patch.object(related_data_service, "_CACHED_CATALOG", None),
            patch.object(related_data_service, "_CACHED_DATA", None),
            patch.object(related_data_service, "_BUILD_COUNT", 0),
            warm_source,
            warm_success,
            warm_files,
            warm_guides,
            warm_items,
        ):
            first = related_data_service.build_related_encyclopedia_data(catalog)
            second = related_data_service.build_related_encyclopedia_data(catalog)

            self.assertIs(first, second)
            self.assertIsNone(first.achievement_provider)
            self.assertIs(first.guide_provider, related_data_service._EMPTY_GUIDE_PROVIDER)
            self.assertIsNone(first.quest_graph)
            self.assertEqual(first.warmed_source_count, 7)
            self.assertEqual(first.warmed_achievement_count, 1418)
            self.assertEqual(first.warmed_guide_file_count, 3)
            self.assertEqual(first.warmed_guide_count, 20)
            self.assertEqual(first.warmed_guide_item_count, 6)
            self.assertEqual(related_data_service.related_data_build_count(), 1)
            self.assertEqual(related_data_service._CACHED_CATALOG, id(catalog))

            warm_source.assert_called_once_with()
            warm_success.assert_called_once_with()
            warm_files.assert_called_once_with()
            warm_guides.assert_called_once_with()
            warm_items.assert_called_once_with()

    def test_new_catalog_rebuilds_tiny_metadata_without_retaining_graph(self) -> None:
        first_catalog = object()
        second_catalog = object()
        warm_source, warm_success, warm_files, warm_guides, warm_items = self._warm_patches()

        with (
            patch.object(related_data_service, "_CACHED_CATALOG", None),
            patch.object(related_data_service, "_CACHED_DATA", None),
            patch.object(related_data_service, "_BUILD_COUNT", 0),
            warm_source,
            warm_success,
            warm_files,
            warm_guides,
            warm_items,
        ):
            first = related_data_service.build_related_encyclopedia_data(first_catalog)
            second = related_data_service.build_related_encyclopedia_data(second_catalog)

            self.assertIsNot(first, second)
            self.assertIsNone(first.quest_graph)
            self.assertIsNone(second.quest_graph)
            self.assertEqual(related_data_service.related_data_build_count(), 2)
            self.assertEqual(warm_source.call_count, 2)
            self.assertEqual(warm_success.call_count, 2)
            self.assertEqual(warm_files.call_count, 2)
            self.assertEqual(warm_guides.call_count, 2)
            self.assertEqual(warm_items.call_count, 2)


if __name__ == "__main__":
    unittest.main()
