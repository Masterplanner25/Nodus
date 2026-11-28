"""Closed-issue test for #1021: `run_loop()` from library code is refused.

`run_loop()` drains the scheduler's whole ready deque, and the VM chain shares
one, so a library that calls it runs every coroutine its caller spawned and had
not started. Decision D4 of `docs/governance/V6_0_PLAN.md` made that the
cohort's seventh flip: a `StagedFlipWarning` in 5.21.0, refused since 6.0.0.

"A library" is code from any module but the program's entry file, and there
are three ways to be running it. Each looks different from inside the VM:

- a module function called outside a coroutine runs on a detached child VM;
- one called inside a coroutine runs on the caller's VM, its context swapped in;
- an imported module's top level runs on the loader's VM, before the program's.

A refusal stops the program, so each route gets a program of its own. A closure
the program hands to a library is the program's code on both call routes, and
is not refused; neither is any use in the entry file.

`std:async.parallel` and `series` were themselves instances. They drive with
`__settle(task)`, which is `wait(task)` without claiming the outcome, so their
documented contract holds: nil back, a failing task reported as before, the
other tasks still run.

Plain `nodus check` reports every `run_loop()` call in an imported file as an
error, because the scan is exact: each one fails whenever it runs.
"""
import os
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, "C:/dev/Coding Language/src")

from nodus.runtime.embedding import NodusRuntime  # noqa: E402

_REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

_LIB = (
    "export fn drive() {\n"          # 1
    "    run_loop()\n"               # 2  a module function
    "    return 1\n"                 # 3
    "}\n"                            # 4
    "export fn call_back(f) {\n"     # 5
    "    return f()\n"               # 6
    "}\n"                            # 7
)

_LIB_TOP = (
    'print("lib top level")\n'       # 1
    "run_loop()\n"                   # 2  an import's top level
)

#: One program per library route: the library, the line in it that is refused,
#: and whether the refusal fails the program. Inside a spawned coroutine it fails
#: that coroutine, which is reported and does not stop the program -- the same as
#: any error a spawned task raises.
_ROUTES = {
    "module function at top level": (
        "lib.nd", 'import "./lib.nd" as lib\nlib.drive()\nprint("unreached")\n', 2, True),
    "module function in a coroutine": (
        "lib.nd",
        'import "./lib.nd" as lib\nspawn(coroutine(fn() { lib.drive() }))\nrun_loop()\n',
        2, False),
    "an import's top level": (
        "libtop.nd", 'import "./libtop.nd" as t\nprint("unreached")\n', 2, True),
}

#: Every use that is the program's own: none of these may be refused.
_ALLOWED = (
    'import "./lib.nd" as lib\n'
    "run_loop()\n"
    "fn own() { run_loop() }\n"
    "own()\n"
    "spawn(coroutine(fn() { run_loop() }))\n"
    "run_loop()\n"
    "lib.call_back(fn() { run_loop() })\n"
    "spawn(coroutine(fn() { lib.call_back(fn() { run_loop() }) }))\n"
    "run_loop()\n"
    'print("done")\n'
)

_PARALLEL = (
    'import "std:async" as async\n'
    "let r = async.parallel([\n"
    '    fn() { print("a") },\n'
    '    fn() { throw "boom" },\n'
    '    fn() { print("c") }\n'
    "])\n"
    'print("parallel returned \\(r)")\n'
    'async.series([fn() { async.sleep(10); print("s1") }, fn() { print("s2") }])\n'
    "let t = spawn(coroutine(fn() {\n"
    # The failing task is first and still sleeping when parallel parks on it,
    # so the park path is the one that meets the failure.
    '    async.parallel([fn() { async.sleep(5); throw "inner" },\n'
    '                    fn() { async.sleep(10); print("slow") }, fn() { print("fast") }])\n'
    '    return "outer"\n'
    "}))\n"
    'print("wait -> \\(wait(t))")\n'
)

_REFUSED = "run_loop() was called from library code"


def _write(directory, name, text):
    path = os.path.join(directory, name)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)
    return path


def _project(d):
    _write(d, "nodus.toml", '[project]\nname = "d4"\n')
    _write(d, "lib.nd", _LIB)
    _write(d, "libtop.nd", _LIB_TOP)


def _nodus(d, *args):
    env = dict(os.environ, PYTHONPATH=os.path.join(_REPO, "src"),
               NODUS_WORKFLOW_STORE_BACKEND="local")
    return subprocess.run([sys.executable, "-m", "nodus", *args], cwd=d, env=env,
                          capture_output=True, text=True, timeout=120)


class LibraryRunLoopIsRefused(unittest.TestCase):

    # closes: #1021
    def test_cli_refuses_each_library_route(self):
        with tempfile.TemporaryDirectory() as d:
            _project(d)
            for route, (lib, main, line, fails) in _ROUTES.items():
                _write(d, "main.nd", main)
                # Twice: the second run loads the modules from the bytecode cache.
                for run in (1, 2):
                    with self.subTest(route=route, run=run):
                        proc = _nodus(d, "run", "main.nd")
                        out = proc.stdout + proc.stderr
                        self.assertEqual(proc.returncode, 1 if fails else 0, out)
                        self.assertIn(_REFUSED, proc.stderr)
                        self.assertIn(f"{lib}:{line}:", out)
                        self.assertIn("wait(task)", out)
                        self.assertNotIn("unreached", proc.stdout)

    def test_embedded_refuses_each_library_route(self):
        with tempfile.TemporaryDirectory() as d:
            _project(d)
            for route, (lib, main, line, fails) in _ROUTES.items():
                with self.subTest(route=route):
                    path = _write(d, "main.nd", main)
                    result = NodusRuntime(project_root=d).run_file(path)
                    if fails:
                        self.assertFalse(result["ok"], result)
                        message = (result.get("error") or {}).get("message", "")
                    else:
                        # A spawned task's failure: reported, not the run's.
                        self.assertTrue(result["ok"], result)
                        (spawned,) = result["spawned_errors"]
                        message = spawned["message"]
                    self.assertIn(_REFUSED, message)
                    self.assertIn(f"{lib}:{line}:", message)

    def test_the_programs_own_uses_are_not_refused(self):
        """The entry file, in a function or a coroutine, and a callback the
        program handed to a library, on both call routes."""
        with tempfile.TemporaryDirectory() as d:
            _project(d)
            _write(d, "main.nd", _ALLOWED)
            proc = _nodus(d, "run", "main.nd")
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            self.assertIn("done", proc.stdout)
            self.assertNotIn(_REFUSED, proc.stderr)

    def test_nodus_check_errs_on_each_library_call(self):
        with tempfile.TemporaryDirectory() as d:
            _project(d)
            _write(d, "main.nd", 'import "./lib.nd" as lib\nimport "./libtop.nd" as t\n')
            for run in (1, 2):  # cold, then after a run has warmed the cache
                with self.subTest(run=run):
                    proc = _nodus(d, "check", "main.nd")
                    self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
                    errors = [ln for ln in proc.stderr.splitlines() if ": error: run_loop()" in ln]
                    self.assertEqual(len(errors), 2, proc.stderr)
                    self.assertTrue(any("lib.nd:2:5" in e for e in errors), errors)
                    self.assertTrue(any("libtop.nd:2:1" in e for e in errors), errors)
                    _nodus(d, "run", "main.nd")

    def test_nodus_check_passes_the_programs_own_uses(self):
        with tempfile.TemporaryDirectory() as d:
            _project(d)
            _write(d, "main.nd", 'import "./lib.nd" as lib\nrun_loop()\n')
            proc = _nodus(d, "check", "main.nd")
            self.assertEqual(proc.returncode, 1, "lib.nd's own call is an error")
            _write(d, "lib.nd", "export fn call_back(f) {\n    return f()\n}\n")
            proc = _nodus(d, "check", "main.nd")
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)


class StdAsyncKeepsItsContract(unittest.TestCase):

    def test_parallel_and_series_keep_their_contract_and_are_not_refused(self):
        with tempfile.TemporaryDirectory() as d:
            _write(d, "par.nd", _PARALLEL)
            proc = _nodus(d, "run", "par.nd")
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            out = proc.stdout.splitlines()
            # Every task ran, the failure did not stop the others, nil came back.
            self.assertEqual(out[:4], ["a", "c", "parallel returned nil", "s1"], out)
            self.assertEqual(out[4], "s2")
            # Inside a coroutine it parks until its own tasks settle.
            self.assertEqual(out[5:], ["fast", "slow", "wait -> outer"], out)
            # A failure is reported as an un-waited task's always was, once, and
            # is not raised into the code that called parallel -- at top level
            # or inside a coroutine, where `__settle` parks.
            self.assertEqual(proc.stderr.count("boom"), 1, proc.stderr)
            self.assertEqual(proc.stderr.count("inner"), 1, proc.stderr)
            self.assertNotIn(_REFUSED, proc.stderr)

    def test_std_async_does_not_call_run_loop(self):
        path = os.path.join(_REPO, "src", "nodus", "stdlib", "async.nd")
        with open(path, encoding="utf-8") as f:
            code = [line.split("//", 1)[0] for line in f]
        self.assertFalse([line for line in code if "run_loop(" in line])


if __name__ == "__main__":
    unittest.main()
