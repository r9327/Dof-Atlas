from __future__ import annotations

import json
import unittest
from pathlib import Path

from app.modules.encyclopedia.services.guide_ultime_manual_route import load_manual_chapter


ROOT = Path(__file__).resolve().parents[1]
MANUAL = ROOT / "data" / "routes" / "guide_ultime_manual"


def _stage(payload: dict, stage_id: str) -> dict:
    return next(stage for stage in payload.get("stages", []) if stage.get("id") == stage_id)


def _text(stage: dict) -> str:
    return json.dumps(stage, ensure_ascii=False)


class GuideUltimeSilvosseCausalityTests(unittest.TestCase):
    def test_post200_orders_dom_cultures_sigils_flovoraison_and_final_sylvestre(self) -> None:
        payload = load_manual_chapter(MANUAL / "level_200_plus_v9.json")
        self.assertEqual(payload["stage_count"], 12)
        self.assertEqual(payload["stage_count"], len(payload["stages"]))
        ids = [str(stage.get("id") or "") for stage in payload["stages"]]

        expected = ["P200-21", "P200-22", "P200-23", "P200-24", "P200-25"]
        for left, right in zip(expected, expected[1:]):
            self.assertLess(ids.index(left), ids.index(right))

        dom = _stage(payload, "P200-21")
        cultures = _stage(payload, "P200-22")
        sigils = _stage(payload, "P200-23")
        flovoraison = _stage(payload, "P200-24")
        sylvestre = _stage(payload, "P200-25")

        self.assertIn("Dom de Pin réellement obtenu", _text(dom))
        self.assertIn("Les derniers d'entre nous", str(cultures.get("entry") or ""))
        self.assertIn("Gobstination d'un Grobelin", str(cultures.get("entry") or ""))
        self.assertIn("Par ce serment s'écrit le monde", str(cultures.get("entry") or ""))
        self.assertIn("Cultures et turpitudes", str(sigils.get("entry") or ""))
        self.assertIn("Mort et renouveau", str(sigils.get("entry") or ""))
        self.assertIn("Un héritage tourmenté", str(sigils.get("entry") or ""))
        self.assertIn("Dites-le avec des fleurs", str(sigils.get("entry") or ""))
        self.assertIn("Pas de fumée sans feu", str(sigils.get("entry") or ""))
        self.assertIn("Le givre des révélations", str(sigils.get("entry") or ""))
        self.assertIn("Dom de Pin + six Primordiaux", str(flovoraison.get("level") or ""))

        final_text = _text(sylvestre)
        self.assertIn("Dofus Verdoyant", final_text)
        self.assertIn("vrai Dofus Sylvestre", final_text)
        self.assertIn("Nouvelle graine d'Albuera", final_text)

    def test_cultures_routes_all_six_twenty_resource_counters_without_idle_wait(self) -> None:
        payload = load_manual_chapter(MANUAL / "level_200_plus_v9.json")
        cultures = _stage(payload, "P200-22")
        text = _text(cultures)

        for resource in (
            "Humus plantalien",
            "Pierre fertile",
            "Limon des cascades",
            "Cendres fécondes",
            "Akènes à tout vent",
            "Pandouilles fantômes",
        ):
            self.assertIn(resource, text)
            self.assertIn(f"{resource} 20/20", text)

        for zone in ("Terrdala", "Akwadala", "Feudala", "Aerdala", "Plantala", "Grobe"):
            self.assertIn(zone, text)

        self.assertIn("environ 20 minutes", text)
        self.assertIn("jamais 20 minutes d'attente sur une carte", text)
        self.assertIn("Un seul Élixir des Trépasseurs", text)
        self.assertIn("44 combats", text)
        self.assertIn("120 ressources", text)

    def test_cultures_locks_repop_answers_and_real_completion(self) -> None:
        payload = load_manual_chapter(MANUAL / "level_200_plus_v9.json")
        cultures = _stage(payload, "P200-22")
        text = _text(cultures)

        self.assertIn("pas pas pas patient", text)
        self.assertIn("vous êtes un mort réincarné", text)
        self.assertIn("rester immobile", text)
        self.assertIn("délai de 5 minutes", text)
        self.assertIn("Aucune attente immobile", text)
        self.assertIn("Aucun compteur de ressource déclaré terminé avant 20/20 réel", text)
        self.assertIn("Qui nous protège du Protecteur ? disponible", text)

    def test_bonta_sigils_lock_alignment_counts_order_and_post_boss_dialogues(self) -> None:
        payload = load_manual_chapter(MANUAL / "level_200_plus_v9.json")
        sigils = _stage(payload, "P200-23")
        text = _text(sigils)

        self.assertIn("25 Douleurs de Brûlâme", text)
        self.assertIn("100 Âmes de Possédé", text)
        self.assertIn("La Griffe des Démons", text)
        self.assertIn("25 suffisent", text)
        self.assertIn("Hécate ne doit jamais être planifiée avant Ulgrude", text)
        self.assertIn("500 Pépites SUR le personnage", text)
        self.assertIn("NE PAS SORTIR : parler à Sumens", text)
        self.assertIn("Djaul → Solar → Djaul", text)
        self.assertIn("Ménologium béni", text)
        self.assertIn("Aucun second Nidas/Aurore/Solar", text)

    def test_flovoraison_locks_four_seeds_two_spirits_and_dofus_equipment_order(self) -> None:
        payload = load_manual_chapter(MANUAL / "level_200_plus_v9.json")
        flovoraison = _stage(payload, "P200-24")
        text = _text(flovoraison)

        for position in ("[40,-84]", "[38,-80]", "[38,-78]", "[38,-81]", "[23,-80]", "[22,-81]"):
            self.assertIn(position, text)
        self.assertIn("Grolours grognon", text)
        self.assertIn("Colliers de ronces", text)
        self.assertIn("Dofus Turquoise + Dofus Pourpre + Dom de Pin", text)
        self.assertIn("équiper le Dofus Ivoire", text)
        self.assertIn("RÉCEPTACLE DE QUÊTE", text)
        self.assertIn("il n'est jamais enregistré comme Dofus final", text)

    def test_silvosse_heals_then_closes_flovoraison_before_real_final_dofus(self) -> None:
        payload = load_manual_chapter(MANUAL / "level_200_plus_v9.json")
        sylvestre = _stage(payload, "P200-25")
        text = _text(sylvestre)

        self.assertIn("2000/200000", text)
        self.assertIn("200000/200000", text)
        self.assertIn("2 à 3 Gnauls", text)
        self.assertIn("162000 PV", text)
        self.assertIn("attendre que Silvosse joue son tour", text)
        self.assertIn("fantôme de Simple", text)
        self.assertIn("donner le Dofus Verdoyant à Silvosse", text)
        self.assertIn("Flovoraison se termine", text)
        self.assertIn("Nouvelle graine d'Albuera", text)
        self.assertIn("VRAI Dofus Sylvestre final", text)
        self.assertIn("Aucune fermeture synthétique", text)


if __name__ == "__main__":
    unittest.main()
