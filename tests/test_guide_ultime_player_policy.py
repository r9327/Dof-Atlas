from __future__ import annotations

import unittest

from app.modules.encyclopedia.services.guide_ultime_manual_runtime_core import (
    GuideUltimeManualRuntimeService as GuideUltimeManualRuntimeCore,
)
from app.modules.encyclopedia.services.guide_ultime_manual_runtime_service import (
    GuideUltimeManualRuntimeService,
)
from app.modules.encyclopedia.services.guide_ultime_player_policy import (
    apply_player_line_policy,
    ensure_drop_purchase_alternative,
    line_acquires_resource,
    split_real_actions,
)


class GuideUltimePlayerPolicyTests(unittest.TestCase):
    def test_public_runtime_wraps_the_canonical_core(self) -> None:
        self.assertTrue(issubclass(GuideUltimeManualRuntimeService, GuideUltimeManualRuntimeCore))

    def test_splits_consecutive_real_actions_but_keeps_consequences(self) -> None:
        text = (
            "Après Gourlo, parler au Chevalier Noir et Rose avec La vengeance de Peggy active, "
            "prendre Le Chevalier Noir et Rose puis gagner le combat. "
            "Cette victoire ferme les deux fils et ouvre définitivement la Tourbière nauséabonde."
        )
        self.assertEqual(
            split_real_actions(text),
            [
                "Après Gourlo, parler au Chevalier Noir et Rose avec La vengeance de Peggy active",
                "prendre Le Chevalier Noir et Rose",
                "gagner le combat. Cette victoire ferme les deux fils et ouvre définitivement la Tourbière nauséabonde.",
            ],
        )

    def test_quest_title_commas_do_not_create_fake_actions(self) -> None:
        text = "Après Monarchie parlementaire et Fais dodo, t'auras du gâteau, prendre Piwates."
        self.assertEqual(split_real_actions(text), [text])

    def test_drop_action_gets_hdv_alternative_but_drop_noun_does_not(self) -> None:
        self.assertEqual(
            ensure_drop_purchase_alternative("Drop 3 Poudres magik sur Bozoteur."),
            "Drop 3 Poudres magik sur Bozoteur. Alternative : achat en HDV possible.",
        )
        noun = "Conserve les ressources et drops utiles."
        self.assertEqual(ensure_drop_purchase_alternative(noun), noun)

    def test_acquisition_requires_resource_and_verb_in_the_same_clause(self) -> None:
        text = (
            "Après Nyée, remettre l'Oeuf noir, fabriquer l'ambre enchanté avec les ressources déjà préparées, "
            "terminer les combats/dialogues et purifier l'ambre avec l'Anneau Ocre."
        )
        self.assertFalse(line_acquires_resource(text, "Ambre"))
        self.assertFalse(line_acquires_resource("Conserver l'Or pendant l'Ordre 80.", "Or"))
        self.assertTrue(line_acquires_resource("Achète 30 Ambre avant de repartir.", "Ambre"))

    def test_preparation_is_removed_only_when_the_same_stage_acquires_the_item(self) -> None:
        rows = apply_player_line_policy(
            [
                {"kind": "warning", "position": "", "text": "Prépare 2 × Clef du donjon."},
                {"kind": "action", "position": "[1,2]", "text": "Achète 2 × Clef du donjon."},
            ]
        )
        self.assertEqual([row["kind"] for row in rows], ["action"])

        rows = apply_player_line_policy(
            [
                {"kind": "warning", "position": "", "text": "Prépare 2 × Clef du donjon."},
                {"kind": "action", "position": "[1,2]", "text": "Donne 2 × Clef du donjon à Bob."},
            ]
        )
        self.assertEqual([row["kind"] for row in rows], ["warning", "action"])


if __name__ == "__main__":
    unittest.main()
