from __future__ import annotations

import json
import unittest
from pathlib import Path

from app.modules.encyclopedia.services.guide_ultime_manual_route import load_manual_chapter

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "data" / "routes" / "guide_ultime_manual"


class GuideUltimeManualLevel191200V4Tests(unittest.TestCase):
    def test_level120_v7_repairs_ice_careers(self) -> None:
        resolved = load_manual_chapter(BASE / "level_120_150_v7.json")
        self.assertEqual(resolved["stage_count"], 34)
        by_id = {str(x.get("id") or ""): x for x in resolved["stages"]}
        self.assertIn("L'ombre et la glace", by_id["L120-20G"]["quests"])
        self.assertIn("Lumière sur l'ombre", by_id["L120-20G"]["quests"])

    def test_level191_v4_resolves_33_unique_stages(self) -> None:
        resolved = load_manual_chapter(BASE / "level_191_200_v4.json")
        self.assertEqual(resolved["stage_count"], 33)
        ids = [str(x.get("id") or "") for x in resolved["stages"]]
        self.assertEqual(len(ids), len(set(ids)))
        for sid in (
            "L200-DDG1", "L200-DDG2", "L200-DDG3",
            "L200-15E1", "L200-15E2", "L200-15E6",
            "L200-NEB1", "L200-NEB2", "L200-NEB3",
            "L200-NEB4", "L200-NEB5", "L200-NEB6",
        ):
            self.assertIn(sid, ids)

    def test_ddg_missiz_is_shared_after_sylargh_klime(self) -> None:
        resolved = load_manual_chapter(BASE / "level_191_200_v4.json")
        ids = [str(x.get("id") or "") for x in resolved["stages"]]
        by_id = {str(x.get("id") or ""): x for x in resolved["stages"]}
        self.assertLess(ids.index("L200-DDG1"), ids.index("L197-02"))
        text = json.dumps(by_id["L197-02"], ensure_ascii=False)
        for token in ("À glacer le sang", "La dernière carte", "Chaud et Froid", "Missiz passage unique"):
            self.assertIn(token, text)

    def test_ivoire_nidas_and_meno_are_optimized(self) -> None:
        resolved = load_manual_chapter(BASE / "level_191_200_v4.json")
        by_id = {str(x.get("id") or ""): x for x in resolved["stages"]}
        nidas = json.dumps(by_id["L200-09"], ensure_ascii=False)
        for token in ("Casse en Enutrosor", "Un morceau de roi", "Coiffeur de génie", "Un seul Nidas"):
            self.assertIn(token, nidas)
        meno = json.dumps(by_id["L200-13"], ensure_ascii=False)
        self.assertIn("RERUN CAUSAL MENO", meno)
        self.assertIn("Aucun troisième Meno", meno)
        self.assertIn("Il faut mettre un terme aux maîtres", meno)

    def test_ebene_never_fakes_songes(self) -> None:
        resolved = load_manual_chapter(BASE / "level_191_200_v4.json")
        by_id = {str(x.get("id") or ""): x for x in resolved["stages"]}
        first = json.dumps(by_id["L200-15E1"], ensure_ascii=False)
        self.assertIn("12/12", first)
        self.assertIn("SUSPENDRE", first)
        koutoulou = json.dumps(by_id["L200-15E2"], ensure_ascii=False)
        self.assertIn("RERUN CAUSAL", koutoulou)
        final = json.dumps(by_id["L200-15E6"], ensure_ascii=False)
        self.assertIn("runtime confirme", final)

    def test_nebuleux_shares_nidas_and_uses_one_vortex(self) -> None:
        resolved = load_manual_chapter(BASE / "level_191_200_v4.json")
        by_id = {str(x.get("id") or ""): x for x in resolved["stages"]}
        self.assertIn("Aucun Nidas isolé", json.dumps(by_id["L200-NEB1"], ensure_ascii=False))
        vortex = by_id["L200-NEB5"]
        self.assertEqual(vortex["dungeon"]["name"], "Œil de Vortex")
        text = json.dumps(vortex, ensure_ascii=False)
        self.assertIn("La vérité est au fond du puits", text)
        self.assertIn("Les sables du temps", text)
        self.assertIn("Faire UN Vortex", text)
        final = json.dumps(by_id["L200-NEB6"], ensure_ascii=False)
        self.assertIn("4 personnages", final)
        self.assertIn("runtime confirme", final)


if __name__ == "__main__":
    unittest.main()
