from __future__ import annotations

import ast
from pathlib import Path


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


def test_only_shared_guide_classes_own_visual_composition() -> None:
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


def test_legacy_names_redirect_to_shared_renderer() -> None:
    source = LEGACY.read_text(encoding="utf-8")
    assert "return SharedGuideManualView.__new__(SharedGuideManualView)" in source
    assert "return SharedGuideManualCard.__new__(SharedGuideManualCard)" in source


def test_sylvestre_has_no_dedicated_ui_file_or_class() -> None:
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


def test_shared_renderer_is_guide_agnostic() -> None:
    """The concrete renderer must not know whether it renders Lanyel or Guide Succès."""
    source = SHARED.read_text(encoding="utf-8").casefold()
    assert "dofus_sylvestre" not in source
    assert "lanyel" not in source
    assert "sylvestre" not in source


def test_both_sources_construct_the_exact_same_shared_view() -> None:
    source = ROUTER.read_text(encoding="utf-8")
    assert 'CATALOG_MANUAL_GUIDE_IDS = frozenset({"dofus_sylvestre"})' in source
    assert source.count("view = SharedGuideManualView(") == 2
    assert "GuideUltimeManualRuntimeService(" in source
    assert "GuideCatalogManualRuntimeService(" in source


def test_sylvestre_has_no_dedicated_qss_or_style_selector() -> None:
    for path in UI_STYLES.rglob("*.py") if UI_STYLES.exists() else ():
        source = path.read_text(encoding="utf-8").casefold()
        assert "dofus_sylvestre" not in source, path
        assert "lanyel" not in source, path
        assert "sylvestre" not in source, path
