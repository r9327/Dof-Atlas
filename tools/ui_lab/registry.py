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
    """Return the UI Lab catalog using the same top-level hierarchy as AtlasWindow."""

    return (
        PreviewSpec(
            key="home",
            label="Accueil",
            group="Accueil",
            source="app/pages/home_page.py",
            status=LIVE,
            factory_path="tools.ui_lab.screens:create_home_preview",
            description="Vraie HomePage produit.",
            scenarios=("default", "saved_progress"),
        ),
        PreviewSpec(
            key="organizer",
            label="Organizer",
            group="Organizer",
            source="app/pages/organizer_page.py",
            status=LIVE,
            factory_path="tools.ui_lab.screens:create_organizer_preview",
            description="Vraie OrganizerPage ; persistence et watcher Windows isolés.",
        ),
        PreviewSpec(
            key="encyclopedia.guides",
            label="Guide",
            group="Encyclopédie",
            source="app/modules/encyclopedia/views/encyclopedia_page.py",
            status=LIVE,
            factory_path="tools.ui_lab.screens:create_guides_preview",
            description="Vrai onglet GUIDES avec la visibilité d'onglets appliquée par AtlasWindow.",
            scenarios=("default", "guide_first", "target"),
        ),
        PreviewSpec(
            key="encyclopedia.quests",
            label="Quêtes",
            group="Encyclopédie",
            source="app/modules/encyclopedia/views/encyclopedia_page.py",
            status=LIVE,
            factory_path="tools.ui_lab.screens:create_quests_preview",
            description="Vrai onglet QUÊTES avec la visibilité d'onglets appliquée par AtlasWindow.",
            scenarios=("default", "detail_first", "target"),
        ),
        PreviewSpec(
            key="encyclopedia.achievements",
            label="Succès",
            group="Encyclopédie",
            source="app/modules/encyclopedia/views/encyclopedia_page.py",
            status=LIVE,
            factory_path="tools.ui_lab.screens:create_achievements_preview",
            description="Vrai onglet SUCCÈS avec la visibilité d'onglets appliquée par AtlasWindow.",
            scenarios=("default", "detail_first", "target"),
        ),
        PreviewSpec(
            key="bestiary.dungeons",
            label="Donjons",
            group="Bestiaire",
            source="app/modules/encyclopedia/views/encyclopedia_page.py",
            status=LIVE,
            factory_path="tools.ui_lab.screens:create_dungeons_preview",
            description="Vrai sous-onglet DONJONS du groupe Bestiaire ; capture l'état produit actuel.",
        ),
        PreviewSpec(
            key="bestiary.monsters",
            label="Monstres",
            group="Bestiaire",
            source="app/modules/encyclopedia/views/encyclopedia_page.py",
            status=LIVE,
            factory_path="tools.ui_lab.screens:create_monsters_preview",
            description="Vrai sous-onglet MONSTRES du groupe Bestiaire ; capture l'état produit actuel.",
        ),
        PreviewSpec(
            key="bestiary.archmonsters",
            label="Archimonstres",
            group="Bestiaire",
            source="app/modules/encyclopedia/views/encyclopedia_page.py",
            status=LIVE,
            factory_path="tools.ui_lab.screens:create_archmonsters_preview",
            description="Vrai sous-onglet ARCHIMONSTRES du groupe Bestiaire ; capture l'état produit actuel.",
        ),
        PreviewSpec(
            key="bestiary.wanted",
            label="Avis de recherche",
            group="Bestiaire",
            source="app/modules/encyclopedia/views/encyclopedia_page.py",
            status=LIVE,
            factory_path="tools.ui_lab.screens:create_wanted_preview",
            description="Vrai sous-onglet AVIS DE RECHERCHE du groupe Bestiaire ; capture l'état produit actuel.",
        ),
        PreviewSpec(
            key="tools.crafts",
            label="Crafts",
            group="Outils",
            source="app/pages/craft_page.py",
            status=LIVE,
            factory_path="tools.ui_lab.extra_screens:create_crafts_preview",
            description="Vraie CraftPage dans son état produit de chargement différé.",
        ),
        PreviewSpec(
            key="tools.world_map",
            label="Map monde",
            group="Outils",
            source="app/ui/world_scan_panel.py",
            status=LIVE,
            factory_path="tools.ui_lab.extra_screens:create_world_map_preview",
            description="Vrai WorldScanPanel ; son chargement local suit le chemin produit normal.",
        ),
        PreviewSpec(
            key="tools.treasure_hunt",
            label="Chasse au trésor",
            group="Outils",
            source="main.py",
            status=LIVE,
            factory_path="tools.ui_lab.screens:create_treasure_hunt_preview",
            description="Placeholder produit actuel, créé par AtlasWindow.placeholder_page.",
        ),
        PreviewSpec(
            key="tools.ocre",
            label="Ocre",
            group="Outils",
            source="main.py",
            status=LIVE,
            factory_path="tools.ui_lab.screens:create_ocre_preview",
            description="Placeholder produit actuel, créé par AtlasWindow.placeholder_page.",
        ),
        PreviewSpec(
            key="stuffs.pvm",
            label="PvM",
            group="Stuffs",
            source="app/pages/equipment_page.py",
            status=LIVE,
            factory_path="tools.ui_lab.screens:create_equipment_pvm_preview",
            description="Vraie EquipmentPage, capturée avant contenu Web externe pour garder le squelette déterministe.",
        ),
        PreviewSpec(
            key="stuffs.pvp",
            label="PvP",
            group="Stuffs",
            source="app/pages/equipment_page.py",
            status=LIVE,
            factory_path="tools.ui_lab.screens:create_equipment_pvp_preview",
            description="Vraie EquipmentPage, section PvP si l'API produit l'expose.",
        ),
        PreviewSpec(
            key="stuffs.builders",
            label="Builders",
            group="Stuffs",
            source="app/pages/equipment_page.py",
            status=LIVE,
            factory_path="tools.ui_lab.screens:create_equipment_builders_preview",
            description="Vraie EquipmentPage, section Builders si l'API produit l'expose.",
        ),
        PreviewSpec(
            key="almanax",
            label="Almanax",
            group="Almanax",
            source="main.py",
            status=LIVE,
            factory_path="tools.ui_lab.screens:create_almanax_preview",
            description="Placeholder produit actuel, créé par AtlasWindow.placeholder_page.",
        ),
        PreviewSpec(
            key="tutorials.default",
            label="Tutoriels",
            group="Tutoriels",
            source="main.py",
            status=LIVE,
            factory_path="tools.ui_lab.screens:create_tutorials_preview",
            description="Placeholder produit actuel du bouton Tutoriels.",
        ),
        PreviewSpec(
            key="tutorials.dofus_noob",
            label="Dofus Noob",
            group="Tutoriels",
            source="main.py",
            status=LIVE,
            factory_path="tools.ui_lab.screens:create_dofus_noob_preview",
            description="Placeholder produit actuel du menu Tutoriels > Dofus Noob.",
        ),
        PreviewSpec(
            key="zaap",
            label="Zaap intégré à Organizer",
            group="Organizer",
            source="app/pages/organizer_page.py",
            description="Zaap n'est pas un onglet principal : il est déjà visible dans Organizer.",
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

    def product_factory(context):
        from tools.ui_lab.product_shell import wrap_product_shell

        content = factory(context)
        return wrap_product_shell(
            content,
            group=spec.group,
            active_label=spec.label,
        )

    return product_factory
