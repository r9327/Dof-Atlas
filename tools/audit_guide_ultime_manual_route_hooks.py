from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.modules.encyclopedia.services.guide_ultime_manual_route import load_manual_chapter


MANUAL = ROOT / "data" / "routes" / "guide_ultime_manual"
MANIFEST = MANUAL / "manifest_v1.json"


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit des route_hooks/transversals du Guide Ultime manuel.")
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()

    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    canonical = manifest.get("canonical") if isinstance(manifest.get("canonical"), dict) else {}
    chapters = [row for row in canonical.get("chapters", []) or [] if isinstance(row, dict)]
    chapters.sort(key=lambda row: int(row.get("order") or 0))

    errors: list[dict[str, Any]] = []
    checked: list[dict[str, Any]] = []
    for meta in chapters:
        chapter_id = str(meta.get("id") or "").strip()
        filename = str(meta.get("file") or "").strip()
        if not filename:
            errors.append({"code": "missing_file", "chapter": chapter_id})
            continue
        try:
            payload = load_manual_chapter(MANUAL / filename)
        except Exception as exc:
            errors.append({
                "code": "chapter_resolution_failed",
                "chapter": chapter_id,
                "file": filename,
                "error": f"{type(exc).__name__}: {exc}",
            })
            continue

        stages = [row for row in payload.get("stages", []) or [] if isinstance(row, dict)]
        unresolved_tokens: list[dict[str, str]] = []
        for stage in stages:
            stage_id = str(stage.get("id") or "")
            for key in ("route_hooks",):
                raw = stage.get(key)
                values = raw if isinstance(raw, list) else [raw] if raw else []
                for value in values:
                    token = str(value or "").strip()
                    if token:
                        if not stage.get("route") and not stage.get("quests"):
                            unresolved_tokens.append({"stage": stage_id, "hook": token})
        if unresolved_tokens:
            errors.append({
                "code": "hook_without_concrete_payload",
                "chapter": chapter_id,
                "items": unresolved_tokens,
            })
        checked.append({
            "chapter": chapter_id,
            "file": filename,
            "stage_count": len(stages),
            "resolved_from": list(payload.get("_resolved_from", []) or []),
        })

    result = {
        "schema_version": 1,
        "status": "PASS" if not errors else "FAIL",
        "chapter_count": len(chapters),
        "checked": checked,
        "error_count": len(errors),
        "errors": errors,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if args.strict and errors:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
