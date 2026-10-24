from __future__ import annotations

"""Independently reviewable, closed-world HIGH -> SMART canary.

This is routing eligibility, not PASS, FULL, release or phase certification.
Unknown sources, mixed application diffs, deletions, policies and missing test
owners all retain the historical mandatory FULL. Do not add globs here.
"""
from pathlib import Path

HIGH_SOURCE = "app/modules/encyclopedia/services/guide_progress_service.py"
REQUIRED_TESTS = frozenset({
    "tests.test_guide_progress_persistence",
    "tests.test_progress_cross_surface_reload",
})
ALLOWED_TEST_PATHS = frozenset(
    str(Path(*module.split(".")).with_suffix(".py")) for module in REQUIRED_TESTS
)
POLICY_ID = "high-smart-bounded-guide-progress-v1"


def bounded_paths(paths, *, deleted=()) -> bool:
    """Only one audited HIGH owner plus its exact tests and harmless metadata."""
    if deleted or not paths or any(not isinstance(path, str) for path in paths):
        return False
    selected = set(paths)
    if len(selected) != len(paths) or HIGH_SOURCE not in selected:
        return False
    for path in selected - {HIGH_SOURCE} - ALLOWED_TEST_PATHS - {".ai/context_index.json"}:
        if not (path.startswith("docs/") and path.endswith(".md")
                and ".." not in path.split("/") and "\\" not in path):
            return False
    return True


def eligible(root: Path | None, paths, *, deleted=()) -> bool:
    """A missing checkout/mandatory test can never downscope."""
    if root is None or not bounded_paths(paths, deleted=deleted):
        return False
    root = root.resolve()
    for relative in (HIGH_SOURCE, *(str(Path(*m.split(".")).with_suffix(".py"))
                                    for m in REQUIRED_TESTS)):
        target = root / relative
        if not target.is_file() or target.is_symlink():
            return False
    return True
