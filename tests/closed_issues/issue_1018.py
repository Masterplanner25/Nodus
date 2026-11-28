"""Closed-issue test for #1018: coverage counted a line that never ran.

An instruction a statement emits after a nested block -- a function's implicit
`return nil`, an `if`'s jump, a loop's jump back, the program's closing `HALT`
-- took the location of the last line the compiler had seen, which was the
block's last line. Executing it reported that line to the line observer, so
`nodus test --coverage` counted it as covered:

- a module ending in an uncalled function had that function's last line
  covered, by the `HALT` that loading the module runs;
- `fn sign(x) { if (x > 0i) { print("pos") } }`, called with 0, had the
  `print` line covered, by the implicit `return nil`.

Now a statement's location is restored once it is compiled, the implicit
return carries the `fn` line, and `HALT` carries no line.
"""
import json
import os
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, "C:/dev/Coding Language/src")

from nodus.compiler.compiler import normalize_bytecode  # noqa: E402
from nodus.runtime.module_loader import ModuleLoader  # noqa: E402

_REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

_CALC = (
    "export fn add(a, b) {\n"           # 1
    "    let t = a + b\n"               # 2
    "    return t\n"                    # 3
    "}\n"                               # 4
    "\n"                                # 5
    "export fn sign(x) {\n"             # 6
    "    if (x > 0i) {\n"               # 7
    '        print("pos")\n'            # 8
    "    }\n"                           # 9
    "}\n"                               # 10
    "\n"                                # 11
    "export fn loop(n) {\n"             # 12
    "    let i = 0i\n"                  # 13
    "    while (i < n) {\n"             # 14
    "        i = i + 1i\n"              # 15
    "        if (i > 100i) {\n"         # 16
    '            print("big")\n'        # 17
    "        }\n"                       # 18
    "    }\n"                           # 19
    "    return i\n"                    # 20
    "}\n"                               # 21
    "\n"                                # 22
    "export fn unused(x) {\n"           # 23
    "    if (x > 0i) {\n"               # 24
    '        return "pos"\n'            # 25
    "    }\n"                           # 26
    '    return "neg"\n'                # 27
    "}\n"                               # 28
)

_TEST = (
    'import "std:test" as test\n'
    'import "../calc.nd" as calc\n'
    'test.suite("m", fn() {\n'
    '    test.case("runs", fn() {\n'
    '        test.assert_eq(calc.add(1i, 2i), 3i, "sum")\n'
    "        calc.sign(0i)\n"
    '        test.assert_eq(calc.loop(3i), 3i, "loop")\n'
    "    })\n"
    "})\n"
)


def _write(directory, name, text):
    path = os.path.join(directory, name)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)
    return path


class BorrowedLinesAreNotCovered(unittest.TestCase):

    # closes: #1018
    def test_lines_that_never_ran_are_uncovered(self):
        with tempfile.TemporaryDirectory() as d:
            _write(d, "nodus.toml", '[project]\nname = "calc"\n')
            _write(d, "calc.nd", _CALC)
            _write(d, os.path.join("tests", "calc_test.nd"), _TEST)
            env = dict(os.environ, PYTHONPATH=os.path.join(_REPO, "src"))
            # Twice: the second run loads `calc.nd` from the bytecode cache.
            for run in (1, 2):
                proc = subprocess.run(
                    [sys.executable, "-m", "nodus", "test", "--coverage",
                     "--coverage-output", os.path.join(d, "cov")],
                    cwd=d, env=env, capture_output=True, text=True, timeout=120,
                )
                self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
                with open(os.path.join(d, "cov", "coverage.json"), encoding="utf-8") as f:
                    report = json.load(f)
                files = {os.path.basename(p): info for p, info in report["files"].items()}
                calc = files["calc.nd"]
                covered = {int(k) for k in calc["covered_lines"]}
                never_ran = {8, 17, 23, 24, 25, 27}
                self.assertFalse(covered & never_ran,
                                 f"run {run}: covered {sorted(covered)}")
                self.assertTrue({1, 2, 3, 6, 7, 12, 13, 14, 15, 16, 20} <= covered,
                                f"run {run}: covered {sorted(covered)}")

    def test_halt_and_implicit_return_borrow_no_line(self):
        for optimize in (False, True):
            loader = ModuleLoader(project_root=None)
            bytecode, functions, locs = loader.compile_only(
                _CALC, module_name="calc.nd", optimize=optimize)
            _version, code = normalize_bytecode(bytecode)
            halts = [i for i, instr in enumerate(code) if instr[0] == "HALT"]
            self.assertTrue(halts)
            for i in halts:
                self.assertIsNone(locs[i][1], f"optimize={optimize}: HALT at {locs[i]}")
            # `sign`'s implicit `return nil` is the function's last RETURN.
            info = next(v for k, v in functions.items() if k.endswith("sign"))
            ret = next(i for i in range(info.addr, len(code)) if code[i][0] == "RETURN")
            self.assertEqual(locs[ret][1], 6, f"optimize={optimize}: {locs[ret]}")


if __name__ == "__main__":
    unittest.main()
