from __future__ import annotations

import json
import os
import sys
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
UNITYPY_VENDOR = ROOT_DIR / ".codex_deps" / "unitypy"
if UNITYPY_VENDOR.exists():
    sys.path.insert(0, str(UNITYPY_VENDOR))

import re

import UnityPy  # type: ignore
from UnityPy import config as unitypy_config  # type: ignore


unitypy_config.FALLBACK_UNITY_VERSION = "6000.0.0f1"


def main() -> int:
    local_app_data = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    bundle_path = (
        local_app_data
        / "Ankama"
        / "Dofus-dofus3"
        / "Dofus_Data"
        / "StreamingAssets"
        / "Content"
        / "Picto"
        / "Worldmaps"
        / "worldmap_assets_.bundle"
    )
    env = UnityPy.load(str(bundle_path))
    rows = []
    for key, item in env.container.items():
        obj = item if hasattr(item, "read") else getattr(item, "asset", item)
        path_id = getattr(obj, "path_id", "")
        rows.append({"key": str(key), "path_id": str(path_id), "item": type(item).__name__})
    print(json.dumps(rows[:500], ensure_ascii=False, indent=2))
    print(f"container_count={len(rows)}")

    catalog_path = bundle_path.with_name("catalog_1.0.bin")
    raw = catalog_path.read_bytes()
    string_re = re.compile(rb"[\x20-\x7e]{2,}")
    strings = [(m.start(), m.group(0).decode("ascii", "replace")) for m in string_re.finditer(raw)]
    for wanted in (1, 2, 3, 10, 12, 13, 14, 15, 16, 18, 21, 28, 33, 34, 35, 37, 38, 40, 41):
        needle = f"worldmaps/{wanted}"
        matches = [idx for idx, (_, text) in enumerate(strings) if text == needle]
        for idx in matches:
            start = max(0, idx - 12)
            end = min(len(strings), idx + 18)
            print(f"\n-- {needle} strings[{idx}] --")
            for pos, text in strings[start:end]:
                print(f"{pos:08d} {text}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
