from __future__ import annotations

import unittest

from app.network.events import FinishedQuestsSnapshotEvent
from app.network.normalizer import DecodedClientMessage, ProtocolEventNormalizer
from app.network.quest_snapshot_decoder import FinishedQuestsSnapshotRule


class NetworkSnapshotContractTests(unittest.TestCase):
    def test_snapshot_mapping_requires_player_id_field(self) -> None:
        with self.assertRaises(ValueError):
            FinishedQuestsSnapshotRule(
                type_url="type.ankama.com/qst",
                finished_entry_field=1,
                quest_id_path_from_entry=(1,),
                player_id_field=None,
            )

    def test_normalizer_rejects_snapshot_without_player_id(self) -> None:
        message = DecodedClientMessage(
            session_id="s1",
            event_type="finished_quests_snapshot",
            fields={"quest_ids": (101, 202)},
            verified=True,
        )
        self.assertIsNone(ProtocolEventNormalizer().normalize(message))

    def test_normalizer_keeps_exact_snapshot_player_id(self) -> None:
        message = DecodedClientMessage(
            session_id="s1",
            event_type="finished_quests_snapshot",
            fields={"quest_ids": (101, 202), "player_id": 9001},
            event_id="snapshot:1",
            verified=True,
        )
        event = ProtocolEventNormalizer().normalize(message)
        self.assertIsInstance(event, FinishedQuestsSnapshotEvent)
        self.assertEqual(event.player_id, 9001)
        self.assertEqual(event.quest_ids, (101, 202))
        self.assertEqual(event.event_id, "snapshot:1")


if __name__ == "__main__":
    unittest.main()
