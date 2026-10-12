from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from app.modules.encyclopedia.services import guide_ultime_manual_runtime_core as manual_runtime
from app.modules.encyclopedia.services.guide_ultime_manual_runtime_service import (
    GuideUltimeManualRuntimeService,
)


class _Service(GuideUltimeManualRuntimeService):
    def _load_manual_preview_uncached(self) -> None:
        self.compose(self)


def _service(compose) -> _Service:
    service = object.__new__(_Service)
    service.compose = compose
    service.route = {}
    service.cards = []
    service.manual_audit_data = {}
    service.manual_preview_active = False
    service.manual_preview_error = ""
    service.manual_preview_chapters = ()
    service.manual_manifest_active = False
    service.manual_chapters = ()
    service._common_quest_ids = ()
    service._full_success_ids = ()
    return service


class GuideManualBundleCacheTests(unittest.TestCase):
    def setUp(self) -> None:
        manual_runtime.clear_manual_bundle_cache()

    def test_second_service_reuses_composed_bundle_with_isolated_cards(self) -> None:
        calls = 0

        def compose(service) -> None:
            nonlocal calls
            calls += 1
            card = {"manual_source": True, "manual_stage_id": "stage", "rows": [calls]}
            service.route = {"steps": [card], "manual_manifest": True}
            service.cards = service.route["steps"]
            service.manual_audit_data = {"card_count": 1}
            service.manual_preview_active = True
            service.manual_preview_chapters = ("chapter",)
            service.manual_manifest_active = True
            service.manual_chapters = ("chapter",)
            service._common_quest_ids = (101,)
            service._full_success_ids = ()

        first = _service(compose)
        second = _service(compose)
        with patch.object(manual_runtime, "_manual_bundle_cache_key", return_value=("bundle", 1)):
            first._load_manual_preview()
            second._load_manual_preview()

        self.assertEqual(calls, 1)
        self.assertEqual(second.cards[0]["rows"], [1])
        self.assertIs(second.cards, second.route["steps"])
        self.assertIsNot(first.route, second.route)
        self.assertIsNot(first.cards[0], second.cards[0])

        first.cards[0]["rows"].append(999)
        self.assertEqual(second.cards[0]["rows"], [1])

    def test_compact_route_writer_keeps_exact_bytes_and_nested_payloads(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manual_dir = root / "manual"
            manual_dir.mkdir()
            (manual_dir / "manifest_v1.json").write_text("{}", encoding="utf-8")
            sidecar = root / "compact.json"
            encoded_sheet = bytes.fromhex("0001f09f9089") * 4096
            card = {
                "manual_stage_id": "test",
                "_manual_stage_payload": encoded_sheet,
                "_manual_chapter_preparation_payload": bytearray(bytes.fromhex("0203")),
                "nested": [{"id": 18, "quests": (18, 19)}],
            }
            service = SimpleNamespace(
                manual_dir=manual_dir,
                route={"steps": [card], "chapter": {"id": "test"}},
                cards=[card],
                manual_audit_data={"source": {"ok": True}},
                manual_preview_active=True,
                manual_preview_chapters=("test",),
                manual_manifest_active=True,
                manual_chapters=("test",),
                _quest_name_to_id={"Test": 18},
                _common_quest_ids=(18,),
                _full_success_ids=(),
            )
            self.assertEqual(
                manual_runtime.write_manual_runtime_compact_cache(service, sidecar),
                1,
            )
            stored = json.loads(sidecar.read_text(encoding="utf-8"))
            self.assertEqual(
                stored["cards"],
                manual_runtime._manual_runtime_json_encode(service.cards),
            )
            self.assertEqual(
                manual_runtime._manual_runtime_json_decode(stored["cards"])[0][
                    "_manual_stage_payload"
                ],
                encoded_sheet,
            )
            self.assertEqual(stored["route"], {"chapter": {"id": "test"}})
            self.assertEqual(stored["manual_audit_data"], service.manual_audit_data)

    def test_route_or_catalog_revision_change_recomposes_bundle(self) -> None:
        calls = 0

        def compose(service) -> None:
            nonlocal calls
            calls += 1
            service.route = {"steps": [{"manual_source": True, "call": calls}]}
            service.cards = service.route["steps"]
            service.manual_audit_data = {}
            service.manual_preview_active = True
            service.manual_preview_chapters = ("chapter",)
            service.manual_manifest_active = True
            service.manual_chapters = ("chapter",)
            service._common_quest_ids = ()
            service._full_success_ids = ()

        first = _service(compose)
        second = _service(compose)
        with patch.object(
            manual_runtime,
            "_manual_bundle_cache_key",
            side_effect=[("bundle", 1), ("bundle", 2)],
        ):
            first._load_manual_preview()
            second._load_manual_preview()

        self.assertEqual(calls, 2)
        self.assertEqual(first.cards[0]["call"], 1)
        self.assertEqual(second.cards[0]["call"], 2)


if __name__ == "__main__":
    unittest.main()
