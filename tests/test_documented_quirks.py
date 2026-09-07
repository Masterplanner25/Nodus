"""The documented quirks that are *errors*, each run and its message checked (#815).

`tests/eval/quirk_probe.nd` asserts what works. It could not assert what fails:
the probe is one process and any of these would abort it, so each lived as a
commented-out `// TRAP:` line with a note telling a reader to uncomment it
individually. Nothing ever did.

The cost was not hypothetical. Two of the six trap groups had gone stale --
compound assignment stopped being a parse error in **4.0.1**, and a closure's
write to an outer `let` started working in **5.8.0** (#671) -- and the probe went
on printing `ALL QUIRKS CONFIRMED` for both, because the claim was a comment and
the body asserted the workaround instead. One of them, `// TRAP: x += 1 -- parse
error if uncommented`, was simply false for eleven minors.

So the division is now: **the probe asserts what works, this file asserts what
errors**, and neither restates the other. The two that went stale are positive
cases now and live in the probe (`[Q5]`, `[Q6]`), with the underlying name
resolution pinned in `test_name_resolution_agreement.py`.

**The message is the assertion, not just the fact that something raised.** These
are the errors a user meets while learning the language, and a `LangRuntimeError`
wrapping a Python `TypeError` repr would satisfy a bare `assertRaises` while
being a regression. That is the class #807 was filed for.

Each quirk below was re-run against 5.12.0 dev source when this file was written;
the four here still fire. If one stops firing, that is a language change and this
test is where it should surface -- **fix the test by moving the quirk into the
probe as a positive case, not by deleting it.**
"""

import io
import unittest
from contextlib import redirect_stdout

import nodus as lang
from nodus.runtime.diagnostics import LangRuntimeError
from nodus.runtime.module_loader import ModuleLoader


def run_program(src: str, source_path: str | None = None) -> list[str]:
    vm = lang.VM([], {}, code_locs=[], source_path=source_path)
    _loader = ModuleLoader(project_root=None, vm=vm)
    buf = io.StringIO()
    with redirect_stdout(buf):
        _loader.load_module_from_source(
            src, module_name=source_path or "<memory>", base_dir=None
        )
    return buf.getvalue().splitlines()


class QuirkErrorCase(unittest.TestCase):
    def assert_error(self, src: str, expected: str) -> None:
        with self.assertRaises(LangRuntimeError) as caught:
            run_program(src)
        self.assertIn(expected, str(caught.exception))


class Q3NoStringNumberCoercionTests(QuirkErrorCase):
    """`+` does not coerce a number to a string; use `str()`."""

    def test_string_plus_float_is_refused(self):
        self.assert_error('let bad = "n=" + 5', "Cannot add string and float")

    def test_string_plus_int_is_refused(self):
        self.assert_error('let bad = "n=" + 5i', "Cannot add string and int")


class Q4NoMethodSugarTests(QuirkErrorCase):
    """No `.append()` / `.length()` / `.contains()` -- methods are records-only.

    All three report the same thing, which is the useful part: the refusal is
    about the *receiver*, not about the method name, so a reader is not sent
    hunting for a correctly spelled method that does not exist either.
    """

    _MESSAGE = "Method calls are only supported on records"

    def test_append_on_a_list_is_refused(self):
        self.assert_error("let xs = [1, 2]\nxs.append(3)", self._MESSAGE)

    def test_length_on_a_list_is_refused(self):
        self.assert_error("let xs = [1, 2]\nprint(xs.length())", self._MESSAGE)

    def test_contains_on_a_map_is_refused(self):
        self.assert_error('let m = {"k": 1}\nprint(m.contains("k"))', self._MESSAGE)


class Q7StoredFunctionNeedsExtractionTests(QuirkErrorCase):
    """`r.f(x)` passes the record as the first argument, whatever `f` expects.

    A stored `fn(x)` called that way receives `(r, x)`. The probe asserts the
    working idiom -- bind it first, then call -- and this is the error the other
    spelling gives.
    """

    def test_calling_a_stored_plain_function_as_a_method_passes_self(self):
        self.assert_error(
            "let r = record {get_plain: fn(x) { return x * 2 }}\nprint(r.get_plain(5))",
            "expected 1 args, got 2",
        )


class Q9ToolNamesMustBeDottedTests(unittest.TestCase):
    """`std:tool` refuses an undotted name.

    Not an exception -- `tool.register` *returns* the refusal and the tool is
    simply not registered. That distinction is the reason this quirk is easy to
    miss in real code: a program ignoring the return value carries on and only
    fails later, at the call site, with a missing tool. Both halves are asserted.
    """

    def test_an_undotted_name_is_refused_and_not_registered(self):
        src = """
import "std:tool" as tool
let outcome = tool.register(record {name: "nodot", description: "x", handler: fn(x) { return x }})
print(outcome)
print(tool.has("nodot"))
"""
        out = run_program(src)
        self.assertIn("must use dotted namespacing", out[0])
        self.assertEqual(out[1], "false")

    def test_a_dotted_name_registers(self):
        """The control. Without it the refusal above could be about anything."""
        src = """
import "std:tool" as tool
tool.register(record {name: "quirks.test", description: "probe", handler: fn(x) { return x }})
print(tool.has("quirks.test"))
"""
        self.assertEqual(run_program(src), ["true"])


class TheStaleTrapsAreGoneTests(unittest.TestCase):
    """The two claims that were false for eleven and one minors (#815).

    Asserted here as well as in the probe, deliberately and as the only
    duplication in this file: if either regresses, the probe's own harness is
    affected -- `[Q6]` is the mechanism its `check()` counter would rely on if
    that counter were ever simplified to a plain `let`. A Python-side assertion
    does not share that exposure.
    """

    # closes: #815
    def test_compound_assignment_is_not_a_parse_error(self):
        self.assertEqual(run_program("let x = 10\nx += 5\nprint(x)"), ["15.0"])

    def test_a_closure_assigns_an_outer_let(self):
        src = """
let count = 0
fn inc() { count = count + 1 }
inc()
inc()
print(count)
"""
        self.assertEqual(run_program(src), ["2.0"])


if __name__ == "__main__":
    unittest.main()
