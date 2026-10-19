"""Stage-action evidence is never mistaken for a verified Doduda objective."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from tools.audit_ganymede_action_to_doduda import (
    audit_action_to_doduda, DIRECTORY,
)

class StageActionCanonicalEvidenceTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root=Path(temp.name)
        self.guide_dir=self.root/DIRECTORY
        self.guide_dir.mkdir(parents=True)
        self.raw=self.root/"doduda"
        self.raw.mkdir()
        self.path=DIRECTORY/"ganymede_9001_action_candidates.json"
        self.source={
            "source":{"guide_id":9001,
                      "source_url":"https://ganymede-app.com/guides/9001"},
            "steps":[
                {"source_step_number":1,"source_page":1,
                 "linked_guide_ids":[],"coordinate_mentions":[[1,2]],
                 "external_dofusdb_ids":{
                     "quest":[101],"object":[],"monster":[],"dungeon":[]}},
                {"source_step_number":2,"source_page":1,
                 "linked_guide_ids":[],"coordinate_mentions":[[2,3]],
                 "external_dofusdb_ids":{
                     "quest":[101],"object":[],"monster":[],"dungeon":[]}},
            ],
        }
        (self.guide_dir/"ganymede_test_observed_links.json").write_text(
            json.dumps(self.source),encoding="utf-8")
        self.payload={
            "source_guide_id":9001,"atlas_guide_id":"dofus_test",
            "source_step_count":2,
            "evidence_level":"AUTOMATED_SOURCE_ACTION_HINTS_UNVERIFIED",
            "editorial_text_copied":False,"ready_to_replace":False,
            "certified_actions":0,"steps":[
                {"source_step_number":num,
                 "stable_step_id":f"ganymede_9001_step_{num:04d}",
                 "source_page":1,"review_status":"AUTO_EXTRACTED_NEEDS_REVIEW",
                 "quest_objectives_verified":False,
                 "at":coords,"next":coords,
                 "actions":[{"kind":kind,"label":label,"quest_id":101}]}
                for num,coords,kind,label in [
                    (1,[1,2],"quest_start","Démarrer quête 101"),
                    (2,[2,3],"quest_finish","Terminer quête 101"),
                ]
            ],
        }
        self.write_candidate()

    def write_candidate(self):
        (self.root/self.path).write_text(
            json.dumps(self.payload),encoding="utf-8")

    def write_raw(self,*,missing_second_objective=False):
        quests=[{"data":{"id":101,"stepIds":{"Array":[401,402]},
                         "startCriterion":"Qf=9&(Qa=7|PL>150)"}}]
        steps=[{"data":{"id":401}},{"data":{"id":402}}]
        objs=[{"data":{"id":501,"stepId":401,"typeId":6}}]
        if not missing_second_objective:
            objs.append({"data":{"id":502,"stepId":402,"typeId":7}})
        for name,items in [
            ("quests.json",quests),("quest_steps.json",steps),
            ("quest_objectives.json",objs),
        ]:
            (self.raw/name).write_text(
                json.dumps({"RefIds":items}),encoding="utf-8")

    def audit(self):
        return audit_action_to_doduda(
            self.root,raw_dir=self.raw,candidate_paths=[self.path]
        )

    def test_source_without_installed_doduda_remains_blocked(self):
        result=self.audit()
        self.assertEqual(result["status"],"BLOCKED_CANONICAL_SOURCE_UNAVAILABLE")
        self.assertEqual(result["source_quest_action_occurrences"],2)
        self.assertEqual(result["certified_quest_actions"],0)
        self.assertFalse(result["ready_to_replace"])

    def test_repeated_quest_and_or_criteria_are_not_collapsed(self):
        self.write_raw()
        result=self.audit()
        self.assertEqual(result["status"],"REVIEW_CANONICAL_STRUCTURE_ONLY",
                         result.get("issues"))
        self.assertEqual(result["distinct_quest_ids"],1)
        self.assertEqual(result["source_quest_action_occurrences"],2)
        occurrences=result["source_occurrences"]
        self.assertEqual([x["source_step_number"] for x in occurrences],[1,2])
        self.assertTrue(all(not x["action_verified"] for x in occurrences))
        self.assertTrue(all(not x["canonical_objective_match_verified"]
                            for x in occurrences))
        quest=result["quest_structure"]["101"]
        self.assertEqual(quest["canonical_step_ids"],[401,402])
        self.assertEqual([s["objective_ids"] for s in quest["raw_steps"]],
                         [[501],[502]])
        self.assertEqual(
            len(quest["criterion_branches"]["alternative_branches"]),2
        )
        self.assertTrue(quest["criterion_branches"]["has_or"])
        self.assertEqual(result["certified_prerequisites"],0)
        self.assertEqual(result["verified_character_progress"],0)

    def test_missing_canonical_objective_is_review_not_proof(self):
        self.write_raw(missing_second_objective=True)
        report=self.audit()
        self.assertEqual(report["status"],"REVIEW_RAW_STRUCTURE_GAPS")
        self.assertEqual(len(report["structure_gaps"]),1)
        self.assertFalse(report["quest_structure"]["101"]["raw_steps"][1][
            "objectives_verified_for_candidate_action"])

    def test_tampered_quest_reference_fails_before_raw_lookup(self):
        self.payload["steps"][0]["actions"][0]["quest_id"]=999
        self.write_candidate()
        report=self.audit()
        self.assertEqual(report["status"],"FAIL")
        self.assertEqual(report["issues"][0]["code"],
                         "invalid_source_action_candidate")

    def test_malformed_canonical_source_cannot_return_success(self):
        self.write_raw()
        (self.raw/"quests.json").write_text('{"RefIds":[',encoding="utf-8")
        report=self.audit()
        self.assertEqual(report["status"],"FAIL")
        self.assertEqual(report["issues"][0]["code"],"canonical_data_unreadable")

if __name__=="__main__":
    unittest.main()
