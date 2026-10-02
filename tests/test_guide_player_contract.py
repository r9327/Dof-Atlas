from __future__ import annotations

import unittest

from tools.guide_player_contract import (
    audit,
    line_contract_issues,
    stage_contract_issues,
)


class GuidePlayerContractTests(unittest.TestCase):
    def test_destination_suivante_is_a_hard_issue(self) -> None:
        issues = line_contract_issues(
            chapter_id="chapter",
            stage_id="stage",
            line_index=0,
            line={"kind": "warning", "position": "", "text": "Destination suivante : Astrub."},
        )
        self.assertIn("destination_suivante_visible", {row["code"] for row in issues})
        self.assertIn("hard", {row["severity"] for row in issues})

    def test_multiple_real_actions_are_flagged_for_review(self) -> None:
        issues = line_contract_issues(
            chapter_id="chapter",
            stage_id="stage",
            line_index=0,
            line={"kind": "action", "position": "[1,2]", "text": "Parle à Bob puis achète la clef."},
        )
        self.assertIn("multiple_real_actions_in_one_line", {row["code"] for row in issues})

    def test_narrative_consequence_is_not_a_second_player_action(self) -> None:
        issues = line_contract_issues(
            chapter_id="chapter",
            stage_id="stage",
            line_index=0,
            line={
                "kind": "action",
                "position": "",
                "text": "Dans Traître ou pas traître, choisir le camp de Vil Smisse. La quête se ferme et ouvre Info pour un vrai traître.",
            },
        )
        self.assertNotIn("multiple_real_actions_in_one_line", {row["code"] for row in issues})

    def test_drop_instruction_requires_purchase_alternative(self) -> None:
        missing = line_contract_issues(
            chapter_id="chapter",
            stage_id="stage",
            line_index=0,
            line={"kind": "action", "position": "", "text": "Drop 5 ressources sur les monstres."},
        )
        self.assertIn("drop_without_purchase_alternative", {row["code"] for row in missing})

        complete = line_contract_issues(
            chapter_id="chapter",
            stage_id="stage",
            line_index=0,
            line={"kind": "action", "position": "", "text": "Drop 5 ressources, ou achète-les en HDV."},
        )
        self.assertNotIn("drop_without_purchase_alternative", {row["code"] for row in complete})

    def test_drop_noun_does_not_require_purchase_alternative(self) -> None:
        issues = line_contract_issues(
            chapter_id="chapter",
            stage_id="stage",
            line_index=0,
            line={"kind": "action", "position": "", "text": "Conserve les ressources et drops utiles pour plus tard."},
        )
        self.assertNotIn("drop_without_purchase_alternative", {row["code"] for row in issues})

    def test_repeated_talks_on_same_position_are_flagged(self) -> None:
        issues = stage_contract_issues(
            chapter_id="chapter",
            stage_id="stage",
            lines=[
                {"kind": "action", "position": "[1,2]", "text": "Parle à Bob."},
                {"kind": "action", "position": "[1,2]", "text": "Parle à Bob pour rendre la quête."},
            ],
            resource_names=[],
        )
        self.assertIn("repeated_talk_same_position", {row["code"] for row in issues})

    def test_different_talk_targets_on_same_position_are_not_flagged(self) -> None:
        issues = stage_contract_issues(
            chapter_id="chapter",
            stage_id="stage",
            lines=[
                {"kind": "action", "position": "[1,2]", "text": "Parler à Berb pour avancer la quête."},
                {"kind": "action", "position": "[1,2]", "text": "Parler au tavernier pour la visite."},
            ],
            resource_names=[],
        )
        self.assertNotIn("repeated_talk_same_position", {row["code"] for row in issues})

    def test_preparation_repeated_by_acquisition_is_flagged(self) -> None:
        issues = stage_contract_issues(
            chapter_id="chapter",
            stage_id="stage",
            lines=[
                {"kind": "warning", "position": "", "text": "Prépare 2 × Clef du donjon."},
                {"kind": "action", "position": "[1,2]", "text": "Achète 2 × Clef du donjon."},
            ],
            resource_names=["Clef du donjon"],
        )
        self.assertIn("preparation_repeated_in_now", {row["code"] for row in issues})

    def test_preparation_is_not_repeated_when_action_only_uses_item(self) -> None:
        issues = stage_contract_issues(
            chapter_id="chapter",
            stage_id="stage",
            lines=[
                {"kind": "warning", "position": "", "text": "Prépare 2 × Clef du donjon."},
                {"kind": "action", "position": "[1,2]", "text": "Donne 2 × Clef du donjon à Bob."},
            ],
            resource_names=["Clef du donjon"],
        )
        self.assertNotIn("preparation_repeated_in_now", {row["code"] for row in issues})

    def test_repository_audit_closes_the_phase7e_player_contract(self) -> None:
        report = audit()
        self.assertEqual(report["chapter_count"], 13)
        self.assertEqual(report["stage_count"], 267)
        self.assertGreater(report["line_count"], 0)
        self.assertEqual(report["hard_issue_count"], 0, report["issues"][:20])
        self.assertEqual(report["review_issue_count"], 0, report["issues"][:20])
        self.assertEqual(report["status"], "PASS")


if __name__ == "__main__":
    unittest.main()
