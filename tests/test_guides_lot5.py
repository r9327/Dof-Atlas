from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QTWEBENGINE_CHROMIUM_FLAGS", "--disable-gpu")

from PySide6.QtWidgets import QApplication, QLabel, QToolButton

from app.modules.encyclopedia.providers import GuideProvider
from app.modules.encyclopedia.services.guide_quest_view_model import guide_rewards, reward_label
from app.modules.encyclopedia.views.guides_view import CollapsibleInfoSection, GuidesView


class GuidesLot5Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def make_view(self, root: Path, navigate_callback=None) -> GuidesView:
        view = GuidesView(
            lambda _text: None,
            quest_progress_path=root / "quest_progress.json",
            achievement_progress_path=root / "achievement_progress.json",
            guide_progress_path=root / "guide_progress.json",
            navigate_callback=navigate_callback,
        )
        view.set_character_key("character:1")
        return view

    def test_full_guide_contains_every_active_dofus_quest_once(self) -> None:
        provider = GuideProvider()
        guides = provider.load_all()
        full = provider.get_by_id("guide_complet")
        self.assertIsNotNone(full)
        assert full is not None

        expected = {
            quest_id
            for guide in guides
            if guide.category == "dofus"
            for quest_id in guide.quest_ids
        }
        self.assertTrue(expected.issubset(set(full.quest_ids)))
        self.assertEqual(len(full.quest_ids), len(set(full.quest_ids)))
        self.assertEqual(len(full.quest_ids), 1149)

    def test_dofus_global_rewards_include_quest_xp_kamas_and_items(self) -> None:
        provider = GuideProvider()
        guide = provider.get_by_id("dofus_cawotte")
        self.assertIsNotNone(guide)
        assert guide is not None
        catalog = provider.quest_provider.get_catalog()

        rewards = guide_rewards(
            guide,
            provider.achievement_provider,
            (
                catalog.by_id[int(step.entity_id)]
                for step in guide.required_steps
                if step.step_type == "quest" and step.entity_id in catalog.by_id
            ),
        )
        labels = [reward_label(reward) for reward in rewards]

        self.assertEqual(labels[0], "Dofus Cawotte")
        self.assertTrue(any(label.endswith(" XP") for label in labels))
        self.assertTrue(any(label.endswith(" Kamas") for label in labels))
        self.assertGreater(len(rewards), 12)

    def test_live_quest_progress_updates_step_and_global_counts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            view = self.make_view(Path(tmp))
            view.select_guide("dofus_cawotte")
            self.app.processEvents()

            guide = view.current_guide()
            self.assertIsNotNone(guide)
            assert guide is not None
            _done, total, _state = view.guide_progress_tuple(guide)
            self.assertEqual(view.detail_header_progress.text(), f"0/{total}")
            center = view.findChild(QLabel, "GuideSeriesHeaderTitle")
            self.assertIsNotNone(center)
            assert center is not None
            self.assertIn("0/", center.text())
            tree_labels = [
                label.text()
                for label in view.findChildren(QLabel)
                if label.objectName() in {"GuideTreePartText", "GuideTreeChildText"}
            ]
            # Dofus guides intentionally devote the left column to the compact
            # overview; the selected series carries the live progress count.
            self.assertEqual(tree_labels, [])

            quest_id = next(
                int(step.entity_id)
                for step in guide.required_steps
                if step.step_type == "quest" and step.entity_id is not None
            )
            view.set_quest_completed(quest_id, True)
            self.app.processEvents()
            self.assertEqual(view.detail_header_progress.text(), f"1/{total}")
            self.assertIn("1/", center.text())
            view.deleteLater()
            self.app.processEvents()

    def test_guide_prerequisites_collapse_and_quest_stays_in_guides(self) -> None:
        routed: list[dict[str, object]] = []

        def navigate(entity_type: str, entity_id: int, **context) -> bool:
            routed.append({"type": entity_type, "id": entity_id, **context})
            return True

        with tempfile.TemporaryDirectory() as tmp:
            view = self.make_view(Path(tmp), navigate_callback=navigate)
            view.select_guide("dofus_cawotte")
            self.app.processEvents()

            sections = view.findChildren(CollapsibleInfoSection)
            self.assertTrue(sections)
            self.assertTrue(sections[0].body.isHidden())
            chevron = sections[0].findChild(QToolButton, "GuideChevronButton")
            self.assertIsNotNone(chevron)
            assert chevron is not None
            self.assertFalse(chevron.isHidden())
            self.assertEqual(chevron.text(), "▼")
            chevron.click()
            self.assertFalse(sections[0].body.isHidden())
            self.assertEqual(chevron.text(), "▲")

            quest_id = next(
                int(step.entity_id)
                for step in view.current_guide().required_steps
                if step.step_type == "quest" and step.entity_id is not None
            )
            self.assertTrue(view.show_quest_detail(quest_id))
            self.assertEqual(view.state, view.QUEST_DETAIL)
            self.assertFalse(view.detail_header.isHidden())
            self.assertIs(view.detail_stack.currentWidget(), view.quest_detail_view)
            self.assertIs(view.stack.currentWidget(), view.detail_page)

            progress_before = view.detail_header_progress.text()
            view.quest_detail_view.toggle_completed()
            self.app.processEvents()
            self.assertEqual(view.state, view.QUEST_DETAIL)
            self.assertIs(view.detail_stack.currentWidget(), view.quest_detail_view)
            self.assertNotEqual(view.detail_header_progress.text(), progress_before)

            view.open_prerequisite_from_guide(827)
            self.assertTrue(routed)
            self.assertEqual(routed[-1]["source"], "guide_prerequisite")
            view.deleteLater()
            self.app.processEvents()


if __name__ == "__main__":
    unittest.main()
