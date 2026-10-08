from __future__ import annotations

import json
import subprocess
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import urlopen

from tools.atlas_doctor_lib.live_graph import change_snapshot, handler_factory


class LiveGraphTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.git("init", "-q")
        self.git("config", "user.name", "Doctor")
        self.git("config", "user.email", "doctor@example.invalid")
        self.path = self.root / "app" / "file.py"
        self.path.parent.mkdir()
        self.path.write_text("x = 1\n")
        self.git("add", "-A")
        self.git("commit", "-qm", "base")
        self.sha = self.git("rev-parse", "HEAD")

    def git(self, *args):
        return subprocess.run(["git", *args], cwd=self.root, check=True,
                              capture_output=True, text=True).stdout.strip()

    def test_tracks_dirty_files_without_rebuilding(self):
        clean = change_snapshot(self.root, self.sha)
        self.assertEqual(clean["status"], "CLEAN")
        self.path.write_text("x = 2\n")
        changed = change_snapshot(self.root, self.sha)
        self.assertEqual(changed["changed_files"], ["app/file.py"])
        self.assertTrue(changed["graph_stale"])
        self.assertFalse(changed["graph_rebuilt"])
        self.assertFalse(changed["tests_executed"])

    def test_follows_new_commits_and_new_untracked_python_files(self):
        self.path.write_text("x = 3\n")
        self.git("add", "-A")
        self.git("commit", "-qm", "change")
        other = self.root / "app" / "new.py"
        other.write_text("pass\n")
        result = change_snapshot(self.root, self.sha)
        self.assertEqual(result["changed_files"], ["app/file.py", "app/new.py"])
        self.assertNotEqual(result["current_commit"], self.sha)

    def test_loopback_api_only_and_404(self):
        with ThreadingHTTPServer(("127.0.0.1", 0), handler_factory("<html>Atlas</html>",
                                            lambda: change_snapshot(self.root, self.sha))) as server:
            server.daemon_threads = True
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                base = f"http://127.0.0.1:{server.server_port}"
                with urlopen(base + "/api/live", timeout=5) as response:
                    body = json.load(response)
                    self.assertEqual(body["status"], "CLEAN")
                    self.assertEqual(response.headers["Cache-Control"], "no-store")
                with self.assertRaises(HTTPError) as err:
                    urlopen(base + "/../../.git/config", timeout=5)
                self.assertEqual(err.exception.code, 404)
            finally:
                server.shutdown()
                thread.join(timeout=3)

    def test_ping_does_not_scan_git_or_invoke_provider(self):
        calls = []
        def provider():
            calls.append("git")
            raise AssertionError("heartbeat must not scan the repo")
        with ThreadingHTTPServer(("127.0.0.1", 0), handler_factory("<html>Atlas</html>",provider)) as server:
            server.daemon_threads = True
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                with urlopen(f"http://127.0.0.1:{server.server_port}/api/ping", timeout=5) as response:
                    self.assertEqual(json.load(response)["status"], "ALIVE")
                self.assertEqual(calls, [])
            finally:
                server.shutdown()
                thread.join(timeout=3)

    def test_once_accepts_stale_graph_to_report_changes(self):
        from argparse import Namespace
        from unittest.mock import patch
        from tools.atlas_doctor import command_graph_live
        (self.root / "graphify-out").mkdir()
        (self.root / "graphify-out/graph.json").write_text(json.dumps({"built_at_commit": self.sha}))
        self.path.write_text("x = 44\n")
        with patch("tools.atlas_doctor_lib.architecture.graph_status", return_value={
                "status": "STALE", "graph": str(self.root / "graphify-out/graph.json")}):
            result = command_graph_live(self.root, Namespace(once=True, json=True))
        self.assertEqual(result["status"], "CHANGED")
        self.assertEqual(result["graph_validation"], "STALE")

    def test_ast_imports_changed_since_graph_snapshot(self):
        self.path.write_text("import json\nfrom collections import deque\n")
        result = change_snapshot(self.root, self.sha)
        change = result["source_import_delta"]["changes"][0]
        self.assertEqual(change["path"], "app/file.py")
        self.assertEqual([row["statement"] for row in change["added_imports"]],
                         ["from collections import deque", "import json"])
        self.assertEqual(result["source_import_delta"]["status"], "COMPLETE")

    def test_implicit_dynamic_import_not_claimed(self):
        self.path.write_text('name = "app.some_module"\n')
        self.assertEqual(change_snapshot(self.root, self.sha)["source_import_delta"]["changes"], [])

    def test_syntax_error_is_reported_without_false_pass(self):
        self.path.write_text("def bad(\\n")
        result = change_snapshot(self.root, self.sha)["source_import_delta"]
        self.assertEqual(result["status"], "PARTIAL")
        self.assertEqual(result["changes"], [])
        self.assertEqual(result["errors"][0]["path"], "app/file.py")

    def test_rejects_untrusted_git_sha(self):
        self.assertEqual(change_snapshot(self.root, "HEAD;rm -rf .")["status"], "BLOCKED")


if __name__ == "__main__":
    unittest.main()
