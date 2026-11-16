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

BASE = "https://ganymede-app.com/guides/24"
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
            context = browser.new_context(locale="fr-FR")
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


def _native_visual_probe(route: dict, cover_png: bytes) -> None:
    """Render real source cards in Atlas' existing shared Qt reader, read-only.

    Screenshots are limited QA excerpts, never installed/published guide data.
    """
    from PySide6.QtCore import QPoint, Qt
    from PySide6.QtGui import QPixmap
    from PySide6.QtWidgets import QApplication, QCheckBox, QFrame, QLabel, QVBoxLayout
    from app.ui.theme import GUIDE_READING_METRICS
    from app.ui.theme import atlas_stylesheet
    from app.ui.unity_skin import UnityBackdrop
    from app.modules.encyclopedia.views.ganymede_guide_shell import GanymedeGuideShell
    from app.modules.encyclopedia.views.guide_library_sources import GanymedeListing

    app = QApplication.instance() or QApplication([])
    app.setStyleSheet(atlas_stylesheet())
    backdrop = UnityBackdrop()
    backdrop.resize(1280, 720)
    container = QVBoxLayout(backdrop)
    shell = GanymedeGuideShell(lambda: None)
    container.addWidget(shell)
    listing = GanymedeListing(2205, "Dofus Cawotte",
                              "dofus", 60, 64,
                              "https://ganymede-app.com/guides/2205")
    cover = QPixmap()
    if not cover.loadFromData(cover_png):
        raise AssertionError("Source-linked Cawotte cover art failed to decode")
    shell.set_listing(listing, artwork=cover)
    if not shell.show_cawotte_review():
        raise AssertionError("Cawotte shared shell inaccessible")
    # The source route is injected only into an ephemeral read-only shell.
    # Preserve all original rich_blocks, IDs, ordering and image bytes.
    import copy
    cards = [copy.deepcopy(card) for card in route["steps"]]
    for card in cards:
        card["manual_review_only"] = True
    shell.service.cards = tuple(cards)
    shell.service.guide_title = "Dofus Cawotte"
    shell.guide_title_label.setText(shell.service.guide_title)
    shell.guide_title_label.setToolTip(shell.service.guide_title)
    shell._preparation_loaded = False
    shell._preparation_needs = ()
    shell._preparation_preview = ()
    shell._populate_summary()
    shell._refresh_header()
    backdrop.show()
    app.processEvents()
    out = Path("artifacts/visual-cawotte")
    out.mkdir(parents=True, exist_ok=True)
    reports = []
    filenames = {
        0: "real-cawotte-step-01.png",
        1: "real-cawotte-step-02-long.png",
        2: "real-cawotte-step-03.png",
        5: "real-cawotte-step-06-image.png",
    }
    try:
        for index in (0, 1, 2, 5, 39, 63):
            shell._show_index(index)
            app.processEvents()
            frame = shell.cards_layout.itemAt(0).widget()
            if shell.rendered_card_count != 1 or frame is None:
                raise AssertionError(f"step {index + 1}: not exactly one Atlas sheet")
            sheets = shell.findChildren(QFrame, "GuideManualSheet")
            if sum(int(w.isVisibleTo(shell)) for w in sheets) != 1:
                raise AssertionError(f"step {index + 1}: duplicate visible Qt sheet")
            expected_title = cards[index]["manual_title"]
            if expected_title.startswith("Step "):
                expected_title = expected_title.replace("Step ", "Étape ", 1)
            if index == 0:
                # Text prerequisite rows stay in Prérequis ONLY.
                texts = [label.text() for label in frame.findChildren(QLabel)]
                for forbidden in (
                    "nécessaire d'être niveau 60",
                    "Vous devriez avoir fait le guide",
                    "Intrusion chez les wabbits",
                ):
                    if any(forbidden in label for label in texts):
                        raise AssertionError(
                            f"Prerequisite duplicated in Route: {forbidden}"
                        )
            if frame.findChildren(QCheckBox, "GuideManualSourceChecklist"):
                raise AssertionError("Source checklist still draws selection squares")
            if shell._metric_caption_labels["Préparation"].text() != "Prérequis":
                raise AssertionError("Source route has wrong top-level Prérequis menu")
            if shell._metric_caption_labels["Route"].text() != "Route":
                raise AssertionError("Source route label was overwritten")
            if shell.sheet_title_label.text() != expected_title:
                raise AssertionError(f"step {index + 1}: wrong source title")
            if shell.page_jump.value() != index + 1:
                raise AssertionError(f"step {index + 1}: broken page selector")
            if frame.width() > shell.scroll.viewport().width() + 2:
                raise AssertionError(f"step {index + 1}: horizontal sheet clipping")
            for image_label in frame.findChildren(QLabel, "GuideManualSourceImage"):
                pixmap = image_label.pixmap()
                if pixmap is None or pixmap.isNull():
                    raise AssertionError(f"step {index + 1}: image not rendered")
                if (pixmap.width() > GUIDE_READING_METRICS["source_image_max_width"]
                        or pixmap.height() > GUIDE_READING_METRICS["source_image_max_height"]):
                    raise AssertionError(f"step {index + 1}: source image too large")
            for line in frame.findChildren(QLabel):
                if not line.isVisibleTo(frame):
                    continue
                left = line.mapTo(frame, QPoint(0, 0)).x()
                if left < -4 or left + line.width() > frame.width() + 5:
                    raise AssertionError(f"step {index + 1}: text/image horizontal overflow")
            images = len(frame.findChildren(QLabel, "GuideManualSourceImage"))
            expected = sum(
                block["type"] == "image"
                for block in cards[index]["manual_runtime_metadata"]["source_step"]
                    ["actions"][0]["rich_blocks"]
            )
            if images != expected:
                raise AssertionError(
                    f"step {index + 1}: missing image widgets ({images}/{expected})"
                )
            if index in filenames:
                screenshot = out / filenames[index]
                if not backdrop.grab().save(str(screenshot), "PNG"):
                    raise AssertionError("Native Qt screenshot failed")
            reports.append((index + 1, frame.height(),
                            shell.scroll.verticalScrollBar().maximum(), images))
        shell._show_index(5)
        app.processEvents()
        shell.scroll.verticalScrollBar().setValue(
            shell.scroll.verticalScrollBar().maximum()
        )
        app.processEvents()
        if not backdrop.grab().save(str(out / "real-cawotte-step-06-bottom.png"), "PNG"):
            raise AssertionError("Bottom-of-page screenshot failed")
        shell._show_index(0)
        shell.preparation_button.click()
        app.processEvents()
        if shell._preparation_tab != "Prérequis":
            raise AssertionError("Imported guide opens the wrong prerequisite tab")
        first_preview = tuple(shell._preparation_preview)
        source_labels = shell.preparation_panel.findChildren(QLabel, "GuideManualLine")
        if len(source_labels) < 4:
            raise AssertionError("Prérequis should retain four source-authored lines")
        if not any('href="' in label.text() for label in source_labels):
            raise AssertionError("Authored prerequisite links became plain copy-only text")
        if not backdrop.grab().save(str(out / "real-cawotte-prerequisites.png"), "PNG"):
            raise AssertionError("Prerequisites screenshot failed")
        print("CAWOTTE_VISUAL_QT: 1280x720 native Windows,"
              f" checked={reports}, prerequisite_rows={len(first_preview)}",
              flush=True)
        # Report the gap without changing the authored source or inventing gates.
        if len([1 for category, *_ in first_preview if category == "Prérequis"]) < 3:
            raise AssertionError("Step 1: authored prerequisites absent from dedicated tab")
    finally:
        backdrop.close()
        app.processEvents()


def _cover_image_from_original_html(html: str) -> bytes:
    """Fetch only the Dofus icon explicitly linked by source step 1."""
    expected_url = "https://api.dofusdb.fr/img/items/23006.png"
    dom = _DOM(html)
    linked = [
        n for n in _desc(dom.root)
        if n.attrs.get("type") == "item" and n.attrs.get("dofusdbid") == "972"
        and n.attrs.get("imageurl") == expected_url
    ]
    if not linked:
        raise AssertionError("Cannot ground Cawotte icon in original guide markup")
    with urlopen(Request(expected_url, headers={
        "User-Agent": "DOFUS-ATLAS-Visual-Source-Icon/1.0",
    }), timeout=20) as response:
        data = response.read(256 * 1024 + 1)
    if not data.startswith(b"\x89PNG\r\n\x1a\n") or len(data) > 256 * 1024:
        raise AssertionError("Invalid source-linked icon bytes")
    return data


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
                "title": "Dofus Cawotte",
                "steps": steps,
            })
            self.assertEqual(len(projected["steps"]), 64)
            if os.environ.get("ATLAS_CAWOTTE_VISUAL") == "1":
                _native_visual_probe(projected, _cover_image_from_original_html(page_html[0]))
            print(
                "READ_ONLY_NOT_CERTIFIED: "
                f"source_articles={len(steps)} "
                f"candidate_positions_matching={len(steps)} "
                f"embedded_source_image_urls={len(urls)} "
                f"projected_steps={len(projected['steps'])}"
            )


if __name__ == "__main__":
    unittest.main()
