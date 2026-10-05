from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from app.quest_source_index import JsonSourceMapping


def _write_json(path: Path, payload: object) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )


def test_object_mapping_streams_nested_unicode_and_escaped_values(tmp_path: Path) -> None:
    source = tmp_path / "mapping.json"
    _write_json(
        source,
        {
            "ignored": {"large": [1, 2, {"text": "brace } and comma ,"}]},
            "entries": {
                "clé-é": {
                    "text": "guillemet \" et accolade }",
                    "nested": [1, {"emoji": "éàç"}],
                },
                "plain": "valeur",
            },
            "tail": True,
        },
    )

    mapping = JsonSourceMapping(source, tmp_path / "cache", "entries")
    with patch.object(Path, "read_bytes", side_effect=AssertionError("full read forbidden")):
        assert len(mapping) == 2
        assert mapping["clé-é"]["nested"][1]["emoji"] == "éàç"
        assert mapping["plain"] == "valeur"
    mapping.close()


def test_doduda_array_streams_one_record_at_a_time(tmp_path: Path) -> None:
    source = tmp_path / "rows.json"
    _write_json(
        source,
        {
            "meta": {"version": 1},
            "RefIds": [
                {
                    "data": {
                        "id": 42,
                        "name": "Monstre, {test}",
                        "nested": {"quote": "\\\""},
                    }
                },
                {"data": {"id": 7, "items": ["a,b", "é"]}},
            ],
        },
    )

    rows = JsonSourceMapping(source, tmp_path / "cache", "RefIds", doduda=True)
    with patch.object(Path, "read_bytes", side_effect=AssertionError("full read forbidden")):
        assert set(rows) == {42, 7}
        assert rows[42]["name"] == "Monstre, {test}"
        assert rows[7]["items"] == ["a,b", "é"]
    rows.close()


def test_streaming_offset_cache_is_reused_without_rescanning(tmp_path: Path) -> None:
    source = tmp_path / "mapping.json"
    _write_json(source, {"entries": {"1": {"name": "A"}, "2": {"name": "B"}}})
    cache_root = tmp_path / "cache"

    first = JsonSourceMapping(source, cache_root, "entries")
    assert first["1"]["name"] == "A"
    first.close()
    assert list(cache_root.glob("source_*.json.gz"))

    second = JsonSourceMapping(source, cache_root, "entries")
    with patch.object(
        JsonSourceMapping,
        "_build_offsets",
        side_effect=AssertionError("offset cache should be reused"),
    ):
        assert second["2"]["name"] == "B"
    second.close()
