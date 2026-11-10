"""#180 stage 1: `checkpoint "label"` outside a step body is a diagnosed error.

Before this, the spelling outside a step parsed as two expression statements -- a
bare reference to a variable named `checkpoint` and a discarded string -- and failed
at *run* time as `Undefined variable: checkpoint`. That names neither the rule nor
the way forward, and the place people most often write it is a bare coroutine,
which cannot checkpoint yet (docs/design/v5/08-durable-coroutines.md).

The constraint that shapes the fix (design §8): **the word must not become
reserved.** `checkpoint` is contextual, and every ordinary use of it as a name must
keep compiling. So only the one never-meaningful shape is refused -- the identifier
immediately followed by a string literal on the same line, in statement position --
and `AllowedShapesTests` holds the rest open.

Both paths are driven: the CLI (`nodus run`, `nodus check`) and an embedded
`NodusRuntime`. They share the parser today, which is exactly the assumption a test
should not leave unchecked.
"""

import os
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO_ROOT / "src"))  # noqa: E402

from nodus.frontend.ast.ast_nodes import CheckpointStmt  # noqa: E402
from nodus.frontend.lexer import tokenize  # noqa: E402
from nodus.frontend.parser import CHECKPOINT_OUTSIDE_STEP, Parser  # noqa: E402
from nodus.runtime.diagnostics import LangSyntaxError  # noqa: E402
from nodus.runtime.embedding import NodusRuntime  # noqa: E402

_NODUS_PY = str(_REPO_ROOT / "nodus.py")
_DESIGN = _REPO_ROOT / "docs/design/v5/08-durable-coroutines.md"


def _parse(src: str):
    return Parser(tokenize(textwrap.dedent(src))).parse()


def _walk(node):
    """Every AST node under `node`, found through its attributes and lists."""
    yield node
    for value in vars(node).values() if hasattr(node, "__dict__") else ():
        children = value if isinstance(value, list) else [value]
        for child in children:
            if hasattr(child, "__dict__") and type(child).__module__.endswith("ast_nodes"):
                yield from _walk(child)


# Each refused shape, with the (line, col) of the `checkpoint` word after dedent.
_REFUSED = {
    "in a bare coroutine (the case #180 is about)": ("""
        fn main() {
            let c = coroutine(fn() {
                checkpoint "half-way"
                return 1i
            })
            spawn(c); run_loop()
        }
        main()
        """, (4, 9)),
    "at top level": ("""
        checkpoint "top"
        print("after")
        """, (2, 1)),
    "in a plain function": ("""
        fn f() {
            if (true) { checkpoint "inner" }
            return 1i
        }
        """, (3, 17)),
    "with an interpolated label": ("""
        let x = 1i
        checkpoint "at \\(x)"
        """, (3, 1)),
    "after a binding of the same name, on one line": ("""
        let checkpoint = 1i; checkpoint "x"
        """, (2, 22)),
}


class RefusedShapesTests(unittest.TestCase):
    """The spelling outside a step is a compile-time error naming the rule."""

    def test_each_shape_is_refused_at_parse_time_with_its_position(self):
        for name, (src, (line, col)) in _REFUSED.items():
            with self.subTest(name):
                with self.assertRaises(LangSyntaxError) as caught:
                    _parse(src)
                self.assertIn("only valid inside a workflow step body", str(caught.exception))
                self.assertEqual((line, col), (caught.exception.line, caught.exception.col))

    def test_the_message_points_somewhere_real(self):
        """The message names #180 and the design doc. A pointer to a moved file
        is the kind of thing that rots silently, so check the file is there."""
        self.assertIn("#180", CHECKPOINT_OUTSIDE_STEP)
        self.assertIn("docs/design/v5/08-durable-coroutines.md", CHECKPOINT_OUTSIDE_STEP)
        self.assertTrue(_DESIGN.is_file(), _DESIGN)
        self.assertIn("workflow", CHECKPOINT_OUTSIDE_STEP)  # the way forward today

    def test_embedded_runtime_reports_it_as_a_syntax_error(self):
        src, _ = _REFUSED["in a bare coroutine (the case #180 is about)"]
        result = NodusRuntime(timeout_ms=None, max_steps=None).run_source(textwrap.dedent(src))
        self.assertFalse(result.get("ok"), result)
        text = str(result.get("error") or "") + (result.get("stderr") or "")
        self.assertIn("only valid inside a workflow step body", text)
        self.assertNotIn("Undefined variable", text)

    def test_cli_run_and_check_both_refuse_it(self):
        src, _ = _REFUSED["in a bare coroutine (the case #180 is about)"]
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "cp_outside.nd")
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(textwrap.dedent(src))
            env = dict(os.environ, PYTHONPATH=str(_REPO_ROOT / "src"))
            for args in (["run", "--time-limit", "30", path], ["check", path]):
                with self.subTest(args[0]):
                    proc = subprocess.run(
                        [sys.executable, _NODUS_PY, *args],
                        cwd=tmp, env=env, capture_output=True, text=True, timeout=120,
                    )
                    out = proc.stdout + proc.stderr
                    self.assertIn("only valid inside a workflow step body", out)
                    self.assertIn("cp_outside.nd:4:9", out)
                    self.assertNotIn("Undefined variable", out)


class AllowedShapesTests(unittest.TestCase):
    """The word is contextual and stays that way. Each of these compiled and ran
    before stage 1, and each must still -- the obvious implementation (reserve
    the word) breaks every one of them."""

    _PROGRAMS = {
        "a binding": ('let checkpoint = 42i\nprint(checkpoint)\n', "42"),
        "a call": ('let checkpoint = fn(s) { return "got \\(s)" }\nprint(checkpoint("x"))\n', "got x"),
        "a record field": ('let r = {checkpoint: 7i}\nprint(r.checkpoint)\n', "7"),
        "a parameter": ('fn f(checkpoint) { return checkpoint }\nprint(f(3i))\n', "3"),
        "name and string on separate lines": (
            'let checkpoint = 1i\ncheckpoint\n"x"\nprint("ok")\n', "ok"),
    }

    def test_each_still_runs(self):
        for name, (src, expected) in self._PROGRAMS.items():
            with self.subTest(name):
                result = NodusRuntime(timeout_ms=None, max_steps=None).run_source(src)
                self.assertTrue(result.get("ok"), (name, result))
                self.assertEqual(expected, (result.get("stdout") or "").strip())

    def test_inside_a_step_it_is_still_a_checkpoint(self):
        """Including from a function nested in the step body, which is still
        inside the step for the parser's purposes."""
        nodes = _parse("""
            workflow w {
                step a {
                    checkpoint "top"
                    let f = fn() { checkpoint "nested"; return 1i }
                    return f()
                }
            }
            """)
        labels = sorted(
            n.label.v for root in nodes for n in _walk(root) if isinstance(n, CheckpointStmt)
        )
        self.assertEqual(["nested", "top"], labels)


if __name__ == "__main__":
    unittest.main()
