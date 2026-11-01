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
    """Experimental package has no verified targeted input backend.

    Even two boolean observations are not an exact-SHA Windows/Unity
    attestation, so do not expose an activatable background mode yet.
    """
    del capability
    return "sequential"


def _valid_handles(values: Iterable[int]) -> tuple[int, ...]:
    clean: list[int] = []
    seen: set[int] = set()
    for raw in values:
        if isinstance(raw, bool):
            continue
        try:
            hwnd = int(raw)
        except (ValueError, TypeError, OverflowError):
            continue
        if 0 < hwnd <= (2**64 - 1) and hwnd not in seen:
            seen.add(hwnd)
            clean.append(hwnd)
    return tuple(clean)


def mirror_targets(
    configured_handles: Iterable[int],
    explicitly_selected_handles: Collection[int],
    source_handle: int,
) -> tuple[int, ...]:
    """Only tracked/selected other clients, in Organizer's configured order.

    The original gesture already reaches the source client. Including it again
    would double the click. Unknown or stale handles are not eligible.
    """
    configured = _valid_handles(configured_handles)
    source = _valid_handles((source_handle,))
    # The supported Organizer roster is 1–8 clients. An oversized or invalid
    # roster fails closed rather than broadcasting to an unreviewed window.
    if len(configured) > 8 or len(source) != 1 or source[0] not in configured:
        return ()
    selected = set(_valid_handles(explicitly_selected_handles))
    return tuple(
        handle for handle in configured
        if handle != source[0] and handle in selected
    )



def mirror_delivery_targets(
    configured_handles: Iterable[int],
    explicitly_selected_handles: Collection[int],
    source_handle: int,
    *,
    source_was_consumed: bool,
) -> tuple[int, ...]:
    """Plan a gesture exactly once without guessing how the native hook behaved.

    When a native mouse hook *consumed* the physical gesture, Organizer must
    also deliver that gesture to the source once. Otherwise the original
    gesture already reached the source, so resending it would double-click.

    This is a pure planner, not a runtime sender. No background input is
    enabled by this helper. Only the native hook may supply the consumption
    fact; callers must never infer it from a window title or focus alone.
    """
    if not isinstance(source_was_consumed, bool):
        return ()
    configured = _valid_handles(configured_handles)
    source = _valid_handles((source_handle,))
    if len(configured) > 8 or len(source) != 1 or source[0] not in configured:
        return ()
    other_targets = set(
        mirror_targets(configured, explicitly_selected_handles, source[0])
    )
    if source_was_consumed:
        other_targets.add(source[0])
    return tuple(handle for handle in configured if handle in other_targets)
