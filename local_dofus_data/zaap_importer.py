from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from .config import DEFAULT_CONFIG, LocalDataConfig, ensure_directories
from .data_store import DataStore
from .utils import now_iso, safe_int, save_json_atomic


DOFUSDB_API = "https://api.dofusdb.fr"

SUPPLEMENTAL_ZAAPS = [
    {"name": "Cite d'Astrub", "search": "Cite d'Astrub", "posX": 4, "posY": -19, "subareas": ["Astrub", "Cite d'Astrub"]},
    {"name": "Bonta", "search": "Bonta", "posX": -32, "posY": -56, "subareas": ["Bonta"]},
    {"name": "Brakmar", "search": "Brakmar", "posX": -26, "posY": 35, "subareas": ["Brakmar"]},
    {"name": "Chateau d'Amakna", "search": "Chateau d'Amakna", "posX": 3, "posY": -5, "subareas": ["Chateau d'Amakna"]},
    {"name": "Village d'Amakna", "search": "Village d'Amakna", "posX": -2, "posY": 0, "subareas": ["Village d'Amakna"]},
    {"name": "Sufokia", "search": "Sufokia", "posX": 13, "posY": 26, "subareas": ["Sufokia"]},
]


class ZaapImporter:
    def __init__(self, config: LocalDataConfig = DEFAULT_CONFIG, store: DataStore | None = None):
        self.config = config
        self.store = store

    def build(self, online: bool = False, include_supplemental: bool = True) -> dict[str, Any]:
        ensure_directories(self.config)
        subareas = self._load_subareas()
        subarea_by_id = {safe_int(row.get("id") or row.get("m_id")): row for row in subareas}
        grouped: dict[int, list[dict[str, Any]]] = {}
        for row in subareas:
            map_id = safe_int(row.get("associatedZaapMapId"))
            if map_id:
                grouped.setdefault(map_id, []).append(row)

        zaaps = []
        map_positions: dict[int, dict[str, Any]] = {}
        for map_id, rows in grouped.items():
            map_position = self._load_map_position(map_id)
            if not map_position and online:
                map_position = self._fetch_map_position_by_id(map_id)
            if map_position:
                map_positions[map_id] = map_position
            zaaps.append(self._entry_from_group(map_id, rows, map_position, subarea_by_id))

        if include_supplemental:
            for entry in SUPPLEMENTAL_ZAAPS:
                supplemental = dict(entry)
                map_position = None
                if online:
                    map_position = self._fetch_map_position_by_position(entry["posX"], entry["posY"])
                if map_position:
                    map_id = safe_int(map_position.get("id") or map_position.get("m_id"))
                    if map_id:
                        supplemental["mapId"] = map_id
                        map_positions[map_id] = map_position
                    supplemental["posX"] = safe_int(map_position.get("posX")) if map_position.get("posX") is not None else supplemental["posX"]
                    supplemental["posY"] = safe_int(map_position.get("posY")) if map_position.get("posY") is not None else supplemental["posY"]
                supplemental.setdefault("mapId", 0)
                supplemental["label"] = self._label(supplemental["name"], supplemental.get("posX"), supplemental.get("posY"))
                supplemental["source"] = "dofusdb_map_positions_supplemental" if map_position else "curated_dofus3_zaap_supplemental"
                zaaps.append(supplemental)

        zaaps = self._deduplicate(zaaps)
        report = {
            "source": "dofusdb_subareas_associatedZaapMapId",
            "offline_runtime": True,
            "online_import": bool(online),
            "generated_at": now_iso(),
            "count": len(zaaps),
            "zaaps": zaaps,
        }
        save_json_atomic(self.config.local_dir / "zaaps.json", report)
        save_json_atomic(
            self.config.reports_dir / "zaap_import_report.json",
            {
                "generated_at": report["generated_at"],
                "count": len(zaaps),
                "associated_source_count": len(grouped),
                "supplemental_count": len(SUPPLEMENTAL_ZAAPS) if include_supplemental else 0,
                "online_import": bool(online),
            },
        )
        self._write_maps(map_positions)
        return report

    def _entry_from_group(
        self,
        map_id: int,
        rows: list[dict[str, Any]],
        map_position: dict[str, Any] | None,
        subarea_by_id: dict[int | None, dict[str, Any]],
    ) -> dict[str, Any]:
        names = [self._name(row) for row in rows if self._name(row)]
        primary = names[0] if names else f"Zaap {map_id}"
        map_subarea_id = safe_int((map_position or {}).get("subAreaId"))
        if map_subarea_id in subarea_by_id:
            primary = self._name(subarea_by_id[map_subarea_id]) or primary
        pos_x = safe_int((map_position or {}).get("posX"))
        pos_y = safe_int((map_position or {}).get("posY"))
        return {
            "mapId": map_id,
            "name": primary,
            "label": self._label(primary, pos_x, pos_y),
            "search": primary,
            "posX": pos_x,
            "posY": pos_y,
            "subareas": sorted(set(names), key=str.casefold),
            "source": "dofusdb_subareas_associatedZaapMapId",
        }

    def _write_maps(self, map_positions: dict[int, dict[str, Any]]) -> None:
        if not self.store:
            return
        self.store.initialize()
        self.store.upsert_source(
            {
                "type": "dofusdb_map_positions",
                "name": "DofusDB map positions",
                "path": str(self.config.raw_json_dir / "api_static"),
                "status": "ok",
                "metadata_json": {"offline_runtime": True},
            }
        )
        for map_id, raw in map_positions.items():
            self.store.upsert_entity(
                "maps",
                {
                    "map_id": map_id,
                    "x": safe_int(raw.get("posX")),
                    "y": safe_int(raw.get("posY")),
                    "subarea_id": safe_int(raw.get("subAreaId")),
                    "source": "dofusdb_map_positions",
                    "metadata_json": {"raw": raw},
                },
                conflict_column="map_id",
            )

    def _load_subareas(self) -> list[dict[str, Any]]:
        path = self.config.raw_json_dir / "api_static" / "dofusdb_subareas.json"
        if path.exists():
            payload = json.loads(path.read_text(encoding="utf-8"))
            data = payload.get("data") if isinstance(payload, dict) else payload
            return [row for row in data if isinstance(row, dict)] if isinstance(data, list) else []
        if self.store:
            rows = self.store.query_all("SELECT metadata_json FROM subareas")
            loaded = []
            for row in rows:
                try:
                    raw = json.loads(row.get("metadata_json") or "{}").get("raw")
                    if isinstance(raw, dict):
                        loaded.append(raw)
                except Exception:
                    continue
            return loaded
        return []

    def _load_map_position(self, map_id: int) -> dict[str, Any] | None:
        path = self.config.raw_json_dir / "api_static" / f"dofusdb_map_position_{map_id}.json"
        if not path.exists():
            return None
        payload = json.loads(path.read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else None

    def _fetch_map_position_by_id(self, map_id: int) -> dict[str, Any] | None:
        try:
            return self._fetch_json(f"{DOFUSDB_API}/map-positions/{map_id}")
        except Exception:
            return None

    def _fetch_map_position_by_position(self, x: int, y: int) -> dict[str, Any] | None:
        query = urlencode({"$limit": 20, "posX": x, "posY": y})
        try:
            payload = self._fetch_json(f"{DOFUSDB_API}/map-positions?{query}")
        except Exception:
            return None
        rows = payload.get("data") if isinstance(payload, dict) else []
        if not isinstance(rows, list):
            return None
        rows = [row for row in rows if isinstance(row, dict)]
        if not rows:
            return None
        rows.sort(
            key=lambda row: (
                not bool(row.get("capabilityAllowTeleportTo")),
                not bool(row.get("capabilityAllowTeleportFrom")),
                safe_int(row.get("worldMap")) or 999,
                safe_int(row.get("id")) or 0,
            )
        )
        selected = rows[0]
        map_id = safe_int(selected.get("id") or selected.get("m_id"))
        if map_id:
            save_json_atomic(self.config.raw_json_dir / "api_static" / f"dofusdb_map_position_{map_id}.json", selected)
        return selected

    @staticmethod
    def _fetch_json(url: str) -> dict[str, Any]:
        request = Request(url, headers={"User-Agent": "Dofus Atlas local importer"})
        with urlopen(request, timeout=30) as response:
            payload = json.load(response)
        return payload if isinstance(payload, dict) else {}

    @staticmethod
    def _name(row: dict[str, Any]) -> str:
        value = row.get("name")
        if isinstance(value, dict):
            return str(value.get("fr") or value.get("en") or value.get("id") or "").strip()
        return str(row.get("name_fr") or row.get("name_en") or value or "").strip()

    @staticmethod
    def _label(name: str, x: Any, y: Any) -> str:
        if x is None or y is None:
            return str(name)
        return f"{name} [{x},{y}]"

    @staticmethod
    def _deduplicate(zaaps: list[dict[str, Any]]) -> list[dict[str, Any]]:
        best: dict[str, dict[str, Any]] = {}
        for zaap in zaaps:
            key = str(zaap.get("search") or zaap.get("name") or zaap.get("label") or "").casefold()
            if not key:
                continue
            current = best.get(key)
            if current is None or (not current.get("mapId") and zaap.get("mapId")):
                best[key] = zaap
        return sorted(best.values(), key=lambda row: str(row.get("label", "")).casefold())


def main(argv: list[str] | None = None) -> dict[str, Any]:
    parser = argparse.ArgumentParser(description="Build local Dofus 3 zaap index")
    parser.add_argument("--online", action="store_true", help="allow one-time DofusDB map-position lookup")
    parser.add_argument("--no-supplemental", action="store_true", help="do not add curated city zaaps")
    args = parser.parse_args(argv)
    store = DataStore(config=DEFAULT_CONFIG)
    report = ZaapImporter(DEFAULT_CONFIG, store=store).build(online=args.online, include_supplemental=not args.no_supplemental)
    store.close()
    print(json.dumps({"count": report["count"], "path": str(DEFAULT_CONFIG.local_dir / "zaaps.json")}, ensure_ascii=False, indent=2))
    return report


if __name__ == "__main__":
    main()
