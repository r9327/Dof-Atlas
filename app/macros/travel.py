from __future__ import annotations

import re
from typing import TYPE_CHECKING

from app.macros.input_tools import send_chat_command
from app.windows.focus import activate_window
from app.windows.unity_windows import is_unity_window

if TYPE_CHECKING:
    from app.core.runtime_state import AtlasRuntime
    from app.core.settings import AtlasClient


_TRAVEL_RE = re.compile(r"^/travel\s+(-?\d+)\s*,\s*(-?\d+)$", re.IGNORECASE)
_GUIDE_SEQUENCE_RE = re.compile(
    r"^/zaap\s+(-?\d+)\s*,\s*(-?\d+)\s*;\s*/travel\s+(-?\d+)\s*,\s*(-?\d+)$",
    re.IGNORECASE,
)


def normalize_guide_travel_command(value: str) -> str | None:
    text = str(value or "").replace("\r", " ").replace("\n", " ").strip()
    match = _TRAVEL_RE.fullmatch(text)
    if match is not None:
        return f"/travel {int(match.group(1))},{int(match.group(2))}"
    match = _GUIDE_SEQUENCE_RE.fullmatch(text)
    if match is None:
        return None
    return (
        f"/zaap {int(match.group(1))},{int(match.group(2))} ; "
        f"/travel {int(match.group(3))},{int(match.group(4))}"
    )


class TravelMacro:
    def __init__(self, runtime: "AtlasRuntime"):
        self.runtime = runtime

    def run_async(self, text: str, character_keys=None) -> bool:
        command = str(text or "").strip()
        targets = None if character_keys is None else tuple(
            dict.fromkeys(str(key or "").strip() for key in character_keys if str(key or "").strip())
        )
        return self.runtime._spawn_macro("Travel", lambda: self._run(command, targets))

    def _targeted_clients(
        self,
        character_keys: tuple[str, ...],
    ) -> tuple[list["AtlasClient"], int] | None:
        if not character_keys:
            self.runtime.logger.info("Travel guide ignore: aucun participant selectionne.")
            self.runtime._emit_status("Déplacement ignoré : aucun participant sélectionné.")
            return None
        if any(not re.fullmatch(r"character:[1-9]\d*", key) for key in character_keys):
            self.runtime.logger.warning("Travel guide ignore: identite participant invalide.")
            self.runtime._emit_status("Déplacement ignoré : identité de participant invalide.")
            return None
        buckets: dict[str, list["AtlasClient"]] = {key: [] for key in character_keys}
        for client in self.runtime.settings.clients:
            if client.character_key in buckets:
                buckets[client.character_key].append(client)
        if any(len(rows) > 1 for rows in buckets.values()):
            self.runtime.logger.warning("Travel guide ignore: identite ambigue dans les fenetres Unity.")
            self.runtime._emit_status("Déplacement ignoré : identité de participant ambiguë.")
            return None
        clients = [buckets[key][0] for key in character_keys if len(buckets[key]) == 1]
        offline = sum(1 for key in character_keys if not buckets[key])
        if not clients:
            self.runtime.logger.info("Travel guide ignore: tous les participants sont hors ligne.")
            self.runtime._emit_status("Déplacement ignoré : tous les participants sont hors ligne.")
            return None
        return clients, offline

    def _run(self, command: str, character_keys: tuple[str, ...] | None = None) -> None:
        command = normalize_guide_travel_command(command)
        if command is None:
            self.runtime.logger.info("Travel ignore: commande invalide.")
            if character_keys is not None:
                self.runtime._emit_status("Déplacement ignoré : commande invalide.")
            return
        offline = 0
        if character_keys is None:
            clients = self.runtime.switch_character.ordered_clients_from_source()
        else:
            targeted = self._targeted_clients(character_keys)
            if targeted is None:
                return
            clients, offline = targeted
        if not clients:
            self.runtime.logger.info("Travel ignore: aucune fenetre chargee.")
            return
        timings = self.runtime.settings.timings
        sent = 0
        for client in clients:
            if self.runtime.macro_lock.should_stop():
                return
            if not is_unity_window(client.handle):
                self.runtime.logger.info("Travel fenetre introuvable/non Unity: hwnd=%s", client.handle)
                continue
            if activate_window(
                client.handle,
                timings.travel_focus_settle_ms,
                timings.activate_attempts,
                timings.activate_retry_ms,
                self.runtime.logger,
                "Travel",
                should_stop=self.runtime.macro_lock.should_stop,
            ):
                if not send_chat_command(
                    command,
                    self.runtime.logger,
                    submit_twice=True,
                    chat_open_ms=timings.auto_group_chat_open_ms,
                    key_step_ms=timings.auto_group_key_step_ms,
                    paste_settle_ms=timings.auto_group_paste_settle_ms,
                    should_stop=self.runtime.macro_lock.should_stop,
                ):
                    if self.runtime.macro_lock.should_stop():
                        return
                    continue
                sent += 1
        self.runtime.switch_character.restore_preferred_client("Travel")
        self.runtime.logger.info("Travel termine: envoyes=%s/%s", sent, len(clients))
        if character_keys is not None:
            suffix = f", {offline} hors ligne" if offline else ""
            self.runtime._emit_status(f"Déplacement envoyé à {sent} participant(s){suffix}.")
