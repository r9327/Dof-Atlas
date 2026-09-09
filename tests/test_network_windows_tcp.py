from __future__ import annotations

import unittest

from app.network.windows_tcp import established_tcp_flows_for_pids


class NetworkWindowsTcpTests(unittest.TestCase):
    def test_invalid_pid_entries_are_ignored_without_querying_windows(self) -> None:
        self.assertEqual(
            established_tcp_flows_for_pids([None, "", "bad", 0, -1]),
            (),
        )

    def test_non_iterable_pid_input_fails_closed(self) -> None:
        self.assertEqual(established_tcp_flows_for_pids(None), ())


if __name__ == "__main__":
    unittest.main()
