from __future__ import annotations

import ast
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
VIEWS = ROOT / "app/modules/encyclopedia/views"
WIDGETS = ROOT / "app/modules/encyclopedia/widgets"
UI_STYLES = ROOT / "app/ui/styles"
LEGACY = VIEWS / "guide_ultime_manual_view.py"
SHARED = VIEWS / "shared_manual_guide_view.py"
ROUTER = VIEWS / "manual_route_guides_view.py"


def _class_methods(path: Path, class_name: str) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            return {
                child.name
                for child in node.body
                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef))
            }
    raise AssertionError(f"Missing class {class_name} in {path}")



class SharedGuideSingleRendererContractTests(unittest.TestCase):
    def test_only_shared_guide_classes_own_visual_composition(self) -> None:
        legacy_view = _class_methods(LEGACY, "GuideUltimeManualView")
        legacy_card = _class_methods(LEGACY, "GuideUltimeManualCard")
        shared_view = _class_methods(SHARED, "SharedGuideManualView")
        shared_card = _class_methods(SHARED, "SharedGuideManualCard")

        assert "_build_ui" not in legacy_view
        assert "_render_window" not in legacy_view
        assert "__init__" not in legacy_card
        assert "_add_line_section" not in legacy_card

        assert "_build_ui" in shared_view
        assert "_render_window" in shared_view
        assert "__init__" in shared_card
        assert "_add_line_section" in shared_card


    def test_legacy_names_redirect_to_shared_renderer(self) -> None:
        source = LEGACY.read_text(encoding="utf-8")
        assert "return SharedGuideManualView.__new__(SharedGuideManualView)" in source
        assert "return SharedGuideManualCard.__new__(SharedGuideManualCard)" in source


    def test_sylvestre_has_no_dedicated_ui_file_or_class(self) -> None:
        """Lanyel may own route data/services, never its own UI implementation."""
        for base in (VIEWS, WIDGETS, UI_STYLES):
            if not base.exists():
                continue
            for path in base.rglob("*.py"):
                filename = path.name.casefold()
                assert "lanyel" not in filename, path
                assert "sylvestre" not in filename, path

                tree = ast.parse(path.read_text(encoding="utf-8"))
                for node in ast.walk(tree):
                    if not isinstance(node, ast.ClassDef):
                        continue
                    class_name = node.name.casefold()
                    assert "lanyel" not in class_name, f"{path}: {node.name}"
                    assert "sylvestre" not in class_name, f"{path}: {node.name}"


    def test_shared_renderer_is_guide_agnostic(self) -> None:
        """The concrete renderer must not know whether it renders Lanyel or Guide Succès."""
        source = SHARED.read_text(encoding="utf-8").casefold()
        assert "dofus_sylvestre" not in source
        assert "lanyel" not in source
        assert "sylvestre" not in source


    def test_every_manual_and_imported_source_constructs_the_same_shared_view(self) -> None:
        source = ROUTER.read_text(encoding="utf-8")
        assert 'CATALOG_MANUAL_GUIDE_IDS = frozenset({"dofus_sylvestre"})' in source
        # Guide Succès, catalogue optimisé et every authorized imported source
        # use the exact same renderer; an extra UI implementation is forbidden.
        assert source.count("view = SharedGuideManualView(") == 3
        assert "ensure_imported_source_manual_view" in source
        assert "ImportedSourceManualRuntimeService" in source
        assert "GuideUltimeManualRuntimeService(" in source
        assert "GuideCatalogManualRuntimeService(" in source


    def test_all_authorized_ganymede_entrypoints_use_indexed_guide_header(self) -> None:
        """Both trusted continuous cutovers and imported manual guides share
        the indexed Guide header controls; metadata-only rows stay disabled."""
        source = ROUTER.read_text(encoding="utf-8")
        continuous_router = (VIEWS / "guides_view.py").read_text(encoding="utf-8")
        continuous = (VIEWS / "guide_continuous_route_panel.py").read_text(encoding="utf-8")
        shared = SHARED.read_text(encoding="utf-8")
        assert "SharedGuideManualView(" in source
        assert "ContinuousGuideRoutePanel(" in continuous_router
        assert 'replacement_status") == "TRUSTED_SOURCE_STEPS"' in continuous_router
        for renderer in (continuous, shared):
            for role in ("GuideCompactHeader", "GuideGlobalProgress",
                         "GuideParticipantsButton", "GuideCompactPreparationProgress"):
                assert role in renderer, (role, renderer[:80])
        # Drawer geometry/arrow behaviour now lives in the indexed shared
        # component instead of duplicating an object name in every renderer.
        controls = (ROOT / "app/ui/components.py").read_text(encoding="utf-8")
        assert 'self.setObjectName("GuideMetricDropdown")' in controls
        assert "AtlasGuideDisclosure(" in shared
        assert "GuideMetricDropdown" in continuous
        assert "background" not in (VIEWS / "guide_continuous_route_panel.py").name

    def test_shared_reader_shows_bounded_read_ahead_and_complete_summary(self) -> None:
        """One active step for validation, plus two scrollable read-ahead steps."""
        shared = SHARED.read_text(encoding="utf-8")
        preview = (VIEWS / "ganymede_guide_shell.py").read_text(encoding="utf-8")
        continuous = (VIEWS / "guide_continuous_route_panel.py").read_text(
            encoding="utf-8"
        )
        generated = (VIEWS / "guide_ultime_universal_view.py").read_text(
            encoding="utf-8"
        )

        assert "READING_WINDOW_SIZE = 3" in shared
        assert "for number in self._reading_step_range(index):" in shared
        assert "self._sync_validation_control(widget.page_check" in shared
        assert "widget.page_check.hide()" in shared
        assert "for index, card in enumerate(self.service.cards):" in shared
        assert "self.summary_list.addItem(item)" in shared
        assert 'label = f"{index + 1}. {title}"' in shared
        # The metadata pilot MUST NOT have its own Qt sheet loop; it must
        # inherit the very same source layout as every authorized import.
        assert "super()._render_window(reset_scroll=reset_scroll)" in preview
        assert "for number in self._reading_step_range(index):" not in preview
        assert "SharedGuideManualCard(" not in preview
        assert "_configure_imported_sheet_layout(" in shared
        assert "self._review_end_index = self.view_index + self.rendered_card_count" in preview
        assert "pair_fills_gap" not in preview
        assert "for i, row in enumerate(self.rows, 1)" in continuous
        assert "self.title_label.setText(str(row.get(" in continuous
        assert "self.rendered_card_count = 1" in generated

    def test_all_authored_source_pages_share_one_to_one_universal_policy(self) -> None:
        """No Cawotte-specific page composition or author-specific styling."""
        shared = SHARED.read_text(encoding="utf-8")
        shell = (VIEWS / "ganymede_guide_shell.py").read_text(encoding="utf-8")
        stylesheet = (ROOT / "app/ui/theme.py").read_text(encoding="utf-8")
        assert "count = 1 if source_sheet else self.READING_WINDOW_SIZE" in shared
        assert 'card.get("manual_review_only") is True' in shared
        assert "self._configure_imported_sheet_layout(widget, card)" in shared
        assert "widget.page_check.hide()" in shared
        assert 'self._continuous_source' in shared
        assert "GuideManualSourceReadingSection" not in shell
        assert "QFrame#GuideManualSheet" not in shell
        assert "#GuideManualSheet" in stylesheet
        assert "GuideManualSourceReadingSection" not in stylesheet

    def test_sylvestre_has_no_dedicated_qss_or_style_selector(self) -> None:
        for path in UI_STYLES.rglob("*.py") if UI_STYLES.exists() else ():
            source = path.read_text(encoding="utf-8").casefold()
            assert "dofus_sylvestre" not in source, path
            assert "lanyel" not in source, path
            assert "sylvestre" not in source, path
