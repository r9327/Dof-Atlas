from __future__ import annotations

import ctypes
import ctypes.wintypes
import os
import re
import threading
from dataclasses import dataclass, field
from logging import Logger
from typing import Callable

from app.core.settings import AtlasSettings
from app.input.hook_lifecycle import current_native_thread_id, stop_message_hook
from app.input.input_state import InputState

HotkeyCallback = Callable[[str, dict[str, object]], None]

WH_KEYBOARD_LL = 13
WM_KEYDOWN = 0x0100
WM_KEYUP = 0x0101
WM_SYSKEYDOWN = 0x0104
WM_SYSKEYUP = 0x0105
LLKHF_INJECTED = 0x00000010
HOOK_START_TIMEOUT_SECONDS = 2.0

VK_CONTROL = 0x11
VK_SHIFT = 0x10
VK_MENU = 0x12
VK_LWIN = 0x5B
LEFT_RIGHT_MODIFIERS = {
    0xA2: VK_CONTROL,
    0xA3: VK_CONTROL,
    0xA0: VK_SHIFT,
    0xA1: VK_SHIFT,
    0xA4: VK_MENU,
    0xA5: VK_MENU,
    0x5C: VK_LWIN,
}
MODIFIER_VKS = frozenset({VK_CONTROL, VK_SHIFT, VK_MENU, VK_LWIN})

MODIFIER_ORDER = ("CTRL", "ALT", "SHIFT", "WIN")
MODIFIER_ALIASES = {
    "CTRL": (VK_CONTROL, "CTRL"),
    "CONTROL": (VK_CONTROL, "CTRL"),
    "LCTRL": (VK_CONTROL, "CTRL"),
    "RCTRL": (VK_CONTROL, "CTRL"),
    "ALT": (VK_MENU, "ALT"),
    "MENU": (VK_MENU, "ALT"),
    "SHIFT": (VK_SHIFT, "SHIFT"),
    "LSHIFT": (VK_SHIFT, "SHIFT"),
    "RSHIFT": (VK_SHIFT, "SHIFT"),
    "WIN": (VK_LWIN, "WIN"),
    "LWIN": (VK_LWIN, "WIN"),
    "RWIN": (VK_LWIN, "WIN"),
    "WINDOWS": (VK_LWIN, "WIN"),
}

NAMED_KEYS = {
    "ESC": 0x1B,
    "ESCAPE": 0x1B,
    "RETURN": 0x0D,
    "ENTER": 0x0D,
    "SPACE": 0x20,
    "TAB": 0x09,
    "BACKSPACE": 0x08,
    "DELETE": 0x2E,
    "DEL": 0x2E,
    "INSERT": 0x2D,
    "INS": 0x2D,
    "HOME": 0x24,
    "END": 0x23,
    "PAGEUP": 0x21,
    "PAGEDOWN": 0x22,
    "PGUP": 0x21,
    "PGDN": 0x22,
    "UP": 0x26,
    "DOWN": 0x28,
    "LEFT": 0x25,
    "RIGHT": 0x27,
    "PAUSE": 0x13,
    "PRINTSCREEN": 0x2C,
    "CAPSLOCK": 0x14,
    "NUMLOCK": 0x90,
    "SCROLLLOCK": 0x91,
    "/": 0xBF,
    "\\": 0xDC,
    ";": 0xBA,
    ",": 0xBC,
    ".": 0xBE,
    "-": 0xBD,
    "=": 0xBB,
    "'": 0xDE,
    "`": 0xC0,
}
for index in range(1, 25):
    NAMED_KEYS[f"F{index}"] = 0x6F + index


@dataclass(frozen=True)
class HotkeySpec:
    text: str
    keys: frozenset[int]
    canonical: str

    def matches(self, pressed: set[int]) -> bool:
        if not self.keys or not self.keys.issubset(pressed):
            return False

        # Un raccourci sans ALT ne doit pas être déclenché par ALT+TAB,
        # ALT+ECHAP, etc. Les touches non modificatrices supplémentaires
        # restent autorisées, mais les modificateurs doivent correspondre
        # exactement à ceux configurés dans le raccourci.
        required_modifiers = self.keys.intersection(MODIFIER_VKS)
        pressed_modifiers = pressed.intersection(MODIFIER_VKS)
        return required_modifiers == pressed_modifiers


@dataclass(frozen=True)
class HotkeyAction:
    action_id: str
    label: str
    hotkey_text: str
    kind: str
    payload: dict[str, object] = field(default_factory=dict)
    spec: HotkeySpec | None = None
    enabled: bool = True
    error: str = ""


@dataclass(frozen=True)
class HotkeyReport:
    actions: tuple[HotkeyAction, ...]
    errors: tuple[str, ...]

    @property
    def ok(self) -> bool:
        return not self.errors


class KBDLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [
        ("vkCode", ctypes.c_ulong),
        ("scanCode", ctypes.c_ulong),
        ("flags", ctypes.c_ulong),
        ("time", ctypes.c_ulong),
        ("dwExtraInfo", ctypes.c_void_p),
    ]


LRESULT = getattr(ctypes.wintypes, "LRESULT", ctypes.c_ssize_t)
LowLevelKeyboardProc = getattr(ctypes, "WINFUNCTYPE", ctypes.CFUNCTYPE)(
    LRESULT,
    ctypes.c_int,
    ctypes.wintypes.WPARAM,
    ctypes.wintypes.LPARAM,
)


def _configure_hook_api(user32, kernel32) -> None:
    kernel32.GetModuleHandleW.argtypes = (ctypes.wintypes.LPCWSTR,)
    kernel32.GetModuleHandleW.restype = ctypes.c_void_p
    kernel32.GetLastError.argtypes = ()
    kernel32.GetLastError.restype = ctypes.wintypes.DWORD
    user32.SetWindowsHookExW.argtypes = (
        ctypes.c_int,
        LowLevelKeyboardProc,
        ctypes.c_void_p,
        ctypes.wintypes.DWORD,
    )
    user32.SetWindowsHookExW.restype = ctypes.c_void_p
    user32.UnhookWindowsHookEx.argtypes = (ctypes.c_void_p,)
    user32.UnhookWindowsHookEx.restype = ctypes.wintypes.BOOL
    user32.CallNextHookEx.argtypes = (
        ctypes.c_void_p,
        ctypes.c_int,
        ctypes.wintypes.WPARAM,
        ctypes.wintypes.LPARAM,
    )
    user32.CallNextHookEx.restype = LRESULT
    user32.GetMessageW.argtypes = (
        ctypes.POINTER(ctypes.wintypes.MSG),
        ctypes.wintypes.HWND,
        ctypes.wintypes.UINT,
        ctypes.wintypes.UINT,
    )
    user32.GetMessageW.restype = ctypes.wintypes.BOOL
    user32.TranslateMessage.argtypes = (ctypes.POINTER(ctypes.wintypes.MSG),)
    user32.TranslateMessage.restype = ctypes.wintypes.BOOL
    user32.DispatchMessageW.argtypes = (ctypes.POINTER(ctypes.wintypes.MSG),)
    user32.DispatchMessageW.restype = LRESULT


def _tokenize_hotkey(text: str) -> list[str]:
    text = str(text or "").strip()
    if not text:
        return []
    text = text.replace("^", "CTRL+").replace("!", "ALT+").replace("+", "+")
    text = text.replace("#", "WIN+")
    return [part.strip().upper() for part in re.split(r"\s*\+\s*", text) if part.strip()]


def _vk_for_character(token: str) -> int | None:
    if len(token) != 1:
        return None
    char = token.upper()
    if "A" <= char <= "Z" or "0" <= char <= "9":
        return ord(char)
    if os.name == "nt":
        try:
            result = ctypes.windll.user32.VkKeyScanW(ord(token))
            if result != -1:
                return int(result) & 0xFF
        except Exception:
            return None
    return NAMED_KEYS.get(token)


def parse_hotkey(text: str) -> tuple[HotkeySpec | None, str]:
    tokens = _tokenize_hotkey(text)
    if not tokens:
        return None, "raccourci vide"
    keys: list[int] = []
    display_parts: list[str] = []
    for token in tokens:
        if token in MODIFIER_ALIASES:
            vk, display = MODIFIER_ALIASES[token]
        elif token in NAMED_KEYS:
            vk, display = NAMED_KEYS[token], token
        else:
            vk = _vk_for_character(token)
            display = token
        if vk is None:
            return None, f"raccourci invalide ou non supporte: {text}"
        if vk not in keys:
            keys.append(vk)
        if display not in display_parts:
            display_parts.append(display)
    ordered = [part for part in MODIFIER_ORDER if part in display_parts]
    ordered.extend(part for part in display_parts if part not in ordered)
    canonical = "+".join(ordered)
    return HotkeySpec(text=text, keys=frozenset(keys), canonical=canonical), ""


def build_hotkey_actions(settings: AtlasSettings) -> list[HotkeyAction]:
    actions: list[HotkeyAction] = []
    if settings.switch_click_enabled or settings.switch_click_hotkey:
        actions.append(
            HotkeyAction(
                action_id="switch_click",
                label="Switch clique",
                hotkey_text=settings.switch_click_hotkey,
                kind="switch",
                payload={"click_count": 1, "label": "Switch clique"},
                enabled=settings.switch_click_enabled,
            )
        )
    if settings.switch_double_click_enabled or settings.switch_double_click_hotkey:
        actions.append(
            HotkeyAction(
                action_id="switch_double_click",
                label="Switch clic x2",
                hotkey_text=settings.switch_double_click_hotkey,
                kind="switch",
                payload={"click_count": 2, "label": "Switch clic x2"},
                enabled=settings.switch_double_click_enabled,
            )
        )
    # Stop urgence is optional. An empty optional binding is absence of an action,
    # not a registry error and must never poison the runtime readiness report.
    if settings.stop_hotkey:
        actions.append(
            HotkeyAction(
                action_id="stop_script",
                label="Stop urgence",
                hotkey_text=settings.stop_hotkey,
                kind="press",
            )
        )

    if settings.switch_character_enabled:
        for client in settings.clients:
            if not client.binding:
                continue
            actions.append(
                HotkeyAction(
                    action_id=f"client:{client.index}",
                    label=f"Personnage {client.index}",
                    hotkey_text=client.binding,
                    kind="press",
                    payload={"client_index": client.index, "handle": client.handle},
                )
            )

    if settings.movement_enabled:
        for key_name in ("HOME", "DELETE", "END", "PAGEDOWN"):
            actions.append(
                HotkeyAction(
                    action_id=f"direction:{key_name}",
                    label=f"Direction {key_name}",
                    hotkey_text=key_name,
                    kind="press",
                    payload={"key_name": key_name},
                )
            )
    return actions


class HotkeyRegistry:
    def __init__(self, input_state: InputState, logger: Logger, callback: HotkeyCallback):
        self.input_state = input_state
        self.logger = logger
        self.callback = callback
        self._actions: tuple[HotkeyAction, ...] = ()
        self._switch_actions: tuple[HotkeyAction, ...] = ()
        self._stop_actions: tuple[HotkeyAction, ...] = ()
        self._hook = None
        self._callback_ref = None
        self._thread: threading.Thread | None = None
        self._hook_thread_id = 0
        self._stop_event = threading.Event()
        self._startup_event = threading.Event()
        self._start_ok = False
        self._suppressed_until_release: set[str] = set()

    def register_hotkeys(self, actions: list[HotkeyAction]) -> HotkeyReport:
        parsed: list[HotkeyAction] = []
        errors: list[str] = []
        owner_by_key: dict[str, HotkeyAction] = {}
        for action in actions:
            if not action.enabled:
                if action.error:
                    errors.append(action.error)
                continue
            spec, error = parse_hotkey(action.hotkey_text)
            if error:
                errors.append(f"{action.label}: {error}")
                continue
            assert spec is not None
            existing = owner_by_key.get(spec.canonical)
            if existing is not None:
                message = f"conflit raccourci: {action.label} refuse sur {spec.canonical}, deja utilise par {existing.label}"
                errors.append(message)
                continue
            action = HotkeyAction(
                action_id=action.action_id,
                label=action.label,
                hotkey_text=action.hotkey_text,
                kind=action.kind,
                payload=action.payload,
                spec=spec,
            )
            owner_by_key[spec.canonical] = action
            parsed.append(action)
            self.logger.debug("Hotkey actif: %s action=%s", spec.canonical, action.action_id)
        self._actions = tuple(parsed)
        self._switch_actions = tuple(action for action in parsed if action.kind == "switch")
        self._stop_actions = tuple(action for action in parsed if action.action_id == "stop_script")
        self._suppressed_until_release.clear()
        self.input_state.reset_armed()
        return HotkeyReport(actions=self._actions, errors=tuple(errors))

    def switch_action_for_pressed_keys(self) -> HotkeyAction | None:
        # Plusieurs raccourcis peuvent correspondre aux touches maintenues.
        # Exemple : CTRL correspond aussi lorsque CTRL+SHIFT est enfonce.
        # On choisit donc toujours la combinaison la plus precise.
        matches = [
            action
            for action in self._switch_actions
            if action.spec and self._spec_physically_pressed(action.spec)
        ]
        if not matches:
            return None
        return max(
            matches,
            key=lambda action: len(action.spec.keys) if action.spec else 0,
        )

    def armed_switch_action(self) -> HotkeyAction | None:
        return self.switch_action_for_pressed_keys()

    def _spec_physically_pressed(self, spec: HotkeySpec) -> bool:
        if os.name == "nt":
            try:
                user32 = ctypes.windll.user32
                if not all(
                    bool(user32.GetAsyncKeyState(int(vk)) & 0x8000)
                    for vk in spec.keys
                ):
                    return False

                # Même règle pour les macros maintenues : F11 ne doit pas
                # devenir ALT+F11 lorsqu'ALT est encore enfoncé.
                for modifier_vk in MODIFIER_VKS:
                    modifier_pressed = bool(
                        user32.GetAsyncKeyState(int(modifier_vk)) & 0x8000
                    )
                    if modifier_pressed != (modifier_vk in spec.keys):
                        return False
                return True
            except Exception:
                pass
        return spec.matches(self.input_state.snapshot())

    def start(self) -> bool:
        if os.name != "nt":
            self.logger.warning("Hooks clavier indisponibles hors Windows.")
            return False
        if self._thread is not None:
            if self._thread.is_alive():
                return self._start_ok
            self._thread = None
            self._hook = None
            self._start_ok = False
        self._stop_event.clear()
        self._startup_event.clear()
        self._start_ok = False
        self._thread = threading.Thread(target=self._run_hook, name="DofusAtlasKeyboardHook", daemon=True)
        self._thread.start()
        self._startup_event.wait(HOOK_START_TIMEOUT_SECONDS)
        return self._start_ok

    def stop(self) -> None:
        stop_message_hook(self)

    def _run_hook(self) -> None:
        self._hook_thread_id = current_native_thread_id(self.logger)
        try:
            self._callback_ref = LowLevelKeyboardProc(self._keyboard_proc)
            user32 = ctypes.windll.user32
            kernel32 = ctypes.windll.kernel32
            _configure_hook_api(user32, kernel32)
            module_handle = kernel32.GetModuleHandleW(None)
            self._hook = user32.SetWindowsHookExW(WH_KEYBOARD_LL, self._callback_ref, module_handle, 0)
            if not self._hook:
                error_code = int(kernel32.GetLastError())
                self.logger.error(
                    "Hooks clavier Python impossibles: error=%s module_handle=%s. Relancer Dofus Atlas avec les memes droits que Dofus.",
                    error_code,
                    module_handle,
                )
                self._start_ok = False
                self._startup_event.set()
                return
            self._start_ok = True
            self._startup_event.set()
            self.logger.info("Hook clavier Python actif.")
            msg = ctypes.wintypes.MSG()
            while not self._stop_event.is_set() and user32.GetMessageW(ctypes.byref(msg), None, 0, 0) != 0:
                user32.TranslateMessage(ctypes.byref(msg))
                user32.DispatchMessageW(ctypes.byref(msg))
        finally:
            self._hook_thread_id = 0

    def _keyboard_proc(self, n_code: int, w_param: int, l_param: int) -> int:
        try:
            if n_code >= 0:
                event = ctypes.cast(ctypes.c_void_p(l_param), ctypes.POINTER(KBDLLHOOKSTRUCT)).contents
                if event.flags & LLKHF_INJECTED:
                    return ctypes.windll.user32.CallNextHookEx(self._hook, n_code, w_param, l_param)
                pressed = w_param in (WM_KEYDOWN, WM_SYSKEYDOWN)
                released = w_param in (WM_KEYUP, WM_SYSKEYUP)
                if pressed or released:
                    vk_code = LEFT_RIGHT_MODIFIERS.get(int(event.vkCode), int(event.vkCode))
                    self.input_state.set_key(vk_code, pressed)
                    if self._dispatch_priority_stop(vk_code, pressed):
                        return 1
                    self._dispatch_matching_hotkeys()
        except Exception:
            self.logger.exception("Hook clavier: erreur callback.")
        return ctypes.windll.user32.CallNextHookEx(self._hook, n_code, w_param, l_param)

    def _dispatch_priority_stop(self, vk_code: int, pressed: bool) -> bool:
        if not self._stop_actions:
            return False
        pressed_keys = self.input_state.snapshot()
        consumed = False
        for action in self._stop_actions:
            spec = action.spec
            if spec is None:
                continue
            if not pressed:
                if int(vk_code) in spec.keys or not spec.matches(pressed_keys):
                    self._suppressed_until_release.discard(action.action_id)
                continue
            if not spec.matches(pressed_keys):
                continue
            consumed = True
            if action.action_id in self._suppressed_until_release:
                continue
            self.logger.warning("Stop urgence prioritaire: %s", spec.canonical)
            self.callback(action.action_id, action.payload)
            self._suppressed_until_release.add(action.action_id)
        return consumed

    def _dispatch_matching_hotkeys(self) -> None:
        pressed = self.input_state.snapshot()
        for action in self._actions:
            if action.spec is None:
                continue
            active = action.spec.matches(pressed)
            if action.kind == "switch":
                continue
            changed_to_active = self.input_state.mark_hotkey_active(action.action_id, active)
            if not active:
                self._suppressed_until_release.discard(action.action_id)
                continue
            if active and action.action_id in self._suppressed_until_release:
                continue
            if active and changed_to_active:
                self.callback(action.action_id, action.payload)
                self._suppressed_until_release.add(action.action_id)
