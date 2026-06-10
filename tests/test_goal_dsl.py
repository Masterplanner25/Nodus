import io
import json
import os
import task_graph
import tempfile
import time
import unittest
from contextlib import redirect_stderr, redirect_stdout
import http.client

import nodus as lang
from nodus.runtime.module_loader import ModuleLoader
from nodus.services.agent_runtime import AGENT_REGISTRY, register_agent
from nodus.services.memory_runtime import GLOBAL_MEMORY_STORE
from nodus.services.server import run_in_thread


def run_program(src: str, source_path: str = "goal.nd"):
    _loader = ModuleLoader(project_root=None)
    code, functions, code_locs = _loader.compile_only(
        src,
        module_name=source_path,
    )
    vm = lang.VM(code, functions, code_locs=code_locs, source_path=source_path)
    out_buf = io.StringIO()
    err_buf = io.StringIO()
    with redirect_stdout(out_buf), redirect_stderr(err_buf):
        vm.run()
    return vm, out_buf.getvalue().splitlines(), err_buf.getvalue()


class GoalDslTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server, cls.thread = run_in_thread("127.0.0.1", 0, allowed_paths=["."])
        cls.port = cls.server.server_address[1]
        time.sleep(0.05)

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def setUp(self):
        GLOBAL_MEMORY_STORE.load_snapshot({})
        AGENT_REGISTRY.clear()

    def tearDown(self):
        GLOBAL_MEMORY_STORE.load_snapshot({})
        AGENT_REGISTRY.clear()

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

    def test_linear_goal(self):
        src = """
goal demo {
    step a { return 1 }
    step b after a { return a + 1 }
}

let result = run_goal(demo)
print(result["goal"])
print(result["steps"]["a"])
print(result["steps"]["b"])
"""
        _vm, out, err = run_program(src)
        self.assertEqual(out, ["demo", "1.0", "2.0"])
        self.assertEqual(err.strip(), "")

    def test_tool_action_result_is_step_result(self):
        src = """
goal demo {
    step research {
        action tool "nodus_check" with {
            code: "print(1 + 1)",
            filename: "inline.nd"
        }
    }
}

let result = run_goal(demo)
print(result["steps"]["research"]["ok"])
print(result["steps"]["research"]["stage"])
"""
        _vm, out, _err = run_program(src)
        self.assertEqual(out, ["true", "check"])

    def test_agent_action_result_propagates(self):
        register_agent("summarize", lambda payload: {"summary": payload["input"]["text"]})
        src = """
goal publish_article {
    step research {
        return { "text": "condensed" }
    }

    step summarize after research {
        action agent "summarize" with {
            input: research
        }
    }
}

let result = run_goal(publish_article)
print(result["steps"]["summarize"]["result"]["summary"])
"""
        _vm, out, _err = run_program(src)
        self.assertEqual(out, ["condensed"])

    def test_memory_actions(self):
        src = """
goal demo {
    step store {
        action memory_put "article_summary" { "value": "done" }
    }

    step fetch after store {
        let x = action memory_get "article_summary"
        return x["value"]
    }
}

let result = run_goal(demo)
print(result["steps"]["store"]["value"])
print(result["steps"]["fetch"])
"""
        _vm, out, _err = run_program(src)
        self.assertEqual(out, ["done", "done"])

    def test_plan_goal_uses_step_names(self):
        src = """
goal demo {
    step a { return 1 }
    step b after a { return a + 1 }
    step c after a { return a * 2 }
}

let plan = plan_goal(demo)
print(plan["goal"])
print(len(plan["parallel_groups"][1]))
"""
        _vm, out, _err = run_program(src)
        self.assertEqual(out, ["demo", "2"])

    def test_resume_goal(self):
        src = """
goal demo {
    state x = 1

    step a {
        x = x + 1
        checkpoint "after_a"
        return x
    }

    step b after a {
        return x
    }
}

let result = run_goal(demo)
"""
        with tempfile.TemporaryDirectory() as td:
            path = os.path.join(td, "goal_resume.nd")
            with open(path, "w", encoding="utf-8") as f:
                f.write(src)
            vm, _out, _err = run_program(src, source_path=path)
            result = vm.globals["result"]
            if hasattr(result, "value"):
                result = result.value
            graph_id = result["graph_id"]
            task_graph._GRAPH_REGISTRY.pop(graph_id, None)
            task_graph._GRAPH_VMS.pop(graph_id, None)

            resumed_vm = lang.VM([], {}, code_locs=[], source_path=None)
            resumed = resumed_vm.builtin_resume_goal(graph_id, "after_a")
            self.assertEqual(resumed["goal"], "demo")
            self.assertEqual(resumed["steps"]["a"], 3)
            self.assertEqual(resumed["steps"]["b"], 3)
            self.assertEqual(resumed["state"]["x"], 3)

    def test_goal_runtime_events(self):
        src = """
goal demo {
    step a {
        action emit "step_started" with { source: "demo" }
        return 1
    }

    step b after a {
        action memory_put "x" a
    }
}

run_goal(demo)
"""
        vm, _out, _err = run_program(src)
        event_types = [event.type for event in vm.event_bus.events()]
        self.assertIn("goal_start", event_types)
        self.assertIn("goal_step_start", event_types)
        self.assertIn("goal_action_start", event_types)
        self.assertIn("goal_action_complete", event_types)
        self.assertIn("goal_complete", event_types)

    def test_goal_api_endpoints(self):
        register_agent("summarize", lambda payload: {"summary": payload["input"]["text"]})
        code = """
goal publish_article {
    step research {
        return { "text": "condensed" }
    }

    step summarize after research {
        action agent "summarize" with {
            input: research
        }
    }
}
"""
        status, payload = self.request("POST", "/goal/run", {"code": code, "filename": "inline.nd"})
        self.assertEqual(status, 200)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["result"]["goal"], "publish_article")
        self.assertEqual(payload["result"]["steps"]["summarize"]["result"]["summary"], "condensed")
        graph_id = payload["result"]["graph_id"]

        status, payload = self.request("POST", "/goal/plan", {"code": code, "filename": "inline.nd"})
        self.assertEqual(status, 200)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["plan"]["goal"], "publish_article")
        self.assertEqual(payload["plan"]["parallel_groups"][1], ["summarize"])

        task_graph._GRAPH_REGISTRY.pop(graph_id, None)
        task_graph._GRAPH_VMS.pop(graph_id, None)
        status, payload = self.request("POST", "/goal/resume", {"graph_id": graph_id})
        self.assertEqual(status, 200)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["result"]["goal"], "publish_article")

    def test_goal_cli_commands(self):
        code = """
goal demo {
    step a { return 1 }
    step b after a { return a + 1 }
}
"""
        with tempfile.TemporaryDirectory() as td:
            path = os.path.join(td, "demo.nd")
            with open(path, "w", encoding="utf-8") as f:
                f.write(code)

            out = io.StringIO()
            with redirect_stdout(out):
                run_exit = lang.main(["nodus", "goal-run", path])
            self.assertEqual(run_exit, 0)
            run_payload = json.loads(out.getvalue().strip())
            self.assertEqual(run_payload["goal"], "demo")
            self.assertEqual(run_payload["steps"]["b"], 2)
            graph_id = run_payload["graph_id"]

            out = io.StringIO()
            with redirect_stdout(out):
                plan_exit = lang.main(["nodus", "goal-plan", path])
            self.assertEqual(plan_exit, 0)
            plan_payload = json.loads(out.getvalue().strip())
            self.assertEqual(plan_payload["parallel_groups"][1], ["b"])

            task_graph._GRAPH_REGISTRY.pop(graph_id, None)
            task_graph._GRAPH_VMS.pop(graph_id, None)
            out = io.StringIO()
            with redirect_stdout(out):
                resume_exit = lang.main(["nodus", "goal-resume", graph_id])
            self.assertEqual(resume_exit, 0)
            resume_payload = json.loads(out.getvalue().strip())
            self.assertEqual(resume_payload["steps"]["b"], 2)


class GoalFrameworkRegistrationTests(unittest.TestCase):
    """#108/#109: run_goal() and resume_goal() must route through WorkflowFrameworkRunner."""

    def _run_goal(self, src: str, td: str):
        from nodus.cli import cli as nodus_cli
        from nodus.tooling.runner import run_goal_code
        path = os.path.join(td, "goal.nd")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(src)
        vm = lang.VM([], {}, code_locs=[], source_path=path)
        with nodus_cli._project_root_context(td):
            result, vm = run_goal_code(vm, src, filename=path, project_root=td, timeout_ms=5000)
        return result, vm, path

    def test_run_goal_creates_framework_run_record(self):
        """run_goal() must register the run in the WorkflowFrameworkRunner store."""
        from nodus_lang_workflow.store import LocalWorkflowStore

        src = """
goal demo {
    step a { return 1 }
    step b after a { return a + 1 }
}
let result = run_goal(demo)
"""
        with tempfile.TemporaryDirectory() as td:
            result, _vm, _path = self._run_goal(src, td)
            self.assertTrue(result.get("ok"), result)
            graph_id = result["result"]["graph_id"]
            store = LocalWorkflowStore(root=os.path.join(td, ".nodus", "workflow_framework"))
            record = store.get_run(graph_id)
            self.assertIsNotNone(record, "run_goal() should create a WorkflowFrameworkRunner record")
            self.assertEqual(record.execution_kind, "goal")
            from nodus_lang_workflow.models import RUN_STATUS_COMPLETED
            self.assertEqual(record.status, RUN_STATUS_COMPLETED)

    def test_resume_goal_routes_through_framework_and_updates_resume_count(self):
        """resume_goal() must go through WorkflowFrameworkRunner and update resume_count."""
        from nodus.cli import cli as nodus_cli
        from nodus_lang_workflow.store import LocalWorkflowStore

        src = """
goal demo {
    state x = 0

    step a {
        x = x + 1
        checkpoint "after_a"
        return x
    }

    step b after a {
        x = x + 1
        return x
    }
}
let result = run_goal(demo)
"""
        with tempfile.TemporaryDirectory() as td:
            result, _vm, path = self._run_goal(src, td)
            self.assertTrue(result.get("ok"), result)
            graph_id = result["result"]["graph_id"]
            task_graph._GRAPH_REGISTRY.pop(graph_id, None)
            task_graph._GRAPH_VMS.pop(graph_id, None)

            resumed_vm = lang.VM([], {}, code_locs=[], source_path=path)
            with nodus_cli._project_root_context(td):
                resumed = resumed_vm.builtin_resume_goal(graph_id, "after_a")
            self.assertTrue(isinstance(resumed, dict) and resumed.get("goal") == "demo", resumed)

            store = LocalWorkflowStore(root=os.path.join(td, ".nodus", "workflow_framework"))
            record = store.get_run(graph_id)
            self.assertIsNotNone(record)
            self.assertEqual(record.resume_count, 1, "resume_goal() must increment resume_count")

    def test_run_goal_execution_kind_is_goal(self):
        """execution_kind in the framework record must be 'goal', not 'workflow'."""
        from nodus_lang_workflow.store import LocalWorkflowStore

        src = """
goal my_task {
    step run { return 42 }
}
let _ = run_goal(my_task)
"""
        with tempfile.TemporaryDirectory() as td:
            result, _vm, _path = self._run_goal(src, td)
            self.assertTrue(result.get("ok"), result)
            graph_id = result["result"]["graph_id"]
            store = LocalWorkflowStore(root=os.path.join(td, ".nodus", "workflow_framework"))
            record = store.get_run(graph_id)
            self.assertIsNotNone(record)
            self.assertEqual(record.execution_kind, "goal")


if __name__ == "__main__":
    unittest.main()
