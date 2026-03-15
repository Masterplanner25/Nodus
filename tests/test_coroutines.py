import io
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


class CoroutineTests(unittest.TestCase):
    def test_simple_coroutine_yields_sequential_values(self):
        src = """
fn worker() {
    print("start")
    yield 1
    print("resume")
    yield 2
}

let c = coroutine(worker)
print(coroutine_status(c))
print(resume(c))
print(coroutine_status(c))
print(resume(c))
print(coroutine_status(c))
"""
        self.assertEqual(
            run_program(src, source_path="main.nd"),
            ["created", "start", "1.0", "suspended", "resume", "2.0", "suspended"],
        )

    def test_coroutine_finishes_and_cannot_resume_again(self):
        src = """
fn done() {
    return 7
}

let c = coroutine(done)
print(resume(c))
print(coroutine_status(c))
resume(c)
"""
        with self.assertRaises(lang.LangRuntimeError) as cm:
            run_program(src, source_path="main.nd")
        self.assertEqual(cm.exception.kind, "runtime")
        self.assertIn("Cannot resume finished coroutine", str(cm.exception))

    def test_nested_coroutine_resume(self):
        src = """
fn child() {
    yield 1
    yield 2
}

fn parent() {
    let c = coroutine(child)
    yield resume(c)
    yield resume(c)
}

let p = coroutine(parent)
print(resume(p))
print(resume(p))
"""
        self.assertEqual(run_program(src, source_path="main.nd"), ["1.0", "2.0"])

    def test_coroutine_can_resume_child_and_continue(self):
        src = """
fn child() {
    yield 10
    return 20
}

fn parent() {
    let c = coroutine(child)
    let first = resume(c)
    yield first
    let second = resume(c)
    yield second
}

let p = coroutine(parent)
print(resume(p))
print(resume(p))
"""
        self.assertEqual(run_program(src, source_path="main.nd"), ["10.0", "20.0"])

    def test_resuming_running_coroutine_raises(self):
        src = """
let c = nil

fn self_resume() {
    resume(c)
}

c = coroutine(self_resume)
resume(c)
"""
        with self.assertRaises(lang.LangRuntimeError) as cm:
            run_program(src, source_path="main.nd")
        self.assertEqual(cm.exception.kind, "runtime")
        self.assertIn("Cannot resume running coroutine", str(cm.exception))


if __name__ == "__main__":
    unittest.main()
