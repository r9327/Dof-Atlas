from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from app.modules.encyclopedia.services.guide_ultime_manual_route import load_manual_chapter

ROOT = Path(__file__).resolve().parents[1]
ROUTE_BASE = ROOT / "data" / "routes" / "guide_ultime_manual"


class GuideUltimeManualRouteCompositionTests(unittest.TestCase):
    def _write(self, root: Path, name: str, payload: dict) -> Path:
        path = root / name
        path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        return path

    def test_stage_order_reorders_without_losing_stages(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write(root, "base.json", {
                "schema_version": 1,
                "stages": [{"id": "A"}, {"id": "B"}, {"id": "C"}],
            })
            path = self._write(root, "v2.json", {
                "schema_version": 2,
                "base_file": "base.json",
                "stage_order": ["A", "C", "B"],
            })
            resolved = load_manual_chapter(path)
            self.assertEqual([row["id"] for row in resolved["stages"]], ["A", "C", "B"])
            self.assertEqual(resolved["stage_count"], 3)

    def test_stage_order_rejects_missing_stage(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write(root, "base.json", {"stages": [{"id": "A"}, {"id": "B"}, {"id": "C"}]})
            path = self._write(root, "v2.json", {"base_file": "base.json", "stage_order": ["A", "C"]})
            with self.assertRaises(ValueError):
                load_manual_chapter(path)

    def test_stage_order_rejects_duplicate_stage(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write(root, "base.json", {"stages": [{"id": "A"}, {"id": "B"}]})
            path = self._write(root, "v2.json", {"base_file": "base.json", "stage_order": ["A", "A"]})
            with self.assertRaises(ValueError):
                load_manual_chapter(path)

    def test_repository_bonta_v10_resolves_rank90_and_keeps_order80_history(self) -> None:
        resolved = load_manual_chapter(ROUTE_BASE / "bonta_1_90_v10.json")
        self.assertEqual(resolved["quest_range"], [1, 90])
        self.assertEqual(resolved["stage_count"], 43)
        by_id = {str(row.get("id") or ""): row for row in resolved["stages"]}

        sphincter = by_id["BNT-27"]
        self.assertIn("La bénédiction de Thomahon", sphincter["quests"])
        self.assertIn("Tour de rein", sphincter["quests"])
        self.assertIn("Bandanarthrie", sphincter["quests"])
        self.assertNotIn("Ne pas attendre La bénédiction de Thomahon", json.dumps(sphincter, ensure_ascii=False))

        rank80 = by_id["BNT-36"]
        self.assertIn("L'Éclat de l'Aube", rank80["quests"])
        self.assertIn("Ordre80", json.dumps(rank80, ensure_ascii=False))

        rank85 = by_id["BNT-39"]
        self.assertIn("Gelé à pierre fendre", rank85["quests"])
        self.assertIn("PASS3 GLOBAL CAUSAL", json.dumps(rank85, ensure_ascii=False))

        rank90 = by_id["BNT-42"]
        self.assertIn("Ça fait froid dans le dos", rank90["quests"])
        rank90_text = json.dumps(rank90, ensure_ascii=False)
        self.assertIn("Grolloum", rank90_text)
        self.assertIn("Gobiling", rank90_text)
        self.assertEqual(resolved["_resolved_from"][-3:], [
            "bonta_1_80_v8.json",
            "bonta_1_80_v9.json",
            "bonta_1_90_v10.json",
        ])

    def test_repository_backpatches_resolve_without_extra_dungeons(self) -> None:
        level70 = load_manual_chapter(ROUTE_BASE / "level_70_100_v6.json")
        self.assertEqual(level70["stage_count"], 17)
        by70 = {str(row.get("id") or ""): row for row in level70["stages"]}
        self.assertIn("Le Gardien du Pont de la Mort", by70["L70-05"]["quests"])
        self.assertIn("Le Chevalier Noir et Rose", by70["L70-05"]["quests"])
        self.assertIn("Tourbière nauséabonde", json.dumps(by70["L70-05"], ensure_ascii=False))

        level120 = load_manual_chapter(ROUTE_BASE / "level_120_150_v6.json")
        self.assertEqual(level120["stage_count"], 33)
        by120 = {str(row.get("id") or ""): row for row in level120["stages"]}
        self.assertIn("La destinée", by120["L120-00"]["quests"])
        for quest in ("Bricole Girl", "Pêche en eaux gelées", "L'essentiel est dans Lac Gelé", "Hôtel de glace", "La fonte des glaces"):
            self.assertIn(quest, by120["L120-20F"]["quests"])
        self.assertIn("Malédiction !", by120["L120-21M"]["quests"])

        level150 = load_manual_chapter(ROUTE_BASE / "level_150_170_v8.json")
        self.assertEqual(level150["stage_count"], 24)
        by150 = {str(row.get("id") or ""): row for row in level150["stages"]}
        self.assertIn("La voie du guerrier", by150["L150-02T"]["quests"])
        self.assertIn("Minotot", json.dumps(by150["L150-02T"], ensure_ascii=False))
        self.assertIn("À la recherche de Dan Lavy", by150["L150-03"]["quests"])
        self.assertIn("sans Obsidiantre supplémentaire", json.dumps(by150["L150-03"], ensure_ascii=False))
        self.assertIn("Convoi humanitaire", by150["L150-07D"]["quests"])
        self.assertIn("Sang dessus-dessous", by150["L150-07D"]["quests"])
        self.assertIn("Les rescapés de Frigost", by150["L150-08R"]["quests"])

    def test_repository_level_171_180_v4_closes_tour_and_prepares_glours(self) -> None:
        resolved = load_manual_chapter(ROUTE_BASE / "level_171_180_v4.json")
        self.assertEqual(resolved["stage_count"], 30)
        ids = [str(row.get("id") or "") for row in resolved["stages"]]
        self.assertEqual(len(ids), len(set(ids)))
        by_id = {str(row.get("id") or ""): row for row in resolved["stages"]}

        self.assertIn("La prolifération a crû", by_id["L180-12"]["quests"])
        self.assertNotIn("La prolifération à crû", by_id["L180-12"]["quests"])

        korriandre = [
            row for row in resolved["stages"]
            if isinstance(row.get("dungeon"), dict)
            and row["dungeon"].get("name") == "Antre du Korriandre"
        ]
        self.assertEqual([row["id"] for row in korriandre], ["L180-05", "L180-07"])

        self.assertIn("La voie du guerrier", by_id["L180-13B"]["quests"])
        self.assertIn("Le tracas du guerrier", by_id["L180-13B"]["quests"])
        self.assertIn("Tour du Monde complet", json.dumps(by_id["L180-13B"], ensure_ascii=False))

        merkator = by_id["L180-13S"]
        self.assertEqual(merkator["dungeon"]["name"], "Aquadôme de Merkator")
        self.assertFalse(merkator["dungeon"]["capture_allowed"])
        self.assertIn("Tour nage", merkator["quests"])
        self.assertIn("Pollution, je dis non", merkator["quests"])
        self.assertIn("Le tour est joué", merkator["quests"])

        slip = by_id["L180-13F"]
        self.assertIn("Dépôt de ravitaillement", slip["quests"])
        self.assertIn("Chaud du S.L.I.P.", slip["quests"])
        self.assertIn("Mission Solution", slip["quests"])
        slip_text = json.dumps(slip, ensure_ascii=False)
        self.assertIn("frigost_depot_lulu_day_window", slip_text)
        self.assertIn("frigost_chaud_slip_night_window", slip_text)
        self.assertIn("STOP AVANT ENTRÉE", slip_text)

        self.assertFalse(by_id["L180-02"]["dungeon"]["capture_allowed"])
        self.assertFalse(by_id["L180-15"]["dungeon"]["capture_allowed"])
        self.assertNotIn("Dofus Ébène obtenu", json.dumps(by_id["L180-18"], ensure_ascii=False))
        self.assertEqual(resolved["_resolved_from"][-3:], [
            "level_171_180_v2.json",
            "level_171_180_v3.json",
            "level_171_180_v4.json",
        ])

    def test_repository_level_181_190_v3_has_causal_boss_counts_and_abyssal(self) -> None:
        resolved = load_manual_chapter(ROUTE_BASE / "level_181_190_v3.json")
        self.assertEqual(resolved["stage_count"], len(resolved["stages"]))
        ids = [str(row.get("id") or "") for row in resolved["stages"]]
        self.assertEqual(len(ids), len(set(ids)))
        by_id = {str(row.get("id") or ""): row for row in resolved["stages"]}

        def dungeon_ids(name: str) -> list[str]:
            return [
                str(row.get("id") or "") for row in resolved["stages"]
                if isinstance(row.get("dungeon"), dict)
                and row["dungeon"].get("name") == name
            ]

        self.assertEqual(dungeon_ids("Antre du Korriandre"), ["L185-02"])
        self.assertEqual(dungeon_ids("Cavernes du Kolosso"), ["L190-02", "L190-04"])
        self.assertEqual(dungeon_ids("Antichambre des Gloursons"), ["L190-05", "L190-06"])
        self.assertEqual(dungeon_ids("Vaisseau du Capitaine Meno"), ["L190-10B"])
        self.assertEqual(dungeon_ids("Palais de Dantinéa"), ["L190-10C"])
        self.assertEqual(dungeon_ids("Temple de Koutoulou"), ["L190-10E"])

        self.assertIn("Un remède à tous les maux", by_id["L190-02"]["quests"])
        self.assertIn("C'est Rébro", by_id["L190-04"]["quests"])
        self.assertIn("Mission Solution", by_id["L190-05"]["quests"])
        self.assertIn("Glourson et lumière", by_id["L190-06"]["quests"])
        self.assertIn("Au fion du trou", by_id["L190-08"]["quests"])
        self.assertIn("Grolloum", json.dumps(by_id["L190-08"], ensure_ascii=False))

        self.assertEqual(by_id["L190-10"].get("quests"), [])
        self.assertIn("Dofus Nébuleux", by_id["L190-10"].get("thread", ""))
        self.assertIn("La pêche aux infos", by_id["L190-10A"]["quests"])
        self.assertIn("Piège de crystal", by_id["L190-10B"]["quests"])
        self.assertIn("Reine de beauté", by_id["L190-10C"]["quests"])
        self.assertIn("Fhtagn !", by_id["L190-10D"]["quests"])
        self.assertIn("De mal en impie", by_id["L190-10E"]["quests"])
        self.assertIn("Le héros de Sufokia", by_id["L190-10F"]["quests"])
        self.assertIn("Aucun faux Abyssal", json.dumps(by_id["L190-10F"], ensure_ascii=False))
        self.assertEqual(resolved["_resolved_from"][-3:], [
            "level_181_190_v1.json",
            "level_181_190_v2.json",
            "level_181_190_v3.json",
        ])


if __name__ == "__main__":
    unittest.main()
