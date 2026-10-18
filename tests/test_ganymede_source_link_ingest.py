from __future__ import annotations

import unittest

from tools.ganymede_source_link_ingest import build_snapshot, parse_reference_page


def _page(number: int, *, coord: str = "[-3,-3]", link: str = "/en/database/quest/123") -> str:
    start = (number - 1) * 50
    return "".join(
        f'<article id="step-{start+i}">'
        f'<h2>Step {start+i} {coord}</h2>'
        f'<div class="guide-content">'
        f'<a href="https://dofusdb.fr{link}">Quest</a>'
        f'<a href="https://ganymede-app.com/guides/2205?page=1">Guide</a>'
        f'<p>Coordinates {coord}</p>'
        f'</div></article>'
        for i in range(1, 51)
    )


def _catalog(steps: int) -> dict:
    return {"guides": [
        {"ganymede_guide_id": 2203, "listed_step_count": steps},
        {"ganymede_guide_id": 2205, "listed_step_count": 64},
    ]}


class GanymedeSourceLinkImportTests(unittest.TestCase):
    def test_parse_factual_links_and_step_heading_coordinates(self) -> None:
        html = (
            '<article id="step-1"><h2>Step 1 [-3,-3]</h2>'
            '<div><a href="https://dofusdb.fr/en/database/quest/123">'
            'quest</a><a href="https://dofusdb.fr/fr/database/quest/123">duplicate</a>'
            '<a href="https://ganymede-app.com/guides/2205?page=1&stepsPerPage=1">'
            'Cawotte</a><p>[-3,-3] then [4,-5]</p></div></article>'
        )
        rows = parse_reference_page(html, page=1)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["external_dofusdb_ids"]["quest"], [123])
        self.assertEqual(rows[0]["linked_guide_ids"], [2205])
        self.assertEqual(rows[0]["coordinate_mentions"], [[-3, -3], [4, -5]])

    def test_never_import_editorial_text(self) -> None:
        html = ('<article id="step-1"><h2>Step 1</h2>'
                '<p>Guide licensed editorial text must not be copied</p>'
                '</article>')
        row = parse_reference_page(html, page=1)[0]
        self.assertNotIn("Guide licensed", str(row))
        self.assertEqual(set(row), {
            "source_step_number", "source_page", "linked_guide_ids",
            "external_dofusdb_ids", "coordinate_mentions",
        })

    def test_ignore_untrusted_link_hosts(self) -> None:
        html = (
            '<article id="step-1">'
            '<a href="https://ganymede-app.com.evil.com/guides/2203">no</a>'
            '<a href="http://ganymede-app.com/guides/2203">no</a>'
            '<a href="https://dofusdb.fr.evil.com/en/database/quest/3">no</a>'
            '<a href="https://dofusdb.fr/en/database/quest/3">yes</a>'
            '</article>'
        )
        row = parse_reference_page(html, page=1)[0]
        self.assertEqual(row["linked_guide_ids"], [])
        self.assertEqual(row["external_dofusdb_ids"]["quest"], [3])

    def test_escaped_html_entities_and_title_coordinates(self) -> None:
        html = ('<article id="step-1"><h2>Step 1 &#91;3,-11&#93;</h2>'
                '<p>do not infer travel</p></article>')
        self.assertEqual(parse_reference_page(html, page=1)[0]["coordinate_mentions"], [[3, -11]])

    def test_strict_step_numbers_and_page_fallback(self) -> None:
        with self.assertRaisesRegex(ValueError, "unexpected step number"):
            parse_reference_page('<article id="step-1"></article>', page=2)
        with self.assertRaisesRegex(ValueError, "empty"):
            parse_reference_page("<div>No steps</div>", page=1)

    def test_snapshot_rejects_truncated_page(self) -> None:
        with self.assertRaisesRegex(ValueError, "expected 100 steps"):
            build_snapshot(2203, _catalog(100), [
                _page(1), '<article id="step-51"></article>'
            ], checked_on="2026-10-18")

    def test_snapshot_rejects_missing_page(self) -> None:
        with self.assertRaisesRegex(ValueError, "expected 2 pages"):
            build_snapshot(2203, _catalog(100), [_page(1)], checked_on="2026-10-18")

    def test_snapshot_preserves_uncertified_status(self) -> None:
        snapshot = build_snapshot(2203, _catalog(50), [_page(1)], checked_on="2026-10-18")
        self.assertEqual(snapshot["coverage"]["observed_steps"], 50)
        self.assertEqual(snapshot["coverage"]["coordinate_mentions"], 50)
        self.assertEqual(snapshot["coverage"]["dofusdb_step_link_counts"]["quest"], 50)
        self.assertEqual(snapshot["coverage"]["linked_main_index_guide_ids"], 1)
        self.assertFalse(snapshot["coverage"]["route_order_certified"])
        self.assertEqual(snapshot["coverage"]["quest_objective_mapping_verified"], 0)
        self.assertFalse(snapshot["source"]["editorial_text_imported"])

    def test_snapshot_does_not_guess_missing_guide(self) -> None:
        with self.assertRaisesRegex(ValueError, "not indexed"):
            build_snapshot(99999, _catalog(50), [_page(1)], checked_on="2026-10-18")


if __name__ == "__main__":
    unittest.main()
