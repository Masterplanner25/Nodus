import http.client
import json
import os
import shutil
import tempfile
import time
import unittest

from nodus.services.server import run_in_thread


class SnapshotTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp_dir = tempfile.mkdtemp()
        cls.snapshot_dir = os.path.join(cls.temp_dir, "snapshots")
        os.environ["NODUS_SNAPSHOT_DIR"] = cls.snapshot_dir
        cls.server, cls.thread = run_in_thread("127.0.0.1", 0)
        cls.port = cls.server.server_address[1]
        time.sleep(0.05)

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        shutil.rmtree(cls.temp_dir, ignore_errors=True)
        if "NODUS_SNAPSHOT_DIR" in os.environ:
            del os.environ["NODUS_SNAPSHOT_DIR"]

    def request(self, method: str, path: str, payload: dict | None = None):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        body = None
        headers = {}
        if payload is not None:
            body = json.dumps(payload)
            headers["Content-Type"] = "application/json"
        conn.request(method, path, body=body, headers=headers)
        resp = conn.getresponse()
        data = resp.read().decode("utf-8")
        conn.close()
        return resp.status, json.loads(data) if data else {}

    def test_snapshot_persistence(self):
        status, payload = self.request("POST", "/session")
        session_id = payload["session"]
        self.request("POST", "/execute", {"session": session_id, "code": "x = 5", "filename": "inline.nd"})
        status, payload = self.request("POST", "/snapshot", {"session": session_id})
        snapshot_id = payload["snapshot"]
        status, payload = self.request("POST", "/restore", {"snapshot": snapshot_id})
        new_session = payload["session"]
        status, payload = self.request("POST", "/execute", {"session": new_session, "code": "print(x)", "filename": "inline.nd"})
        self.assertEqual(payload["stdout"], "5.0\n")

    def test_snapshot_isolation(self):
        status, payload = self.request("POST", "/session")
        session_id = payload["session"]
        self.request("POST", "/execute", {"session": session_id, "code": "x = 9", "filename": "inline.nd"})
        status, payload = self.request("POST", "/snapshot", {"session": session_id})
        snapshot_id = payload["snapshot"]
        status, payload = self.request("POST", "/restore", {"snapshot": snapshot_id})
        new_session = payload["session"]
        self.assertNotEqual(session_id, new_session)

    def test_snapshot_deletion(self):
        status, payload = self.request("POST", "/session")
        session_id = payload["session"]
        status, payload = self.request("POST", "/snapshot", {"session": session_id})
        snapshot_id = payload["snapshot"]
        status, payload = self.request("DELETE", f"/snapshot/{snapshot_id}")
        self.assertTrue(payload["ok"])
        status, payload = self.request("POST", "/restore", {"snapshot": snapshot_id})
        self.assertIn("error", payload)


if __name__ == "__main__":
    unittest.main()
