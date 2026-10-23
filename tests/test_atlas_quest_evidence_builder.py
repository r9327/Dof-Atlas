from hashlib import sha256
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from tools.atlas_quest_evidence_builder import (
    InvalidQuestEvidence, build_quest_evidence_packet,
)


def bundle(*rows):
    records = []
    for payload in rows:
        canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True,
                               separators=(",", ":")).encode("utf-8")
        records.append({
            "id": str(payload["id"]),
            "sha256": sha256(canonical).hexdigest(),
            "payload": payload,
        })
    obj = {"schema": "documentalist-batch/v1", "source": "local:fixture",
           "collected_at": "2026-10-22T15:00:00Z",
           "source_sha256": "a" * 64, "records": records}
    return json.dumps(obj, ensure_ascii=False).encode("utf-8")


def prep():
    return {"items": [{"item_id": 51, "name": "Pierre", "quantity": 3}],
            "combats": [{"objective_id": 81, "monster": "Gobelin", "quantity": 2}]}


class QuestEvidenceBuilderTests(unittest.TestCase):
    def test_mixed_batch_keeps_only_explicit_quest_preparation(self):
        raw = bundle(
            {"id": 13, "kind": "quest", "label": "No facts"},
            {"id": 42, "kind": "quest", "preparation": prep()},
            {"id": 9, "kind": "success", "preparation": prep()},
            {"id": 3, "kind": "guide", "references": [{"kind": "quest", "id": 42}]},
        )
        data = json.loads(build_quest_evidence_packet(raw))
        self.assertEqual(data["schema"], "atlas-quest-guide-evidence/v1")
        self.assertEqual(list(data["quests"]), ["42"])
        self.assertEqual(data["quests"]["42"], prep())

    def test_determinism_across_input_order(self):
        a = {"id": 42, "kind": "quest", "preparation": prep()}
        b = {"id": 43, "kind": "quest", "preparation": {"items": [], "combats": []}}
        self.assertEqual(build_quest_evidence_packet(bundle(a, b)),
                         build_quest_evidence_packet(bundle(b, a)))

    def test_incomplete_facts_are_not_guessed(self):
        for bad in (
            {"items": []},
            {"items": [], "combats": [{"objective_id": True, "monster": "x", "quantity": 1}]},
            {"items": [{"item_id": 1, "name": "Object", "quantity": 0}], "combats": []},
            {"items": [], "combats": [], "unknown": "extra"},
        ):
            with self.subTest(case=str(bad)), self.assertRaises(InvalidQuestEvidence):
                build_quest_evidence_packet(bundle({"id": 42, "kind": "quest",
                                                    "preparation": bad}))

    def test_tampered_source_record_digest_refused(self):
        obj = json.loads(bundle({"id": 42, "kind": "quest", "preparation": prep()}))
        obj["records"][0]["payload"]["preparation"]["items"][0]["quantity"] = 999
        with self.assertRaises(ValueError):
            build_quest_evidence_packet(json.dumps(obj).encode("utf-8"))

    def test_no_approved_preparation_fails_closed(self):
        with self.assertRaisesRegex(InvalidQuestEvidence, "no explicit"):
            build_quest_evidence_packet(bundle({"id": 42, "kind": "quest"}))

    def test_build_cli_writes_once_and_never_installs(self):
        with tempfile.TemporaryDirectory() as root:
            folder = Path(root)
            before = folder / "from-documentalist.json"
            output = folder / "data" / "quests" / "v1.json"
            output.parent.mkdir(parents=True)
            before.write_bytes(bundle({"id": 42, "kind": "quest", "preparation": prep()}))
            argv = [sys.executable, "-m", "tools.atlas_quest_evidence_builder",
                    str(before), "--out", str(output)]
            run = subprocess.run(argv, capture_output=True, text=True, check=False)
            self.assertEqual(run.returncode, 0, run.stderr)
            status = json.loads(run.stdout)
            self.assertEqual(status["status"], "STAGED_ONLY")
            self.assertFalse(status["installation_performed"])
            self.assertEqual(status["sha256"], sha256(output.read_bytes()).hexdigest())
            repeated = subprocess.run(argv, capture_output=True, text=True, check=False)
            self.assertEqual(repeated.returncode, 2)
            self.assertEqual(output.read_bytes(), build_quest_evidence_packet(before.read_bytes()))


if __name__ == "__main__":
    unittest.main()
