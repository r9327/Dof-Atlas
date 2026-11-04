"""Fail-closed routing rules for an *experimental* Organizer mirror mode.

No OS event injection is performed here. The existing macro executor remains
the only actual input sender until a separate Windows/Dofus compatibility test
establishes that targeted background delivery is supported.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import PureWindowsPath
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
    # Never iterate a scalar/string as a sequence of window IDs.  A bare
    # "202" previously became handles (2, 0), which could target the wrong
    # window. Native session indexes provide a genuine iterable instead.
    if values is None or isinstance(values, (str, bytes, bytearray)):
        return ()
    try:
        iterator = iter(values)
    except TypeError:
        return ()
    clean: list[int] = []
    seen: set[int] = set()
    for raw in iterator:
        if isinstance(raw, float):
            continue
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


def is_dofus_unity_executable(image_path: str) -> bool:
    """Require an absolute Dofus.exe image, never merely a Unity window."""
    if not isinstance(image_path, str) or not image_path:
        return False
    path = PureWindowsPath(image_path)
    return path.is_absolute() and path.name.casefold() == "dofus.exe"


def is_dofus_unity_process(hwnd: int) -> bool:
    """Fail closed if the HWND process identity is not independently readable."""
    if type(hwnd) is not int or not 0 < hwnd <= (2**64 - 1):
        return False
    from app.windows_embed import window_class, window_process_id, process_image_path
    try:
        if window_class(hwnd) != "UnityWndClass":
            return False
        pid = window_process_id(hwnd)
        # A Win32 PID is a positive DWORD. Reject bool, overflow and other
        # malformed identities BEFORE querying a possibly unrelated process.
        if type(pid) is not int or not 0 < pid <= (2**32 - 1):
            return False
        return is_dofus_unity_executable(process_image_path(pid))
    except (OSError, ValueError, TypeError, OverflowError):
        return False


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
    # An invalid/missing selection must not cause even the favorite to be
    # replayed: no gesture can be safely planned without real recipients.
    selected = _valid_handles(explicitly_selected_handles)
    if not selected:
        return ()
    configured = _valid_handles(configured_handles)
    source = _valid_handles((source_handle,))
    if len(configured) > 8 or len(source) != 1 or source[0] not in configured:
        return ()
    other_targets = set(
        mirror_targets(configured, selected, source[0])
    )
    if source_was_consumed:
        other_targets.add(source[0])
    return tuple(handle for handle in configured if handle in other_targets)


def mirror_latency_percentiles_ms(samples_ms: Iterable[float]) -> dict[str, float] | None:
    """Measured SendInput call percentiles using nearest-rank, never fake values.

    These numbers are per completed mirror action, not proof of real-game
    background support or input-to-render latency.
    """
    import math

    clean: list[float] = []
    for sample in samples_ms:
        try:
            numeric = float(sample)
        except (TypeError, ValueError, OverflowError):
            continue
        if math.isfinite(numeric) and numeric >= 0:
            clean.append(numeric)
    if not clean:
        return None
    clean.sort()

    def value(percent: float) -> float:
        return round(clean[max(0, math.ceil(len(clean) * percent) - 1)], 3)

    return {
        "n": len(clean),
        "p50": value(0.50),
        "p95": value(0.95),
        "p99": value(0.99),
    }


@dataclass(frozen=True)
class MirrorHeldKeys:
    """Observed physical key-downs, in order, for later safe release."""
    pressed: tuple[int, ...] = ()


def mirror_key_transition(
    state: MirrorHeldKeys,
    vk_code: int,
    is_down: bool,
) -> tuple[MirrorHeldKeys, tuple[str, int] | None]:
    """Pure pairing state; does not send a key to any client.

    Repeated downs and unmatched ups are ignored. No key is injected until
    the platform adapter supports balanced, cancellable replay.
    """
    if not isinstance(state, MirrorHeldKeys):
        raise TypeError("MirrorHeldKeys state required")
    if type(vk_code) is not int or not (1 <= vk_code <= 254) or type(is_down) is not bool:
        return state, None
    if is_down:
        if vk_code in state.pressed:
            return state, None
        return MirrorHeldKeys(state.pressed + (vk_code,)), ("down", vk_code)
    if vk_code not in state.pressed:
        return state, None
    return MirrorHeldKeys(tuple(key for key in state.pressed if key != vk_code)), ("up", vk_code)


def mirror_release_all_keys(
    state: MirrorHeldKeys,
) -> tuple[MirrorHeldKeys, tuple[tuple[str, int], ...]]:
    """Emergency-stop release plan in reverse press order, no OS injection."""
    if not isinstance(state, MirrorHeldKeys):
        raise TypeError("MirrorHeldKeys state required")
    return MirrorHeldKeys(), tuple(("up", vk) for vk in reversed(state.pressed))
