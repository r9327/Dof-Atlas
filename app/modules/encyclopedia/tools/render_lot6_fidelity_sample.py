from __future__ import annotations

import os
import tempfile
import time
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QTWEBENGINE_CHROMIUM_FLAGS", "--disable-gpu")

from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from app.constants import ROOT_DIR
from app.modules.encyclopedia.providers import AchievementProvider, GuideProvider, QuestProvider
from app.modules.encyclopedia.services import QuestGraphService, QuestProgressService
from app.modules.encyclopedia.widgets.quest_detail_view import QuestDetailView


def main() -> int:
    app = QApplication.instance() or QApplication([])
    quest_provider = QuestProvider()
    achievement_provider = AchievementProvider(quest_provider=quest_provider)
    guide_provider = GuideProvider(
        quest_provider=quest_provider,
        achievement_provider=achievement_provider,
    )
    graph = QuestGraphService(quest_provider, guide_provider, achievement_provider)
    output_dir = ROOT_DIR / "artifacts"
    output_dir.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory() as tmp:
        view = QuestDetailView(
            quest_provider,
            graph,
            QuestProgressService(Path(tmp) / "progress.json"),
            achievement_provider=achievement_provider,
            guide_provider=guide_provider,
        )
        view.resize(980, 720)
        view.show()
        for quest_id, filename in (
            (1760, "lot6_fidelity_documentary_render.png"),
            (2464, "lot6_fidelity_colonie_render.png"),
        ):
            if not view.show_quest(quest_id):
                raise RuntimeError(f"Quest {quest_id} is unavailable")
            view.center_scroll.verticalScrollBar().setValue(0)
            for _ in range(60):
                app.processEvents()
                time.sleep(0.05)
            labels = view.findChildren(type(view.title_label), 'QuestSolutionImage')
            print('IMAGE LABELS:', len(labels))
            for i, label in enumerate(labels):
                pm = label.pixmap()
                print(i, 'TEXT=', repr(label.text()), 'SOURCE_NULL=', label.source.isNull(), 'PIXMAP=', bool(pm and not pm.isNull()), 'PATH=', label._image_path)
            if not view.grab().save(str(output_dir / filename)):
                raise RuntimeError(f"Could not save {filename}")
        view.close()
        view.deleteLater()
        app.processEvents()

    print(output_dir / "lot6_fidelity_documentary_render.png")
    print(output_dir / "lot6_fidelity_colonie_render.png")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


