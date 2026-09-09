from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from app.constants import KEY_SESSION_ORDER
from app.network.character_resolver import CharacterSlotResolver
from app.services.character_order_service import CharacterOrderService


class CharacterIdentityInvariantTests(unittest.TestCase):
    @staticmethod
    def _write_json(path: Path, payload: object) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def _build_state(self, root: Path) -> dict[str, Path]:
        paths = {
            "profile": root / "client_profiles.json",
            "clients": root / "client_index.json",
            "bindings": root / "network_character_bindings.json",
            "quests": root / "quest_progress.json",
            "achievements": root / "achievement_progress.json",
            "guides": root / "guide_progress.json",
        }
        self._write_json(
            paths["profile"],
            {KEY_SESSION_ORDER: ["alpha", "beta", "gamma"]},
        )
        self._write_json(
            paths["clients"],
            {
                "clients": [
                    {"character_name": "Alpha", "pid": 1011, "slot": 1},
                    {"character_name": "Beta", "pid": 2022, "slot": 2},
                    {"character_name": "Gamma", "pid": 3033, "slot": 3},
                ]
            },
        )
        self._write_json(
            paths["bindings"],
            {
                "characters": {
                    "101": {
                        "name": "Alpha",
                        "pid": 1011,
                        "organizer_slot": 1,
                        "source": "verified_network_identity",
                    },
                    "202": {
                        "name": "Beta",
                        "pid": 2022,
                        "organizer_slot": 2,
                        "source": "verified_network_identity",
                    },
                    "303": {
                        "name": "Gamma",
                        "pid": 3033,
                        "organizer_slot": 3,
                        "source": "verified_network_identity",
                    },
                },
                "legacy_slots": {},
            },
        )
        for name, field in (
            ("quests", "done"),
            ("achievements", "completed"),
            ("guides", "manual"),
        ):
            self._write_json(
                paths[name],
                {
                    "version": 1,
                    "characters": {
                        "character:101": {field: {"alpha": True}},
                        "character:202": {field: {"beta": True}},
                        "character:303": {field: {"gamma": True}},
                    },
                },
            )
        return paths

    @staticmethod
    def _progress_snapshot(paths: dict[str, Path]) -> dict[str, object]:
        return {
            name: json.loads(paths[name].read_text(encoding="utf-8"))
            for name in ("quests", "achievements", "guides")
        }

    @staticmethod
    def _resolver(paths: dict[str, Path]) -> CharacterSlotResolver:
        return CharacterSlotResolver(
            profile_path=paths["profile"],
            client_index_path=paths["clients"],
            binding_path=paths["bindings"],
            progress_paths=(
                paths["quests"],
                paths["achievements"],
                paths["guides"],
            ),
        )

    def test_reorder_changes_only_logical_order_not_progress_ownership(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            paths = self._build_state(Path(temporary))
            before = self._progress_snapshot(paths)

            self.assertTrue(
                CharacterOrderService(paths["profile"]).save_labels(
                    ["Gamma", "Alpha", "Beta"]
                )
            )

            profile = json.loads(paths["profile"].read_text(encoding="utf-8"))
            self.assertEqual(profile[KEY_SESSION_ORDER], ["gamma", "alpha", "beta"])
            self.assertEqual(self._progress_snapshot(paths), before)
            for payload in before.values():
                self.assertEqual(
                    set(payload["characters"]),
                    {"character:101", "character:202", "character:303"},
                )

    def test_organizer_slot_move_does_not_change_identity_or_progress(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            paths = self._build_state(Path(temporary))
            resolver = self._resolver(paths)
            before = self._progress_snapshot(paths)

            first = resolver.resolve_for_session("Alpha", "tcp:1011:1", 101)
            self.assertIsNotNone(first)
            self.assertEqual(first.character_key, "character:101")

            clients = json.loads(paths["clients"].read_text(encoding="utf-8"))
            clients["clients"][0]["slot"] = 8
            self._write_json(paths["clients"], clients)
            second = resolver.resolve_for_session("Alpha", "tcp:1011:2", 101)

            self.assertIsNotNone(second)
            self.assertEqual(second.character_key, "character:101")
            self.assertEqual(second.slot, 8)
            self.assertEqual(self._progress_snapshot(paths), before)

    def test_reconnection_keeps_same_verified_character_key(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            paths = self._build_state(Path(temporary))
            resolver = self._resolver(paths)
            before = self._progress_snapshot(paths)

            original = resolver.resolve_for_session("Beta", "tcp:2022:1", 202)
            clients = json.loads(paths["clients"].read_text(encoding="utf-8"))
            clients["clients"][1].update({"pid": 9090, "slot": 6})
            self._write_json(paths["clients"], clients)
            reconnected = resolver.resolve_for_session("Beta", "tcp:9090:2", 202)

            self.assertIsNotNone(original)
            self.assertIsNotNone(reconnected)
            self.assertEqual(original.character_key, "character:202")
            self.assertEqual(reconnected.character_key, "character:202")
            self.assertEqual(self._progress_snapshot(paths), before)

    def test_runtime_position_change_never_becomes_business_identity(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            paths = self._build_state(Path(temporary))
            resolver = self._resolver(paths)
            before = self._progress_snapshot(paths)

            clients = json.loads(paths["clients"].read_text(encoding="utf-8"))
            clients["clients"] = [clients["clients"][2], clients["clients"][0], clients["clients"][1]]
            clients["clients"][0]["slot"] = 1
            clients["clients"][1]["slot"] = 2
            clients["clients"][2]["slot"] = 3
            self._write_json(paths["clients"], clients)

            gamma = resolver.resolve_for_session("Gamma", "tcp:3033:9", 303)
            alpha = resolver.resolve_for_session("Alpha", "tcp:1011:9", 101)

            self.assertIsNotNone(gamma)
            self.assertIsNotNone(alpha)
            self.assertEqual(gamma.character_key, "character:303")
            self.assertEqual(alpha.character_key, "character:101")
            self.assertNotEqual(gamma.character_key, "slot:1")
            self.assertNotEqual(alpha.character_key, "slot:2")
            self.assertEqual(self._progress_snapshot(paths), before)

    def test_without_verified_numeric_id_name_pid_slot_and_order_cannot_create_identity(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            paths = self._build_state(Path(temporary))
            self._write_json(
                paths["bindings"],
                {
                    "characters": {},
                    "legacy_slots": {
                        "1": {
                            "name": "Unverified",
                            "pid": 7777,
                            "organizer_slot": 1,
                        }
                    },
                },
            )
            self._write_json(
                paths["clients"],
                {"clients": [{"character_name": "Unverified", "pid": 7777, "slot": 1}]},
            )
            self._write_json(paths["profile"], {KEY_SESSION_ORDER: ["unverified"]})
            before = self._progress_snapshot(paths)

            resolution = self._resolver(paths).resolve_for_session(
                "Unverified",
                "tcp:7777:1",
                None,
            )

            self.assertIsNone(resolution)
            bindings = json.loads(paths["bindings"].read_text(encoding="utf-8"))
            self.assertEqual(bindings.get("characters"), {})
            self.assertIn("1", bindings.get("legacy_slots", {}))
            self.assertEqual(self._progress_snapshot(paths), before)

    def test_legacy_slot_progress_migrates_losslessly_and_idempotently(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            paths = self._build_state(Path(temporary))
            self._write_json(
                paths["bindings"],
                {
                    "slots": {
                        "1": {
                            "character_id": 101,
                            "name": "Alpha",
                            "pid": 1011,
                        }
                    }
                },
            )
            self._write_json(
                paths["quests"],
                {
                    "version": 1,
                    "characters": {
                        "slot:1": {
                            "done": {"10": True},
                            "completed_quest_objectives": {"10": [100]},
                            "quest_items": {"10": {"1000": True}},
                        },
                        "character:101": {
                            "done": {"20": True},
                            "completed_quest_objectives": {"20": [200]},
                            "quest_items": {"20": {"2000": True}},
                        },
                    },
                },
            )
            self._write_json(
                paths["achievements"],
                {
                    "version": 1,
                    "characters": {
                        "slot:1": {
                            "completed_achievements": [101],
                            "completed_objectives": {"101": [1]},
                        },
                        "character:101": {
                            "completed_achievements": [202],
                            "completed_objectives": {"202": [2]},
                        },
                    },
                },
            )
            self._write_json(
                paths["guides"],
                {
                    "version": 1,
                    "characters": {
                        "slot:1": {"steps": {"guide-a": ["step-1"]}},
                        "character:101": {"steps": {"guide-a": ["step-2"]}},
                    },
                },
            )
            resolver = self._resolver(paths)
            before_verified_identity = self._progress_snapshot(paths)

            direct = resolver.resolve_for_session("Alpha", "tcp:1011:0", None)
            self.assertIsNotNone(direct)
            self.assertEqual(direct.character_key, "character:101")
            self.assertEqual(self._progress_snapshot(paths), before_verified_identity)

            resolved = resolver.resolve_for_session("Alpha", "tcp:1011:1", 101)
            self.assertIsNotNone(resolved)
            self.assertEqual(resolved.character_key, "character:101")

            migrated = self._progress_snapshot(paths)
            for payload in migrated.values():
                self.assertNotIn("slot:1", payload["characters"])
                self.assertEqual(set(payload["characters"]), {"character:101"})

            quest_state = migrated["quests"]["characters"]["character:101"]
            self.assertEqual(quest_state["done"], {"10": True, "20": True})
            self.assertEqual(
                quest_state["completed_quest_objectives"],
                {"10": [100], "20": [200]},
            )
            self.assertEqual(
                quest_state["quest_items"],
                {"10": {"1000": True}, "20": {"2000": True}},
            )

            achievement_state = migrated["achievements"]["characters"]["character:101"]
            self.assertEqual(achievement_state["completed_achievements"], [202, 101])
            self.assertEqual(
                achievement_state["completed_objectives"],
                {"202": [2], "101": [1]},
            )

            guide_state = migrated["guides"]["characters"]["character:101"]
            self.assertEqual(guide_state["steps"], {"guide-a": ["step-2", "step-1"]})

            bindings = json.loads(paths["bindings"].read_text(encoding="utf-8"))
            self.assertNotIn("slots", bindings)
            self.assertEqual(bindings.get("legacy_slots"), {})
            self.assertIn("101", bindings.get("characters", {}))
            self.assertNotIn("legacy_slot", bindings["characters"]["101"])

            replay = resolver.resolve_for_session("Alpha", "tcp:1011:2", 101)
            self.assertIsNotNone(replay)
            self.assertEqual(replay.character_key, "character:101")
            self.assertEqual(self._progress_snapshot(paths), migrated)


if __name__ == "__main__":
    unittest.main()
