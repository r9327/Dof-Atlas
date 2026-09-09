from __future__ import annotations

import argparse
import html
import json
import re
from html.parser import HTMLParser
from typing import Any
from urllib.parse import quote
from urllib.request import Request, urlopen

from .config import DEFAULT_CONFIG, LocalDataConfig, ensure_directories
from .utils import normalize_text, now_iso, save_json_atomic


SEARCH_URL = "https://www.gamosaurus.com/wp-json/wp/v2/search?search={query}&subtype=post&per_page=100"
USER_AGENT = "DofusAtlasLocalImporter/1.0"

FALLBACK_GUIDES = {
    "Alchimiste": "https://www.gamosaurus.com/jeux/dofus/dofus-unity-monter-alchimiste-200",
    "Bijoutier": "https://www.gamosaurus.com/jeux/dofus/dofus-unity-monter-bijoutier-200",
    "Bricoleur": "https://www.gamosaurus.com/jeux/dofus/dofus-unity-monter-bricoleur-200",
    "Bucheron": "https://www.gamosaurus.com/jeux/dofus/dofus-unity-monter-bucheron-200",
    "Chasseur": "https://www.gamosaurus.com/jeux/dofus/dofus-unity-monter-chasseur-200",
    "Cordonnier": "https://www.gamosaurus.com/jeux/dofus/dofus-unity-monter-cordonnier-200",
    "Faconneur": "https://www.gamosaurus.com/jeux/dofus/dofus-unity-monter-faconneur-200",
    "Forgeron": "https://www.gamosaurus.com/jeux/dofus/dofus-unity-monter-forgeron-200",
    "Mineur": "https://www.gamosaurus.com/jeux/dofus/dofus-unity-monter-mineur-200",
    "Paysan": "https://www.gamosaurus.com/jeux/dofus/dofus-unity-monter-paysan-200",
    "Pecheur": "https://www.gamosaurus.com/jeux/dofus/dofus-unity-monter-pecheur-200",
    "Sculpteur": "https://www.gamosaurus.com/jeux/dofus/dofus-unity-monter-sculpteur-200",
    "Tailleur": "https://www.gamosaurus.com/jeux/dofus/dofus-unity-monter-tailleur-200",
}


class TableExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.tables: list[list[list[str]]] = []
        self._table_depth = 0
        self._current_table: list[list[str]] = []
        self._current_row: list[str] = []
        self._current_cell: list[str] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.casefold()
        if tag == "table":
            self._table_depth += 1
            if self._table_depth == 1:
                self._current_table = []
        elif self._table_depth and tag == "tr":
            self._current_row = []
        elif self._table_depth and tag in {"td", "th"}:
            self._current_cell = []
        elif self._table_depth and tag == "br" and self._current_cell is not None:
            self._current_cell.append("\n")

    def handle_endtag(self, tag: str) -> None:
        tag = tag.casefold()
        if self._table_depth and tag in {"td", "th"} and self._current_cell is not None:
            cell = _clean("".join(self._current_cell))
            self._current_row.append(cell)
            self._current_cell = None
        elif self._table_depth and tag == "tr":
            if any(self._current_row):
                self._current_table.append(self._current_row)
            self._current_row = []
        elif tag == "table" and self._table_depth:
            if self._current_table:
                self.tables.append(self._current_table)
            self._current_table = []
            self._table_depth -= 1

    def handle_data(self, data: str) -> None:
        if self._table_depth and self._current_cell is not None:
            self._current_cell.append(data)


def _fetch_text(url: str) -> str:
    request = Request(url, headers={"User-Agent": USER_AGENT, "Accept": "text/html,application/json,*/*"})
    with urlopen(request, timeout=35) as response:
        data = response.read()
    return data.decode("utf-8", errors="replace")


def _clean(value: Any) -> str:
    text = html.unescape(str(value or "")).replace("\xa0", " ")
    text = re.sub(r"[ \t\r\f\v]+", " ", text)
    text = re.sub(r" *\n *", "\n", text)
    return text.strip()


def _parse_name_quantity(value: str) -> dict[str, Any]:
    text = _clean(value).replace(" x ", " x")
    match = re.match(r"(.+?)\s+x\s*([0-9 ]+)$", text, flags=re.IGNORECASE)
    if not match:
        return {"name": text, "quantity": 1}
    return {
        "name": _clean(match.group(1)),
        "quantity": int(match.group(2).replace(" ", "")),
    }


def _job_from_title(title: str) -> str:
    text = _clean(re.sub(r"<[^>]+>", "", title))
    match = re.search(r"Monter\s+(.+?)\s+200", text, flags=re.IGNORECASE)
    return _clean(match.group(1)) if match else text


def discover_guides() -> dict[str, str]:
    url = SEARCH_URL.format(query=quote("Monter Dofus Unity"))
    try:
        payload = json.loads(_fetch_text(url))
    except Exception:
        return dict(FALLBACK_GUIDES)

    guides: dict[str, str] = {}
    for entry in payload:
        title = _clean(entry.get("title", ""))
        link = entry.get("url") or ""
        if "Monter" not in title or "Dofus Unity" not in title or not link:
            continue
        guides[_job_from_title(title)] = link
    return guides or dict(FALLBACK_GUIDES)


def parse_guide(job: str, url: str) -> dict[str, Any]:
    document = _fetch_text(url)
    parser = TableExtractor()
    parser.feed(document)
    entries: list[dict[str, Any]] = []
    seen: set[tuple[str, str, int]] = set()
    for table in parser.tables:
        for row in table:
            if len(row) < 3:
                continue
            level_range = _clean(row[0])
            if not re.match(r"^\d+\s*-\s*\d+$", level_range):
                continue
            craft = _parse_name_quantity(row[1])
            resources: list[dict[str, Any]] = []
            for cell in row[2:]:
                for line in cell.splitlines():
                    line = _clean(line)
                    if line:
                        resources.append(_parse_name_quantity(line))
            key = (level_range, normalize_text(craft["name"]), int(craft["quantity"]))
            if key in seen:
                continue
            seen.add(key)
            entries.append(
                {
                    "level_range": level_range,
                    "craft": craft,
                    "resources": resources,
                }
            )
    return {
        "job": job,
        "url": url,
        "entry_count": len(entries),
        "entries": entries,
    }


def import_guides(config: LocalDataConfig = DEFAULT_CONFIG) -> dict[str, Any]:
    ensure_directories(config)
    guides = discover_guides()
    result = {
        "source": "gamosaurus",
        "imported_at": now_iso(),
        "offline_runtime": True,
        "guide_count": 0,
        "entry_count": 0,
        "guides": {},
        "errors": [],
    }
    for job, url in sorted(guides.items(), key=lambda item: normalize_text(item[0])):
        try:
            parsed = parse_guide(job, url)
        except Exception as exc:
            result["errors"].append({"job": job, "url": url, "error": str(exc)})
            continue
        result["guides"][job] = parsed
        result["guide_count"] += 1
        result["entry_count"] += parsed["entry_count"]

    output = config.raw_json_dir / "gamosaurus" / "metiers_leveling.json"
    save_json_atomic(output, result)
    return result


def main(argv: list[str] | None = None) -> dict[str, Any]:
    parser = argparse.ArgumentParser(description="Import Gamosaurus Dofus Unity profession leveling guides into local JSON")
    parser.parse_args(argv)
    report = import_guides(DEFAULT_CONFIG)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return report


if __name__ == "__main__":
    main()
