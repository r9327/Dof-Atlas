from __future__ import annotations

from dataclasses import dataclass
from importlib import import_module
from typing import Callable


LIVE = "live"
PLANNED = "planned"
DEFAULT_SCENARIO = "default"


@dataclass(frozen=True, slots=True)
class PreviewSpec:
    key: str
    label: str
    group: str
    source: str
    status: str = PLANNED
    factory_path: str | None = None
    description: str = ""
    scenarios: tuple[str, ...] = (DEFAULT_SCENARIO,)

    @property
    def is_live(self) -> bool:
        return self.status == LIVE and bool(self.factory_path)


def default_previews() -> tuple[PreviewSpec, ...]:
    """Return the canonical UI Lab catalog.

    LIVE entries instantiate the real product widget hierarchy. Planned entries
    stay visible only to describe capture coverage; they never render a fake UI.
    """

    return (
        PreviewSpec(
            key="encyclopedia.guides",
            label="Guide Succès",
            group="Encyclopédie",
            source="app/modules/encyclopedia/views/encyclopedia_page.py",
            status=LIVE,
            factory_path="tools.ui_lab.screens:create_guides_preview",
            description="Vrai onglet GUIDES dans le vrai EncyclopediaPage.",
            scenarios=("default", "guide_first"),
        ),
        PreviewSpec(
            key="encyclopedia.quests",
            label="Quêtes",
            group="Encyclopédie",
            source="app/modules/encyclopedia/views/encyclopedia_page.py",
            status=LIVE,
            factory_path="tools.ui_lab.screens:create_quests_preview",
            description="Vrai onglet QUÊTES dans le vrai EncyclopediaPage.",
            scenarios=("default", "detail_first"),
        ),
        PreviewSpec(
            key="encyclopedia.achievements",
            label="Succès",
            group="Encyclopédie",
            source="app/modules/encyclopedia/views/encyclopedia_page.py",
            status=LIVE,
            factory_path="tools.ui_lab.screens:create_achievements_preview",
            description="Vrai onglet SUCCÈS dans le vrai EncyclopediaPage.",
            scenarios=("default", "detail_first"),
        ),
        PreviewSpec(
            key="encyclopedia.bestiary",
            label="Bestiaire",
            group="Encyclopédie",
            source="vue autonome non localisée",
            description="Entrée réservée : raccorder la vue canonique quand son hôte exact est identifié.",
        ),
        PreviewSpec(
            key="home",
            label="Accueil",
            group="Application",
            source="app/pages/home_page.py",
            status=LIVE,
            factory_path="tools.ui_lab.screens:create_home_preview",
            description="Vraie HomePage produit, sans reconstruction du layout.",
            scenarios=("default", "saved_progress"),
        ),
        PreviewSpec(
            key="organizer",
            label="Organizer",
            group="Application",
            source="app/pages/organizer_page.py",
            description="À brancher sur la vraie page Organizer.",
        ),
        PreviewSpec(
            key="equipment",
            label="Équipement",
            group="Application",
            source="app/pages/equipment_page.py",
            description="À brancher sur la vraie page Équipement.",
        ),
        PreviewSpec(
            key="zaap",
            label="Zaap",
            group="Application",
            source="app/macros/zaap.py",
            description="Logique Zaap repérée ; aucune page UI autonome n'est raccordée au labo pour l'instant.",
        ),
    )


def get_preview(key: str) -> PreviewSpec:
    for spec in default_previews():
        if spec.key == key:
            return spec
    raise KeyError(f"Écran UI Lab inconnu: {key}")


def resolve_factory(spec: PreviewSpec) -> Callable:
    if not spec.factory_path:
        raise LookupError(f"Aucune factory UI Lab pour {spec.key}")
    module_name, separator, attribute = spec.factory_path.partition(":")
    if not separator or not module_name or not attribute:
        raise ValueError(f"Factory UI Lab invalide: {spec.factory_path!r}")
    module = import_module(module_name)
    factory = getattr(module, attribute)
    if not callable(factory):
        raise TypeError(f"Factory UI Lab non appelable: {spec.factory_path}")
    return factory
