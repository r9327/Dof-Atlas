from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from app.modules.encyclopedia.services.guide_ultime_manual_runtime_service import (
    GuideUltimeManualRuntimeService,
)
from app.modules.encyclopedia.services.guide_ultime_ocre_registry import (
    load_ocre_capture_registry,
    ocre_bosses_for_stage,
    ocre_capture_lines,
)


class GuideUltimeOcreRegistryRuntimeTests(unittest.TestCase):
    def _registry(self) -> dict:
        return {
            "rules": {"kralamoure_special_capture": True},
            "boss_steps": {
                "1": ["Scarabosse Doré", "Bouftou Royal"],
                "3": ["Kralamoure Géant"],
            },
            "early_route_state": [
                {"boss": "Scarabosse Doré", "state": "capture_first_pass", "minimum_power": 50},
                {"boss": "Bouftou Royal", "state": "backfill_if_not_already_owned"},
            ],
        }

    def test_registry_loader_follows_manifest_reference(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "registry.json").write_text(
                '{"boss_steps":{"1":["Boss Test"]},"rules":{}}',
                encoding="utf-8",
            )
            registry = load_ocre_capture_registry(
                root,
                {"canonical": {"ocre_capture_registry": "registry.json"}},
            )
            self.assertEqual(registry["boss_steps"]["1"], ["Boss Test"])

    def test_stage_matching_requires_authored_boss_evidence(self) -> None:
        registry = self._registry()
        matching = ocre_bosses_for_stage(
            {
                "title": "Donjon Scarafeuilles",
                "route": [{"do": "Vaincre Scarabosse Doré avec les fils actifs."}],
            },
            registry,
        )
        self.assertEqual([row["name"] for row in matching], ["Scarabosse Doré"])

        unrelated = ocre_bosses_for_stage(
            {"title": "Plaine des Scarafeuilles", "route": [{"do": "Continuer la quête."}]},
            registry,
        )
        self.assertEqual(unrelated, ())

    def test_known_stone_power_is_shown_only_when_authored(self) -> None:
        lines = ocre_capture_lines(
            {"route": [{"do": "Vaincre Scarabosse Doré."}]},
            self._registry(),
            capture_unlocked=True,
        )
        self.assertEqual(len(lines), 1)
        self.assertIn("puissance 50 minimum", lines[0]["text"])
        self.assertIn("conserve-la en banque", lines[0]["text"])

        generic = ocre_capture_lines(
            {"route": [{"do": "Vaincre Bouftou Royal."}]},
            self._registry(),
            capture_unlocked=True,
        )
        self.assertEqual(len(generic), 1)
        self.assertIn("puissance adaptée au boss", generic[0]["text"])
        self.assertNotIn("puissance 50", generic[0]["text"])

    def test_pre_unlock_boss_is_backfill_not_fake_capture(self) -> None:
        lines = ocre_capture_lines(
            {"route": [{"do": "Vaincre Bouftou Royal."}]},
            self._registry(),
            capture_unlocked=False,
        )
        self.assertEqual(len(lines), 1)
        self.assertIn("avant l'obtention de Capture d'âmes", lines[0]["text"])
        self.assertIn("ne simule aucune capture", lines[0]["text"])

    def test_existing_authored_capture_instruction_is_not_duplicated(self) -> None:
        lines = ocre_capture_lines(
            {"route": [{"do": "Vaincre Scarabosse Doré."}]},
            self._registry(),
            capture_unlocked=True,
            existing_lines=[
                {
                    "kind": "action",
                    "position": "",
                    "text": "Équipe une pierre et capture Scarabosse Doré avec Capture d'âmes.",
                }
            ],
        )
        self.assertEqual(lines, [])

    def test_capture_for_another_boss_does_not_hide_guidance(self) -> None:
        lines = ocre_capture_lines(
            {"route": [{"do": "Vaincre Bouftou Royal."}]},
            self._registry(),
            capture_unlocked=True,
            existing_lines=[
                {
                    "kind": "action",
                    "position": "",
                    "text": "Capture Scarabosse Doré avec une pierre d'âme adaptée.",
                }
            ],
        )
        self.assertEqual(len(lines), 1)
        self.assertIn("Bouftou Royal", lines[0]["text"])

    def test_kralamoure_never_gets_standard_stone_instruction(self) -> None:
        lines = ocre_capture_lines(
            {"dungeon": {"name": "Antre du Kralamoure Géant"}},
            self._registry(),
            capture_unlocked=True,
        )
        self.assertEqual(len(lines), 1)
        self.assertIn("pierre spéciale", lines[0]["text"])
        self.assertIn("n'utilise pas de pierre standard", lines[0]["text"])

    def test_capture_transition_and_archi_policy_are_visible(self) -> None:
        service = object.__new__(GuideUltimeManualRuntimeService)
        service.manual_dir = Path(__file__).resolve().parents[1] / "data" / "routes" / "guide_ultime_manual"
        service._manual_manifest_cache = None
        service._manual_ocre_registry_cache = None
        card = {
            "index": 1,
            "manual_quest_names": [],
            "manual_stage_data": {
                "id": "AMK-07",
                "title": "Nid du Kwakwa — apprendre Capture d'âmes",
                "capture_transition": [
                    "Préparer ensuite trois Petites pierres d'âme puissance 50 minimum."
                ],
            },
        }
        service.cards = [card]
        result: list[dict] = []

        service._append_ocre_policy_lines(result, card)

        text = "\n".join(str(row.get("text") or "") for row in result)
        self.assertIn("trois Petites pierres d'âme puissance 50 minimum", text)
        self.assertIn("archimonstre encore manquant", text)
        self.assertIn("ne bloque jamais la route principale", text)


if __name__ == "__main__":
    unittest.main()
