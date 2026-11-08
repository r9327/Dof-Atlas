from __future__ import annotations

import threading
import time
from dataclasses import dataclass, replace
from logging import Logger
from typing import NamedTuple


ATLAS_SYNTHETIC_MOUSE_EXTRA_INFO = 0xA71A5C1
ATLAS_SYNTHETIC_KEYBOARD_EXTRA_INFO = 0xA71A5C2
MIRROR_PENDING_CAPACITY = 4
MIRROR_PENDING_TTL_SECONDS = 2.0


@dataclass(frozen=True)
class MirrorPointerContext:
    profile: object
    source: int
    handles: tuple[int, ...]
    process_ids: tuple[tuple[int, int], ...]


class MirrorPointerSnapshot(NamedTuple):
    epoch: int
    context: MirrorPointerContext
    cancel_generation: int
    foreground: int | None


@dataclass(frozen=True)
class DeferredMirrorGesture:
    context: MirrorPointerContext
    foreground: int
    kind: str
    payload: tuple
    captured_at: float
    cancel_generation: int
    ready: bool


class InputState:
    def __init__(self):
        self._lock = threading.RLock()
        self.pressed_vks: set[int] = set()
        self.active_hotkeys: set[str] = set()
        self._mouse_block_count = 0
        self._mouse_block_label = ""
        # A physical gesture refused while a worker owns the pointer must
        # interrupt that worker. Deferred delivery requires an authenticated
        # Unity context; ordinary pointer blocks never authorize replay.
        self._mouse_block_interrupted = False
        self._mouse_block_gesture_count = 0
        # Emergency Stop revokes all prior pointer leases. Track ownership
        # per thread so a stale worker cannot decrement a NEW worker's block.
        # All canonical macro senders acquire/release on their worker thread.
        self._mouse_block_epoch = 0
        self._mouse_block_owners = threading.local()
        self._mirror_pointer_context: MirrorPointerContext | None = None
        self._mirror_pointer_target: int | None = None
        self._mirror_pointer_generation = 0
        self._mirror_pending: list[DeferredMirrorGesture] = []
        self._mirror_cancel_generation = 0
        self._physical_mouse_buttons: set[int] = set()
        self._mirror_focus_handoff: tuple[MirrorPointerContext, int, int] | None = None
        self._mirror_pending_counts = dict(accepted=0, expired=0, cancelled=0, full=0, ambiguous=0, taken=0)

    def set_key(self, vk_code: int, pressed: bool, *, preserve_deferred: bool = False) -> None:
        with self._lock:
            # A physical keyboard gesture takes priority over a deferred
            # pointer action, including a modifier pressed then released
            # before the worker could observe its current state.
            if not preserve_deferred:
                self.invalidate_deferred_mirror_pointer()
            if pressed:
                self.pressed_vks.add(int(vk_code))
            else:
                self.pressed_vks.discard(int(vk_code))

    def snapshot(self) -> set[int]:
        with self._lock:
            return set(self.pressed_vks)

    def set_physical_mouse_button(self, token: int, pressed: bool) -> None:
        with self._lock:
            if pressed:
                self._physical_mouse_buttons.add(token)
            else:
                self._physical_mouse_buttons.discard(token)

    def invalidate_deferred_mirror_pointer(self) -> int:
        with self._lock:
            count = len(self._mirror_pending)
            self._mirror_pending_counts["cancelled"] += count
            self._mirror_pending.clear()
            self._mirror_cancel_generation += 1
            self._mirror_focus_handoff = None
            return count

    def mark_hotkey_active(self, action_id: str, active: bool) -> bool:
        with self._lock:
            already = action_id in self.active_hotkeys
            if active:
                self.active_hotkeys.add(action_id)
                return not already
            self.active_hotkeys.discard(action_id)
            return already

    def reset_armed(self) -> None:
        with self._lock:
            self.invalidate_deferred_mirror_pointer()
            self.active_hotkeys.clear()
            self.pressed_vks.clear()

    def begin_mouse_block(
        self, label: str, *, mirror_context: MirrorPointerContext | None = None,
        mirror_generation: int | None = None,
    ) -> int:
        with self._lock:
            owners = getattr(self._mouse_block_owners, "epochs", None)
            if owners is None:
                owners = []
                self._mouse_block_owners.epochs = owners
            if self._mouse_block_count == 0:
                # A new, independent pointer lease needs a new epoch even
                # without Stop. A delayed native-hook probe must not cancel
                # the next worker simply because both ran between Stops.
                self._mouse_block_epoch += 1
                self._mouse_block_interrupted = False
                self._mouse_block_gesture_count = 0
                self._mirror_pointer_context = (
                    mirror_context if type(mirror_context) is MirrorPointerContext else None
                )
                self._mirror_pointer_target = (
                    mirror_context.source if type(mirror_context) is MirrorPointerContext else None
                )
                self._mirror_pointer_generation = (
                    mirror_generation if type(mirror_generation) is int else self._mirror_cancel_generation
                )
            else:
                # Nested pointer owners cannot authorize the same deferred
                # gesture on behalf of two potentially different senders.
                self._mirror_pointer_context = None
                self._mirror_pointer_target = None
            owners.append(self._mouse_block_epoch)
            # The result of an earlier release must never contaminate this
            # worker's next lease after another macro was dispatched.
            self._mouse_block_owners.last_release_interrupted = False
            self._mouse_block_owners.last_release_blocked_count = 0
            self._mouse_block_count += 1
            self._mouse_block_label = str(label or "macro")
            return self._mouse_block_count

    def end_mouse_block(self) -> int:
        with self._lock:
            owners = getattr(self._mouse_block_owners, "epochs", None)
            # Capture the interruption under the SAME lock as the lease
            # decrement. A physical DOWN can arrive after a worker's last
            # independent collision probe but before this release.
            self._mouse_block_owners.last_release_interrupted = False
            self._mouse_block_owners.last_release_blocked_count = 0
            if not owners:
                # Never unlock a lease acquired by another worker thread.
                return self._mouse_block_count
            epoch = owners.pop()
            if epoch != self._mouse_block_epoch:
                # Stop invalidated this lease; another macro may already
                # own a new block after the prior worker was interrupted.
                return self._mouse_block_count
            self._mouse_block_owners.last_release_interrupted = (
                self._mouse_block_interrupted
            )
            self._mouse_block_owners.last_release_blocked_count = (
                self._mouse_block_gesture_count
            )
            self._mouse_block_count = max(0, self._mouse_block_count - 1)
            if self._mouse_block_count == 0:
                self._mouse_block_label = ""
                self._mouse_block_interrupted = False
                self._mouse_block_gesture_count = 0
            return self._mouse_block_count

    def last_release_interrupted(self) -> bool:
        """The calling worker's last valid mouse release was interrupted.

        Snapshot set atomically by end_mouse_block; no cross-worker status
        contamination and no replay promise. Only read after the release.
        """
        return bool(getattr(
            self._mouse_block_owners, "last_release_interrupted", False,
        ))

    def last_release_blocked_count(self) -> int:
        """Number of intercepted physical gestures in this worker's lease.

        Recorded by the same atomic release as last_release_interrupted;
        useful for exact-action diagnostics without blocking the mouse hook.
        """
        return int(getattr(
            self._mouse_block_owners, "last_release_blocked_count", 0,
        ))

    def clear_mouse_block(self) -> None:
        with self._lock:
            # The next worker's lease belongs to a distinct generation.
            self._mouse_block_epoch += 1
            self._mouse_block_count = 0
            self._mouse_block_label = ""
            self._mouse_block_interrupted = False
            self._mouse_block_gesture_count = 0
            self._mirror_pointer_context = None
            self._mirror_pointer_target = None
            self.invalidate_deferred_mirror_pointer()

    def mirror_pointer_snapshot(self) -> MirrorPointerSnapshot | None:
        with self._lock:
            if (self._mouse_block_count <= 0 or self._mirror_pointer_context is None
                    or self._mirror_pointer_generation != self._mirror_cancel_generation):
                return None
            return MirrorPointerSnapshot(self._mouse_block_epoch, self._mirror_pointer_context,
                                         self._mirror_cancel_generation, self._mirror_pointer_target)

    def set_mirror_pointer_target(self, foreground: int) -> bool:
        with self._lock:
            owners = getattr(self._mouse_block_owners, "epochs", ())
            context = self._mirror_pointer_context
            if (not owners or owners[-1] != self._mouse_block_epoch
                    or self._mouse_block_count <= 0 or context is None
                    or self._mirror_pointer_generation != self._mirror_cancel_generation
                    or type(foreground) is not int or foreground not in context.handles):
                return False
            self._mirror_pointer_target = foreground
            return True

    def mirror_pointer_snapshot_is_current(self, snapshot: MirrorPointerSnapshot) -> bool:
        with self._lock:
            return (type(snapshot) is MirrorPointerSnapshot
                    and snapshot.epoch == self._mouse_block_epoch
                    and snapshot.context is self._mirror_pointer_context
                    and snapshot.cancel_generation == self._mirror_pointer_generation == self._mirror_cancel_generation)

    def _prune_deferred_mirror_pointer(self, now: float) -> None:
        previous_count = len(self._mirror_pending)
        self._mirror_pending[:] = [
            gesture for gesture in self._mirror_pending
            if (gesture.cancel_generation == self._mirror_cancel_generation
                and 0 <= now - gesture.captured_at <= MIRROR_PENDING_TTL_SECONDS)
        ]
        self._mirror_pending_counts["expired"] += previous_count - len(self._mirror_pending)

    def deferred_mirror_capacity_available(self) -> bool:
        with self._lock:
            self._prune_deferred_mirror_pointer(time.monotonic())
            available = len(self._mirror_pending) < MIRROR_PENDING_CAPACITY
            if not available:
                self._mirror_pending_counts["full"] += 1
            return available

    def mirror_gesture_generation(self) -> int:
        with self._lock:
            return self._mirror_cancel_generation

    def deferred_mirror_counts(self) -> dict[str, int]:
        with self._lock:
            self._prune_deferred_mirror_pointer(time.monotonic())
            return dict(self._mirror_pending_counts)

    def defer_mirror_pointer(
        self, epoch: int, generation: int, context: MirrorPointerContext,
        foreground: int, kind: str, payload: tuple, *, captured_at: float,
        ambiguous: bool = False,
    ) -> str:
        """Admit an already intercepted gesture, never a native/synthetic one.

        Native probes may finish after the owning worker releases its lease.
        Accept that handoff only until another lease or Stop changes its epoch.
        The shared lock makes admission, Stop and release ordering explicit.
        """
        with self._lock:
            now = time.monotonic()
            self._prune_deferred_mirror_pointer(now)
            if (type(context) is not MirrorPointerContext
                    or type(epoch) is not int or epoch != self._mouse_block_epoch
                    or type(generation) is not int
                    or generation != self._mirror_pointer_generation or generation != self._mirror_cancel_generation
                    or context is not self._mirror_pointer_context):
                return "obsolete"
            if (type(captured_at) not in (int, float)
                    or not 0 <= now - captured_at <= MIRROR_PENDING_TTL_SECONDS):
                return "expired"
            if (type(foreground) is not int or foreground not in context.handles
                    or type(payload) is not tuple or kind not in ("click", "wheel", "key")):
                return "invalid"
            if kind == "click":
                if len(payload) != 3 or payload[0] not in ("Left", "Right"):
                    return "invalid"
                button = payload[0]
                if ambiguous or any(
                    g.kind == "click" and not g.ready and g.payload[0] == button
                    for g in self._mirror_pending
                ):
                    previous_count = len(self._mirror_pending)
                    self._mirror_pending[:] = [
                        g for g in self._mirror_pending
                        if not (g.kind == "click" and not g.ready and g.payload[0] == button)
                    ]
                    self._mirror_pending_counts["ambiguous"] += 1
                    self._mirror_pending_counts["cancelled"] += previous_count - len(self._mirror_pending)
                    return "ambiguous"
            elif kind == "key":
                if len(payload) != 1 or type(payload[0]) is not int or not 0 < payload[0] <= 0xFE:
                    return "invalid"
                if any(g.kind == "key" and not g.ready and g.payload == payload
                       for g in self._mirror_pending):
                    self._mirror_pending_counts["ambiguous"] += 1
                    return "ambiguous"
            elif (len(payload) != 4 or type(payload[0]) is not int
                  or payload[0] == 0 or abs(payload[0]) > 32767
                  or type(payload[1]) is not bool):
                return "invalid"
            # NaN fails this comparison too. Never coerce bool/fractional
            # objects into client ratios or interpolate invalid coordinates.
            if kind != "key" and any(type(v) not in (float, int) or not 0 <= v <= 1 for v in payload[-2:]):
                return "invalid"
            if len(self._mirror_pending) >= MIRROR_PENDING_CAPACITY:
                self._mirror_pending_counts["full"] += 1
                return "full"
            self._mirror_pending.append(DeferredMirrorGesture(
                context, foreground, kind, payload, captured_at,
                generation, kind == "wheel",
            ))
            self._mirror_pending_counts["accepted"] += 1
            return "accepted"

    def release_deferred_mirror_pointer(self, button: str) -> None:
        with self._lock:
            self._prune_deferred_mirror_pointer(time.monotonic())
            for index, gesture in enumerate(self._mirror_pending):
                if (gesture.kind == "click" and not gesture.ready
                        and gesture.payload[0] == button):
                    self._mirror_pending[index] = replace(gesture, ready=True)
                    break

    def release_deferred_mirror_key(self, vk_code: int) -> None:
        with self._lock:
            self._prune_deferred_mirror_pointer(time.monotonic())
            for index, gesture in enumerate(self._mirror_pending):
                if gesture.kind == "key" and not gesture.ready and gesture.payload == (vk_code,):
                    self._mirror_pending[index] = replace(gesture, ready=True)
                    break

    def take_deferred_mirror_pointer(self) -> DeferredMirrorGesture | None:
        with self._lock:
            self._prune_deferred_mirror_pointer(time.monotonic())
            # An incomplete earlier click must not be overtaken by a wheel.
            if (self._mouse_block_count > 0 or self._physical_mouse_buttons
                    or self.pressed_vks or not self._mirror_pending
                    or not self._mirror_pending[0].ready):
                return None
            self._mirror_pending_counts["taken"] += 1
            return self._mirror_pending.pop(0)

    def deferred_mirror_pointer_is_current(self, gesture: DeferredMirrorGesture) -> bool:
        with self._lock:
            return (type(gesture) is DeferredMirrorGesture
                    and gesture.ready is True
                    and gesture.cancel_generation == self._mirror_cancel_generation
                    and not self._physical_mouse_buttons and not self.pressed_vks
                    and 0 <= time.monotonic() - gesture.captured_at <= MIRROR_PENDING_TTL_SECONDS)

    def deferred_mirror_queue_age(self, gesture: DeferredMirrorGesture) -> float | None:
        with self._lock:
            if not self.deferred_mirror_pointer_is_current(gesture):
                return None
            return max(0.0, time.monotonic() - gesture.captured_at)

    def deferred_mirror_expected_foreground(self, gesture: DeferredMirrorGesture) -> int:
        with self._lock:
            handoff = self._mirror_focus_handoff
            if (handoff is not None and handoff[0] is gesture.context
                    and handoff[1] == gesture.cancel_generation == self._mirror_cancel_generation):
                return handoff[2]
            return gesture.foreground

    def note_deferred_mirror_focus_handoff(
        self, owner: DeferredMirrorGesture | MirrorPointerSnapshot, foreground: int,
    ) -> None:
        with self._lock:
            current = (self.deferred_mirror_pointer_is_current(owner)
                       if type(owner) is DeferredMirrorGesture else self.mirror_pointer_snapshot_is_current(owner))
            if (current and type(foreground) is int and foreground in owner.context.handles):
                self._mirror_focus_handoff = (owner.context, self._mirror_cancel_generation, foreground)

    def mouse_block_epoch_if_active(self) -> int | None:
        """Snapshot current pointer ownership without reviving an old lease."""
        with self._lock:
            return self._mouse_block_epoch if self._mouse_block_count > 0 else None

    def note_blocked_physical_gesture(
        self, *, expected_epoch: int | None = None, interrupt: bool = True,
    ) -> bool:
        """Claim an intercepted gesture on the CURRENT pointer lease.

        Called for an intercepted physical click, wheel or queued key. It
        does not itself promise replay; the frozen deferred context owns that.
        A potentially admissible gesture can be counted without interrupting
        the current fan-out. Refusal then latches interruption separately.
        Unlike an emergency Stop, this does not revoke the
        worker's cleanup ownership or release the pointer prematurely.
        """
        with self._lock:
            if (self._mouse_block_count <= 0
                    or (expected_epoch is not None
                        and self._mouse_block_epoch != expected_epoch)):
                # A Stop/restart must not cancel the next worker on behalf
                # of a gesture admitted under an obsolete pointer lease.
                return False
            if interrupt:
                self._mouse_block_interrupted = True
            self._mouse_block_gesture_count += 1
            return True

    def interrupt_mouse_block(self, *, expected_epoch: int) -> bool:
        with self._lock:
            if (type(expected_epoch) is not int or self._mouse_block_count <= 0
                    or expected_epoch != self._mouse_block_epoch):
                return False
            self._mouse_block_interrupted = True
            return True

    def mouse_block_interrupted(self) -> bool:
        with self._lock:
            return self._mouse_block_count > 0 and self._mouse_block_interrupted

    def is_mouse_blocked(self) -> bool:
        with self._lock:
            return self._mouse_block_count > 0

    def mouse_block_label(self) -> str:
        with self._lock:
            return self._mouse_block_label


class SyntheticInputGuard:
    def __init__(self, logger: Logger):
        self._logger = logger
        self._lock = threading.RLock()
        self._until = 0.0
        self._active_count = 0

    def begin(self, duration_ms: int = 250) -> None:
        with self._lock:
            self._active_count += 1
            self._until = max(self._until, time.monotonic() + max(0, duration_ms) / 1000.0)
            try:
                self._logger.debug("Protection clic synthetique active: count=%s", self._active_count)
            except Exception:
                # A logger failure cannot invalidate an acquired input guard.
                pass

    def end(self, duration_ms: int = 120) -> None:
        with self._lock:
            self._active_count = max(0, self._active_count - 1)
            self._until = max(self._until, time.monotonic() + max(0, duration_ms) / 1000.0)
            try:
                self._logger.debug("Protection clic synthetique relachee: count=%s", self._active_count)
            except Exception:
                # The release already happened; do not report a sent click as
                # failed solely because diagnostics are unavailable.
                pass

    def reset(self) -> None:
        with self._lock:
            self._active_count = 0
            self._until = 0.0

    def is_synthetic_window(self) -> bool:
        with self._lock:
            return self._active_count > 0 or time.monotonic() < self._until
