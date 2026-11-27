"""Closed-issue test for #1015: `nodus test --coverage` counts lines.

The collector listened for a `line_executed` event that nothing emitted, from
the day it was added, so every report read `0.0% (0/0 lines)`. The VM now calls
a `line_observer` each time execution moves to another line, from the
instrumented loop it already runs for a debugger or profiler, and every child
VM inherits it, so lines in imported modules count. The totals come from the
location tables of the programs it sees.
"""
import json
import os
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, "C:/dev/Coding Language/src")

import nodus  # noqa: E402
from nodus.runtime.capability import derive_child_vm  # noqa: E402
from nodus.runtime.module_loader import ModuleLoader  # noqa: E402
from nodus.testing.coverage import CoverageCollector  # noqa: E402
from nodus.vm import pycompile  # noqa: E402

_REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

_CALC = (
    'import "std:strings" as s\n'           # 1
    "\n"                                    # 2
    "export fn add(a, b) {\n"               # 3
    "    let t = 0i\n"                      # 4
    "    for x in range(0i, 3i) {\n"        # 5
    "        t = t + x\n"                   # 6
    "    }\n"                               # 7
    "    return a + b + t\n"                # 8
    "}\n"                                   # 9
    "\n"                                    # 10
    "export fn unused(x) {\n"               # 11
    "    if (x > 0i) {\n"                   # 12
    '        return s.join(["a", "b"], ",")\n'  # 13
    "    }\n"                               # 14
    '    return "none"\n'                   # 15
    "}\n"                                   # 16
)

_TEST = (
    'import "std:test" as test\n'
    'import "./calc.nd" as calc\n'
    'test.suite("math", fn() {\n'
    '    test.case("adds", fn() {\n'
    '        test.assert_eq(calc.add(1i, 2i), 6i, "sum")\n'
    "    })\n"
    "})\n"
)

_HOT = (
    "fn hot(n) {\n"
    "    let t = 0i\n"
    "    for x in range(0i, n) {\n"
    "        t = t + x\n"
    "    }\n"
    "    return t\n"
    "}\n"
    "let total = 0i\n"
    "for i in range(0i, 40i) {\n"
    "    total = total + hot(5i)\n"
    "}\n"
    "print(total)\n"
)


def _write(directory, name, text):
    path = os.path.join(directory, name)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)
    return path


def _hits(path, compiled):
    vm = nodus.VM([], {}, code_locs=[], source_path=path)
    if compiled:
        pycompile.enable(vm, threshold=1)
    collector = CoverageCollector()
    collector.attach(vm)
    ModuleLoader(project_root=os.path.dirname(path), vm=vm).load_module_from_path(path)
    collector.detach(vm)
    return {p: dict(lines) for p, lines in collector.hits.items()}, vm


class CoverageCountsLines(unittest.TestCase):

    # closes: #1015
    def test_nodus_test_coverage_reports_the_module_under_test(self):
        with tempfile.TemporaryDirectory() as d:
            _write(d, "calc.nd", _CALC)
            test_path = _write(d, "calc_test.nd", _TEST)
            env = dict(os.environ, PYTHONPATH=os.path.join(_REPO, "src"))
            # Twice: the second run loads `calc.nd` from the bytecode cache.
            for run in (1, 2):
                proc = subprocess.run(
                    [sys.executable, "-m", "nodus", "test", "--coverage",
                     "--coverage-output", os.path.join(d, "cov"), test_path],
                    cwd=d, env=env, capture_output=True, text=True, timeout=120,
                )
                self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
                with open(os.path.join(d, "cov", "coverage.json"), encoding="utf-8") as f:
                    report = json.load(f)
                files = {os.path.basename(p): info for p, info in report["files"].items()}
                # Only the module under test: not the test file, not std:strings
                # or std:test.
                self.assertEqual(list(files), ["calc.nd"], f"run {run}: {list(files)}")
                calc = files["calc.nd"]
                covered = {int(k) for k in calc["covered_lines"]}
                self.assertTrue({4, 5, 6, 8} <= covered, f"run {run}: {sorted(covered)}")
                self.assertTrue({12, 13, 15} <= set(calc["uncovered_lines"]),
                                f"run {run}: {calc['uncovered_lines']}")
                self.assertFalse({2, 7, 10, 14} & set(calc["executable_lines"]),
                                 "blank lines and lone braces are not executable")
                summary = report["summary"]
                self.assertGreater(summary["total_executable_lines"], 0)
                self.assertGreater(summary["overall_coverage_pct"], 0)
                self.assertLess(summary["overall_coverage_pct"], 100)

    def test_compiled_functions_report_the_same_lines(self):
        """An observer keeps a compiled function interpreted, so no line is lost."""
        with tempfile.TemporaryDirectory() as d:
            path = _write(d, "hot.nd", _HOT)
            interpreted, _ = _hits(path, compiled=False)
            compiled, vm = _hits(path, compiled=True)
            self.assertEqual(compiled, interpreted)
            hot = next(v for p, v in interpreted.items() if p.endswith("hot.nd"))
            self.assertEqual(hot.get(2), 40, hot)  # `let t = 0i`, once per call
            # `hot` was compiled, so the equality above is not vacuous: its
            # calls ran interpreted because an observer was attached.
            self.assertGreater(vm._pycompile.compiled_count, 0)

    def test_no_observer_keeps_the_fast_loop(self):
        vm = nodus.VM([], {}, code_locs=[], source_path="x.nd")
        self.assertFalse(vm._instrumented())
        collector = CoverageCollector()
        collector.attach(vm)
        self.assertTrue(vm._instrumented())
        collector.detach(vm)
        self.assertIsNone(vm.line_observer)
        self.assertFalse(vm._instrumented())

    def test_child_vms_inherit_the_observer_and_its_absence(self):
        parent = nodus.VM([], {}, code_locs=[], source_path="p.nd")
        child = nodus.VM([], {}, code_locs=[], source_path="c.nd")
        collector = CoverageCollector()
        collector.attach(parent)
        derive_child_vm(child, parent)
        self.assertEqual(child.line_observer, collector.record_line)
        # A pooled child reused after coverage detached must not keep reporting.
        collector.detach(parent)
        derive_child_vm(child, parent)
        self.assertIsNone(child.line_observer)


if __name__ == "__main__":
    unittest.main()
