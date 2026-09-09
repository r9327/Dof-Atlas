from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from app.modules.encyclopedia.services.guide_ultime_manual_route import load_manual_chapter


ROOT = Path(__file__).resolve().parents[1]
MANUAL = ROOT / "data" / "routes" / "guide_ultime_manual"
MANIFEST = MANUAL / "manifest_v1.json"


def resolved_counts() -> tuple[list[dict], int]:
    payload = json.loads(MANIFEST.read_text(encoding="utf-8"))
    canonical = payload.get("canonical") if isinstance(payload.get("canonical"), dict) else {}
    rows = [row for row in canonical.get("chapters", []) or [] if isinstance(row, dict)]
    rows.sort(key=lambda row: int(row.get("order") or 0))
    report: list[dict] = []
    total = 0
    for row in rows:
        filename = str(row.get("file") or "").strip()
        chapter = load_manual_chapter(MANUAL / filename)
        actual = len([stage for stage in chapter.get("stages", []) or [] if isinstance(stage, dict)])
        declared = int(row.get("stage_count") or 0)
        report.append(
            {
                "id": str(row.get("id") or ""),
                "file": filename,
                "declared": declared,
                "actual": actual,
                "ok": declared == actual,
            }
        )
        total += actual
    return report, total


def rewrite_manifest(report: list[dict], total: int) -> bool:
    text = MANIFEST.read_text(encoding="utf-8")
    original = text
    for item in report:
        chapter_id = re.escape(item["id"])
        actual = int(item["actual"])
        pattern = re.compile(
            rf'("id":"{chapter_id}"[^\n]*?"stage_count":)\d+'
        )
        text, count = pattern.subn(rf"\g<1>{actual}", text, count=1)
        if count != 1:
            raise RuntimeError(f"Impossible de mettre à jour stage_count pour {item['id']}")

    text = re.sub(
        r"stage_count total attendu=\d+",
        f"stage_count total attendu={total}",
        text,
    )
    if text == original:
        return False
    MANIFEST.write_text(text, encoding="utf-8", newline="\n")
    return True


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true", help="Corrige les compteurs du manifeste.")
    args = parser.parse_args()

    report, total = resolved_counts()
    mismatches = [item for item in report if not item["ok"]]
    for item in report:
        marker = "OK" if item["ok"] else "MISMATCH"
        print(
            f"{marker:8} {item['id']:18} {item['file']:28} "
            f"declared={item['declared']:>3} actual={item['actual']:>3}"
        )
    print(f"TOTAL_RESOLVED={total}")

    if args.write:
        changed = rewrite_manifest(report, total)
        print("MANIFEST_UPDATED=1" if changed else "MANIFEST_UPDATED=0")
        # Re-read after writing so a malformed replacement cannot be hidden.
        json.loads(MANIFEST.read_text(encoding="utf-8"))
        return 0

    return 1 if mismatches else 0


if __name__ == "__main__":
    raise SystemExit(main())
