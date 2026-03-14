import io
import unittest
from contextlib import redirect_stderr, redirect_stdout

import nodus as lang
from nodus.tooling.runner import run_in_vm
import json
import os
from nodus.services.server import run_in_thread
import threading
import http.client
import time
from nodus.orchestration.task_graph import set_default_dispatcher
from nodus.runtime.runtime_events import RuntimeEventBus


def run_program(src: str, source_path: str | None = None):
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


class TaskGraphTests(unittest.TestCase):
    def _poll_job(self, worker_manager, worker_id: str, timeout: float = 2.0):
        deadline = time.time() + timeout
        while time.time() < deadline:
            job = worker_manager.poll(worker_id)
            if job.get("job_id"):
                return job
            time.sleep(0.01)
        return {"job_id": None}

    def test_dependency_ordering(self):
        src = """
let A = task(fn() { return 2 }, nil)
let B = task(fn(x) { return x * 3 }, A)
let C = task(fn(x) { return x + 1 }, B)

let result = run_graph([A, B, C])
print(result["tasks"]["task_1"])
print(result["tasks"]["task_2"])
print(result["tasks"]["task_3"])
"""
        _vm, out, err = run_program(src, source_path="main.nd")
        self.assertEqual(out, ["2.0", "6.0", "7.0"])
        self.assertEqual(err.strip(), "")

    def test_parallel_execution(self):
        src = """
let A = task(fn() { return 2 }, nil)
let B = task(fn() { return 3 }, nil)
let C = task(fn(x, y) { return x + y }, [A, B])

run_graph([A, B, C])
"""
        vm, _out, _err = run_program(src, source_path="main.nd")
        starts = [e.name for e in vm.event_bus.events() if e.type == "task_start"]
        self.assertEqual(starts[0:2], ["task_1", "task_2"])
        self.assertEqual(starts[2], "task_3")

    def test_error_propagation(self):
        src = """
let A = task(fn() { return 2 }, nil)
let B = task(fn(x) { throw "boom" }, A)
let C = task(fn(x) { return x + 1 }, B)

let result = run_graph([A, B, C])
print(result["failed"])
"""
        _vm, out, _err = run_program(src, source_path="main.nd")
        self.assertEqual(out, ["[\"task_2\"]"])

    def test_task_yield(self):
        src = """
let A = task(fn() {
    yield 0
    return 2
}, nil)
let B = task(fn(x) { return x + 1 }, A)
let result = run_graph([A, B])
print(result["tasks"]["task_2"])
"""
        _vm, out, err = run_program(src, source_path="main.nd")
        self.assertEqual(out, ["3.0"])
        self.assertEqual(err.strip(), "")

    def test_task_timeout(self):
        src = """
let A = task(fn() {
    while (true) { yield 0 }
    return 1
}, { "deps": nil, "timeout_ms": 10 })
let result = run_graph([A])
print(result["failed"])
"""
        _vm, out, _err = run_program(src, source_path="main.nd")
        self.assertEqual(out, ["[\"task_1\"]"])

    def test_task_retry_success(self):
        src = """
let state = { "count": 0 }
let A = task(fn() {
    if (state["count"] == 0) {
        state["count"] = 1
        throw "fail"
    }
    return 5
}, { "retries": 2, "retry_delay_ms": 5 })
let result = run_graph([A])
print(result["tasks"]["task_1"])
print(result["attempts"]["task_1"])
"""
        _vm, out, _err = run_program(src, source_path="main.nd")
        self.assertEqual(out, ["5.0", "2.0"])

    def test_task_retry_exhausted(self):
        src = """
let A = task(fn() {
    throw "fail"
}, { "retries": 1, "retry_delay_ms": 1 })
let result = run_graph([A])
print(result["failed"])
print(result["attempts"]["task_1"])
"""
        _vm, out, _err = run_program(src, source_path="main.nd")
        self.assertEqual(out, ["[\"task_1\"]", "2.0"])

    def test_task_retry_delay(self):
        src = """
let state = { "count": 0 }
let A = task(fn() {
    if (state["count"] == 0) {
        state["count"] = 1
        throw "fail"
    }
    return 5
}, { "retries": 1, "retry_delay_ms": 50 })
let result = run_graph([A])
let timing = result["timings"]["task_1"]
print(timing["finished_at"] - timing["started_at"])
"""
        _vm, out, _err = run_program(src, source_path="main.nd")
        self.assertTrue(float(out[0]) >= 50.0)

    def test_task_cache_hit(self):
        src = """
let A = task(fn() { return 5 }, { "cache": true })
let result1 = run_graph([A])
let result2 = run_graph([A])
print(result1["tasks"]["task_1"])
print(result2["cache_hits"][0])
"""
        _vm, out, _err = run_program(src, source_path="main.nd")
        self.assertEqual(out, ["5.0", "task_1"])

    def test_task_cache_disabled(self):
        src = """
let state = { "count": 0 }
let A = task(fn() { state["count"] = state["count"] + 1 return state["count"] }, nil)
let result1 = run_graph([A])
let result2 = run_graph([A])
print(result1["tasks"]["task_1"])
print(result2["tasks"]["task_1"])
"""
        _vm, out, _err = run_program(src, source_path="main.nd")
        self.assertEqual(out, ["1.0", "2.0"])

    def test_task_cache_with_dependencies(self):
        src = """
let A = task(fn() { return 2 }, { "cache": true })
let B = task(fn(x) { return x + 3 }, { "deps": A, "cache": true })
let result1 = run_graph([A, B])
let result2 = run_graph([A, B])
print(result1["tasks"]["task_2"])
print(result2["cache_hits"][0])
"""
        _vm, out, _err = run_program(src, source_path="main.nd")
        self.assertEqual(out, ["5.0", "task_1"])

    def test_graph_plan_linear(self):
        src = """
let A = task(fn() { return 2 }, nil)
let B = task(fn(x) { return x * 3 }, A)
let C = task(fn(x) { return x + 1 }, B)
let plan = plan_graph([A, B, C])
print(len(plan["levels"]))
"""
        _vm, out, _err = run_program(src, source_path="main.nd")
        self.assertEqual(out, ["3.0"])

    def test_graph_plan_branching(self):
        src = """
let A = task(fn() { return 1 }, nil)
let B = task(fn(x) { return x + 1 }, A)
let C = task(fn(x) { return x * 2 }, A)
let plan = plan_graph([A, B, C])
print(len(plan["parallel_groups"][1]))
"""
        _vm, out, _err = run_program(src, source_path="main.nd")
        self.assertEqual(out, ["2.0"])

    def test_graph_persistence_and_resume(self):
        src = """
let state = { "count": 0 }
let A = task(fn() { state["count"] = state["count"] + 1 return 2 }, nil)
let B = task(fn(x) { return x + 1 }, A)
let plan = plan_graph([A, B])
"""
        _ast, code, functions, code_locs = lang.compile_source(
            src,
            source_path="main.nd",
            import_state={"loaded": set(), "loading": set(), "exports": {}, "modules": {}, "module_ids": {}, "project_root": None},
        )
        vm = lang.VM(code, functions, code_locs=code_locs, source_path="main.nd")
        vm.run()
        graph_id = None
        if getattr(vm, "last_graph_plan", None):
            graph_id = vm.last_graph_plan.get("graph_id")
        if graph_id is None:
            plan_val = vm.globals.get("plan")
            if hasattr(plan_val, "value"):
                plan_val = plan_val.value
            graph_id = plan_val.get("graph_id") if isinstance(plan_val, dict) else None
        if graph_id is None:
            graph_dir = os.path.join(".nodus", "graphs")
            if os.path.isdir(graph_dir):
                files = [f for f in os.listdir(graph_dir) if f.endswith(".json")]
                if files:
                    files.sort()
                    graph_id = files[-1].rsplit(".", 1)[0]
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
        result = vm.builtin_resume_graph(graph_id)
        self.assertEqual(result["tasks"]["task_2"], 3)

    def test_worker_execution(self):
        from nodus.services.server import WorkerManager
        worker_manager = WorkerManager()
        set_default_dispatcher(worker_manager)
        worker_id = worker_manager.register()

        src = """
let A = task(fn() { return 5 }, nil)
let result = run_graph([A])
print(result["tasks"]["task_1"])
"""
        _ast, code, functions, code_locs = lang.compile_source(
            src,
            source_path="main.nd",
            import_state={"loaded": set(), "loading": set(), "exports": {}, "modules": {}, "module_ids": {}, "project_root": None},
        )
        vm = lang.VM(code, functions, code_locs=code_locs, source_path="main.nd")
        vm.worker_dispatcher = worker_manager

        out_buf = io.StringIO()
        err_buf = io.StringIO()

        def run_graph():
            with redirect_stdout(out_buf), redirect_stderr(err_buf):
                vm.run()

        t = threading.Thread(target=run_graph)
        t.start()
        job = None
        for _ in range(100):
            job = worker_manager.poll(worker_id)
            if job.get("job_id"):
                break
            time.sleep(0.05)
        self.assertIsNotNone(job["job_id"])
        worker_manager.result(worker_id, job["job_id"], "execute")
        t.join(timeout=2)
        self.assertFalse(t.is_alive())

    def test_worker_capability_gpu_only(self):
        from nodus.services.server import WorkerManager
        worker_manager = WorkerManager()
        set_default_dispatcher(worker_manager)
        cpu_worker = worker_manager.register(["cpu"])
        gpu_worker = worker_manager.register(["gpu"])

        src = """
let A = task(fn() { return 1 }, { "worker": "gpu" })
let B = task(fn() { return 2 }, { "worker": "cpu" })
let result = run_graph([A, B])
print(result["tasks"]["task_1"])
print(result["tasks"]["task_2"])
"""
        _ast, code, functions, code_locs = lang.compile_source(
            src,
            source_path="main.nd",
            import_state={"loaded": set(), "loading": set(), "exports": {}, "modules": {}, "module_ids": {}, "project_root": None},
        )
        vm = lang.VM(code, functions, code_locs=code_locs, source_path="main.nd")
        vm.worker_dispatcher = worker_manager

        def run_graph():
            vm.run()

        t = threading.Thread(target=run_graph)
        t.start()

        cpu_job = self._poll_job(worker_manager, cpu_worker)
        self.assertIsNotNone(cpu_job.get("job_id"))
        self.assertEqual(cpu_job["task_id"], "task_2")
        worker_manager.result(cpu_worker, cpu_job["job_id"], "execute")

        gpu_job = self._poll_job(worker_manager, gpu_worker)
        self.assertIsNotNone(gpu_job.get("job_id"))
        self.assertEqual(gpu_job["task_id"], "task_1")
        worker_manager.result(gpu_worker, gpu_job["job_id"], "execute")

        t.join(timeout=2)
        self.assertFalse(t.is_alive())

    def test_worker_capability_cpu_dispatch(self):
        from nodus.services.server import WorkerManager
        worker_manager = WorkerManager()
        set_default_dispatcher(worker_manager)
        cpu_worker = worker_manager.register(["cpu"])

        src = """
let A = task(fn() { return 3 }, { "worker": "cpu" })
let result = run_graph([A])
print(result["tasks"]["task_1"])
"""
        _ast, code, functions, code_locs = lang.compile_source(
            src,
            source_path="main.nd",
            import_state={"loaded": set(), "loading": set(), "exports": {}, "modules": {}, "module_ids": {}, "project_root": None},
        )
        vm = lang.VM(code, functions, code_locs=code_locs, source_path="main.nd")
        vm.worker_dispatcher = worker_manager

        t = threading.Thread(target=vm.run)
        t.start()
        job = self._poll_job(worker_manager, cpu_worker)
        self.assertIsNotNone(job.get("job_id"))
        self.assertEqual(job["task_id"], "task_1")
        worker_manager.result(cpu_worker, job["job_id"], "execute")
        t.join(timeout=2)
        self.assertFalse(t.is_alive())

    def test_worker_capability_fallback_dispatch(self):
        from nodus.services.server import WorkerManager
        worker_manager = WorkerManager()
        set_default_dispatcher(worker_manager)
        gpu_worker = worker_manager.register(["gpu"])

        src = """
let A = task(fn() { return 4 }, nil)
let result = run_graph([A])
print(result["tasks"]["task_1"])
"""
        _ast, code, functions, code_locs = lang.compile_source(
            src,
            source_path="main.nd",
            import_state={"loaded": set(), "loading": set(), "exports": {}, "modules": {}, "module_ids": {}, "project_root": None},
        )
        vm = lang.VM(code, functions, code_locs=code_locs, source_path="main.nd")
        vm.worker_dispatcher = worker_manager

        t = threading.Thread(target=vm.run)
        t.start()
        job = self._poll_job(worker_manager, gpu_worker)
        self.assertIsNotNone(job.get("job_id"))
        self.assertEqual(job["task_id"], "task_1")
        worker_manager.result(gpu_worker, job["job_id"], "execute")
        t.join(timeout=2)
        self.assertFalse(t.is_alive())

    def test_worker_capability_missing(self):
        from nodus.services.server import WorkerManager
        worker_manager = WorkerManager()
        set_default_dispatcher(worker_manager)
        _cpu_worker = worker_manager.register(["cpu"])

        src = """
let A = task(fn() { return 9 }, { "worker": "gpu", "worker_timeout_ms": 50 })
let result = run_graph([A])
print(result["failed"])
print(result["error"])
"""
        _ast, code, functions, code_locs = lang.compile_source(
            src,
            source_path="main.nd",
            import_state={"loaded": set(), "loading": set(), "exports": {}, "modules": {}, "module_ids": {}, "project_root": None},
        )
        vm = lang.VM(code, functions, code_locs=code_locs, source_path="main.nd")
        vm.worker_dispatcher = worker_manager
        out_buf = io.StringIO()
        err_buf = io.StringIO()
        with redirect_stdout(out_buf), redirect_stderr(err_buf):
            vm.run()
        out = out_buf.getvalue().splitlines()
        self.assertEqual(out[0], "[\"task_1\"]")
        self.assertIn("capability: gpu", out[1])
        events = [e for e in vm.event_bus.events() if e.type == "task_worker_timeout"]
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].name, "task_1")
        self.assertEqual(events[0].data.get("worker"), "gpu")
        self.assertEqual(events[0].data.get("timeout_ms"), 50.0)

    def test_worker_heartbeat_updates_health(self):
        from nodus.services.server import WorkerManager
        worker_manager = WorkerManager()
        worker_manager.event_bus = RuntimeEventBus()
        worker_manager._worker_heartbeat_timeout_ms = 30
        worker_id = worker_manager.register(["cpu"])
        time.sleep(0.02)
        self.assertEqual(worker_manager.heartbeat(worker_id), {"ok": True})
        time.sleep(0.02)
        worker_manager.poll(worker_id)
        self.assertIn(worker_id, worker_manager._workers)
        dead_events = [e for e in worker_manager.event_bus.events() if e.type == "worker_dead"]
        self.assertEqual(dead_events, [])

    def test_worker_death_detection(self):
        from nodus.services.server import WorkerManager
        worker_manager = WorkerManager()
        worker_manager.event_bus = RuntimeEventBus()
        worker_manager._worker_heartbeat_timeout_ms = 10
        worker_id = worker_manager.register(["cpu"])
        time.sleep(0.02)
        worker_manager.poll(worker_id)
        self.assertNotIn(worker_id, worker_manager._workers)
        dead_events = [e for e in worker_manager.event_bus.events() if e.type == "worker_dead"]
        self.assertEqual(len(dead_events), 1)
        self.assertEqual(dead_events[0].data.get("worker_id"), worker_id)

    def test_task_reassignment_after_worker_failure(self):
        from nodus.services.server import WorkerManager
        worker_manager = WorkerManager()
        worker_manager.event_bus = RuntimeEventBus()
        worker_manager._worker_heartbeat_timeout_ms = 20
        set_default_dispatcher(worker_manager)
        worker_a = worker_manager.register(["cpu"])
        worker_b = worker_manager.register(["cpu"])

        src = """
let A = task(fn() { return 10 }, { "worker": "cpu", "worker_timeout_ms": 100 })
let result = run_graph([A])
print(result["tasks"]["task_1"])
"""
        _ast, code, functions, code_locs = lang.compile_source(
            src,
            source_path="main.nd",
            import_state={"loaded": set(), "loading": set(), "exports": {}, "modules": {}, "module_ids": {}, "project_root": None},
        )
        vm = lang.VM(code, functions, code_locs=code_locs, source_path="main.nd")
        vm.worker_dispatcher = worker_manager

        t = threading.Thread(target=vm.run)
        t.start()

        job_a = self._poll_job(worker_manager, worker_a)
        self.assertIsNotNone(job_a.get("job_id"))
        worker_manager._worker_last_seen[worker_a] = time.monotonic() - 1.0
        worker_manager.poll(worker_b)

        job_b = self._poll_job(worker_manager, worker_b)
        self.assertEqual(job_b.get("job_id"), job_a.get("job_id"))
        worker_manager.result(worker_b, job_b["job_id"], "execute")

        t.join(timeout=2)
        self.assertFalse(t.is_alive())

        requeued = [e for e in worker_manager.event_bus.events() if e.type == "task_requeued"]
        self.assertEqual(len(requeued), 1)
        self.assertEqual(requeued[0].data.get("task_id"), "task_1")

    def test_worker_death_detected_by_sweeper(self):
        from nodus.services.server import RuntimeService
        service = RuntimeService()
        service.workers.event_bus = RuntimeEventBus()
        service.workers._worker_heartbeat_timeout_ms = 10
        worker_id = service.workers.register(["cpu"])
        dead_event = None
        deadline = time.time() + 0.5
        while time.time() < deadline:
            dead_events = [e for e in service.workers.event_bus.events() if e.type == "worker_dead"]
            if dead_events:
                dead_event = dead_events[0]
                break
            time.sleep(0.01)
        self.assertIsNotNone(dead_event)
        self.assertEqual(dead_event.data.get("worker_id"), worker_id)


if __name__ == "__main__":
    unittest.main()
