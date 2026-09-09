from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

from app.modules.encyclopedia.services.quest_graph_service import QuestGraphService
from app.quest_catalog import QuestCatalog, QuestRecord, normalize_text


@dataclass(frozen=True, slots=True)
class QuestSeries:
    id: str
    name: str
    category: str
    quest_ids: tuple[int, ...]
    order: int = 0
    source: str = "achievement"


@dataclass(frozen=True, slots=True)
class QuestCategoryGroup:
    name: str
    series: tuple[QuestSeries, ...]


@dataclass(frozen=True, slots=True)
class QuestHierarchyPath:
    category: QuestCategoryGroup
    series: QuestSeries


class QuestHierarchy:
    def __init__(self, categories: tuple[QuestCategoryGroup, ...]) -> None:
        self.categories = categories
        self.series_by_id = {
            series.id: series
            for category in categories
            for series in category.series
        }
        paths: dict[int, list[QuestHierarchyPath]] = defaultdict(list)
        for category in categories:
            for series in category.series:
                path = QuestHierarchyPath(category, series)
                for quest_id in series.quest_ids:
                    paths[int(quest_id)].append(path)
        self.paths_by_quest = {quest_id: tuple(values) for quest_id, values in paths.items()}

    def path_for(self, quest_id: int, preferred_series_id: str = "") -> QuestHierarchyPath | None:
        paths = self.paths_by_quest.get(int(quest_id), ())
        if preferred_series_id:
            preferred = next((path for path in paths if path.series.id == preferred_series_id), None)
            if preferred is not None:
                return preferred
        if not paths:
            return None
        return min(
            paths,
            key=lambda path: (
                path.series.source != "achievement",
                len(path.series.quest_ids),
                path.series.order,
                normalize_text(path.category.name),
                normalize_text(path.series.name),
            ),
        )

    def neighbors(self, quest_id: int, series_id: str) -> tuple[int | None, int | None]:
        series = self.series_by_id.get(str(series_id))
        if series is None:
            return None, None
        try:
            index = series.quest_ids.index(int(quest_id))
        except ValueError:
            return None, None
        previous = series.quest_ids[index - 1] if index > 0 else None
        following = series.quest_ids[index + 1] if index + 1 < len(series.quest_ids) else None
        return previous, following


class QuestHierarchyService:
    """Build Category -> Suite -> Quest without inventing missing game data."""

    def __init__(self, catalog: QuestCatalog, graph: QuestGraphService) -> None:
        self.catalog = catalog
        self.graph = graph

    def build(self) -> QuestHierarchy:
        series_rows: list[QuestSeries] = []
        covered: set[int] = set()
        for source in getattr(self.catalog, "achievement_series", ()):
            quest_ids = tuple(quest_id for quest_id in source.quest_ids if quest_id in self.catalog.by_id)
            if not quest_ids:
                continue
            category = display_category(source.category or self._majority_category(quest_ids))
            series_rows.append(
                QuestSeries(
                    id=f"achievement:{source.achievement_id}",
                    name=source.name,
                    category=category,
                    quest_ids=quest_ids,
                    order=source.order,
                    source="achievement",
                )
            )
            covered.update(quest_ids)

        fallback_groups: dict[tuple[str, str], list[int]] = defaultdict(list)
        for quest in self.catalog.quests:
            if quest.id in covered:
                continue
            raw_category = quest.category.strip() or "Autres quêtes"
            fallback_groups[(display_category(raw_category), raw_category)].append(int(quest.id))

        for (category, raw_category), quest_ids in fallback_groups.items():
            ordered_ids = tuple(self.graph.logical_order(quest_ids))
            if category == "Alignement" and normalize_text(raw_category).startswith("alignement_"):
                name = raw_category
            elif normalize_text(category) != normalize_text(raw_category):
                name = f"{raw_category} — sans suite identifiée"
            else:
                name = "Sans suite identifiée"
            series_rows.append(
                QuestSeries(
                    id=f"fallback:{normalize_text(category)}:{normalize_text(raw_category)}",
                    name=name,
                    category=category,
                    quest_ids=ordered_ids,
                    order=100_000,
                    source="fallback",
                )
            )

        grouped: dict[str, list[QuestSeries]] = defaultdict(list)
        for series in series_rows:
            grouped[series.category].append(series)
        categories = tuple(
            QuestCategoryGroup(
                name=category,
                series=tuple(sorted(rows, key=self._series_key)),
            )
            for category, rows in sorted(grouped.items(), key=lambda item: category_sort_key(item[0]))
        )
        return QuestHierarchy(categories)

    def _majority_category(self, quest_ids: tuple[int, ...]) -> str:
        counts: dict[str, int] = defaultdict(int)
        for quest_id in quest_ids:
            quest = self.catalog.by_id.get(int(quest_id))
            if quest is not None:
                counts[quest.category.strip()] += 1
        if not counts:
            return "Autres quêtes"
        return min(counts, key=lambda category: (-counts[category], normalize_text(category)))

    @staticmethod
    def _series_key(series: QuestSeries) -> tuple[bool, int, str, str]:
        return (
            series.source != "achievement",
            series.order,
            normalize_text(series.name),
            series.id,
        )


def display_category(value: str) -> str:
    label = str(value or "").strip() or "Autres quêtes"
    key = normalize_text(label)
    if key in {"ile_de_frigost", "frigost"}:
        return "Frigost"
    if key in {
        "dimensions_divines",
        "dimensions",
        "enutrosor",
        "srambad",
        "xelorium",
        "ecaflipus",
        "osavora",
    }:
        return "Dimensions"
    if key in {
        "bonta_et_brakmar",
        "bonta",
        "brakmar",
        "alignement_bonta",
        "alignement_brakmar",
        "alignement",
    }:
        return "Alignement"
    return label


def category_sort_key(category: str) -> tuple[int, str]:
    priorities = {
        "alignement": 0,
        "ile_des_wabbits": 1,
        "frigost": 2,
        "dimensions": 3,
    }
    key = normalize_text(category)
    return priorities.get(key, 100), key
