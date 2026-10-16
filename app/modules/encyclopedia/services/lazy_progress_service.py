from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from app.constants import DATA_DIR


ACHIEVEMENT_PROGRESS_FILE = (
    DATA_DIR / "encyclopedia" / "progress" / "achievement_progress.json"
)
GUIDE_PROGRESS_FILE = (
    DATA_DIR / "encyclopedia" / "progress" / "guide_progress.json"
)


class LazyProgressService:
    """Keep optional progress engines cold until a tab actually uses them."""

    __slots__ = ("path", "_loader", "_service")

    def __init__(self, path: Path, loader: Callable[[Path], Any]) -> None:
        self.path = Path(path)
        self._loader = loader
        self._service: Any = None

    def _resolve(self):
        service = self._service
        if service is None:
            service = self._loader(self.path)
            self._service = service
        return service

    def peek(self):
        return self._service

    def __getattr__(self, name: str):
        return getattr(self._resolve(), name)


def _load_achievement_progress(path: Path):
    from app.modules.encyclopedia.services import AchievementProgressService

    return AchievementProgressService(path)


def _load_guide_progress(path: Path):
    from app.modules.encyclopedia.services import GuideProgressService

    return GuideProgressService(path)


def lazy_achievement_progress_service(
    path: Path = ACHIEVEMENT_PROGRESS_FILE,
) -> LazyProgressService:
    return LazyProgressService(path, _load_achievement_progress)


def lazy_guide_progress_service(
    path: Path = GUIDE_PROGRESS_FILE,
) -> LazyProgressService:
    return LazyProgressService(path, _load_guide_progress)


__all__ = [
    "ACHIEVEMENT_PROGRESS_FILE",
    "GUIDE_PROGRESS_FILE",
    "LazyProgressService",
    "lazy_achievement_progress_service",
    "lazy_guide_progress_service",
]
