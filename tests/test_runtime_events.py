import io
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout

import nodus as lang
from nodus.runtime.module_loader import ModuleLoader


def run_program(src: str, source_path: str | None = None):
    _loader = ModuleLoader(project_root=None)
    code, functions, code_locs = _loader.compile_only(
        src,
        module_name=source_path or "<memory>",
    )
    vm = lang.VM(code, functions, code_locs=code_locs, source_path=source_path)
    out_buf = io.StringIO()
    err_buf = io.StringIO()
    with redirect_stdout(out_buf), redirect_stderr(err_buf):
        vm.run()
    return vm, out_buf.getvalue().splitlines(), err_buf.getvalue()


class RuntimeEventTests(unittest.TestCase):
    def test_spawn_event(self):
        src = """
fn worker() {
    yield
}

spawn(coroutine(worker))
run_loop()
"""
        vm, _out, _err = run_program(src, source_path="main.nd")
        types = [event.type for event in vm.event_bus.events()]
        self.assertIn("coroutine_spawn", types)

    def test_yield_event(self):
        src = """
fn worker() {
    yield
}

spawn(coroutine(worker))
run_loop()
"""
        vm, _out, _err = run_program(src, source_path="main.nd")
        types = [event.type for event in vm.event_bus.events()]
        self.assertIn("coroutine_yield", types)

    def test_scheduler_event_order(self):
        src = """
fn worker() {
    yield
}

spawn(coroutine(worker))
run_loop()
"""
        vm, _out, _err = run_program(src, source_path="main.nd")
        types = [event.type for event in vm.event_bus.events() if event.type.startswith("coroutine_")]
        expected = ["coroutine_spawn", "coroutine_resume", "coroutine_yield", "coroutine_resume", "coroutine_complete"]
        self.assertEqual(types[: len(expected)], expected)

    def test_event_clearing(self):
        src = """
fn worker() {
    yield
}

spawn(coroutine(worker))
runtime_clear_events()
"""
        vm, _out, _err = run_program(src, source_path="main.nd")
        types = [event.type for event in vm.event_bus.events()]
        self.assertNotIn("coroutine_spawn", types)

    def test_cli_trace_events(self):
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
                exit_code = lang.main(["nodus", "run", script, "--trace-events"])
            output = buf.getvalue()
            self.assertEqual(exit_code, 0)
            self.assertIn("coroutine_spawn", output)
            self.assertIn("coroutine_resume", output)


if __name__ == "__main__":
    unittest.main()
