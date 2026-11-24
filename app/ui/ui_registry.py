"""Executable Qt-free index of the real Dev UI style contract.

This is not another palette, stylesheet or component implementation.
The 23 showcase families and consumer names are owned by unity_palette;
this index attaches real QSS selectors, interactive states and source paths
so an audit can detect missing adoption instead of merely listing names.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

from app.ui.unity_palette import (
    UNITY_PAINTED_UI_ROLES, UNITY_UI_FAMILY_INDEX, UNITY_UI_CONSUMERS,
    UNITY_UI_UNIFICATION_CONTRACT,
)


UI_FAMILY_QSS_SELECTORS: dict[str, tuple[str, ...]] = {
    "buttons": (
        "#PrimaryActionButton", "#SecondaryButton", "#ActiveButton", "#DangerButton",
        "#InlineActionButton", "#PopupLinkButton", "#TopNavButton", "#TopNavButtonActive",
        "#GuideInlineQuestButton", "#GuideInlineAchievementButton",
        "#favoriteChipName",
    ),
    "navigation": (
        "QTabBar::tab", "QTabWidget::pane", "QMenu {",
        "QLabel#AtlasPageCounter",
        "#WorldMenu", "#WorldMenuItem", "#WorldMenuItemActive",
    ),
    "breadcrumbs": ("QFrame#GuideBreadcrumb", "QPushButton#GuideBreadcrumbButton", "QLabel#GuideBreadcrumbCurrent",
                    "QLabel#GuideBreadcrumbCurrentStrong"),
    "headers": (
        "#PageTitle", "#PanelTitle", "QFrame#GuideHeader",
        "QLabel#GuideHeaderTitle", "QLabel#GuideHeaderMeta",
        "QFrame#GuideCompactHeader", "QFrame#GuideGlobalDetailsPanel",
        "QWidget#GuideGlobalCharacterProgress",
        "QLabel#GuideCompactTitle",
        "QFrame#GuideSheetHeader", "QLabel#GuideSheetMeta",
        "QLabel#GuideSheetTitle", "#GuideManualProgress",
        "QToolButton#GuideMetricDropdown", "QToolButton#GuideParticipantsButton",
        "QSpinBox#GuideCompactPageJump", "QScrollArea#GuideManualScroll",
        "QProgressBar#GuideCompactPreparationProgress",
        "QPushButton#GuidePreparationModeTab",
        "#GuideCompactDonutHeading", "#GuideCompactDonutCount",
        "#DialogHeader",
    ),
    "sidebar": ("#sidebar", "#navItem", "#navItemActive", "#MenuButton", "#NavSeparator"),
    "data_views": (
        "QTreeWidget::item", "QTableWidget", "QHeaderView::section",
        "#MapViewTree", "#MapViewTree::item", "#AchievementsView",
        "#AchievementDetailStack", "#GuideLeftPanel", "#GuideCenterPanel",
        "QTreeWidget#QuestHierarchyTree",
    ),
    "scroll_resize": (
        "QSplitter::handle:horizontal", "QScrollBar:vertical",
        "QScrollArea", "QScrollBar::handle:vertical",
    ),
    "layouts": ("#card", "#Panel"),
    "fields": (
        "QLineEdit", "QComboBox", "QSpinBox", "QPlainTextEdit",
        "QCheckBox", "QRadioButton", "QSlider::groove:horizontal",
    ),
    "advanced_fields": (
        "QDoubleSpinBox", "QDateEdit", "QTimeEdit",
        "QCalendarWidget#AlmanaxCalendar",
    ),
    "statuses": ('#StatusBadge[state="done"]', "#StatusChip"),
    "notifications": ("#StatusBadge", "#MutedLabel", "#card"),
    "surfaces": (
        "#PageTitle", "#PanelTitle", "#MutedLabel", "#card",
        "#MapToolbar", "#WorldDetailPanel", "#WorldDetailValue", "#MapDetailValue",
    ),
    "metrics": (),  # Values resolve into QSS, not standalone selectors.
    "panels": (
        "#OrganizerPanel", "#GuideRightPanelToggle",
        "#organizerPage QFrame#card", "QGroupBox",
    ),
    "backdrop": ("QWidget#AtlasUnityBackdrop",),
    "startup": (
        "#PreloadPopupTitle", "#PreloadPopupCurrent", "#PreloadPopupProgress",
    ),
    "guides": (
        "#GuideHeader", "#GuidesHomeCategory", "#GuideDofusCard",
        "#GuideQuestLineActive", "#GuideCompactHeader",
        "#GuidePreparationPanel", "#GuideManualNav", "#GuideUltimeGeneratedView",
        "QFrame#GuidePreparationSummary", "QFrame#GuidePreparationRow",
        "QLabel#GuidePreparationSummaryTitle", "QLabel#GuidePreparationSummaryCount",
        "QLabel#GuidePreparationRowStatus", "QSpinBox#GuidePreparationQuantity",
        "QPushButton#GuidePreparationItemCopy", "QPushButton#GuidePreparationShowMore",
        "QToolButton#GuidePreparationDetailsButton",
        "QLabel#GuideManualCombatTargetsTitle",
        "#QuestLaunchPosition",
    ),
    "assets": ("#InlineShortcutButton", "QToolTip"),
    "motion": (),  # Unapproved animation prototypes; never promise adoption.
    "coverage": (),  # Documentation / source index, not a painted widget.
    "dialogs": ("#AtlasDialog", "#DialogHeader", "#DialogTitle"),
    "palette": (),  # Colors resolve into other families, not standalone QSS.
}


# Painted Qt iconography has no QSS selector, but belongs to the same
# Dev UI family registry. Derive roles by namespace to prevent duplicate maps.
UI_FAMILY_PAINTED_ROLES = {
    "startup": tuple(role for role in UNITY_PAINTED_UI_ROLES
                     if role.startswith("splash.")),
    "assets": tuple(role for role in UNITY_PAINTED_UI_ROLES
                    if (role.startswith("organizer.") and role != "organizer.shadow")
                    or role.startswith("world_scan.planet_")),
    "panels": ("organizer.shadow", "world_scan.placeholder"),
}


# Each state is checked against the SAME compiled QSS that all Qt pages use.
UI_INTERACTION_QSS_SELECTORS = {
    "buttons": (
        "QPushButton:hover", "QPushButton:pressed",
        "QPushButton:disabled", "QPushButton:focus",
    ),
    "navigation": (
        "QTabBar::tab:hover", "QTabBar::tab:selected",
        "QTabBar::tab:selected:hover",
        "#WorldMenuItem:hover", "#WorldMenuItemActive:hover",
        "#WorldMenuItem:disabled",
    ),
    "data_views": (
        "#MapViewTree::item:hover", "#MapViewTree::item:selected",
    ),
    "sidebar": ("#navItem:hover", "#navItemActive", "#burgerButton:pressed"),
    "breadcrumbs": ("QPushButton#GuideBreadcrumbButton:hover",),
    "guides": (
        "QFrame#GuideDofusCard:hover",
        "QFrame#GuideQuestLineActive",
        'QFrame#GuideQuestLine[state="done"]',
    ),
    "fields": ("QComboBox:hover", "QComboBox:disabled"),
    "statuses": ("#StatusChip:hover", "#StatusChip:checked"),
    "panels": (
        "#primaryButton:hover",
        "#primaryButton:pressed",
        "#primaryButton:disabled",
        '#organizerPage QPushButton[atlasShortcutInset="true"]',
    ),
}


# Real source owners, not an assertion that every functional click was certified.
# Qt consumers inherit QApplication.setStyleSheet(atlas_stylesheet()).
# Organizer's exceptions are now *also* compiled into that global sheet.
# Launcher gets its colors through the Qt-free launcher_colors adapter.
UI_CONSUMER_INDEX = {
    "Accueil": {
        "paths": ("app/pages/home_page.py",), "adapter": "qt",
    },
    "Personnage": {
        "paths": ("app/pages/character_page.py", "app/pages/_character_page_impl.py"),
        "adapter": "qt",
    },
    "Quêtes": {
        "paths": (
            "app/pages/_quests_page_impl.py",
            "app/pages/quests_page.py",
            "app/pages/lazy_quests_page.py",
            "app/modules/encyclopedia/widgets/quest_detail_view.py",
            "app/modules/encyclopedia/widgets/quest_widgets.py",
            "app/modules/encyclopedia/widgets/quest_item_row.py",
        ), "adapter": "qt",
    },
    "Succès": {
        "paths": (
            "app/modules/encyclopedia/views/achievements_view.py",
            "app/modules/encyclopedia/views/deferred_achievement_guides_view.py",
            "app/modules/encyclopedia/widgets/filter_panel.py",
            "app/modules/encyclopedia/widgets/achievement_entity_section.py",
            "app/modules/encyclopedia/widgets/achievement_detail_widget.py",
            "app/modules/encyclopedia/widgets/achievement_objective_widget.py",
            "app/modules/encyclopedia/widgets/achievement_reward_widget.py",
            "app/modules/encyclopedia/widgets/reward_card.py",
            "app/modules/encyclopedia/widgets/dashboard.py",
            "app/modules/encyclopedia/widgets/achievement_summary_widget.py",
            "app/modules/encyclopedia/widgets/result_list.py",
        ),
        "adapter": "qt",
    },
    "Guides": {
        "paths": (
            "app/modules/encyclopedia/views/guides_view.py",
            "app/modules/encyclopedia/views/guide_catalog_view.py",
            "app/modules/encyclopedia/views/guide_featured_home.py",
            "app/modules/encyclopedia/widgets/guide_card.py",
            "app/modules/encyclopedia/widgets/quest_detail_view.py",
            "app/modules/encyclopedia/views/guide_continuous_route_panel.py",
            "app/modules/encyclopedia/views/manual_route_guides_view.py",
            "app/modules/encyclopedia/views/guide_ultime_generated_view.py",
            "app/modules/encyclopedia/views/guide_ultime_manual_view.py",
            "app/modules/encyclopedia/views/guide_ultime_universal_view.py",
            "app/modules/encyclopedia/views/guide_ultime_walkthrough_card.py",
            "app/modules/encyclopedia/views/shared_manual_guide_view.py",
            "app/modules/encyclopedia/widgets/dashboard.py",
            "app/modules/encyclopedia/widgets/entity_link_button.py",
            "app/modules/encyclopedia/widgets/guide_progress_header.py",
            "app/modules/encyclopedia/widgets/guide_section_widget.py",
            "app/modules/encyclopedia/widgets/guide_step_widget.py",
            "app/modules/encyclopedia/widgets/progress_card.py",
            "app/modules/encyclopedia/widgets/quest_item_row.py",
        ), "adapter": "qt",
    },
    "Bestiaire": {
        "paths": (
            "app/modules/encyclopedia/views/encyclopedia_page.py",
            "app/modules/encyclopedia/views/memory_bound_encyclopedia_page.py",
            "app/modules/encyclopedia/widgets/detail_panel.py",
        ),
        "adapter": "qt",
    },
    "Outils": {
        "paths": (
            "app/pages/craft_page.py",
            "app/ui/world_scan_panel.py",
            "app/ui/map_canvas_widget.py",
        ),
        "adapter": "qt",
    },
    "Stuffs": {
        "paths": ("app/pages/equipment_page.py",), "adapter": "qt",
    },
    "Organizer": {
        "paths": (
            "app/pages/organizer_page.py",
            "app/pages/organizer/organizer_ui.py",
            "app/pages/organizer/character_sessions.py",
            "app/pages/organizer/organizer_drag_drop.py",
            "app/pages/organizer/organizer_hotkeys.py",
            "app/pages/organizer/glass_material.py",
            "app/pages/organizer/radial_overlay.py",
            "app/pages/organizer/radial_selection.py",
            "app/ui/organizer_style.py",
            "app/storage.py",  # ZaapWidget favorites and suggestions in Organizer.
        ), "adapter": "qt_scoped",
    },
    "Almanax": {
        "paths": ("app/pages/home_page.py", "main.py"), "adapter": "qt",
    },
    "Réseau": {
        "paths": ("app/ui/network_bridge.py",), "adapter": "qt",
    },
    "Launcher": {
        "paths": (
            "app/distribution/launcher.py", "app/distribution/launcher_ui.py",
        ), "adapter": "tk",
    },
    "Craft": {
        "paths": ("app/pages/craft_page.py",), "adapter": "qt",
    },
    "Carte du monde": {
        "paths": ("app/ui/world_scan_panel.py", "app/ui/map_canvas_widget.py"),
        "adapter": "qt",
    },
    "Paramètres": {
        "paths": ("main.py",), "adapter": "qt",
    },
    "Dev UI": {
        "paths": ("app/pages/dev_ui_page.py",), "adapter": "qt",
    },
    "Popups et dialogues": {
        "paths": (
            "main.py", "app/pages/craft_page.py", "app/storage.py",
            "app/ui/preload_popup.py", "app/modules/encyclopedia/views/guides_view.py",
            "app/pages/dev_ui_page.py",
        ),
        "adapter": "qt",
        # Existing popup capture scenarios, not distinct component implementations.
        "surfaces": (
            ("PreloadProgressPopup", "app/ui/preload_popup.py"),
            ("CloseActionDialog", "main.py"),
            ("QMessageBox.Question", "app/pages/craft_page.py"),
            ("QMessageBox.Warning", "app/pages/craft_page.py"),
            ("CraftResourceDialog", "app/pages/craft_page.py"),
            ("ItemSetDialog", "app/pages/craft_page.py"),
            ("LevelingDialog", "app/pages/craft_page.py"),
            ("RouteDialog", "app/pages/craft_page.py"),
            ("ZaapSuggestionPopup", "app/storage.py"),
            ("GuideImagePopup", "app/modules/encyclopedia/views/guides_view.py"),
            ("QMenu", "app/pages/dev_ui_page.py"),
            ("QComboBox popup", "app/pages/dev_ui_page.py"),
        ),
    },
    "Overlays et démarrage": {
        "paths": (
            "app/pages/organizer/radial_overlay.py",
            "app/pages/organizer/radial_selection.py",
            "app/ui/splash_image.py", "app/ui/preload_popup.py",
        ),
        "adapter": "qt",
        "surfaces": (
            ("Organizer radial", "app/pages/organizer/radial_overlay.py"),
            ("Organizer selection", "app/pages/organizer/radial_selection.py"),
            ("Splash Unity", "app/ui/splash_image.py"),
            ("PreloadProgressPopup", "app/ui/preload_popup.py"),
        ),
    },
}



# Audit-only projection of the 18 needs agreed for Dev UI. It REUSES the
# existing family/style index; these are not additional widget classes or QSS.
# Signatures indicate source-level references, not certified runtime use.
# Aggregate inventory zones and the Dev UI gallery are excluded from the
# consumer count to avoid counting the same source screen more than once.
UI_MUTUALIZATION_TARGETS = (
    ("Boutons", "buttons", "AtlasButton", r"\bAtlasButton\s*\("),
    ("Menus de sélection", "fields", "AtlasComboBox", r"\bAtlasComboBox\s*\("),
    ("Sélecteurs numériques", "fields", "QSpinBox + fit_unity_number_spinbox",
     r"\b(?:QSpinBox|fit_unity_number_spinbox)\s*\("),
    ("Fenêtres et popups classiques", "dialogs", "AtlasDialog + composition partagée",
     r"\bAtlasDialog\s*\(|\bclass\s+\w+\s*\(\s*AtlasDialog\s*\)|\.add_(?:header|scroll_rows|action_row)\s*\("),
    ("Cases à cocher", "fields", "QCheckBox + thème Unity", r"\bQCheckBox\s*\("),
    ("Champs de texte", "fields", "QLineEdit + thème Unity", r"\bQLineEdit\s*\("),
    ("Barres de progression", "statuses", "QProgressBar + thème Unity",
     r"\bQProgressBar\s*\("),
    ("Panneaux et modules", "panels", "AtlasPanelToggle / QFrame",
     r"\b(?:AtlasPanelToggle|QFrame|QGroupBox)\s*\("),
    ("Titres et sous-titres", "headers", "AtlasPageTitle / AtlasDialogHeader",
     r"\b(?:AtlasPageTitle|AtlasDialogHeader)\s*\(|\.add_header\s*\("),
    ("Bordures et arrondis", "surfaces", "Tokens du thème Unity",
     r"\.setObjectName\s*\(\s*['\"](?:card|Panel|QuestPanel)['\"]\s*\)"),
    ("Glass et ombres", "panels", "Tokens et helper Unity",
     r"\b(?:apply_unity_panel_shadow|apply_unity_shadow)\s*\("),
    ("Icônes et logos", "assets", "Assets Unity existants",
     r"\b(?:unity_original_preview_icon|atlas_application_icon|atlas_guide_symbol_icon|_guide_symbol_icon)\s*\("),
    ("Navigation et fil d'Ariane", "breadcrumbs", "AtlasBreadcrumb / AtlasPageNavigator",
     r"\b(?:AtlasBreadcrumb|AtlasPageNavigator)\s*\("),
    ("Onglets et sous-menus", "navigation", "QTabWidget / QMenu / AtlasPanelToggle",
     r"\b(?:QTabWidget|QMenu|AtlasPanelToggle|fill_unity_navigation_menu)\s*\("),
    ("Listes et tableaux", "data_views", "Qt listes / tableaux / arbres",
     r"\b(?:QTreeWidget|QTableWidget|QListWidget)\s*\("),
    ("Infobulles", "assets", "QToolTip via thème Unity", r"\.setToolTip\s*\("),
    ("Badges et statuts", "statuses", "AtlasStatusBadge",
     r"\bAtlasStatusBadge\s*\("),
    ("Scrollbars et resize", "scroll_resize", "Qt scroll / splitter + règles Unity",
     r"\b(?:QScrollArea|QScrollBar|QSplitter|configure_unity_scroll_area)\s*\(|\.add_scroll_rows\s*\("),
)

_AUDIT_AGGREGATE_ZONES = frozenset({
    "Outils", "Dev UI", "Popups et dialogues", "Overlays et démarrage",
    "Launcher",  # Tk uses a Qt-free adapter; no Qt constructors to count.
})


def inspect_ui_mutualization_sources(
    repo_root: Path | None = None,
) -> tuple[dict[str, object], ...]:
    """Measure declared source references; never claim a runtime migration PASS.

    Scanning is opt-in and only used when the developer opens the Dev UI
    audit. Paths are restricted to registered consumers; duplicate file
    reads are cached for that invocation. Nothing executes/imports a module.
    """
    root = repo_root or Path(__file__).resolve().parents[2]
    source_cache: dict[str, str | None] = {}
    consumers = {
        module: tuple(info["paths"])
        for module, info in UI_CONSUMER_INDEX.items()
        if module not in _AUDIT_AGGREGATE_ZONES
    }
    for paths in consumers.values():
        for path in paths:
            if path in source_cache:
                continue
            try:
                source_cache[path] = (root / path).read_text(encoding="utf-8")
            except OSError:
                source_cache[path] = None

    # Only two families currently have a meaningful direct-Qt constructor
    # duplication check. Other roles may legitimately use native Qt widgets.
    # AST ignores imports, class declarations, comments and string literals.
    raw_qt_calls: dict[str, list[tuple[str, int]]] = {
        "QPushButton": [],
        "QComboBox": [],
        "QDialog": [],
    }
    local_style_calls: list[tuple[str, int]] = []
    literal_width_calls: list[tuple[str, int, int]] = []
    for path, source in source_cache.items():
        if source is None:
            continue
        try:
            tree = ast.parse(source, filename=path)
        except SyntaxError:
            source_cache[path] = None
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            name = (
                func.id if isinstance(func, ast.Name)
                else func.attr if isinstance(func, ast.Attribute)
                else ""
            )
            if name in raw_qt_calls:
                raw_qt_calls[name].append((path, node.lineno))
            if name == "setStyleSheet" and path != "main.py":
                local_style_calls.append((path, node.lineno))
            if (
                name == "setFixedWidth" and node.args
                and isinstance(node.args[0], ast.Constant)
                and type(node.args[0].value) is int
                and node.args[0].value > 0
            ):
                literal_width_calls.append(
                    (path, node.lineno, node.args[0].value)
                )

    craft_source = source_cache.get("app/pages/craft_page.py")
    craft_dialog_classes = (
        "CraftResourceDialog", "ItemSetDialog", "LevelingDialog", "RouteDialog",
    )
    craft_shared_count = (
        sum(
            bool(re.search(
                rf"class\s+{name}\s*\(\s*AtlasDialog\s*\)",
                craft_source,
            ))
            for name in craft_dialog_classes
        )
        if craft_source is not None else None
    )
    craft_local_qdialog_count = (
        sum(
            bool(re.search(
                rf"class\s+{name}\s*\(\s*QDialog\s*\)",
                craft_source,
            ))
            for name in craft_dialog_classes
        )
        if craft_source is not None else None
    )
    results: list[dict[str, object]] = []
    for label, family, component, signature in UI_MUTUALIZATION_TARGETS:
        matcher = re.compile(signature)
        detected: list[str] = []
        incomplete: list[str] = []
        for module, paths in consumers.items():
            if any(source_cache[path] is None for path in paths):
                incomplete.append(module)
            if any(
                source_cache[path] is not None
                and matcher.search(source_cache[path]) is not None
                for path in paths
            ):
                detected.append(module)
        results.append({
            "label": label,
            "family": family,
            "component": component,
            "qss_rules": len(UI_FAMILY_QSS_SELECTORS[family]),
            "source_consumers": tuple(detected),
            "unreadable_consumers": tuple(incomplete),
            "style_owner": UNITY_UI_FAMILY_INDEX[family]["style_owner"],
            "raw_qt_constructors": (
                tuple(raw_qt_calls["QPushButton"]) if label == "Boutons"
                else tuple(raw_qt_calls["QComboBox"])
                if label == "Menus de sélection" else None
            ),
            "local_style_calls": (
                tuple(sorted(local_style_calls)) if label == "Bordures et arrondis"
                else None
            ),
            "literal_width_calls": (
                tuple(sorted(literal_width_calls))
                if label == "Scrollbars et resize" else None
            ),
            "native_dialog_calls": (
                tuple(sorted(raw_qt_calls["QDialog"]))
                if family == "dialogs" else None
            ),
            "craft_shared_dialogs": craft_shared_count if family == "dialogs" else None,
            "craft_local_qdialogs": craft_local_qdialog_count if family == "dialogs" else None,
        })
    return tuple(results)


def validate_ui_index() -> None:
    """Fail promptly if a Dev UI family or consumer lacks its index entry."""
    families = tuple(UNITY_UI_FAMILY_INDEX)
    if families != tuple(UI_FAMILY_QSS_SELECTORS):
        raise ValueError("Dev UI family selector index differs from gallery order")
    if not UNITY_UI_UNIFICATION_CONTRACT or any(
        not label or family not in UNITY_UI_FAMILY_INDEX
        for label, family in UNITY_UI_UNIFICATION_CONTRACT
    ):
        raise ValueError("UI-unification topic without a reachable Dev UI family")
    if tuple(UNITY_UI_CONSUMERS) != tuple(UI_CONSUMER_INDEX):
        raise ValueError("Dev UI consumer index differs from module list")
    painted = [role for group in UI_FAMILY_PAINTED_ROLES.values() for role in group]
    if len(painted) != len(set(painted)) or set(painted) != set(UNITY_PAINTED_UI_ROLES):
        raise ValueError("Unindexed or duplicated painted Unity role")
    if any(name not in UI_FAMILY_QSS_SELECTORS for name in UI_FAMILY_PAINTED_ROLES):
        raise ValueError("Painted Unity role belongs to an unknown Dev UI family")
    if len(UI_MUTUALIZATION_TARGETS) != 18:
        raise ValueError("Expected exactly 18 audited UI needs")
    for label, family, component, signature in UI_MUTUALIZATION_TARGETS:
        if not label or not component or family not in UI_FAMILY_QSS_SELECTORS:
            raise ValueError(f"Invalid mutualization target: {label}")
        re.compile(signature)
    if len({row[0] for row in UI_MUTUALIZATION_TARGETS}) != 18:
        raise ValueError("Duplicated UI mutualization target")
    for name, info in UI_CONSUMER_INDEX.items():
        if not info["paths"] or info["adapter"] not in {"qt", "qt_scoped", "tk"}:
            raise ValueError(f"Invalid UI consumer registration: {name}")
        surfaces = info.get("surfaces", ())
        if any(
            not label or path not in info["paths"]
            for label, path in surfaces
        ):
            raise ValueError(f"Invalid UI surface owner: {name}")
        if len({label for label, _path in surfaces}) != len(surfaces):
            raise ValueError(f"Duplicate UI surface in: {name}")
