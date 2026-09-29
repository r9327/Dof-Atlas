from __future__ import annotations

import argparse
import json
import re
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

from PySide6.QtCore import QEventLoop
from PySide6.QtWidgets import QApplication

from app.ui.theme import atlas_stylesheet
from tools.ui_lab.registry import DEFAULT_SCENARIO, PreviewSpec, get_preview, resolve_factory
from tools.ui_lab.screens import PreviewContext


DEFAULT_WIDTH = 1400
DEFAULT_HEIGHT = 900
DEFAULT_SETTLE_MS = 1000


@dataclass(frozen=True, slots=True)
class CaptureSpec:
    screen: str
    scenario: str = DEFAULT_SCENARIO
    width: int = DEFAULT_WIDTH
    height: int = DEFAULT_HEIGHT
    settle_ms: int = DEFAULT_SETTLE_MS


def _safe_slug(value: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9._-]+", "-", value.strip()).strip("-.")
    return slug or "capture"


def _settle(app: QApplication, milliseconds: int) -> None:
    deadline = time.monotonic() + max(0, milliseconds) / 1000.0
    while time.monotonic() < deadline:
        app.processEvents(QEventLoop.AllEvents, 50)
        time.sleep(0.01)
    app.processEvents(QEventLoop.AllEvents, 50)


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


def capture_preview(app: QApplication, spec: CaptureSpec, output_dir: Path) -> dict[str, Any]:
    preview = get_preview(spec.screen)
    _validate_capture(spec, preview)
    output_dir.mkdir(parents=True, exist_ok=True)
    filename = f"{_safe_slug(preview.key)}__{_safe_slug(spec.scenario)}.png"
    output_path = output_dir / filename
    status_messages: list[str] = []

    with TemporaryDirectory(prefix="dofus_atlas_ui_capture_") as sandbox:
        context = PreviewContext(
            sandbox_root=Path(sandbox),
            report_status=status_messages.append,
            scenario=spec.scenario,
        )
        widget = resolve_factory(preview)(context)
        try:
            widget.resize(spec.width, spec.height)
            widget.show()
            _settle(app, spec.settle_ms)
            pixmap = widget.grab()
            if pixmap.isNull() or not pixmap.save(str(output_path), "PNG"):
                raise RuntimeError(f"Capture PNG impossible: {output_path}")
        finally:
            widget.close()
            widget.deleteLater()
            app.processEvents(QEventLoop.AllEvents, 50)

    return {
        "screen": preview.key,
        "label": preview.label,
        "scenario": spec.scenario,
        "source": preview.source,
        "width": spec.width,
        "height": spec.height,
        "settle_ms": spec.settle_ms,
        "file": filename,
        "status_messages": status_messages,
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


def _capture_spec_from_dict(raw: dict[str, Any]) -> CaptureSpec:
    screen = str(raw.get("screen", "")).strip()
    if not screen:
        raise ValueError("Chaque capture doit renseigner 'screen'")
    return CaptureSpec(
        screen=screen,
        scenario=str(raw.get("scenario", DEFAULT_SCENARIO)),
        width=int(raw.get("width", DEFAULT_WIDTH)),
        height=int(raw.get("height", DEFAULT_HEIGHT)),
        settle_ms=int(raw.get("settle_ms", DEFAULT_SETTLE_MS)),
    )


def load_request(path: Path) -> tuple[list[CaptureSpec], bool]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("La requête UI Lab doit être un objet JSON")
    raw_captures = payload.get("captures")
    if not isinstance(raw_captures, list) or not raw_captures:
        raise ValueError("La requête UI Lab doit contenir une liste 'captures' non vide")
    captures = []
    for raw in raw_captures:
        if not isinstance(raw, dict):
            raise ValueError("Chaque entrée de 'captures' doit être un objet JSON")
        captures.append(_capture_spec_from_dict(raw))
    return captures, bool(payload.get("include_lab_shell", False))


def run_request(request_path: Path, output_dir: Path) -> Path:
    captures, include_lab_shell = load_request(request_path)
    app = QApplication.instance() or QApplication([])
    if not isinstance(app, QApplication):
        raise RuntimeError("Une QApplication est requise pour les captures UI Lab")
    app.setApplicationName("Dofus Atlas UI Capture")
    app.setStyleSheet(atlas_stylesheet())

    results = [capture_preview(app, capture, output_dir) for capture in captures]
    if include_lab_shell:
        results.append(capture_lab_shell(app, output_dir))

    manifest_path = output_dir / "manifest.json"
    manifest_path.write_text(
        json.dumps({"captures": results}, ensure_ascii=False, indent=2) + "\n",
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
    app.setApplicationName("Dofus Atlas UI Capture")
    app.setStyleSheet(atlas_stylesheet())
    result = capture_preview(
        app,
        CaptureSpec(
            screen=args.screen,
            scenario=args.scenario,
            width=args.width,
            height=args.height,
            settle_ms=args.settle_ms,
        ),
        args.output_dir,
    )
    manifest = args.output_dir / "manifest.json"
    manifest.write_text(json.dumps({"captures": [result]}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(manifest)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
