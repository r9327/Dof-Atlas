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
    """Real Qt: one continuous container/page, 64 immutable source fiches.

    Browser-rendered French author blocks are temporary QA fixtures only.
    Pages are responsive projections, not a different Quest order.
    """
    import copy
    from html import unescape
    from PySide6.QtCore import QPoint, Qt, QTimer
    from PySide6.QtGui import QPixmap
    from PySide6.QtWidgets import (
        QApplication, QCheckBox, QDialog, QFrame, QLabel, QSlider, QVBoxLayout,
    )
    from app.ui.theme import GUIDE_READING_METRICS, atlas_stylesheet
    from app.ui.unity_skin import UnityBackdrop
    from app.modules.encyclopedia.views.ganymede_guide_shell import GanymedeGuideShell
    from app.modules.encyclopedia.views.guide_library_sources import GanymedeListing
    from app.modules.encyclopedia.services.guide_source_reading_pages import (
        authored_reading_blocks,
    )

    app = QApplication.instance() or QApplication([])
    app.setStyleSheet(atlas_stylesheet())
    backdrop = UnityBackdrop()
    backdrop.resize(1280, 720)
    container = QVBoxLayout(backdrop)
    shell = GanymedeGuideShell(lambda: None)
    container.addWidget(shell)
    # Preview entrypoint remains pilot-guarded; only its ephemeral Qt cards
    # are replaced by exact source /24, without installation/progress writes.
    listing = GanymedeListing(
        2205, "Dofus Cawotte", "dofus", 60, 64,
        "https://ganymede-app.com/guides/2205",
    )
    cover = QPixmap()
    if not cover.loadFromData(cover_png):
        raise AssertionError("Real Cawotte source cover did not decode")
    shell.set_listing(listing, artwork=cover)
    if not shell.show_cawotte_review():
        raise AssertionError("Read-only Cawotte preview not available")
    shell._listing = GanymedeListing(24, "Dofus Cawotte", "dofus", 60, 64, BASE)
    cards = [copy.deepcopy(card) for card in route["steps"]]
    for card in cards:
        card["manual_review_only"] = True
    shell.service.cards = tuple(cards)
    shell.service.guide_title = "Dofus Cawotte"
    shell.guide_title_label.setText("Dofus Cawotte")
    shell._preparation_loaded = False
    shell._preparation_needs = ()
    shell._preparation_preview = ()
    backdrop.show()
    app.processEvents()
    shell._populate_summary()
    shell._refresh_header()

    original_blocks = authored_reading_blocks(cards)
    pages = shell._source_reading_pages()
    assert len(cards) == 64
    if not 4 <= len(pages) < len(cards):
        raise AssertionError(f"Invalid responsive page count {len(pages)}")
    if tuple(entry for page in pages for entry in page) != original_blocks:
        raise AssertionError("A source paragraph/link/image was lost or reordered")
    if shell.summary_list.count() != len(pages):
        raise AssertionError("Route summary must list pages, not fake 64 steps")

    out = Path("artifacts/visual-cawotte")
    out.mkdir(parents=True, exist_ok=True)
    reports = []
    zoom_checked = False
    for page_index in range(len(pages)):
        shell._show_reading_page(page_index)
        app.processEvents()
        frame = shell.cards_layout.itemAt(0).widget()
        if frame is None or shell.rendered_card_count != 1:
            raise AssertionError(f"Page {page_index + 1}: missing single reader")
        if frame.objectName() != "GuideManualSheet":
            raise AssertionError("Original authored blocks inside wrong container")
        if frame.property("sourceContinuousReading") is not True:
            raise AssertionError("Still using nested artificial Atlas step cards")
        if shell.sheet_title_label.text() != "Parcours":
            raise AssertionError("Duplicated Step/Quest heading in reading header")
        if shell.page_jump.value() != page_index + 1:
            raise AssertionError(f"Broken page navigation at {page_index + 1}")
        if shell.page_jump.maximum() != len(pages):
            raise AssertionError("Page selector counts source fiches, not reader pages")
        if shell.scroll.objectName() != "GuideManualSourceScroll":
            raise AssertionError("Source reader still paints full empty scroll glass")
        if frame.width() > shell.scroll.viewport().width() + 2:
            raise AssertionError(f"Page {page_index + 1}: horizontal clipping")
        if frame.findChildren(QCheckBox, "GuideManualSourceChecklist"):
            raise AssertionError("Copied source checkboxes must not be interactive")
        for label in frame.findChildren(QLabel):
            if not label.isVisibleTo(frame):
                continue
            left = label.mapTo(frame, QPoint(0, 0)).x()
            if left < -4 or left + label.width() > frame.width() + 5:
                raise AssertionError(f"Page {page_index + 1}: clipped rich text")
        image_labels = frame.findChildren(QLabel, "GuideManualSourceImage")
        expected_images = sum(
            entry["block"]["type"] == "image" for entry in pages[page_index]
        )
        if len(image_labels) != expected_images:
            raise AssertionError(
                f"Page {page_index + 1}: image loss "
                f"{len(image_labels)}/{expected_images}"
            )
        for label in image_labels:
            pix = label.pixmap()
            if pix is None or pix.isNull():
                raise AssertionError("Source illustration cannot render")
            if (pix.width() > GUIDE_READING_METRICS["source_image_max_width"]
                    or pix.height() > GUIDE_READING_METRICS["source_image_max_height"]):
                raise AssertionError("Source illustration exceeds indexed thumbnail")
            if not zoom_checked:
                def exercise_zoom() -> None:
                    modal = app.activeModalWidget()
                    if not isinstance(modal, QDialog):
                        raise AssertionError("Image click did not open its zoom popup")
                    slider = modal.findChild(QSlider, "GuideSourceImageZoomSlider")
                    image = modal.findChild(QLabel, "GuideSourceImageZoomed")
                    if slider is None or image is None or image.pixmap() is None:
                        raise AssertionError("Missing zoom slider/original image")
                    first = image.pixmap().width()
                    slider.setValue(200)
                    if image.pixmap().width() <= first:
                        raise AssertionError("Zoom does not enlarge original image")
                    modal.accept()
                QTimer.singleShot(0, exercise_zoom)
                label.open_zoom()
                zoom_checked = True
        if page_index == 0:
            # Source prerequisites stay in their own drawer.
            text = " ".join(label.text() for label in frame.findChildren(QLabel))
            for forbidden in ("nécessaire d'être niveau 60",
                              "Vous devriez avoir fait le guide"):
                if forbidden in text:
                    raise AssertionError("Prerequisites duplicated inside Route")
        scrollbar = shell.scroll.verticalScrollBar()
        top = out / f"page-{page_index + 1:02d}-haut.png"
        if not backdrop.grab().save(str(top), "PNG"):
            raise AssertionError("Cannot save real Qt page")
        scroll_max = scrollbar.maximum()
        bottom_name = None
        if scroll_max > 0:
            scrollbar.setValue(scroll_max)
            app.processEvents()
            bottom = out / f"page-{page_index + 1:02d}-bas.png"
            if not backdrop.grab().save(str(bottom), "PNG"):
                raise AssertionError("Cannot save page bottom")
            bottom_name = bottom.name
        reports.append({
            "page": page_index + 1,
            "original_source_fiches": sorted(set(
                entry["source_index"] + 1 for entry in pages[page_index]
            )),
            "complete_rich_blocks": len(pages[page_index]),
            "images": expected_images,
            "scroll_max": scroll_max,
            "screenshot_top": top.name,
            "screenshot_bottom": bottom_name,
        })
    if not zoom_checked:
        raise AssertionError("Source image zoom not tested")

    # Route and Prérequis are INDEPENDENT half-width drawers.
    shell._show_reading_page(0)
    shell.summary_button.setChecked(True)
    shell.preparation_button.setChecked(True)
    app.processEvents()
    if not shell.summary_panel.isVisibleTo(shell):
        raise AssertionError("Route drawer fails to open")
    if not shell.preparation_panel.isVisibleTo(shell):
        raise AssertionError("Prérequis drawer cannot remain open with Route")
    if (shell.summary_panel.width() > shell.route_bar.width() + 45
            or shell.preparation_panel.width() > shell.preparation_bar.width() + 45):
        raise AssertionError("Guide drawer wider than its progress-bar column")
    if not backdrop.grab().save(str(out / "route-et-prerequis-ouverts.png"), "PNG"):
        raise AssertionError("Cannot capture both open drawers")
    if shell._preparation_tab != "Prérequis":
        raise AssertionError("Wrong default Prérequis subtab")
    if shell.preparation_progress_label.text() != "5 à vérifier":
        raise AssertionError("Source prerequisite counter lost")
    prerequisite_lines = shell.preparation_panel.findChildren(QLabel, "GuideManualLine")
    if len(prerequisite_lines) < 4 or not any(
        'href="' in line.text() for line in prerequisite_lines
    ):
        raise AssertionError("Source prerequisites lost original linked text")
    if not backdrop.grab().save(str(out / "onglet-prerequis.png"), "PNG"):
        raise AssertionError("Cannot capture prerequisites")
    for tab in shell.preparation_tab_group.buttons():
        if tab.property("tabKey") == "À préparer":
            tab.click()
            break
    app.processEvents()
    if shell._preparation_tab != "À préparer":
        raise AssertionError("Cannot open material subtab")
    material_lines = shell.preparation_panel.findChildren(QLabel, "GuideManualLine")
    captions = shell.preparation_panel.findChildren(
        QLabel, "GuidePreparationSourceContext"
    )
    objects = unescape(" ".join(line.text() for line in material_lines))
    context = unescape(" ".join(label.text() for label in captions))
    if "Cawotte" not in objects or "Couronne" not in objects:
        raise AssertionError("Typed source item or equipment disappeared")
    if "Art gastronomique" in objects or "L'œuf ou la cawotte" in objects:
        raise AssertionError("Context masquerades as repeated item row")
    if "Art gastronomique" not in context or "L'œuf ou la cawotte" not in context:
        raise AssertionError("Author section headings were lost")
    if not backdrop.grab().save(str(out / "onglet-a-preparer.png"), "PNG"):
        raise AssertionError("Cannot capture original material/context groups")
    if not shell.summary_panel.isVisibleTo(shell):
        raise AssertionError("Opening À préparer closed Route unexpectedly")

    # Responsive QA at half-width: paragraphs stay whole, page model adapts.
    old_page_count = len(pages)
    backdrop.resize(820, 720)
    app.processEvents()
    shell._source_resize_reflow()
    app.processEvents()
    narrow = shell._source_reading_pages()
    if tuple(entry for pg in narrow for entry in pg) != original_blocks:
        raise AssertionError("Resize lost or duplicated an authored source block")
    if not backdrop.grab().save(str(out / "lecture-resize-etroit.png"), "PNG"):
        raise AssertionError("Cannot capture resized reader")
    (out / "controle-visuel-index.json").write_text(json.dumps({
        "commit_expected": os.environ.get("GITHUB_SHA"),
        "capture_scope": "READ_ONLY_SOURCE_NOT_CERTIFIED",
        "original_source_fiches": len(cards),
        "source_image_blocks": sum(
            entry["block"]["type"] == "image" for entry in original_blocks
        ),
        "pages_at_desktop_width": old_page_count,
        "pages_at_narrow_width": len(narrow),
        "zoom_popup_checked": zoom_checked,
        "both_drawers_checked": True,
        "pages": reports,
    }, indent=2, ensure_ascii=False), encoding="utf-8")
    print(
        "CAWOTTE_RESPONSIVE_QT: source_fiches=64,"
        f" pages={old_page_count}, narrow_pages={len(narrow)},"
        f" zoom={zoom_checked}, both_drawers=True",
        flush=True,
    )
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
                "guide_id": "cawotte_fr_24_probe_unverified",
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
