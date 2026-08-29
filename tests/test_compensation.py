"""`compensates`: a declared undo path for work that already succeeded (#577).

A workflow declared its forward edges and had no representation for the undo
path. When a run ended failed, the work that had already **succeeded** — a
reservation made, a card charged — had no declared compensation; the only
mechanism was caller-side code that had to know the reverse completion order
itself.

Spec: `docs/design/workflow-dsl/01-compensation.md`.

Two things here are load-bearing and easy to weaken by accident:

**Order comes from `completion_seq`, never from `finished_at`.**
`test_unwind_is_in_reverse_completion_order` uses a **causal chain of trivial
steps** — the exact shape that ties on the clock, since `runtime_time_ms()` is
`time.monotonic()` at ~15.6 ms granularity. A test with slow or concurrent steps
would pass on a timestamp sort and prove nothing.

**The trigger is the transition to failed, not a failure payload's return.**
`run_task_graph` has three failed exits, and the resume-rebuild path returns a
recorded failure for a run that already unwound. A hook in the wrong place
compensates twice.
"""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))  # noqa: E402

from nodus.frontend.lexer import tokenize  # noqa: E402
from nodus.frontend.parser import Parser  # noqa: E402
from nodus.runtime.embedding import NodusRuntime  # noqa: E402


def _run(source: str) -> str:
    cwd = os.getcwd()
    with tempfile.TemporaryDirectory() as td:
        os.chdir(td)
        try:
            result = NodusRuntime(timeout_ms=None).run_source(source)
        finally:
            os.chdir(cwd)
    assert result["ok"], result.get("error")
    return result.get("stdout") or ""


SAGA = """
workflow saga {
    step reserve { return "res-1" }
    step charge after reserve { return "ch-1" }
    step ship after charge { throw "carrier down" }
    step release compensates reserve { return "released \\(reserve)" }
    step refund compensates charge { return "refunded \\(charge)" }
}
fn main() {
    let r = run_workflow(saga)
    print("R=\\(r["compensation"])")
    print("S=\\(r["statuses"])")
    print("F=\\(r["failed"])")
}
"""


class UnwindTests(unittest.TestCase):
    # closes: #577
    def test_unwind_is_in_reverse_completion_order(self):
        """`charge` completed after `reserve`, so `refund` runs before `release`.

        A causal chain deliberately: these steps do no I/O, so every
        `finished_at` in this workflow can carry the same value. Ordering by the
        clock would be arbitrary here — refund-before-uncharge is exactly the
        failure compensation exists to prevent.
        """
        out = _run(SAGA)
        compensation = [line for line in out.splitlines() if line.startswith("R=")][0]
        self.assertLess(
            compensation.index('"step": "refund"'),
            compensation.index('"step": "release"'),
            "compensation ran in the wrong order — later work must unwind first",
        )

    def test_the_compensated_step_binds_by_name(self):
        """`reserve` and `charge` read as their return values in the handler.

        The same rule `after` already uses, which is why the clause needed no new
        scoping concept.
        """
        out = _run(SAGA)
        self.assertIn("refunded ch-1", out)
        self.assertIn("released res-1", out)

    def test_handlers_do_not_appear_in_statuses(self):
        """`steps`, `statuses` and `failed` describe the forward run.

        Keeping handlers out of them is also what avoids an eighth
        `TASK_STATUSES` entry.
        """
        out = _run(SAGA)
        statuses = [line for line in out.splitlines() if line.startswith("S=")][0]
        self.assertNotIn("release", statuses)
        self.assertNotIn("refund", statuses)
        self.assertIn('"ship": "failed"', statuses)

    def test_a_completed_run_does_not_unwind(self):
        out = _run(
            "workflow ok {\n"
            '    step reserve { return "res" }\n'
            '    step release compensates reserve { return "released" }\n'
            "}\n"
            'fn main() { let r = run_workflow(ok); print("C=\\(has_key(r, "compensation"))") }\n'
        )
        self.assertIn("C=false", out)

    def test_a_tolerated_failure_does_not_unwind(self):
        """`allow_failure` means the run *completes*; a completed run has nothing
        to undo. No special case was needed — the trigger reads `failed`, which
        is empty for a tolerated failure."""
        out = _run(
            "workflow saga {\n"
            '    step reserve { return "res" }\n'
            '    step flaky after reserve with { allow_failure: true } { throw "t" }\n'
            '    step release compensates reserve { return "released" }\n'
            "}\n"
            "fn main() { let r = run_workflow(saga)\n"
            '    print("C=\\(has_key(r, "compensation")) T=\\(r["tolerated"])") }\n'
        )
        self.assertIn("C=false", out)
        self.assertIn('T=["flaky"]', out)

    def test_a_failing_handler_is_recorded_and_does_not_cascade(self):
        """Deliberately not Argo's behaviour, where an exit handler can fail the
        workflow status. There is no status left to change — the run is already
        `failed`."""
        out = _run(
            "workflow saga {\n"
            '    step reserve { return "res" }\n'
            '    step ship after reserve { throw "boom" }\n'
            '    step release compensates reserve { throw "gateway down" }\n'
            "}\n"
            "fn main() { let r = run_workflow(saga)\n"
            '    print("R=\\(r["compensation"]) F=\\(r["failed"])") }\n'
        )
        self.assertIn('"status": "failed"', out)
        self.assertIn("gateway down", out)
        self.assertIn('F=["ship"]', out)


class TerminalityTests(unittest.TestCase):
    def test_a_compensated_run_cannot_be_resumed(self):
        """Its completed work has been undone, and a resume *re-executes*
        (#494 / I-WFLOW-06) — so resuming would re-run steps against a remote
        already refunded."""
        out = _run(
            "workflow saga {\n"
            '    step reserve { checkpoint "reserved"\n        return "res" }\n'
            '    step ship after reserve { throw "carrier down" }\n'
            '    step release compensates reserve { return "released" }\n'
            "}\n"
            "fn main() {\n"
            "    let r = run_workflow(saga)\n"
            '    let again = resume_workflow(r["graph_id"], "reserved")\n'
            '    print("A=\\(again)")\n'
            "}\n"
        )
        self.assertIn('"ok": false', out)
        self.assertIn("was compensated", out)


class DeclarationRefusalTests(unittest.TestCase):
    """Refused at declaration. Each could only ever be inert or ambiguous."""

    def _refuse(self, source: str) -> str:
        with self.assertRaises(Exception) as caught:
            Parser(tokenize(source)).parse()
        return str(caught.exception)

    def test_a_handler_cannot_declare_after(self):
        message = self._refuse(
            "workflow s { step a { return 1i } "
            "step b compensates a after a { return 2i } }"
        )
        self.assertIn("cannot declare `after`", message)

    def test_a_handler_cannot_declare_each(self):
        """Checked before `after`, because `each x in src` puts `src` in `deps`
        — testing `deps` first would refuse it with the `after` message and send
        the author looking for a clause they did not write."""
        message = self._refuse(
            "workflow s { step a { return [1i] } "
            "step b compensates a each x in a { return 2i } }"
        )
        self.assertIn("cannot declare `each`", message)

    def test_a_handler_cannot_declare_when(self):
        message = self._refuse(
            'workflow s { step a { checkpoint "c"\n return 1i } '
            'step b compensates a when reached("c") { return 2i } }'
        )
        self.assertIn("cannot declare `when`", message)

    def test_a_step_cannot_compensate_itself(self):
        message = self._refuse("workflow s { step a compensates a { return 1i } }")
        self.assertIn("compensates itself", message)

    def test_compensates_is_still_usable_as_an_identifier(self):
        """Contextual, like every keyword added since 4.1.0."""
        out = _run("fn main() { let compensates = 41i; print(compensates + 1i) }")
        self.assertIn("42", out)


class OrderingSourceTests(unittest.TestCase):
    def test_the_unwind_sorts_on_completion_seq_not_a_timestamp(self):
        """Source assertion, because the behavioural test cannot distinguish them
        on a machine whose clock happens to be fine.

        `finished_at` is `time.monotonic()`, ~15.6 ms here, so a causal chain
        ties. A future edit that sorted on it would pass every behavioural test
        on Linux and be arbitrary on Windows — the worst shape available.

        Read from the AST with the docstring dropped, not by substring: the
        first version of this test matched `finished_at` inside the docstring
        that explains why not to use it, and failed on itself — the
        self-matching trap this repo has produced before.
        """
        import ast
        import inspect

        from nodus.orchestration import task_graph

        tree = ast.parse(inspect.getsource(task_graph))
        unwind = next(
            node for node in ast.walk(tree)
            if isinstance(node, ast.FunctionDef) and node.name == "_run_compensation"
        )
        body = list(unwind.body)
        if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant):
            body = body[1:]  # drop the docstring
        code = "\n".join(ast.unparse(node) for node in body)

        self.assertIn("completion_seq", code)
        self.assertNotIn("finished_at", code)


if __name__ == "__main__":
    unittest.main()
