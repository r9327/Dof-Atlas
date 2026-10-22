"""Safe batch ingest for source hints, with strict link identity and rollback."""
from __future__ import annotations
import json
import tempfile
import unittest
from pathlib import Path
from tools.build_ganymede_action_hints import (
    DIRECTORY, build_review_hints, write_gated_preview,
)

class BatchActionHintTests(unittest.TestCase):
    def setUp(self):
        t=tempfile.TemporaryDirectory()
        self.addCleanup(t.cleanup)
        self.root=Path(t.name)
        (self.root/DIRECTORY/"replacement_drafts").mkdir(parents=True)
        self.snapshot={"source":{"guide_id":9001,"source_url":"https://example.org/guides/9001"},
                       "steps":[{"source_step_number":1,"source_page":1,
                                 "coordinate_mentions":[[1,2],[3,4]],
                                 "external_dofusdb_ids":{"quest":[42],"object":[9],
                                                        "monster":[100],"dungeon":[8]},
                                 "linked_guide_ids":[11]},
                                {"source_step_number":2,"source_page":1,
                                 "coordinate_mentions":[],
                                 "external_dofusdb_ids":{"quest":[],"object":[],
                                                        "monster":[],"dungeon":[]},
                                 "linked_guide_ids":[]}]}
        self.proposals={"steps":[{"number":1,"actions":[
            {"kind":"quest_start","label":"Démarrer la quête","quest_id":42},
            {"kind":"prepare_object","label":"Prévoir un objet","object_id":9,"quantity":2}]},
            {"number":2,"actions":[{"kind":"talk","label":"Parler au gardien"}]}]}
        self.evidence=build_review_hints(self.snapshot,"dofus_test",self.proposals)
        (self.root/DIRECTORY/"ganymede_9001_observed_links.json").write_text(
            json.dumps(self.snapshot),encoding="utf-8")
        (self.root/DIRECTORY/"replacement_drafts"/"dofus_test.json").write_text(
            "{\"replacement_active\":false}\n",encoding="utf-8")

    def test_step_continuity_and_review_gate(self):
        e=self.evidence
        self.assertEqual(e["source_step_count"],2)
        self.assertEqual(e["steps"][0]["stable_step_id"],"ganymede_9001_step_0001")
        self.assertEqual(e["steps"][0]["at"],[1,2])
        self.assertEqual(e["steps"][0]["next"],[3,4])
        self.assertIsNone(e["steps"][1]["at"])
        self.assertTrue(all(s["review_status"]=="AUTO_EXTRACTED_NEEDS_REVIEW" for s in e["steps"]))
        self.assertEqual(e["certified_actions"],0)
        self.assertFalse(e["ready_to_replace"])

    def test_reject_unknown_ids_duplicates_and_unsupported_steps(self):
        for malformed in [
            {"steps":[{"number":1,"actions":[{"kind":"quest_start","label":"x","quest_id":404}]}]},
            {"steps":[{"number":1,"actions":[{"kind":"talk","label":"x","guide_id":12}]}]},
            {"steps":[{"number":1,"actions":[{"kind":"talk","label":"x"}]},
                      {"number":1,"actions":[{"kind":"talk","label":"y"}]}]},
            {"steps":[{"number":3,"actions":[{"kind":"talk","label":"x"}]}]},
            {"steps":[{"number":1,"actions":[{"kind":"invalid","label":"x"}]}]},
            {"steps":[{"number":1,"actions":[{"kind":"talk","label":"x","quantity":0}]}]},
        ]:
            with self.subTest(malformed=malformed):
                with self.assertRaises(ValueError):
                    build_review_hints(self.snapshot,"dofus_test",malformed)

    def test_preview_only_does_not_mutate_files(self):
        result=write_gated_preview(self.root,self.evidence,write=False)
        self.assertEqual(result["status"],"PREVIEW_ONLY")
        self.assertFalse((self.root/DIRECTORY/"ganymede_9001_action_candidates.json").exists())

    def test_never_overwrites_manually_reviewed_evidence(self):
        path=self.root/DIRECTORY/"ganymede_9001_action_candidates.json"
        path.write_text(json.dumps({"evidence_level":"FACTUAL_ACTION_CANDIDATES_NEED_CANONICAL_OBJECTIVE_VERIFICATION"}),
                        encoding="utf-8")
        with self.assertRaisesRegex(ValueError,"human-reviewed"):
            write_gated_preview(self.root,self.evidence,write=True)

    def test_bad_source_rolls_back_both_files(self):
        bad=json.loads(json.dumps(self.evidence))
        bad["steps"][0]["actions"][0]["quest_id"]=404
        draft=self.root/DIRECTORY/"replacement_drafts"/"dofus_test.json"
        previous=draft.read_bytes()
        with self.assertRaises(ValueError):
            write_gated_preview(self.root,bad,write=True)
        self.assertEqual(draft.read_bytes(),previous)
        self.assertFalse((self.root/DIRECTORY/"ganymede_9001_action_candidates.json").exists())
if __name__=="__main__":
    unittest.main()
