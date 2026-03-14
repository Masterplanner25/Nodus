import json
import os
import time
import unittest
import http.client

from nodus.services.server import run_in_thread


class ApiEndpointTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server, cls.thread = run_in_thread("127.0.0.1", 0)
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

    def test_disassemble_endpoint(self):
        status, payload = self.request("POST", "/disassemble", {"code": "print(1)", "filename": "inline.nd"})
        self.assertEqual(status, 200)
        self.assertTrue(payload["ok"])
        self.assertIn("CALL print", payload["disassembly"])

    def test_dis_endpoint(self):
        status, payload = self.request("POST", "/dis", {"code": "print(1)", "filename": "inline.nd"})
        self.assertEqual(status, 200)
        self.assertTrue(payload["ok"])
        self.assertIn("dis", payload)

    def test_plan_graph_endpoint(self):
        code = (
            "let A = task(fn() { return 1 }, nil)\n"
            "let plan = plan_graph([A])\n"
        )
        status, payload = self.request("POST", "/plan_graph", {"code": code, "filename": "inline.nd"})
        self.assertEqual(status, 200)
        self.assertTrue(payload["ok"])
        self.assertIsNotNone(payload.get("plan", {}).get("graph_id"))
        self.assertIsNotNone(payload.get("graph_id"))

    def test_graph_plan_endpoint(self):
        code = (
            "let A = task(fn() { return 1 }, nil)\n"
            "let plan = plan_graph([A])\n"
        )
        status, payload = self.request("POST", "/graph/plan", {"code": code, "filename": "inline.nd"})
        self.assertEqual(status, 200)
        self.assertTrue(payload["ok"])
        self.assertIsNotNone(payload.get("graph_id"))

    def test_graph_run_and_events(self):
        code = (
            "let A = task(fn() { return 1 }, nil)\n"
            "let result = run_graph([A])\n"
        )
        status, payload = self.request("POST", "/graph/run", {"code": code, "filename": "inline.nd"})
        self.assertEqual(status, 200)
        self.assertTrue(payload["ok"])
        self.assertIsNotNone(payload.get("graph_id"))
        events_status, events = self.request("GET", "/runtime/events")
        self.assertEqual(events_status, 200)
        types = [event["type"] for event in events.get("events", [])]
        self.assertIn("task_start", types)
        self.assertIn("task_success", types)

    def test_graph_resume_endpoint(self):
        code = (
            "let A = task(fn() { return 2 }, nil)\n"
            "let B = task(fn(x) { return x + 1 }, A)\n"
            "let plan = plan_graph([A, B])\n"
        )
        status, payload = self.request("POST", "/graph/plan", {"code": code, "filename": "inline.nd"})
        self.assertEqual(status, 200)
        self.assertTrue(payload["ok"])
        graph_id = payload.get("graph_id")
        self.assertIsNotNone(graph_id)
        path = os.path.join(".nodus", "graphs", f"{graph_id}.json")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        state = {
            "graph_id": graph_id,
            "status": "running",
            "tasks": {
                "task_1": {"state": "completed", "result": 2, "attempts": 1},
                "task_2": {"state": "pending", "attempts": 0},
            },
        }
        with open(path, "w", encoding="utf-8") as f:
            json.dump(state, f)
        status, payload = self.request("POST", "/graph/resume", {"graph_id": graph_id})
        self.assertEqual(status, 200)
        self.assertTrue(payload["ok"])
        self.assertIn("task_2", payload.get("result", {}).get("tasks", {}))


if __name__ == "__main__":
    unittest.main()
