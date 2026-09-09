from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


Metadata = dict[str, Any]


@dataclass
class BaseEntity:
    id: int | None = None
    ankama_id: int | None = None
    gid: int | None = None
    name_fr: str = ""
    name_en: str = ""
    type: str = ""
    category: str = ""
    level: int | None = None
    source: str = ""
    image_path: str = ""
    metadata_json: Metadata = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Item(BaseEntity):
    family: str = ""


@dataclass
class Resource(BaseEntity):
    job_id: int | None = None
    job_name: str = ""


@dataclass
class Equipment(BaseEntity):
    set_id: int | None = None


@dataclass
class Consumable(BaseEntity):
    pass


@dataclass
class Recipe:
    id: int | None = None
    ankama_id: int | None = None
    result_item_id: int | None = None
    result_ankama_id: int | None = None
    result_name_fr: str = ""
    result_name_en: str = ""
    job_id: int | None = None
    job_name: str = ""
    level: int | None = None
    source: str = ""
    metadata_json: Metadata = field(default_factory=dict)


@dataclass
class RecipeIngredient:
    id: int | None = None
    recipe_id: int | None = None
    ingredient_item_id: int | None = None
    ingredient_ankama_id: int | None = None
    name_fr: str = ""
    name_en: str = ""
    quantity: int = 1
    type: str = ""
    level: int | None = None
    source: str = ""
    image_path: str = ""
    metadata_json: Metadata = field(default_factory=dict)


@dataclass
class Job(BaseEntity):
    is_recolt: bool | None = None


@dataclass
class Spell(BaseEntity):
    class_id: int | None = None


@dataclass
class ClassData(BaseEntity):
    pass


@dataclass
class Monster(BaseEntity):
    family_id: int | None = None
    area_id: int | None = None


@dataclass
class MonsterFamily(BaseEntity):
    pass


@dataclass
class MapData:
    id: int | None = None
    map_id: int | None = None
    x: int | None = None
    y: int | None = None
    area_id: int | None = None
    subarea_id: int | None = None
    neighbours_json: Metadata = field(default_factory=dict)
    source: str = ""
    metadata_json: Metadata = field(default_factory=dict)


@dataclass
class CellData:
    id: int | None = None
    map_id: int | None = None
    cell_id: int | None = None
    walkable: bool | None = None
    los: bool | None = None
    source: str = ""
    metadata_json: Metadata = field(default_factory=dict)


@dataclass
class Area(BaseEntity):
    pass


@dataclass
class SubArea(BaseEntity):
    area_id: int | None = None


@dataclass
class InteractiveElement(BaseEntity):
    map_id: int | None = None
    cell_id: int | None = None


@dataclass
class TextEntry:
    id: int | None = None
    text_id: int | None = None
    lang: str = "fr"
    text: str = ""
    source: str = ""
    metadata_json: Metadata = field(default_factory=dict)


@dataclass
class ImageAsset:
    id: int | None = None
    ankama_id: int | None = None
    item_ankama_id: int | None = None
    name: str = ""
    path: str = ""
    kind: str = "item"
    source: str = ""
    metadata_json: Metadata = field(default_factory=dict)


@dataclass
class Effect:
    id: int | None = None
    ankama_id: int | None = None
    name_fr: str = ""
    name_en: str = ""
    description_fr: str = ""
    description_en: str = ""
    type: str = ""
    category: str = "effect"
    source: str = ""
    metadata_json: Metadata = field(default_factory=dict)


@dataclass
class ItemEffect:
    id: int | None = None
    item_ankama_id: int | None = None
    effect_id: int | None = None
    effect_ankama_id: int | None = None
    effect_name_fr: str = ""
    value_int: int | None = None
    min_int: int | None = None
    max_int: int | None = None
    raw_order: int = 0
    source: str = ""
    metadata_json: Metadata = field(default_factory=dict)


@dataclass
class Condition:
    id: int | None = None
    owner_type: str = ""
    owner_ankama_id: int | None = None
    condition_type: str = ""
    expression: str = ""
    source: str = ""
    metadata_json: Metadata = field(default_factory=dict)


@dataclass
class DataSource:
    id: int | None = None
    name: str = ""
    type: str = ""
    path: str = ""
    version: str = ""
    status: str = "ok"
    metadata_json: Metadata = field(default_factory=dict)


@dataclass
class ImportReport:
    id: int | None = None
    source: str = ""
    status: str = "ok"
    started_at: str = ""
    finished_at: str = ""
    counts_json: Metadata = field(default_factory=dict)
    warnings_json: list[str] = field(default_factory=list)
    errors_json: list[str] = field(default_factory=list)
