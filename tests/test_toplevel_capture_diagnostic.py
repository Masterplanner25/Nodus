"""A closure in a top-level loop body gets a diagnosis, not a lie (#416).

Upvalue capture reads an enclosing *function* frame, and a block scope at
module root -- a top-level `while`/`for`/`if` body -- has no frame, so a
closure written there has nothing to capture from. The compile error for that
shape used to be "Undefined variable: snap" with `snap` declared on the line
above -- accurate about resolution, actively misleading about the fix.

The error now names the constraint and both remedies. Making top-level blocks
actually capturable is the deeper option recorded on the issue; the semantics
where capture works (per-iteration binding inside a function) are pinned here
so neither fix path regresses them.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))  # noqa: E402

from nodus.runtime.embedding import NodusRuntime  # noqa: E402


def _run(source: str) -> dict:
    return NodusRuntime(timeout_ms=None).run_source(source)


# closes: #416
class TopLevelCaptureDiagnosticTests(unittest.TestCase):
    def test_while_body_let_gets_the_capture_message(self):
        result = _run(
            "let acc = []\n"
            "let n = 0i\n"
            "while (n < 3i) {\n"
            "    let snap = n\n"
            "    acc = acc + [fn() { return snap }]\n"
            "    n = n + 1i\n"
            "}\n"
        )
        self.assertFalse(result["ok"])
        text = str(result)
        self.assertIn("Cannot capture 'snap'", text)
        self.assertIn("top-level loop or block body", text)
        self.assertIn("Move the loop into a function", text)
        self.assertNotIn("Undefined variable", text)

    def test_for_loop_variable_gets_the_capture_message(self):
        result = _run(
            "let fs = []\n"
            "for item in [1i, 2i] {\n"
            "    fs = fs + [fn() { return item }]\n"
            "}\n"
        )
        self.assertFalse(result["ok"])
        self.assertIn("Cannot capture 'item'", str(result))

    def test_top_level_if_block_let_gets_the_capture_message(self):
        result = _run(
            "let go = true\n"
            "if (go) {\n"
            "    let inner = 1i\n"
            "    let f = fn() { return inner }\n"
            "}\n"
        )
        self.assertFalse(result["ok"])
        self.assertIn("Cannot capture 'inner'", str(result))

    def test_genuinely_undefined_name_still_says_undefined(self):
        """Falsifiability control: the capture message must not fire for a
        name that is not a top-level block local -- a plain typo stays a
        plain 'Undefined variable'."""
        result = _run("fn f() { return zz_never_declared }\nlet x = f()\n")
        self.assertFalse(result["ok"])
        text = str(result)
        self.assertIn("zz_never_declared", text)
        self.assertNotIn("Cannot capture", text)

    def test_loop_inside_a_function_still_captures_per_iteration(self):
        """The working shape and its semantics, pinned: capture happens and
        binds per iteration (0 1 2, not 2 2 2)."""
        result = _run(
            "fn build() {\n"
            "    let acc = []\n"
            "    let n = 0i\n"
            "    while (n < 3i) {\n"
            "        let snap = n\n"
            "        acc = acc + [fn() { return snap }]\n"
            "        n = n + 1i\n"
            "    }\n"
            "    return acc\n"
            "}\n"
            "fn main() {\n"
            "    let fs = build()\n"
            "    let a = fs[0]\n"
            "    let b = fs[1]\n"
            "    let c = fs[2]\n"
            '    print("\\(a()) \\(b()) \\(c())")\n'
            "}\n"
        )
        self.assertTrue(result["ok"], result.get("error"))
        self.assertIn("0 1 2", result.get("stdout") or "")

    def test_top_level_let_outside_any_block_still_captures(self):
        """A closure over a plain top-level `let` is a global access and must
        keep working -- the diagnostic is for block-scoped locals only."""
        result = _run(
            "let base = 41i\n"
            "fn bump() { return base + 1i }\n"
            "fn main() { print(bump()) }\n"
        )
        self.assertTrue(result["ok"], result.get("error"))
        self.assertIn("42", result.get("stdout") or "")


if __name__ == "__main__":
    unittest.main()
