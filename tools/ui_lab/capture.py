from __future__ import annotations

import argparse
import json
import re
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

from PySide6.QtCore import QEventLoop
from PySide6.QtGui import QFont, QFontDatabase, QImage, QPainter
from PySide6.QtWidgets import QApplication, QAbstractScrollArea, QScrollArea

from app.ui.theme import atlas_stylesheet
from tools.ui_lab.registry import DEFAULT_SCENARIO, PreviewSpec, get_preview, resolve_factory
from tools.ui_lab.screens import PreviewContext


DEFAULT_WIDTH = 1400
DEFAULT_HEIGHT = 900
DEFAULT_SETTLE_MS = 1000
DEFAULT_SEGMENT_OVERLAP = 80
MAX_FULL_SCROLL_HEIGHT = 30000


@dataclass(frozen=True, slots=True)
class CaptureSpec:
    screen: str
    scenario: str = DEFAULT_SCENARIO
    width: int = DEFAULT_WIDTH
    height: int = DEFAULT_HEIGHT
    settle_ms: int = DEFAULT_SETTLE_MS
    params: dict[str, Any] = field(default_factory=dict)
    output_name: str = ""
    capture_segments: bool = False
    capture_full_scroll: bool = False
    segment_overlap: int = DEFAULT_SEGMENT_OVERLAP
    scroll_object_name: str = ""


def _safe_slug(value: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9._-]+", "-", value.strip()).strip("-.")
    return slug or "capture"


def _settle(app: QApplication, milliseconds: int) -> None:
    deadline = time.monotonic() + max(0, milliseconds) / 1000.0
    while time.monotonic() < deadline:
        app.processEvents(QEventLoop.AllEvents, 50)
        time.sleep(0.01)
    app.processEvents(QEventLoop.AllEvents, 50)


def _configure_application(app: QApplication) -> str:
    families = set(QFontDatabase.families())
    candidates = ("Segoe UI", "Arial", "Tahoma", "DejaVu Sans")
    family = next((candidate for candidate in candidates if candidate in families), app.font().family())
    app.setApplicationName("Dofus Atlas UI Capture")
    app.setFont(QFont(family))
    app.setStyleSheet(atlas_stylesheet() + f'\nQWidget {{ font-family: "{family}"; }}\n')
    return family


def _validate_capture(spec: CaptureSpec, preview: PreviewSpec) -> None:
    if not preview.is_live:
        raise RuntimeError(f"Écran non capturable tant qu'il n'est pas LIVE: {preview.key}")
    if spec.scenario not in preview.scenarios:
        raise ValueError(
            f"Scénario inconnu pour {preview.key}: {spec.scenario!r}; "
            f"disponibles={preview.scenarios!r}"
        )
    if spec.width < 320 or spec.height < 240:
        raise ValueError("Viewport UI Lab trop petit")
    if spec.segment_overlap < 0:
        raise ValueError("segment_overlap doit être positif ou nul")


def _scroll_target(widget, spec: CaptureSpec) -> QAbstractScrollArea | None:
    requested_name = str(spec.scroll_object_name or "").strip()
    if not requested_name:
        requested_name = str(widget.property("uiLabCaptureScrollTarget") or "").strip()
    if requested_name:
        target = widget.findChild(QAbstractScrollArea, requested_name)
        if target is None:
            raise RuntimeError(f"Zone de scroll UI Lab introuvable: {requested_name}")
        return target

    candidates = [
        area
        for area in widget.findChildren(QAbstractScrollArea)
        if area.isVisible() and area.verticalScrollBar().maximum() > 0
    ]
    if not candidates:
        return None

    def score(area: QAbstractScrollArea) -> tuple[int, int, int]:
        bar = area.verticalScrollBar()
        preferred = 1 if isinstance(area, QScrollArea) else 0
        return preferred, int(bar.maximum()), int(area.viewport().width())

    return max(candidates, key=score)


def _scroll_positions(area: QAbstractScrollArea, overlap: int) -> list[int]:
    bar = area.verticalScrollBar()
    maximum = max(0, int(bar.maximum()))
    if maximum <= 0:
        return [0]
    viewport_height = max(1, int(area.viewport().height()))
    step = max(1, viewport_height - min(max(0, overlap), viewport_height - 1))
    positions = list(range(0, maximum + 1, step))
    if positions[-1] != maximum:
        positions.append(maximum)
    return positions


def _capture_long_view(
    app: QApplication,
    widget,
    spec: CaptureSpec,
    output_dir: Path,
    base_name: str,
) -> dict[str, Any]:
    if not (spec.capture_segments or spec.capture_full_scroll):
        return {}

    area = _scroll_target(widget, spec)
    if area is None or area.verticalScrollBar().maximum() <= 0:
        return {
            "scroll_target": None,
            "segments": [],
            "full_file": None,
            "scroll_range": 0,
        }

    bar = area.verticalScrollBar()
    original_value = int(bar.value())
    positions = _scroll_positions(area, spec.segment_overlap)
    segments: list[str] = []
    full_file: str | None = None
    safe_base = _safe_slug(base_name)

    viewport = area.viewport()
    viewport_width = max(1, int(viewport.width()))
    viewport_height = max(1, int(viewport.height()))
    full_height = int(bar.maximum()) + viewport_height
    if spec.capture_full_scroll and full_height > MAX_FULL_SCROLL_HEIGHT:
        raise RuntimeError(
            f"Capture full trop haute ({full_height}px > {MAX_FULL_SCROLL_HEIGHT}px) pour {base_name}"
        )

    full_image: QImage | None = None
    painter: QPainter | None = None
    if spec.capture_full_scroll:
        full_image = QImage(viewport_width, full_height, QImage.Format_ARGB32)
        full_image.fill(0)
        painter = QPainter(full_image)

    try:
        for index, position in enumerate(positions, 1):
            bar.setValue(position)
            _settle(app, min(max(80, spec.settle_ms // 4), 300))

            if spec.capture_segments:
                segment_name = f"{safe_base}-{index:02d}.png"
                segment_path = output_dir / segment_name
                segment = widget.grab()
                if segment.isNull() or not segment.save(str(segment_path), "PNG"):
                    raise RuntimeError(f"Capture segment impossible: {segment_path}")
                segments.append(segment_name)

            if painter is not None:
                viewport_pixmap = viewport.grab()
                if viewport_pixmap.isNull():
                    raise RuntimeError(f"Capture viewport impossible pour {base_name}")
                painter.drawPixmap(0, position, viewport_pixmap)

        if painter is not None and full_image is not None:
            painter.end()
            painter = None
            full_file = f"{safe_base}-full.png"
            full_path = output_dir / full_file
            if not full_image.save(str(full_path), "PNG"):
                raise RuntimeError(f"Capture full impossible: {full_path}")
    finally:
        if painter is not None:
            painter.end()
        bar.setValue(original_value)
        _settle(app, 50)

    return {
        "scroll_target": str(area.objectName() or area.metaObject().className()),
        "segments": segments,
        "full_file": full_file,
        "scroll_range": int(bar.maximum()),
        "full_scope": "scroll_content" if full_file else None,
    }


def capture_preview(app: QApplication, spec: CaptureSpec, output_dir: Path) -> dict[str, Any]:
    preview = get_preview(spec.screen)
    _validate_capture(spec, preview)
    output_dir.mkdir(parents=True, exist_ok=True)
    base_name = spec.output_name.strip() or f"{preview.key}__{spec.scenario}"
    filename = f"{_safe_slug(base_name)}.png"
    output_path = output_dir / filename
    status_messages: list[str] = []

    with TemporaryDirectory(prefix="dofus_atlas_ui_capture_") as sandbox:
        context = PreviewContext(
            sandbox_root=Path(sandbox),
            report_status=status_messages.append,
            scenario=spec.scenario,
            params=dict(spec.params),
        )
        widget = resolve_factory(preview)(context)
        try:
            widget.resize(spec.width, spec.height)
            widget.show()
            _settle(app, spec.settle_ms)
            pixmap = widget.grab()
            if pixmap.isNull() or not pixmap.save(str(output_path), "PNG"):
                raise RuntimeError(f"Capture PNG impossible: {output_path}")
            long_capture = _capture_long_view(app, widget, spec, output_dir, base_name)
        finally:
            widget.close()
            widget.deleteLater()
            app.processEvents(QEventLoop.AllEvents, 50)

    return {
        "screen": preview.key,
        "label": preview.label,
        "scenario": spec.scenario,
        "params": spec.params,
        "source": preview.source,
        "width": spec.width,
        "height": spec.height,
        "settle_ms": spec.settle_ms,
        "file": filename,
        "status_messages": status_messages,
        **long_capture,
    }


def capture_lab_shell(app: QApplication, output_dir: Path, width: int = 1600, height: int = 1000) -> dict[str, Any]:
    from tools.ui_lab.window import UiLabWindow

    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "ui-lab-shell.png"
    window = UiLabWindow()
    try:
        window.resize(width, height)
        window.show()
        _settle(app, DEFAULT_SETTLE_MS)
        pixmap = window.grab()
        if pixmap.isNull() or not pixmap.save(str(output_path), "PNG"):
            raise RuntimeError(f"Capture PNG impossible: {output_path}")
        current = window._current_spec.key if window._current_spec is not None else None
        return {
            "screen": "ui-lab-shell",
            "scenario": DEFAULT_SCENARIO,
            "width": width,
            "height": height,
            "file": output_path.name,
            "current_preview": current,
        }
    finally:
        window.close()
        window.deleteLater()
        app.processEvents(QEventLoop.AllEvents, 50)


def _capture_spec_from_dict(
    raw: dict[str, Any],
    *,
    default_segments: bool = False,
    default_full_scroll: bool = False,
    default_overlap: int = DEFAULT_SEGMENT_OVERLAP,
) -> CaptureSpec:
    screen = str(raw.get("screen", "")).strip()
    if not screen:
        raise ValueError("Chaque capture doit renseigner 'screen'")
    params = raw.get("params", {})
    if params is None:
        params = {}
    if not isinstance(params, dict):
        raise ValueError("Le champ 'params' d'une capture doit être un objet JSON")
    return CaptureSpec(
        screen=screen,
        scenario=str(raw.get("scenario", DEFAULT_SCENARIO)),
        width=int(raw.get("width", DEFAULT_WIDTH)),
        height=int(raw.get("height", DEFAULT_HEIGHT)),
        settle_ms=int(raw.get("settle_ms", DEFAULT_SETTLE_MS)),
        params=dict(params),
        output_name=str(raw.get("output_name", "") or ""),
        capture_segments=bool(raw.get("capture_segments", default_segments)),
        capture_full_scroll=bool(raw.get("capture_full_scroll", default_full_scroll)),
        segment_overlap=int(raw.get("segment_overlap", default_overlap)),
        scroll_object_name=str(raw.get("scroll_object_name", "") or ""),
    )


def load_request(path: Path) -> tuple[list[CaptureSpec], bool]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("La requête UI Lab doit être un objet JSON")
    raw_captures = payload.get("captures")
    if not isinstance(raw_captures, list) or not raw_captures:
        raise ValueError("La requête UI Lab doit contenir une liste 'captures' non vide")

    default_segments = bool(payload.get("capture_segments", False))
    default_full_scroll = bool(payload.get("capture_full_scroll", False))
    default_overlap = int(payload.get("segment_overlap", DEFAULT_SEGMENT_OVERLAP))
    captures = []
    for raw in raw_captures:
        if not isinstance(raw, dict):
            raise ValueError("Chaque entrée de 'captures' doit être un objet JSON")
        captures.append(
            _capture_spec_from_dict(
                raw,
                default_segments=default_segments,
                default_full_scroll=default_full_scroll,
                default_overlap=default_overlap,
            )
        )
    return captures, bool(payload.get("include_lab_shell", False))


def run_request(request_path: Path, output_dir: Path) -> Path:
    captures, include_lab_shell = load_request(request_path)
    app = QApplication.instance() or QApplication([])
    if not isinstance(app, QApplication):
        raise RuntimeError("Une QApplication est requise pour les captures UI Lab")
    font_family = _configure_application(app)

    results = [capture_preview(app, capture, output_dir) for capture in captures]
    if include_lab_shell:
        results.append(capture_lab_shell(app, output_dir))

    manifest_path = output_dir / "manifest.json"
    manifest_path.write_text(
        json.dumps({"font_family": font_family, "captures": results}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return manifest_path


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Capture deterministic Dofus Atlas UI previews.")
    parser.add_argument("--request", type=Path, help="JSON capture request")
    parser.add_argument("--output-dir", type=Path, default=Path("artifacts/ui_lab"))
    parser.add_argument("--screen", help="Single screen key when no request JSON is supplied")
    parser.add_argument("--scenario", default=DEFAULT_SCENARIO)
    parser.add_argument("--width", type=int, default=DEFAULT_WIDTH)
    parser.add_argument("--height", type=int, default=DEFAULT_HEIGHT)
    parser.add_argument("--settle-ms", type=int, default=DEFAULT_SETTLE_MS)
    parser.add_argument("--segments", action="store_true")
    parser.add_argument("--full-scroll", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    if args.request is not None:
        manifest = run_request(args.request, args.output_dir)
        print(manifest)
        return 0
    if not args.screen:
        raise SystemExit("--request ou --screen est requis")

    app = QApplication.instance() or QApplication(sys.argv[:1])
    if not isinstance(app, QApplication):
        raise RuntimeError("Une QApplication est requise pour les captures UI Lab")
    font_family = _configure_application(app)
    result = capture_preview(
        app,
        CaptureSpec(
            screen=args.screen,
            scenario=args.scenario,
            width=args.width,
            height=args.height,
            settle_ms=args.settle_ms,
            capture_segments=bool(args.segments),
            capture_full_scroll=bool(args.full_scroll),
        ),
        args.output_dir,
    )
    manifest = args.output_dir / "manifest.json"
    manifest.write_text(
        json.dumps({"font_family": font_family, "captures": [result]}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(manifest)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
