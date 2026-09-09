from __future__ import annotations

from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]

from app.constants import JOB_RESOURCE_GROUPS, REPORTS_DIR
from app.storage import (
    ZaapWidget,
    canonical_job_name,
    display_path,
    existing_route_path,
    item_id,
    key_sequence_to_hotkey,
    local_data_cache,
    local_image_path,
    normalize_key,
    parse_size_pair,
    read_zaap_button_ratios,
    read_zaap_favorites,
    route_path_for,
    save_zaap_button_ratios,
    save_zaap_favorites,
    score_match,
    write_json,
    zaap_search_min_score,
    zaap_search_score,
)
from app.windows_embed import hwnd_value
from app.pages.organizer_page import OrganizerPage
from app.pages.craft_page import CraftPage, CraftResourceDialog, ItemSetDialog, LevelingDialog, RouteDialog, RouteImageLabel
from app.pages.equipment_page import EquipmentPage
from app.pages.quests_page import QuestsPage
from app.modules.encyclopedia.views import EncyclopediaPage
from main import AtlasWindow, main

__all__ = [
    "AtlasWindow",
    "CraftPage",
    "CraftResourceDialog",
    "EncyclopediaPage",
    "EquipmentPage",
    "ItemSetDialog",
    "JOB_RESOURCE_GROUPS",
    "LevelingDialog",
    "OrganizerPage",
    "QuestsPage",
    "REPORTS_DIR",
    "ROOT_DIR",
    "RouteDialog",
    "RouteImageLabel",
    "ZaapWidget",
    "canonical_job_name",
    "display_path",
    "existing_route_path",
    "hwnd_value",
    "item_id",
    "key_sequence_to_hotkey",
    "local_data_cache",
    "local_image_path",
    "main",
    "normalize_key",
    "parse_size_pair",
    "read_zaap_button_ratios",
    "read_zaap_favorites",
    "route_path_for",
    "save_zaap_button_ratios",
    "save_zaap_favorites",
    "score_match",
    "write_json",
    "zaap_search_min_score",
    "zaap_search_score",
]

if __name__ == "__main__":
    raise SystemExit(main())
