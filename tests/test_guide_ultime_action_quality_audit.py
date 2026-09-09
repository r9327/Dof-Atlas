from __future__ import annotations

import unittest

from tools.audit_guide_ultime_action_quality import _line_issues, audit


class GuideUltimeActionQualityAuditTests(unittest.TestCase):
    def test_repository_inventory_covers_locked_route(self) -> None:
        report = audit()
        self.assertEqual(report["chapter_count"], 13)
        self.assertEqual(report["stage_count"], 267)
        self.assertEqual(sum(int(row["stage_count"]) for row in report["chapters"].values()), 267)
        self.assertGreater(report["instruction_line_count"], 0)
        self.assertGreater(report["action_line_count"], 0)
        self.assertGreaterEqual(report["positioned_action_line_count"], 0)
        self.assertIn(report["status"], {"BLOCKED", "REVIEW_REQUIRED", "HEURISTICALLY_CLEAN"})

    def test_placeholder_is_hard_issue(self) -> None:
        issues = _line_issues(
            chapter_id="chapter",
            stage_id="stage",
            line_index=0,
            line={"kind": "action", "position": "[1,2]", "text": "TODO à confirmer"},
        )
        self.assertIn("placeholder_or_unverified_instruction", {row["code"] for row in issues})
        self.assertIn("hard", {row["severity"] for row in issues})

    def test_punctuation_placeholder_does_not_match_normal_text(self) -> None:
        normal = _line_issues(
            chapter_id="chapter",
            stage_id="stage",
            line_index=0,
            line={"kind": "action", "position": "[1,2]", "text": "Parle au PNJ."},
        )
        self.assertNotIn("placeholder_or_unverified_instruction", {row["code"] for row in normal})

        placeholder = _line_issues(
            chapter_id="chapter",
            stage_id="stage",
            line_index=0,
            line={"kind": "action", "position": "[1,2]", "text": "???"},
        )
        self.assertIn("placeholder_or_unverified_instruction", {row["code"] for row in placeholder})

    def test_authoring_language_is_review_issue(self) -> None:
        for text in (
            "Ne déclarer obtenu que si le runtime confirme.",
            "Faire un rerun causal seulement après le blocker.",
            "Lancer le cleanup après le startCriterion.",
            "Suivre temporal_registry_v13 si pending.",
        ):
            with self.subTest(text=text):
                issues = _line_issues(
                    chapter_id="chapter",
                    stage_id="stage",
                    line_index=0,
                    line={"kind": "warning", "position": "", "text": text},
                )
                self.assertIn("authoring_language_visible_to_player", {row["code"] for row in issues})
                self.assertIn("review", {row["severity"] for row in issues})

    def test_internal_file_and_stage_references_are_review_issues(self) -> None:
        for line in (
            {"kind": "action", "position": "quête de classe", "text": "Suivre astrub_class_branches_v1.json."},
            {"kind": "action", "position": "transversal BNT-06", "text": "Continuer le rang 16."},
            {"kind": "warning", "position": "", "text": "Reprendre après AMK-03."},
        ):
            with self.subTest(line=line):
                issues = _line_issues(
                    chapter_id="chapter",
                    stage_id="stage",
                    line_index=0,
                    line=line,
                )
                self.assertIn("authoring_language_visible_to_player", {row["code"] for row in issues})

    def test_normal_coordinate_is_not_internal_stage_reference(self) -> None:
        issues = _line_issues(
            chapter_id="chapter",
            stage_id="stage",
            line_index=0,
            line={"kind": "action", "position": "[-59,15] Grotte Hesque", "text": "Entrer dans la Grotte Hesque."},
        )
        self.assertNotIn("authoring_language_visible_to_player", {row["code"] for row in issues})

    def test_travel_action_without_position_is_review_issue(self) -> None:
        issues = _line_issues(
            chapter_id="chapter",
            stage_id="stage",
            line_index=0,
            line={"kind": "action", "position": "", "text": "Parle au PNJ pour lancer la quête."},
        )
        self.assertIn("travel_action_without_position", {row["code"] for row in issues})

    def test_coordinate_in_action_text_satisfies_unpositioned_travel(self) -> None:
        issues = _line_issues(
            chapter_id="chapter",
            stage_id="stage",
            line_index=0,
            line={"kind": "action", "position": "", "text": "Rends-toi en [3,-5] puis parle au PNJ."},
        )
        self.assertNotIn("travel_action_without_position", {row["code"] for row in issues})

    def test_vague_action_condition_is_review_issue(self) -> None:
        issues = _line_issues(
            chapter_id="chapter",
            stage_id="stage",
            line_index=0,
            line={"kind": "action", "position": "zone", "text": "Achète la ressource si besoin."},
        )
        self.assertIn("vague_action_condition", {row["code"] for row in issues})

    def test_issue_rows_are_traceable_to_stage_and_line(self) -> None:
        report = audit()
        for row in report["issues"]:
            self.assertTrue(str(row.get("chapter") or ""))
            self.assertTrue(str(row.get("stage") or ""))
            self.assertGreaterEqual(int(row.get("line_index") or 0), 0)
            self.assertIn(row.get("severity"), {"hard", "review"})
            self.assertTrue(str(row.get("code") or ""))
            self.assertTrue(str(row.get("text") or "") or str(row.get("position") or ""))


if __name__ == "__main__":
    unittest.main()
