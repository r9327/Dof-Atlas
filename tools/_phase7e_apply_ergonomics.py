from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
VIEW = ROOT / "app/modules/encyclopedia/views/guide_ultime_manual_view.py"
RUNTIME = ROOT / "app/modules/encyclopedia/services/guide_ultime_manual_runtime_service.py"
NAV_TEST = ROOT / "tests/test_guide_ultime_manual_ui_navigation.py"


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if old not in text:
        raise SystemExit(f"patch anchor missing: {label}")
    return text.replace(old, new, 1)


def patch_view() -> None:
    text = VIEW.read_text(encoding="utf-8")
    text = replace_once(text, "import re\nfrom typing import Any\n", "import re\nfrom typing import Any\nfrom urllib.parse import quote, unquote\n", "view urllib import")
    text = replace_once(
        text,
        "from PySide6.QtCore import QTimer, Signal, Qt\n",
        "from PySide6.QtCore import QTimer, Signal, Qt\nfrom PySide6.QtGui import QCursor\n",
        "view cursor import",
    )
    text = replace_once(
        text,
        "from PySide6.QtWidgets import (\n    QCheckBox,\n",
        "from PySide6.QtWidgets import (\n    QApplication,\n    QCheckBox,\n",
        "view QApplication import",
    )
    text = replace_once(
        text,
        "    QToolButton,\n    QVBoxLayout,\n",
        "    QToolButton,\n    QToolTip,\n    QVBoxLayout,\n",
        "view QToolTip import",
    )
    text = replace_once(
        text,
        "            button.setToolTip(\n                f\"{name}\\nOuvrir la fiche canonique dans l'onglet Quêtes.\"\n            )\n",
        "            button.setToolTip(name)\n",
        "compact quest tooltip",
    )
    text = replace_once(
        text,
        "            line.setTextInteractionFlags(Qt.TextSelectableByMouse)\n            row_layout.addWidget(line, 1)\n",
        "            line.setTextInteractionFlags(Qt.TextSelectableByMouse | Qt.LinksAccessibleByMouse)\n            line.setOpenExternalLinks(False)\n            line.linkActivated.connect(self._copy_item_link)\n            row_layout.addWidget(line, 1)\n",
        "resource link interaction",
    )
    text = replace_once(
        text,
        "                add_span(match.start(), match.end(), \"resource\")\n",
        "                add_span(match.start(), match.end(), f\"resource:{quote(name, safe='')}\")\n",
        "resource span payload",
    )
    text = replace_once(
        text,
        "            elif kind == \"resource\":\n                rendered.append(f'<span style=\"color:{RESOURCE_COLOR};\"><b>{value}</b></span>')\n            else:\n",
        "            elif kind.startswith(\"resource:\"):\n                payload = kind.split(\":\", 1)[1]\n                rendered.append(\n                    f'<a href=\"copy-item:{payload}\" style=\"color:{RESOURCE_COLOR}; text-decoration:none;\"><b>{value}</b></a>'\n                )\n            else:\n",
        "resource anchor rendering",
    )
    insertion = '''\n    def _copy_item_link(self, href: str) -> None:\n        value = str(href or \"\")\n        if not value.startswith(\"copy-item:\"):\n            return\n        item_name = unquote(value.split(\":\", 1)[1]).strip()\n        if not item_name:\n            return\n        QApplication.clipboard().setText(item_name)\n        QToolTip.showText(QCursor.pos(), f\"Copié : {item_name}\", self)\n\n'''
    anchor = "    @staticmethod\n    def _resource_regex(name: str) -> re.Pattern[str]:\n"
    text = replace_once(text, anchor, insertion + anchor, "copy item handler")
    VIEW.write_text(text, encoding="utf-8")


def patch_runtime() -> None:
    text = RUNTIME.read_text(encoding="utf-8")
    text = replace_once(
        text,
        "from app.modules.encyclopedia.services.guide_ultime_manual_conditions import GuideUltimeManualConditionsMixin\n",
        "from app.modules.encyclopedia.services.guide_route_detour_audit import find_avoidable_revisits\nfrom app.modules.encyclopedia.services.guide_ultime_manual_conditions import GuideUltimeManualConditionsMixin\n",
        "detour import",
    )
    text = replace_once(
        text,
        "        self._link_next_cards(cards)\n\n        self.manual_audit_data = {\n",
        "        self._link_next_cards(cards)\n        avoidable_revisits = find_avoidable_revisits(cards)\n\n        self.manual_audit_data = {\n",
        "detour calculation",
    )
    text = replace_once(
        text,
        "            \"unsupported_stage_fields\": unsupported_by_chapter,\n        }\n",
        "            \"unsupported_stage_fields\": unsupported_by_chapter,\n            \"avoidable_revisit_count\": len(avoidable_revisits),\n            \"avoidable_revisits\": avoidable_revisits,\n        }\n",
        "detour audit payload",
    )
    RUNTIME.write_text(text, encoding="utf-8")


def patch_navigation_test() -> None:
    text = NAV_TEST.read_text(encoding="utf-8")
    text = replace_once(
        text,
        "            self.assertIn(\"Quête canonique test\", button.toolTip())\n            self.assertIn(\"fiche canonique\", button.toolTip())\n",
        "            self.assertEqual(button.toolTip(), \"Quête canonique test\")\n",
        "quest tooltip expectation",
    )
    NAV_TEST.write_text(text, encoding="utf-8")


if __name__ == "__main__":
    patch_view()
    patch_runtime()
    patch_navigation_test()
