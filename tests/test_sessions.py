import http.client
import json
import time
import unittest

from nodus.services.server import run_in_thread


class SessionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server, cls.thread = run_in_thread("127.0.0.1", 0, session_timeout_ms=50, allowed_paths=["."])
        cls.port = cls.server.server_address[1]
        time.sleep(0.05)

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

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

    def test_session_persistence(self):
        status, payload = self.request("POST", "/session")
        self.assertEqual(status, 200)
        session_id = payload["session"]
        self.request("POST", "/execute", {"session": session_id, "code": "x = 10", "filename": "inline.nd"})
        status, payload = self.request("POST", "/execute", {"session": session_id, "code": "print(x)", "filename": "inline.nd"})
        self.assertEqual(status, 200)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["stdout"], "10.0\n")

    def test_isolation(self):
        status, payload = self.request("POST", "/session")
        session_a = payload["session"]
        status, payload = self.request("POST", "/session")
        session_b = payload["session"]
        self.request("POST", "/execute", {"session": session_a, "code": "x = 1", "filename": "inline.nd"})
        self.request("POST", "/execute", {"session": session_b, "code": "x = 2", "filename": "inline.nd"})
        _status, payload = self.request("POST", "/execute", {"session": session_a, "code": "print(x)", "filename": "inline.nd"})
        self.assertEqual(payload["stdout"], "1.0\n")
        _status, payload = self.request("POST", "/execute", {"session": session_b, "code": "print(x)", "filename": "inline.nd"})
        self.assertEqual(payload["stdout"], "2.0\n")

    def test_expiration(self):
        status, payload = self.request("POST", "/session")
        session_id = payload["session"]
        time.sleep(0.1)
        status, payload = self.request("GET", "/sessions")
        sessions = {item["id"] for item in payload["sessions"]}
        self.assertNotIn(session_id, sessions)


if __name__ == "__main__":
    unittest.main()
