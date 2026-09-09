from __future__ import annotations

import threading
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
        self._direction = None
        self._travel = None
        self._zaap = None
        self._auto_group = None
        self.registry = ManagedHotkeyRegistry(self.input_state, self.logger, self._handle_hotkey)
        self.mouse_hook = ManagedMouseHook(self.input_state, self.synthetic_guard, self.logger, self._handle_mouse_click)
        self.last_client_point = LastClientPoint()
        self.active_client_handle = 0
        self._running = False
        self._admin_ok = True
        self._state_lock = threading.RLock()
        self._startup_cancel = threading.Event()
        self._startup_thread: threading.Thread | None = None
        self._startup_reload_requested = False
        self._starting = False
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
        self.registry.stop()
        self.mouse_hook.stop()
        with self._state_lock:
            self._running = False
        self._emit_active(False)
        self.logger.info("Runtime Python arrete.")
        self._emit_status("Runtime Python arrete.")

    def reload_hotkeys(self, force_restart: bool = False) -> None:
        self.settings = load_settings()
        set_debug_logging(self.settings.debug_enabled)
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

    def launch_zaap(self, text: str, click_position=None, click_ratios=None) -> None:
        self.settings = load_settings()
        self.zaap.run_async(text, click_position=click_position, click_ratios=click_ratios)

    def launch_auto_group(self, invite_entries: list[dict[str, object]]) -> None:
        self.settings = load_settings()
        self.auto_group.run_async(invite_entries)

    def emergency_stop(self, reason: str = "stop urgence") -> None:
        self.macro_lock.request_stop(reason)
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

        thread = threading.Thread(target=runner, name=f"DofusAtlas-{label}", daemon=True)
        self._threads = [thread for thread in self._threads if thread.is_alive()]
        self._threads.append(thread)
        thread.start()
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
        if action_id.startswith("client:"):
            try:
                client_index = int(payload.get("client_index", 0))
            except (TypeError, ValueError):
                self.logger.debug("Payload invalide pour switch personnage: action=%s payload=%s", action_id, payload)
                return
            self.switch_character.activate_by_index(client_index)
            return
        if action_id.startswith("direction:"):
            key_name = str(payload.get("key_name", "")).strip()
            if not key_name:
                self.logger.debug("Payload invalide pour direction: action=%s payload=%s", action_id, payload)
                return
            self.direction.run_async(key_name)
            return

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
        action = self.registry.switch_action_for_pressed_keys()
        if action is None:
            self.logger.debug(
                "Clic sans macro: aucun raccourci switch physiquement maintenu button=%s x=%s y=%s",
                button,
                screen_x,
                screen_y,
            )
            return False
        active_macro = self.macro_lock.active_label
        if active_macro:
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
        except (TypeError, ValueError):
            self.logger.debug("Payload switch invalide: action=%s payload=%s", action.action_id, action.payload)
            click_count = 1
        action_label = str(action.payload.get("label", "Switch clique"))
        try:
            started = self.switch_click.run_async(
                button,
                screen_x,
                screen_y,
                click_count,
                action_label,
            )
        except Exception:
            self.logger.exception(
                "Déclenchement switch clique impossible: action=%s",
                action_label,
            )
            return True

        if not started:
            self.logger.debug(
                "Clic switch consommé sans lancement: action=%s",
                action_label,
            )
        return True
