from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from app.network.character_resolver import CharacterSlotResolver
from app.network.character_runtime_state import CharacterRuntimeStateStore
from app.network.events import CharacterIdentifiedEvent, QuestStartedEvent
from app.network.known_session_recovery import (
    KnownSessionProgressBridge,
    KnownSessionProtocolMessageDecoder,
    VerifiedKnownSessionRecovery,
)
from app.network.progress_bridge import EventApplicationResult
from app.network.transport import CapturedProtocolMessage


class _DecoderDelegate:
    def __init__(self) -> None:
        self.messages: list[object] = []

    def decode(self, message):
        self.messages.append(message)
        return None


class _BridgeDelegate:
    def __init__(self) -> None:
        self.routes: dict[str, str] = {}
        self.events: list[object] = []

    def session_character_key(self, session_id: str) -> str:
        return self.routes.get(session_id, "")

    def handle(self, event):
        self.events.append(event)
        if isinstance(event, CharacterIdentifiedEvent):
            key = f"character:{int(event.character_id or 0)}"
            self.routes[event.session_id] = key
            return EventApplicationResult(True, True, "character_identified", key)
        return EventApplicationResult(
            True,
            False,
            "handled",
            self.routes.get(event.session_id, ""),
        )

    def reset_sessions(self) -> None:
        self.routes.clear()


class KnownSessionRecoveryTests(unittest.TestCase):
    def _paths(self, root: Path) -> tuple[Path, Path, Path]:
        return (
            root / "profiles.json",
            root / "client_index.json",
            root / "network_character_bindings.json",
        )

    def _resolver(self, root: Path) -> CharacterSlotResolver:
        profile, client_index, bindings = self._paths(root)
        return CharacterSlotResolver(
            profile_path=profile,
            client_index_path=client_index,
            binding_path=bindings,
            progress_paths=(),
        )

    @staticmethod
    def _client(pid: int, slot: int, name: str) -> dict:
        # Mirrors Organizer export: the visible label is generic, while the
        # cleaned character name is carried separately.
        return {
            "pid": pid,
            "index": slot,
            "slot": slot,
            "label": f"Personnage {slot}",
            "character_name": name,
        }

    @staticmethod
    def _write_clients(path: Path, clients: list[dict]) -> None:
        path.write_text(json.dumps({"clients": clients}), encoding="utf-8")

    @staticmethod
    def _write_bindings(path: Path, characters: dict[str, dict]) -> None:
        path.write_text(
            json.dumps({"characters": characters, "legacy_slots": {}}),
            encoding="utf-8",
        )

    def test_recovers_same_already_open_process_from_verified_pid_binding(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            _profile, client_index, bindings = self._paths(root)
            self._write_clients(client_index, [self._client(1234, 1, "Alpha")])
            self._write_bindings(
                bindings,
                {
                    "42": {
                        "name": "Alpha",
                        "pid": 1234,
                        "organizer_slot": 1,
                        "source": "verified_network_identity",
                    }
                },
            )

            recovery = VerifiedKnownSessionRecovery(self._resolver(root))
            resolution = recovery.resolve("tcp:1234:1")
            self.assertIsNotNone(resolution)
            self.assertEqual(resolution.character_key, "character:42")
            self.assertEqual(resolution.label, "Alpha")
            self.assertEqual(resolution.slot, 1)

    def test_generic_title_and_recycled_pid_cannot_prove_selected_character(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            _profile, client_index, bindings = self._paths(root)
            self._write_clients(
                client_index,
                [
                    {
                        "pid": 1234,
                        "index": 1,
                        "slot": 1,
                        "label": "Personnage 1",
                        "character_name": "Dofus Release 3 6 10 10",
                    }
                ],
            )
            self._write_bindings(
                bindings,
                {
                    "42": {
                        "name": "Alpha",
                        "pid": 1234,
                        "organizer_slot": 1,
                        "source": "verified_network_identity",
                    }
                },
            )

            resolution = VerifiedKnownSessionRecovery(self._resolver(root)).resolve("tcp:1234:1")
            self.assertIsNone(resolution)

    def test_never_recovers_from_unverified_or_slot_only_rows(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            _profile, client_index, bindings = self._paths(root)
            self._write_clients(client_index, [self._client(1234, 1, "Alpha")])
            self._write_bindings(
                bindings,
                {
                    "42": {
                        "name": "Alpha",
                        "pid": 1234,
                        "organizer_slot": 1,
                        "source": "organizer_slot",
                    }
                },
            )
            self.assertIsNone(
                VerifiedKnownSessionRecovery(self._resolver(root)).resolve("tcp:1234:1")
            )

    def test_current_client_name_blocks_stale_pid_reuse(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            _profile, client_index, bindings = self._paths(root)
            self._write_clients(client_index, [self._client(1234, 1, "Beta")])
            self._write_bindings(
                bindings,
                {
                    "42": {
                        "name": "Alpha",
                        "pid": 1234,
                        "organizer_slot": 1,
                        "source": "verified_network_identity",
                    }
                },
            )
            self.assertIsNone(
                VerifiedKnownSessionRecovery(self._resolver(root)).resolve("tcp:1234:1")
            )

    def test_verified_unique_name_can_recover_after_pid_changes(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            _profile, client_index, bindings = self._paths(root)
            self._write_clients(client_index, [self._client(9876, 2, "Alpha")])
            self._write_bindings(
                bindings,
                {
                    "42": {
                        "name": "Alpha",
                        "pid": 1234,
                        "organizer_slot": 2,
                        "source": "verified_network_identity",
                    }
                },
            )
            resolution = VerifiedKnownSessionRecovery(self._resolver(root)).resolve("tcp:9876:4")
            self.assertIsNotNone(resolution)
            self.assertEqual(resolution.character_key, "character:42")

    def test_protocol_wrapper_seeds_runtime_state_before_later_profile_packet(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            _profile, client_index, bindings = self._paths(root)
            self._write_clients(client_index, [self._client(1234, 1, "Alpha")])
            self._write_bindings(
                bindings,
                {
                    "42": {
                        "name": "Alpha",
                        "pid": 1234,
                        "organizer_slot": 1,
                        "source": "verified_network_identity",
                    }
                },
            )
            state = CharacterRuntimeStateStore()
            wrapper = KnownSessionProtocolMessageDecoder(
                _DecoderDelegate(),
                VerifiedKnownSessionRecovery(self._resolver(root)),
                state=state,
            )
            wrapper.decode(
                CapturedProtocolMessage(
                    session_id="tcp:1234:1",
                    type_url="type.ankama.com/anything",
                    payload=b"",
                    direction="server_to_client",
                )
            )
            snapshot = state.snapshot_for_session("tcp:1234:1")
            self.assertIsNotNone(snapshot)
            self.assertEqual(snapshot.character_key, "character:42")

    def test_protocol_wrapper_does_not_recover_old_binding_on_fresh_identity_packets(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            _profile, client_index, bindings = self._paths(root)
            self._write_clients(client_index, [self._client(1234, 1, "Alpha")])
            self._write_bindings(
                bindings,
                {
                    "42": {
                        "name": "Alpha",
                        "pid": 1234,
                        "organizer_slot": 1,
                        "source": "verified_network_identity",
                    }
                },
            )
            state = CharacterRuntimeStateStore()
            wrapper = KnownSessionProtocolMessageDecoder(
                _DecoderDelegate(),
                VerifiedKnownSessionRecovery(self._resolver(root)),
                state=state,
            )
            for type_url in ("type.ankama.com/kvi", "type.ankama.com/kva"):
                wrapper.decode(
                    CapturedProtocolMessage(
                        session_id="tcp:1234:1",
                        type_url=type_url,
                        payload=b"",
                        direction="server_to_client",
                    )
                )
            self.assertIsNone(state.snapshot_for_session("tcp:1234:1"))

    def test_progress_wrapper_reinjects_identity_through_existing_bridge_contract(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            _profile, client_index, bindings = self._paths(root)
            self._write_clients(client_index, [self._client(1234, 1, "Alpha")])
            self._write_bindings(
                bindings,
                {
                    "42": {
                        "name": "Alpha",
                        "pid": 1234,
                        "organizer_slot": 1,
                        "source": "verified_network_identity",
                    }
                },
            )
            delegate = _BridgeDelegate()
            wrapper = KnownSessionProgressBridge(
                delegate,
                VerifiedKnownSessionRecovery(self._resolver(root)),
            )
            result = wrapper.handle(
                QuestStartedEvent(
                    session_id="tcp:1234:1",
                    event_id="quest-started",
                    reliable=True,
                    quest_id=100,
                )
            )
            self.assertEqual(delegate.session_character_key("tcp:1234:1"), "character:42")
            self.assertIsInstance(delegate.events[0], CharacterIdentifiedEvent)
            self.assertIsInstance(delegate.events[1], QuestStartedEvent)
            self.assertEqual(result.character_key, "character:42")


if __name__ == "__main__":
    unittest.main()
