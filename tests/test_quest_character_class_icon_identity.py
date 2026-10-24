"""Only verified identity metadata can expose a Dofus class portrait."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from app.quest_catalog import load_quest_characters


class QuestCharacterClassIdentityTests(unittest.TestCase):
    def test_unverified_rows_never_claim_a_class_icon(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            profile = root / "profile.json"
            clients = root / "clients.json"
            bindings = root / "bindings.json"
            profile.write_text("{}", encoding="utf-8")
            clients.write_text('{"clients":[]}', encoding="utf-8")
            bindings.write_text(json.dumps({"characters": {
                "1": {"name": "Alpha", "class_key": "feca",
                      "source": "verified_network_identity"},
                "2": {"name": "Beta", "class_key": "cra",
                      "source": "unverified_candidate"},
            }}), encoding="utf-8")
            rows = load_quest_characters(
                profile, clients, binding_path=bindings
            )
            by_key = {row.key: row for row in rows}
            self.assertEqual(by_key["character:1"].class_key, "feca")
            self.assertEqual(by_key["character:2"].class_key, "")

    def test_untrusted_class_paths_are_not_exposed_as_icons(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            profile = root / "profile.json"
            clients = root / "clients.json"
            bindings = root / "bindings.json"
            profile.write_text("{}", encoding="utf-8")
            clients.write_text('{"clients":[]}', encoding="utf-8")
            bindings.write_text(json.dumps({"characters": {
                "1": {"name": "Alpha", "class_key": "../outside",
                      "source": "verified_network_identity"},
                "2": {"name": "Beta", "class_key": "feca.png",
                      "source": "verified_network_identity"},
            }}), encoding="utf-8")
            rows = load_quest_characters(
                profile, clients, binding_path=bindings
            )
            self.assertEqual({r.class_key for r in rows}, {""})


    def test_guide_portrait_does_not_infer_class_from_character_name(self):
        from app.modules.encyclopedia.views.shared_manual_guide_view import SharedGuideManualView
        from app.pages.organizer import common
        from app.quest_catalog import QuestCharacter

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "feca.png").write_bytes(b"icon")
            with patch.object(common, "CLASS_ICON_DIRS", (root,)):
                unverified = QuestCharacter(
                    "character:42", "Alice - Feca", 1, False, class_key=""
                )
                self.assertEqual(
                    SharedGuideManualView._participant_icon(None, unverified),
                    ("", ""),
                )
                verified = QuestCharacter(
                    "character:42", "Alice", 1, False, class_key="feca"
                )
                self.assertEqual(
                    SharedGuideManualView._participant_icon(None, verified),
                    (str(root / "feca.png"), "Feca"),
                )
                unsafe = QuestCharacter(
                    "character:43", "Alice", 1, False, class_key="../outside"
                )
                self.assertEqual(
                    SharedGuideManualView._participant_icon(None, unsafe),
                    ("", ""),
                )


    def test_modern_client_index_cannot_claim_another_verified_character(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            profile = root / "profile.json"
            clients = root / "clients.json"
            bindings = root / "bindings.json"
            profile.write_text("{}", encoding="utf-8")
            bindings.write_text(
                json.dumps({"characters": {
                    "1": {"name": "Alpha", "class_key": "feca",
                          "source": "verified_network_identity"},
                    "2": {"name": "Beta", "class_key": "cra",
                          "source": "verified_network_identity"},
                }}), encoding="utf-8",
            )
            entry = {"character_name": "Alpha", "pid": 55, "slot": 1,
                     "class_key": "feca", "character_key": "character:1"}

            def connected():
                clients.write_text(
                    json.dumps({"clients": [entry]}), encoding="utf-8"
                )
                return load_quest_characters(
                    profile, clients, binding_path=bindings, connected_only=True
                )

            self.assertEqual([row.key for row in connected()], ["character:1"])
            entry["character_key"] = "character:2"
            self.assertEqual(connected(), [])
            entry["character_key"] = ""
            self.assertEqual(connected(), [])
            entry["character_key"] = "character:1"
            entry["class_key"] = "cra"
            self.assertEqual(connected(), [])
            entry["class_key"] = "feca"
            entry["character_name"] = "Beta"
            self.assertEqual(connected(), [])
            entry["character_name"] = "Alpha"
            self.assertEqual([row.key for row in connected()], ["character:1"])



    def test_shell_does_not_treat_matching_window_name_as_network_connection(self):
        from main import AtlasWindow
        from app.quest_catalog import QuestCharacter

        shell = SimpleNamespace(_ordered_characters=lambda rows: list(rows))
        offline = QuestCharacter("character:5", "Alice", 0, False, class_key="feca")
        online = QuestCharacter("character:6", "Bob", 1, True, class_key="cra")
        runtime = SimpleNamespace(snapshot=lambda _key: None)
        with patch(
            "app.network.character_runtime_state.character_runtime_state",
            return_value=runtime,
        ):
            connected = AtlasWindow._connected_characters(shell, [offline, online])
        self.assertEqual([row.key for row in connected], ["character:6"])
        self.assertFalse(offline.connected)

    def test_shell_portraits_require_verified_class_even_when_name_has_class(self):
        from main import AtlasWindow
        from app.pages.organizer import common

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            icon = root / "feca.png"
            icon.write_bytes(b"icon")
            with (
                patch.object(common, "CLASS_ICON_DIRS", (root,)),
                patch("main.LOGO_PATH", root / "missing-logo.png"),
            ):
                self.assertEqual(
                    AtlasWindow.character_icon_path(None, "Alice - Feca"), ""
                )
                self.assertEqual(
                    AtlasWindow.character_icon_path(
                        None, "Alice", class_key="feca"
                    ),
                    str(icon),
                )
                self.assertEqual(
                    AtlasWindow.character_icon_path(
                        None, "Alice", class_key="../unsafe"
                    ),
                    "",
                )



if __name__ == "__main__":
    unittest.main()
