"""A step body's dependencies are bound names, not undefined ones.

`after a` binds `a` to a's return value, `each p in d` binds `p` to the item, and
`compensates a` binds `a` to the compensated step's result (#577). All three are
the documented way to read a dependency, and all three *work at runtime*.

The analyzer pushed a scope for the step body and bound **none** of them, so
every such read reported `Undefined variable` on correct code. Confirmed against
published **5.6.0** for `after` and `each`, so this long predates the release
that surfaced it.

It was editor-only noise until #489 wired `nodus check` to this analyzer for
files declaring an `extern` — at which point a false positive became `nodus check`
**rejecting a correct program**. That is how it was found: Stage 5 of the 5.7.0
release, running the published wheel as a new user would, on a program using both
new features.

**Neither feature is broken alone; the interaction was.** The compensation tests
declared no `extern` and the extern tests used no compensation, so nothing
covered the pair. `test_extern_strictness_accepts_a_dependency_read` is the case
that would have caught it.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))  # noqa: E402

from nodus.runtime.embedding import NodusRuntime  # noqa: E402
from nodus.tooling.diagnostics import WorkspaceDiagnosticEngine  # noqa: E402
from nodus.tooling.runner import check_source  # noqa: E402


def _undefined(source: str) -> list[str]:
    result = WorkspaceDiagnosticEngine().analyze("m.nd", source=source)
    return [
        d.message
        for diags in result.diagnostics_by_file.values()
        for d in diags
        if "Undefined" in d.message
    ]


class StepDependenciesAreBoundTests(unittest.TestCase):
    # closes: #662
    def test_an_after_bound_dependency_is_not_undefined(self):
        """The documented idiom, false-flagged since before 5.6.0."""
        self.assertEqual(
            _undefined("workflow w { step a { return 1i } step b after a { return a } }"),
            [],
        )

    def test_an_each_loop_variable_is_not_undefined(self):
        self.assertEqual(
            _undefined("workflow w { step d { return [1i] } step r each p in d { return p } }"),
            [],
        )

    def test_a_compensated_step_name_is_not_undefined(self):
        self.assertEqual(
            _undefined(
                "workflow w { step a { return 1i } "
                'step s after a { throw "x" } '
                "step u compensates a { return a } }"
            ),
            [],
        )

    def test_a_genuine_typo_is_still_reported(self):
        """The binding must not turn the analyzer permissive.

        Without this, 'bind everything' would pass the three tests above and
        delete the feature they exist to protect.
        """
        self.assertEqual(
            _undefined("workflow w { step a { return 1i } step b after a { return nope } }"),
            ["Undefined variable: nope"],
        )

    def test_the_each_source_does_not_leak_as_a_name(self):
        """`each p in d` binds `p`, not `d` — the lowering substitutes the item
        for the list in the closure's parameter slot, and the analyzer must
        model the same substitution rather than binding both."""
        self.assertEqual(
            _undefined("workflow w { step d { return [1i] } step r each p in d { return d } }"),
            ["Undefined variable: d"],
        )


class ExternStrictnessTests(unittest.TestCase):
    """The interaction that shipped broken in 5.7.0."""

    SOURCE = (
        'extern notify(who: string) -> string\n'
        "workflow saga {\n"
        '    step reserve { return "res-1" }\n'
        '    step ship after reserve { throw "carrier down" }\n'
        '    step release compensates reserve { return "released \\(reserve)" }\n'
        "}\n"
        'fn main() { print(notify("x")) }\n'
    )

    def test_extern_strictness_accepts_a_dependency_read(self):
        """`nodus check` rejected this correct program in 5.7.0.

        Strict mode inherited the analyzer's false positives wholesale, so a
        file that declared an extern could not read any dependency by name.
        """
        result = check_source(self.SOURCE, filename="saga.nd")
        self.assertTrue(result["ok"], result.get("error"))

    def test_the_program_actually_runs(self):
        """The code was always correct — only the checker disagreed."""
        runtime = NodusRuntime(timeout_ms=None)
        runtime.register_function("notify", lambda who: "notified " + str(who), arity=1)
        cwd = os.getcwd()
        import tempfile

        with tempfile.TemporaryDirectory() as td:
            os.chdir(td)
            try:
                result = runtime.run_source(
                    self.SOURCE.replace(
                        'fn main() { print(notify("x")) }',
                        'fn main() { let r = run_workflow(saga)\n'
                        '    print("C=\\(r["compensation"])") }',
                    )
                )
            finally:
                os.chdir(cwd)
        self.assertTrue(result["ok"], result.get("error"))
        self.assertIn("released res-1", result.get("stdout") or "")

    def test_a_typo_in_a_declaring_file_is_still_rejected(self):
        """Strictness still works — the fix narrows it, it does not remove it."""
        broken = self.SOURCE.replace('print(notify("x"))', 'print(notif("x"))')
        result = check_source(broken, filename="saga.nd")
        self.assertFalse(result["ok"])
        self.assertIn("notif", (result.get("error") or {}).get("message", ""))


if __name__ == "__main__":
    unittest.main()
