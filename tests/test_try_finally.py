"""`try { } finally { }` needs no catch (#415).

The grammar demanded `catch`, so the canonical cleanup-without-handling form
had to be spelled `catch e { throw e }` -- forcing every cleanup site onto the
catch-re-throws path, the exact path #361 had to fix. The parser now accepts a
catch-less try when `finally` is present, and the compiler lowers it to the
rethrowing form, so the VM machinery is untouched.

Seven consumers read `catch_var`/`catch_block`; each is exercised here so the
None-carrying node cannot break one silently (the enumeration-risk shape).
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))  # noqa: E402

from nodus.runtime.embedding import NodusRuntime  # noqa: E402


def _run(source: str) -> dict:
    return NodusRuntime(timeout_ms=None).run_source(source)


# closes: #415
class TryFinallyTests(unittest.TestCase):
    def test_finally_runs_and_the_error_propagates(self):
        result = _run(
            "fn main() {\n"
            "    try {\n"
            '        try { throw "boom" } finally { print("CLEANUP") }\n'
            "    } catch e {\n"
            '        print("CAUGHT=\\(e)")\n'
            "    }\n"
            "}\n"
        )
        self.assertTrue(result["ok"], result.get("error"))
        stdout = result.get("stdout") or ""
        self.assertIn("CLEANUP", stdout)
        self.assertIn("CAUGHT=boom", stdout)
        self.assertLess(stdout.index("CLEANUP"), stdout.index("CAUGHT"))

    def test_finally_runs_on_the_success_path(self):
        result = _run(
            "fn main() {\n"
            '    try { print("WORK") } finally { print("CLEANUP") }\n'
            '    print("AFTER")\n'
            "}\n"
        )
        self.assertTrue(result["ok"], result.get("error"))
        stdout = result.get("stdout") or ""
        for marker in ("WORK", "CLEANUP", "AFTER"):
            self.assertIn(marker, stdout)

    def test_uncaught_error_still_fails_the_run(self):
        """The lowering is a rethrow, not a swallow."""
        result = _run(
            'fn main() { try { throw "boom" } finally { print("CLEANUP") } }\n'
        )
        self.assertFalse(result["ok"])
        self.assertIn("CLEANUP", result.get("stdout") or "")
        self.assertIn("boom", str(result))

    def test_try_alone_is_still_an_error(self):
        result = _run("fn main() { try { print(1i) } }\n")
        self.assertFalse(result["ok"])
        self.assertIn("catch", str(result))
        self.assertIn("finally", str(result))

    def test_works_inside_a_workflow_step(self):
        """The state rewriter is one of the seven consumers."""
        result = _run(
            "workflow w {\n"
            "    state log = \"\"\n"
            "    step a {\n"
            '        try { log = log + "x" } finally { log = log + "!" }\n'
            "        return 1i\n"
            "    }\n"
            "}\n"
            "fn main() {\n"
            "    let r = run_workflow(w)\n"
            '    let s = r["state"]\n'
            '    print("STATE=\\(s)")\n'
            "}\n"
        )
        self.assertTrue(result["ok"], result.get("error"))
        self.assertIn('"log": "x!"', result.get("stdout") or "")

    def test_formatter_round_trips_the_form(self):
        """The formatter must render the source form, not the lowering."""
        from nodus.frontend.lexer import tokenize
        from nodus.frontend.parser import Parser
        from nodus.tooling.formatter import format_program

        source = 'fn main() {\n    try {\n        print(1i)\n    } finally {\n        print(2i)\n    }\n}\n'
        formatted = format_program(Parser(tokenize(source)).parse())
        self.assertIn("} finally {", formatted)
        self.assertNotIn("catch", formatted)
        reparsed = format_program(Parser(tokenize(formatted)).parse())
        self.assertEqual(formatted, reparsed)

    def test_check_and_diagnostics_accept_the_form(self):
        from nodus.tooling.runner import check_source

        result = check_source(
            'fn main() { try { print(1i) } finally { print(2i) } }\n',
            filename="t.nd",
        )
        self.assertTrue(result["ok"], result.get("error"))

    def test_catch_and_finally_together_still_work(self):
        """Falsifiability control: the optionality must not have broken the
        full form."""
        result = _run(
            "fn main() {\n"
            '    try { throw "x" } catch e { print("C=\\(e)") } finally { print("F") }\n'
            "}\n"
        )
        self.assertTrue(result["ok"], result.get("error"))
        stdout = result.get("stdout") or ""
        self.assertIn("C=x", stdout)
        self.assertIn("F", stdout)


if __name__ == "__main__":
    unittest.main()
