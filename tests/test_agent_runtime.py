import io
import json
import time
import http.client
import unittest
from contextlib import redirect_stdout

import nodus as lang

from nodus.services.agent_runtime import AGENT_REGISTRY, register_agent, unregister_agent
from nodus.services.memory_runtime import GLOBAL_MEMORY_STORE
from nodus.services.server import run_in_thread


def import_state():
    return {
        "loaded": set(),
        "loading": set(),
        "exports": {},
        "modules": {},
        "module_ids": {},
        "project_root": None,
    }


def run_program(src: str, *, source_path: str = "main.nd"):
    _ast, code, functions, code_locs = lang.compile_source(
        src,
        source_path=source_path,
        import_state=import_state(),
    )
    vm = lang.VM(code, functions, code_locs=code_locs, source_path=source_path)
    buf = io.StringIO()
    with redirect_stdout(buf):
        vm.run()
    return vm, buf.getvalue().splitlines()


class AgentRuntimeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server, cls.thread = run_in_thread("127.0.0.1", 0)
        cls.port = cls.server.server_address[1]
        time.sleep(0.05)

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def setUp(self):
        AGENT_REGISTRY.clear()
        GLOBAL_MEMORY_STORE.load_snapshot({})

    def tearDown(self):
        AGENT_REGISTRY.clear()
        GLOBAL_MEMORY_STORE.load_snapshot({})

    def request(self, method: str, path: str, payload: dict | None = None):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        headers = {}
        body = None
        if payload is not None:
            headers["Content-Type"] = "application/json"
            body = json.dumps(payload)
        conn.request(method, path, body=body, headers=headers)
        response = conn.getresponse()
        data = response.read().decode("utf-8")
        conn.close()
        return response.status, json.loads(data) if data else {}

    def test_tool_dispatch_builtin(self):
        _vm, out = run_program(
            """
print(json_stringify(tool_call("nodus_check", {
    "code": "print(1 + 1)",
    "filename": "inline.nd"
})))
"""
        )
        result = json.loads(out[0])
        self.assertTrue(result["ok"])
        self.assertEqual(result["stage"], "check")

    def test_std_tools_wrappers(self):
        _vm, out = run_program(
            """
import "std:tools" as tools
print(json_stringify(tools.available()))
print(json_stringify(tools.describe("nodus_check")))
print(json_stringify(tools.execute("nodus_execute", {
    "code": "print(2)",
    "filename": "inline.nd"
})))
"""
        )
        names = json.loads(out[0])
        info = json.loads(out[1])
        result = json.loads(out[2])
        self.assertIn("nodus_check", names)
        self.assertEqual(info["name"], "nodus_check")
        self.assertTrue(result["ok"])
        self.assertEqual(result["stdout"], "2.0\n")

    def test_memory_store(self):
        _vm, out = run_program(
            """
import "std:memory" as memory
memory.put("topic", "AI SEO")
print(json_stringify(memory.get("topic")))
print(json_stringify(memory.has("topic")))
print(json_stringify(memory.keys()))
print(json_stringify(memory.delete("topic")))
print(json_stringify(memory.get("topic")))
"""
        )
        self.assertEqual(json.loads(out[0]), "AI SEO")
        self.assertTrue(json.loads(out[1]))
        self.assertEqual(json.loads(out[2]), ["topic"])
        self.assertTrue(json.loads(out[3]))
        self.assertIsNone(json.loads(out[4]))

    def test_agent_call_fallback(self):
        _vm, out = run_program(
            """
print(json_stringify(agent_call("summarize", {
    "input": "notes"
})))
"""
        )
        result = json.loads(out[0])
        self.assertFalse(result["ok"])
        self.assertEqual(result["error"]["type"], "agent")

    def test_registered_mock_agent(self):
        register_agent("summarize", lambda payload: {"summary": payload["input"]})
        _vm, out = run_program(
            """
import "std:agent" as agent
print(json_stringify(agent.call("summarize", {
    "input": "hello"
})))
"""
        )
        result = json.loads(out[0])
        self.assertTrue(result["ok"])
        self.assertEqual(result["result"]["summary"], "hello")
        unregister_agent("summarize")

    def test_runtime_events_emitted(self):
        register_agent("summarize", lambda payload: {"summary": payload["input"]})
        vm, _out = run_program(
            """
tool_call("nodus_check", {
    "code": "print(1)",
    "filename": "inline.nd"
})
memory_put("topic", "AI SEO")
memory_get("topic")
agent_call("summarize", {
    "input": "AI SEO"
})
agent_call("missing", {
    "input": "AI SEO"
})
"""
        )
        types = [event.type for event in vm.event_bus.events()]
        self.assertIn("tool_call_start", types)
        self.assertIn("tool_call_complete", types)
        self.assertIn("memory_put", types)
        self.assertIn("memory_get", types)
        self.assertIn("agent_call_start", types)
        self.assertIn("agent_call_complete", types)
        self.assertIn("agent_call_fail", types)

    def test_api_endpoints(self):
        register_agent("summarize", lambda payload: {"summary": payload["input"]})
        status, payload = self.request(
            "POST",
            "/tool/call",
            {"name": "nodus_check", "args": {"code": "print(1 + 1)", "filename": "inline.nd"}},
        )
        self.assertEqual(status, 200)
        self.assertTrue(payload["ok"])

        status, payload = self.request(
            "POST",
            "/agent/call",
            {"name": "summarize", "payload": {"input": "notes"}},
        )
        self.assertEqual(status, 200)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["result"]["summary"], "notes")

        status, payload = self.request("POST", "/memory", {"key": "topic", "value": "AI SEO"})
        self.assertEqual(status, 200)
        self.assertTrue(payload["ok"])

        status, payload = self.request("GET", "/memory?key=topic")
        self.assertEqual(status, 200)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["result"], "AI SEO")

        status, payload = self.request("GET", "/memory")
        self.assertEqual(status, 200)
        self.assertTrue(payload["ok"])
        self.assertIn("topic", payload["result"])

        status, payload = self.request("DELETE", "/memory/topic")
        self.assertEqual(status, 200)
        self.assertTrue(payload["ok"])
        self.assertTrue(payload["result"])

    def test_cli_wrappers(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            exit_code = lang.main(
                ["nodus", "tool-call", "nodus_check", "--json", "{\"code\":\"print(1)\",\"filename\":\"inline.nd\"}"]
            )
        self.assertEqual(exit_code, 0)
        payload = json.loads(buf.getvalue().strip())
        self.assertTrue(payload["ok"])

        buf = io.StringIO()
        with redirect_stdout(buf):
            exit_code = lang.main(["nodus", "memory-put", "topic", "--json", "\"AI SEO\""])
        self.assertEqual(exit_code, 0)

        buf = io.StringIO()
        with redirect_stdout(buf):
            exit_code = lang.main(["nodus", "memory-get", "topic"])
        self.assertEqual(exit_code, 0)
        self.assertEqual(json.loads(buf.getvalue().strip()), "AI SEO")

        buf = io.StringIO()
        with redirect_stdout(buf):
            exit_code = lang.main(["nodus", "memory-keys"])
        self.assertEqual(exit_code, 0)
        self.assertIn("topic", json.loads(buf.getvalue().strip()))


if __name__ == "__main__":
    unittest.main()
