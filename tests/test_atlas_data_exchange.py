import hashlib
import json
import unittest

from tools.atlas_data_exchange import (
    InvalidDocumentExchange, load_documentalist_exchange, plan_documentalist_exchange,
)

SOURCE_SHA = "a" * 64


def batch(*records):
    rows = []
    for payload in records:
        raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
        rows.append({"id": str(payload["id"]), "sha256": hashlib.sha256(raw).hexdigest(), "payload": payload})
    obj = {"schema": "documentalist-batch/v1", "source": "local:fixture",
           "collected_at": "2026-10-22T15:30:00Z",
           "source_sha256": SOURCE_SHA, "records": rows}
    return json.dumps(obj, ensure_ascii=False).encode("utf-8")


class AtlasDataExchangeTests(unittest.TestCase):
    def test_accepts_documentalist_wire_format(self):
        obj = load_documentalist_exchange(batch(
            {"id": 42, "kind": "quest", "label": "Start", "references": []},
        ))
        self.assertEqual(obj.records[0].identifier, "42")
        self.assertEqual(obj.records[0].kind, "quest")
        self.assertEqual(obj.source_sha256, SOURCE_SHA)

    def test_diffs_and_checks_cross_links_without_deleting(self):
        old = load_documentalist_exchange(batch(
            {"id": 1, "kind": "quest", "label": "A"},
            {"id": 2, "kind": "quest", "label": "Old"},
        ))
        new = load_documentalist_exchange(batch(
            {"id": 1, "kind": "quest", "label": "Updated"},
            {"id": 9, "kind": "guide", "references": [{"kind": "quest", "id": 1}]},
        ))
        result = plan_documentalist_exchange(old, new)
        self.assertEqual([(r.kind, r.identifier, r.action) for r in result],
                         [("guide", "9", "add"), ("quest", "1", "update"),
                          ("quest", "2", "absent_in_batch")])

    def test_unknown_quest_link_is_refused(self):
        incoming = load_documentalist_exchange(batch(
            {"id": 9, "kind": "guide", "references": [{"kind": "quest", "id": 404}]},
        ))
        old = load_documentalist_exchange(batch())
        with self.assertRaises(ValueError):
            plan_documentalist_exchange(old, incoming)

    def test_rejects_tampered_hash_and_id(self):
        doc = json.loads(batch({"id": 1, "kind": "quest"}))
        doc["records"][0]["payload"]["label"] = "tampered"
        with self.assertRaises(InvalidDocumentExchange):
            load_documentalist_exchange(json.dumps(doc).encode())
        doc = json.loads(batch({"id": 1, "kind": "quest"}))
        doc["records"][0]["id"] = "different"
        with self.assertRaises(InvalidDocumentExchange):
            load_documentalist_exchange(json.dumps(doc).encode())

    def test_rejects_invalid_schema_and_duplicate_json_keys(self):
        data = batch({"id": 1, "kind": "quest"})
        with self.assertRaises(InvalidDocumentExchange):
            load_documentalist_exchange(data.replace(b"documentalist-batch/v1", b"future-batch/v2"))
        with self.assertRaises(InvalidDocumentExchange):
            load_documentalist_exchange(b'{"schema":"v1","schema":"v2"}')

    def test_rejects_duplicate_identity_and_unknown_kind(self):
        with self.assertRaises(InvalidDocumentExchange):
            load_documentalist_exchange(batch({"id": 1, "kind": "quest"},
                                              {"id": 1, "kind": "quest"}))
        with self.assertRaises(InvalidDocumentExchange):
            load_documentalist_exchange(batch({"id": 1, "kind": "unknown"}))


if __name__ == "__main__":
    unittest.main()
