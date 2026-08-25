"""Static analysis enters workflow step bodies (#401).

Two walkers skipped them: the type analyzer bound a flow's name and returned,
so `nodus check` never type-checked a step body; and the workspace diagnostics
engine (`nodus lsp`) had no case for flow declarations, so a step body got no
undefined-variable, unused-variable or unreachable-code diagnostics at all.

Found on the way in, and fixed here because it blocked the walk: the
diagnostics engine never bound *any* block-scoped `let`, so
`fn f() { let y = 1i; return y }` reported a false "Undefined variable: y" on
every function local.

What is deliberately NOT changed, pinned below: `nodus check` still accepts a
call to a name defined nowhere. A program calling a host-registered function
is indistinguishable from a typo until a program can declare its host surface
-- that is #489, and tightening this before it lands would reject every
embedded program.
"""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))  # noqa: E402

from nodus.tooling.diagnostics import WorkspaceDiagnosticEngine  # noqa: E402
from nodus.tooling.runner import check_source  # noqa: E402


def _diags(source: str) -> list[str]:
    with tempfile.TemporaryDirectory() as td:
        path = os.path.join(td, "m.nd")
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(source)
        result = WorkspaceDiagnosticEngine().analyze(path, source=source)
        return [
            f"{d.severity}|{d.message}"
            for diags in result.diagnostics_by_file.values()
            for d in diags
        ]


# closes: #401
class CheckEntersStepBodiesTests(unittest.TestCase):
    def test_check_type_checks_a_step_body(self):
        result = check_source(
            "fn greet(name: string, times: int) -> string { return name }\n"
            'workflow w { step a { return greet(42i, "no") } }\n',
            filename="t.nd",
        )
        self.assertFalse(result["ok"])
        self.assertIn("expected string but got int", str(result))

    def test_check_passes_a_clean_workflow(self):
        result = check_source(
            "workflow w {\n"
            '    state log = ""\n'
            '    step a { log = log + "a"; checkpoint "cp"; return 1i }\n'
            "    step b after a { return 2i }\n"
            "}\n"
            "fn main() { let r = run_workflow(w) }\n",
            filename="t.nd",
        )
        self.assertTrue(result["ok"], result.get("error"))

    def test_check_still_accepts_unknown_host_shaped_calls(self):
        """The deliberate permissiveness, pinned as decided: an unknown free
        name may be a host-registered function, and until a program can
        declare its host surface (#489) rejecting it would reject every
        embedded program. This is the half of the issue that stays open."""
        result = check_source(
            "workflow w { step a { return maybe_a_host_function(1i) } }\n",
            filename="t.nd",
        )
        self.assertTrue(result["ok"], result.get("error"))

    def test_lsp_flags_an_undefined_variable_in_a_step_body(self):
        """The issue's re-verified repro: this file reported no diagnostics."""
        diags = _diags(
            "workflow w {\n"
            "  step a { let x = totally_undefined_thing(); return x }\n"
            "}\n"
        )
        self.assertTrue(
            any("Undefined variable: totally_undefined_thing" in d for d in diags),
            diags,
        )

    def test_lsp_warns_on_an_unused_step_local(self):
        diags = _diags(
            "workflow w { step a { let unused_thing = 1i; return 2i } }\n"
        )
        self.assertTrue(any("Unused variable: unused_thing" in d for d in diags), diags)

    def test_state_cells_resolve_and_are_never_reported_unused(self):
        """Steps read cells bare, and whether a cell is ever read is the
        runtime's business (#485), not a lint."""
        diags = _diags(
            "workflow w {\n"
            '    state log = ""\n'
            "    state never_read = 0i\n"
            '    step a { log = log + "a"; return 1i }\n'
            "}\n"
        )
        self.assertFalse([d for d in diags if "Undefined variable: log" in d], diags)
        self.assertFalse([d for d in diags if "never_read" in d], diags)

    def test_function_locals_are_no_longer_falsely_undefined(self):
        """The wider gap found on the way in: the engine never bound any
        block-scoped `let`, so every function local was a false error."""
        diags = _diags("fn f() { let y = 1i; return y }\nfn main() { print(f()) }\n")
        self.assertEqual([d for d in diags if "error" in d], [], diags)


if __name__ == "__main__":
    unittest.main()
