"""Live, read-only Cawotte HTML -> source card diagnostic.

Explicitly not a legal/source-rights, installed-guide, gameplay or UI certificate.
No downloaded author HTML/images are committed, printed or uploaded as artifacts.
The standard atlas_guide_html_capture importer remains entirely offline.
"""
from __future__ import annotations

import json
import os
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

from app.constants import DATA_DIR
from app.modules.encyclopedia.services.guide_shared_route_contract import project_authorized_guide
from tools.atlas_guide_html_capture import (
    _DECORATIVE_TAG_IMAGE_ALTS, _DOM, _STEP, _desc, extract_saved_html,
)

BASE = "https://ganymede-app.com/guides/2205"
CANDIDATE = DATA_DIR / "encyclopedia" / "guides" / "ganymede_2205_action_candidates.json"
MAX_PAGE_BYTES = 4 * 1024 * 1024
MAX_IMAGE_BYTES = 2 * 1024 * 1024


def _download(url: str, limit: int) -> bytes:
    parts = urlsplit(url)
    if parts.scheme != "https" or parts.hostname != "ganymede-app.com" or parts.username:
        raise ValueError("Unapproved live diagnostic source host")
    with urlopen(Request(url, headers={
        "User-Agent": "DOFUS-ATLAS-Cawotte-read-only-probe/1.0",
        "Accept": "text/html,image/webp,image/png,image/jpeg",
        "Accept-Language": "en-US,en;q=0.8",
    }), timeout=20) as response:
        data = response.read(limit + 1)
    if not data or len(data) > limit:
        raise ValueError("Empty or oversized live source response")
    return data



def _render_source_pages() -> list[str]:
    """Read only the real browser DOM. Ganymede step articles are JS-rendered."""
    from playwright.sync_api import sync_playwright
    pages: list[str] = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True, args=["--no-sandbox"])
        try:
            context = browser.new_context(locale="en-US")
            page = context.new_page()
            for number in range(1, 8):
                page.goto(
                    f"{BASE}?page={number}&stepsPerPage=10",
                    wait_until="domcontentloaded", timeout=45000,
                )
                expected = 4 if number == 7 else 10
                page.wait_for_function(
                    """expected => document.querySelectorAll(
                        'article[id^="step-"]').length === expected""",
                    arg=expected, timeout=40000,
                )
                html = page.content()
                if len(html.encode("utf-8")) > MAX_PAGE_BYTES:
                    raise ValueError("Rendered HTML page exceeds size limit")
                pages.append(html)
        finally:
            browser.close()
    return pages


def _guide_image_urls(html: str) -> set[str]:
    dom = _DOM(html)
    found: set[str] = set()
    for article in _desc(dom.root):
        if article.tag != "article" or not _STEP.fullmatch(article.attrs.get("id", "")):
            continue
        contents = [
            node for node in _desc(article)
            if node.tag == "div" and "guide-content" in node.attrs.get("class", "").split()
        ]
        if len(contents) != 1:
            raise ValueError("Ambiguous source guide-content container")
        for node in _desc(contents[0]):
            if node.tag != "img" or node.attrs.get("alt") in _DECORATIVE_TAG_IMAGE_ALTS:
                continue
            src = node.attrs.get("src", "")
            parts = urlsplit(src)
            if (parts.scheme != "https" or parts.hostname != "ganymede-app.com"
                    or not parts.path.startswith("/storage/guides/")
                    or not parts.path.endswith((".png", ".jpg", ".jpeg", ".webp"))
                    or parts.query or parts.fragment):
                raise ValueError("Unapproved authored image URL in source")
            found.add(src)
    return found


@unittest.skipUnless(os.environ.get("ATLAS_LIVE_CAWOTTE") == "1",
                     "requires explicit read-only live network opt-in")
class CawotteLiveSourceDiagnostic(unittest.TestCase):
    def test_all_64_ganymede_articles_parse_without_loss(self):
        # Do not set the importer's rights_verified/reference_verified flags.
        # This only probes source HTML parsing in an ephemeral CI workspace.
        candidate = json.loads(CANDIDATE.read_text(encoding="utf-8"))
        self.assertEqual(candidate["source_step_count"], 64)
        page_html = _render_source_pages()
        urls: set[str] = set()
        for html in page_html:
            urls.update(_guide_image_urls(html))
        with tempfile.TemporaryDirectory(prefix="atlas-cawotte-live-") as tmp:
            root = Path(tmp)

            def fetch_image(pair: tuple[int, str]) -> tuple[str, Path]:
                index, url = pair
                data = _download(url, MAX_IMAGE_BYTES)
                path = root / f"asset_{index}{Path(urlsplit(url).path).suffix}"
                path.write_bytes(data)
                return url, path

            with ThreadPoolExecutor(max_workers=4) as pool:
                assets = dict(pool.map(fetch_image, enumerate(sorted(urls), 1)))
            steps = []
            for html in page_html:
                for entry in extract_saved_html(html, assets=assets):
                    self.assertEqual(entry["number"], len(steps) + 1)
                    steps.append(entry["step"])
            self.assertEqual(len(steps), 64)
            self.assertEqual(
                [s["source_step_id"] for s in steps],
                [f"step-{i:04d}" for i in range(1, 65)],
            )
            for i, step in enumerate(steps):
                self.assertEqual(step.get("coordinates"), candidate["steps"][i]["at"])
                self.assertEqual(len(step["actions"]), 1)
                blocks = step["actions"][0]["rich_blocks"]
                self.assertGreater(len(blocks), 0)
            # Can it pass the exact canonical converter? No staging/activation.
            projected = project_authorized_guide({
                "guide_id": "cawotte_probe_unverified",
                "title": "Cawotte technical probe (NOT_CERTIFIED)",
                "steps": steps,
            })
            self.assertEqual(len(projected["steps"]), 64)
            print(
                "READ_ONLY_NOT_CERTIFIED: "
                f"source_articles={len(steps)} "
                f"candidate_positions_matching={len(steps)} "
                f"embedded_source_image_urls={len(urls)} "
                f"projected_steps={len(projected['steps'])}"
            )


if __name__ == "__main__":
    unittest.main()
