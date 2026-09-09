from __future__ import annotations

import os
import sys
import json
from pathlib import Path


os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT_DIR))

from PIL import Image
from PySide6.QtWidgets import QApplication

from app.ui.world_scan_panel import WorldScanPanel
TARGET_IDS = {1, 2, 3, 10, 12, 13, 14, 15, 16, 18, 21, 28, 33, 34, 35, 37, 38, 40, 41}


def _raw_data(view: dict) -> dict:
    raw = view.get("raw_data") or {}
    if isinstance(raw, str):
        try:
            decoded = json.loads(raw)
        except json.JSONDecodeError:
            return {}
        return decoded if isinstance(decoded, dict) else {}
    return raw if isinstance(raw, dict) else {}


def main() -> int:
    app = QApplication.instance() or QApplication([])
    panel = WorldScanPanel()
    # The desktop page now loads DB/image data on a worker so navigation remains
    # responsive. This CLI validator intentionally builds/applies the same
    # snapshot synchronously because it needs deterministic data before printing.
    payload = panel._build_cartography_payload(
        {
            "mode": "reload",
            "view_key": panel.current_view_key,
            "push_history": False,
        }
    )
    panel._apply_cartography_payload(payload)
    print(f"panel_views={len(panel.views)}")
    print(f"menu_buttons={len(panel.world_buttons)}")
    print(f"current_view={panel.current_view_key}")
    for view in panel.views:
        raw = _raw_data(view)
        worldmap_id = int(raw.get("worldmap_id") or view.get("worldmap_id") or 0)
        if worldmap_id not in TARGET_IDS:
            continue
        asset_path = ROOT_DIR / str(view.get("asset_path") or raw.get("asset_path") or "")
        status = raw.get("asset_status", "")
        map_count = len(panel.service.get_maps_for_view(str(view.get("view_key") or "")))
        link_count = len(panel.service.get_links_for_view(str(view.get("view_key") or "")))
        size = "missing"
        if asset_path.exists():
            with Image.open(asset_path) as image:
                size = f"{image.width}x{image.height}"
        print(f"{worldmap_id:02d}|{view.get('view_key')}|{status}|{size}|maps={map_count}|links={link_count}")
    panel.close()
    panel.deleteLater()
    app.quit()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
