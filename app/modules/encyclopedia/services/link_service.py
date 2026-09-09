from __future__ import annotations

from collections.abc import Callable
from typing import Any


class LinkService:
    def __init__(self, navigator: Callable[..., bool] | None = None) -> None:
        self.navigator = navigator

    def navigate_to_entity(self, entity_type: str, entity_id: int | str, **context: Any) -> bool:
        if self.navigator is None:
            return False
        return bool(self.navigator(str(entity_type), entity_id, **context))
