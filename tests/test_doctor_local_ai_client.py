import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import threading
import unittest

from tools.atlas_doctor_lib.local_ai_client import LocalDoctorModelError, diagnose_local
from tools.atlas_doctor_lib.local_ai_evidence import prepare_local_evidence

SHA = "a" * 40


class OllamaStub(BaseHTTPRequestHandler):
    payload = {"hypothesis": "A worker might retain a view reference.",
               "recommended_test_ids": ["test.ui.worker_lifecycle"]}
    requests = []

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        data = json.loads(self.rfile.read(length))
        type(self).requests.append((self.path, data))
        output = {"message": {"role": "assistant", "content": json.dumps(self.payload)}}
        body = json.dumps(output).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


class LocalDoctorModelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), OllamaStub)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.host = f"http://127.0.0.1:{cls.server.server_port}"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=5)

    def setUp(self):
        OllamaStub.requests.clear()
        OllamaStub.payload = {
            "hypothesis": "A worker might retain a view reference.",
            "recommended_test_ids": ["test.ui.worker_lifecycle"],
        }
        self.evidence = prepare_local_evidence(
            source_sha=SHA, affected_paths=["app/ui.py"],
            failing_test_ids=["test.ui.worker_lifecycle"], issue_ids=["RAM-1"],
        )

    def test_real_loopback_http_response_remains_advisory(self):
        result = diagnose_local(self.evidence, model="qwen2.5-coder:1.5b", base_url=self.host)
        self.assertEqual(result.status, "ADVISORY_ONLY")
        self.assertEqual(result.recommended_test_ids, ("test.ui.worker_lifecycle",))
        path, payload = OllamaStub.requests[0]
        self.assertEqual(path, "/api/chat")
        self.assertEqual(payload["messages"][-1]["role"], "user")
        self.assertIn(SHA, payload["messages"][-1]["content"])
        self.assertEqual(payload["keep_alive"], 0)
        self.assertEqual(payload["stream"], False)

    def test_remote_endpoint_rejected_before_any_request(self):
        for address in ("https://example.com", "http://example.com:11434",
                        "http://localhost:11434/evil", "http://user:pass@localhost:11434"):
            with self.subTest(address=address), self.assertRaises(LocalDoctorModelError):
                diagnose_local(self.evidence, model="example", base_url=address)
        self.assertFalse(OllamaStub.requests)

    def test_forged_pass_is_never_accepted(self):
        OllamaStub.payload = {"hypothesis": "CERTIFIED",
                              "recommended_test_ids": []}
        with self.assertRaises(LocalDoctorModelError):
            diagnose_local(self.evidence, model="example", base_url=self.host)

    def test_missing_or_invalid_model_is_rejected(self):
        for model in ("", "../model", "models/remote"):
            with self.subTest(model=model), self.assertRaises(LocalDoctorModelError):
                diagnose_local(self.evidence, model=model, base_url=self.host)
        self.assertFalse(OllamaStub.requests)

    def test_output_cannot_add_status_or_commands(self):
        OllamaStub.payload = {
            "hypothesis": "something",
            "recommended_test_ids": [],
            "status": "PASS",
            "command": "rm -rf .",
        }
        with self.assertRaises(LocalDoctorModelError):
            diagnose_local(self.evidence, model="example", base_url=self.host)


if __name__ == "__main__":
    unittest.main()
