from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
LEGACY = ROOT / "app/modules/encyclopedia/views/guide_ultime_manual_view.py"
SHARED = ROOT / "app/modules/encyclopedia/views/shared_manual_guide_view.py"


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
    assert "return SharedGuideManualView(*args, **kwargs)" in source
    assert "return SharedGuideManualCard(*args, **kwargs)" in source
