"""Where `checkpoint "label"` is allowed, and what it says when it is not (#180).

**Stage 1** made the spelling outside a step body a parse error. Before that it
parsed as two expression statements -- a reference to a variable named
`checkpoint` and a discarded string -- and failed at run time as `Undefined
variable: checkpoint`, which names neither the rule nor the way forward.

**Stage 4b** (design 08a, D2) narrowed it. Inside any function body the
statement now compiles, because whether a function runs as a durable coroutine
is a run-time fact (`durable_spawn`). So:

- **at module level** it is still a parse error: no function is running, so it
  can never be in a durable coroutine;
- **inside a function** it is a checkpoint, and if that function is not running
  as a durable coroutine or a step it fails *at run time* with a message that
  names `durable_spawn`;
- **inside a step body** it is unchanged.

One constraint has held through both stages: **the word must not become
reserved.** `AllowedShapesTests` holds every ordinary use of the name open.

Both paths are driven: the CLI (`nodus run`, `nodus check`) and an embedded
`NodusRuntime`.
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
from nodus.runtime.durable import CHECKPOINT_NOT_DURABLE  # noqa: E402
from nodus.runtime.embedding import NodusRuntime  # noqa: E402

_NODUS_PY = str(_REPO_ROOT / "nodus.py")
_DESIGN = _REPO_ROOT / "docs/design/v5/08a-durable-coroutines-stage4.md"


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


def _checkpoint_labels(src: str) -> list[str]:
    return sorted(n.label.v for root in _parse(src) for n in _walk(root)
                  if isinstance(n, CheckpointStmt))


def _cli(args: list[str], src: str) -> str:
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "cp.nd")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(textwrap.dedent(src))
        env = dict(os.environ, PYTHONPATH=str(_REPO_ROOT / "src"))
        argv = [path if arg == "{path}" else arg for arg in args]
        assert path in argv, f"no {{path}} placeholder in {args}"
        proc = subprocess.run(
            [sys.executable, _NODUS_PY, *argv],
            cwd=tmp, env=env, capture_output=True, text=True, timeout=120,
        )
        return proc.stdout + proc.stderr


# Each shape refused at module level, with the (line, col) of the word after dedent.
_REFUSED = {
    "at top level": ("""
        checkpoint "top"
        print("after")
        """, (2, 1)),
    "with an interpolated label": ("""
        let x = 1i
        checkpoint "at \\(x)"
        """, (3, 1)),
    "after a binding of the same name, on one line": ("""
        let checkpoint = 1i; checkpoint "x"
        """, (2, 22)),
}


class RefusedAtModuleLevelTests(unittest.TestCase):

    def test_each_shape_is_refused_at_parse_time_with_its_position(self):
        for name, (src, (line, col)) in _REFUSED.items():
            with self.subTest(name):
                with self.assertRaises(LangSyntaxError) as caught:
                    _parse(src)
                self.assertIn("at module level records nothing", str(caught.exception))
                self.assertEqual((line, col), (caught.exception.line, caught.exception.col))

    def test_the_message_points_somewhere_real(self):
        """It names the two places the statement does work, and the design it
        points at must exist: a pointer to a moved file rots silently."""
        for text in (CHECKPOINT_OUTSIDE_STEP, CHECKPOINT_NOT_DURABLE):
            with self.subTest(text[:30]):
                self.assertIn("durable_spawn", text)
                self.assertIn("workflow", text)
                self.assertIn("docs/design/v5/08a-durable-coroutines-stage4.md", text)
        self.assertIn("#180", CHECKPOINT_OUTSIDE_STEP)
        self.assertTrue(_DESIGN.is_file(), _DESIGN)

    def test_cli_run_and_check_both_refuse_it(self):
        src, _ = _REFUSED["at top level"]
        for args in (["run", "--time-limit", "30", "{path}"], ["check", "{path}"]):
            with self.subTest(args[0]):
                out = _cli(args, src)
                self.assertIn("at module level records nothing", out)
                self.assertIn("cp.nd:2:1", out)
                self.assertNotIn("Undefined variable", out)


# Stage 1 refused these at parse time. Stage 4b compiles them.
_IN_A_FUNCTION = {
    "in a bare coroutine": """
        fn main() {
            let c = coroutine(fn() {
                checkpoint "half-way"
                return 1i
            })
            spawn(c); run_loop()
        }
        main()
        """,
    "in a plain function": """
        fn f() {
            if (true) { checkpoint "inner" }
            return 1i
        }
        print(f())
        """,
}


class InsideAFunctionItIsACheckpointTests(unittest.TestCase):

    def test_each_shape_parses_as_a_checkpoint(self):
        for name, src in _IN_A_FUNCTION.items():
            with self.subTest(name):
                self.assertEqual(1, len(_checkpoint_labels(src)))

    def test_not_running_durably_it_fails_at_run_time_naming_durable_spawn(self):
        """The embedded runtime. A coroutine's failure is reported on stderr
        and in `spawned_errors`; a plain call fails the run."""
        for name, src in _IN_A_FUNCTION.items():
            with self.subTest(name):
                result = NodusRuntime(timeout_ms=None, max_steps=None).run_source(
                    textwrap.dedent(src))
                text = (str(result.get("error") or "") + (result.get("stderr") or "")
                        + str(result.get("spawned_errors") or ""))
                self.assertIn(CHECKPOINT_NOT_DURABLE, text)
                self.assertNotIn("Undefined variable", text)

    def test_cli_check_accepts_it_and_run_reports_it(self):
        src = _IN_A_FUNCTION["in a plain function"]
        self.assertIn("OK", _cli(["check", "{path}"], src))
        out = _cli(["run", "--time-limit", "30", "{path}"], src)
        self.assertIn("ran outside a workflow step and outside a durable coroutine", out)
        # At the `checkpoint` word (col 17), not at its label (col 28): the
        # call is the statement, and that is where the error belongs.
        self.assertIn("cp.nd:3:17", out)

    def test_an_interpolated_label_is_refused_as_in_a_step(self):
        with self.assertRaises(LangSyntaxError) as caught:
            _parse('fn f() {\n    let x = 1i\n    checkpoint "at \\(x)"\n}\n')
        self.assertIn("checkpoint label must be a string", str(caught.exception))


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
        # Stage 4b: inside a function the name still works wherever it is not
        # immediately followed by a string literal.
        "a local and a call inside a function": (
            'fn f() {\n    let checkpoint = fn(s) { return s }\n    return checkpoint("y")\n}\nprint(f())\n',
            "y"),
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
        labels = _checkpoint_labels("""
            workflow w {
                step a {
                    checkpoint "top"
                    let f = fn() { checkpoint "nested"; return 1i }
                    return f()
                }
            }
            """)
        self.assertEqual(["nested", "top"], labels)


if __name__ == "__main__":
    unittest.main()
