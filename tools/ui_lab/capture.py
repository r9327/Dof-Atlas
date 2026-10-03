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
DEFAULT_READY_TIMEOUT_MS = 15000
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


def _target_id(spec: CaptureSpec, name: str) -> int | None:
    value = spec.params.get(name)
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _target_ready(widget, spec: CaptureSpec) -> bool:
    if spec.screen == "encyclopedia.quests":
        quest_id = _target_id(spec, "quest_id")
        if quest_id is None:
            return True
        page = getattr(widget, "quest_page", None)
        detail = getattr(page, "quest_detail_view", None)
        return bool(
            page is not None
            and not bool(getattr(page, "_detail_pending", False))
            and int(getattr(detail, "current_quest_id", 0) or 0) == quest_id
        )

    if spec.screen == "encyclopedia.guides":
        quest_id = _target_id(spec, "quest_id")
        if quest_id is None:
            return True
        view = getattr(widget, "guides_view", None)
        detail = getattr(view, "quest_detail_view", None)
        return bool(
            view is not None
            and int(getattr(view, "current_quest_id", 0) or 0) == quest_id
            and int(getattr(detail, "current_quest_id", 0) or 0) == quest_id
        )

    if spec.screen == "encyclopedia.achievements":
        achievement_id = _target_id(spec, "achievement_id")
        if achievement_id is None:
            return True
        getter = getattr(widget, "get_achievements_view", None)
        view = getter() if callable(getter) else None
        return bool(
            view is not None
            and bool(getattr(view, "_detail_open", False))
            and int(getattr(view, "current_achievement_id", 0) or 0) == achievement_id
        )

    return True


def _wait_for_target_ready(
    app: QApplication,
    widget,
    spec: CaptureSpec,
    timeout_ms: int = DEFAULT_READY_TIMEOUT_MS,
) -> None:
    if _target_ready(widget, spec):
        return
    deadline = time.monotonic() + max(1, timeout_ms) / 1000.0
    while time.monotonic() < deadline:
        app.processEvents(QEventLoop.AllEvents, 50)
        if _target_ready(widget, spec):
            app.processEvents(QEventLoop.AllEvents, 50)
            return
        time.sleep(0.02)
    raise RuntimeError(
        f"La cible UI n'est pas devenue prête avant capture: {spec.screen} "
        f"scenario={spec.scenario} params={spec.params}"
    )


def _product_scroll_target(widget, spec: CaptureSpec) -> QAbstractScrollArea | None:
    if spec.screen == "encyclopedia.quests":
        page = getattr(widget, "quest_page", None)
        detail = getattr(page, "quest_detail_view", None)
        area = getattr(detail, "center_scroll", None)
        return area if isinstance(area, QAbstractScrollArea) else None

    if spec.screen == "encyclopedia.guides":
        view = getattr(widget, "guides_view", None)
        if view is None:
            return None
        if _target_id(spec, "quest_id") is not None:
            detail = getattr(view, "quest_detail_view", None)
            area = getattr(detail, "center_scroll", None)
        else:
            area = getattr(view, "center_scroll", None)
        return area if isinstance(area, QAbstractScrollArea) else None

    if spec.screen == "encyclopedia.achievements":
        getter = getattr(widget, "get_achievements_view", None)
        view = getter() if callable(getter) else None
        area = getattr(view, "detail_scroll", None)
        return area if isinstance(area, QAbstractScrollArea) else None

    if spec.screen == "organizer":
        area = getattr(widget, "sessions_area", None)
        return area if isinstance(area, QAbstractScrollArea) else None

    if spec.screen == "tools.crafts":
        area = getattr(widget, "global_scroll", None)
        return area if isinstance(area, QAbstractScrollArea) else None

    return None


def _scroll_target(widget, spec: CaptureSpec) -> QAbstractScrollArea | None:
    product_target = _product_scroll_target(widget, spec)
    if product_target is not None and product_target.isVisible():
        return product_target

    requested_name = str(spec.scroll_object_name or "").strip()
    if not requested_name:
        requested_name = str(widget.property("uiLabCaptureScrollTarget") or "").strip()
    if requested_name:
        matches = [
            area
            for area in widget.findChildren(QAbstractScrollArea, requested_name)
            if area.isVisible()
        ]
        if not matches:
            raise RuntimeError(f"Zone de scroll UI Lab introuvable ou invisible: {requested_name}")
        return max(matches, key=lambda area: int(area.verticalScrollBar().maximum()))

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


def _save_full_frame_stack(frames: list[QImage], path: Path) -> None:
    if not frames:
        raise RuntimeError(f"Aucune frame disponible pour la capture full: {path}")
    width = max(frame.width() for frame in frames)
    height = sum(frame.height() for frame in frames)
    if height > MAX_FULL_SCROLL_HEIGHT:
        raise RuntimeError(
            f"Capture full trop haute ({height}px > {MAX_FULL_SCROLL_HEIGHT}px) pour {path.name}"
        )
    full_image = QImage(width, height, QImage.Format_ARGB32)
    full_image.fill(0)
    painter = QPainter(full_image)
    try:
        y = 0
        for frame in frames:
            painter.drawImage(0, y, frame)
            y += frame.height()
    finally:
        painter.end()
    if not full_image.save(str(path), "PNG"):
        raise RuntimeError(f"Capture full impossible: {path}")


def _capture_long_view(
    app: QApplication,
    widget,
    spec: CaptureSpec,
    output_dir: Path,
    base_name: str,
) -> dict[str, Any]:
    if not (spec.capture_segments or spec.capture_full_scroll):
        return {}

    safe_base = _safe_slug(base_name)
    area = _scroll_target(widget, spec)
    if area is None or area.verticalScrollBar().maximum() <= 0:
        full_file: str | None = None
        if spec.capture_full_scroll:
            frame = widget.grab()
            if frame.isNull():
                raise RuntimeError(f"Capture full impossible pour {base_name}")
            full_file = f"{safe_base}-full.png"
            if not frame.save(str(output_dir / full_file), "PNG"):
                raise RuntimeError(f"Capture full impossible: {output_dir / full_file}")
        return {
            "scroll_target": None,
            "segments": [],
            "full_file": full_file,
            "scroll_range": 0,
            "full_scope": "full_window" if full_file else None,
        }

    bar = area.verticalScrollBar()
    original_value = int(bar.value())
    positions = _scroll_positions(area, spec.segment_overlap)
    segments: list[str] = []
    full_frames: list[QImage] = []
    full_file: str | None = None

    try:
        for index, position in enumerate(positions, 1):
            bar.setValue(position)
            _settle(app, min(max(80, spec.settle_ms // 4), 300))
            frame = widget.grab()
            if frame.isNull():
                raise RuntimeError(f"Capture segment impossible pour {base_name}")

            if spec.capture_segments:
                segment_name = f"{safe_base}-{index:02d}.png"
                segment_path = output_dir / segment_name
                if not frame.save(str(segment_path), "PNG"):
                    raise RuntimeError(f"Capture segment impossible: {segment_path}")
                segments.append(segment_name)

            if spec.capture_full_scroll:
                full_frames.append(frame.toImage())

        if spec.capture_full_scroll:
            full_file = f"{safe_base}-full.png"
            _save_full_frame_stack(full_frames, output_dir / full_file)
    finally:
        bar.setValue(original_value)
        _settle(app, 50)

    return {
        "scroll_target": str(area.objectName() or area.metaObject().className()),
        "segments": segments,
        "full_file": full_file,
        "scroll_range": int(bar.maximum()),
        "full_scope": "full_window_segments" if full_file else None,
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
            _wait_for_target_ready(app, widget, spec)
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
