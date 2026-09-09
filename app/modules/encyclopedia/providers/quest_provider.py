from __future__ import annotations

from pathlib import Path
from threading import Lock

from app.constants import RAW_QUEST_DATA_DIR
from app.quest_catalog import QuestCatalog, QuestRecord

_DEFAULT_DATA_DIR = RAW_QUEST_DATA_DIR.resolve()
_SHARED_DEFAULT_CATALOG: QuestCatalog | None = None
_SHARED_DEFAULT_CATALOG_LOCK = Lock()


def _is_default_data_dir(data_dir: Path) -> bool:
    return data_dir.resolve() == _DEFAULT_DATA_DIR


def _shared_default_catalog() -> QuestCatalog:
    global _SHARED_DEFAULT_CATALOG
    with _SHARED_DEFAULT_CATALOG_LOCK:
        if _SHARED_DEFAULT_CATALOG is None:
            _SHARED_DEFAULT_CATALOG = QuestCatalog.load(RAW_QUEST_DATA_DIR)
        return _SHARED_DEFAULT_CATALOG


class QuestProvider:
    """Adapter around the existing QuestCatalog parser.

    Phase 1 keeps the proven quest loading path intact and exposes it through
    the encyclopedia provider boundary.
    """

    def __init__(
        self,
        catalog: QuestCatalog | None = None,
        data_dir: Path = RAW_QUEST_DATA_DIR,
    ) -> None:
        self._catalog = catalog
        self.data_dir = data_dir

    def get_catalog(self) -> QuestCatalog:
        if self._catalog is None:
            self._catalog = _shared_default_catalog() if _is_default_data_dir(self.data_dir) else QuestCatalog.load(self.data_dir)
        return self._catalog

    def list_quests(self) -> list[QuestRecord]:
        return self.get_catalog().quests

    def get_quest(self, quest_id: int) -> QuestRecord | None:
        return self.get_catalog().by_id.get(int(quest_id))

    def count(self) -> int:
        return len(self.list_quests())
