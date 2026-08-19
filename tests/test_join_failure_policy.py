"""A step declares which dependency outcomes satisfy its join: `with { on: [...] }`.

`after b, c` has always meant *and every one of them produced a value*. That is a
join policy, and it was the only one -- there was no way to say "run this when the
deploy fails", so the cleanup step every pipeline needs could not be expressed in
the graph at all (#475).

The policy is data rather than compiled code, following the precedent set by a
goal's `until` predicate: a join condition you can read before the run is the point,
and a compiled-away one would be no better than a callback.

Falsifiability was checked rather than assumed -- see the note on each class.
"""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))  # noqa: E402

from nodus.orchestration.task_graph import (  # noqa: E402
    DEFAULT_JOIN_ON,
    JOIN_ON_STATES,
    TaskNode,
)
from nodus.runtime.embedding import NodusRuntime  # noqa: E402


def _run(source: str) -> dict:
    with tempfile.TemporaryDirectory() as td:
        cwd = os.getcwd()
        os.chdir(td)
        try:
            return NodusRuntime(timeout_ms=None, max_steps=None).run_source(source)
        finally:
            os.chdir(cwd)


def _statuses(source: str) -> str:
    result = _run(source)
    stdout = result.get("stdout") or ""
    for line in stdout.splitlines():
        if line.startswith("S="):
            return line
    raise AssertionError(f"no status line in {stdout!r} (error={result.get('error')})")


SAGA = """
workflow saga {{
    step deploy {{ {deploy} }}
    step rollback after deploy with {{ on: {on} }} {{ print("ROLLBACK"); return "rolled" }}
    step announce after deploy {{ print("ANNOUNCE"); return "announced" }}
}}
fn main() {{
    let r = run_workflow(saga)
    let st = r["statuses"]
    print("S=\\(st)")
}}
"""


class TheDefaultIsUnchangedTests(unittest.TestCase):
    """`after` still means what it meant. Every other test here is a change in
    behaviour; this one exists so the change cannot leak into workflows that did
    not ask for it."""

    def test_task_node_defaults_to_requiring_completion(self):
        self.assertEqual(TaskNode(task_id="t", function=None).on_states, DEFAULT_JOIN_ON)
        self.assertEqual(DEFAULT_JOIN_ON, frozenset({"completed"}))

    def test_a_failed_dependency_still_blocks_an_undeclared_step(self):
        rendered = _statuses(SAGA.format(deploy='throw "boom"', on='["completed"]'))
        self.assertIn('"announce": "upstream_failed"', rendered)


class AStepCanDeclareItRunsOnFailureTests(unittest.TestCase):
    """Falsifiable: with `_dep_satisfied` reverted to `dep.task_id in results`,
    `rollback` never becomes ready and reports `cancelled` instead of running."""

    def test_a_failure_tolerant_step_runs_when_its_dependency_fails(self):
        result = _run(SAGA.format(deploy='throw "boom"', on='["completed", "failed"]'))
        stdout = result.get("stdout") or ""
        self.assertIn("ROLLBACK", stdout)
        self.assertIn('"rollback": "completed"', stdout)

    def test_it_still_runs_when_the_dependency_succeeds(self):
        result = _run(SAGA.format(deploy='return "v2"', on='["completed", "failed"]'))
        self.assertIn("ROLLBACK", result.get("stdout") or "")

    def test_fail_fast_does_not_suppress_a_step_that_opted_in(self):
        """A failure stops the run scheduling new work. A step declaring
        `on: ["failed"]` is the one case that must be exempt, or the option would
        be unreachable in exactly the situation it exists for."""
        result = _run(SAGA.format(deploy='throw "boom"', on='["failed"]'))
        self.assertIn("ROLLBACK", result.get("stdout") or "")


class AnUnmetConditionIsOmittedNotFailedTests(unittest.TestCase):
    """The distinction is Argo's, and it is what makes the report worth reading:
    `upstream_failed` means something above me broke, `omitted` means the condition
    I declared was not met."""

    def test_a_step_whose_condition_is_not_met_reports_omitted(self):
        rendered = _statuses(SAGA.format(deploy='return "v2"', on='["failed"]'))
        self.assertIn('"rollback": "omitted"', rendered)
        self.assertIn('"deploy": "completed"', rendered)

    def test_an_omitted_step_does_not_run(self):
        result = _run(SAGA.format(deploy='return "v2"', on='["failed"]'))
        self.assertNotIn("ROLLBACK", result.get("stdout") or "")

    def test_an_omitted_step_is_not_a_broken_graph(self):
        """It used to be. A step left pending fell through to the cycle/missing
        dependency branch, so the whole run returned an err record rather than a
        result -- the caller could not even index it."""
        result = _run(SAGA.format(deploy='return "v2"', on='["failed"]'))
        self.assertIsNone(result.get("error"), msg=result.get("error"))
        self.assertIn('"announce": "completed"', result.get("stdout") or "")

    def test_a_real_missing_dependency_is_still_an_error(self):
        """Falsifiability guard for the above: widening the pending check must not
        swallow a graph that genuinely could never run.

        Assert on the returned value, not on a print. `run_workflow` returns an
        err *value* rather than unwinding, so the statement after it runs either
        way -- an earlier version of this test checked that a later `print` did
        not happen and passed for the wrong reason.
        """
        result = _run(
            """
workflow cyc {
    step a after b { return 1i }
    step b after a { return 2i }
}
fn main() {
    let r = run_workflow(cyc)
    print("KIND=\\(type(r))")
    print("MSG=\\(r.message)")
}
"""
        )
        stdout = result.get("stdout") or ""
        self.assertIn("KIND=error", stdout)
        self.assertIn("Dependency cycle detected", stdout)


class UnknownOutcomesAreRefusedTests(unittest.TestCase):
    """A declaration the runtime accepts must bind or be refused. An `on` naming an
    outcome nothing can produce would be silently unsatisfiable -- the
    "declared but not enforced" shape this codebase has five other instances of."""

    def _error_message(self, on_value: str) -> str:
        result = _run(
            """
workflow w {{
    step a {{ return 1i }}
    step b after a with {{ on: {on} }} {{ return 2i }}
}}
fn main() {{ let r = run_workflow(w); print("ran") }}
""".format(on=on_value)
        )
        error = result.get("error") or {}
        return error.get("message", "") if isinstance(error, dict) else str(error)

    def test_a_misspelled_outcome_is_refused(self):
        self.assertIn("unknown outcome 'suceeded'", self._error_message('["suceeded"]'))

    def test_an_empty_list_is_refused(self):
        self.assertIn("could never run", self._error_message("[]"))

    def test_a_non_list_is_refused(self):
        self.assertIn("expects a list", self._error_message('"failed"'))

    def test_the_accepted_vocabulary_is_only_what_a_dependency_can_reach(self):
        """`upstream_failed` and `cancelled` are conclusions drawn once the run
        winds down, so a step waiting on one would never become ready. Accepting
        them here would ship a knob that silently never fires."""
        self.assertEqual(set(JOIN_ON_STATES), {"completed", "failed"})


if __name__ == "__main__":
    unittest.main()
