import io
import unittest
from contextlib import redirect_stderr, redirect_stdout

import nodus as lang
from nodus.runtime.module_loader import ModuleLoader


def run_program(src: str, source_path: str | None = None) -> tuple[list[str], str]:
    vm = lang.VM([], {}, code_locs=[], source_path=source_path)
    _loader = ModuleLoader(project_root=None, vm=vm)
    out_buf = io.StringIO()
    err_buf = io.StringIO()
    with redirect_stdout(out_buf), redirect_stderr(err_buf):
        _loader.load_module_from_source(src, module_name=source_path or "<memory>")
    return out_buf.getvalue().splitlines(), err_buf.getvalue()


class SchedulerTests(unittest.TestCase):
    def test_interleaves_coroutines(self):
        src = """
fn worker(name) {
    print("start " + name)
    yield
    print("resume " + name)
}

let a = coroutine(fn() { worker("A") })
let b = coroutine(fn() { worker("B") })
spawn(a)
spawn(b)
run_loop()
"""
        out, err = run_program(src, source_path="main.nd")
        self.assertEqual(out, ["start A", "start B", "resume A", "resume B"])
        self.assertEqual(err.strip(), "")

    def test_sleep_allows_other_tasks_to_run(self):
        src = """
import "std:async"

fn sleeper() {
    print("wait")
    sleep(50)
    print("done")
}

fn fast() {
    print("fast")
    yield
    print("fast2")
}

let a = coroutine(fn() { sleeper() })
let b = coroutine(fn() { fast() })
spawn(a)
spawn(b)
run_loop()
"""
        out, err = run_program(src, source_path="main.nd")
        self.assertEqual(out, ["wait", "fast", "fast2", "done"])
        self.assertEqual(err.strip(), "")

    def test_error_isolation(self):
        src = """
fn bad() {
    throw "boom"
}

fn good() {
    print("ok")
}

spawn(coroutine(bad))
spawn(coroutine(good))
run_loop()
"""
        out, err = run_program(src, source_path="main.nd")
        self.assertEqual(out, ["ok"])
        self.assertIn("Runtime error", err)
        self.assertIn("boom", err)


if __name__ == "__main__":
    unittest.main()
