from __future__ import annotations

import json
import unittest
from pathlib import Path

from app.modules.encyclopedia.services.guide_ultime_manual_route import load_manual_chapter


ROOT = Path(__file__).resolve().parents[1]
ROUTE_BASE = ROOT / "data" / "routes" / "guide_ultime_manual"


class GuideUltimeManualBossFusionTests(unittest.TestCase):
    def test_current_level_191_200_has_causal_boss_fusions(self) -> None:
        resolved = load_manual_chapter(ROUTE_BASE / "level_191_200_v22.json")
        self.assertEqual(resolved["stage_count"], len(resolved["stages"]))
        ids = [str(row.get("id") or "") for row in resolved["stages"]]
        self.assertEqual(len(ids), len(set(ids)))
        by_id = {str(row.get("id") or ""): row for row in resolved["stages"]}

        def pos(stage_id: str) -> int:
            return ids.index(stage_id)

        self.assertLess(pos("P200-15"), pos("L200-VUL1"))
        self.assertLess(pos("P200-15"), pos("L200-DDG1"))
        self.assertLess(pos("P200-15"), pos("L200-13"))
        self.assertLess(pos("P200-15"), pos("L200-15E2"))
        self.assertLess(pos("P200-15"), pos("L200-15E4"))
        self.assertLess(pos("P200-15"), pos("L200-DDG3"))
        self.assertEqual(by_id["P200-15"].get("quests"), [])
        planned = by_id["P200-15"]["totem_policy"]["planned_merges"]
        self.assertEqual(planned, {
            "joy": "Klime",
            "sadness": "Sylargh",
            "fear": "Larve de Koutoulou",
            "anger": "Dazak Martegel",
            "disgust": "Nileza",
            "surprise": "Comte Harebourg",
        })
        self.assertNotIn("Missiz Frizz", planned.values())

        pre_ravages = by_id["P200-13"]
        self.assertIn("Toute possession dépossède", pre_ravages["quests"])
        self.assertNotIn("Au détour d'un rêve perdu", pre_ravages["quests"])

        self.assertIn("Totem Tristesse", json.dumps(by_id["L200-DDG1"], ensure_ascii=False))
        self.assertIn("Totem Joie", json.dumps(by_id["L200-DDG1"], ensure_ascii=False))
        dazak_text = json.dumps(by_id["L200-15E4"], ensure_ascii=False)
        self.assertIn("Totem de la colère", dazak_text)
        self.assertIn("La bible des rancunes", dazak_text)
        self.assertIn("Second Dazak causal uniquement si", dazak_text)
        self.assertIn("Aucun troisième Dazak", dazak_text)
        self.assertIn("Totem Dégoût", json.dumps(by_id["L200-13"], ensure_ascii=False))
        self.assertIn("Totem Peur", json.dumps(by_id["L200-15E2"], ensure_ascii=False))
        missiz_text = json.dumps(by_id["L197-02"], ensure_ascii=False)
        self.assertIn("la Colère est réservée à Dazak", missiz_text)
        self.assertNotIn("Totem Colère obtenu sur Missiz Frizz", missiz_text)
        self.assertNotIn("Totem de la colère", missiz_text)

        self.assertLess(pos("L200-15E6"), pos("P200-00"))
        self.assertLess(pos("P200-00"), pos("P200-06"))
        self.assertLess(pos("P200-06"), pos("P200-07-PREP"))

        self.assertLess(pos("L200-NEB5"), pos("P200-07-CLOSE"))
        self.assertLess(pos("P200-07-CLOSE"), pos("L200-NEB6"))
        self.assertLess(pos("L200-NEB6"), pos("L200-15E6"))
        self.assertLess(pos("P200-07-PREP"), pos("L200-DDG3"))
        self.assertLess(pos("L200-DDG3"), pos("P200-15-CLOSE"))

        comte_text = json.dumps(by_id["L200-DDG3"], ensure_ascii=False)
        self.assertIn("Totem Surprise", comte_text)
        self.assertIn("éclat de destin brisé", comte_text)
        self.assertIn("ddg_totem_sarmer_single_pass", comte_text)

        vortex_text = json.dumps(by_id["L200-NEB5"], ensure_ascii=False)
        self.assertIn("La vérité est au fond du puits", vortex_text)
        self.assertIn("Les sables du temps", vortex_text)
        self.assertIn("S'armer contre le destin", vortex_text)
        self.assertIn("nebuleux_two_quests_plus_sarmer_single_pass", vortex_text)

        close_text = json.dumps(by_id["P200-15-CLOSE"], ensure_ascii=False)
        for donor in ("Klime", "Sylargh", "Koutoulou", "Dazak Martegel", "Nileza", "Comte Harebourg"):
            self.assertIn(donor, close_text)
        self.assertNotIn("Missiz Frizz", close_text)
        self.assertNotIn("Colère Missiz", close_text)

    def test_current_level_191_200_declares_prerequisites_at_their_real_start(self) -> None:
        resolved = load_manual_chapter(ROUTE_BASE / "level_191_200_v22.json")
        self.assertEqual(resolved["stage_count"], 62)
        self.assertEqual(resolved["stage_count"], len(resolved["stages"]))
        ids = [str(row.get("id") or "") for row in resolved["stages"]]
        by_id = {str(row.get("id") or ""): row for row in resolved["stages"]}

        self.assertLess(ids.index("P200-06"), ids.index("P200-07-PREP"))
        self.assertIn("S'armer contre le destin", by_id["P200-07-PREP"]["quests"])
        self.assertNotIn("S'armer contre le destin", by_id["P200-07-CLOSE"].get("quests", []))

        self.assertLess(ids.index("P200-13"), ids.index("P200-14"))
        self.assertLess(ids.index("P200-14"), ids.index("P200-15"))
        self.assertIn("La loi du plus faible", by_id["P200-14"]["quests"])
        self.assertIn("Leçon d'histoire", by_id["P200-14"]["quests"])
        p20014_text = json.dumps(by_id["P200-14"], ensure_ascii=False)
        self.assertIn("Descendre aux cendres terminée", p20014_text)

        self.assertIn("L200-ENUT-PREP", by_id)
        self.assertIn("L200-ENUT-CLOSE", by_id)
        self.assertIn("Reconnaissance de dettes", by_id["L200-ENUT-PREP"]["quests"])

    def test_post_200_v5_removes_every_relocated_stage_and_defers_au_detour(self) -> None:
        resolved = load_manual_chapter(ROUTE_BASE / "level_200_plus_v5.json")
        self.assertEqual(resolved["stage_count"], 12)
        ids = [str(row.get("id") or "") for row in resolved["stages"]]
        self.assertEqual(len(ids), len(set(ids)))

        removed = {
            *(f"P200-0{i}" for i in range(8)),
            *(f"P200-{i}" for i in range(9, 16)),
        }
        self.assertTrue(removed.isdisjoint(ids))
        self.assertIn("P200-08", ids)
        self.assertIn("P200-AU-DETOUR", ids)
        self.assertLess(ids.index("P200-08"), ids.index("P200-AU-DETOUR"))
        self.assertLess(ids.index("P200-AU-DETOUR"), ids.index("P200-16"))

        by_id = {str(row.get("id") or ""): row for row in resolved["stages"]}
        self.assertEqual(by_id["P200-AU-DETOUR"]["quests"], ["Au détour d'un rêve perdu"])

    def test_current_post200_routes_sorceress_before_rebellion_seed(self) -> None:
        resolved = load_manual_chapter(ROUTE_BASE / "level_200_plus_v11.json")
        self.assertEqual(resolved["stage_count"], 12)
        ids = [str(row.get("id") or "") for row in resolved["stages"]]
        self.assertLess(ids.index("P200-18"), ids.index("P200-20"))
        self.assertLess(ids.index("P200-20"), ids.index("P200-19"))
        by_id = {str(row.get("id") or ""): row for row in resolved["stages"]}
        self.assertIn("La sorcière exilée", by_id["P200-20"]["quests"])
        self.assertIn("La graine de la révolte", by_id["P200-19"]["quests"])

    def test_manifest_points_only_to_new_canonical_versions(self) -> None:
        manifest = json.loads((ROUTE_BASE / "manifest_v1.json").read_text(encoding="utf-8"))
        chapters = {
            str(row.get("id") or ""): row
            for row in manifest["canonical"]["chapters"]
        }
        self.assertEqual(chapters["level_191_200"]["file"], "level_191_200_v22.json")
        self.assertEqual(chapters["level_191_200"]["stage_count"], 62)
        self.assertEqual(chapters["level_181_190"]["file"], "level_181_190_v15.json")
        self.assertEqual(chapters["level_181_190"]["stage_count"], 24)
        self.assertEqual(chapters["level_200_plus"]["file"], "level_200_plus_v11.json")
        self.assertEqual(chapters["level_200_plus"]["stage_count"], 12)
        self.assertEqual(sum(int(row["stage_count"]) for row in chapters.values()), 267)


if __name__ == "__main__":
    unittest.main()
