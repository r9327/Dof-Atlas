from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.modules.encyclopedia.providers.dofus_item_provider import (
    _read_guide_items_index,
)
from app.modules.encyclopedia.providers.memory_bound_guide_provider import (
    _guide_compact_cache_valid,
)
from app.modules.encyclopedia.providers.memory_bound_achievement_provider import (
    _achievement_compact_cache_valid,
)
from app.modules.encyclopedia.services.guide_ultime_manual_runtime_core import (
    restore_manual_runtime_compact_cache,
)
from app import startup_cache_warmup


class RebuildableCacheSchemaRecoveryTests(unittest.TestCase):
    def test_cache_readers_reject_bad_schema_without_throwing(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            target = root / "cache.json"
            for schema in ("broken", {}, [], None, True, 1.5):
                with self.subTest(schema=schema):
                    target.write_text(json.dumps({
                        "kind": "meta", "schema_version": schema,
                        "items": {}, "domains": {},
                    }) + "\n", encoding="utf-8")
                    self.assertIsNone(_read_guide_items_index(path=target, data_dir=root))
                    self.assertFalse(_guide_compact_cache_valid(target, guides_dir=root))
                    self.assertFalse(_achievement_compact_cache_valid(target, data_dir=root))
                    self.assertFalse(restore_manual_runtime_compact_cache(object(), target))
                    with patch.object(startup_cache_warmup, "STARTUP_CACHE_MANIFEST", target):
                        self.assertEqual(startup_cache_warmup._load_manifest()["domains"], {})

    def test_invalid_manual_quest_signature_is_cache_miss(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            target = Path(temp) / "manual.json"
            # The version matches, but quest_signature is malformed.
            from app.modules.encyclopedia.services import guide_ultime_manual_runtime_core as runtime
            target.write_text(json.dumps({
                "schema_version": runtime._MANUAL_RUNTIME_COMPACT_SCHEMA,
                "source_signature": [],
                "quest_signature": "broken",
            }), encoding="utf-8")
            class Fake:
                manual_dir = Path(temp)
            self.assertFalse(restore_manual_runtime_compact_cache(Fake(), target))

    def test_valid_shape_contract_can_still_miss_on_source_change(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            target = Path(temp) / "warmup.json"
            target.write_text(json.dumps({
                "schema_version": startup_cache_warmup._MANIFEST_SCHEMA_VERSION,
                "domains": {"guide": {"artifact": "cached"}},
            }), encoding="utf-8")
            with patch.object(startup_cache_warmup, "STARTUP_CACHE_MANIFEST", target):
                self.assertIn("guide", startup_cache_warmup._load_manifest()["domains"])


if __name__ == "__main__":
    unittest.main()
