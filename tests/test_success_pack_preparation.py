from hashlib import sha256
import json
import os
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch

from app.constants import RAW_QUEST_DATA_DIR
from app.distribution.data_pack_plan import DataPack
from app.distribution.data_pack_store import acknowledge_pack, install_pack
from app.modules.encyclopedia.models.entity_ref import EntityRef
from app.modules.encyclopedia.providers.achievement_provider import AchievementProvider
from app.modules.encyclopedia.providers.quest_provider import QuestProvider


def packet():
    return json.dumps({
        "schema": "atlas-quest-guide-evidence/v1",
        "quests": {
            "42": {
                "items": [{"item_id": 771, "name": "Pierre ancienne", "quantity": 3}],
                "combats": [{"objective_id": 901, "monster": "Gobelin", "quantity": 2}],
            },
            "43": {
                "items": [{"item_id": 771, "name": "Pierre ancienne", "quantity": 1}],
                "combats": [],
            },
        },
    }, ensure_ascii=False, sort_keys=True).encode("utf-8")


class SuccessPackPreparationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.root = self.base / "runtime"
        self.stage = self.base / "stage"
        self.baseline = {"items": [{"item_id": 5, "name": "Ancien", "quantity": 1}],
                         "combats": []}
        catalogue = SimpleNamespace(
            by_id={42: object(), 43: object()},
            guide_evidence=lambda id_: dict(self.baseline) if id_ == 42 else {},
        )
        quest_provider = QuestProvider(catalog=catalogue, data_dir=RAW_QUEST_DATA_DIR)
        self.provider = AchievementProvider(data_dir=RAW_QUEST_DATA_DIR,
                                            quest_provider=quest_provider)
        self.provider._loaded = True
        links = (
            EntityRef("quest", 42, "Quête A"),
            EntityRef("quest", 43, "Quête B"),
            EntityRef("quest", 42, "Quête A en double"),
        )
        self.provider._by_id = {
            9: SimpleNamespace(resolved_linked_quests=links, linked_quests=())
        }

    def install(self):
        blob = packet()
        path = self.stage / "data" / "quests" / "v1.json"
        path.parent.mkdir(parents=True)
        path.write_bytes(blob)
        pack = DataPack("quests", 1, 1, sha256(blob).hexdigest(), "data/quests/v1.json")
        install_pack(self.root, self.stage, pack)

    def test_pending_pack_stays_invisible_to_successes(self):
        self.install()
        with patch.dict(os.environ, {"DOFUS_ATLAS_PACK_ROOT": str(self.root)}):
            data = self.provider.get_quest_preparation(9)
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]["items"][0]["item_id"], 5)

    def test_acknowledged_pack_in_success_provider_is_lazy_and_stable(self):
        self.install()
        acknowledge_pack(self.root, "quests")
        with patch.dict(os.environ, {"DOFUS_ATLAS_PACK_ROOT": str(self.root)}):
            data = self.provider.get_quest_preparation(9)
            self.assertEqual([row["quest_id"] for row in data], [42, 43])
            self.assertEqual([row["items"][0]["quantity"] for row in data], [3, 1])
            self.assertEqual(data[0]["combats"][0]["monster"], "Gobelin")
            data[0]["items"][0]["quantity"] = 999
            refreshed = self.provider.get_quest_preparation(9)
            self.assertEqual(refreshed[0]["items"][0]["quantity"], 3)
        self.assertEqual(self.provider.get_quest_preparation(404), ())

    def test_no_pack_preserves_source_data_and_does_not_create_store(self):
        with patch.dict(os.environ, {"DOFUS_ATLAS_PACK_ROOT": str(self.root)}):
            self.assertEqual(
                self.provider.get_quest_preparation(9)[0]["items"][0]["item_id"], 5)
        self.assertFalse((self.root / "data-pack-store").exists())

    def test_missing_links_and_invalid_ids_do_not_create_fake_quests(self):
        self.provider._by_id[10] = SimpleNamespace(
            resolved_linked_quests=(
                EntityRef("monster", 42, "Not a quest"),
                EntityRef("quest", "not-an-integer", "Wrong"),
                EntityRef("quest", -3, "Invalid"),
                EntityRef("quest", 404, "Missing"),
            ),
            linked_quests=(),
        )
        with patch.dict(os.environ, {"DOFUS_ATLAS_PACK_ROOT": str(self.root)}):
            self.assertEqual(self.provider.get_quest_preparation(10), ())


if __name__ == "__main__":
    unittest.main()
