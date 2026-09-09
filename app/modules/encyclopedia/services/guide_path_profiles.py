from __future__ import annotations

import copy
import json
import re
import unicodedata
from collections import defaultdict, deque
from dataclasses import dataclass
from typing import Any, Iterable

from app.constants import DATA_DIR
from app.modules.encyclopedia.providers.achievement_provider import safe_int
from app.quest_catalog import normalize_text


# The profiles below are deliberately conservative: they enumerate the route/success
# families that are actually mandatory for the Dofus, then resolve them against the
# LOCAL quest/achievement catalogue. We never invent quest IDs.

ORDER_QUEST_IDS: dict[str, dict[str, tuple[int, ...]]] = {
    "bonta": {
        "Ordre du Cœur Vaillant": (433, 109, 120, 421, 1916),
        "Ordre de l'Esprit Salvateur": (434, 111, 121, 423, 1917),
        "Ordre de l'Œil Attentif": (435, 110, 122, 425, 1918),
    },
    "brakmar": {
        "Ordre du Cœur Saignant": (436, 112, 123, 422, 1919),
        "Ordre de l'Esprit Malsain": (437, 114, 124, 424, 1920),
        "Ordre de l'Œil Putride": (438, 113, 125, 426, 1921),
    },
}

ORDER_QUESTS: dict[str, dict[str, tuple[str, ...]]] = {
    "bonta": {
        "Ordre du Cœur Vaillant": (
            "Apprentissage : Disciple de Ménalt",
            "Apprentissage : Écuyer",
            "Apprentissage : Chevalier de l'Espoir",
            "Apprentissage : Champion Merveilleux",
            "Apprentissage : Héros Légendaire",
        ),
        "Ordre de l'Esprit Salvateur": (
            "Apprentissage : Disciple de Jiva",
            "Apprentissage : Apprenti Éclairé",
            "Apprentissage : Adepte des Écrits",
            "Apprentissage : Maître des Parchemins",
            "Apprentissage : Gardien du Savoir",
        ),
        "Ordre de l'Œil Attentif": (
            "Apprentissage : Disciple de Silvosse",
            "Apprentissage : Espion silencieux",
            "Apprentissage : Chasseur de Rénégats",
            "Apprentissage : Assassin Suprême",
            "Apprentissage : Maître des Illusions",
        ),
    },
    "brakmar": {
        "Ordre du Cœur Saignant": (
            "Apprentissage : Disciple de Djaul",
            "Apprentissage : Surineur",
            "Apprentissage : Chevalier du Désespoir",
            "Apprentissage : Champion du Chaos",
            "Apprentissage : Héros de l'Apocalypse",
        ),
        "Ordre de l'Esprit Malsain": (
            "Apprentissage : Disciple d'Hécate",
            "Apprentissage : Apprenti Sombre",
            "Apprentissage : Adepte des Douleurs",
            "Apprentissage : Maître des Sévices",
            "Apprentissage : Gardien des Tortures",
        ),
        "Ordre de l'Œil Putride": (
            "Apprentissage : Disciple de Brumaire",
            "Apprentissage : Espion Sombre",
            "Apprentissage : Chasseur d'Âmes",
            "Apprentissage : Psychopathe",
            "Apprentissage : Maître des Ombres",
        ),
    },
}


@dataclass(frozen=True, slots=True)
class PathProfile:
    achievement_names: tuple[str, ...] = ()
    quest_names: tuple[str, ...] = ()
    quest_ids: tuple[int, ...] = ()
    dependency_guides: tuple[str, ...] = ()
    expected_exact: int | None = None
    expected_min: int | None = None
    expand_quest_prerequisites: bool = True
    use_enriched_prerequisites: bool = False
    external_requirements: tuple[str, ...] = ()
    source_url: str = ""


MOW_ALL = ("Mais où sont les Dofus ?",)
MOW_FIRST_FOUR = (
    "Le réceptacle des Dofus",
    "Un sage parmi les sages",
    "Protection divine",
    "Voir le Dark Vlad et mourir... ou pas",
)

NEBULEUX_SUCCESSES = (
    "Même pas malle",
    "Après les phorreurs, le réconfort",
    "Le roi et moi",
    "Raisons de retraite",
    "Sauvé par le gong",
    "Crache ton venin",
    "Le jeu du trône",
    "Les voleurs de Srambad",
    "Les temps qui courent",
    "Carpe Diem",
    "Les puits du fou",
    "Moments d'égarement",
    "D'un monde à l'autre",
    "Aux portes de la nuit",
    "Générations futures",
    "Par-delà les apparences",
)

CAUCHEMAR_SUCCESSES = (
    "Eliocalypse : Résonance",
    "La guerre éternelle",
    "Prisonniers de la mer",
    "Jugement dernier",
    "Je suis malade, complétement malade",
    "Eliocalypse : Résilience",
    "Eliocalypse : Réminiscence",
    "Démons et merveilles",
)

CAUCHEMAR_QUESTS = (
    "Les sentiers de la guerre",
    "Les quatre volontés",
    "L'avis de la Mort",
    "La guerre de Cania n'aura pas lieu",
    "Prise de conscience",
    "Toute possession dépossède",
    "Le chant du Pandamonium",
    "Le début de la fin",
    "Entretemps, une renaissance",
    "Le fléau de Burin",
    "Légende d'automne",
)

DOFOOZBZ_QUESTS = (
    "Ça barde là-haut",
    "Un problème de taille",
    "Le vol des bourdons",
    "Des petites bêtes qui font bzzzbz",
    "Têtes de ponte",
    "Dérive insectaire",
    "La proie des vérités",
    "Quand on la cherche, on finit par tomber dessus",
    "Devoir de réserve",
    "Trois cœurs, un roi",
    "Un hôte de marque",
    "L'union sacrée",
    "Destructeur de mondes",
)

EBENE_BLOCKERS = (
    "Mieux vaut ne pas se fier à la première impression",
    "Le fléau de Burin",
    "La colère des dieux",
    "Frappez, ami et entrez",
    "De Brikke et de Brokke",
    "Un pendule pour guider ses pas",
)

SYLVESTRE_REQUIRED_IDS = (
    1618,  # C'est tout Simple
    1619,  # Arak-haï en pagaille
    1620,  # Munster lève le mystère
    1621,  # L'art de la langue de bois
    2486,  # Les derniers d'entre nous
    2487,  # Cultures et turpitudes
    2488,  # Qui nous protège du Protecteur ?
    2489,  # Flovoraison
)


# Fixed local IDs are used only when the external route contains mandatory quests
# that are not represented by Doduda's achievement criteria. They were resolved
# against data/encyclopedia/quests/source_mapping.json from this project.
DOFOOZBZ_REQUIRED_IDS = (
    2515, 2520, 2516, 2521, 2522, 2523, 2517,
    2530, 2531, 2518, 2532, 2533, 2519,
)

GLACES_HIDDEN_REQUIRED_IDS = (
    615,  # Les monologues du vaccin
    577, 578, 628, 629, 579,  # L'essentiel est dans Lac Gelé
    556, 557, 558, 559, 560, 561, 562, 563, 564, 565,  # Développement durable (voie agriculture)
    1319, 1320, 1321, 1322,  # Les derniers rescapés
    1335, 1336, 1337, 1338, 1339,  # La vie de château
    678, 1286, 375, 583, 582, 581,  # L'âme de glace / sous-prérequis
)

EBENE_BLOCKER_IDS = (894, 1869, 1938, 2010, 2011, 2450)
VULBIS_BLOCKER_IDS = (2064, 2087)
TACHETE_SIDE_CHAIN_IDS = (2204, 2169, 2199, 2203, 2205, 2158)

PROFILES: dict[str, PathProfile] = {
    "dofus_argente": PathProfile(
        expected_exact=58,
        source_url="https://www.dofuspourlesnoobs.com/quetes-du-dofus-argente.html",
    ),
    "dofus_cawotte": PathProfile(
        expected_exact=16,
        source_url="https://www.dofuspourlesnoobs.com/dofus-cawotte.html",
    ),
    "dokoko": PathProfile(expected_exact=5),
    "dofus_emeraude": PathProfile(
        expected_exact=15,
        source_url="https://www.dofuspourlesnoobs.com/dofus-emeraude.html",
    ),
    "dolmanax": PathProfile(expected_exact=1),
    "dofus_pourpre": PathProfile(
        quest_names=("Comment perdre ses plumes",),
        expected_exact=16,
        source_url="https://www.dofuspourlesnoobs.com/quecirctes-du-dofus-pourpre.html",
    ),
    "domakuro": PathProfile(expected_exact=8),
    "dorigami": PathProfile(
        quest_names=MOW_FIRST_FOUR,
        dependency_guides=("domakuro",),
        expected_exact=17,
        source_url="https://www.dofuspourlesnoobs.com/maudite-disparition.html",
    ),
    "dofus_turquoise": PathProfile(expected_exact=17),
    "dofus_des_veilleurs": PathProfile(expected_exact=15),
    "dofoozbz": PathProfile(
        quest_ids=DOFOOZBZ_REQUIRED_IDS,
        expected_exact=13,
        source_url="https://www.dofuspourlesnoobs.com/dofoozbz.html",
    ),
    "dofus_des_glaces": PathProfile(
        quest_ids=GLACES_HIDDEN_REQUIRED_IDS,
        expected_exact=72,
        expand_quest_prerequisites=True,
        source_url="https://www.dofuspourlesnoobs.com/dofus-des-glaces.html",
    ),
    "dofus_nebuleux": PathProfile(
        expected_exact=101,
        source_url="https://www.dofuspourlesnoobs.com/quetes-du-dofus-nebuleux.html",
    ),
    "dofus_abyssal": PathProfile(expected_exact=40),
    "dofus_ivoire": PathProfile(
        expected_exact=17,
        external_requirements=(
            "Alignement 100 + rang 5 d'un Ordre : terminer Bonta OU Brâkmar puis les 5 quêtes de l'Ordre choisi. Voir le guide Alignement correspondant.",
        ),
        source_url="https://www.dofuspourlesnoobs.com/quecirctes-du-dofus-ivoire.html",
    ),
    "dofus_ebene": PathProfile(
        quest_ids=EBENE_BLOCKER_IDS,
        expected_min=29,
        expand_quest_prerequisites=True,
        source_url="https://www.dofuspourlesnoobs.com/quetes-du-dofus-ebene.html",
    ),
    "dofus_vulbis": PathProfile(
        quest_ids=VULBIS_BLOCKER_IDS,
        expected_min=10,
        expand_quest_prerequisites=True,
        source_url="https://www.dofuspourlesnoobs.com/quetes-du-dofus-vulbis.html",
    ),
    "dofus_tachete": PathProfile(
        quest_ids=TACHETE_SIDE_CHAIN_IDS,
        dependency_guides=("dorigami",),
        expected_min=26,
        source_url="https://www.dofuspourlesnoobs.com/quetes-du-dofus-tachete.html",
    ),
    "dofus_dom_de_pin": PathProfile(
        expected_min=270,
        expand_quest_prerequisites=True,
        use_enriched_prerequisites=True,
        external_requirements=(
            "Alignement 100 : la branche Bonta OU Brâkmar nécessaire à l'Ivoire reste dans le guide Alignement.",
        ),
        source_url="https://www.dofuspourlesnoobs.com/dom-de-pin.html",
    ),
    "dofus_sylvestre": PathProfile(
        quest_ids=SYLVESTRE_REQUIRED_IDS,
        dependency_guides=("dofus_dom_de_pin",),
        expected_min=278,
        expand_quest_prerequisites=True,
        use_enriched_prerequisites=True,
        external_requirements=(
            "Le parcours global dépasse 400 quêtes quand la branche Alignement 1→100 du Dom de Pin est développée. Elle reste dans le guide Alignement pour ne pas dupliquer Bonta ET Brâkmar.",
        ),
        source_url="https://www.dofuspourlesnoobs.com/quetes-du-dofus-sylvestre.html",
    ),
    "dofus_du_cauchemar": PathProfile(
        quest_names=CAUCHEMAR_QUESTS,
        dependency_guides=("dofus_argente",),
        expected_min=119,
        expand_quest_prerequisites=True,
        source_url="https://www.dofuspourlesnoobs.com/quetes-du-dofus-du-cauchemar.html",
    ),
    "dokille": PathProfile(
        quest_names=("Premier Contact", "Chasse aux Krokilles"),
        expected_exact=6,
        source_url="https://www.dofuspourlesnoobs.com/le-safari-des-acircmes.html",
    ),
}


# Simple aliases for punctuation/name drift in local data.
ACHIEVEMENT_ALIASES: dict[str, tuple[str, ...]] = {
    normalize_text("Je suis malade, complétement malade"): (
        "Je suis malade, complètement malade",
        "Je suis malade, complétement malade",
    ),
    normalize_text("Deux dragons entrent dans un bar..."): (
        "Deux dragons entrent dans un bar...",
        "Deux dragons entrent dans un bar",
    ),
}

QUEST_ALIASES: dict[str, tuple[str, ...]] = {
    normalize_text("La quête de l'oiseau du temps"): (
        "La quête de l'oiseau du temps",
        "La quete de l'oiseau du temps",
    ),
    normalize_text("Légende d'automne"): (
        "Légende d'automne",
        "Legende d'automne",
    ),
}


def _loose_name(value: Any) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(char for char in text if not unicodedata.combining(char))
    text = text.replace("’", "'").replace("œ", "oe").replace("Œ", "OE").casefold()
    return " ".join(re.findall(r"[a-z0-9]+", text))


class GuidePathResolver:
    def __init__(self, quest_provider: Any, achievement_provider: Any) -> None:
        self.quest_provider = quest_provider
        self.achievement_provider = achievement_provider
        self.quest_catalog = quest_provider.get_catalog()
        self.quest_by_id = dict(self.quest_catalog.by_id)
        self.achievements = list(achievement_provider.load_all())
        self.achievement_by_id = {int(row.id): row for row in self.achievements}
        self.quest_by_name: dict[str, list[Any]] = defaultdict(list)
        self.achievement_by_name: dict[str, list[Any]] = defaultdict(list)
        self.quest_by_loose_name: dict[str, list[Any]] = defaultdict(list)
        self.achievement_by_loose_name: dict[str, list[Any]] = defaultdict(list)
        self.quest_source_name_to_ids: dict[str, list[int]] = defaultdict(list)
        self.quest_source_loose_to_ids: dict[str, list[int]] = defaultdict(list)
        for quest in self.quest_catalog.quests:
            self.quest_by_name[normalize_text(quest.name)].append(quest)
            self.quest_by_loose_name[_loose_name(quest.name)].append(quest)
        for achievement in self.achievements:
            self.achievement_by_name[normalize_text(achievement.name)].append(achievement)
            self.achievement_by_loose_name[_loose_name(achievement.name)].append(achievement)
        mapping_path = DATA_DIR / "encyclopedia" / "quests" / "source_mapping.json"
        try:
            mapping_payload = json.loads(mapping_path.read_text(encoding="utf-8"))
        except Exception:
            mapping_payload = {}
        mapping_rows = mapping_payload.get("quests", {}) if isinstance(mapping_payload, dict) else {}
        if isinstance(mapping_rows, dict):
            for raw_id, row in mapping_rows.items():
                if not isinstance(row, dict):
                    continue
                qid = safe_int(row.get("quest_id"), safe_int(raw_id))
                name = str(row.get("name") or "").strip()
                if qid is None or qid not in self.quest_by_id or not name:
                    continue
                self.quest_source_name_to_ids[normalize_text(name)].append(int(qid))
                self.quest_source_loose_to_ids[_loose_name(name)].append(int(qid))
        self._load_enriched_prerequisites()

    def _load_enriched_prerequisites(self) -> None:
        self.enriched_quest_prerequisites: dict[int, set[int]] = defaultdict(set)
        path = DATA_DIR / "encyclopedia" / "quests" / "quests_enriched.json"
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return
        rows = payload.get("quests", {}) if isinstance(payload, dict) else {}
        if not isinstance(rows, dict):
            return
        for raw_id, row in rows.items():
            if not isinstance(row, dict):
                continue
            qid = safe_int(raw_id)
            if qid is None or qid not in self.quest_by_id:
                continue
            for value in row.get("prerequisites", []) or []:
                self.enriched_quest_prerequisites[int(qid)].update(
                    self._quest_ids_from_prerequisite_text(str(value or ""))
                )

    def _quest_ids_from_prerequisite_text(self, text: str) -> set[int]:
        normalized = normalize_text(text)
        loose = _loose_name(text)
        if not normalized and not loose:
            return set()
        result: set[int] = set()
        # Exact source-name resolution first.
        result.update(self.quest_source_name_to_ids.get(normalized, ()))
        result.update(self.quest_source_loose_to_ids.get(loose, ()))
        # DPLN prerequisite lines often contain prefixes such as "Quête :" or
        # "Avoir terminé ...". Match canonical quest titles only inside this
        # dedicated prerequisite field, longest names first to avoid pollution.
        if not result:
            candidates = sorted(
                self.quest_source_name_to_ids.items(),
                key=lambda item: len(item[0]),
                reverse=True,
            )
            padded = f"_{normalized}_"
            for name_key, ids in candidates:
                if len(name_key) < 8:
                    continue
                if f"_{name_key}_" in padded or normalized.endswith(name_key):
                    result.update(int(value) for value in ids)
        return {qid for qid in result if qid in self.quest_by_id}

    def _direct_quest_prerequisites(
        self,
        quest: Any,
        *,
        include_enriched: bool = False,
    ) -> set[int]:
        qrefs, _srefs = mandatory_references(str(getattr(quest, "start_criterion", "") or ""))
        result = set(qrefs)
        if include_enriched:
            result.update(self.enriched_quest_prerequisites.get(int(quest.id), set()))
        for value in getattr(quest, "prerequisites", ()) or ():
            result.update(self._quest_ids_from_prerequisite_text(str(value or "")))
        result.discard(int(quest.id))
        return {qid for qid in result if qid in self.quest_by_id}

    @staticmethod
    def collect_achievement_ids(value: Any) -> set[int]:
        result: set[int] = set()
        def walk(node: Any) -> None:
            if isinstance(node, dict):
                rows = node.get("linked_achievement_ids")
                if isinstance(rows, list):
                    for raw in rows:
                        qid = safe_int(raw)
                        if qid is not None:
                            result.add(int(qid))
                for child in node.values():
                    walk(child)
            elif isinstance(node, list):
                for child in node:
                    walk(child)
        walk(value)
        return result

    # --------------------------- public API ---------------------------

    def alignment_order_sections(self, side: str) -> list[dict[str, Any]]:
        rows = ORDER_QUEST_IDS.get(str(side), {})
        if len(rows) != 3:
            raise RuntimeError(f"Ordres inconnus pour {side!r}")
        sections: list[dict[str, Any]] = []
        for index, order_name in enumerate(sorted(rows, key=normalize_text), 1):
            quest_ids = [int(value) for value in rows[order_name]]
            missing_local = [qid for qid in quest_ids if qid not in self.quest_by_id]
            if missing_local:
                raise RuntimeError(f"{side} / {order_name}: quest_id locaux absents {missing_local}")
            if len(quest_ids) != 5 or len(set(quest_ids)) != 5:
                raise RuntimeError(f"{side} / {order_name}: 5 quêtes uniques attendues, obtenu {quest_ids}")
            sections.append(
                {
                    "id": f"alignement_{side}_ordre_{index}",
                    "title": order_name,
                    "description": "Quêtes de l'Ordre, rangs 1 à 5 (paliers alignement 20/40/60/80/100).",
                    "optional_branch": True,
                    "exclusive_group": f"alignement_{side}_ordres",
                    "steps": self._steps(f"alignement_{side}_ordre_{index}", quest_ids, optional=True),
                }
            )
        return sections

    def enrich_all(self, base_guides: dict[str, dict[str, Any]]) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
        resolved: dict[str, dict[str, Any]] = {}
        report: dict[str, dict[str, Any]] = {}
        resolving: set[str] = set()

        def build_one(guide_id: str) -> dict[str, Any]:
            if guide_id in resolved:
                return resolved[guide_id]
            original = base_guides.get(guide_id)
            if original is None:
                raise KeyError(guide_id)
            if guide_id in resolving:
                raise RuntimeError(f"Dépendance circulaire de guide: {guide_id}")
            resolving.add(guide_id)
            try:
                payload, row = self.enrich_guide(
                    guide_id,
                    original,
                    dependency_loader=build_one,
                )
            except Exception as exc:
                payload = copy.deepcopy(original)
                payload.pop("parts", None)
                payload["completeness_status"] = "partial"
                warnings = [str(value) for value in payload.get("validation_warnings", []) if str(value).strip()]
                warnings.append(f"Profil de parcours non résolu: {exc}")
                payload["validation_warnings"] = list(dict.fromkeys(warnings))
                row = {
                    "before": len(self.collect_quest_ids(original)),
                    "after": len(self.collect_quest_ids(payload)),
                    "status": "PARTIEL",
                    "error": str(exc),
                }
            finally:
                resolving.discard(guide_id)
            resolved[guide_id] = payload
            report[guide_id] = row
            return payload

        for guide_id in base_guides:
            if guide_id in PROFILES:
                build_one(guide_id)
            else:
                resolved[guide_id] = copy.deepcopy(base_guides[guide_id])
        return resolved, report

    def enrich_guide(
        self,
        guide_id: str,
        original: dict[str, Any],
        dependency_loader: Any,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        profile = PROFILES.get(guide_id)
        payload = copy.deepcopy(original)
        payload.pop("parts", None)  # IMPORTANT: GuideProvider must derive visible parts from the new sections.
        before_ids = self.collect_quest_ids(original)
        if profile is None:
            return payload, {"before": len(before_ids), "after": len(before_ids), "status": "UNCHANGED"}

        base_sections = copy.deepcopy(payload.get("sections", [])) if isinstance(payload.get("sections"), list) else []
        section_rows: list[dict[str, Any]] = []
        used: set[int] = set()
        unresolved: list[str] = []

        # Dependency guides are expanded first so shared quest progress is visible in this guide too.
        for dependency_id in profile.dependency_guides:
            try:
                dependency_payload = dependency_loader(dependency_id)
            except Exception as exc:
                unresolved.append(f"dépendance {dependency_id}: {exc}")
                continue
            if str(dependency_payload.get("completeness_status") or "").casefold() != "complete":
                unresolved.append(f"dépendance {dependency_id}: guide encore partiel")
            dep_ids = self.collect_quest_ids(dependency_payload)
            fresh = [qid for qid in dep_ids if qid not in used]
            if fresh:
                used.update(fresh)
                section_rows.append(self._quest_section(
                    f"{guide_id}_dependency_{dependency_id}",
                    f"Prérequis — {dependency_payload.get('title') or dependency_id}",
                    fresh,
                ))

        # Preserve the currently known direct guide route, but de-duplicate it against dependencies.
        for index, section in enumerate(base_sections, 1):
            section_ids = self.collect_quest_ids(section)
            fresh = [qid for qid in section_ids if qid not in used]
            if not fresh:
                # Keep pure info sections.
                if not section_ids and section.get("steps"):
                    copied = copy.deepcopy(section)
                    copied["id"] = f"{guide_id}_base_info_{index}"
                    section_rows.append(copied)
                continue
            used.update(fresh)
            section_rows.append(self._quest_section(
                f"{guide_id}_base_{index}",
                str(section.get("title") or "Quêtes"),
                fresh,
                linked_achievement_ids=section.get("linked_achievement_ids", []),
            ))

        # The guide's own linked success IDs are the canonical roots. This is
        # what fixes routes such as Nébuleux: success 1188 recursively exposes
        # all 101 mandatory quests even when translated achievement names are
        # unavailable in a lightweight/offline catalogue.
        root_achievement_ids = self.collect_achievement_ids(original)

        # Named successes are optional enrichment only; inability to translate
        # a success name must never invalidate a route already proven by IDs.
        for achievement_name in profile.achievement_names:
            try:
                achievement = self.resolve_achievement(achievement_name)
            except Exception:
                continue
            root_achievement_ids.add(int(achievement.id))

        # Curated mandatory quest blockers. Fixed IDs come from this project's
        # source_mapping.json; names remain for readable/source-driven blockers.
        named_ids: list[int] = []
        for raw_id in profile.quest_ids:
            qid = int(raw_id)
            if qid not in self.quest_by_id:
                unresolved.append(f"quest_id obligatoire absent du catalogue: {qid}")
                continue
            if qid not in used and qid not in named_ids:
                named_ids.append(qid)
        for quest_name in profile.quest_names:
            try:
                qid = int(self.resolve_quest(quest_name).id)
            except Exception as exc:
                unresolved.append(f"quête {quest_name}: {exc}")
                continue
            if qid not in used and qid not in named_ids:
                named_ids.append(qid)
        if named_ids:
            used.update(named_ids)
            section_rows.insert(0, self._quest_section(
                f"{guide_id}_named_prerequisites",
                "Prérequis obligatoires",
                named_ids,
            ))

        # Boolean-aware recursive Qf/Sc/OA closure only on profiles that really need it.
        if profile.expand_quest_prerequisites:
            closure_quests, closure_achievements = self._mandatory_closure(
                set(used),
                seed_achievements=root_achievement_ids,
                include_enriched=profile.use_enriched_prerequisites,
            )
            missing = [qid for qid in self._topological_order(closure_quests) if qid not in used]
            if missing:
                used.update(missing)
                section_rows.insert(0, self._quest_section(
                    f"{guide_id}_recursive_prerequisites",
                    "Prérequis de quêtes",
                    missing,
                ))
            # Success prerequisites discovered from quests are also expanded into leaf groups.
            for achievement_id in sorted(closure_achievements):
                achievement = self.achievement_by_id.get(achievement_id)
                if achievement is None:
                    continue
                for child_id, title, ids in self._achievement_leaf_groups(achievement):
                    fresh = [qid for qid in ids if qid not in used]
                    if fresh:
                        used.update(fresh)
                        section_rows.insert(0, self._quest_section(
                            f"{guide_id}_criterion_achievement_{child_id}",
                            f"Prérequis — {title}",
                            fresh,
                            linked_achievement_ids=[child_id],
                        ))

        for index, text in enumerate(profile.external_requirements, 1):
            section_rows.append(
                {
                    "id": f"{guide_id}_external_requirement_{index}",
                    "title": "Prérequis externe",
                    "description": "",
                    "steps": [
                        {
                            "id": f"{guide_id}_external_requirement_{index}_info",
                            "type": "info",
                            "title": "",
                            "content": text,
                            "optional": True,
                            "notes": "",
                            "prerequisites": [],
                        }
                    ],
                }
            )

        after_ids = self.collect_quest_ids({"sections": section_rows})
        after_count = len(after_ids)
        count_ok = True
        count_message = ""
        if profile.expected_exact is not None and after_count != profile.expected_exact:
            count_ok = False
            count_message = f"{after_count}/{profile.expected_exact} quêtes attendues"
        elif profile.expected_min is not None and after_count < profile.expected_min:
            count_ok = False
            count_message = f"{after_count}/{profile.expected_min} quêtes minimum attendues"

        complete = count_ok and not unresolved
        warnings = [
            str(value)
            for value in payload.get("validation_warnings", [])
            if str(value).strip() and not str(value).startswith("Profil DPLN:")
        ]
        if not complete:
            details = "; ".join([value for value in [count_message, *unresolved] if value])
            warnings.append(f"Profil DPLN: parcours encore partiel ({details or 'validation incomplète'}).")
        else:
            warnings.append("Profil DPLN: parcours obligatoire résolu dans le catalogue local.")

        payload["sections"] = section_rows
        payload["verified_steps"] = after_count
        payload["total_steps"] = after_count
        payload["completeness_status"] = "complete" if complete else "partial"
        payload["validation_warnings"] = list(dict.fromkeys(warnings))
        payload["generation_source"] = "doduda+dpln_profile"
        source_urls = [str(value) for value in payload.get("source_urls", []) if str(value).strip()]
        if profile.source_url and profile.source_url not in source_urls:
            source_urls.append(profile.source_url)
        if source_urls:
            payload["source_urls"] = source_urls

        row = {
            "before": len(before_ids),
            "after": after_count,
            "added": len(set(after_ids) - set(before_ids)),
            "expected_exact": profile.expected_exact,
            "expected_min": profile.expected_min,
            "status": "OK" if complete else "PARTIEL",
            "unresolved": unresolved,
        }
        return payload, row

    # --------------------------- resolution ---------------------------

    def resolve_quest(self, name: str) -> Any:
        candidates = [name, *QUEST_ALIASES.get(normalize_text(name), ())]
        exact: dict[int, Any] = {}
        for candidate in candidates:
            for row in self.quest_by_name.get(normalize_text(candidate), []):
                exact[int(row.id)] = row
            for qid in self.quest_source_name_to_ids.get(normalize_text(candidate), []):
                row = self.quest_by_id.get(int(qid))
                if row is not None:
                    exact[int(qid)] = row
        if len(exact) == 1:
            return next(iter(exact.values()))
        if len(exact) > 1:
            raise RuntimeError(f"ambiguë {name!r}: {[(qid, row.name) for qid, row in exact.items()]}")

        loose: dict[int, Any] = {}
        for candidate in candidates:
            key = _loose_name(candidate)
            for row in self.quest_by_loose_name.get(key, []):
                loose[int(row.id)] = row
            for qid in self.quest_source_loose_to_ids.get(key, []):
                row = self.quest_by_id.get(int(qid))
                if row is not None:
                    loose[int(qid)] = row
        if len(loose) == 1:
            return next(iter(loose.values()))
        raise RuntimeError(f"introuvable/ambiguë {name!r}: {[(qid, row.name) for qid, row in loose.items()]}")

    def resolve_achievement(self, name: str) -> Any:
        candidates = [name, *ACHIEVEMENT_ALIASES.get(normalize_text(name), ())]
        exact: dict[int, Any] = {}
        for candidate in candidates:
            for row in self.achievement_by_name.get(normalize_text(candidate), []):
                exact[int(row.id)] = row
        if len(exact) == 1:
            return next(iter(exact.values()))
        if len(exact) > 1:
            raise RuntimeError(f"ambigu {name!r}: {[(aid, row.name) for aid, row in exact.items()]}")

        loose: dict[int, Any] = {}
        for candidate in candidates:
            for row in self.achievement_by_loose_name.get(_loose_name(candidate), []):
                loose[int(row.id)] = row
        if len(loose) == 1:
            return next(iter(loose.values()))
        raise RuntimeError(f"introuvable/ambigu {name!r}: {[(aid, row.name) for aid, row in loose.items()]}")

    def _achievement_leaf_groups(self, achievement: Any, visited: set[int] | None = None) -> list[tuple[int, str, list[int]]]:
        seen = set() if visited is None else visited
        achievement_id = int(achievement.id)
        if achievement_id in seen:
            return []
        seen.add(achievement_id)

        child_ids: set[int] = set()
        direct_ids = [
            int(ref.entity_id)
            for ref in getattr(achievement, "linked_quests", ()) or ()
            if safe_int(getattr(ref, "entity_id", None)) in self.quest_by_id
        ]
        for objective in getattr(achievement, "objectives", ()) or ():
            criterion = str(getattr(objective, "criterion", "") or "")
            _qrefs, srefs = mandatory_references(criterion)
            child_ids.update(aid for aid in srefs if aid in self.achievement_by_id)

        groups: list[tuple[int, str, list[int]]] = []
        for child_id in sorted(child_ids):
            child = self.achievement_by_id.get(child_id)
            if child is not None:
                groups.extend(self._achievement_leaf_groups(child, seen))

        direct_ids = list(dict.fromkeys(direct_ids))
        if direct_ids:
            groups.append((achievement_id, str(achievement.name), direct_ids))
        return groups

    def _mandatory_closure(
        self,
        seed_quests: set[int],
        seed_achievements: Iterable[int] = (),
        *,
        include_enriched: bool = False,
    ) -> tuple[set[int], set[int]]:
        quests = {int(qid) for qid in seed_quests if int(qid) in self.quest_by_id}
        achievements: set[int] = set()
        quest_queue = deque(quests)
        achievement_queue: deque[int] = deque()

        def add_quest(qid: int) -> None:
            qid = int(qid)
            if qid in self.quest_by_id and qid not in quests:
                quests.add(qid)
                quest_queue.append(qid)

        def add_achievement(aid: int) -> None:
            aid = int(aid)
            if aid in self.achievement_by_id and aid not in achievements:
                achievements.add(aid)
                achievement_queue.append(aid)

        for aid in seed_achievements:
            add_achievement(int(aid))

        while quest_queue or achievement_queue:
            while quest_queue:
                quest = self.quest_by_id[quest_queue.popleft()]
                _qrefs, srefs = mandatory_references(str(getattr(quest, "start_criterion", "") or ""))
                for qid in self._direct_quest_prerequisites(
                    quest,
                    include_enriched=include_enriched,
                ):
                    add_quest(qid)
                for aid in srefs:
                    add_achievement(aid)

            while achievement_queue:
                achievement = self.achievement_by_id[achievement_queue.popleft()]
                for ref in getattr(achievement, "linked_quests", ()) or ():
                    qid = safe_int(getattr(ref, "entity_id", None))
                    if qid is not None:
                        add_quest(qid)
                for objective in getattr(achievement, "objectives", ()) or ():
                    qrefs, srefs = mandatory_references(str(getattr(objective, "criterion", "") or ""))
                    for qid in qrefs:
                        add_quest(qid)
                    for aid in srefs:
                        add_achievement(aid)

            if len(quests) > 1200:
                raise RuntimeError("fermeture de prérequis >1200 quêtes, refus de contamination")
        return quests, achievements

    # --------------------------- payload helpers ---------------------------

    @staticmethod
    def collect_quest_ids(value: Any) -> list[int]:
        result: list[int] = []
        seen: set[int] = set()

        def walk(node: Any) -> None:
            if isinstance(node, dict):
                kind = normalize_text(node.get("type") or node.get("step_type") or "")
                if kind == "quest":
                    qid = safe_int(node.get("entity_id"))
                    if qid is not None and qid not in seen:
                        seen.add(qid)
                        result.append(qid)
                for child in node.values():
                    walk(child)
            elif isinstance(node, list):
                for child in node:
                    walk(child)

        walk(value)
        return result

    def _quest_section(
        self,
        section_id: str,
        title: str,
        quest_ids: Iterable[int],
        linked_achievement_ids: Iterable[int] = (),
    ) -> dict[str, Any]:
        ids = [int(qid) for qid in dict.fromkeys(int(value) for value in quest_ids) if int(qid) in self.quest_by_id]
        return {
            "id": section_id,
            "title": title,
            "description": "",
            "linked_achievement_ids": [int(value) for value in linked_achievement_ids],
            "steps": self._steps(section_id, ids),
        }

    def _steps(self, prefix: str, quest_ids: list[int], optional: bool = False) -> list[dict[str, Any]]:
        allowed = set(quest_ids)
        steps: list[dict[str, Any]] = []
        for qid in quest_ids:
            quest = self.quest_by_id.get(qid)
            direct = set()
            if quest is not None:
                direct = self._direct_quest_prerequisites(quest) & allowed
            steps.append(
                {
                    "id": f"{prefix}_quest_{qid}",
                    "type": "quest",
                    "entity_id": qid,
                    "optional": bool(optional),
                    "notes": "",
                    "prerequisites": [
                        {"type": "quest", "entity_id": previous}
                        for previous in sorted(direct)
                    ],
                }
            )
        return steps

    def _topological_order(self, quest_ids: set[int]) -> list[int]:
        ids = {int(qid) for qid in quest_ids if int(qid) in self.quest_by_id}
        incoming = {qid: 0 for qid in ids}
        children: dict[int, set[int]] = defaultdict(set)
        for qid in ids:
            quest = self.quest_by_id[qid]
            refs = self._direct_quest_prerequisites(quest)
            for previous in refs & ids:
                if qid not in children[previous]:
                    children[previous].add(qid)
                    incoming[qid] += 1

        def key(qid: int) -> tuple[int, str, int]:
            quest = self.quest_by_id[qid]
            level = safe_int(getattr(quest, "level_min", 0), 0) or 0
            return level, normalize_text(getattr(quest, "name", "")), qid

        ready = sorted((qid for qid, count in incoming.items() if count == 0), key=key)
        result: list[int] = []
        while ready:
            qid = ready.pop(0)
            result.append(qid)
            for child in sorted(children.get(qid, ()), key=key):
                incoming[child] -= 1
                if incoming[child] == 0:
                    ready.append(child)
                    ready.sort(key=key)
        result.extend(sorted(ids - set(result), key=key))
        return result


# --------------------------- boolean criterion parser ---------------------------

_QF_EQ_RE = re.compile(r"\bQf\s*(?:==|=)\s*(\d+)\b", re.IGNORECASE)
_SUCCESS_EQ_RE = re.compile(r"\b(?:Sc|OA)\s*(?:==|=)\s*(\d+)\b", re.IGNORECASE)


def mandatory_references(criterion: str) -> tuple[set[int], set[int]]:
    """Return references that are mandatory in every valid branch.

    AND => union; OR => intersection. This is intentionally stricter than a
    blind regex walk and prevents the previous patch from importing both sides
    of optional quest alternatives.
    """

    text = str(criterion or "").replace("&&", "&").replace("||", "|").strip()
    if not text:
        return set(), set()

    def strip_outer(value: str) -> str:
        value = value.strip()
        changed = True
        while changed and value.startswith("(") and value.endswith(")"):
            depth = 0
            changed = False
            for index, char in enumerate(value):
                if char == "(":
                    depth += 1
                elif char == ")":
                    depth -= 1
                    if depth == 0 and index != len(value) - 1:
                        return value
            if depth == 0:
                value = value[1:-1].strip()
                changed = True
        return value

    def split_top(value: str, separator: str) -> list[str]:
        parts: list[str] = []
        depth = 0
        start = 0
        for index, char in enumerate(value):
            if char == "(":
                depth += 1
            elif char == ")":
                depth = max(0, depth - 1)
            elif char == separator and depth == 0:
                parts.append(value[start:index])
                start = index + 1
        if parts:
            parts.append(value[start:])
        return [part.strip() for part in parts if part.strip()]

    def parse(value: str) -> tuple[set[int], set[int]]:
        value = strip_outer(value)
        or_parts = split_top(value, "|")
        if or_parts:
            branches = [parse(part) for part in or_parts]
            q_common = set(branches[0][0])
            s_common = set(branches[0][1])
            for qrefs, srefs in branches[1:]:
                q_common.intersection_update(qrefs)
                s_common.intersection_update(srefs)
            return q_common, s_common

        and_parts = split_top(value, "&")
        if and_parts:
            qrefs: set[int] = set()
            srefs: set[int] = set()
            for part in and_parts:
                qchild, schild = parse(part)
                qrefs.update(qchild)
                srefs.update(schild)
            return qrefs, srefs

        # A negated atom is never a mandatory completion requirement.
        if re.search(r"(^|[\s(])!\s*(?:Qf|Sc|OA)\b", value, re.IGNORECASE):
            return set(), set()
        return (
            {int(match.group(1)) for match in _QF_EQ_RE.finditer(value)},
            {int(match.group(1)) for match in _SUCCESS_EQ_RE.finditer(value)},
        )

    return parse(text)
