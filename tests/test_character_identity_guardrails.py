from __future__ import annotations

import ast
import re
import unittest
from pathlib import Path

from tests.source_guardrails import parse_source, runtime_python_files, string_constants


ROOT = Path(__file__).resolve().parents[1]
LEGACY_SLOT_COMPATIBILITY_FILES = {
    "app/network/character_resolver.py",
}
KNOWN_SLOT_BUSINESS_DEBT: tuple[str, ...] = ()


def _slot_identity_literal(value: str) -> bool:
    return bool(re.search(r"(?<![A-Za-z])slot:", value, flags=re.IGNORECASE))


class CharacterIdentityGuardrailTests(unittest.TestCase):
    def test_only_legacy_resolver_may_reference_slot_business_keys(self) -> None:
        """New application code must never recreate ``slot:N`` identities.

        Organizer slots remain transient UI/runtime metadata. Historical slot
        progress is understood only by CharacterSlotResolver so it can be
        quarantined or migrated after a verified Dofus character id is known.
        Every other application path must work with ``character:<id>`` or with
        no selected identity at all.
        """

        violations: list[str] = []
        diagnostics: list[str] = []
        for path in runtime_python_files(ROOT):
            relative = path.relative_to(ROOT).as_posix()
            if relative in LEGACY_SLOT_COMPATIBILITY_FILES:
                continue
            tree = parse_source(path, ROOT)
            for line, value in string_constants(tree):
                if _slot_identity_literal(value):
                    violations.append(f"{relative}:literal:{value!r}")
                    diagnostics.append(f"{relative} ligne {line}: literal {value!r}")

        self.assertEqual(
            tuple(sorted(KNOWN_SLOT_BUSINESS_DEBT)),
            tuple(sorted(violations)),
            "Nouvelle identite slot:N interdite hors resolver/migration. "
            f"Dette Guide connue={sorted(KNOWN_SLOT_BUSINESS_DEBT)}, trouve={sorted(violations)}; "
            f"diagnostics={diagnostics}",
        )

    def test_modern_progress_surfaces_do_not_default_to_a_slot_identity(self) -> None:
        """No UI/progress surface may silently select slot 1 as a fallback."""

        surfaces = (
            "main.py",
            "app/pages/home_page.py",
            "app/pages/_quests_page_impl.py",
            "app/modules/encyclopedia/views/encyclopedia_page.py",
            "app/modules/encyclopedia/views/guides_view.py",
            "app/modules/encyclopedia/views/achievements_view.py",
            "app/modules/encyclopedia/widgets/quest_detail_view.py",
            "app/modules/encyclopedia/widgets/achievement_objective_widget.py",
            "app/modules/encyclopedia/services/quest_progress_service.py",
            "app/modules/encyclopedia/services/guide_progress_service.py",
            "app/modules/encyclopedia/services/serialized_achievement_progress_service.py",
        )
        violations: list[str] = []
        for relative in surfaces:
            tree = parse_source(ROOT / relative, ROOT)
            if any(_slot_identity_literal(value) for _, value in string_constants(tree)):
                violations.append(relative)

        self.assertEqual([], violations)

    def test_character_keys_are_not_derived_from_display_or_process_metadata(self) -> None:
        """Business character keys must not be built from name, PID, slot or position."""

        allowed_non_business_cache = {
            "app/pages/organizer_icon_cache.py:character_key",
        }
        violations: list[str] = []
        diagnostics: list[str] = []
        forbidden_fragments = ("name", "pid", "slot", "index", "position")
        for path in runtime_python_files(ROOT):
            relative = path.relative_to(ROOT).as_posix()
            tree = parse_source(path, ROOT)
            for node in ast.walk(tree):
                if not isinstance(node, (ast.Assign, ast.AnnAssign)) or node.value is None:
                    continue
                targets = node.targets if isinstance(node, ast.Assign) else (node.target,)
                target_names = [ast.unparse(target) for target in targets]
                business_targets = [
                    target
                    for target in target_names
                    if "character_key" in target or "identity_key" in target
                ]
                if not business_targets:
                    continue
                referenced = {
                    child.id.casefold()
                    for child in ast.walk(node.value)
                    if isinstance(child, ast.Name)
                } | {
                    child.attr.casefold()
                    for child in ast.walk(node.value)
                    if isinstance(child, ast.Attribute)
                }
                if any(fragment in name for name in referenced for fragment in forbidden_fragments):
                    violations.append(f"{relative}:{business_targets[0]}")
                    diagnostics.append(
                        f"{relative} ligne {node.lineno}: {business_targets[0]} derive de {sorted(referenced)}"
                    )
        self.assertEqual(
            allowed_non_business_cache,
            set(violations),
            "Nouvelle cle personnage derivee d'un nom/PID/slot/index/position. "
            "L'exception Organizer ne concerne que la cle du cache d'icone. "
            f"Trouve={sorted(violations)}; diagnostics={diagnostics}",
        )


if __name__ == "__main__":
    unittest.main()
