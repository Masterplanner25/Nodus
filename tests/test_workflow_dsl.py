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
from nodus.services.server import run_in_thread
from nodus.orchestration.workflow_lowering import find_workflow_value


def run_program(src: str, source_path: str = "workflow.nd"):
    _ast, code, functions, code_locs = lang.compile_source(
        src,
        source_path=source_path,
        import_state={"loaded": set(), "loading": set(), "exports": {}, "modules": {}, "module_ids": {}, "project_root": None},
    )
    vm = lang.VM(code, functions, code_locs=code_locs, source_path=source_path)
    out_buf = io.StringIO()
    err_buf = io.StringIO()
    with redirect_stdout(out_buf), redirect_stderr(err_buf):
        vm.run()
    return vm, out_buf.getvalue().splitlines(), err_buf.getvalue()


class WorkflowDslTests(unittest.TestCase):
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

    def test_linear_workflow(self):
        src = """
workflow demo {
    step a {
        return 1
    }

    step b after a {
        return a + 1
    }
}

let result = run_workflow(demo)
print(result["steps"]["a"])
print(result["steps"]["b"])
"""
        _vm, out, err = run_program(src)
        self.assertEqual(out, ["1.0", "2.0"])
        self.assertEqual(err.strip(), "")

    def test_workflow_state_initialization(self):
        src = """
workflow demo {
    state x = 1

    step a {
        return x
    }
}

let result = run_workflow(demo)
print(result["steps"]["a"])
print(result["state"]["x"])
"""
        _vm, out, err = run_program(src)
        self.assertEqual(out, ["1.0", "1.0"])
        self.assertEqual(err.strip(), "")

    def test_workflow_state_mutation(self):
        src = """
workflow demo {
    state x = 1

    step a {
        x = x + 1
        return x
    }

    step b after a {
        return x
    }
}

let result = run_workflow(demo)
print(result["steps"]["b"])
print(result["state"]["x"])
"""
        _vm, out, err = run_program(src)
        self.assertEqual(out, ["2.0", "2.0"])
        self.assertEqual(err.strip(), "")

    def test_workflow_checkpoint_recorded(self):
        src = """
workflow demo {
    state x = 1

    step a {
        checkpoint "after_a"
        return x
    }
}

let result = run_workflow(demo)
print(result["checkpoints"][0]["label"])
print(result["checkpoints"][0]["step"])
"""
        _vm, out, err = run_program(src)
        self.assertEqual(out, ["after_a", "a"])
        self.assertEqual(err.strip(), "")

    def test_workflow_checkpoint_rollback(self):
        src = """
workflow demo {
    state x = 0

    step a {
        x = x + 1
        checkpoint "after_a"
        return x
    }

    step b after a {
        return x
    }
}
"""
        _ast, code, functions, code_locs = lang.compile_source(
            src,
            source_path="rollback.nd",
            import_state={"loaded": set(), "loading": set(), "exports": {}, "modules": {}, "module_ids": {}, "project_root": None},
        )
        vm = lang.VM(code, functions, code_locs=code_locs, source_path="rollback.nd")
        vm.run()
        workflow = find_workflow_value(vm.globals, "demo")
        first = vm.builtin_run_workflow(workflow)
        graph_id = first["graph_id"]
        resumed = vm.builtin_resume_workflow(graph_id, "after_a")
        self.assertEqual(resumed["steps"]["a"], 2)
        self.assertEqual(resumed["steps"]["b"], 2)
        self.assertEqual(resumed["state"]["x"], 2)

    def test_branching_workflow_plan_uses_step_names(self):
        src = """
workflow demo {
    step a { return 1 }
    step b after a { return a + 1 }
    step c after a { return a * 2 }
}

let plan = plan_workflow(demo)
print(len(plan["parallel_groups"][1]))
print(plan["parallel_groups"][1][0] == "b" || plan["parallel_groups"][1][1] == "b")
"""
        _vm, out, _err = run_program(src)
        self.assertEqual(out[0], "2.0")
        self.assertEqual(out[1], "true")

    def test_merge_workflow_injects_dependency_values(self):
        src = """
workflow demo {
    step a { return 1 }
    step b { return 2 }
    step c after a, b {
        return a + b
    }
}

let result = run_workflow(demo)
print(result["steps"]["c"])
"""
        _vm, out, _err = run_program(src)
        self.assertEqual(out, ["3.0"])

    def test_workflow_step_options_use_existing_retries(self):
        src = """
let state = { "count": 0 }

workflow demo {
    step flaky with { retries: 2, retry_delay_ms: 1 } {
        if (state["count"] == 0) {
            state["count"] = 1
            throw "fail"
        }
        return 5
    }
}

let result = run_workflow(demo)
print(result["steps"]["flaky"])
print(result["attempts"]["task_1"])
"""
        _vm, out, _err = run_program(src)
        self.assertEqual(out, ["5.0", "2.0"])

    def test_workflow_resume(self):
        src = """
workflow demo {
    state x = 1
    step a {
        x = x + 1
        return x
    }
    step b after a { return x }
}
"""
        _ast, code, functions, code_locs = lang.compile_source(
            src,
            source_path="resume.nd",
            import_state={"loaded": set(), "loading": set(), "exports": {}, "modules": {}, "module_ids": {}, "project_root": None},
        )
        vm = lang.VM(code, functions, code_locs=code_locs, source_path="resume.nd")
        vm.run()
        workflow = find_workflow_value(vm.globals, "demo")
        first = vm.builtin_run_workflow(workflow)
        graph_id = first["graph_id"]
        path = os.path.join(".nodus", "graphs", f"{graph_id}.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(
                {
                    "graph_id": graph_id,
                    "status": "running",
                    "metadata": {
                        "workflow_name": "demo",
                        "step_to_task": {"a": "task_1", "b": "task_2"},
                        "task_to_step": {"task_1": "a", "task_2": "b"},
                    },
                    "workflow_state": {"x": 2},
                    "checkpoints": [{"label": "after_a", "step": "a", "timestamp": 1, "state": {"x": 2}}],
                    "tasks": {
                        "task_1": {"state": "completed", "result": 2, "attempts": 1, "step_name": "a"},
                        "task_2": {"state": "pending", "attempts": 0, "step_name": "b"},
                    },
                },
                f,
            )
        resumed = vm.builtin_resume_workflow(graph_id, "after_a")
        self.assertEqual(resumed["steps"]["b"], 3)
        self.assertEqual(resumed["state"]["x"], 3)

    def test_workflow_resume_rebuilds_from_persisted_metadata(self):
        src = """
workflow demo {
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

let result = run_workflow(demo)
"""
        with tempfile.TemporaryDirectory() as td:
            path = os.path.join(td, "rebuild.nd")
            with open(path, "w", encoding="utf-8") as f:
                f.write(src)
            _ast, code, functions, code_locs = lang.compile_source(
                src,
                source_path=path,
                import_state={"loaded": set(), "loading": set(), "exports": {}, "modules": {}, "module_ids": {}, "project_root": None},
            )
            vm = lang.VM(code, functions, code_locs=code_locs, source_path=path)
            vm.run()
            result = vm.globals["__mod0__result"]
            if hasattr(result, "value"):
                result = result.value
            graph_id = result["graph_id"]
            task_graph._GRAPH_REGISTRY.pop(graph_id, None)
            task_graph._GRAPH_VMS.pop(graph_id, None)

            resumed_vm = lang.VM([], {}, code_locs=[], source_path=None)
            resumed = resumed_vm.builtin_resume_workflow(graph_id, "after_a")
            self.assertEqual(resumed["steps"]["a"], 3)
            self.assertEqual(resumed["steps"]["b"], 3)
            self.assertEqual(resumed["state"]["x"], 3)

    def test_workflow_runtime_events(self):
        src = """
workflow demo {
    step a { return 1 }
    step b after a { return a + 1 }
}

run_workflow(demo)
"""
        vm, _out, _err = run_program(src)
        event_types = [event.type for event in vm.event_bus.events()]
        self.assertIn("workflow_start", event_types)
        self.assertIn("workflow_step_start", event_types)
        self.assertIn("workflow_step_complete", event_types)
        self.assertIn("workflow_complete", event_types)

    def test_workflow_api_endpoints(self):
        code = """
workflow demo {
    state x = 1
    step a {
        checkpoint "after_a"
        return x
    }
    step b after a { return a + 1 }
}
"""
        status, payload = self.request("POST", "/workflow/run", {"code": code, "filename": "inline.nd"})
        self.assertEqual(status, 200)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["result"]["steps"]["b"], 2)
        self.assertEqual(payload["result"]["state"]["x"], 1)
        self.assertEqual(payload["result"]["checkpoints"][0]["label"], "after_a")
        graph_id = payload["result"]["graph_id"]

        status, payload = self.request("POST", "/workflow/plan", {"code": code, "filename": "inline.nd"})
        self.assertEqual(status, 200)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["plan"]["parallel_groups"][1], ["b"])

        status, payload = self.request("GET", f"/workflow/checkpoints/{graph_id}")
        self.assertEqual(status, 200)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["checkpoints"][0]["label"], "after_a")

        task_graph._GRAPH_REGISTRY.pop(graph_id, None)
        task_graph._GRAPH_VMS.pop(graph_id, None)
        status, payload = self.request("POST", "/workflow/resume", {"graph_id": graph_id, "checkpoint": "after_a"})
        self.assertEqual(status, 200)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["result"]["state"]["x"], 1)
        self.assertEqual(payload["result"]["checkpoints"][0]["label"], "after_a")
        self.assertEqual(payload["result"]["steps"]["a"], 1)
        self.assertEqual(payload["result"]["steps"]["b"], 2)

    def test_workflow_cli_commands(self):
        code = """
workflow demo {
    state x = 1
    step a {
        checkpoint "after_a"
        return x
    }
    step b after a { return a + 1 }
}
"""
        with tempfile.TemporaryDirectory() as td:
            path = os.path.join(td, "demo.nd")
            with open(path, "w", encoding="utf-8") as f:
                f.write(code)

            out = io.StringIO()
            with redirect_stdout(out):
                run_exit = lang.main(["nodus", "workflow-run", path])
            self.assertEqual(run_exit, 0)
            run_payload = json.loads(out.getvalue().strip())
            self.assertEqual(run_payload["steps"]["b"], 2)
            graph_id = run_payload["graph_id"]

            out = io.StringIO()
            with redirect_stdout(out):
                plan_exit = lang.main(["nodus", "workflow-plan", path])
            self.assertEqual(plan_exit, 0)
            plan_payload = json.loads(out.getvalue().strip())
            self.assertEqual(plan_payload["parallel_groups"][1], ["b"])

            out = io.StringIO()
            with redirect_stdout(out):
                checkpoints_exit = lang.main(["nodus", "workflow-checkpoints", graph_id])
            self.assertEqual(checkpoints_exit, 0)
            checkpoints_payload = json.loads(out.getvalue().strip())
            self.assertEqual(checkpoints_payload[0]["label"], "after_a")

            task_graph._GRAPH_REGISTRY.pop(graph_id, None)
            task_graph._GRAPH_VMS.pop(graph_id, None)
            out = io.StringIO()
            with redirect_stdout(out):
                resume_exit = lang.main(["nodus", "workflow-resume", graph_id, "--checkpoint", "after_a"])
            self.assertEqual(resume_exit, 0)
            resume_payload = json.loads(out.getvalue().strip())
            self.assertEqual(resume_payload["steps"]["b"], 2)


if __name__ == "__main__":
    unittest.main()
