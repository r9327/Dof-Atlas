"""Fail-closed routing rules for an *experimental* Organizer mirror mode.

No OS event injection is performed here. The existing macro executor remains
the only actual input sender until a separate Windows/Dofus compatibility test
establishes that targeted background delivery is supported.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Collection, Iterable


@dataclass(frozen=True)
class MirrorCapability:
    targeted_win32_tested: bool = False
    dofus_unity_confirmed: bool = False


def delivery_mode(capability: MirrorCapability) -> str:
    """Background mode cannot silently turn on based on a presumed API feature."""
    if capability.targeted_win32_tested and capability.dofus_unity_confirmed:
        return "targeted"
    return "sequential"


def mirror_targets(
    configured_handles: Iterable[int],
    explicitly_selected_handles: Collection[int],
    source_handle: int,
) -> tuple[int, ...]:
    """Only tracked/selected other clients, in Organizer's configured order.

    The original gesture already reaches the source client. Including it again
    would double the click. Unknown or stale handles are not eligible.
    """
    configured = tuple(int(h) for h in configured_handles if int(h) > 0)
    registered = set(configured)
    if int(source_handle) not in registered:
        return ()
    selected = {int(h) for h in explicitly_selected_handles if int(h) > 0}
    seen: set[int] = set()
    targets = []
    for handle in configured:
        if handle == source_handle or handle not in selected or handle in seen:
            continue
        seen.add(handle)
        targets.append(handle)
    return tuple(targets)
