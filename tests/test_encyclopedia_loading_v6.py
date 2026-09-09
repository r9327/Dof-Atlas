from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from app.modules.encyclopedia.providers.dofus_item_provider import DofusItemProvider
from app.modules.encyclopedia.providers.indexed_guide_provider import IndexedGuideProvider
from app.modules.encyclopedia.services.encyclopedia_service import EncyclopediaService


def test_dofus_item_none_does_not_materialize_catalog(tmp_path: Path) -> None:
    provider = DofusItemProvider(data_dir=tmp_path)

    assert provider.get_by_id(None) is None
    assert provider._loaded is False


def test_dofus_items_use_one_lazy_items_payload_for_catalog_and_effects(tmp_path: Path) -> None:
    def write_payload(relative_path: str, refs: list[dict]) -> None:
        path = tmp_path / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps({"references": {"RefIds": refs}}, ensure_ascii=False),
            encoding="utf-8",
        )

    language_path = tmp_path / "languages" / "fr.json"
    language_path.parent.mkdir(parents=True)
    language_path.write_text(
        json.dumps(
            {
                "entries": {
                    "100": "Dofus de test",
                    "101": "Description de test",
                    "200": "Dofus primordial",
                    "300": "+#1{{~1~2 à }}#2 vitalité",
                }
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    write_payload(
        "items.json",
        [
            {
                "rid": 1001,
                "data": {
                    "id": 1001,
                    "typeId": 23,
                    "nameId": 100,
                    "descriptionId": 101,
                    "level": 50,
                    "iconId": 9001,
                    "possibleEffects": [{"rid": 5001}],
                },
            },
            {"rid": 2001, "data": {"id": 2001, "typeId": 1, "name": "Ressource"}},
            {"rid": 7113, "data": {"id": 7113, "typeId": 23, "name": "Dofawa"}},
            {
                "rid": 5001,
                "data": {"effectId": 10, "diceNum": 1, "diceSide": 2},
            },
        ],
    )
    write_payload("item_types.json", [{"rid": 23, "data": {"id": 23, "nameId": 200}}])
    write_payload("effects.json", [{"rid": 10, "data": {"id": 10, "descriptionId": 300}}])

    provider = DofusItemProvider(data_dir=tmp_path)
    original_read_json = provider._read_json
    item_reads: list[Path] = []

    def track_read_json(path: Path, default):
        if path == tmp_path / "items.json":
            item_reads.append(path)
        return original_read_json(path, default)

    provider._read_json = track_read_json

    assert provider._loaded is False
    assert item_reads == []

    items = provider.load_all()

    assert item_reads == [tmp_path / "items.json"]
    assert len(items) == 1
    item = items[0]
    assert item.id == 1001
    assert item.original_id == 1001
    assert item.name == "Dofus de test"
    assert item.level == 50
    assert item.type_id == 23
    assert item.type_name == "Dofus primordial"
    assert item.description == "Description de test"
    assert item.icon_id == 9001
    assert item.effects == ("+1 à 2 vitalité",)
    assert item.raw["possibleEffects"] == [{"rid": 5001}]
    assert provider.get_by_id(1001) is item
    assert provider.get_by_id(2001) is None
    assert provider.get_by_id(7113) is None

    assert provider.load_all() == items
    assert item_reads == [tmp_path / "items.json"]


def test_encyclopedia_uses_indexed_guide_provider_by_default() -> None:
    service = EncyclopediaService()

    assert isinstance(service.guide_provider, IndexedGuideProvider)
    assert service.achievement_provider._loaded is False
    assert service.guide_provider._loaded is False


def test_indexed_guide_provider_reuses_hot_achievement_provider() -> None:
    achievement = SimpleNamespace(id=42, name="Succès test")

    class FakeAchievementProvider:
        _loaded = True
        data_dir = Path(".")

        @staticmethod
        def get_by_id(achievement_id: int):
            return achievement if int(achievement_id) == 42 else None

    provider = IndexedGuideProvider(
        quest_provider=object(),
        achievement_provider=FakeAchievementProvider(),
        dofus_item_provider=object(),
    )

    ref, available, errors = provider._resolve_entity(
        "achievement",
        42,
        {"title": ""},
    )

    assert available is True
    assert errors == []
    assert ref is not None
    assert ref.entity_type == "achievement"
    assert ref.entity_id == 42
    assert ref.label == "Succès test"
