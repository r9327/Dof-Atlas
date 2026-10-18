"""Import public, factual Ganymède link references without storing guide prose.

One guide per invocation, read-only by default. HTML can be supplied from a
local staging folder or fetched explicitly with --fetch. Nothing is certified
as an Atlas quest, objective, prerequisite, or runnable travel command.
"""
from __future__ import annotations

import argparse
import json
import re
import time
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from tools.audit_ganymede_master_refs import INDEX, LINK_TYPES, ROOT

_GUIDE = re.compile(r"^/guides/([1-9][0-9]*)/?$")
_DOFUSDB = re.compile(r"^/(?:en|fr)/database/(quest|dungeon|object|monster)/([1-9][0-9]*)/?$")
_COORD = re.compile(r"\[\s*(-?\d+)\s*,\s*(-?\d+)\s*\]")
_STEP = re.compile(r"^step-([1-9][0-9]*)$")
_PER_PAGE = 50


class _ReferenceParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.rows: list[dict[str, object]] = []
        self.active: dict[str, object] | None = None
        self._text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attrs_map = dict(attrs)
        if tag == "article" and attrs_map.get("id"):
            match = _STEP.fullmatch(attrs_map["id"])
            if match:
                if self.active is not None:
                    raise ValueError("nested guide steps")
                self.active = {
                    "source_step_number": int(match.group(1)),
                    "linked_guide_ids": [],
                    "external_dofusdb_ids": {kind: [] for kind in LINK_TYPES},
                }
                self._text = []
        if self.active is None or tag != "a":
            return
        href = attrs_map.get("href") or ""
        parsed = urlparse(href)
        if parsed.scheme != "https":
            return
        if parsed.netloc == "ganymede-app.com":
            match = _GUIDE.fullmatch(parsed.path)
            if match:
                target = int(match.group(1))
                dest = self.active["linked_guide_ids"]
                if target not in dest:
                    dest.append(target)
        elif parsed.netloc in {"dofusdb.fr", "www.dofusdb.fr"}:
            match = _DOFUSDB.fullmatch(parsed.path)
            if match:
                kind, identifier = match.group(1), int(match.group(2))
                dest = self.active["external_dofusdb_ids"][kind]
                if identifier not in dest:
                    dest.append(identifier)

    def handle_data(self, data: str) -> None:
        if self.active is not None:
            self._text.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag != "article" or self.active is None:
            return
        # Coordinate *mentions* can appear in headings and the body. The
        # source contains examples as well as actions; never infer travel.
        text = "".join(self._text)
        coords: list[list[int]] = []
        for match in _COORD.finditer(text):
            coordinate = [int(match.group(1)), int(match.group(2))]
            if coordinate not in coords:
                coords.append(coordinate)
        self.rows.append({**self.active, "coordinate_mentions": coords})
        self.active = None
        self._text = []


def parse_reference_page(html: str, *, page: int, per_page: int = _PER_PAGE) -> list[dict[str, object]]:
    if page < 1 or per_page < 1:
        raise ValueError("invalid page number or size")
    parser = _ReferenceParser()
    parser.feed(html)
    parser.close()
    if parser.active is not None or not parser.rows:
        raise ValueError("incomplete or empty step article markup")
    rows = []
    for offset, row in enumerate(parser.rows):
        expected = (page - 1) * per_page + offset + 1
        if row["source_step_number"] != expected:
            raise ValueError(f"unexpected step number: {row['source_step_number']} != {expected}")
        rows.append({"source_step_number": expected, "source_page": page,
                     "linked_guide_ids": row["linked_guide_ids"],
                     "external_dofusdb_ids": row["external_dofusdb_ids"],
                     "coordinate_mentions": row["coordinate_mentions"]})
    return rows


def build_snapshot(
    guide_id: int,
    index: dict[str, object],
    pages: list[str],
    *,
    checked_on: str,
) -> dict[str, object]:
    if type(guide_id) is not int or guide_id <= 0:
        raise ValueError("invalid Ganymède guide ID")
    sources = index.get("guides", [])
    if not isinstance(sources, list):
        raise ValueError("invalid guide catalog")
    matching = [r for r in sources if isinstance(r, dict) and r.get("ganymede_guide_id") == guide_id]
    if len(matching) != 1:
        raise ValueError("guide not indexed in Ganymède public tree")
    expected = matching[0].get("listed_step_count")
    if type(expected) is not int or expected <= 0:
        raise ValueError("missing public tree step count")
    expected_pages = (expected + _PER_PAGE - 1) // _PER_PAGE
    if len(pages) != expected_pages:
        raise ValueError(f"guide {guide_id}: expected {expected_pages} pages, got {len(pages)}")
    steps = [step for n, html in enumerate(pages, 1)
             for step in parse_reference_page(html, page=n)]
    if len(steps) != expected:
        raise ValueError(f"guide {guide_id}: expected {expected} steps, got {len(steps)}")
    main_ids = {r["ganymede_guide_id"] for r in sources
                if isinstance(r, dict) and type(r.get("ganymede_guide_id")) is int}
    links = {gid for step in steps for gid in step["linked_guide_ids"]}
    totals = {kind: sum(len(step["external_dofusdb_ids"][kind]) for step in steps)
              for kind in LINK_TYPES}
    return {
        "schema_version": 1,
        "source": {
            "name": "Ganymède",
            "guide_id": guide_id,
            "source_url": f"https://ganymede-app.com/guides/{guide_id}",
            "checked_on": checked_on,
            "page_count": expected_pages,
            "steps_per_page": _PER_PAGE,
            "route_role": "orchestrator_master_guide" if guide_id == 2251 else "specialized_guide",
            "extraction_scope": "factual_link_occurrences_only",
            "editorial_text_imported": False,
            "notice": "Link IDs and coordinates are unclassified mentions, not verified route actions.",
        },
        "coverage": {
            "observed_steps": expected,
            "distinct_linked_guide_ids": len(links),
            "linked_main_index_guide_ids": len(links & main_ids),
            "linked_outside_main_index_guide_ids": sorted(links - main_ids),
            "step_guide_links": sum(len(s["linked_guide_ids"]) for s in steps),
            "dofusdb_step_link_counts": totals,
            "coordinate_mentions": sum(len(s["coordinate_mentions"]) for s in steps),
            "quest_objective_mapping_verified": 0,
            "route_order_certified": False,
        },
        "steps": steps,
    }


def _fetch_page(guide_id: int, page: int, *, timeout: int) -> str:
    url = f"https://ganymede-app.com/guides/{guide_id}?page={page}&stepsPerPage={_PER_PAGE}"
    request = Request(url, headers={"User-Agent": "DofusAtlasReferenceAudit/1.0"})
    with urlopen(request, timeout=timeout) as response:
        if response.geturl().split("?")[0] != f"https://ganymede-app.com/guides/{guide_id}":
            raise ValueError("unexpected source redirect")
        return response.read(4_000_001).decode("utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--guide-id", required=True, type=int)
    parser.add_argument("--html-dir", type=Path, help="staged source: <guide-id>-<page>.html")
    parser.add_argument("--fetch", action="store_true", help="request public HTML explicitly")
    parser.add_argument("--apply", action="store_true", help="write a verified JSON snapshot")
    parser.add_argument("--checked-on", required=True, help="source observation date YYYY-MM-DD")
    parser.add_argument("--output", type=Path, help="destination JSON path (requires --apply)")
    parser.add_argument("--timeout", type=int, default=20)
    parser.add_argument("--delay", type=float, default=3.0, help="seconds between public requests")
    args = parser.parse_args()
    if bool(args.html_dir) == bool(args.fetch):
        parser.error("choose exactly one source: --html-dir or --fetch")
    if args.output and not args.apply:
        parser.error("--output requires --apply")
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", args.checked_on):
        parser.error("--checked-on must use YYYY-MM-DD")
    if args.delay < 2 or args.timeout < 1:
        parser.error("minimum public fetch delay is 2 seconds; timeout must be positive")

    index = json.loads((ROOT / INDEX).read_text(encoding="utf-8"))
    guide = next((r for r in index["guides"]
                  if r.get("ganymede_guide_id") == args.guide_id), None)
    if guide is None:
        parser.error("guide ID is absent from the public source catalog")
    count = guide["listed_step_count"]
    pages: list[str] = []
    for page in range(1, (count + _PER_PAGE - 1) // _PER_PAGE + 1):
        if args.fetch:
            if page > 1:
                time.sleep(args.delay)
            pages.append(_fetch_page(args.guide_id, page, timeout=args.timeout))
        else:
            path = args.html_dir / f"{args.guide_id}-{page}.html"
            pages.append(path.read_text(encoding="utf-8"))
    snapshot = build_snapshot(args.guide_id, index, pages, checked_on=args.checked_on)
    print(json.dumps({"status": "OBSERVED_UNCLASSIFIED", "guide_id": args.guide_id,
                      "steps": snapshot["coverage"]["observed_steps"],
                      "apply": args.apply}, ensure_ascii=False))
    if args.apply:
        output = args.output or ROOT / "data/encyclopedia/guides" / f"ganymede_{args.guide_id}_observed_links.json"
        output.parent.mkdir(parents=True, exist_ok=True)
        # Write only after all pages have passed structural coverage checks.
        output.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
