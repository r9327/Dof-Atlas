from __future__ import annotations

import threading
from time import monotonic
from dataclasses import dataclass
from logging import Logger
from typing import Callable

from PySide6.QtCore import QCoreApplication, QObject, Signal, Slot

from app.core.admin import audit_client_admin_rights
from app.core.logger import get_runtime_logger, set_debug_logging
from app.core.macro_lock import MacroLock
from app.core.settings import AtlasSettings, load_settings
from app.input.input_state import InputState, SyntheticInputGuard
from app.input.managed_hooks import (
    ManagedHotkeyRegistry,
    ManagedMouseHook,
    build_runtime_hotkey_actions,
)
from app.macros.input_tools import release_common_inputs
from app.windows.unity_windows import enable_dpi_awareness


StatusCallback = Callable[[str], None]
ActiveCallback = Callable[[bool], None]
RUNTIME_STARTUP_JOIN_TIMEOUT_SECONDS = 5.0
MACRO_THREAD_JOIN_TIMEOUT_SECONDS = 2.0


class _RuntimeCallbackBridge(QObject):
    """Marshal worker callbacks back to the QObject thread that created runtime."""

    statusRequested = Signal(int, str)
    activeRequested = Signal(int, bool)

    def __init__(self, status_callback: StatusCallback, active_callback: ActiveCallback) -> None:
        super().__init__()
        self._status_callback = status_callback
        self._active_callback = active_callback
        self._sequence_lock = threading.Lock()
        self._status_sequence = 0
        self._active_sequence = 0
        # AutoConnection is intentional: UI-thread emissions stay synchronous,
        # worker-thread emissions are queued onto this bridge's Qt thread.
        self.statusRequested.connect(self._deliver_status)
        self.activeRequested.connect(self._deliver_active)

    def publish_status(self, text: str) -> None:
        with self._sequence_lock:
            self._status_sequence += 1
            sequence = self._status_sequence
        self.statusRequested.emit(sequence, str(text))

    def publish_active(self, active: bool) -> None:
        with self._sequence_lock:
            self._active_sequence += 1
            sequence = self._active_sequence
        self.activeRequested.emit(sequence, bool(active))

    @Slot(int, str)
    def _deliver_status(self, sequence: int, text: str) -> None:
        with self._sequence_lock:
            if int(sequence) != self._status_sequence:
                return
        self._status_callback(text)

    @Slot(int, bool)
    def _deliver_active(self, sequence: int, active: bool) -> None:
        with self._sequence_lock:
            if int(sequence) != self._active_sequence:
                return
        self._active_callback(bool(active))


@dataclass
class LastClientPoint:
    hwnd: int = 0
    x: int = 0
    y: int = 0
    x_ratio: float | None = None
    y_ratio: float | None = None
    valid: bool = False


class AtlasRuntime:
    def __init__(
        self,
        status_callback: StatusCallback | None = None,
        active_callback: ActiveCallback | None = None,
    ):
        self.logger: Logger = get_runtime_logger()
        self.status_callback = status_callback or (lambda _text: None)
        self.active_callback = active_callback or (lambda _active: None)
        self._callback_bridge = (
            _RuntimeCallbackBridge(self.status_callback, self.active_callback)
            if QCoreApplication.instance() is not None
            else None
        )
        # The runtime reloads settings in its asynchronous startup worker before
        # hooks are registered. Avoid reading profile/client JSON once on the Qt
        # thread only to read the same files again a few milliseconds later.
        self._settings_lock = threading.RLock()
        self._settings: AtlasSettings | None = None
        self.input_state = InputState()
        self.synthetic_guard = SyntheticInputGuard(self.logger)
        self.macro_lock = MacroLock(self.logger)
        self._macro_init_lock = threading.RLock()
        self._switch_character = None
        self._switch_click = None
        self._pending_physical_switch = None
        self._mirror_input = None
        self._direction = None
        self._travel = None
        self._zaap = None
        self._auto_group = None
        self.registry = ManagedHotkeyRegistry(
            self.input_state, self.logger, self._handle_hotkey,
            physical_key_callback=self._handle_mirror_key,
        )
        self.mouse_hook = ManagedMouseHook(
            self.input_state, self.synthetic_guard, self.logger,
            self._handle_mouse_click,
            wheel_callback=self._handle_mirror_wheel,
            release_callback=self._handle_mouse_release,
        )
        self.last_client_point = LastClientPoint()
        self.active_client_handle = 0
        self._running = False
        self._admin_ok = True
        self._state_lock = threading.RLock()
        self._startup_cancel = threading.Event()
        self._startup_thread: threading.Thread | None = None
        self._startup_reload_requested = False
        self._starting = False
        # False means there is no live Dofus client to bind hooks to. Keep the
        # Win32 hook backends completely cold in that state; a later start()
        # reloads settings and enables them as soon as a session appears.
        self._runtime_bindings_available = True
        self._threads: list[threading.Thread] = []

    @property
    def settings(self) -> AtlasSettings:
        with self._settings_lock:
            settings = self._settings
            if settings is None:
                settings = load_settings()
                self._settings = settings
                set_debug_logging(settings.debug_enabled)
            return settings

    @settings.setter
    def settings(self, value: AtlasSettings) -> None:
        with self._settings_lock:
            # A native DOWN from the previous Organizer generation must not
            # trigger replay when its physical UP arrives after reload.
            self._pending_physical_switch = None
            self._settings = value

    @property
    def switch_character(self):
        with self._macro_init_lock:
            if self._switch_character is None:
                from app.macros.switch_character import SwitchCharacterMacro

                self._switch_character = SwitchCharacterMacro(self)
            return self._switch_character

    @switch_character.setter
    def switch_character(self, value) -> None:
        with self._macro_init_lock:
            self._switch_character = value

    @property
    def switch_click(self):
        with self._macro_init_lock:
            if self._switch_click is None:
                from app.macros.switch_click import SwitchClickMacro

                self._switch_click = SwitchClickMacro(self)
            return self._switch_click

    @switch_click.setter
    def switch_click(self, value) -> None:
        with self._macro_init_lock:
            self._switch_click = value

    @property
    def mirror_input(self):
        with self._macro_init_lock:
            if self._mirror_input is None:
                from app.macros.mirror_input import MirrorInputMacro
                self._mirror_input = MirrorInputMacro(self)
            return self._mirror_input

    @property
    def direction(self):
        with self._macro_init_lock:
            if self._direction is None:
                from app.macros.direction import DirectionMacro

                self._direction = DirectionMacro(self)
            return self._direction

    @direction.setter
    def direction(self, value) -> None:
        with self._macro_init_lock:
            self._direction = value

    @property
    def travel(self):
        with self._macro_init_lock:
            if self._travel is None:
                from app.macros.travel import TravelMacro

                self._travel = TravelMacro(self)
            return self._travel

    @travel.setter
    def travel(self, value) -> None:
        with self._macro_init_lock:
            self._travel = value

    @property
    def zaap(self):
        with self._macro_init_lock:
            if self._zaap is None:
                from app.macros.zaap import ZaapMacro

                self._zaap = ZaapMacro(self)
            return self._zaap

    @zaap.setter
    def zaap(self, value) -> None:
        with self._macro_init_lock:
            self._zaap = value

    @property
    def auto_group(self):
        with self._macro_init_lock:
            if self._auto_group is None:
                from app.macros.auto_group import AutoGroupMacro

                self._auto_group = AutoGroupMacro(self)
            return self._auto_group

    @auto_group.setter
    def auto_group(self, value) -> None:
        with self._macro_init_lock:
            self._auto_group = value

    @property
    def is_starting(self) -> bool:
        with self._state_lock:
            return self._starting

    def _emit_status(self, text: str) -> None:
        bridge = self._callback_bridge
        if bridge is not None:
            bridge.publish_status(str(text))
        else:
            self.status_callback(str(text))

    def _emit_active(self, active: bool) -> None:
        bridge = self._callback_bridge
        if bridge is not None:
            bridge.publish_active(bool(active))
        else:
            self.active_callback(bool(active))

    def start(self) -> None:
        with self._state_lock:
            if self._running:
                already_running = True
            elif self._starting:
                # Organizer may refresh CLIENT_INDEX_JSON while the first hook is
                # still starting. Preserve that reload instead of silently losing it.
                self._startup_reload_requested = True
                return
            else:
                already_running = False

        if already_running:
            self.reload_hotkeys()
            if not self._admin_ok:
                self.registry.stop()
                self.mouse_hook.stop()
                with self._state_lock:
                    self._running = False
                self._emit_active(False)
                self.logger.error("Runtime Python arrete: droits insuffisants apres reload.")
            return

        with self._state_lock:
            if self._running or self._starting:
                return
            self._startup_cancel.clear()
            self._startup_reload_requested = False
            self._starting = True
            thread = threading.Thread(
                target=self._start_hooks_worker,
                name="DofusAtlas-RuntimeStartup",
                daemon=True,
            )
            self._startup_thread = thread
        thread.start()

    def _consume_startup_reload_requests(self) -> None:
        while not self._startup_cancel.is_set():
            with self._state_lock:
                requested = self._startup_reload_requested
                self._startup_reload_requested = False
            if not requested:
                return
            self.reload_hotkeys()

    def _start_hooks_worker(self) -> None:
        keyboard_ok = False
        mouse_ok = False
        cancelled = False
        restart_requested = False
        try:
            enable_dpi_awareness()
            self.reload_hotkeys()
            self._consume_startup_reload_requests()
            cancelled = self._startup_cancel.is_set()
            if cancelled:
                return
            if not self._runtime_bindings_available:
                self.logger.info("Runtime Python en attente: aucune session Unity detectee.")
                self._emit_active(False)
                return
            if not self._admin_ok:
                self.logger.error("Runtime Python non demarre: droits insuffisants pour les hooks.")
                self._emit_active(False)
                self._emit_status("Dofus est lance en administrateur: relancer Atlas en administrateur.")
                return

            keyboard_ok = bool(self.registry.start())
            cancelled = self._startup_cancel.is_set()
            if not cancelled and keyboard_ok:
                mouse_ok = bool(self.mouse_hook.start())
                cancelled = self._startup_cancel.is_set()

            # A session scan can complete while either hook is in its bounded
            # startup wait. Apply the newest settings before publishing readiness.
            if not cancelled:
                self._consume_startup_reload_requests()
                cancelled = self._startup_cancel.is_set()

            running = bool(keyboard_ok and mouse_ok and self._admin_ok and not cancelled)
            with self._state_lock:
                self._running = running

            if cancelled:
                return

            self._emit_active(running)
            if running:
                self.logger.info("Runtime Python demarre.")
                if self.settings.clients:
                    self._emit_status("Runtime Python actif.")
                else:
                    self.logger.warning("Runtime Python actif sans session Unity detectee.")
                    self._emit_status("Runtime Python actif: aucune session Unity detectee.")
                return

            self.logger.error("Runtime Python partiel: keyboard=%s mouse=%s", keyboard_ok, mouse_ok)
            self._emit_status("Hooks Python indisponibles: relancer Atlas avec les memes droits que Dofus.")
        except Exception:
            self.logger.exception("Demarrage asynchrone du runtime Python impossible.")
            with self._state_lock:
                self._running = False
            if not self._startup_cancel.is_set():
                self._emit_active(False)
                self._emit_status("Hooks Python indisponibles: erreur pendant le demarrage du runtime.")
        finally:
            with self._state_lock:
                running = self._running
            if self._startup_cancel.is_set() or not running:
                # Hook start() can have succeeded just before a cancellation or a
                # failure on the second hook. Always tear partial state down.
                self.registry.stop()
                self.mouse_hook.stop()
                with self._state_lock:
                    self._running = False
                if self._startup_cancel.is_set():
                    self._emit_active(False)
            with self._state_lock:
                restart_requested = bool(
                    self._startup_reload_requested and not self._startup_cancel.is_set()
                )
                self._startup_reload_requested = False
                self._starting = False
                if self._startup_thread is threading.current_thread():
                    self._startup_thread = None
            # Cover the tiny race where a second start() lands after the final
            # reload drain but before this worker clears `_starting`.
            if restart_requested:
                self.start()

    def wait_for_startup(self, timeout: float | None = None) -> bool:
        with self._state_lock:
            thread = self._startup_thread
        if thread is not None and thread is not threading.current_thread() and thread.is_alive():
            thread.join(timeout)
        with self._state_lock:
            return bool(self._running and not self._starting)

    def _cancel_pending_startup(self) -> None:
        self._startup_cancel.set()
        with self._state_lock:
            self._startup_reload_requested = False
            thread = self._startup_thread
        if thread is None or thread is threading.current_thread() or not thread.is_alive():
            return
        thread.join(RUNTIME_STARTUP_JOIN_TIMEOUT_SECONDS)
        if thread.is_alive():
            self.logger.error("Thread de demarrage runtime toujours actif apres demande d'arret.")

    def stop(self) -> None:
        self._cancel_pending_startup()
        self.emergency_stop("arret runtime")
        self._join_macro_threads()
        self.registry.stop()
        self.mouse_hook.stop()
        with self._state_lock:
            self._running = False
        self._emit_active(False)
        self.logger.info("Runtime Python arrete.")
        self._emit_status("Runtime Python arrete.")

    def _join_macro_threads(self) -> None:
        current = threading.current_thread()
        threads = [thread for thread in self._threads if thread is not current and thread.is_alive()]
        for thread in threads:
            thread.join(MACRO_THREAD_JOIN_TIMEOUT_SECONDS)
        self._threads = [thread for thread in threads if thread.is_alive()]
        if self._threads:
            self.logger.error(
                "Threads macro encore actifs apres arret: %s",
                [thread.name for thread in self._threads],
            )

    def reload_hotkeys(self, force_restart: bool = False) -> None:
        self.settings = load_settings()
        set_debug_logging(self.settings.debug_enabled)
        if not self.settings.clients:
            # No client means no keyboard/mouse action can target Dofus. Avoid
            # importing/constructing the Win32 hook backends merely to wait.
            self._runtime_bindings_available = False
            self._admin_ok = True
            self.synthetic_guard.reset()
            self.input_state.reset_armed()
            self._emit_active(False)
            self._emit_status("Runtime Python en attente: aucune session Unity detectee.")
            return

        self._runtime_bindings_available = True
        report = self.registry.register_hotkeys(build_runtime_hotkey_actions(self.settings))
        admin_audit = audit_client_admin_rights((client.handle for client in self.settings.clients), self.logger)
        self._admin_ok = admin_audit.ok
        self.synthetic_guard.reset()
        self.input_state.reset_armed()
        # The activity badge represents real hook execution, not configuration
        # readiness. A bad optional/individual binding can warn without claiming
        # that an already-running hook runtime has stopped.
        self._emit_active(bool(self._running and self._admin_ok))
        for error in report.errors:
            self.logger.warning(error)
        if not admin_audit.ok:
            self._emit_status("Dofus est lance en administrateur: relancer Atlas en administrateur.")
        elif report.errors:
            self._emit_status("Raccourcis recharges avec avertissement.")
        elif not self.settings.clients:
            self.logger.warning("Aucune session Unity chargee pour les macros Python.")
            self._emit_status("Raccourcis recharges: aucune session Unity detectee.")
        else:
            self._emit_status("Raccourcis Python recharges." if force_restart else "Runtime Python pret.")

    def launch_travel(self, text: str) -> None:
        self.settings = load_settings()
        self.travel.run_async(text)

    def launch_guide_travel(self, text: str, character_keys) -> None:
        self.settings = load_settings()
        self.travel.run_async(text, tuple(character_keys or ()))

    def launch_zaap(self, text: str, click_position=None, click_ratios=None) -> bool:
        self.settings = load_settings()
        return bool(self.zaap.run_async(
            text, click_position=click_position, click_ratios=click_ratios,
        ))

    def launch_auto_group(self, invite_entries: list[dict[str, object]]) -> bool:
        self.settings = load_settings()
        return bool(self.auto_group.run_async(invite_entries))

    def emergency_stop(self, reason: str = "stop urgence") -> None:
        self.macro_lock.request_stop(reason)
        self._pending_physical_switch = None
        self.input_state.reset_armed()
        self.input_state.clear_mouse_block()
        self.synthetic_guard.reset()
        with self._macro_init_lock:
            switch_click = self._switch_click
            direction = self._direction
        if switch_click is not None:
            switch_click.reset()
        if direction is not None:
            direction.release_virtual_inputs()
        release_common_inputs()
        self.logger.warning("Stop urgence Python: etats internes remis a zero.")
        self._emit_status("Stop urgence: macros Python arretees.")

    def _spawn_macro(self, label: str, target: Callable[[], None]) -> bool:
        if not self.macro_lock.try_begin(label):
            return False

        def runner() -> None:
            try:
                target()
            except Exception:
                self.logger.exception("%s erreur non geree.", label)
            finally:
                self.synthetic_guard.reset()
                self.macro_lock.end(label)

        thread = None
        try:
            thread = threading.Thread(target=runner, name=f"DofusAtlas-{label}", daemon=True)
            self._threads = [worker for worker in self._threads if worker.is_alive()]
            self._threads.append(thread)
            thread.start()
        except Exception:
            # Preserve tracking before start() in case stop() races startup,
            # but never leak the exclusive lease on construction/start failure.
            if thread is not None and thread in self._threads:
                self._threads.remove(thread)
            self.macro_lock.end(label)
            self.logger.exception("%s impossible de demarrer le thread macro.", label)
            self._emit_status(f"{label}: lancement impossible.")
            return False
        return True

    def _handle_hotkey(self, action_id: str, payload: dict[str, object]) -> None:
        if action_id == "stop_script":
            self.logger.warning("Stop urgence recu par raccourci.")
            self.emergency_stop("raccourci")
            return
        if not self._running or not self._admin_ok:
            self.logger.debug(
                "Raccourci ignore: runtime actif=%s admin_ok=%s action=%s",
                self._running,
                self._admin_ok,
                action_id,
            )
            return
        settings = self.settings
        if settings.macro_mode == "mirror":
            return
        if action_id == "next_character":
            if settings.switch_character_enabled and self.settings is settings:
                self.switch_character.activate_next(expected_profile=settings)
            return
        if action_id.startswith("client:"):
            raw_index = payload.get("client_index", 0)
            # Do not truncate bool/float/fractional aliases before the
            # strict slot check in SwitchCharacterMacro receives the value.
            if type(raw_index) not in (int, str):
                self.logger.debug("Payload invalide pour switch personnage: action=%s payload=%s", action_id, payload)
                return
            try:
                client_index = int(raw_index)
            except (TypeError, ValueError, OverflowError):
                self.logger.debug("Payload invalide pour switch personnage: action=%s payload=%s", action_id, payload)
                return
            if not settings.switch_character_enabled or action_id != f"client:{client_index}":
                self.logger.debug("Raccourci personnage périmé ou désactivé: action=%s", action_id)
                return
            # The registry binds a slot AND its HWND. An old callback from a
            # replaced Organizer roster must not activate a different client
            # newly assigned to the same index. Legacy payloads lack handle.
            bound_handle = payload.get("handle")
            if bound_handle is not None and (
                type(bound_handle) is not int or not 0 < bound_handle <= (2**64 - 1)
                or not any(
                    client.index == client_index and client.handle == bound_handle
                    for client in settings.clients
                )
            ):
                self.logger.debug("Raccourci personnage périmé: action=%s", action_id)
                return
            if self.settings is not settings:
                self.logger.debug("Raccourci personnage abandonné: profil Organizer modifié.")
                return
            self.switch_character.activate_by_index(
                client_index, expected_profile=settings,
            )
            return
        if action_id.startswith("direction:"):
            key_name = payload.get("key_name")
            if (
                not settings.movement_enabled
                or type(key_name) is not str
                or key_name not in ("HOME", "DELETE", "END", "PAGEDOWN")
                or action_id != f"direction:{key_name}"
            ):
                self.logger.debug("Payload invalide pour direction: action=%s payload=%s", action_id, payload)
                return
            if self.settings is not settings:
                self.logger.debug("Raccourci déplacement abandonné: profil Organizer modifié.")
                return
            self.direction.run_async(key_name, expected_profile=settings)
            return

    def _mirror_gesture_targets(self) -> tuple[int, tuple[int, ...]] | None:
        """Snapshot one real starred Unity DOFUS source and its session roster."""
        from app.macros.mirror_plan import (
            is_dofus_unity_process, mirror_delivery_targets,
        )
        from app.windows.unity_windows import is_unity_window

        if (not self._running or not self._admin_ok
                or self.settings.macro_mode != "mirror"):
            return None
        settings = self.settings
        source = settings.primary_handle
        favorite = settings.client_by_handle(source) if source else None
        if favorite is None or not is_unity_window(source):
            return None
        if not is_dofus_unity_process(source):
            return None
        # Never silently drop a stale/foreign client. Consuming the physical
        # key or wheel for a reduced roster would lose the source gesture
        # when the worker rejects that snapshot against the live settings.
        live = tuple(client.handle for client in settings.clients)
        if (not 2 <= len(live) <= 8
                or any(type(hwnd) is not int or not 0 < hwnd <= (2**64 - 1) for hwnd in live)
                or len(set(live)) != len(live)
                or source not in live):
            return None
        if not all(
            is_unity_window(hwnd) and is_dofus_unity_process(hwnd)
            for hwnd in live if hwnd != source
        ):
            return None
        # Profiles are replaced atomically on reload. Native process reads
        # may release the GIL, so a previous snapshot must not authorize
        # consumption of a gesture after settings have changed.
        if self.settings is not settings:
            return None
        targets = mirror_delivery_targets(
            live, live, source, source_was_consumed=True,
        )
        # The favorite may be any Organizer slot. Keyboard/wheel workers
        # always begin with that physical source; preserve the relative
        # order of all other clients.
        if len(targets) < 2 or source not in targets:
            return None
        ordered = (source, *(hwnd for hwnd in targets if hwnd != source))
        return source, ordered

    def _report_mirror_busy_input(self, kind: str) -> None:
        """Bounded non-sensitive warning when an input cannot join a busy fan-out."""
        now = monotonic()
        previous = getattr(self, "_last_mirror_busy_notice_at", 0.0)
        if type(previous) not in (int, float) or now - previous >= 0.5:
            self._last_mirror_busy_notice_at = now
            self.logger.warning(
                "Miroir occupe: entree physique %s non synchronisee, sans replay.", kind,
            )
            self._emit_status(
                "Miroir desynchronise : geste non diffuse sur tous les comptes."
            )

    def _handle_mirror_key(self, vk_code: int, pressed: bool) -> bool:
        """Forward only short standalone keystrokes; never modifier/OS chords."""
        from app.input.hotkeys import MIRROR_DISCRETE_KEYS
        from app.windows.unity_windows import foreground_window

        # Reject reserved keys and malformed callbacks before any expensive
        # Win32 focus/process query, even if this method is called directly.
        if (type(pressed) is not bool or type(vk_code) is not int
                or vk_code not in MIRROR_DISCRETE_KEYS):
            return False
        if not pressed:
            return False
        settings = self.settings
        if (not self._running or not self._admin_ok
                or settings.macro_mode != "mirror"):
            return False
        if getattr(settings, "radial_enabled", False) is True:
            radial_text = getattr(settings, "radial_hotkey", "")
            if type(radial_text) is str and radial_text:
                from app.input.hotkeys import parsed_hotkey_keys

                if vk_code in parsed_hotkey_keys(radial_text):
                    # The radial hold-controller owns this physical key.
                    # Do not broadcast it as an extra mirrored tap.
                    return False
        foreground = foreground_window()
        if self.macro_lock.active_label:
            # The existing worker cannot accept a second gesture. Keep real
            # input native if the favorite is still foreground; never enqueue
            # an old key for replay after Stop, reload or focus changes.
            if foreground == settings.primary_handle:
                AtlasRuntime._report_mirror_busy_input(self, "clavier")
                return False
            # During fan-out, suppress only for a trusted secondary while
            # the EXACT profile generation still owns this busy gesture.
            from app.macros.mirror_plan import is_dofus_unity_process

            trusted = (
                foreground in (c.handle for c in settings.clients)
                and is_dofus_unity_process(foreground)
            )
            if not trusted or self.settings is not settings:
                return False
            AtlasRuntime._report_mirror_busy_input(self, "clavier")
            return self.settings is settings
        # Never probe the entire 8-client roster for a key typed into
        # another application or a non-favorite DOFUS window.
        if foreground != settings.primary_handle:
            return False
        snapshot = self._mirror_gesture_targets()
        if snapshot is None:
            return False
        source, targets = snapshot
        if foreground != source or self.settings is not settings:
            return False
        try:
            return bool(self.mirror_input.run_key(
                vk_code, source, targets, expected_profile=settings,
            ))
        except Exception:
            self.logger.exception("Miroir clavier: lancement impossible.")
            return False

    def _handle_mirror_wheel(
        self, delta: int, screen_x: int, screen_y: int, horizontal: bool,
    ) -> bool:
        # A malformed native callback must never trigger a full 8-client
        # identity scan or consume a wheel tick. POINT is a signed LONG.
        if (type(delta) is not int or delta == 0 or abs(delta) > 32767
                or type(horizontal) is not bool
                or type(screen_x) is not int or type(screen_y) is not int
                or not -(2**31) <= screen_x < 2**31
                or not -(2**31) <= screen_y < 2**31):
            return False
        from app.windows.unity_windows import (
            client_point_ratio, find_known_client_from_point,
            foreground_window, screen_to_client,
        )

        settings = self.settings
        if (not self._running or not self._admin_ok
                or settings.macro_mode != "mirror"):
            return False
        foreground = foreground_window()
        if self.macro_lock.active_label:
            # A wheel tick on the still-focused favorite stays physical.
            # A busy worker cannot safely replay it to every client later.
            if foreground == settings.primary_handle:
                AtlasRuntime._report_mirror_busy_input(self, "molette")
                return False
            # Temporary secondary focus is protected only while the profile
            # that authorized the busy Miroir still owns this gesture.
            from app.macros.mirror_plan import is_dofus_unity_process

            trusted = (
                foreground in (c.handle for c in settings.clients)
                and is_dofus_unity_process(foreground)
            )
            if not trusted or self.settings is not settings:
                return False
            AtlasRuntime._report_mirror_busy_input(self, "molette")
            return self.settings is settings
        # A wheel gesture outside the favorite should cost no roster scans.
        if foreground != settings.primary_handle:
            return False
        if find_known_client_from_point(
            screen_x, screen_y, (foreground,),
        ) != foreground:
            return False
        snapshot = self._mirror_gesture_targets()
        if snapshot is None:
            return False
        source, targets = snapshot
        if foreground != source:
            return False
        if find_known_client_from_point(screen_x, screen_y, (source,)) != source:
            return False
        point = screen_to_client(source, screen_x, screen_y)
        ratio = client_point_ratio(source, *point) if point is not None else None
        if ratio is None or self.settings is not settings:
            return False
        try:
            return bool(self.mirror_input.run_wheel(
                delta, horizontal, ratio[0], ratio[1], source, targets,
                expected_profile=settings,
            ))
        except Exception:
            self.logger.exception("Miroir molette: lancement impossible.")
            return False

    def _handle_mirror_click(self, button: str, screen_x: int, screen_y: int) -> bool:
        """Replay a consumed favorite-window click through the existing sender.

        Fail closed without an explicit favorite or a real physical click on
        that foreground Unity window. Do not create a parallel input backend.
        """
        from app.windows.unity_windows import (
            find_known_client_from_point, foreground_window, is_unity_window,
        )
        from app.macros.mirror_plan import mirror_delivery_targets, is_dofus_unity_process

        if (type(button) is not str or button.casefold() not in {"left", "right"}
                or type(screen_x) is not int or type(screen_y) is not int
                or not -(2**31) <= screen_x < 2**31
                or not -(2**31) <= screen_y < 2**31):
            return False
        # A keyboard worker never owns the pointer; a wheel worker only
        # owns it after preflight. The native event is intentionally left
        # alone: do not perform 2–8 expensive process probes inside the
        # low-level mouse hook merely to decide to pass a click through.
        busy = self.macro_lock.active_label
        if busy and not self.input_state.is_mouse_blocked():
            # A queued click worker is not yet moving the pointer. Preserve
            # ordinary native gestures until it actually acquires its mouse
            # block; do not run a full DOFUS roster probe from the hook.
            return False
        settings = self.settings
        # The physical click can arrive while the UI switches Macro/Miroir.
        # A mode decision made before a profile reload is not authority to
        # broadcast the event under the new mode.
        if settings.macro_mode != "mirror" or not settings.primary_handle:
            return False
        # Check the focused/pointed window BEFORE scanning the roster.
        # Physical mouse hooks run globally, including over other apps.
        if foreground_window() != settings.primary_handle:
            return False
        if find_known_client_from_point(
            screen_x, screen_y, (settings.primary_handle,),
        ) != settings.primary_handle:
            return False
        favorite = settings.client_by_handle(settings.primary_handle)
        if (favorite is None or not is_unity_window(favorite.handle)
                or not is_dofus_unity_process(favorite.handle)):
            return False
        # The source click will be consumed only if *every* configured
        # character is still valid. Filtering missing windows would create
        # an unsafe partial mirror and silently drop the user's click.
        live_handles = tuple(client.handle for client in settings.clients)
        if (not 2 <= len(live_handles) <= 8
                or any(type(hwnd) is not int or not 0 < hwnd <= (2**64 - 1) for hwnd in live_handles)
                or len(set(live_handles)) != len(live_handles)
                or favorite.handle not in live_handles):
            return False
        if not all(
            is_unity_window(hwnd) and is_dofus_unity_process(hwnd)
            for hwnd in live_handles if hwnd != favorite.handle
        ):
            return False
        # Do not swallow a physical DOWN for the old favorite if Organizer
        # reloaded while Win32 was verifying the 2–8 client processes.
        if self.settings is not settings:
            return False
        destinations = mirror_delivery_targets(
            live_handles, live_handles, favorite.handle, source_was_consumed=True,
        )
        if len(destinations) < 2 or self.settings is not settings:
            return False
        if busy:
            # Direct calls remain fail-safe while a worker owns the pointer.
            # MouseHook suppresses these physical DOWNs before this callback.
            AtlasRuntime._report_mirror_busy_input(self, "clic")
            return True
        try:
            return bool(self.switch_click.run_async(
                button, screen_x, screen_y, 1, "Miroir",
                exact_source_handle=favorite.handle,
                mirror_target_handles=destinations,
                expected_profile=settings,
            ))
        except Exception:
            self.logger.exception("Miroir: démarrage impossible.")
            return False

    def _handle_mouse_click(self, button: str, screen_x: int, screen_y: int) -> bool:
        if not self._running or not self._admin_ok:
            self.logger.debug(
                "Clic ignore: runtime actif=%s admin_ok=%s button=%s x=%s y=%s",
                self._running,
                self._admin_ok,
                button,
                screen_x,
                screen_y,
            )
            return False
        # A new physical DOWN before the previously captured native UP
        # makes the click pair ambiguous (double press or overlapping
        # buttons). Keep BOTH gestures native and cancel the pending replay:
        # never clone an action whose DOWN/UP can no longer be paired safely.
        pending = getattr(self, "_pending_physical_switch", None)
        if isinstance(pending, tuple) and len(pending) in (7, 8):
            self._pending_physical_switch = None
            self.logger.debug(
                "Clic natif non recopié: cause=overlapping_down button=%s",
                button,
            )
            return False
        settings = self.settings
        if settings.macro_mode == "mirror":
            return self._handle_mirror_click(button, screen_x, screen_y)
        action = self.registry.switch_action_for_pressed_keys()
        if self.settings is not settings:
            # Register lookups can overlap a reload. Never use an old hotkey
            # to consume the first physical DOWN of a replacement profile.
            self.logger.debug("Clic switch abandonné: profil Organizer modifié pendant raccourci.")
            return False
        if action is None:
            self.logger.debug(
                "Clic sans macro: aucun raccourci switch physiquement maintenu button=%s x=%s y=%s",
                button,
                screen_x,
                screen_y,
            )
            return False
        active_macro = self.macro_lock.active_label
        if active_macro and not self.input_state.is_mouse_blocked():
            # Any prevalidating macro that does not own the pointer must leave
            # native DOWN/UP untouched, including Zaap and Auto-groupe.
            return False
        if active_macro:
            # The mouse hook is global. During the narrow interval between
            # MacroLock acquisition and the sender's input block, never eat a
            # click in an unrelated app just because a switch hotkey is held.
            from app.windows.unity_windows import (
                find_known_client_from_point, foreground_window,
            )
            from app.macros.mirror_plan import is_dofus_unity_process

            foreground = foreground_window()
            if (
                foreground not in (c.handle for c in settings.clients)
                or find_known_client_from_point(
                    screen_x, screen_y, (foreground,),
                ) != foreground
                or not is_dofus_unity_process(foreground)
                or self.settings is not settings
            ):
                return False
            self.logger.debug(
                "Clic switch consomme: macro deja active=%s button=%s x=%s y=%s",
                active_macro,
                button,
                screen_x,
                screen_y,
            )
            return True
        try:
            click_count = int(action.payload.get("click_count", 1))
        except (TypeError, ValueError, OverflowError):
            self.logger.debug("Payload switch invalide: action=%s payload=%s", action.action_id, action.payload)
            click_count = 1
        action_label = str(action.payload.get("label", "Switch clique"))
        # Unity world targets can require the native DOWN/UP pair on the
        # foreground source. Keep that pair intact for a simple click and
        # replay only the other clients after physical release.
        if click_count == 1 and str(button).casefold() in {"left", "right"}:
            profile_at_press = settings
            from app.windows.unity_windows import (
                find_known_client_from_point, foreground_window,
            )
            from app.macros.mirror_plan import is_dofus_unity_process

            source = find_known_client_from_point(
                screen_x, screen_y,
                (client.handle for client in settings.clients),
            )
            if (self.settings is not settings):
                return False
            if (source and foreground_window() == source
                    and is_dofus_unity_process(int(source))):
                context = self.switch_click._capture_trigger_context(
                    screen_x, screen_y, action_label,
                )
                if self.settings is not profile_at_press:
                    # The old physical DOWN is already native. Never fall
                    # through to a synthetic replay under the new profile.
                    self.logger.debug("Clic natif non recopié: cause=profile_changed_during_capture")
                    return False
                if (context is not None and context.reason == "cursor"
                        and context.source_hwnd == source):
                    self._pending_physical_switch = (
                        button, screen_x, screen_y, click_count,
                        action_label, context, monotonic(), profile_at_press,
                    )
                    return False
        try:
            started = self.switch_click.run_async(
                button,
                screen_x,
                screen_y,
                click_count,
                action_label,
                expected_profile=settings,
            )
        except Exception:
            self.logger.exception(
                "Déclenchement switch clique impossible: action=%s",
                action_label,
            )
            # No worker owns this DOWN: let the native event reach Unity.
            return False

        if not started:
            self.logger.debug(
                "Clic switch non intercepté: lancement refusé action=%s",
                action_label,
            )
            return False
        return True

    def _handle_mouse_release(self, button: str, screen_x: int, screen_y: int) -> bool:
        """Finish one native foreground click, then replay to other clients.

        True asks the hook to FORWARD the real UP even when the asynchronous
        replay begins blocking later gestures. It does not claim replay worked.
        """
        pending = getattr(self, "_pending_physical_switch", None)
        if (not isinstance(pending, tuple) or len(pending) not in (7, 8)
                or str(pending[0]).casefold() != str(button).casefold()):
            return False
        self._pending_physical_switch = None
        (_button, down_x, down_y, count, label, context, captured_at) = pending[:7]
        profile_at_press = pending[7] if len(pending) == 8 else None
        from app.windows.unity_windows import foreground_window
        from app.macros.mirror_plan import is_dofus_unity_process

        try:
            reason = None
            if not self._running or not self._admin_ok:
                reason = "runtime_unavailable"
            elif profile_at_press is not None and self.settings is not profile_at_press:
                reason = "profile_replaced"
            elif self.settings.macro_mode != "macro":
                reason = "mode_changed"
            elif self.macro_lock.should_stop():
                reason = "emergency_stop"
            elif self.macro_lock.active_label:
                reason = "worker_busy"
            elif not 0 <= monotonic() - captured_at <= 2.0:
                reason = "expired"
            elif (int(screen_x) - down_x) ** 2 + (int(screen_y) - down_y) ** 2 > 24 ** 2:
                reason = "drag_or_moved"
            elif foreground_window() != context.source_hwnd:
                reason = "focus_changed"
            elif not is_dofus_unity_process(context.source_hwnd):
                reason = "source_untrusted"
            elif (profile_at_press is not None
                  and self.settings is not profile_at_press):
                # A native process probe can release the GIL and reload the
                # roster even after our first generation check.
                reason = "profile_replaced"
            if reason is not None:
                self.logger.debug(
                    "Clic natif non recopié: cause=%s button=%s",
                    reason, button,
                )
                return True
            replay_kwargs = (
                {"expected_profile": profile_at_press}
                if profile_at_press is not None else {}
            )
            if not self.switch_click.run_async(
                button, down_x, down_y, count, label,
                captured_context=context,
                physical_source_delivered=True,
                **replay_kwargs,
            ):
                self.logger.warning(
                    "Clic natif non recopié: cause=dispatch_refused button=%s",
                    button,
                )
        except Exception:
            self.logger.exception("%s: duplication après clic physique impossible.", label)
        # Native UP must ALWAYS reach Unity, regardless of replay success.
        return True
