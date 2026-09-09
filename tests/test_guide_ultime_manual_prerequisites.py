from __future__ import annotations

import json
import unittest
from pathlib import Path

from app.modules.encyclopedia.services.guide_ultime_manual_route import load_manual_chapter
from app.modules.encyclopedia.services.guide_ultime_manual_runtime_service import GuideUltimeManualRuntimeService
from tools.audit_guide_ultime_manual_prerequisites import catalog_unavailable_report


ROOT = Path(__file__).resolve().parents[1]
MANUAL = ROOT / "data" / "routes" / "guide_ultime_manual"


class GuideUltimeManualPrerequisiteTests(unittest.TestCase):
    def _bare_service(self) -> GuideUltimeManualRuntimeService:
        service = object.__new__(GuideUltimeManualRuntimeService)
        service.manual_dir = MANUAL
        service.quest_provider = None
        service._quest_name_to_id = {}
        return service

    @staticmethod
    def _texts(lines: list[dict]) -> list[str]:
        return [str(row.get("text") or "") for row in lines]

    @staticmethod
    def _row_names(rows: list[dict]) -> list[str]:
        return [str(row.get("name") or row.get("requirement") or "") for row in rows]

    def test_prerequisites_and_preparation_render_before_travel(self):
        service = self._bare_service()
        stage = {
            "entry": "Niveau 100 réel requis.",
            "activation": "N'exécuter que lorsque le timer est expiré.",
            "hard_gates": ["Métier Alchimiste niveau 50 minimum."],
            "preparation": [{"name": "Clef Test", "quantity": 1}],
            "take": ["Prendre la quête auprès du PNJ."],
            "route": [{"pos": "[1,2]", "do": "Entrer dans le donjon."}],
        }
        lines = service._stage_lines(stage, [])
        texts = self._texts(lines)

        entry = next(i for i, text in enumerate(texts) if "Niveau 100" in text)
        timer = next(i for i, text in enumerate(texts) if "timer" in text)
        profession = next(i for i, text in enumerate(texts) if "Alchimiste niveau 50" in text)
        key = next(i for i, text in enumerate(texts) if "Clef Test" in text)
        take = next(i for i, text in enumerate(texts) if "Prendre la quête" in text)
        travel = next(i for i, text in enumerate(texts) if "Entrer dans le donjon" in text)

        self.assertLess(entry, travel)
        self.assertLess(timer, travel)
        self.assertLess(profession, travel)
        self.assertLess(key, travel)
        self.assertLess(take, travel)

    def test_pandala_chapter_preparation_is_visible_on_first_relevant_card(self):
        chapter = load_manual_chapter(MANUAL / "pandala_access_v1.json")
        stages = [row for row in chapter["stages"] if isinstance(row, dict)]
        schedule = GuideUltimeManualRuntimeService._chapter_preparation_schedule(chapter, stages)
        pad00 = next(i for i, row in enumerate(stages) if row.get("id") == "PAD-00")
        names = self._row_names(schedule.get(pad00, []))

        self.assertIn("Ortie", names)
        self.assertIn("Laine de Boufton Noir", names)
        self.assertIn("Graisse Gélatineuse", names)

    def test_freres_ennemis_global_shopping_is_announced_once_before_rat_blanc(self):
        chapter = load_manual_chapter(MANUAL / "level_100_120_v9.json")
        stages = [row for row in chapter["stages"] if isinstance(row, dict)]
        schedule = GuideUltimeManualRuntimeService._chapter_preparation_schedule(chapter, stages)
        rat_blanc = next(i for i, row in enumerate(stages) if row.get("id") == "L100-09")
        rat_noir = next(i for i, row in enumerate(stages) if row.get("id") == "L100-12")

        blanc_names = self._row_names(schedule.get(rat_blanc, []))
        noir_names = self._row_names(schedule.get(rat_noir, []))
        self.assertIn("Oignon", blanc_names)
        self.assertIn("Aubergine", blanc_names)
        self.assertIn("Champignon Luidegît", blanc_names)
        self.assertNotIn("Oignon", noir_names)
        self.assertNotIn("Aubergine", noir_names)

    def test_ebene_profession_gates_are_visible_on_current_creuset_card(self):
        service = self._bare_service()
        chapter = load_manual_chapter(MANUAL / "level_191_200_v22.json")
        stage = next(row for row in chapter["stages"] if row.get("id") == "L200-15E2")
        rendered = "\n".join(
            self._texts(service._stage_lines(stage, service._stage_quest_names(stage)))
        ).replace(" ", "")

        self.assertIn("Paysan80", rendered)
        self.assertIn("Mineur20", rendered)

    def test_canonical_royalmouth_activation_and_prerequisites_are_rendered(self):
        service = self._bare_service()
        chapter = load_manual_chapter(MANUAL / "level_120_150_v21.json")
        stage = next(row for row in chapter["stages"] if row.get("id") == "L120-20")
        lines = service._stage_lines(stage, service._stage_quest_names(stage))
        text = "\n".join(self._texts(lines))

        self.assertIn("Vaccin temporaire", text)
        self.assertIn("Épis d'Emi", text)
        self.assertIn("quatre quêtes", text)

    def test_frigostien_uses_exact_faire_le_tas_de_pin_title(self):
        chapter = load_manual_chapter(MANUAL / "level_120_150_v21.json")
        stage = next(row for row in chapter["stages"] if row.get("id") == "L120-20F")
        quests = [str(value) for value in stage.get("quests", [])]
        hard_exit = "\n".join(str(value) for value in stage.get("hard_exit", []))
        route = "\n".join(
            str(row.get("do") or "")
            for row in stage.get("route", [])
            if isinstance(row, dict)
        )

        self.assertIn("Faire le tas de pin", quests)
        self.assertNotIn("Faire le tas de pins", quests)
        self.assertIn("Faire le tas de pin terminée une fois", hard_exit)
        self.assertNotIn("Faire le tas de pins", hard_exit)
        self.assertIn("Gormor", route)
        self.assertIn("Chef Rhonté", route)

    def test_missing_quest_catalog_is_reported_as_unavailable_not_route_gaps(self):
        report = catalog_unavailable_report(
            {"status": "BUILDING"},
            [
                {"quests": ["Quête A", "Quête B"]},
                {"quests": ["Quête C"]},
            ],
        )

        self.assertEqual(report["status"], "CATALOG_UNAVAILABLE")
        self.assertFalse(report["audit_complete"])
        self.assertFalse(report["catalog_available"])
        self.assertEqual(report["route_quest_occurrence_count"], 3)
        self.assertEqual(report["route_quest_occurrences_checked"], 0)
        self.assertEqual(report["hard_error_count"], 0)
        self.assertEqual(report["warnings"][0]["code"], "quest_catalog_unavailable")

    def test_canonical_emerald_hard_gates_are_rendered(self):
        service = self._bare_service()
        chapter = load_manual_chapter(MANUAL / "level_100_120_v9.json")
        stage = next(row for row in chapter["stages"] if row.get("id") == "L100-01")
        lines = service._stage_lines(stage, service._stage_quest_names(stage))
        text = "\n".join(self._texts(lines))

        self.assertIn("Éleveur niveau 20", text)
        self.assertIn("Ce n'est qu'un prélèvement", text)
        self.assertIn("Elle a peut-être trop mangé", text)

    def test_ocre_ambre_waits_for_meriana_and_keeps_reruns_causal(self):
        amakna = load_manual_chapter(MANUAL / "amakna_40_60_v5.json")
        amk = next(row for row in amakna["stages"] if row.get("id") == "AMK-02O")
        self.assertNotIn("Le Dofus et l'alchimiste", amk.get("quests", []))
        self.assertNotIn("La raison du plus fort", amk.get("quests", []))

        level51 = load_manual_chapter(MANUAL / "level_51_70_v4.json")
        hesque = next(row for row in level51["stages"] if row.get("id") == "L51-02")
        self.assertNotIn("Après lui, le déluge", hesque.get("quests", []))
        self.assertIn("Donjon magistral", hesque.get("quests", []))
        self.assertIn("L'éternelle moisson", hesque.get("quests", []))

        level70 = load_manual_chapter(MANUAL / "level_70_100_v10.json")
        stage = next(row for row in level70["stages"] if row.get("id") == "L70-00E")
        for quest in (
            "Protéger et sévir",
            "Le Dofus et l'alchimiste",
            "L'éternelle moisson",
            "La raison du plus fort",
            "Après lui, le déluge",
            "Comme un corbac sur sa branche",
        ):
            self.assertIn(quest, stage.get("quests", []))

        route = "\n".join(str(row.get("do") or "") for row in stage.get("route", []) if isinstance(row, dict))
        self.assertLess(route.index("La magicienne des marécages"), route.index("Le Dofus et l'alchimiste"))
        self.assertLess(route.index("Le Dofus et l'alchimiste"), route.index("Protéger et sévir"))
        self.assertLess(route.index("Le Dofus et l'alchimiste"), route.index("La raison du plus fort"))
        self.assertIn("Ce passage est nouveau", route)
        self.assertIn("Revenir dans la Grotte Hesque", route)

    def test_manifest_points_to_causal_ocre_ambre_versions(self):
        manifest = json.loads((MANUAL / "manifest_v1.json").read_text(encoding="utf-8"))
        chapters = {row["id"]: row for row in manifest["canonical"]["chapters"]}
        self.assertEqual(chapters["amakna_40_60"]["file"], "amakna_40_60_v5.json")
        self.assertEqual(chapters["level_51_70"]["file"], "level_51_70_v4.json")
        self.assertEqual(chapters["level_70_100"]["file"], "level_70_100_v10.json")
        self.assertEqual(chapters["level_120_150"]["file"], "level_120_150_v21.json")
        self.assertEqual(chapters["level_150_170"]["file"], "level_150_170_v21.json")
        self.assertEqual(chapters["level_181_190"]["file"], "level_181_190_v15.json")
        self.assertEqual(chapters["level_191_200"]["file"], "level_191_200_v22.json")
        self.assertEqual(chapters["level_200_plus"]["file"], "level_200_plus_v11.json")
        self.assertEqual(sum(int(row["stage_count"]) for row in chapters.values()), 267)


if __name__ == "__main__":
    unittest.main()
