"""Dofus Atlas encyclopedia module."""

__all__ = ["EncyclopediaPage"]


def __getattr__(name: str):
    if name == "EncyclopediaPage":
        from app.modules.encyclopedia.views import EncyclopediaPage

        return EncyclopediaPage
    raise AttributeError(name)
