import http.client
import json
import os
import tempfile
import time
import unittest

from nodus.services.server import run_in_thread
from nodus_workflow.store import SQLiteWorkflowStore


class ServerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._tmpdir = tempfile.TemporaryDirectory()
        cls._original_cwd = os.getcwd()
        os.chdir(cls._tmpdir.name)
        cls.server, cls.thread = run_in_thread("127.0.0.1", 0, allowed_paths=[cls._tmpdir.name])
        cls.port = cls.server.server_address[1]
        time.sleep(0.05)

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=1.0)
        os.chdir(cls._original_cwd)
        cls._tmpdir.cleanup()

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
        self.assertEqual(payload["workflow_store"]["backend"], "local")

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

    def test_runtime_includes_workflow_sweep_summary(self):
        status, payload = self.request("GET", "/runtime")
        self.assertEqual(status, 200)
        self.assertIn("workflow_sweep", payload)
        self.assertIn("workflow_store", payload)
        self.assertIn("expired_waits", payload["workflow_sweep"])
        self.assertIn("resumed_retries", payload["workflow_sweep"])
        self.assertIn("rehydrated_runs", payload["workflow_sweep"])

    def test_workflow_runs_endpoint_filters_by_status(self):
        workflow_code = """
workflow demo {
    step gate {
        return workflow_wait("approval.granted", "req-runs", {kind: "approval"})
    }
}
"""
        status, payload = self.request(
            "POST",
            "/workflow/run",
            {"code": workflow_code, "filename": "runs_filter.nd"},
        )
        self.assertEqual(status, 200)
        self.assertTrue(payload["ok"])

        status, runs = self.request("GET", "/workflow/runs?status=waiting")
        self.assertEqual(status, 200)
        self.assertEqual(runs["filter"]["status"], ["waiting"])
        self.assertIn("counts", runs)
        self.assertIn("pagination", runs)
        self.assertGreaterEqual(runs["counts"]["waiting"], 1)
        self.assertEqual(runs["pagination"]["returned"], len(runs["runs"]))
        self.assertTrue(any(item["status"] == "waiting" for item in runs["runs"]))

    def test_workflow_runs_endpoint_supports_workflow_and_pagination_filters(self):
        workflow_code = """
workflow paging_demo {
    step gate {
        return workflow_wait("approval.granted", "req-runs-paged", {kind: "approval"})
    }
}
"""
        for idx in range(2):
            status, payload = self.request(
                "POST",
                "/workflow/run",
                {"code": workflow_code, "filename": f"runs_filter_{idx}.nd"},
            )
            self.assertEqual(status, 200)
            self.assertTrue(payload["ok"])

        status, runs = self.request("GET", "/workflow/runs?status=waiting&workflow=paging_demo&execution_kind=workflow&limit=1&offset=0")
        self.assertEqual(status, 200)
        self.assertEqual(runs["filter"]["workflow"], "paging_demo")
        self.assertEqual(runs["filter"]["execution_kind"], "workflow")
        self.assertEqual(runs["filter"]["limit"], 1)
        self.assertEqual(runs["filter"]["offset"], 0)
        self.assertEqual(runs["counts"]["waiting"], 2)
        self.assertEqual(runs["pagination"]["total"], 2)
        self.assertEqual(runs["pagination"]["returned"], 1)
        self.assertTrue(runs["pagination"]["has_more"])
        self.assertEqual(len(runs["runs"]), 1)
        self.assertTrue(all(item["workflow_name"] == "paging_demo" for item in runs["runs"]))

    def test_workflow_runs_endpoint_supports_wait_retry_and_cursor_filters(self):
        waiting_code = """
workflow cursor_demo {
    step gate {
        return workflow_wait("approval.granted", "req-cursor", {kind: "approval"})
    }
}
"""
        status, waiting = self.request(
            "POST",
            "/workflow/run",
            {"code": waiting_code, "filename": "cursor_wait.nd"},
        )
        self.assertEqual(status, 200)
        self.assertTrue(waiting["ok"])

        retry_id = "cursor-retry-seeded"
        seeded = self.server.service.workflow_runner.store.create_run(
            run_id=retry_id,
            graph_id=retry_id,
            workflow_name="cursor_demo",
            execution_kind="workflow",
            metadata={},
        )
        self.server.service.workflow_runner.store.schedule_retry(
            retry_id,
            task_id="task_1",
            step_name="flaky",
            attempt=1.0,
            max_retries=1.0,
            delay_ms=50.0,
            next_attempt_at=999999.0,
            classification="retryable",
            last_error="boom",
        )
        self.assertIsNotNone(seeded)

        status, first_page = self.request(
            "GET",
            "/workflow/runs?workflow=cursor_demo&execution_kind=workflow&has_wait=true&has_retry=false&limit=1&cursor=o:0",
        )
        self.assertEqual(status, 200)
        self.assertEqual(first_page["counts"]["waiting"], 1)
        self.assertEqual(first_page["counts"]["retry_scheduled"], 0)
        self.assertEqual(first_page["filter"]["has_wait"], True)
        self.assertEqual(first_page["filter"]["has_retry"], False)
        self.assertEqual(first_page["pagination"]["cursor"], "o:0")
        self.assertIsNone(first_page["pagination"]["next_cursor"])
        self.assertEqual(len(first_page["runs"]), 1)

        status, all_runs = self.request(
            "GET",
            "/workflow/runs?workflow=cursor_demo&execution_kind=workflow&limit=1&cursor=o:0",
        )
        self.assertEqual(status, 200)
        self.assertEqual(all_runs["pagination"]["next_cursor"], "o:1")
        next_cursor = all_runs["pagination"]["next_cursor"]
        status, second_page = self.request(
            "GET",
            f"/workflow/runs?workflow=cursor_demo&execution_kind=workflow&limit=1&cursor={next_cursor}",
        )
        self.assertEqual(status, 200)
        self.assertEqual(second_page["pagination"]["cursor"], "o:1")
        self.assertEqual(len(second_page["runs"]), 1)


class ServerAuthTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.token = "secret-token"
        cls._tmpdir = tempfile.TemporaryDirectory()
        cls._original_cwd = os.getcwd()
        os.chdir(cls._tmpdir.name)
        cls.server, cls.thread = run_in_thread(
            "127.0.0.1",
            0,
            allowed_paths=[cls._tmpdir.name],
            auth_token=cls.token,
        )
        cls.port = cls.server.server_address[1]
        time.sleep(0.05)

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=1.0)
        os.chdir(cls._original_cwd)
        cls._tmpdir.cleanup()

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


class SQLiteWorkflowServerTests(unittest.TestCase):
    def request(self, port: int, method: str, path: str, payload: dict | None = None):
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
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

    def test_workflow_run_uses_sqlite_store_when_configured(self):
        workflow_code = """
workflow demo {
    step first {
        checkpoint "after-first"
        return 1
    }
}
"""
        with tempfile.TemporaryDirectory() as td:
            db_path = os.path.join(td, "workflow_framework.sqlite3")
            original = os.getcwd()
            os.chdir(td)
            try:
                server, thread = run_in_thread(
                    "127.0.0.1",
                    0,
                    allowed_paths=[td],
                    workflow_store_backend="sqlite",
                    workflow_store_path=db_path,
                )
                try:
                    port = server.server_address[1]
                    time.sleep(0.05)
                    status, health = self.request(port, "GET", "/health")
                    self.assertEqual(status, 200)
                    self.assertEqual(health["workflow_store"]["backend"], "sqlite")
                    self.assertEqual(health["workflow_store"]["path"], os.path.abspath(db_path))

                    status, payload = self.request(
                        port,
                        "POST",
                        "/workflow/run",
                        {"code": workflow_code, "filename": "sqlite_workflow.nd"},
                    )
                    self.assertEqual(status, 200)
                    self.assertTrue(payload["ok"])
                    graph_id = payload["result"]["graph_id"]

                    store = SQLiteWorkflowStore(path=db_path)
                    record = store.get_run(graph_id)
                    self.assertIsNotNone(record)
                    self.assertEqual(record.workflow_name, "demo")
                finally:
                    server.shutdown()
                    server.server_close()
                    thread.join(timeout=1.0)
            finally:
                os.chdir(original)

    def test_dead_letter_list_and_replay_are_exposed_over_http(self):
        workflow_code = """
workflow demo {
    step gate {
        return workflow_wait("approval.granted", "req-http-replay", {kind: "approval"}, 500)
    }

    step finish after gate {
        let payload = workflow_resume_payload()
        return payload["approved"]
    }
}
"""
        with tempfile.TemporaryDirectory() as td:
            db_path = os.path.join(td, "workflow_framework.sqlite3")
            original = os.getcwd()
            os.chdir(td)
            try:
                server, thread = run_in_thread(
                    "127.0.0.1",
                    0,
                    allowed_paths=[td],
                    workflow_store_backend="sqlite",
                    workflow_store_path=db_path,
                )
                try:
                    port = server.server_address[1]
                    time.sleep(0.05)
                    status, payload = self.request(
                        port,
                        "POST",
                        "/workflow/run",
                        {"code": workflow_code, "filename": "sqlite_wait_workflow.nd"},
                    )
                    self.assertEqual(status, 200)
                    self.assertTrue(payload["ok"])
                    graph_id = payload["result"]["graph_id"]

                    service = server.service
                    record = service.workflow_runner.get_run(graph_id)
                    self.assertIsNotNone(record)
                    service.workflow_runner.expire_wait_timeouts(now_ms=(record.wait.registered_at or 0) + 1000)

                    status, dead_letters = self.request(port, "GET", "/workflow/dead-letters")
                    self.assertEqual(status, 200)
                    run_ids = {item["run_id"] for item in dead_letters["runs"]}
                    self.assertIn(graph_id, run_ids)

                    status, inspect = self.request(port, "GET", f"/workflow/runs/{graph_id}")
                    self.assertEqual(status, 200)
                    self.assertEqual(inspect["run"]["status"], "dead_lettered")

                    status, rearmed = self.request(
                        port,
                        "POST",
                        "/workflow/replay",
                        {"graph_id": graph_id, "rearm_only": True},
                    )
                    self.assertEqual(status, 200)
                    self.assertTrue(rearmed["ok"])
                    self.assertTrue(rearmed["result"]["rearmed"])

                    status, replayed = self.request(
                        port,
                        "POST",
                        "/workflow/replay",
                        {
                            "graph_id": graph_id,
                            "resume_payload": {"approved": True},
                            "event_type": "approval.granted",
                            "correlation_key": "req-http-replay",
                        },
                    )
                    self.assertEqual(status, 200)
                    self.assertTrue(replayed["ok"])
                    self.assertEqual(replayed["result"]["steps"]["finish"], True)
                finally:
                    server.shutdown()
                    server.server_close()
                    thread.join(timeout=1.0)
            finally:
                os.chdir(original)


if __name__ == "__main__":
    unittest.main()
