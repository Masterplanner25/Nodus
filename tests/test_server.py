import http.client
import json
import time
import unittest

from nodus.services.server import run_in_thread


class ServerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server, cls.thread = run_in_thread("127.0.0.1", 0, allowed_paths=["."])
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

    def test_health(self):
        status, payload = self.request("GET", "/health")
        self.assertEqual(status, 200)
        self.assertEqual(payload["status"], "ok")
        self.assertEqual(payload["runtime"], "nodus")

    def test_execute(self):
        status, payload = self.request("POST", "/execute", {"code": "print(1 + 1)", "filename": "inline.nd"})
        self.assertEqual(status, 200)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["stdout"], "2.0\n")

    def test_syntax_error(self):
        status, payload = self.request("POST", "/execute", {"code": "fn {", "filename": "inline.nd"})
        self.assertEqual(status, 200)
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["error"]["type"], "syntax")

    def test_ast(self):
        status, payload = self.request("POST", "/ast", {"code": "let x = 1", "filename": "inline.nd"})
        self.assertEqual(status, 200)
        self.assertTrue(payload["ok"])
        self.assertIn("Module", payload["ast_pretty"])
        self.assertEqual(payload["ast"][0]["type"], "Let")

    def test_sandbox_timeout(self):
        status, payload = self.request("POST", "/execute", {"code": "while (true) { }", "filename": "inline.nd"})
        self.assertEqual(status, 200)
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["error"]["type"], "sandbox")
        self.assertIn("timed out", payload["error"]["message"])

    def test_input_blocked(self):
        status, payload = self.request("POST", "/execute", {"code": "input(\"x\")", "filename": "inline.nd"})
        self.assertEqual(status, 200)
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["error"]["type"], "sandbox")
        self.assertIn("input()", payload["error"]["message"])


class ServerAuthTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.token = "secret-token"
        cls.server, cls.thread = run_in_thread("127.0.0.1", 0, allowed_paths=["."], auth_token=cls.token)
        cls.port = cls.server.server_address[1]
        time.sleep(0.05)

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def request(self, method: str, path: str, payload: dict | None = None, *, auth: bool = False):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        body = None
        headers = {}
        if payload is not None:
            body = json.dumps(payload)
            headers["Content-Type"] = "application/json"
        if auth:
            headers["Authorization"] = f"Bearer {self.token}"
        conn.request(method, path, body=body, headers=headers)
        resp = conn.getresponse()
        data = resp.read().decode("utf-8")
        conn.close()
        return resp.status, json.loads(data) if data else {}

    def test_auth_required(self):
        status, payload = self.request("GET", "/health")
        self.assertEqual(status, 401)
        self.assertEqual(payload.get("error"), "unauthorized")

    def test_auth_allows_access(self):
        status, payload = self.request("GET", "/health", auth=True)
        self.assertEqual(status, 200)
        self.assertEqual(payload["status"], "ok")


if __name__ == "__main__":
    unittest.main()
