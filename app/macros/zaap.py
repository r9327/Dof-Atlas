from __future__ import annotations

from typing import TYPE_CHECKING

from app.macros.input_tools import clipboard_text, press_hotkey, press_key
from app.storage import read_zaap_button_ratios
from app.windows.clicks import send_client_click
from app.windows.focus import activate_window
from app.windows.unity_windows import client_point_from_ratio, client_to_screen, is_unity_window

if TYPE_CHECKING:
    from app.core.runtime_state import AtlasRuntime


class ZaapMacro:
    def __init__(self, runtime: "AtlasRuntime"):
        self.runtime = runtime

    def run_async(self, text: str, click_position=None, click_ratios=None) -> bool:
        search = str(text or "").replace("\r", " ").replace("\n", " ").strip()
        return self.runtime._spawn_macro(
            "Auto zaap",
            lambda: self._run(search, click_position=click_position, click_ratios=click_ratios),
        )

    def _run(self, text: str, click_position=None, click_ratios=None) -> None:
        if not text:
            self.runtime.logger.info("Auto zaap ignore: texte vide.")
            return
        clients = self.runtime.switch_character.ordered_clients_from_source()
        if not clients:
            self.runtime.logger.info("Auto zaap ignore: aucune fenetre chargee.")
            return
        zaap_timings = self.runtime.settings.zaap_timings
        click_x, click_y = click_position or self.runtime.settings.zaap_click_position
        json_ratios = read_zaap_button_ratios()
        ratios = json_ratios or click_ratios or self.runtime.settings.zaap_click_ratios
        ratio_source = "json" if json_ratios else "callback" if click_ratios else "settings" if ratios else "none"
        self.runtime.logger.info(
            "Auto zaap lance: clients=%s zaap=%s click=%s,%s ratio=%s source=%s",
            len(clients),
            text,
            click_x,
            click_y,
            ratios,
            ratio_source,
        )
        self.runtime.logger.debug(
            "Auto zaap timings: focus=%s open=%s click_settle=%s submit=%s reliable=%s/%s",
            zaap_timings.focus_settle_ms,
            zaap_timings.open_wait_ms,
            zaap_timings.click_settle_ms,
            zaap_timings.submit_settle_ms,
            zaap_timings.reliable_click_pre_ms,
            zaap_timings.reliable_click_post_ms,
        )
        sent = 0
        for client in clients:
            if self.runtime.macro_lock.should_stop():
                return
            if not is_unity_window(client.handle):
                self.runtime.logger.info("Auto zaap fenetre introuvable/non Unity: hwnd=%s", client.handle)
                continue
            if not activate_window(
                client.handle,
                zaap_timings.focus_settle_ms,
                zaap_timings.activate_attempts,
                zaap_timings.activate_retry_ms,
                self.runtime.logger,
                "Auto zaap",
                should_stop=self.runtime.macro_lock.should_stop,
            ):
                self.runtime.logger.info("Auto zaap activation echec: hwnd=%s", client.handle)
                continue
            press_key("H")
            if self.runtime.macro_lock.wait(zaap_timings.open_wait_ms):
                return
            if not activate_window(
                client.handle,
                zaap_timings.focus_settle_ms,
                zaap_timings.activate_attempts,
                zaap_timings.activate_retry_ms,
                self.runtime.logger,
                "Auto zaap apres ouverture",
                should_stop=self.runtime.macro_lock.should_stop,
            ):
                self.runtime.logger.info("Auto zaap click ignore: fenetre plus prete hwnd=%s", client.handle)
                continue
            target = None
            target_mode = "fallback_position"
            if ratios is not None:
                target = client_point_from_ratio(client.handle, ratios[0], ratios[1])
                if target is not None:
                    target_mode = "json_ratio" if ratio_source == "json" else "ratio"
            if target is None:
                target = (int(click_x), int(click_y))
            screen_target = client_to_screen(client.handle, target[0], target[1])
            self.runtime.logger.debug(
                "Auto zaap cible: label=%s hwnd=%s mode=%s client=%s,%s screen=%s ratio=%s",
                client.display_name,
                client.handle,
                target_mode,
                target[0],
                target[1],
                screen_target,
                ratios,
            )
            send_client_click(
                client.handle,
                target[0],
                target[1],
                "Left",
                1,
                zaap_timings.input_click_down_ms,
                zaap_timings.input_double_gap_ms,
                zaap_timings.reliable_click_pre_ms,
                zaap_timings.reliable_click_post_ms,
                self.runtime.synthetic_guard,
                self.runtime.logger,
                should_stop=self.runtime.macro_lock.should_stop,
            )
            if self.runtime.macro_lock.wait(zaap_timings.click_settle_ms):
                return
            if not activate_window(
                client.handle,
                zaap_timings.focus_settle_ms,
                zaap_timings.activate_attempts,
                zaap_timings.activate_retry_ms,
                self.runtime.logger,
                "Auto zaap avant saisie",
                should_stop=self.runtime.macro_lock.should_stop,
            ):
                self.runtime.logger.info("Auto zaap saisie ignore: fenetre plus prete hwnd=%s", client.handle)
                continue
            with clipboard_text(text, self.runtime.logger):
                if self.runtime.macro_lock.should_stop():
                    return
                press_hotkey("CTRL", "A")
                if self.runtime.macro_lock.should_stop():
                    return
                press_key("DELETE")
                if self.runtime.macro_lock.should_stop():
                    return
                press_hotkey("CTRL", "V")
                if self.runtime.macro_lock.should_stop():
                    return
                self.runtime.logger.debug(
                    "Auto zaap saisie collee: text=%s submit_wait_ms=%s",
                    text,
                    zaap_timings.submit_settle_ms,
                )
                if self.runtime.macro_lock.wait(zaap_timings.submit_settle_ms):
                    return
                press_key("ENTER")
            if self.runtime.macro_lock.wait(zaap_timings.submit_settle_ms):
                return
            sent += 1
        self.runtime.switch_character.restore_preferred_client("Auto zaap")
        self.runtime.logger.info("Auto zaap termine: envoyes=%s/%s", sent, len(clients))
