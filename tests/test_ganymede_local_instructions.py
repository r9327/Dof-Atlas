"""Verified authored route contract: observed-link snapshots cannot become guides."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from app.modules.encyclopedia.views.guide_library_sources import (
    GanymedeListing, load_ganymede_local_instructions,
)


class AuthoredGanymedeInstructionTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.folder = Path(temp.name)
        self.entry = GanymedeListing(
            2290, "Test local", "dofus", None, 2,
            "https://ganymede-app.com/guides/2290",
        )
        self.payload = {
            "schema_version": 1,
            "source_guide_id": 2290,
            "source_url": self.entry.source_url,
            "expected_source_step_count": 2,
            "rights_basis": "atlas_original",
            "steps": [
                {
                    "source_step_number": n,
                    "title": f"Étape {n}",
                    "instructions": f"Réaliser une action vérifiée numéro {n}",
                    "actions": [
                        {
                            "kind": "travel",
                            "text": f"Aller à la destination numéro {n}",
                            "coordinates": [n, -n],
                        },
                    ],
                }
                for n in (1, 2)
            ],
        }

    def save(self):
        path = self.folder / "ganymede_2290_instructions.json"
        path.write_text(
            json.dumps(self.payload, ensure_ascii=False), encoding="utf-8",
        )

    def test_missing_is_not_a_playable_guide(self):
        self.assertIsNone(
            load_ganymede_local_instructions(self.entry, data_dir=self.folder),
        )

    def test_full_authored_route_preserves_order_and_actions(self):
        self.save()
        steps = load_ganymede_local_instructions(self.entry, data_dir=self.folder)
        self.assertEqual([s["source_step_number"] for s in steps], [1, 2])
        self.assertEqual(steps[1]["actions"][0]["coordinates"], [2, -2])

    def test_partial_route_fails_closed(self):
        self.payload["steps"].pop()
        self.save()
        with self.assertRaisesRegex(ValueError, "partial"):
            load_ganymede_local_instructions(self.entry, data_dir=self.folder)

    def test_wrong_source_or_unauthorized_content_fails_closed(self):
        self.payload["source_guide_id"] = 2263
        self.save()
        with self.assertRaisesRegex(ValueError, "Unverified"):
            load_ganymede_local_instructions(self.entry, data_dir=self.folder)
        self.payload["source_guide_id"] = 2290
        self.payload["rights_basis"] = "unknown"
        self.save()
        with self.assertRaisesRegex(ValueError, "Unverified"):
            load_ganymede_local_instructions(self.entry, data_dir=self.folder)

    def test_ambiguous_order_or_placeholder_fails_closed(self):
        self.payload["steps"][0]["source_step_number"] = 2
        self.save()
        with self.assertRaisesRegex(ValueError, "Incomplete"):
            load_ganymede_local_instructions(self.entry, data_dir=self.folder)
        self.payload["steps"][0]["source_step_number"] = 1
        self.payload["steps"][0]["instructions"] = "À compléter"
        self.save()
        with self.assertRaisesRegex(ValueError, "Incomplete"):
            load_ganymede_local_instructions(self.entry, data_dir=self.folder)

    def test_authored_copy_labels_are_explicit_and_bounded(self):
        self.payload["steps"][0]["actions"][0]["copy_values"] = [
            "Capitaine Kradoc", "Gros Boulet",
        ]
        self.save()
        self.assertEqual(
            len(load_ganymede_local_instructions(
                self.entry, data_dir=self.folder,
            )), 2,
        )
        for bad in ([""], [123], "Texte arbitraire", ["x" * 257],
                    ["x"] * 33):
            self.payload["steps"][0]["actions"][0]["copy_values"] = bad
            self.save()
            with self.subTest(copy_values=str(bad)[:32]):
                with self.assertRaisesRegex(ValueError, "copy values"):
                    load_ganymede_local_instructions(
                        self.entry, data_dir=self.folder,
                    )

    def test_redistribution_requires_reference_and_attribution(self):
        self.payload["rights_basis"] = "redistribution_permission"
        self.save()
        with self.assertRaisesRegex(ValueError, "permission evidence"):
            load_ganymede_local_instructions(self.entry, data_dir=self.folder)
        self.payload["permission_reference"] = "Written permission ID: fixture"
        self.payload["attribution"] = "Fixture author"
        self.save()
        self.assertEqual(
            len(load_ganymede_local_instructions(self.entry, data_dir=self.folder)), 2,
        )

    def test_actions_must_be_meaningful_and_typed(self):
        self.payload["steps"][0]["actions"][0]["kind"] = "quest_link"
        self.save()
        with self.assertRaisesRegex(ValueError, "Unverified"):
            load_ganymede_local_instructions(self.entry, data_dir=self.folder)
        self.payload["steps"][0]["actions"][0]["kind"] = "travel"
        self.payload["steps"][0]["actions"][0]["coordinates"] = [True, -2]
        self.save()
        with self.assertRaisesRegex(ValueError, "coordinates"):
            load_ganymede_local_instructions(self.entry, data_dir=self.folder)


    def test_every_authored_route_has_complete_local_instructions(self):
        # Every newly authored route is checked automatically, without
        # manually registering IDs for each new guide.
        from app.modules.encyclopedia.views.guide_library_sources import (
            load_ganymede_listings,
        )

        listings = {
            entry.source_id: entry for entry in load_ganymede_listings()
        }
        root = Path(__file__).resolve().parents[1] / "data/encyclopedia/guides"
        files = sorted(root.glob("ganymede_*_instructions.json"))
        self.assertGreaterEqual(len(files), 15)
        expected = {
            2219, 2220, 2227, 2240, 2247, 2248, 2252, 2259,
            2273, 2274, 2284, 2285, 2290, 2590, 2224,
        }
        found = set()
        for file in files:
            source_id = int(file.stem.split("_")[1])
            found.add(source_id)
            with self.subTest(guide_id=source_id):
                entry = listings[source_id]
                steps = load_ganymede_local_instructions(entry)
                self.assertIsNotNone(steps)
                self.assertEqual(len(steps), entry.step_count)
                self.assertEqual(
                    [step["source_step_number"] for step in steps],
                    list(range(1, entry.step_count + 1)),
                )
                self.assertTrue(all(step["title"].strip() for step in steps))
                self.assertTrue(all(step["instructions"].strip() for step in steps))
                self.assertTrue(all(step["actions"] for step in steps))
                self.assertTrue(all(
                    action["text"].strip()
                    for step in steps for action in step["actions"]
                ))
        self.assertTrue(expected.issubset(found))


    def test_every_source_snapshot_loads_from_its_catalogue_id(self):
        # Metadata and offline observations must cover all 95 guides, even
        # where a historic descriptive filename replaces the numeric one.
        from app.modules.encyclopedia.views.guide_library_sources import (
            load_ganymede_listings, load_ganymede_local_observations,
        )

        listings = load_ganymede_listings()
        self.assertEqual(len(listings), 95)
        for entry in listings:
            with self.subTest(source_guide_id=entry.source_id):
                observations = load_ganymede_local_observations(entry)
                self.assertEqual(len(observations), entry.step_count)
                self.assertEqual(
                    [row["source_step_number"] for row in observations],
                    list(range(1, entry.step_count + 1)),
                )

    def test_otomai_three_fournesol_travel_starts_at_stage_two(self):
        # Only source stage 2 mentions Fournesol's [-48,19]; stage 1 is
        # preparatory. Keep an independently corroborated coordinate without
        # moving the whole quest or changing the later stage 3 dialogue.
        from app.modules.encyclopedia.views.guide_library_sources import (
            load_ganymede_listings, load_ganymede_local_observations,
        )

        listing = next(row for row in load_ganymede_listings()
                       if row.source_id == 2252)
        steps = load_ganymede_local_instructions(listing)
        observed = load_ganymede_local_observations(listing)
        source_coordinate = [-48, 19]
        self.assertNotIn(
            source_coordinate,
            [action["coordinates"] for action in steps[0]["actions"]
             if "coordinates" in action],
        )
        stage_two_travel = [
            action for action in steps[1]["actions"]
            if action["kind"] == "travel"
        ]
        self.assertEqual(len(stage_two_travel), 1)
        self.assertEqual(stage_two_travel[0]["coordinates"], source_coordinate)
        self.assertIn(source_coordinate, observed[1]["coordinate_mentions"])
        self.assertTrue(any(action["kind"] == "talk"
                            and "Fournesol" in action["text"]
                            for action in steps[2]["actions"]))

    def test_otomai_one_source_crossing_fights_begin_at_step_four(self):
        # Source GP6/MG6: embark at step 3; the three battles belong to step 4.
        # This narrow regression does not certify the other route objectives.
        from app.modules.encyclopedia.views.guide_library_sources import (
            load_ganymede_listings,
        )

        entry = next(row for row in load_ganymede_listings() if row.source_id == 2219)
        steps = load_ganymede_local_instructions(entry)
        self.assertEqual(len(steps), 7)
        self.assertFalse(any(a["kind"] == "fight" for a in steps[2]["actions"]))
        fights = [a for a in steps[3]["actions"] if a["kind"] == "fight"]
        self.assertEqual(len(fights), 3)
        self.assertTrue(all(
            label in action["text"].casefold()
            for label, action in zip(("premier", "deuxième", "troisième"), fights)
        ))


    def test_otomai_one_comprehensive_pre_certification_contract(self):
        # This is a data regression test, NOT gameplay/source certification.
        from app.modules.encyclopedia.views.guide_library_sources import (
            load_ganymede_listings, load_ganymede_local_observations,
        )

        listing = next(row for row in load_ganymede_listings()
                       if row.source_id == 2219)
        steps = load_ganymede_local_instructions(listing)
        observed = load_ganymede_local_observations(listing)
        self.assertEqual(len(steps), 7)
        self.assertEqual(len(observed), 7)
        root = Path(__file__).resolve().parents[1] / "data/encyclopedia/guides"
        metadata = json.loads(
            (root / "ganymede_2219_instructions.json").read_text(encoding="utf-8")
        )
        self.assertIs(metadata["source_parity_certified"], False)
        self.assertIs(metadata["gameplay_certified"], False)

        def texts(number):
            return " ".join(a["text"] for a in steps[number - 1]["actions"])

        self.assertIn("niveau 40", steps[0]["instructions"].casefold())
        self.assertIn("La grande kradoc", texts(1))
        self.assertIn("Haute voltige", texts(1))
        self.assertIn("étape 5", texts(1))
        self.assertIn("10 Graines de Sésame", texts(2))
        self.assertIn("Kradoc", texts(3))
        self.assertTrue(any(a["kind"] == "deliver" for a in steps[2]["actions"]))
        self.assertFalse(any(a["kind"] == "fight" for a in steps[2]["actions"]))
        self.assertEqual(
            len([a for a in steps[3]["actions"] if a["kind"] == "fight"]), 3
        )
        self.assertIn("Le secret des Flaqueux", texts(4))
        self.assertIn("Parchemin des Flaqueux", texts(4))
        for number, position in (
            (1, [13, 26]), (2, [15, 28]), (3, [15, 28]),
            (4, [19, 42]), (4, [-43, -1]), (4, [-46, 18]),
            (5, [-56, 22]), (6, [-56, 22]), (7, [-54, 19]),
        ):
            self.assertTrue(
                any(a.get("coordinates") == position for a in steps[number-1]["actions"]),
                f"Missing map {position} at stage {number}",
            )
        self.assertIn("1 Dragodinde Rousse", texts(5))
        self.assertIn("1 Dragodinde Amande", texts(5))
        self.assertTrue(any(
            a["kind"] == "deliver" and "format du journal" in a["text"]
            for a in steps[5]["actions"]
        ))
        self.assertIn("version du jeu", steps[4]["instructions"])
        self.assertIn("Le scaéroport de l'Arbre Hakam", texts(6))
        self.assertIn("1 Ailes en bois améliorées", texts(7))
        self.assertIn("1 Casque amélioré", texts(7))

        for step, snapshot in zip(steps, observed):
            known = {tuple(pair) for pair in snapshot["coordinate_mentions"]}
            for action in step["actions"]:
                coords = action.get("coordinates")
                if coords is not None:
                    self.assertEqual(action["kind"], "travel")
                    self.assertIn(tuple(coords), known)

    def test_positioned_actions_follow_local_step_observations(self):
        # A factual coordinate must belong to its exact step in the local
        # observation file. This does not certify the original guide text.
        from app.modules.encyclopedia.views.guide_library_sources import (
            load_ganymede_listings, load_ganymede_local_observations,
        )

        entries = {row.source_id: row for row in load_ganymede_listings()}
        for source_id in (2224, 2259, 2274, 2240):
            with self.subTest(guide=source_id):
                entry = entries[source_id]
                instructions = load_ganymede_local_instructions(entry)
                observations = load_ganymede_local_observations(entry)
                self.assertEqual(len(instructions), entry.step_count)
                self.assertEqual(len(observations), entry.step_count)
                positioned = 0
                for number, (step, observed) in enumerate(
                    zip(instructions, observations), 1
                ):
                    self.assertEqual(step["source_step_number"], number)
                    self.assertEqual(observed["source_step_number"], number)
                    allowed = {
                        tuple(pair) for pair in observed["coordinate_mentions"]
                    }
                    for action in step["actions"]:
                        if "coordinates" not in action:
                            continue
                        positioned += 1
                        self.assertIn(
                            tuple(action["coordinates"]), allowed,
                            f"{source_id} step {number}",
                        )
                self.assertGreater(positioned, 20)


if __name__ == "__main__":
    unittest.main()
