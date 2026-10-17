from __future__ import annotations

"""Data-driven review lenses for the AI control protocol.

Guardians select concerns and evidence from an existing Agent plan.  They do
not execute scanners, duplicate tests, lower Atlas Integrity, or certify work.
"""

from typing import Any, Iterable


PACKS: tuple[dict[str, Any], ...] = (
    {
        "id": "core", "always": True,
        "concerns": ("ownership", "syntax", "targeted_tests", "integrity_policy"),
    },
    {
        "id": "ui",
        "scopes": ("shared_ui", "windows_qt_runtime", "home", "organizer", "equipment",
                   "encyclopedia_shell", "encyclopedia_quests", "encyclopedia_achievements",
                   "encyclopedia_guide"),
        "prefixes": ("app/ui/", "app/pages/", "app/windows/", "app/modules/encyclopedia/views/"),
        "concerns": ("visual_scenario", "qt_lifecycle", "keyboard_navigation", "theme_consistency"),
    },
    {
        "id": "quests_guides",
        "scopes": ("encyclopedia_quests", "encyclopedia_achievements", "encyclopedia_guide"),
        "prefixes": ("data/routes/", "app/quest_catalog.py"),
        "concerns": ("route_contract", "prerequisites", "progress_roundtrip", "content_integrity"),
    },
    {
        "id": "network",
        "scopes": ("network_capture",),
        "prefixes": ("app/network/", "app/ui/network_bridge.py"),
        "concerns": ("protocol_identity", "session_lifecycle", "reconnect", "capture_boundaries"),
    },
    {
        "id": "persistence",
        "scopes": ("persistence_identity",),
        "prefixes": ("data/local/", "app/core/json_store.py", "app/core/progress_coordinator.py"),
        "contains": ("progress_service.py", "migration"),
        "concerns": ("backward_compatibility", "atomic_write", "migration", "user_data_preservation"),
    },
    {
        "id": "performance",
        "scopes": ("startup_lifecycle", "shared_ui", "encyclopedia_shell", "world_scan"),
        "rule_markers": ("PERFORMANCE_GUARDRAILS.md",),
        "groups": ("TIMING_PERFORMANCE",),
        "concerns": ("lazy_loading", "startup_budget", "bounded_work", "memory_when_required"),
    },
    {
        "id": "release",
        "scopes": ("quality_ci",),
        "prefixes": (".github/workflows/", "packaging/", "installer/"),
        "contains": ("release", "distribution"),
        "concerns": ("exact_sha", "artifact_publication", "install_smoke", "independent_attestation"),
    },
    {
        "id": "security",
        "scopes": ("network_capture", "input_hotkeys", "windows_qt_runtime"),
        "prefixes": ("app/network/", "app/input/", "app/windows/"),
        "contains": ("credential", "secret", "permission"),
        "concerns": ("trust_boundary", "untrusted_input", "secret_hygiene", "least_privilege"),
    },
    {
        "id": "simplicity",
        "suffixes": (".py",),
        "concerns": ("bounded_diff", "reuse_before_new_code", "duplication", "deletion_requires_proof"),
    },
)


def _unique(values: Iterable[str]) -> list[str]:
    return list(dict.fromkeys(str(value) for value in values if value))


def _reasons(pack: dict[str, Any], *, paths: list[str], scopes: set[str],
             rules: set[str], groups: set[str]) -> list[str]:
    reasons: list[str] = []
    matched_scopes = sorted(scopes.intersection(pack.get("scopes", ())))
    if matched_scopes:
        reasons.append("scopes:" + ",".join(matched_scopes))
    matched_groups = sorted(groups.intersection(pack.get("groups", ())))
    if matched_groups:
        reasons.append("policy_groups:" + ",".join(matched_groups))
    for marker in pack.get("rule_markers", ()):
        if any(rule == marker or rule.endswith("/" + marker) for rule in rules):
            reasons.append("rule:" + marker)
    matched_paths = []
    for path in paths:
        if (any(path.startswith(prefix) for prefix in pack.get("prefixes", ()))
                or any(token.casefold() in path.casefold()
                       for token in pack.get("contains", ()))
                or any(path.endswith(suffix) for suffix in pack.get("suffixes", ()))):
            matched_paths.append(path)
    if matched_paths:
        reasons.append("paths:" + ",".join(matched_paths[:4]))
    if pack.get("always"):
        reasons.append("baseline")
    return reasons


def guardian_plan(plan: dict[str, Any]) -> dict[str, Any]:
    """Select compact guardian lenses while reusing one test/validation batch."""
    paths = _unique(plan.get("paths", []))
    scopes = set(_unique(plan.get("scopes", [])))
    rules = set(_unique(plan.get("rules", [])))
    groups = set(_unique(plan.get("required_groups", [])))
    selected = []
    for pack in PACKS:
        reasons = _reasons(pack, paths=paths, scopes=scopes, rules=rules, groups=groups)
        if not reasons:
            continue
        selected.append({
            "id": pack["id"],
            "status": "PLANNED",
            "reasons": reasons,
            "concerns": list(pack["concerns"]),
        })
    tests = _unique(plan.get("execution_tests", []))
    return {
        "schema_version": 1,
        "status": "PLANNED" if selected else "REVIEW",
        "selected": selected,
        "selected_ids": [row["id"] for row in selected],
        "execution": {
            "test_modules": tests,
            "test_processes": 1 if tests else 0,
            "validation_command": list(plan.get("validation_command", [])),
            "deduplicated": True,
            "extra_full_run": False,
        },
        "limits": (
            "Guardians are review lenses over the canonical Agent plan. They do not "
            "add PASS results, replace domain scenarios, or weaken Atlas Integrity."
        ),
    }
