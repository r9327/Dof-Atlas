from __future__ import annotations

from app.pages.lazy_quests_page import LazyQuestsPage

# Compatibility import for callers not yet migrated to the canonical lazy page.
ProgressiveQuestsPage = LazyQuestsPage

__all__ = ["ProgressiveQuestsPage"]
