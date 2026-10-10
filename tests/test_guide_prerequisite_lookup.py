from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from app.modules.encyclopedia.services import guide_path_profiles
from app.modules.encyclopedia.services.guide_path_profiles import GuidePathResolver


class GuidePrerequisiteLookupTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        directory = self.root / "encyclopedia" / "quests"
        directory.mkdir(parents=True)
        (directory / "source_mapping.json").write_text(
            json.dumps({"quests": {
                "1": {"quest_id": 1, "name": "La quête de l'aube"},
                "2": {"quest_id": 2, "name": "Légende oubliée"},
                "3": {"quest_id": 3, "name": "Épreuve"},
                "99": {"quest_id": 99, "name": "Quête inconnue"},
            }}),
            encoding="utf-8",
        )
        quests = [
            SimpleNamespace(id=qid, name=name)
            for qid, name in (
                (1, "La quête de l'aube"),
                (2, "Légende oubliée"),
                (3, "Épreuve"),
            )
        ]
        catalog = SimpleNamespace(quests=quests, by_id={q.id: q for q in quests})
        quest_provider = SimpleNamespace(get_catalog=lambda: catalog)
        achievement_provider = SimpleNamespace(load_all=lambda: [])
        with patch.object(guide_path_profiles, "DATA_DIR", self.root):
            self.resolver = GuidePathResolver(quest_provider, achievement_provider)

    def test_exact_loose_and_prefixed_text_keep_same_quest_ids(self) -> None:
        resolver = self.resolver
        self.assertEqual(resolver._quest_ids_from_prerequisite_text("La quête de l'aube"), {1})
        self.assertEqual(resolver._quest_ids_from_prerequisite_text("La quête de l’aube"), {1})
        self.assertEqual(resolver._quest_ids_from_prerequisite_text(
            "Avoir terminé La quête de l'aube"
        ), {1})
        self.assertEqual(resolver._quest_ids_from_prerequisite_text(
            "Avoir terminé Légende oubliée"
        ), {2})
        self.assertEqual(resolver._quest_ids_from_prerequisite_text("quêtes inconnues"), set())
        self.assertEqual(resolver._quest_ids_from_prerequisite_text(""), set())

    def test_lookup_does_not_resort_source_names_on_every_fallback(self) -> None:
        class FrozenItems(dict):
            def items(self):
                raise AssertionError("Resorting the source mapping on each lookup is forbidden")

        resolver = self.resolver
        # The fallback must perform indexed lookups, never loop across all names.
        resolver.quest_source_name_to_ids = FrozenItems(resolver.quest_source_name_to_ids)
        for _ in range(20):
            self.assertEqual(
                resolver._quest_ids_from_prerequisite_text("Avoir terminé La quête de l'aube"),
                {1},
            )
        self.assertEqual(resolver._quest_ids_from_prerequisite_text("Terminer Épreuve"), set())

    def test_indexed_fallback_is_equivalent_to_full_catalog_scan(self) -> None:
        from random import Random

        rng = Random(9327)
        resolver = self.resolver
        keys = [
            "la_quete_de_l_aube", "legende_oubliee", "epreuve",
            "retour_au_village", "quete_des_grands_jours", "le_dernier_souffle",
            "defi_sylvestre", "surprenant", "poursuite", "longue_quete_finale",
        ]
        resolver.quest_source_name_to_ids.clear()
        for ident, key in enumerate(keys, 1):
            resolver.quest_source_name_to_ids[key].append(ident)

        def legacy_full_scan(value: str) -> set[int]:
            padded = f"_{value}_"
            result: set[int] = set()
            for name, ids in resolver.quest_source_name_to_ids.items():
                if len(name) >= 8 and (f"_{name}_" in padded or value.endswith(name)):
                    result.update(ids)
            return result

        handpicked = (
            "", "legende_oubliee", "avoir_termine_legende_oubliee",
            "interdit_surprenant", "lasurprenant", "autresurprenant",
            "quete_des_grands_jours_et_legende_oubliee",
            "xla_quete_de_l_aube", "retour_au_village_extra", "epreuve",
        )
        alphabet = "abcdefghijklmnopqrstuvwxyz_"
        random_cases = [
            "".join(rng.choice(alphabet) for _ in range(rng.randrange(0, 65)))
            for _ in range(500)
        ]
        random_cases.extend(
            "_".join(rng.choice(keys) for _ in range(rng.randrange(1, 5)))
            for _ in range(250)
        )
        for value in (*handpicked, *random_cases):
            with self.subTest(value=value):
                self.assertEqual(
                    resolver._source_prerequisite_matches(value),
                    legacy_full_scan(value),
                )

    def test_fallback_never_scans_whole_catalog(self) -> None:
        resolver = self.resolver
        class IndexOnlyDict(dict):
            def items(self):
                raise AssertionError("full scan is forbidden")
        resolver.quest_source_name_to_ids = IndexOnlyDict(
            resolver.quest_source_name_to_ids
        )
        self.assertEqual(
            resolver._quest_ids_from_prerequisite_text(
                "Avoir terminé Légende oubliée"
            ),
            {2},
        )

    def test_topological_order_preserves_legacy_sorted_priority(self):
        from collections import defaultdict
        quests = {qid: SimpleNamespace(id=qid, name=f'Quest {qid:04d}',
                                      level_min=qid % 7) for qid in range(1, 121)}
        deps = {qid: {max(1, qid // 2), max(1, qid // 3)} for qid in range(4, 100)}
        deps[119], deps[120] = {120}, {119}
        resolver = object.__new__(GuidePathResolver)
        resolver.quest_by_id = quests
        resolver._direct_quest_prerequisites = lambda quest: deps.get(quest.id, set())
        def key(qid):
            q = quests[qid]
            return q.level_min, guide_path_profiles.normalize_text(q.name), qid
        ids = set(quests)
        incoming = {qid: 0 for qid in ids}
        children = defaultdict(set)
        for qid in ids:
            for previous in deps.get(qid, set()) & ids:
                if qid not in children[previous]:
                    children[previous].add(qid)
                    incoming[qid] += 1
        ready = sorted((qid for qid, count in incoming.items() if count == 0), key=key)
        expected = []
        while ready:
            qid = ready.pop(0)
            expected.append(qid)
            for child in sorted(children.get(qid, ()), key=key):
                incoming[child] -= 1
                if incoming[child] == 0:
                    ready.append(child)
                    ready.sort(key=key)
        expected.extend(sorted(ids - set(expected), key=key))
        self.assertEqual(resolver._topological_order(ids), expected)

    def test_text_cache_returns_independent_sets_without_rescanning(self):
        resolver = self.resolver
        phrase = "Avoir terminé La quête de l'aube"
        first = resolver._quest_ids_from_prerequisite_text(phrase)
        self.assertEqual(first, {1})
        first.add(9999)
        # The complete candidate list must not be visited again.
        class NoLookup(dict):
            def get(self, *_args, **_kwargs):
                raise AssertionError("cached text must not probe source mapping")
        resolver.quest_source_name_to_ids = NoLookup(resolver.quest_source_name_to_ids)
        self.assertEqual(resolver._quest_ids_from_prerequisite_text(phrase), {1})
        self.assertEqual(resolver._prerequisite_text_cache[phrase], frozenset({1}))

    def test_direct_cache_avoids_reparsing_but_tracks_record_changes(self):
        resolver = self.resolver
        quest = SimpleNamespace(id=1, start_criterion='Qf=2', prerequisites=[])
        parser = guide_path_profiles.mandatory_references
        with patch.object(guide_path_profiles, 'mandatory_references', wraps=parser) as parse:
            first = resolver._direct_quest_prerequisites(quest)
            self.assertEqual(first, {2})
            first.clear()
            self.assertEqual(resolver._direct_quest_prerequisites(quest), {2})
            self.assertEqual(parse.call_count, 1)
            resolver.enriched_quest_prerequisites[1] = {3}
            self.assertEqual(resolver._direct_quest_prerequisites(quest, include_enriched=True), {2, 3})
            resolver.enriched_quest_prerequisites[1].clear()
            self.assertEqual(resolver._direct_quest_prerequisites(quest, include_enriched=True), {2})
            self.assertEqual(parse.call_count, 1)
            quest.start_criterion = 'Qf=3'
            self.assertEqual(resolver._direct_quest_prerequisites(quest), {3})
            self.assertEqual(parse.call_count, 2)
            quest.prerequisites = ["Avoir terminé La quête de l'aube"]
            # A self-referencing quest remains excluded after a record update.
            self.assertEqual(resolver._direct_quest_prerequisites(quest), {3})
            self.assertEqual(parse.call_count, 3)

    def test_text_cache_is_bounded_to_the_resolver_lifetime(self):
        resolver = self.resolver
        for i in range(4102):
            self.assertEqual(resolver._quest_ids_from_prerequisite_text(f'Unknown condition {i}'), set())
        self.assertEqual(len(resolver._prerequisite_text_cache), 4096)
        self.assertEqual(resolver._quest_ids_from_prerequisite_text('Avoir terminé Légende oubliée'), {2})
        self.assertEqual(len(resolver._prerequisite_text_cache), 4096)


if __name__ == "__main__":
    unittest.main()
