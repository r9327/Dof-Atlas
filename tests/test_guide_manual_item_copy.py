from __future__ import annotations

import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QLabel

from app.modules.encyclopedia.views.guide_ultime_manual_view import GuideUltimeManualCard


ITEM_NAME = "Plume de Piou"


class _Service:
    quest_provider = None

    def manual_sections_for_card(self, _character_key, _card):
        return {
            "now": [
                {
                    "position": "[1, 2]",
                    "text": f"Apporter 3 {ITEM_NAME}s au PNJ",
                    "kind": "action",
                }
            ]
        }


class GuideManualItemCopyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def test_resource_name_is_clickable_and_copies_canonical_item_name(self) -> None:
        card = {
            "manual_stage_id": "stage-items",
            "destination": "[1, 2]",
            "manual_title": "Étape objets",
            "manual_resource_names": [ITEM_NAME],
        }
        widget = GuideUltimeManualCard(_Service(), "", card, 0)
        line = widget.findChild(QLabel, "GuideManualLine")
        self.assertIsNotNone(line)
        self.assertIn("copy-item:", line.text())

        QApplication.clipboard().clear()
        line.linkActivated.emit("copy-item:Plume%20de%20Piou")
        self.assertEqual(QApplication.clipboard().text(), ITEM_NAME)


if __name__ == "__main__":
    unittest.main()
