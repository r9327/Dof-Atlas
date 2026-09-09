from __future__ import annotations

import json
import unittest
from pathlib import Path

from app.modules.encyclopedia.services.guide_ultime_manual_route import load_manual_chapter
from app.modules.encyclopedia.services.guide_ultime_manual_runtime_service import (
    GuideUltimeManualRuntimeService,
)


ROOT = Path(__file__).resolve().parents[1]
MANUAL = ROOT / "data" / "routes" / "guide_ultime_manual"


class GuideUltimeManualStructuredDomainTests(unittest.TestCase):
    def _service(self) -> GuideUltimeManualRuntimeService:
        service = object.__new__(GuideUltimeManualRuntimeService)
        service.quest_provider = None
        service._quest_name_to_id = {}
        return service

    @staticmethod
    def _stage(payload: dict, stage_id: str) -> dict:
        return next(stage for stage in payload.get("stages", []) if stage.get("id") == stage_id)

    def test_manifest_promotes_causal_manual_chapters(self) -> None:
        manifest = json.loads((MANUAL / "manifest_v1.json").read_text(encoding="utf-8"))
        chapters = {
            row["id"]: row
            for row in manifest["canonical"]["chapters"]
        }
        self.assertEqual(chapters["astrub"]["file"], "astrub_v5.json")
        self.assertEqual(chapters["amakna_40_60"]["file"], "amakna_40_60_v5.json")
        self.assertEqual(chapters["level_51_70"]["file"], "level_51_70_v4.json")
        self.assertEqual(chapters["level_70_100"]["file"], "level_70_100_v10.json")
        self.assertEqual(chapters["level_120_150"]["file"], "level_120_150_v21.json")
        self.assertEqual(chapters["level_150_170"]["file"], "level_150_170_v21.json")
        self.assertEqual(chapters["level_171_180"]["file"], "level_171_180_v13.json")
        self.assertEqual(chapters["level_181_190"]["file"], "level_181_190_v15.json")
        self.assertEqual(chapters["level_191_200"]["file"], "level_191_200_v22.json")
        self.assertEqual(chapters["level_191_200"]["stage_count"], 62)
        self.assertEqual(chapters["level_200_plus"]["file"], "level_200_plus_v11.json")
        self.assertEqual(sum(int(row["stage_count"]) for row in chapters.values()), 267)

    def test_causal_prerequisite_repairs_are_in_resolved_level120_route(self) -> None:
        payload = load_manual_chapter(MANUAL / "level_120_150_v21.json")
        stage00 = self._stage(payload, "L120-00")
        stage04 = self._stage(payload, "L120-04")
        stage08 = self._stage(payload, "L120-08")
        stage08s = self._stage(payload, "L120-08S")
        stage19 = self._stage(payload, "L120-19")
        stage21 = self._stage(payload, "L120-21")

        for name in ("La terre banquise", "La maire de glace", "Full Contact", "Bienvenue à Frigost"):
            self.assertIn(name, stage00["quests"])
        self.assertIn("Voyage, voyage", stage04["quests"])
        self.assertIn("Une âme en peine", stage08["quests"])
        for name in ("Désert de revanche", "Les bizarreries du Phare Ouest", "Filouterie épicée"):
            self.assertIn(name, stage08s["quests"])
        for name in ("L'accusé de la réception", "Les monstres aboient, la diligence casse"):
            self.assertIn(name, stage19["quests"])
        self.assertIn("Qu'est-ce qu'on a fait des tuyaux ?", stage21["quests"])
        self.assertIn("Lâcher les gaz", stage21["quests"])

    def test_xelorium_prerequisites_precede_prisoners_and_rifts(self) -> None:
        payload = load_manual_chapter(MANUAL / "level_150_170_v21.json")
        stage15 = self._stage(payload, "L150-15")
        for name in ("Anomalies temporelles", "C'est ton destin", "Retour vers le présent", "Prisonniers du temps"):
            self.assertIn(name, stage15["quests"])
        route = "\n".join(str(row.get("do") or "") for row in stage15.get("route", []) if isinstance(row, dict))
        self.assertLess(route.index("Anomalies temporelles"), route.index("Prisonniers du temps"))
        self.assertLess(route.index("Retour vers le présent"), route.index("Prisonniers du temps"))
        stage17 = self._stage(payload, "L150-17")
        self.assertIn("Anomalies temporelles", json.dumps(stage17, ensure_ascii=False))

    def test_random_baka_hunts_never_leak_as_common_quests(self) -> None:
        level150 = load_manual_chapter(MANUAL / "level_150_170_v21.json")
        level181 = load_manual_chapter(MANUAL / "level_181_190_v15.json")
        random_hunts = {"Complètement givré", "L'appel de la forêt", "Crocs en jambes", "Ourse molle"}

        for stage_id in ("L150-07", "L150-08"):
            quests = [str(value) for value in self._stage(level150, stage_id).get("quests", [])]
            unconditional = {value for value in quests if not value.startswith("conditional:")}
            self.assertFalse(random_hunts.intersection(unconditional))
            self.assertTrue(any(value.startswith("conditional:") and "Baka" in value for value in quests))

        for stage_id, hunt in (("L190-00", "Crocs en jambes"), ("L190-04", "Crocs en jambes"), ("L190-05", "Ourse molle"), ("L190-06", "Ourse molle")):
            quests = [str(value) for value in self._stage(level181, stage_id).get("quests", [])]
            self.assertNotIn(hunt, quests)
            self.assertTrue(any(value.startswith("conditional:") and hunt in value for value in quests))

        checkpoint = self._stage(level181, "L190-09")
        checkpoint_quests = {str(value) for value in checkpoint.get("quests", [])}
        self.assertFalse(random_hunts.intersection(checkpoint_quests))
        self.assertEqual(checkpoint_quests, {
            "Frais de porc inclus",
            "Nos amies les bêtes",
            "Il a fui, il a tout compris",
            "Shyriiwook",
            "À armes égales",
            "La valse des manuels",
        })
        self.assertEqual(set(checkpoint.get("successes", [])), {
            "La maire dénie",
            "L'âme de glace",
            "L'hiver arrive",
            "La chasse aux chasseurs",
        })

    def test_stage_to_card_preserves_structured_domain_without_creating_fake_actions(self) -> None:
        service = self._service()
        stage = {
            "id": "TEST-01",
            "title": "Fiche structurée",
            "start": {"x": 1, "y": 2, "zone": "Zone test"},
            "instructions": ["Faire l'action de test."],
            "preparation": [
                {"name": "Ressource Test", "quantity": 3, "policy": "Garder en banque."},
            ],
            "profession_gates": [
                {"profession": "Alchimiste", "level": 50, "requirement": "Alchimiste niveau 50."},
            ],
            "runtime_gates": [
                {"condition": "Avoir accès à la zone."},
            ],
            "pods": {"warning": "Prévoir suffisamment de pods avant la collecte."},
            "before_leave": [
                {"action": "Vérifier les trois objets avant de partir."},
            ],
            "next": {"zone": "Zone suivante"},
        }
        chapter_preparation = [
            {"name": "Clef Test", "quantity": 1, "for": "TEST-01"},
        ]

        card = service._stage_to_card(
            "test_chapter",
            {"label": "Chapitre test"},
            {"coverage": {"chapter": "Chapitre test"}},
            stage,
            1,
            chapter_preparation=chapter_preparation,
        )

        self.assertEqual(card["manual_stage_id"], "TEST-01")
        self.assertEqual(card["manual_stage_data"], stage)
        self.assertIsNot(card["manual_stage_data"], stage)
        self.assertEqual(card["manual_stage_data"]["pods"]["warning"], stage["pods"]["warning"])
        self.assertEqual(card["manual_chapter_preparation"], chapter_preparation)

        prepared_names = {str(row.get("name") or "") for row in card["a_preparer"]}
        self.assertIn("Ressource Test", prepared_names)
        self.assertIn("Clef Test", prepared_names)
        self.assertTrue(any(row.get("_source_field") == "chapter_preparation" for row in card["a_preparer"]))

        self.assertEqual(card["profession_gates"][0]["profession"], "Alchimiste")
        self.assertEqual(card["profession_gates"][0]["level"], 50)
        self.assertEqual(card["hard_runtime_gates"][0]["condition"], "Avoir accès à la zone.")
        self.assertEqual(card["avant_de_partir"], ["Vérifier les trois objets avant de partir."])

        self.assertEqual(card["a_prendre"], [])
        self.assertEqual(card["a_faire_ici"], [])

        stage["preparation"][0]["name"] = "MODIFIÉ APRÈS COUP"
        chapter_preparation[0]["name"] = "MODIFIÉ APRÈS COUP"
        self.assertEqual(card["manual_stage_data"]["preparation"][0]["name"], "Ressource Test")
        self.assertEqual(card["manual_chapter_preparation"][0]["name"], "Clef Test")

    def test_authored_runtime_narrative_fields_are_visible_and_preserved(self) -> None:
        service = self._service()
        stage = {
            "id": "TEST-RUNTIME",
            "title": "Politiques runtime",
            "route": [{"pos": "[1,2]", "do": "Faire l'action principale."}],
            "branch_file": "astrub_class_branches_v1.json",
            "capture_note": "Ne pas refaire ce boss uniquement pour une future capture.",
            "capture_transition": ["À partir d'ici, auditer chaque boss avant entrée."],
            "carry_forward": ["Conserver le fil Wabbit pour le prochain chapitre."],
            "choice_policy": ["Préférer l'option sans combat si elle valide le même objectif."],
            "defer": "Reporter cette branche jusqu'au passage Wabbit naturel.",
            "future_merge": "Fusionner ce fil seulement s'il est réellement débloqué.",
            "temporal_rule": "Ne jamais répéter la quotidienne sans objectif explicite.",
            "conditional": {"warning": "N'exécuter cette action que si le prérequis runtime est vrai."},
            "branch_policy": {"policy": "N'afficher que la branche réellement sélectionnée."},
        }

        card = service._stage_to_card(
            "test_chapter",
            {"label": "Chapitre test"},
            {},
            stage,
            1,
        )
        rendered = "\n".join(str(row.get("text") or "") for row in card["manual_lines"])

        for token in (
            "future capture",
            "auditer chaque boss",
            "fil Wabbit",
            "option sans combat",
            "passage Wabbit naturel",
            "réellement débloqué",
            "quotidienne",
            "prérequis runtime",
            "branche réellement sélectionnée",
        ):
            self.assertIn(token, rendered)

        metadata = card["manual_runtime_metadata"]
        self.assertEqual(metadata["branch_file"], "astrub_class_branches_v1.json")
        self.assertEqual(metadata["capture_note"], stage["capture_note"])
        self.assertEqual(metadata["branch_policy"], stage["branch_policy"])
        self.assertNotIn("astrub_class_branches_v1.json", rendered)

    def test_link_next_cards_uses_stable_manual_stage_identity(self) -> None:
        cards = [
            {
                "manual_stage_id": "A",
                "destination": "[1,2] — A",
                "x": 1,
                "y": 2,
                "zone": "A",
                "subzone": "A",
                "ensuite": None,
            },
            {
                "manual_stage_id": "B",
                "destination": "[3,4] — B",
                "x": 3,
                "y": 4,
                "zone": "B",
                "subzone": "B",
                "ensuite": None,
            },
        ]

        GuideUltimeManualRuntimeService._link_next_cards(cards)

        self.assertEqual(cards[0]["ensuite"]["manual_stage_id"], "B")
        self.assertEqual(cards[0]["ensuite"]["destination"], "[3,4] — B")
        self.assertIsNone(cards[1]["ensuite"])


if __name__ == "__main__":
    unittest.main()
