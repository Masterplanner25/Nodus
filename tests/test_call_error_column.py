"""#921: an error raised by a call points at the call, not at its last argument.

The compiler emits a call instruction after compiling the arguments, and each
argument moved the current source position, so a builtin refusing its argument
was reported at the *last argument*: `len(     42i     )` said column 18, where
`len` is at 9. The same position is recorded as a frame's call site, so every
"called from" line in a stack trace was off the same way.

Now each call site points at the start of what is being called -- `len` in
`len(...)`, `fs` in `fs.read(...)`, `xs` in `xs[0](...)` -- set in one place
(`Compiler.set_call_loc`) just before each of the call instructions is emitted.

Checked through the embedded runtime's structured error and through `nodus run`,
which formats it.
"""

import os
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))  # noqa: E402

from nodus.runtime.embedding import NodusRuntime  # noqa: E402

# Each case: source, then the (line, column) the error must report, then the
# "called from" positions its stack trace must show, innermost first.
_CASES = {
    "a builtin": ("let a = 1i\nlet n = len(     42i     )\n", (2, 9), []),
    "through a stdlib wrapper": (
        'import "std:fs" as fs\nlet r = fs.read(     42i     )\n', (2, 9), []),
    "an indexed call": (
        "let xs = [fn(v) { return len(v) }]\nlet r = xs[0](     42i     )\n",
        (1, 26), ["(2, 9)"]),
    # A record-field function called as a method receives the record first.
    "a method on a record": (
        "let r = {f: fn(self, v) { return len(v) }}\nlet n = r.f(     42i     )\n",
        (1, 34), ["(2, 9)"]),
    "nested frames": (
        "fn f(v) {\n    return len(v)\n}\nfn g() { return f(     42i     ) }\ng()\n",
        (2, 12), ["(4, 17)", "(5, 1)"]),
}


def _frames(stack: list[str]) -> list[str]:
    """`(line, col)` of each "called from" entry, innermost first."""
    out = []
    for entry in stack:
        if entry.startswith("called from"):
            line, col = entry.rsplit(":", 2)[-2:]
            out.append(f"({line}, {col.rstrip(')')})")
    return out


class TheEmbeddedErrorPointsAtTheCallTests(unittest.TestCase):

    # closes: #921
    def test_each_call_shape_reports_the_callee(self):
        for name, (source, where, called_from) in _CASES.items():
            with self.subTest(name):
                result = NodusRuntime(timeout_ms=None, max_steps=None).run_source(source)
                self.assertFalse(result["ok"])
                error = result["error"]
                self.assertEqual(where, (error["line"], error["column"]), error)
                self.assertEqual(called_from, _frames(error.get("stack") or []), error)


class TheCliPrintsTheSamePositionTests(unittest.TestCase):

    def test_nodus_run_reports_the_callee(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "col.nd")
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(textwrap.dedent(_CASES["a builtin"][0]))
            proc = subprocess.run(
                [sys.executable, str(REPO / "nodus.py"), "run", path],
                cwd=tmp, env=dict(os.environ, PYTHONPATH=str(REPO / "src")),
                capture_output=True, text=True, timeout=120)
        self.assertNotEqual(0, proc.returncode)
        self.assertIn("col.nd:2:9: len(x) expects string, list, or map", proc.stderr)


if __name__ == "__main__":
    unittest.main()
