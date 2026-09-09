from __future__ import annotations

import unittest
from pathlib import Path

from tests.source_guardrails import read_source


ROOT = Path(__file__).resolve().parents[1]


class CleanFoundationGuardrailsTests(unittest.TestCase):
    def _text(self, relative: str) -> str:
        return read_source(ROOT / relative)

    def test_legacy_quest_progress_mutators_stay_inside_catalog_compatibility(self) -> None:
        forbidden = ("set_quest_done", "set_quest_item_done")
        violations: list[str] = []
        for path in (ROOT / "app").rglob("*.py"):
            relative = path.relative_to(ROOT).as_posix()
            if relative == "app/quest_catalog.py":
                continue
            text = read_source(path)
            for name in forbidden:
                if name in text:
                    violations.append(f"{relative}:{name}")
        self.assertEqual([], violations, f"Mutateurs quest_catalog legacy hors compatibilité: {violations}")

    def test_pages_and_shared_widgets_do_not_depend_on_guide_legacy_monolith(self) -> None:
        existing_baseline: set[str] = set()
        violations: list[str] = []
        roots = (ROOT / "app/pages", ROOT / "app/modules/encyclopedia/widgets")
        for root in roots:
            for path in root.rglob("*.py"):
                if "guides_view_legacy" in read_source(path):
                    violations.append(path.relative_to(ROOT).as_posix())
        self.assertEqual(
            existing_baseline,
            set(violations),
            "Nouvelle dependance UI directe au Guide legacy interdite; "
            f"baseline={sorted(existing_baseline)}, trouve={sorted(violations)}",
        )

    def test_progress_compatibility_saves_reject_stale_generations(self) -> None:
        for relative in (
            "app/modules/encyclopedia/services/quest_progress_service.py",
            "app/modules/encyclopedia/services/guide_progress_service.py",
            "app/modules/encyclopedia/services/serialized_achievement_progress_service.py",
        ):
            source = self._text(relative)
            self.assertIn("self._seen_generation != self._coordinator.generation", source, relative)
            self.assertIn("raise RuntimeError", source, relative)

    def test_mutable_progress_persistence_uses_common_json_store(self) -> None:
        quest_catalog = self._text("app/quest_catalog.py")
        guide = self._text("app/modules/encyclopedia/services/guide_progress_service.py")
        achievement = self._text("app/modules/encyclopedia/services/serialized_achievement_progress_service.py")

        self.assertIn("read_json_resilient", quest_catalog)
        self.assertIn("write_json_atomic", quest_catalog)
        self.assertIn("read_json_resilient", guide)
        self.assertIn("write_json_atomic", guide)
        self.assertIn("read_json_resilient", achievement)
        self.assertIn("write_json_atomic", achievement)

    def test_shared_quest_item_row_style_lives_in_ui_styles(self) -> None:
        widget = self._text("app/modules/encyclopedia/widgets/quest_item_row.py")
        style = self._text("app/ui/styles/quests.py")
        self.assertIn("quest_item_row_stylesheet", widget)
        self.assertNotIn("_ITEM_ROW_STYLE", widget)
        self.assertIn("_QUEST_ITEM_ROW_STYLE", style)
        self.assertIn("@PANEL_ACTIVE", style)
        self.assertIn("@GREEN_BORDER", style)

    def test_manual_ocre_registry_is_a_runtime_consumer_not_dead_manifest_data(self) -> None:
        conditions = self._text("app/modules/encyclopedia/services/guide_ultime_manual_conditions.py")
        registry = self._text("app/modules/encyclopedia/services/guide_ultime_ocre_registry.py")
        self.assertIn("load_ocre_capture_registry", conditions)
        self.assertIn("_append_ocre_policy_lines", conditions)
        self.assertIn("capture_transition", conditions)
        self.assertIn("ocre_capture_lines", registry)


if __name__ == "__main__":
    unittest.main()
