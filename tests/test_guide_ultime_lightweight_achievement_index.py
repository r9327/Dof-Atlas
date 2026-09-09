from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from app.modules.encyclopedia.services.guide_auto_validation_contract import (
    build_route_auto_validation_contract,
)


class _UnloadedProvider:
    def __init__(self, data_dir: Path) -> None:
        self.data_dir = data_dir
        self._loaded = False
        self.load_all_calls = 0

    def load_all(self):
        self.load_all_calls += 1
        raise AssertionError("Guide contract must not fully load AchievementProvider")


class _LoadedProvider:
    def __init__(self) -> None:
        self._loaded = True
        self.load_all_calls = 0

    def load_all(self):
        self.load_all_calls += 1
        return [SimpleNamespace(id=77, name="Succès Déjà Chargé")]


class GuideUltimeLightweightAchievementIndexTests(unittest.TestCase):
    @staticmethod
    def _card(success_name: str) -> dict:
        return {
            "index": 1,
            "manual_source": True,
            "manual_chapter_id": "test",
            "manual_stage_id": "TEST-1",
            "manual_success_names": [success_name],
            "manual_stage_data": {},
            "manual_quest_ids": [],
            "manual_quest_names": [],
            "a_preparer": [],
            "manual_lines": [],
        }

    def test_unloaded_provider_resolves_success_from_two_lightweight_raw_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp)
            (data_dir / "languages").mkdir(parents=True)
            (data_dir / "languages" / "fr.json").write_text(
                json.dumps({"entries": {"100": "Succès Test"}}, ensure_ascii=False),
                encoding="utf-8",
            )
            (data_dir / "achievements.json").write_text(
                json.dumps(
                    {
                        "references": {
                            "RefIds": [
                                {"data": {"id": 42, "nameId": 100}},
                            ]
                        }
                    }
                ),
                encoding="utf-8",
            )
            provider = _UnloadedProvider(data_dir)

            contract = build_route_auto_validation_contract(
                [self._card("Succès Test")],
                achievement_provider=provider,
            )

            success = contract["cards"][0]["successes"][0]
            self.assertEqual(success["achievement_id"], 42)
            self.assertEqual(success["name"], "Succès Test")
            self.assertEqual(provider.load_all_calls, 0)

    def test_already_loaded_provider_reuses_existing_achievement_models(self):
        provider = _LoadedProvider()

        contract = build_route_auto_validation_contract(
            [self._card("Succès Déjà Chargé")],
            achievement_provider=provider,
        )

        success = contract["cards"][0]["successes"][0]
        self.assertEqual(success["achievement_id"], 77)
        self.assertEqual(provider.load_all_calls, 1)


if __name__ == "__main__":
    unittest.main()
