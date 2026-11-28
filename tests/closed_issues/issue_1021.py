"""Closed-issue test for #1021: `run_loop()` from a library warns, an error at 6.0.0.

`run_loop()` drains the scheduler's whole ready deque, and the VM chain shares
one, so a library that calls it runs every coroutine its caller spawned and had
not started. Decision D4 of `docs/governance/V6_0_PLAN.md` stages that as the
cohort's seventh flip: a `StagedFlipWarning` from 5.21.0, an error at 6.0.0.

"A library" is code from any module but the program's entry file, and there
are three ways to be running it. Each looks different from inside the VM:

- a module function called outside a coroutine runs on a detached child VM;
- one called inside a coroutine runs on the caller's VM, its context swapped in;
- an imported module's top level runs on the loader's VM, before the program's.

A closure the program hands to a library is the program's code on both call
routes, and does not warn.

`std:async.parallel` and `series` were themselves instances. They drive with
`__settle(task)` now, which is `wait(task)` without claiming the outcome, so
their documented contract holds: nil back, a failing task reported as before,
the other tasks still run.
"""
import os
import subprocess
import sys
import tempfile
import unittest
import warnings

sys.path.insert(0, "C:/dev/Coding Language/src")

from nodus.runtime.embedding import NodusRuntime  # noqa: E402
from nodus.support.staging import StagedFlipWarning, read_staged_flip_report  # noqa: E402

_REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

_LIB = (
    'print("lib top level")\n'       # 1
    "run_loop()\n"                   # 2  an import's top level
    "export fn drive() {\n"          # 3
    "    run_loop()\n"               # 4  a module function at top level
    "    return 1\n"                 # 5
    "}\n"                            # 6
    "export fn drive_in_co() {\n"    # 7
    "    run_loop()\n"               # 8  a module function inside a coroutine
    "    return 2\n"                 # 9
    "}\n"                            # 10
    "export fn call_back(f) {\n"     # 11
    "    return f()\n"               # 12
    "}\n"                            # 13
)

_MAIN = (
    'import "./lib.nd" as lib\n'
    "run_loop()\n"
    "lib.drive()\n"
    "spawn(coroutine(fn() { lib.drive_in_co() }))\n"
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

#: The three library call sites in `_LIB`, and nothing else.
_LIBRARY_LINES = {2, 4, 8}

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


def _write(directory, name, text):
    path = os.path.join(directory, name)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)
    return path


def _project(d):
    _write(d, "nodus.toml", '[project]\nname = "d4"\n')
    _write(d, "lib.nd", _LIB)
    return _write(d, "main.nd", _MAIN)


def _nodus(d, *args, env_extra=None):
    env = dict(os.environ, PYTHONPATH=os.path.join(_REPO, "src"),
               NODUS_WORKFLOW_STORE_BACKEND="local")
    env.update(env_extra or {})
    return subprocess.run([sys.executable, "-m", "nodus", *args], cwd=d, env=env,
                          capture_output=True, text=True, timeout=120)


def _warned_lines(stderr):
    lines = set()
    for line in stderr.splitlines():
        if "run_loop() was called from library code" not in line:
            continue
        where = line.split(" at ", 1)[1].split(". ", 1)[0]
        lines.add(int(where.rsplit(":", 2)[-2]))
    return lines


class LibraryRunLoopWarns(unittest.TestCase):

    # closes: #1021
    def test_cli_warns_for_each_library_route_and_nothing_else(self):
        with tempfile.TemporaryDirectory() as d:
            _project(d)
            # Twice: the second run loads both modules from the bytecode cache.
            for run in (1, 2):
                proc = _nodus(d, "run", "main.nd")
                self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
                self.assertIn("done", proc.stdout)
                self.assertEqual(_warned_lines(proc.stderr), _LIBRARY_LINES,
                                 f"run {run}: {proc.stderr}")
                self.assertIn("wait(task)", proc.stderr)

    def test_embedded_warns_for_the_same_three(self):
        with tempfile.TemporaryDirectory() as d:
            main = _project(d)
            with warnings.catch_warnings(record=True) as caught:
                warnings.simplefilter("always")
                result = NodusRuntime(project_root=d).run_file(main)
            self.assertTrue(result["ok"], result)
            hits = [str(w.message) for w in caught
                    if issubclass(w.category, StagedFlipWarning)
                    and "run_loop() was called from library code" in str(w.message)]
            self.assertEqual(len(hits), 3, hits)
            self.assertTrue(all("lib.nd" in h for h in hits), hits)

    def test_an_entry_file_alone_never_warns(self):
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            result = NodusRuntime().run_source(
                "spawn(coroutine(fn() { run_loop() }))\nrun_loop()\n"
                "fn f() { run_loop() }\nf()\n")
        self.assertTrue(result["ok"], result)
        self.assertFalse([w for w in caught if issubclass(w.category, StagedFlipWarning)])

    def test_the_staged_flip_report_records_it(self):
        with tempfile.TemporaryDirectory() as d:
            _project(d)
            report = os.path.join(d, "flips.jsonl")
            proc = _nodus(d, "run", "main.nd", env_extra={"NODUS_STAGED_FLIP_REPORT": report})
            self.assertEqual(proc.returncode, 0, proc.stderr)
            records = [r for r in read_staged_flip_report(report) if r["flip"] == "library-run-loop"]
            self.assertEqual({int(r["where"].rsplit(":", 2)[-2]) for r in records}, _LIBRARY_LINES)

    def test_check_staged_finds_the_library_calls_from_source(self):
        with tempfile.TemporaryDirectory() as d:
            _project(d)
            for run in (1, 2):  # cold, then after a run has warmed the cache
                proc = _nodus(d, "check", "--staged", "main.nd")
                self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
                self.assertIn("[ 3 found]   library-run-loop (#1021)", proc.stdout,
                              f"check {run}: {proc.stdout}")
                found = {int(line.split("lib.nd:", 1)[1].split(":", 1)[0])
                         for line in proc.stdout.splitlines()
                         if "lib.nd:" in line and "run_loop()" in line}
                self.assertEqual(found, _LIBRARY_LINES, proc.stdout)
                _nodus(d, "run", "main.nd")


class StdAsyncKeepsItsContract(unittest.TestCase):

    def test_parallel_and_series_keep_their_contract_and_do_not_warn(self):
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
            self.assertNotIn("run_loop() was called from library code", proc.stderr)

    def test_std_async_does_not_call_run_loop(self):
        path = os.path.join(_REPO, "src", "nodus", "stdlib", "async.nd")
        with open(path, encoding="utf-8") as f:
            code = [line.split("//", 1)[0] for line in f]
        self.assertFalse([line for line in code if "run_loop(" in line])


if __name__ == "__main__":
    unittest.main()
