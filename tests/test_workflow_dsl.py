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
from nodus.cli import cli as nodus_cli
from nodus.runtime.module_loader import ModuleLoader
from nodus.services.server import run_in_thread
from nodus.orchestration.workflow_lowering import find_workflow_value


def run_program(src: str, source_path: str = "workflow.nd"):
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


class WorkflowDslTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import tempfile as _tempfile
        tmp = _tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        tmp.close()
        cls._wf_store_path = tmp.name
        cls.server, cls.thread = run_in_thread(
            "127.0.0.1", 0, allowed_paths=["."],
            workflow_store_backend="sqlite",
            workflow_store_path=cls._wf_store_path,
        )
        cls.port = cls.server.server_address[1]
        time.sleep(0.05)

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        import os as _os
        try:
            _os.unlink(cls._wf_store_path)
        except OSError:
            pass

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

    # closes: #324
    def test_workflow_composition_routes_to_one_subworkflow(self):
        """#324: a step selects one of several sub-workflows via match +
        run_workflow; only the chosen sub-pipeline runs (workflow composition —
        the documented Nodus idiom for conditional routing over sub-graphs)."""
        src = """
workflow pipe_a {
    step a1 {
        return "a1"
    }
    step a2 after a1 {
        return "a2"
    }
}
workflow pipe_b {
    step b1 {
        return "b1"
    }
}
workflow router {
    step classify {
        return "a"
    }
    step dispatch after classify {
        let sub = match classify {
            "a" => run_workflow(pipe_a),
            _ => run_workflow(pipe_b),
        }
        return sub["steps"]
    }
}

let r = run_workflow(router)
let dispatched = r["steps"]["dispatch"]
print(dispatched["a1"])
print(dispatched["a2"])
"""
        _vm, out, err = run_program(src, "compose.nd")
        self.assertEqual(out, ["a1", "a2"], f"pipe_a should have run; err={err}")
        # pipe_b never ran: its step is absent from the dispatched sub-result.
        dispatched = _vm.globals.get("dispatched")
        self.assertNotIn("b1", dispatched, "the un-taken sub-workflow must not run")

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
        _loader = ModuleLoader(project_root=None)
        code, functions, code_locs = _loader.compile_only(src, module_name="checkpoint_recorded.nd")
        vm = lang.VM(code, functions, code_locs=code_locs, source_path="checkpoint_recorded.nd")
        vm.run()
        result = vm.globals["result"]
        self.assertNotIn("state", result["checkpoints"][0])

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
        _loader = ModuleLoader(project_root=None)
        code, functions, code_locs = _loader.compile_only(src, module_name="rollback.nd")
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
        self.assertEqual(out[0], "2")
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
"""
        with tempfile.TemporaryDirectory() as td:
            path = os.path.join(td, "retry_workflow.nd")
            with open(path, "w", encoding="utf-8") as handle:
                handle.write(src)
            _loader = ModuleLoader(project_root=None)
            code, functions, code_locs = _loader.compile_only(src, module_name=path)
            vm = lang.VM(code, functions, code_locs=code_locs, source_path=path)
            with nodus_cli._project_root_context(td):
                vm.run()
                workflow = find_workflow_value(vm.globals, "demo")
                first = vm.builtin_run_workflow(workflow)
                self.assertEqual(first["status"], "retry_scheduled")
                self.assertEqual(first["retry"]["step"], "flaky")
                self.assertEqual(first["retry"]["attempt"], 1.0)
                time.sleep(0.01)
                resumed = vm.builtin_resume_workflow(first["graph_id"])
            self.assertEqual(resumed["steps"]["flaky"], 5)
            self.assertEqual(resumed["attempts"]["task_1"], 2.0)

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
        _loader = ModuleLoader(project_root=None)
        code, functions, code_locs = _loader.compile_only(src, module_name="resume.nd")
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
            _loader = ModuleLoader(project_root=None)
            code, functions, code_locs = _loader.compile_only(src, module_name=path)
            vm = lang.VM(code, functions, code_locs=code_locs, source_path=path)
            vm.run()
            result = vm.globals["result"]
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

    def test_workflow_wait_returns_waiting_and_resume_continues(self):
        src = """
workflow demo {
    step gate {
        return workflow_wait("approval.granted", "req-1", {kind: "approval"})
    }

    step finish after gate {
        return "done"
    }
}
"""
        with tempfile.TemporaryDirectory() as td:
            path = os.path.join(td, "wait.nd")
            with open(path, "w", encoding="utf-8") as handle:
                handle.write(src)
            _loader = ModuleLoader(project_root=None)
            code, functions, code_locs = _loader.compile_only(src, module_name=path)
            vm = lang.VM(code, functions, code_locs=code_locs, source_path=path)
            with nodus_cli._project_root_context(td):
                vm.run()
                workflow = find_workflow_value(vm.globals, "demo")
                first = vm.builtin_run_workflow(workflow)
                self.assertEqual(first["status"], "waiting")
                self.assertEqual(first["wait"]["event_type"], "approval.granted")
                graph_id = first["graph_id"]
                resumed = vm.builtin_resume_workflow(graph_id)
            self.assertEqual(resumed["steps"]["finish"], "done")

    def test_workflow_resume_payload_is_available_after_wait(self):
        src = """
workflow demo {
    step gate {
        return workflow_wait("approval.granted", "req-2", {kind: "approval"})
    }

    step finish after gate {
        let payload = workflow_resume_payload()
        if (payload == nil) {
            return "missing"
        }
        if (payload["approved"]) {
            return payload["reviewer"]
        }
        return "denied"
    }
}
"""
        with tempfile.TemporaryDirectory() as td:
            path = os.path.join(td, "resume_payload.nd")
            with open(path, "w", encoding="utf-8") as handle:
                handle.write(src)
            _loader = ModuleLoader(project_root=None)
            code, functions, code_locs = _loader.compile_only(src, module_name=path)
            vm = lang.VM(code, functions, code_locs=code_locs, source_path=path)
            with nodus_cli._project_root_context(td):
                vm.run()
                workflow = find_workflow_value(vm.globals, "demo")
                first = vm.builtin_run_workflow(workflow)
                self.assertEqual(first["status"], "waiting")
                graph_id = first["graph_id"]
                resumed = vm.builtin_resume_workflow(
                    graph_id,
                    {"approved": True, "reviewer": "alice"},
                )
        self.assertEqual(resumed["steps"]["finish"], "alice")

    def test_workflow_resume_api_accepts_payload_and_event_metadata(self):
        code = """
workflow demo {
    step gate {
        return workflow_wait("approval.granted", "req-api", {kind: "approval"})
    }

    step finish after gate {
        let payload = workflow_resume_payload()
        return payload["reviewer"]
    }
}
"""
        status, payload = self.request("POST", "/workflow/run", {"code": code, "filename": "wait_api.nd"})
        self.assertEqual(status, 200)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["result"]["status"], "waiting")
        graph_id = payload["result"]["graph_id"]

        status, payload = self.request(
            "POST",
            "/workflow/resume",
            {
                "graph_id": graph_id,
                "resume_payload": {"reviewer": "api-user"},
                "event_type": "approval.granted",
                "correlation_key": "req-api",
            },
        )
        self.assertEqual(status, 200)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["result"]["steps"]["finish"], "api-user")

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
