from __future__ import annotations

import ast
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch


class GuidesLazyUltimeRuntimeTests(unittest.TestCase):
    def test_guides_constructor_does_not_build_manual_runtime(self) -> None:
        path = Path("app/modules/encyclopedia/views/guides_view.py")
        tree = ast.parse(path.read_text(encoding="utf-8"))
        guides_class = next(
            node
            for node in tree.body
            if isinstance(node, ast.ClassDef) and node.name == "GuidesView"
        )
        init = next(
            node
            for node in guides_class.body
            if isinstance(node, ast.FunctionDef) and node.name == "__init__"
        )
        init_source = ast.unparse(init)
        self.assertNotIn("GuideUltimeManualRuntimeService(", init_source)
        self.assertNotIn("SharedGuideManualView(", init_source)
        self.assertNotIn("_build_manual_route_reader(", init_source)

    def test_one_lazy_builder_keeps_the_two_runtime_policies(self) -> None:
        from app.modules.encyclopedia.services import guide_auto_validation_contract as validation
        from app.modules.encyclopedia.services import guide_ultime_manual_runtime_service as runtime
        from app.modules.encyclopedia.views.guides_view import GuidesView
        from app.modules.encyclopedia.views.manual_route_guides_view import ManualRouteGuidesView

        self.assertIs(ManualRouteGuidesView.ensure_guide_ultime_view, GuidesView.ensure_guide_ultime_view)
        for view_class, compact in ((GuidesView, False), (ManualRouteGuidesView, True)):
            with self.subTest(compact=compact):
                service = Mock(available=True, cards=[])
                view = Mock()
                owner = SimpleNamespace(
                    _compact_guide_ultime_runtime=view_class._compact_guide_ultime_runtime,
                    guide_ultime_view=None, guide_ultime_service=None,
                    quest_progress_service=object(), achievement_progress_service=object(),
                    guide_progress_service=object(), quest_provider=object(),
                    achievement_provider=object(), stack=Mock(),
                    _build_manual_route_reader=Mock(return_value=view),
                    _on_guide_ultime_quest_progress_changed=Mock(),
                    _refresh_guide_ultime_home_labels=Mock(),
                )
                with (
                    patch.object(runtime, "GuideUltimeManualRuntimeService", return_value=service) as build,
                    patch.object(validation, "build_route_auto_validation_contract") as validate,
                ):
                    self.assertIs(view_class.ensure_guide_ultime_view(owner), view)
                    self.assertIs(view_class.ensure_guide_ultime_view(owner), view)
                    build.assert_called_once_with(
                        owner.quest_progress_service, owner.achievement_progress_service,
                        owner.guide_progress_service, quest_provider=owner.quest_provider,
                        autoload=False, cache_manual_bundle=not compact, compact_runtime=compact,
                    )
                    if compact:
                        validate.assert_not_called()
                        self.assertIsNone(service.auto_validation_contract)
                    else:
                        validate.assert_called_once_with([], achievement_provider=owner.achievement_provider)
                        self.assertIs(service.auto_validation_contract, validate.return_value)
                owner._build_manual_route_reader.assert_called_once_with(service)
                owner.stack.addWidget.assert_called_once_with(view)

    def test_regular_guide_forwarding_preserves_scroll(self) -> None:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PySide6.QtWidgets import QApplication

        from app.modules.encyclopedia.views.guides_view import GuidesView
        from app.modules.encyclopedia.views.manual_route_guides_view import ManualRouteGuidesView

        app = QApplication.instance() or QApplication([])
        with tempfile.TemporaryDirectory() as directory:
            paths = Path(directory)
            view = ManualRouteGuidesView(
                lambda _status: None, defer_runtime=True,
                quest_progress_path=paths / "quests.json",
                achievement_progress_path=paths / "achievements.json",
                guide_progress_path=paths / "guides.json",
                profile_path=paths / "profile.json",
                client_index_path=paths / "clients.json",
            )
            try:
                with patch.object(GuidesView, "show_guide_overview") as show:
                    view.show_guide_overview("dofus_turquoise", preserve_scroll=True)
                    show.assert_called_once_with("dofus_turquoise", preserve_scroll=True)
            finally:
                view.deleteLater()
                app.processEvents()


if __name__ == "__main__":
    unittest.main()
