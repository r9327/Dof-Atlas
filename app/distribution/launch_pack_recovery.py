"""Optional cold-start recovery of interrupted Atlas data-pack updates.

The launcher calls this ONLY when a data-pack store already exists; no folders,
migrations, downloads, profile writes or catalogue reloads on normal launches.
"""
from __future__ import annotations

from pathlib import Path
from typing import Callable

from .data_pack_plan import InvalidDataPack
from .data_pack_store import recover_pending_packs


def recover_data_packs_on_launch(root: Path, report: Callable[[str, int], None]) -> tuple[str, ...]:
    """Restore pending data packs before the installed application is launched.

    Fails closed if an existing store cannot be recovered. User files and the
    executable release slot are never modified by this operation.
    """
    if not isinstance(root, Path):
        raise InvalidDataPack("invalid Atlas installation root")
    index = root / "data-pack-store" / "state.json"
    if index.is_symlink():
        raise InvalidDataPack("unsafe data-pack index")
    if not index.exists():
        return ()
    recovered = recover_pending_packs(root)
    if recovered:
        report("Paquets de donnees precedents restaures", 2)
    return recovered
