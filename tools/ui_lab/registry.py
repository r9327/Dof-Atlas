from __future__ import annotations

from dataclasses import dataclass
from importlib import import_module
from typing import Callable


LIVE = "live"
PLANNED = "planned"


@dataclass(frozen=True, slots=True)
class PreviewSpec:
    key: str
    label: str
    group: str
    source: str
    status: str = PLANNED
    factory_path: str | None = None
    description: str = ""

    @property
    def is_live(self) -> bool:
        return self.status == LIVE and bool(self.factory_path)


def default_previews() -> tuple[PreviewSpec, ...]:
    """Return the canonical UI Lab catalog.

    A planned entry is intentionally visible in the catalog so the tool also
    shows which important screens are not wired to a standalone preview yet.
    It is not a second product UI implementation.
    """

    return (
        PreviewSpec(
            key="encyclopedia.guides",
            label="Guide Succès",
            group="Encyclopédie",
            source="app/modules/encyclopedia/views/guides_view.py",
            status=LIVE,
            factory_path="tools.ui_lab.screens:create_guides_preview",
            description="Vraie vue Guides, avec progression isolée dans un bac à sable temporaire.",
        ),
        PreviewSpec(
            key="encyclopedia.quests",
            label="Quêtes",
            group="Encyclopédie",
            source="app/modules/encyclopedia/views/quests_view.py",
            description="À brancher sur la vraie vue Quêtes.",
        ),
        PreviewSpec(
            key="encyclopedia.achievements",
            label="Succès",
            group="Encyclopédie",
            source="app/modules/encyclopedia/views/achievements_view.py",
            description="À brancher sur la vraie vue Succès.",
        ),
        PreviewSpec(
            key="encyclopedia.bestiary",
            label="Bestiaire",
            group="Encyclopédie",
            source="app/modules/encyclopedia/views/bestiary_view.py",
            description="À brancher sur la vraie vue Bestiaire.",
        ),
        PreviewSpec(
            key="home",
            label="Accueil",
            group="Application",
            source="app/pages/home_page.py",
            description="À brancher sur la vraie page Accueil.",
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
            source="app/pages/zaap_page.py",
            description="À brancher sur la vraie page Zaap.",
        ),
    )


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
