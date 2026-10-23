import ast
from hashlib import sha256
import json
import os
from pathlib import Path
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from app.constants import RAW_QUEST_DATA_DIR
from app.distribution.data_pack_plan import DataPack, InvalidDataPack
from app.distribution.data_pack_store import (
    accepted_pack, acknowledge_pack, install_pack,
)
from app.distribution.quest_evidence_pack import load_accepted_quest_guide_evidence
from app.modules.encyclopedia.providers.quest_provider import QuestProvider


def content(quest_id="42"):
    return json.dumps({
        "schema": "atlas-quest-guide-evidence/v1",
        "quests": {quest_id: {
            "items": [{"item_id": 771, "name": "Pierre ancienne", "quantity": 4}],
            "combats": [{"objective_id": 901, "monster": "Gobelin", "quantity": 2}],
        }},
    }, ensure_ascii=False, sort_keys=True).encode("utf-8")


class RuntimeQuestPackTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.root = self.base / "installed"
        self.stage = self.base / "staged"
        self.baseline = {"items": [{"item_id": 11, "name": "Ancien", "quantity": 1}], "combats": []}
        self.catalog = SimpleNamespace(
            by_id={42: object()},
            guide_evidence=lambda identifier: dict(self.baseline) if identifier == 42 else {},
        )

    def pack(self, data=None, revision=1):
        data = content() if data is None else data
        digest = sha256(data).hexdigest()
        path = self.stage / "data" / "quests" / f"v{revision}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return DataPack("quests", revision, 1, digest, f"data/quests/v{revision}.json")

    def provider(self):
        return QuestProvider(catalog=self.catalog, data_dir=RAW_QUEST_DATA_DIR)

    def test_no_install_keeps_canonical_evidence_without_creating_store(self):
        with patch.dict(os.environ, {"DOFUS_ATLAS_PACK_ROOT": str(self.root)}):
            self.assertEqual(self.provider().guide_evidence(42), self.baseline)
        self.assertFalse((self.root / "data-pack-store").exists())

    def test_pending_pack_not_visible_to_runtime(self):
        install_pack(self.root, self.stage, self.pack())
        self.assertIsNone(accepted_pack(self.root, "quests"))
        with patch.dict(os.environ, {"DOFUS_ATLAS_PACK_ROOT": str(self.root)}):
            self.assertEqual(self.provider().guide_evidence(42), self.baseline)

    def test_acknowledged_pack_is_visible_to_real_quest_provider(self):
        install_pack(self.root, self.stage, self.pack())
        acknowledge_pack(self.root, "quests")
        with patch.dict(os.environ, {"DOFUS_ATLAS_PACK_ROOT": str(self.root)}):
            provider = self.provider()
            result = provider.guide_evidence(42)
            self.assertEqual(result["items"][0]["item_id"], 771)
            self.assertEqual(result["combats"][0]["monster"], "Gobelin")
            result["items"].clear()
            self.assertEqual(provider.guide_evidence(42)["items"][0]["item_id"], 771)
            self.assertEqual(provider.guide_evidence(99), {})

    def test_generic_unrecognized_documentalist_batch_cannot_replace_runtime(self):
        packet = json.dumps({"schema": "documentalist-batch/v1", "records": []}).encode()
        install_pack(self.root, self.stage, self.pack(packet))
        acknowledge_pack(self.root, "quests")
        with patch.dict(os.environ, {"DOFUS_ATLAS_PACK_ROOT": str(self.root)}):
            with self.assertLogs(level="WARNING"):
                self.assertEqual(self.provider().guide_evidence(42), self.baseline)

    def test_corrupted_pack_is_refused_and_existing_facts_retained(self):
        pack = self.pack()
        install_pack(self.root, self.stage, pack)
        acknowledge_pack(self.root, "quests")
        blob = accepted_pack(self.root, "quests")
        blob.write_bytes(b"altered")
        with self.assertRaises(InvalidDataPack):
            load_accepted_quest_guide_evidence(self.root)
        with patch.dict(os.environ, {"DOFUS_ATLAS_PACK_ROOT": str(self.root)}):
            with self.assertLogs(level="WARNING"):
                self.assertEqual(self.provider().guide_evidence(42), self.baseline)

    def test_wrong_record_types_rejected(self):
        cases = [
            {"items": [{"item_id": True, "name": "Wrong", "quantity": 1}], "combats": []},
            {"items": [], "combats": [{"objective_id": 1, "monster": "Wrong", "quantity": 0}]},
            {"items": [], "combats": [] , "unknown": True},
            {"items": [{"item_id": 1, "name": "X", "quantity": 1}] * 49, "combats": []},
        ]
        for row in cases:
            with self.subTest(row=str(row)[:60]):
                raw = json.dumps({"schema": "atlas-quest-guide-evidence/v1",
                                  "quests": {"42": row}}).encode()
                # One isolated version for each invalid fixture.
                with tempfile.TemporaryDirectory() as folder:
                    previous = self.root
                    self.root = Path(folder)
                    pack = self.pack(raw)
                    install_pack(self.root, self.stage, pack)
                    acknowledge_pack(self.root, "quests")
                    with self.assertRaises(InvalidDataPack):
                        load_accepted_quest_guide_evidence(self.root)
                    self.root = previous

    def test_launcher_provides_pack_root_without_eager_json_read(self):
        launcher = (Path(__file__).resolve().parents[1]
                    / "app" / "distribution" / "launcher.py")
        tree = ast.parse(launcher.read_text(encoding="utf-8"))
        launch = next(node for node in tree.body
                      if isinstance(node, ast.FunctionDef) and node.name == "_launch_with_health")
        names = {x.value for x in ast.walk(launch)
                 if isinstance(x, ast.Constant) and isinstance(x.value, str)}
        self.assertIn("DOFUS_ATLAS_PACK_ROOT", names)


if __name__ == "__main__":
    unittest.main()
