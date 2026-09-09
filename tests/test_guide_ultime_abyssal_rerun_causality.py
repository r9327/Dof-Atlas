from __future__ import annotations

import unittest
from pathlib import Path

from app.modules.encyclopedia.services.guide_ultime_manual_route import load_manual_chapter


BASE = Path(__file__).resolve().parents[1] / "data" / "routes" / "guide_ultime_manual"


class GuideUltimeAbyssalRerunCausalityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        low = load_manual_chapter(BASE / "level_181_190_v15.json")
        high = load_manual_chapter(BASE / "level_191_200_v22.json")
        cls.low = {str(row.get("id") or ""): row for row in low.get("stages", []) if isinstance(row, dict)}
        cls.high = {str(row.get("id") or ""): row for row in high.get("stages", []) if isinstance(row, dict)}

    def test_meno_abyssal_then_ivoire_is_exactly_causal(self) -> None:
        abyssal = str(self.low["L190-10B"])
        ivoire = str(self.high["L200-13"])

        self.assertIn("Piège de crystal", abyssal)
        self.assertIn("Son nom est Personne", abyssal)
        self.assertIn("futur Meno d'Une voix de crystal reste séparé", abyssal)

        self.assertIn("Une voix de crystal", ivoire)
        self.assertIn("Meno reste un rerun causal", ivoire)
        self.assertIn("Pichon kloune", ivoire)
        self.assertIn("sans troisième Meno", ivoire)

    def test_koutoulou_abyssal_then_creuset_totem_is_exactly_causal(self) -> None:
        abyssal = str(self.low["L190-10E"])
        creuset = str(self.high["L200-15E2"])

        self.assertIn("De mal en impie", abyssal)
        self.assertIn("L'appel de Koutoulou", abyssal)
        self.assertIn("sans second Temple Abyssal", abyssal)

        self.assertIn("Le creuset de Mériana", creuset)
        self.assertIn("rerun_causal_after_abyssal", creuset)
        self.assertIn("Totem", creuset)
        self.assertIn("Aucun Koutoulou supplémentaire", creuset)


if __name__ == "__main__":
    unittest.main()
