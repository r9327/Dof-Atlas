# -*- coding: utf-8 -*-
"""Lazy public exports for application pages.

Importing any ``app.pages.*`` submodule executes this package first. Keep the
package initializer dependency-free so opening the process does not import every
unrelated page before the first frame is shown.
"""

from __future__ import annotations

from importlib import import_module


_PAGE_EXPORTS: dict[str, tuple[str, str]] = {
    "HomePage": ("app.pages.home_page", "HomePage"),
    "TreasureHuntPage": ("app.pages.treasure_hunt_page", "TreasureHuntPage"),
    "ResourcesPage": ("app.pages.resources_page", "ResourcesPage"),
    "SettingsPage": ("app.pages.settings_page", "SettingsPage"),
    "AdvancedSettingsPage": ("app.pages.advanced_settings_page", "AdvancedSettingsPage"),
    "LootPage": ("app.pages.loot_page", "LootPage"),
    "BestiaryPage": ("app.pages.bestiary_page", "BestiaryPage"),
    "ItemSetsPage": ("app.pages.item_sets_page", "ItemSetsPage"),
    "QuestsPage": ("app.pages.quests_page", "QuestsPage"),
}

__all__ = list(_PAGE_EXPORTS)


def __getattr__(name: str):
    target = _PAGE_EXPORTS.get(name)
    if target is None:
        raise AttributeError(name)
    module_name, attribute_name = target
    value = getattr(import_module(module_name), attribute_name)
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    return sorted(set(globals()) | set(__all__))
