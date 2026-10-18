from __future__ import annotations

import json
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path

from tools.audit_ganymede_master_refs import (
    INDEX,
    MASTER,
    ROOT,
    audit_ganymede_master_refs,
)


class GanymedeMasterReferenceAuditTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.index = {
            "guides": [
                {
                    "ganymede_guide_id": 2251,
                    "listed_step_count": 2,
                },
                {"ganymede_guide_id": 2203},
            ],
        }
        self.master = {
            "schema_version": 1,
            "source": {
                "guide_id": 2251,
                "source_url": "https://ganymede-app.com/guides/2251",
                "extraction_scope": "factual_link_occurrences_only",
                "editorial_text_imported": False,
                "page_count": 2,
                "steps_per_page": 1,
            },
            "coverage": {
                "observed_steps": 2,
                "distinct_linked_guide_ids": 2,
                "linked_main_index_guide_ids": 1,
                "linked_outside_main_index_guide_ids": [3768],
                "step_guide_links": 2,
                "dofusdb_step_link_counts": {
                    "quest": 1, "dungeon": 0, "object": 0, "monster": 0,
                },
                "coordinate_mentions": 1,
                "quest_objective_mapping_verified": 0,
                "route_order_certified": False,
            },
            "steps": [
                {
                    "source_step_number": 1,
                    "source_page": 1,
                    "linked_guide_ids": [3768],
                    "external_dofusdb_ids": {
                        "quest": [], "dungeon": [], "object": [], "monster": [],
                    },
                    "coordinate_mentions": [],
                },
                {
                    "source_step_number": 2,
                    "source_page": 2,
                    "linked_guide_ids": [2203],
                    "external_dofusdb_ids": {
                        "quest": [1631], "dungeon": [], "object": [], "monster": [],
                    },
                    "coordinate_mentions": [[4, -3]],
                },
            ],
        }
        self._write()

    def _write(self) -> None:
        for path, data in ((INDEX, self.index), (MASTER, self.master)):
            full = self.root / path
            full.parent.mkdir(parents=True, exist_ok=True)
            full.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

    def codes(self) -> list[str]:
        return [i["code"] for i in audit_ganymede_master_refs(self.root)["issues"]]

    def test_observed_links_are_not_certified_routes(self) -> None:
        report = audit_ganymede_master_refs(self.root)
        self.assertEqual(report["status"], "PASS_OBSERVED_LINKS_ONLY")
        self.assertEqual(report["verified_routes"], 0)
        self.assertEqual(report["unclassified_non_main_guide_ids"], [3768])
        self.assertEqual(report["observed_steps"], 2)

    def test_full_repository_snapshot_is_internally_coherent(self) -> None:
        report = audit_ganymede_master_refs(ROOT)
        self.assertEqual(report["status"], "PASS_OBSERVED_LINKS_ONLY", report["issues"])
        self.assertEqual(report["observed_steps"], 156)
        self.assertEqual(report["referenced_main_guides"], 89)
        self.assertEqual(report["unclassified_non_main_guide_ids"], [3238, 3768])
        self.assertEqual(report["verified_routes"], 0)

    def test_priority_source_guides_have_complete_step_sequences(self) -> None:
        for name, expected, guide_id in (
            ("argente", 237, 2203),
            ("cawotte", 64, 2205),
            ("emeraude", 52, 2211),
            ("dolmanax", 9, 2248),
            ("ou_sont_les_dofus", 26, 2204),
            ("dokoko", 49, 2208),
            ("pourpre", 45, 2276),
            ("veilleurs", 88, 2209),
            ("krosmoz", 51, 2230),
            ("turquoise", 87, 2217),
            ("ivoire", 118, 2256),
            ("glaces", 121, 2216),
            ("bwork_camps", 34, 2207),
            ("otomai_1", 7, 2219),
            ("sufokia", 39, 2228),
            ("valonia_1", 30, 2206),
            ("sidimote_1", 25, 2224),
            ("koalaks", 9, 2227),
            ("enudorado_1", 29, 2237),
            ("ecaflipus_1", 48, 2250),
            ("otomai_2", 7, 2220),
            ("xelorium_1", 27, 2240),
            ("otomai_3", 13, 2252),
            ("2290", 2, 2290),
            ("2285", 4, 2285),
            ("2247", 6, 2247),
            ("2273", 15, 2273),
            ("2590", 16, 2590),
            ("2284", 21, 2284),
            ("2259", 25, 2259),
            ("2274", 26, 2274),
            ("2244", 29, 2244),
            ("2278", 29, 2278),
            ("2214", 30, 2214),
            ("2235", 31, 2235),
            ("2265", 32, 2265),
            ("2282", 32, 2282),
            ("2218", 33, 2218),
            ("2258", 39, 2258),
            ("2280", 40, 2280),
            ("2264", 40, 2264),
            ("2291", 41, 2291),
            ("2255", 43, 2255),
            ("2279", 43, 2279),
            ("2232", 44, 2232),
            ("2236", 45, 2236),
            ("2260", 47, 2260),
            ("2238", 50, 2238),
            ("2254", 52, 2254),
            ("2277", 53, 2277),
            ("2225", 54, 2225),
            ("2226", 54, 2226),
            ("2275", 54, 2275),
            ("2283", 55, 2283),
            ("2272", 56, 2272),
            ("2253", 59, 2253),
            ("2223", 60, 2223),
            ("2241", 61, 2241),
            ("2271", 62, 2271),
            ("2221", 64, 2221),
            ("2231", 65, 2231),
            ("2286", 65, 2286),
            ("2239", 65, 2239),
            ("2229", 67, 2229),
            ("2595", 67, 2595),
            ("2281", 69, 2281),
            ("2245", 71, 2245),
            ("2266", 71, 2266),
            ("2292", 72, 2292),
            ("2246", 73, 2246),
            ("2243", 73, 2243),
            ("2222", 74, 2222),
            ("2210", 76, 2210),
            ("2262", 79, 2262),
            ("2288", 79, 2288),
            ("2233", 87, 2233),
            ("2257", 91, 2257),
            ("3738", 97, 3738),
            ("2215", 101, 2215),
            ("2268", 101, 2268),
            ("3795", 103, 3795),
            ("2289", 112, 2289),
            ("3737", 113, 3737),
            ("2212", 120, 2212),
            ("2261", 142, 2261),
            ("2269", 174, 2269),
            ("2213", 181, 2213),
            ("2270", 141, 2270),
            ("2234", 212, 2234),
        ):
            with self.subTest(guide=name):
                path = Path(f"data/encyclopedia/guides/ganymede_{name}_observed_links.json")
                report = audit_ganymede_master_refs(ROOT, snapshot=path)
                self.assertEqual(report["status"], "PASS_OBSERVED_LINKS_ONLY", report["issues"])
                self.assertEqual(report["source_guide_id"], guide_id)
                self.assertEqual(report["observed_steps"], expected)
                self.assertEqual(report["verified_routes"], 0)

    def test_missing_source_step_fails(self) -> None:
        self.master["steps"].pop()
        self._write()
        self.assertIn("step_coverage", self.codes())

    def test_out_of_order_step_fails(self) -> None:
        self.master["steps"][1]["source_step_number"] = 3
        self._write()
        self.assertIn("step_sequence", self.codes())

    def test_wrong_page_fails(self) -> None:
        self.master["steps"][1]["source_page"] = 1
        self._write()
        self.assertIn("step_page", self.codes())

    def test_unreported_non_main_link_fails(self) -> None:
        self.master["coverage"]["linked_outside_main_index_guide_ids"] = []
        self._write()
        self.assertIn("link_count_mismatch", self.codes())

    def test_changed_external_id_fails(self) -> None:
        self.master["steps"][0]["linked_guide_ids"] = [0]
        self._write()
        self.assertIn("invalid_guide_links", self.codes())

    def test_wrong_count_fails(self) -> None:
        self.master["coverage"]["dofusdb_step_link_counts"]["quest"] = 2
        self._write()
        self.assertIn("link_count_mismatch", self.codes())

    def test_false_route_certification_fails(self) -> None:
        self.master["coverage"]["route_order_certified"] = True
        self._write()
        self.assertIn("false_certification", self.codes())

    def test_false_quest_verification_fails(self) -> None:
        self.master["coverage"]["quest_objective_mapping_verified"] = 1
        self._write()
        self.assertIn("false_certification", self.codes())

    def test_editorial_content_import_claim_fails(self) -> None:
        self.master["source"]["editorial_text_imported"] = True
        self._write()
        self.assertIn("unproven_source", self.codes())

    def test_duplicate_links_fail(self) -> None:
        self.master["steps"][0]["linked_guide_ids"] = [3768, 3768]
        self._write()
        self.assertIn("invalid_guide_links", self.codes())


if __name__ == "__main__":
    unittest.main()
