from __future__ import annotations

import unittest
from types import SimpleNamespace

from app.modules.encyclopedia.models.entity_ref import EntityRef
from app.modules.encyclopedia.models.guide import Guide
from app.modules.encyclopedia.models.guide_section import GuideSection
from app.modules.encyclopedia.models.guide_step import GuideStep
from app.modules.encyclopedia.views.guides_view import GuidesView


class DofusGuidePrerequisitesTests(unittest.TestCase):
    @staticmethod
    def _guide(category="dofus", extra_refs=()):
        first = GuideStep(
            id="first", step_type="quest", order=1, entity_id=1,
            prerequisites=(
                EntityRef("achievement", 900, "Succès brut"),
                EntityRef("quest", 10, "Quête couverte par le Succès"),
                EntityRef("quest", 11, "Quête réellement distincte"),
                *extra_refs,
            ),
        )
        return Guide(
            id="dofus_fixture", title="Dofus de test", category=category,
            sections=(GuideSection(id="main", title="Route", steps=(first,)),),
        )

    @staticmethod
    def _context():
        success = SimpleNamespace(
            id=900, name="Succès prérequis vérifié",
            linked_quests=(EntityRef("quest", 10, "Quête couverte"),),
            resolved_linked_quests=(),
        )
        catalogue = {
            1: SimpleNamespace(id=1, prerequisites=[]),
            10: SimpleNamespace(id=10, name="Quête couverte"),
            11: SimpleNamespace(id=11, name="Quête distincte"),
            12: SimpleNamespace(id=12, name="Autre quête préalable"),
        }
        return SimpleNamespace(
            achievement_provider=SimpleNamespace(get_by_id=lambda achievement_id: success if achievement_id == 900 else None),
            quest_catalog=SimpleNamespace(by_id=catalogue),
            graph=SimpleNamespace(previous_ids=lambda _qid: (10, 11, 12)),
            _quest_id_from_requirement_line=lambda _line: None,
        )

    def test_explicit_required_success_replaces_only_its_covered_quests(self) -> None:
        entries = GuidesView._guide_prerequisite_entries(self._context(), self._guide())
        self.assertEqual(
            entries,
            [
                ("Succès prérequis vérifié", None, 900),
                ("Quête réellement distincte", 11, None),
                ("Autre quête préalable", 12, None),
            ],
        )

    def test_without_explicit_success_no_quest_can_be_omitted(self) -> None:
        guide = self._guide()
        first = guide.steps[0]
        no_success = GuideStep(
            id=first.id, step_type="quest", order=1, entity_id=1,
            prerequisites=tuple(ref for ref in first.prerequisites if ref.entity_type != "achievement"),
        )
        guide = Guide(
            id="dofus_fixture", title="Dofus", category="dofus",
            sections=(GuideSection(id="main", title="Route", steps=(no_success,)),),
        )
        entries = GuidesView._guide_prerequisite_entries(self._context(), guide)
        self.assertNotIn(("Succès prérequis vérifié", None, 900), entries)
        self.assertIn(("Quête couverte par le Succès", 10, None), entries)

    def test_more_than_eight_true_requirements_are_not_silently_hidden(self) -> None:
        additional = tuple(EntityRef("quest", 100 + i, f"Condition {i}") for i in range(12))
        entries = GuidesView._guide_prerequisite_entries(
            self._context(), self._guide(extra_refs=additional)
        )
        self.assertEqual(len(entries), 15)
        self.assertIn(("Condition 11", 111, None), entries)


if __name__ == "__main__":
    unittest.main()
