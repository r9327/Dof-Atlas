from __future__ import annotations

import copy
import json
import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.constants import DATA_DIR, RAW_QUEST_DATA_DIR
from app.modules.encyclopedia.models import Achievement, DofusItem
from app.modules.encyclopedia.providers import AchievementProvider, DofusItemProvider, QuestProvider
from app.modules.encyclopedia.providers.achievement_provider import safe_int
from app.modules.encyclopedia.services.guide_path_profiles import GuidePathResolver
from app.modules.encyclopedia.services.quest_graph_service import QuestClosure, QuestGraphService
from app.modules.encyclopedia.providers.guide_provider import (
    GUIDE_ALLOWED_CATEGORIES,
    GUIDE_CATALOG_FILE,
    GUIDES_DIR,
)
from app.quest_catalog import QuestRecord, doduda_rows, normalize_text, read_json_file

CATALOG_CATEGORIES = [
    {"id": "aventure", "label": "Aventure", "order": 10},
    {"id": "dofus", "label": "Dofus", "order": 20},
    {"id": "alignements", "label": "Alignements", "order": 30},
]

DOFUS_GUIDE_ORDER = [
    "dofus_argente",
    "dofus_cawotte",
    "dokoko",
    "dofus_emeraude",
    "dolmanax",
    "dofus_pourpre",
    "domakuro",
    "dorigami",
    "dofus_turquoise",
    "dofus_des_veilleurs",
    "dofoozbz",
    "dofus_des_glaces",
    "dofus_nebuleux",
    "dofus_abyssal",
    "dofus_ivoire",
    "dofus_ebene",
    "dofus_vulbis",
    "dofus_tachete",
    "dofus_dom_de_pin",
    "dofus_sylvestre",
    "dofus_du_cauchemar",
    "dokille",
]

ACHIEVEMENT_META_RE = re.compile(r"\bOA\s*=\s*(\d+)", re.IGNORECASE)
VERIFIED_GUIDE_SOURCES = {
    19629: {
        "url": "https://www.dofuspourlesnoobs.com/quetes-du-dofus-argente.html",
        "expected_quests": 58,
        "prepend_quests": ("L'anneau de tous les dangers", "Sous le regard des dieux"),
    },
    972: {
        "url": "https://www.dofuspourlesnoobs.com/dofus-cawotte.html",
        "expected_quests": 11,
        "achievement_ids": (989, 991),
        "external_prerequisite": "Un sage parmi les sages",
    },
    16061: {
        "url": "https://www.dofuspourlesnoobs.com/dofus-des-veilleurs.html",
        "expected_quests": 15,
    },
    18043: {
        "url": "https://www.dofuspourlesnoobs.com/quetes-du-dofus-abyssal.html",
        "expected_quests": 40,
    },
    7043: {
        "url": "https://www.dofuspourlesnoobs.com/dofus-des-glaces.html",
        "expected_quests": 72,
    },
}
AUDITED_GUIDE_IDS = frozenset(
    {
        "guide_complet",
        "alignement_bonta",
        "alignement_brakmar",
        *DOFUS_GUIDE_ORDER,
    }
)

AVENTURE_BLOCKS = [
    {
        "id": "premiers_pas",
        "title": "Premiers pas",
        "description": "Tutoriel local et premières actions du personnage.",
        "quests": [2502, 2545, 2511, 1629],
        "achievements": [8518],
    },
    {
        "id": "incarnam_depart",
        "title": "Incarnam : départ",
        "description": "Premier fil de quêtes menant vers Astrub.",
        "quests": [1631, 1632, 1634, 1635, 2004],
        "achievements": [1378],
    },
    {
        "id": "incarnam_services",
        "title": "Incarnam : services et milice",
        "description": "Branches parallèles utiles avant de quitter Incarnam.",
        "quests": [1639, 1640, 1641, 1642, 1643, 1644, 1645, 1646, 1647, 1648, 1649, 2512, 1650, 1651, 2513, 1637, 1633, 1638, 1655],
        "achievements": [1379, 1380, 649, 1381],
    },
    {
        "id": "astrub_citoyen",
        "title": "Astrub : bases du continent",
        "description": "Premiers succès de quêtes Astrub avec relations Doduda.",
        "quests": [1958, 1959, 2009, 1841, 1960, 1962, 1975, 1976, 1977, 1978, 1979, 1980, 1981, 1982, 1983],
        "achievements": [1678, 1671, 1673],
    },
    {
        "id": "astrub_branches",
        "title": "Astrub : branches complémentaires",
        "description": "Quêtes locales d'Astrub organisées par succès.",
        "quests": [1984, 1985, 1986, 1987, 1988, 1989, 1990, 1991, 1992, 1994, 718, 1996, 1998, 2000, 1999, 2007, 2008],
        "achievements": [1674, 1672, 1675, 1676],
    },
    {
        "id": "premiers_dofus",
        "title": "Premiers Dofus",
        "description": "Jalons locaux menant au Dofus Argenté et aux premières recherches de Dofus.",
        "quests": [2192, 2193, 2194, 2195, 1462],
        "achievements": [1036, 1679],
    },
    {
        "id": "tour_du_monde",
        "title": "Tour du Monde intégré",
        "description": "Chaîne de donjons conservée comme section du parcours complet.",
        "quests": [2005, 2006, 153, 154, 155, 156, 157, 893],
        "achievements": [559],
    },
]


@dataclass(slots=True)
class DofusGuideCandidate:
    item: DofusItem
    achievement: Achievement | None = None
    linked_quests: list[int] = field(default_factory=list)
    quest_groups: list[tuple[int, str, list[int]]] = field(default_factory=list)
    expected_quests: int | None = None
    source_url: str = ""
    external_prerequisite_id: int | None = None
    root_achievement_ids: list[int] = field(default_factory=list)
    closure: QuestClosure | None = None
    accepted: bool = False
    reason: str = ""

    @property
    def guide_id(self) -> str:
        return _guide_id_from_title(self.item.name)


@dataclass(slots=True)
class GuideBuildResult:
    catalog: dict[str, Any]
    guides: dict[str, dict[str, Any]]
    report: dict[str, Any]


class GuideCatalogBuilder:
    def __init__(
        self,
        guides_dir: Path = GUIDES_DIR,
        data_dir: Path = RAW_QUEST_DATA_DIR,
        quest_provider: QuestProvider | None = None,
        achievement_provider: AchievementProvider | None = None,
        dofus_item_provider: DofusItemProvider | None = None,
    ) -> None:
        self.guides_dir = guides_dir
        self.data_dir = data_dir
        self.quest_provider = quest_provider or QuestProvider(data_dir=data_dir)
        self.achievement_provider = achievement_provider or AchievementProvider(data_dir=data_dir, quest_provider=self.quest_provider)
        self.dofus_item_provider = dofus_item_provider or DofusItemProvider(data_dir=data_dir)
        self.quest_catalog = self.quest_provider.get_catalog()
        self.quests_by_id = self.quest_catalog.by_id
        self.path_resolver = GuidePathResolver(
            quest_provider=self.quest_provider,
            achievement_provider=self.achievement_provider,
        )
        self.quest_graph = QuestGraphService(
            quest_provider=self.quest_provider,
            achievement_provider=self.achievement_provider,
        )
        self._v4_audits: dict[str, dict[str, Any]] = {}
        self._existing_snapshot: dict[str, dict[str, Any]] = {}

    def build(self) -> GuideBuildResult:
        self._v4_audits = {}
        candidates = self._dofus_candidates()
        accepted = [candidate for candidate in candidates if candidate.accepted]
        generated_dofus = [self._dofus_guide_payload(candidate) for candidate in accepted]

        existing = self._existing_guide_payloads()
        self._existing_snapshot = copy.deepcopy(existing)
        dofus_bases: dict[str, dict[str, Any]] = {
            guide_id: payload
            for guide_id, payload in existing.items()
            if str(payload.get("category") or "") == "dofus"
        }
        # V4 always starts from the freshly generated route. Existing quest IDs
        # and pure information blocks are merged as audited local knowledge,
        # never used as a reason to keep a stale Dofus JSON wholesale.
        for payload in generated_dofus:
            guide_id = str(payload["id"])
            dofus_bases[guide_id] = self._merge_existing_dofus(payload, dofus_bases.get(guide_id))
        profiled_dofus, profile_report = self.path_resolver.enrich_all(dofus_bases)
        candidates_by_id = {candidate.guide_id: candidate for candidate in accepted}
        normalized_dofus: dict[str, dict[str, Any]] = {}
        for guide_id, payload in profiled_dofus.items():
            normalized_dofus[guide_id] = self._normalize_dofus_v4(
                payload,
                candidates_by_id.get(guide_id),
                profile_report.get(guide_id, {}),
            )

        generated_guides: dict[str, dict[str, Any]] = {
            "guide_complet": self._adventure_payload(accepted),
            **normalized_dofus,
            "alignement_bonta": self._alignment_payload("bonta"),
            "alignement_brakmar": self._alignment_payload("brakmar"),
        }
        guides = {**existing, **generated_guides}
        catalog = self._catalog_payload(guides)
        report = self._report_payload(guides, candidates)
        report["profiled_dofus"] = profile_report
        return GuideBuildResult(catalog=catalog, guides=guides, report=report)

    def write_missing(self, result: GuideBuildResult) -> list[str]:
        self.guides_dir.mkdir(parents=True, exist_ok=True)
        written: list[str] = []
        for guide_id, payload in result.guides.items():
            file_name = self._file_name_for_guide(guide_id)
            path = self.guides_dir / file_name
            if path.exists():
                continue
            _write_json(path, payload)
            written.append(str(path))
        catalog_path = self.guides_dir / GUIDE_CATALOG_FILE
        if catalog_path.exists():
            current = read_json_file(catalog_path, None)
            if current != result.catalog:
                backup = catalog_path.with_suffix(catalog_path.suffix + ".bak")
                shutil.copy2(catalog_path, backup)
                _write_json(catalog_path, result.catalog)
                written.append(str(catalog_path))
        else:
            _write_json(catalog_path, result.catalog)
            written.append(str(catalog_path))
        return written

    def write_dofus_v4(self, result: GuideBuildResult) -> list[str]:
        """Replace only category=dofus JSON files, with stable V4 backups.

        Aventure and Alignements payloads are deliberately never written by
        this operation. The catalog keeps its existing non-Dofus rows.
        """

        self.guides_dir.mkdir(parents=True, exist_ok=True)
        written: list[str] = []
        for guide_id, payload in sorted(result.guides.items()):
            if str(payload.get("category") or "") != "dofus":
                continue
            path = self.guides_dir / self._file_name_for_guide(guide_id)
            current = read_json_file(path, None) if path.exists() else None
            if isinstance(current, dict) and str(current.get("category") or "") not in {"", "dofus"}:
                raise RuntimeError(f"Refus d'écraser un guide non-Dofus: {path}")
            if current == payload:
                continue
            if path.exists():
                backup = path.with_suffix(path.suffix + ".bak_v4")
                if not backup.exists():
                    shutil.copy2(path, backup)
            _write_json(path, payload)
            written.append(str(path))

        catalog_path = self.guides_dir / GUIDE_CATALOG_FILE
        current_catalog = read_json_file(catalog_path, {}) if catalog_path.exists() else {}
        catalog = copy.deepcopy(current_catalog) if isinstance(current_catalog, dict) else {}
        catalog.setdefault("schema_version", result.catalog.get("schema_version", 1))
        catalog.setdefault("categories", copy.deepcopy(result.catalog.get("categories", CATALOG_CATEGORIES)))
        existing_rows = catalog.get("guides", []) if isinstance(catalog.get("guides"), list) else []
        preserved_rows = [
            copy.deepcopy(row)
            for row in existing_rows
            if isinstance(row, dict) and str(row.get("category") or "") != "dofus"
        ]
        dofus_rows = [
            copy.deepcopy(row)
            for row in result.catalog.get("guides", [])
            if isinstance(row, dict) and str(row.get("category") or "") == "dofus"
        ]
        catalog["guides"] = sorted(
            [*preserved_rows, *dofus_rows],
            key=lambda row: (_category_order(str(row.get("category") or "")), safe_int(row.get("order"), 9999) or 9999, str(row.get("id") or "")),
        )
        if current_catalog != catalog:
            if catalog_path.exists():
                backup = catalog_path.with_suffix(catalog_path.suffix + ".bak_v4")
                if not backup.exists():
                    shutil.copy2(catalog_path, backup)
            _write_json(catalog_path, catalog)
            written.append(str(catalog_path))
        return written

    def write_audited(self, result: GuideBuildResult) -> list[str]:
        """Write only the addendum-audited guides and their catalog entries."""

        self.guides_dir.mkdir(parents=True, exist_ok=True)
        written: list[str] = []
        for guide_id in sorted(AUDITED_GUIDE_IDS):
            payload = result.guides.get(guide_id)
            if payload is None:
                continue
            path = self.guides_dir / self._file_name_for_guide(guide_id)
            _write_json(path, payload)
            written.append(str(path))
        catalog_path = self.guides_dir / GUIDE_CATALOG_FILE
        catalog = dict(result.catalog)
        catalog["guides"] = [
            row
            for row in result.catalog.get("guides", [])
            if (self.guides_dir / str(row.get("file") or "")).is_file()
        ]
        _write_json(catalog_path, catalog)
        written.append(str(catalog_path))
        return written

    def _existing_guide_payloads(self) -> dict[str, dict[str, Any]]:
        guides: dict[str, dict[str, Any]] = {}
        if not self.guides_dir.is_dir():
            return guides
        for path in sorted(self.guides_dir.glob("*.json")):
            if path.name in {GUIDE_CATALOG_FILE, "manifest.json"}:
                continue
            payload = read_json_file(path, None)
            if not isinstance(payload, dict):
                continue
            guide_id = str(payload.get("id") or "").strip()
            if guide_id and payload.get("category") and isinstance(payload.get("sections"), list):
                guides[guide_id] = payload
        return guides

    def write_report(self, result: GuideBuildResult, path: Path | None = None) -> Path:
        target = path or DATA_DIR.parent / "artifacts" / "guides_build_report.json"
        _write_json(target, result.report)
        return target

    def _catalog_payload(self, guides: dict[str, dict[str, Any]]) -> dict[str, Any]:
        rows = []
        for payload in guides.values():
            status = str(payload.get("completeness_status") or "complete")
            enabled = status != "draft" and not payload.get("validation_errors")
            rows.append(
                {
                    "id": payload["id"],
                    "file": self._file_name_for_guide(payload["id"]),
                    "category": payload["category"],
                    "order": self._guide_order(payload),
                    "enabled": enabled,
                }
            )
        return {
            "schema_version": 1,
            "categories": CATALOG_CATEGORIES,
            "guides": sorted(rows, key=lambda row: (_category_order(row["category"]), row["order"], row["id"])),
        }

    def _adventure_payload(self, dofus_candidates: list[DofusGuideCandidate]) -> dict[str, Any]:
        linked_achievement_ids: list[int] = []
        sections: list[dict[str, Any]] = []
        for block in AVENTURE_BLOCKS:
            sections.append(self._section_from_quests_and_achievements(block))
            linked_achievement_ids.extend(int(value) for value in block.get("achievements", []))
        existing_ids = {
            int(step.get("entity_id"))
            for section in sections
            for step in section.get("steps", [])
            if step.get("type") == "quest" and safe_int(step.get("entity_id")) is not None
        }
        sections.extend(self._adventure_dofus_sections(dofus_candidates, existing_ids))
        linked_achievement_ids.extend(
            candidate.achievement.id
            for candidate in dofus_candidates
            if candidate.achievement is not None
        )
        return {
            "schema_version": 1,
            "id": "guide_complet",
            "title": "Aventure de zéro",
            "subtitle": "Parcours complet du niveau 1 au niveau 200",
            "category": "aventure",
            "description": "Parcours complet du niveau 1 au niveau 200, rempli avec les quêtes et succès Doduda actuellement reliables.",
            "recommended_level_min": 1,
            "recommended_level_max": 200,
            "reward_item_id": None,
            "illustration_item_id": None,
            "image": None,
            "linked_achievement_ids": sorted(set(linked_achievement_ids)),
            "completeness_status": "partial",
            "verified_steps": sum(len(section.get("steps", [])) for section in sections),
            "total_steps": sum(len(section.get("steps", [])) for section in sections),
            "validation_warnings": ["Parcours partiel : les arcs haut niveau seront étendus progressivement depuis les données locales."],
            "generation_source": "mixed",
            "sections": sections,
        }

    def _adventure_dofus_sections(
        self,
        candidates: list[DofusGuideCandidate],
        existing_ids: set[int],
    ) -> list[dict[str, Any]]:
        sections: list[dict[str, Any]] = []
        for candidate in candidates:
            quest_ids = [quest_id for quest_id in candidate.linked_quests if quest_id not in existing_ids]
            if not quest_ids or candidate.achievement is None:
                continue
            existing_ids.update(quest_ids)
            sections.append(
                {
                    "id": f"aventure_{candidate.guide_id}",
                    "title": candidate.item.name,
                    "description": f"Série locale partagée avec le guide {candidate.item.name}.",
                    "linked_achievement_ids": [candidate.achievement.id],
                    "steps": _quest_chain_steps(f"aventure_{candidate.guide_id}", quest_ids),
                }
            )
        return sections

    def _section_from_quests_and_achievements(self, block: dict[str, Any]) -> dict[str, Any]:
        steps: list[dict[str, Any]] = []
        previous_quest: int | None = None
        for quest_id in block.get("quests", []):
            if quest_id not in self.quests_by_id:
                continue
            step = _quest_step(block["id"], quest_id, previous_quest)
            steps.append(step)
            previous_quest = quest_id
        return {
            "id": f"aventure_{block['id']}",
            "title": block["title"],
            "description": block["description"],
            "linked_achievement_ids": [
                int(achievement_id)
                for achievement_id in block.get("achievements", [])
                if self.achievement_provider.get_by_id(int(achievement_id)) is not None
            ],
            "steps": steps,
        }

    def _dofus_candidates(self) -> list[DofusGuideCandidate]:
        dofus_items = {item.id: item for item in self.dofus_item_provider.load_all()}
        candidates_by_item: dict[int, DofusGuideCandidate] = {
            item.id: DofusGuideCandidate(item=item, accepted=False, reason="aucun succès fiable récompensant l'objet")
            for item in dofus_items.values()
        }
        for achievement in self.achievement_provider.load_all():
            reward_item_ids = [reward.entity_id for reward in achievement.rewards if reward.kind == "item" and reward.entity_id in dofus_items]
            for item_id in reward_item_ids:
                if item_id is None:
                    continue
                quest_groups = self._achievement_quest_groups(achievement.id)
                source = VERIFIED_GUIDE_SOURCES.get(int(item_id), {})
                root_achievement_ids = [int(achievement.id)]
                if source.get("achievement_ids"):
                    quest_groups = []
                    root_achievement_ids.extend(int(value) for value in source["achievement_ids"])
                    for root_achievement_id in source["achievement_ids"]:
                        quest_groups.extend(self._achievement_quest_groups(int(root_achievement_id)))
                prepend_names = tuple(source.get("prepend_quests") or ())
                prepended: list[int | None] = []
                if prepend_names:
                    prepended = [self._quest_id_by_name(name) for name in prepend_names]
                    if quest_groups and prepended:
                        first_id, first_title, first_quests = quest_groups[0]
                        quest_groups[0] = (
                            first_id,
                            first_title,
                            self._unique_quest_ids([quest_id for quest_id in prepended if quest_id is not None] + first_quests),
                        )
                external_prerequisite_id = self._quest_id_by_name(str(source.get("external_prerequisite") or ""))
                seed_quests = [quest_id for quest_id in prepended if quest_id is not None]
                if external_prerequisite_id is not None:
                    seed_quests.append(external_prerequisite_id)
                closure = self.quest_graph.prerequisite_closure(
                    seed_quests=seed_quests,
                    seed_achievements=self._unique_quest_ids(root_achievement_ids),
                )
                linked_quests = list(closure.ordered_quest_ids)
                candidate = DofusGuideCandidate(
                    item=dofus_items[int(item_id)],
                    achievement=achievement,
                    linked_quests=linked_quests,
                    quest_groups=quest_groups,
                    expected_quests=safe_int(source.get("expected_quests")),
                    source_url=str(source.get("url") or ""),
                    external_prerequisite_id=external_prerequisite_id,
                    root_achievement_ids=self._unique_quest_ids(root_achievement_ids),
                    closure=closure,
                )
                if not linked_quests:
                    candidate.reason = "aucune quête fiable liée au succès récompensant l'objet"
                else:
                    candidate.accepted = True
                    candidate.reason = "succès et quêtes Doduda reliés"
                current = candidates_by_item.get(int(item_id))
                if current is None or (candidate.accepted and not current.accepted) or (current.achievement is None and candidate.achievement is not None):
                    candidates_by_item[int(item_id)] = candidate
        return sorted(candidates_by_item.values(), key=lambda candidate: self._dofus_order(candidate))

    def _achievement_quest_groups(
        self,
        achievement_id: int,
        visited: set[int] | None = None,
    ) -> list[tuple[int, str, list[int]]]:
        seen = set() if visited is None else visited
        achievement_id = int(achievement_id)
        if achievement_id in seen:
            return []
        seen.add(achievement_id)
        achievement = self.achievement_provider.get_by_id(achievement_id)
        if achievement is None:
            return []
        groups: list[tuple[int, str, list[int]]] = []
        direct_ids: list[int] = []
        for objective in achievement.objectives:
            match = ACHIEVEMENT_META_RE.search(str(objective.criterion or ""))
            if match:
                groups.extend(self._achievement_quest_groups(int(match.group(1)), seen))
                continue
            ref = objective.entity_ref
            if ref is not None and ref.entity_type == "quest" and int(ref.entity_id) in self.quests_by_id:
                direct_ids.append(int(ref.entity_id))
        direct_ids = self._unique_quest_ids(direct_ids)
        if direct_ids:
            groups.insert(0, (achievement.id, achievement.name, direct_ids))
        return groups

    def _quest_id_by_name(self, name: str) -> int | None:
        key = normalize_text(name)
        if not key:
            return None
        matches = [quest.id for quest in self.quest_catalog.quests if normalize_text(quest.name) == key]
        return int(matches[0]) if len(matches) == 1 else None

    @staticmethod
    def _unique_quest_ids(values) -> list[int]:
        seen: set[int] = set()
        rows: list[int] = []
        for value in values:
            quest_id = int(value)
            if quest_id not in seen:
                seen.add(quest_id)
                rows.append(quest_id)
        return rows

    def _dofus_guide_payload(self, candidate: DofusGuideCandidate) -> dict[str, Any]:
        assert candidate.achievement is not None
        guide_id = candidate.guide_id
        item = candidate.item
        quest_levels = [self.quests_by_id[quest_id].level_min for quest_id in candidate.linked_quests if quest_id in self.quests_by_id]
        minimum_level = min(quest_levels + [item.level or 1])
        maximum_level = max(quest_levels + [item.level or minimum_level])
        if guide_id == "dofus_turquoise":
            minimum_level, maximum_level = 160, 200
        expected = candidate.expected_quests
        status = (
            "complete"
            if expected is not None and len(candidate.linked_quests) == expected
            else "partial"
        )
        closure = candidate.closure or self.quest_graph.prerequisite_closure(
            seed_achievements=candidate.root_achievement_ids or [candidate.achievement.id]
        )
        sections = [{
            "id": f"{guide_id}_v4_route",
            "title": "Parcours de quêtes",
            "description": f"Succès {candidate.achievement.name} • Récompense {item.name}.",
            "linked_achievement_ids": candidate.root_achievement_ids or [candidate.achievement.id],
            "steps": self._closure_steps(guide_id, closure),
        }]
        if guide_id == "dofus_cawotte":
            sections.append(
                {
                    "id": "dofus_cawotte_obtention",
                    "title": "Poil de Cawotte",
                    "description": "Obtention finale vérifiée après les deux succès de quêtes.",
                    "linked_achievement_ids": [candidate.achievement.id],
                    "steps": [
                        {
                            "id": "dofus_cawotte_obtention_finale",
                            "type": "info",
                            "title": "",
                            "content": (
                                "Après les deux succès de quêtes, terminer le Terrier du Wa Wabbit puis, "
                                "avant de quitter le donjon, parler au Gawdien du Dofus en portant la "
                                "Couronne, le Bâton et la Cape du Wa Wabbit."
                            ),
                            "optional": True,
                            "notes": candidate.source_url,
                            "prerequisites": [],
                        }
                    ],
                }
            )
        warnings = []
        if status == "partial":
            if expected is not None:
                warnings.append(f"Parcours partiel : {len(candidate.linked_quests)} quêtes locales positionnées sur {expected} annoncées par la source externe.")
            else:
                warnings.append("Parcours partiel : la complétude externe n'est pas démontrée.")
        if not item.image_path or not Path(item.image_path).exists():
            warnings.append("Image locale de l'objet manquante.")
        return {
            "schema_version": 1,
            "id": guide_id,
            "title": item.name,
            "category": "dofus",
            "description": f"Parcours local fondé sur le succès Doduda et ses méta-succès pour {item.name}.",
            "recommended_level_min": minimum_level,
            "recommended_level_max": maximum_level,
            "reward_item_id": item.id,
            "illustration_item_id": item.id,
            "image": None,
            "linked_achievement_ids": [candidate.achievement.id],
            "completeness_status": status,
            "verified_steps": sum(len(section["steps"]) for section in sections),
            "total_steps": sum(len(section["steps"]) for section in sections),
            "validation_warnings": warnings,
            "generation_source": "doduda",
            "source_urls": [candidate.source_url] if candidate.source_url else [],
            "sections": sections,
        }

    def _merge_existing_dofus(
        self,
        generated: dict[str, Any],
        current: dict[str, Any] | None,
    ) -> dict[str, Any]:
        if not isinstance(current, dict):
            return copy.deepcopy(generated)
        merged = copy.deepcopy(generated)
        generated_ids = set(self.path_resolver.collect_quest_ids(merged))
        current_ids = self.path_resolver.collect_quest_ids(current)
        preserved_ids = [quest_id for quest_id in current_ids if quest_id not in generated_ids]
        if preserved_ids:
            merged.setdefault("sections", []).append(
                {
                    "id": f"{merged['id']}_preserved_local",
                    "title": "Parcours local validé conservé",
                    "description": "Quêtes déjà auditées dans le guide local avant la régénération V4.",
                    "steps": [_quest_step(f"{merged['id']}_preserved", quest_id) for quest_id in preserved_ids],
                }
            )
        known_info_step_ids = {
            str(step.get("id") or "")
            for section in merged.get("sections", []) if isinstance(section, dict)
            for step in section.get("steps", []) if isinstance(step, dict) and step.get("type") == "info"
            if str(step.get("id") or "")
        }
        for section in current.get("sections", []) if isinstance(current.get("sections"), list) else []:
            if not isinstance(section, dict):
                continue
            if not self.path_resolver.collect_quest_ids(section) and section.get("steps"):
                copied = copy.deepcopy(section)
                copied["steps"] = [
                    step for step in copied.get("steps", [])
                    if isinstance(step, dict) and step.get("type") == "info"
                ]
                if not copied["steps"]:
                    continue
                step_ids = {
                    str(step.get("id") or "")
                    for step in copied["steps"] if str(step.get("id") or "")
                }
                if step_ids & known_info_step_ids:
                    continue
                merged.setdefault("sections", []).append(copied)
                known_info_step_ids.update(step_ids)
        merged["linked_achievement_ids"] = sorted(
            self.path_resolver.collect_achievement_ids(generated)
            | self.path_resolver.collect_achievement_ids(current)
        )
        merged["source_urls"] = list(
            dict.fromkeys(
                str(value)
                for value in [*generated.get("source_urls", []), *current.get("source_urls", [])]
                if str(value).strip()
            )
        )
        merged["validation_warnings"] = list(
            dict.fromkeys(
                str(value)
                for value in [*generated.get("validation_warnings", []), *current.get("validation_warnings", [])]
                if str(value).strip()
            )
        )
        return merged

    def _closure_steps(
        self,
        prefix: str,
        closure: QuestClosure,
        notes_by_quest: dict[int, str] | None = None,
    ) -> list[dict[str, Any]]:
        notes = notes_by_quest or {}
        steps: list[dict[str, Any]] = []
        for quest_id in closure.ordered_quest_ids:
            relation = "mandatory"
            if quest_id in closure.context_quests:
                relation = "context"
            elif quest_id in closure.optional_quests:
                relation = "alternative"
            step = _quest_step(
                prefix,
                quest_id,
                optional=relation != "mandatory",
                notes=notes.get(quest_id, ""),
            )
            step["prerequisites"] = [
                {"type": "quest", "entity_id": previous}
                for previous in closure.hard_prerequisites(quest_id)
            ]
            step["relation"] = relation
            context = closure.context_predecessors(quest_id)
            if context:
                step["context_quests"] = context
            groups = sorted(closure.quest_alternative_groups.get(quest_id, ()))
            if groups:
                step["alternative_groups"] = groups
            steps.append(step)
        return steps

    def _normalize_dofus_v4(
        self,
        payload: dict[str, Any],
        candidate: DofusGuideCandidate | None,
        profile_row: dict[str, Any],
    ) -> dict[str, Any]:
        guide_id = str(payload.get("id") or "")
        original = self._existing_snapshot.get(guide_id, {})
        before_rows = self._quest_rows(original)
        source_rows = self._quest_rows(payload)
        optional_ids = {
            int(step["entity_id"])
            for step in self._quest_steps(payload)
            if step.get("optional") and safe_int(step.get("entity_id")) is not None
        }
        context_ids = {
            int(step["entity_id"])
            for step in self._quest_steps(payload)
            if str(step.get("relation") or "") == "context" and safe_int(step.get("entity_id")) is not None
        }
        if candidate is not None and candidate.closure is not None:
            optional_ids.update(candidate.closure.optional_quests)
            context_ids.update(candidate.closure.context_quests)
        source_ids = set(source_rows)
        mandatory_ids = source_ids - optional_ids - context_ids
        achievement_ids = self.path_resolver.collect_achievement_ids(payload)
        if candidate is not None:
            achievement_ids.update(candidate.root_achievement_ids)
        closure = self.quest_graph.prerequisite_closure(
            seed_quests=mandatory_ids,
            seed_achievements=achievement_ids,
            seed_context_quests=context_ids,
            seed_optional_quests=optional_ids,
        )

        notes_by_quest: dict[int, str] = {}
        for step in self._quest_steps(payload):
            quest_id = safe_int(step.get("entity_id"))
            if quest_id is not None and str(step.get("notes") or "").strip():
                notes_by_quest.setdefault(int(quest_id), str(step.get("notes") or ""))
        info_sections: list[dict[str, Any]] = []
        seen_info_step_ids: set[str] = set()
        for section in payload.get("sections", []) if isinstance(payload.get("sections"), list) else []:
            if not isinstance(section, dict) or not section.get("steps") or self.path_resolver.collect_quest_ids(section):
                continue
            step_ids = {
                str(step.get("id") or "")
                for step in section.get("steps", []) if isinstance(step, dict) and str(step.get("id") or "")
            }
            if step_ids & seen_info_step_ids:
                continue
            copied = copy.deepcopy(section)
            copied["steps"] = [
                step for step in copied.get("steps", [])
                if isinstance(step, dict) and step.get("type") == "info"
            ]
            if copied["steps"]:
                info_sections.append(copied)
                seen_info_step_ids.update(
                    str(step.get("id") or "") for step in copied["steps"] if str(step.get("id") or "")
                )
        route_section = {
            "id": f"{guide_id}_v4_route",
            "title": "Parcours de quêtes",
            "description": "Ordre topologique issu des critères locaux Qf/Qa/Sc, sans dépendance d'affichage inventée.",
            "linked_achievement_ids": sorted(achievement_ids),
            "steps": self._closure_steps(guide_id, closure, notes_by_quest),
        }
        normalized = copy.deepcopy(payload)
        normalized.pop("parts", None)
        normalized["sections"] = [route_section, *info_sections]
        normalized["linked_achievement_ids"] = sorted(achievement_ids)
        normalized["verified_steps"] = len(closure.ordered_quest_ids)
        normalized["total_steps"] = len(closure.ordered_quest_ids) + sum(
            len(section.get("steps", [])) for section in info_sections
        )

        explicit_profile_ok = str(profile_row.get("status") or "").upper() == "OK"
        explicit_source_ok = bool(
            candidate is not None
            and candidate.expected_quests is not None
            and len(candidate.linked_quests) == candidate.expected_quests
        )
        graph_ok = not closure.invalid_quest_ids and not closure.invalid_achievement_ids and not closure.cycles
        complete = graph_ok and (explicit_profile_ok or explicit_source_ok)
        warnings = [
            str(value)
            for value in normalized.get("validation_warnings", [])
            if str(value).strip()
        ]
        if closure.invalid_quest_ids:
            warnings.append(f"V4: références de quêtes invalides: {sorted(closure.invalid_quest_ids)}")
        if closure.invalid_achievement_ids:
            warnings.append(f"V4: références de succès invalides: {sorted(closure.invalid_achievement_ids)}")
        if closure.cycles:
            warnings.append(f"V4: cycles de prérequis détectés: {closure.cycles}")
        if not complete:
            warnings.append("V4: complétude non démontrée par un profil attendu ou une source explicite.")
        normalized["completeness_status"] = "complete" if complete else "partial"
        normalized["validation_warnings"] = sorted(dict.fromkeys(warnings), key=normalize_text)
        source = str(normalized.get("generation_source") or "doduda")
        normalized["generation_source"] = source if source.endswith("+v4_graph") else f"{source}+v4_graph"
        normalized["graph_semantics"] = {
            "Qf": "prerequisite_completed",
            "Qa": "ordering_context_only",
            "Sc": "achievement_quest_expansion",
            "OR": "optional_alternatives",
        }

        after_rows = self._quest_rows(normalized)
        self._v4_audits[guide_id] = {
            "id": guide_id,
            "old_quest_count": len(set(before_rows)),
            "new_quest_count": len(set(after_rows)),
            "added_quest_ids": sorted(set(after_rows) - set(before_rows)),
            "removed_quest_ids": sorted(set(before_rows) - set(after_rows)),
            "old_warnings": [str(value) for value in original.get("validation_warnings", []) if str(value).strip()],
            "new_warnings": list(normalized["validation_warnings"]),
            "duplicates_before": len(before_rows) - len(set(before_rows)),
            "duplicates_after": len(after_rows) - len(set(after_rows)),
            "invalid_quest_references": sorted(closure.invalid_quest_ids),
            "invalid_achievement_references": sorted(closure.invalid_achievement_ids),
            "cycles": closure.cycles,
            "context_quests": sorted(closure.context_quests),
            "optional_quests": sorted(closure.optional_quests),
            "alternative_groups": closure.alternative_groups,
            "status_before": str(original.get("completeness_status") or "missing"),
            "status_after": normalized["completeness_status"],
        }
        return normalized

    @staticmethod
    def _quest_steps(payload: dict[str, Any]) -> list[dict[str, Any]]:
        return [
            step
            for section in payload.get("sections", []) if isinstance(section, dict)
            for step in section.get("steps", []) if isinstance(step, dict) and step.get("type") == "quest"
        ]

    @classmethod
    def _quest_rows(cls, payload: dict[str, Any]) -> list[int]:
        return [
            int(step["entity_id"])
            for step in cls._quest_steps(payload)
            if safe_int(step.get("entity_id")) is not None
        ]

    def _alignment_payload(self, side: str) -> dict[str, Any]:
        title = "Alignement Bonta" if side == "bonta" else "Alignement Brâkmar"
        ps_value = 1 if side == "bonta" else 2
        category_id = 9 if side == "bonta" else 10
        rows = self._alignment_rows(category_id, ps_value)
        required = [row for row in rows if not row["optional"]]
        sections: list[dict[str, Any]] = []
        for start, end, section_title in [
            (0, 19, "Rangs 1 à 20"),
            (20, 39, "Rangs 21 à 40"),
            (40, 59, "Rangs 41 à 60"),
            (60, 79, "Rangs 61 à 80"),
            (80, 99, "Rangs 81 à 100"),
        ]:
            # Keep exactly one canonical quest per alignment rank. Alternative
            # same-rank branches are not part of the 100-quest main spine.
            section_rows = [row for row in required if start <= row["rank"] <= end]
            steps = []
            for row in section_rows:
                previous = self._previous_alignment_quest(required, row["rank"])
                steps.append(
                    _quest_step(
                        f"alignement_{side}",
                        row["quest_id"],
                        previous,
                        optional=row["optional"],
                        notes=f"Rang {row['rank'] + 1} Doduda.",
                    )
                )
            sections.append(
                {
                    "id": f"alignement_{side}_{start + 1}_{end + 1}",
                    "title": section_title,
                    "description": f"Quêtes d'alignement {title.split()[-1]} rangs {start + 1} à {end + 1}.",
                    "steps": steps,
                }
            )

        # IMPORTANT: each Order is a separate section after the 100 main ranks.
        # GuideProvider derives guide.parts from these sections, therefore they
        # appear as three distinct tasks in the left Guide column.
        order_sections = self.path_resolver.alignment_order_sections(side)
        sections.extend(order_sections)
        unique_quest_ids = {
            int(step["entity_id"])
            for section in sections
            for step in section.get("steps", [])
            if step.get("type") == "quest" and safe_int(step.get("entity_id")) is not None
        }
        warnings = []
        if any(row["optional"] for row in rows):
            warnings.append("Les variantes alternatives de même rang ne sont pas comptées dans la trame principale de 100 quêtes.")
        warnings.append("Les trois Ordres sont des branches alternatives affichées séparément après l'alignement 100.")
        return {
            "schema_version": 1,
            "id": f"alignement_{side}",
            "title": title,
            "category": "alignements",
            "description": f"100 quêtes d'alignement {title.split()[-1]}, puis les trois Ordres séparés.",
            "recommended_level_min": 30,
            "recommended_level_max": 200,
            "reward_item_id": None,
            "illustration_item_id": None,
            "image": None,
            "completeness_status": "complete" if len(order_sections) == 3 else "partial",
            "verified_steps": len(unique_quest_ids),
            "total_steps": len(unique_quest_ids),
            "validation_warnings": warnings,
            "generation_source": "doduda+dpln_profile",
            "sections": sections,
        }

    def _alignment_rows(self, category_id: int, ps_value: int) -> list[dict[str, Any]]:
        quests = doduda_rows(self.data_dir / "quests.json")
        rows_by_rank: dict[int, list[tuple[int, QuestRecord]]] = {}
        for quest_id, row in quests.items():
            if safe_int(row.get("categoryId")) != category_id:
                continue
            criterion = str(row.get("startCriterion") or "")
            rank_match = re.search(r"\bPa\s*=\s*(\d+)\b", criterion)
            side_match = re.search(r"\bPs\s*=\s*(\d+)\b", criterion)
            if not rank_match or not side_match or safe_int(side_match.group(1)) != ps_value:
                continue
            quest = self.quest_provider.get_quest(quest_id)
            if quest is None:
                continue
            rows_by_rank.setdefault(int(rank_match.group(1)), []).append((quest_id, quest))
        rows: list[dict[str, Any]] = []
        for rank in sorted(rows_by_rank):
            candidates = sorted(rows_by_rank[rank], key=lambda pair: (pair[1].level_min, normalize_text(pair[1].name), pair[0]))
            for index, (quest_id, quest) in enumerate(candidates):
                rows.append({"rank": rank, "quest_id": quest_id, "name": quest.name, "optional": index > 0})
        return rows

    @staticmethod
    def _previous_alignment_quest(required_rows: list[dict[str, Any]], rank: int) -> int | None:
        previous = [row["quest_id"] for row in required_rows if row["rank"] < rank]
        return previous[-1] if previous else None

    def _report_payload(self, guides: dict[str, dict[str, Any]], candidates: list[DofusGuideCandidate]) -> dict[str, Any]:
        added = [candidate for candidate in candidates if candidate.accepted]
        refused = [candidate for candidate in candidates if not candidate.accepted]
        return {
            "schema_version": 2,
            "categories": [category["id"] for category in CATALOG_CATEGORIES],
            "guides_actifs": sorted(guides),
            "guides_dofus_ajoutes": [
                {
                    "id": candidate.guide_id,
                    "nom": candidate.item.name,
                    "item_id": candidate.item.id,
                    "achievement_id": candidate.achievement.id if candidate.achievement else None,
                    "quetes": candidate.linked_quests,
                    "image": candidate.item.image_path,
                }
                for candidate in added
            ],
            "guides_non_ajoutes": [
                {
                    "nom": candidate.item.name,
                    "categorie_prevue": "dofus",
                    "objet_trouve": candidate.item.id,
                    "succes_trouve": candidate.achievement.id if candidate.achievement else None,
                    "nombre_quetes_trouvees": len(candidate.linked_quests),
                    "raison_refus": candidate.reason,
                    "donnees_manquantes": ["quetes"] if not candidate.linked_quests else [],
                    "statut_propose": "draft",
                }
                for candidate in refused
            ],
            "v4_before_after": [self._v4_audits[guide_id] for guide_id in sorted(self._v4_audits)],
            "v4_summary": {
                "guides": len(self._v4_audits),
                "duplicates_after": sum(row["duplicates_after"] for row in self._v4_audits.values()),
                "invalid_quest_references": sum(len(row["invalid_quest_references"]) for row in self._v4_audits.values()),
                "invalid_achievement_references": sum(len(row["invalid_achievement_references"]) for row in self._v4_audits.values()),
                "cycles": sum(len(row["cycles"]) for row in self._v4_audits.values()),
            },
        }

    def _guide_order(self, payload: dict[str, Any]) -> int:
        category = str(payload.get("category") or "")
        if category == "aventure":
            return 10
        if category == "alignements":
            return 10 if payload.get("id") == "alignement_bonta" else 20
        guide_id = str(payload.get("id") or "")
        if guide_id in DOFUS_GUIDE_ORDER:
            return 10 + DOFUS_GUIDE_ORDER.index(guide_id) * 10
        item_level = safe_int(payload.get("recommended_level_min"), 9999) or 9999
        return 1000 + item_level

    def _dofus_order(self, candidate: DofusGuideCandidate) -> tuple[int, int, str]:
        guide_id = candidate.guide_id
        if guide_id in DOFUS_GUIDE_ORDER:
            return DOFUS_GUIDE_ORDER.index(guide_id), candidate.item.level or 9999, normalize_text(candidate.item.name)
        return 999, candidate.item.level or 9999, normalize_text(candidate.item.name)

    @staticmethod
    def _file_name_for_guide(guide_id: str) -> str:
        return f"{guide_id}.json"


def _guide_id_from_title(title: str) -> str:
    return normalize_text(title)


def _category_order(category: str) -> int:
    try:
        return list(GUIDE_ALLOWED_CATEGORIES).index(category)
    except ValueError:
        return 999


def _quest_chain_steps(prefix: str, quest_ids: list[int]) -> list[dict[str, Any]]:
    steps = []
    previous: int | None = None
    for quest_id in quest_ids:
        steps.append(_quest_step(prefix, quest_id, previous))
        previous = quest_id
    return steps


def _quest_step(prefix: str, quest_id: int, previous_quest_id: int | None = None, optional: bool = False, notes: str = "") -> dict[str, Any]:
    prerequisites = [{"type": "quest", "entity_id": previous_quest_id}] if previous_quest_id is not None else []
    return {
        "id": f"{prefix}_quest_{quest_id}",
        "type": "quest",
        "entity_id": int(quest_id),
        "optional": bool(optional),
        "notes": notes,
        "prerequisites": prerequisites,
    }


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)
