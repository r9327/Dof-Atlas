import contextlib
from hashlib import sha256
import io
import json
from pathlib import Path
import tempfile
import unittest

from tools.atlas_data_exchange_cli import main


def bundle(records):
    rows = []
    for p in records:
        canonical = json.dumps(p, separators=(",", ":"), sort_keys=True).encode()
        rows.append({"id": str(p["id"]), "sha256": sha256(canonical).hexdigest(),
                     "payload": p})
    return {
        "schema": "documentalist-batch/v1", "source": "local:test",
        "source_sha256": "f" * 64,
        "collected_at": "2026-10-22T15:30:00Z", "records": rows,
    }


class DocumentalistPreviewCliTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.before = self.root / "before.json"
        self.after = self.root / "after.json"
        self.before.write_text(json.dumps(bundle([
            {"id": 1, "kind": "quest", "name": "One"},
            {"id": 2, "kind": "quest", "name": "Removed source"}
        ])))
        self.after.write_text(json.dumps(bundle([
            {"id": 1, "kind": "quest", "name": "Changed"},
            {"id": 9, "kind": "guide", "references": [{"kind": "quest", "id": 1}]}
        ])))

    def test_cli_outputs_source_bound_read_only_diff(self):
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            status = main([str(self.before), str(self.after), "--json"])
        self.assertEqual(status, 0)
        value = json.loads(stdout.getvalue())
        self.assertEqual(value["status"], "PREVIEW_ONLY")
        self.assertEqual(value["counts"], {"add": 1, "update": 1, "keep": 0, "absent_in_batch": 1})
        self.assertTrue(self.before.exists())
        self.assertTrue(self.after.exists())

    def test_cli_rejects_unknown_reference(self):
        self.after.write_text(json.dumps(bundle([
            {"id": 9, "kind": "guide", "references": [{"kind": "quest", "id": 404}]},
        ])))
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            status = main([str(self.before), str(self.after), "--json"])
        self.assertEqual(status, 2)
        self.assertEqual(json.loads(stderr.getvalue())["status"], "INVALID")

    def test_cli_rejects_missing_file(self):
        with contextlib.redirect_stderr(io.StringIO()):
            status = main([str(self.before), str(self.root / "missing"), "--json"])
        self.assertEqual(status, 2)


if __name__ == "__main__":
    unittest.main()
