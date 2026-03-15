import io
import tempfile
import unittest
from contextlib import redirect_stdout

import nodus as lang
from nodus.runtime.module_loader import ModuleLoader


def run_program(src: str, source_path: str | None = None) -> list[str]:
    _loader = ModuleLoader(project_root=None)
    code, functions, code_locs = _loader.compile_only(
        src,
        module_name=source_path or "<memory>",
    )
    vm = lang.VM(code, functions, code_locs=code_locs, source_path=source_path)
    buf = io.StringIO()
    with redirect_stdout(buf):
        vm.run()
    return buf.getvalue().splitlines()


class RuntimeStatsTests(unittest.TestCase):
    def test_task_tracking_counts(self):
        src = """
fn worker() {
    yield
}

let a = coroutine(worker)
let b = coroutine(worker)
spawn(a)
spawn(b)
print(len(runtime_tasks()))
run_loop()
let stats = runtime_scheduler_stats()
print(stats["completed"])
"""
        self.assertEqual(run_program(src, source_path="main.nd"), ["2.0", "2.0"])

    def test_resume_count_increments(self):
        src = """
fn worker() {
    yield
    yield
}

let c = coroutine(worker)
spawn(c)
let tasks = runtime_tasks()
let id = tasks[0]["id"]
run_loop()
let info = runtime_task(id)
print(info["resumes"])
"""
        self.assertEqual(run_program(src, source_path="main.nd"), ["3.0"])

    def test_scheduler_sleeping_counts(self):
        src = """
fn sleeper() {
    sleep(50)
}

fn inspector() {
    yield
    let stats = runtime_scheduler_stats()
    print(stats["sleeping"])
}

spawn(coroutine(sleeper))
spawn(coroutine(inspector))
run_loop()
"""
        self.assertEqual(run_program(src, source_path="main.nd"), ["1.0"])

    def test_cli_trace_scheduler(self):
        with tempfile.TemporaryDirectory() as td:
            script = f"{td}/trace.nd"
            with open(script, "w", encoding="utf-8") as f:
                f.write(
                    "fn worker() { yield }\n"
                    "spawn(coroutine(worker))\n"
                    "run_loop()\n"
                )
            buf = io.StringIO()
            with redirect_stdout(buf):
                exit_code = lang.main(["nodus", "run", script, "--trace-scheduler"])
            output = buf.getvalue()
            self.assertEqual(exit_code, 0)
            self.assertIn("spawn coroutine #", output)
            self.assertIn("resume coroutine #", output)


if __name__ == "__main__":
    unittest.main()
