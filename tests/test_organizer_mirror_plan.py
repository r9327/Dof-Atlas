from __future__ import annotations

from app.macros.mirror_plan import MirrorCapability, delivery_mode, mirror_targets


def test_mirror_never_broadcasts_to_unregistered_windows() -> None:
    assert mirror_targets([101, 202, 303], {202, 303, 999}, 101) == (202, 303)
    assert mirror_targets([101, 202], {202}, 999) == ()


def test_mirror_never_sends_original_gesture_twice() -> None:
    assert mirror_targets([101, 202, 202, 303], {101, 202, 303}, 101) == (202, 303)
    assert mirror_targets([101], {101}, 101) == ()


def test_mirror_preserves_configured_order() -> None:
    assert mirror_targets([303, 101, 202], {202, 303}, 101) == (303, 202)


def test_parallel_delivery_remains_disabled_without_real_unity_proof() -> None:
    assert delivery_mode(MirrorCapability()) == "sequential"
    assert delivery_mode(MirrorCapability(targeted_win32_tested=True)) == "sequential"
    assert delivery_mode(MirrorCapability(dofus_unity_confirmed=True)) == "sequential"
    assert delivery_mode(MirrorCapability(True, True)) == "targeted"
