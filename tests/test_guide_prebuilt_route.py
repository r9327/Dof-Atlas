"""Portable Guide bundle: exact content, corruption and fallback contracts."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from app.constants import RAW_QUEST_DATA_DIR
from app.modules.encyclopedia.providers.quest_provider import QuestProvider
from app.modules.encyclopedia.services.guide_catalog_prebuilt_route import (
    GUIDE_ID, MANIFEST_NAME, LEGACY_STORE_NAME, STORE_SIGNATURE,
    publish_prebuilt_route, restore_prebuilt_route,
)
from app.modules.encyclopedia.services.guide_catalog_route_store import (
    indexed_path, load_detail,
)


class PrebuiltGuideRouteTests(unittest.TestCase):
    def _source(self):
        guide = SimpleNamespace(required_steps=[
            SimpleNamespace(id="quest-1", step_type="quest", entity_id=42, order=1),
        ])
        cards = []
        for idx in range(1001):
            line = {"text": f"Action {idx}", "kind": "action", "position": "[1,2]"}
            cards.append({
                "index": idx + 1,
                "manual_stage_id": f"sylvestre:{idx + 1}",
                "manual_lines": [line],
                "manual_sections": {"now": [line]},
                "manual_quest_ids": [42],
                "manual_quest_names": ["Quête de test"],
            })
        return SimpleNamespace(
            guide_id=GUIDE_ID,
            guide_title="Sylvestre",
            catalog_guide=guide,
            quest_provider=QuestProvider(data_dir=RAW_QUEST_DATA_DIR),
            cards=cards,
            route={"id": f"catalog_manual_{GUIDE_ID}", "steps": cards},
            manual_audit_data={"card_count": len(cards), "quest_count": 1},
            _common_quest_ids=(42,),
        )

    def test_portable_index_roundtrip_and_character_free(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = self._source()
            manifest = publish_prebuilt_route(source, Path(tmp), source_sha="a" * 40)
            self.assertEqual(manifest["card_count"], len(source.cards))
            self.assertEqual(manifest["store_signature"], STORE_SIGNATURE)
            manifest_text = (Path(tmp) / MANIFEST_NAME).read_text(encoding="utf-8")
            self.assertNotIn("character:", manifest_text)
            self.assertNotIn("quest_progress", manifest_text)

            restored = SimpleNamespace(
                guide_id=GUIDE_ID,
                catalog_guide=source.catalog_guide,
                quest_provider=source.quest_provider,
            )
            self.assertTrue(restore_prebuilt_route(restored, directory=Path(tmp)))
            self.assertEqual(len(restored.cards), len(source.cards))
            self.assertEqual(restored._common_quest_ids, (42,))
            self.assertNotIn("manual_lines", restored.cards[0])
            self.assertEqual(restored.cards[-1]["manual_stage_id"], source.cards[-1]["manual_stage_id"])
            for idx in (0, 500, 1000):
                detail = load_detail(restored._catalog_detail_store_path, idx)
                self.assertEqual(detail["manual_lines"], source.cards[idx]["manual_lines"])
                self.assertEqual(detail["manual_sections"], source.cards[idx]["manual_sections"])

    def test_relative_output_matches_windows_portable_build_contract(self):
        # The Windows package writes to data/bootstrap/guide_routes, a relative
        # path. Path.as_uri() rejects it even when the SQLite file exists.
        with tempfile.TemporaryDirectory(dir=".") as temp:
            root = Path(temp)
            self.assertFalse(root.is_absolute())
            source = self._source()
            publish_prebuilt_route(source, root, source_sha="d" * 40)
            restored = SimpleNamespace(
                guide_id=GUIDE_ID,
                catalog_guide=source.catalog_guide,
                quest_provider=source.quest_provider,
            )
            self.assertTrue(restore_prebuilt_route(restored, directory=root))
            self.assertEqual(len(restored.cards), 1001)
            self.assertEqual(
                load_detail(restored._catalog_detail_store_path, 500)["manual_lines"],
                source.cards[500]["manual_lines"],
            )

    def test_tampered_route_and_source_manifest_fail_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = self._source()
            root = Path(tmp)
            publish_prebuilt_route(src, root, source_sha="b" * 40)
            file = indexed_path(root / LEGACY_STORE_NAME)
            payload = file.read_bytes()
            file.write_bytes(payload[:-1] + bytes([payload[-1] ^ 1]))
            dest = SimpleNamespace(
                guide_id=GUIDE_ID, catalog_guide=src.catalog_guide,
                quest_provider=src.quest_provider,
            )
            self.assertFalse(restore_prebuilt_route(dest, directory=root))
            self.assertFalse(hasattr(dest, "cards"))
            file.write_bytes(payload)

            manifest_path = root / MANIFEST_NAME
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["quest_source_sizes"]["quests.json"] = -12345
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            self.assertFalse(restore_prebuilt_route(dest, directory=root))
            self.assertFalse(hasattr(dest, "cards"))

    def test_provider_guide_identity_and_invalid_build_are_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = self._source()
            root = Path(tmp)
            with self.assertRaises(ValueError):
                publish_prebuilt_route(src, root, source_sha="short")
            self.assertFalse((root / MANIFEST_NAME).exists())
            publish_prebuilt_route(src, root, source_sha="c" * 40)
            foreign = SimpleNamespace(
                guide_id=GUIDE_ID,
                catalog_guide=SimpleNamespace(required_steps=[]),
                quest_provider=src.quest_provider,
            )
            self.assertFalse(restore_prebuilt_route(foreign, directory=root))
            foreign.catalog_guide = src.catalog_guide
            foreign.quest_provider = object()
            self.assertFalse(restore_prebuilt_route(foreign, directory=root))

    def test_prebuilt_short_circuit_precedes_expensive_cache_signature(self):
        from app.modules.encyclopedia.services import guide_catalog_manual_runtime_service as module
        obj = object.__new__(module.GuideCatalogManualRuntimeService)
        with (
            patch.object(module, "_catalog_route_cache_identity",
                         side_effect=AssertionError("cold source fallback was called")),
            patch("app.modules.encyclopedia.services.guide_catalog_prebuilt_route.restore_prebuilt_route",
                  return_value=True) as fast,
        ):
            obj._load_manual_preview()
            fast.assert_called_once_with(obj)


if __name__ == "__main__":
    unittest.main()
