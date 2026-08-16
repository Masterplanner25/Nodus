"""Step-level `retries` behave the same on every entry point and both flow kinds.

#392 — `with { retries: N }` was honoured only by `nodus workflow-run`, the one
caller that passed `inline_retries=True`. Every other entry point made one
attempt, dropped the deferral, and returned success.

#393 — `workflow` deferred its retry and `goal` retried in-process, from the same
`execution_kind` branch, on two constructs documented as identical.

Both are the same defect: the retry policy read the keyword you wrote and the
caller you used, when the only thing that should decide is whether a sweeper
exists to resume a deferred run.
"""

import io
import os
import sys
import tempfile
import unittest

sys.path.insert(0, "C:/dev/Coding Language/src")

from nodus.cli import cli as nodus_cli  # noqa: E402
from nodus.runtime.embedding import NodusRuntime  # noqa: E402
from nodus.tooling.runner import run_workflow_code  # noqa: E402
from nodus.vm.vm import VM  # noqa: E402
from nodus_lang_workflow.models import RUN_STATUS_RETRY_SCHEDULED  # noqa: E402
from nodus_lang_workflow.runner import (  # noqa: E402
    WorkflowFrameworkRunner,
    retry_sweeper,
    retry_sweeper_active,
)
from nodus_lang_workflow.store import LocalWorkflowStore  # noqa: E402


# Fails twice, succeeds on the third attempt. With `retries: 2` honoured the
# step completes; without, it stops after attempt 1.
FLOW_BODY = """
let c = {"n": 0i}
%(kind)s main {
    step flaky with { retries: 2, retry_delay_ms: 1 } {
        c["n"] = c["n"] + 1i
        print("attempt \\(c["n"])")
        if (c["n"] < 3i) { throw "boom" }
        return c["n"]
    }
}
"""

DRIVER = """
let r = run_%(kind)s(main)
print("attempts=\\(c["n"])")
print("deferred=\\(has_key(r, "status"))")
"""


def _source(kind: str, *, driver: bool) -> str:
    src = FLOW_BODY % {"kind": kind}
    if driver:
        src += DRIVER % {"kind": kind}
    return src


def _attempts(stdout: str) -> int:
    return sum(1 for line in stdout.splitlines() if line.startswith("attempt "))


def _framework_store(project_root: str) -> LocalWorkflowStore:
    return LocalWorkflowStore(root=os.path.join(project_root, ".nodus", "workflow_framework"))


class _TempProject:
    """A scratch project root, so runs land in its store and not the repo's (#380)."""

    def __enter__(self):
        self._td = tempfile.TemporaryDirectory()
        self.root = self._td.__enter__()
        self._ctx = nodus_cli._project_root_context(self.root)
        self._ctx.__enter__()
        return self

    def __exit__(self, *exc):
        self._ctx.__exit__(*exc)
        return self._td.__exit__(*exc)

    def write(self, name: str, source: str) -> str:
        path = os.path.join(self.root, name)
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(source)
        return path


# _TIMING — why these tests pin an explicit time limit.
#
# The CLI's default deadline is 200 ms (`EXECUTION_TIMEOUT_MS`). Measured on an
# idle machine, three attempts of a *trivial* retrying step cost ~110 ms warm and
# 801 ms on the first (cold) run — mostly graph-state persistence, one write per
# attempt. That is ~1.5x headroom warm and negative cold, against CLAUDE.md's
# rule of 5-10x.
#
# This is a consequence of #392 rather than a quirk of the tests: retries used to
# be deferred (and dropped), so they cost nothing; now they are taken in-process
# and spend the budget. These tests are about retry *semantics*, so they pin a
# generous limit and leave deadline behaviour to the tests that are about
# deadlines. `nodus workflow-run` gained `--time-limit` for this — it was the one
# run command without it.


def _cli(argv) -> tuple[int, str]:
    buf = io.StringIO()
    old = sys.stdout
    sys.stdout = buf
    try:
        rc = nodus_cli.main(argv)
    finally:
        sys.stdout = old
    return rc, buf.getvalue()


# ---------------------------------------------------------------------------
# #392 — every entry point honours `retries`
# ---------------------------------------------------------------------------


# closes: #392
class RetriesHonouredOnEveryEntryPointTests(unittest.TestCase):
    """The table in #392: every entry point, one retry policy.

    The table listed five rows; the `inline_retries=True` one is gone with the
    parameter, leaving the four below plus the exhaustion case.

    Each case asserts the *attempt count*, not just `ok`. `ok: True` was exactly
    what the broken paths returned — a success-shaped result for a run that made
    one attempt and abandoned the rest.
    """

    def test_run_workflow_code_default_honours_retries(self):
        # The path `docs/guide/real-world-integration.md` teaches. It took no
        # `inline_retries` argument, so it dropped the retry.
        with _TempProject() as project:
            source = _source("workflow", driver=False)
            path = project.write("wf.nd", source)
            result, _vm = run_workflow_code(
                VM([], {}, code_locs=[], source_path=None),
                source,
                filename=path,
                project_root=project.root,
                timeout_ms=None,   # see _TIMING note below
            )
        self.assertTrue(result.get("ok"), result)
        self.assertEqual(_attempts(result["stdout"]), 3)
        self.assertNotIn("status", result["result"])
        self.assertEqual(result["result"]["steps"]["flaky"], 3)

    def test_embedding_run_source_honours_retries(self):
        # The worst case in #392: NodusRuntime returned ok:True after one attempt,
        # leaving a host nothing to branch on. This is the nodus-mcp-server path.
        with _TempProject():
            result = NodusRuntime().run_source(_source("workflow", driver=True), filename="wf.nd")
        self.assertTrue(result.get("ok"), result)
        self.assertEqual(_attempts(result["stdout"]), 3)
        self.assertIn("attempts=3", result["stdout"])

    def test_nodus_run_honours_retries(self):
        # `nodus run` on a script that calls run_workflow() in-language.
        with _TempProject() as project:
            path = project.write("wf_run.nd", _source("workflow", driver=True))
            rc, out = _cli(["nodus", "run", path, "--time-limit", "30000"])
        self.assertEqual(rc, 0, out)
        self.assertEqual(_attempts(out), 3)
        self.assertIn("attempts=3", out)

    def test_workflow_run_still_honours_retries(self):
        # The one path #226 fixed. It must keep working now that its wrapper
        # loop is gone and the callee retries instead.
        with _TempProject() as project:
            path = project.write("wf.nd", _source("workflow", driver=False))
            rc, out = _cli(["nodus", "workflow-run", path, "--time-limit", "30000"])
        self.assertEqual(rc, 0, out)
        self.assertEqual(_attempts(out), 3)

    def test_embedding_reports_failure_once_retries_are_exhausted(self):
        # In-process retry must not turn exhaustion into silent success either.
        source = """
let c = {"n": 0i}
workflow main {
    step doomed with { retries: 2, retry_delay_ms: 1 } {
        c["n"] = c["n"] + 1i
        print("attempt \\(c["n"])")
        throw "boom"
    }
}
let r = run_workflow(main)
print("failed=\\(len(r["failed"]))")
"""
        with _TempProject():
            result = NodusRuntime().run_source(source, filename="wf.nd")
        self.assertEqual(_attempts(result["stdout"]), 3)
        self.assertIn("failed=1", result["stdout"])


# ---------------------------------------------------------------------------
# #393 — goal and workflow agree
# ---------------------------------------------------------------------------


# closes: #393
class GoalAndWorkflowRetryIdenticallyTests(unittest.TestCase):
    """`run_task_graph` no longer branches on `execution_kind` for retries."""

    def _run(self, kind: str) -> dict:
        with _TempProject():
            return NodusRuntime().run_source(_source(kind, driver=True), filename=f"{kind}.nd")

    def test_both_kinds_make_the_same_number_of_attempts(self):
        workflow = self._run("workflow")
        goal = self._run("goal")
        self.assertEqual(_attempts(workflow["stdout"]), _attempts(goal["stdout"]))
        self.assertEqual(_attempts(goal["stdout"]), 3)

    def test_neither_kind_defers_without_a_sweeper(self):
        self.assertFalse(retry_sweeper_active())
        for kind in ("workflow", "goal"):
            with self.subTest(kind=kind):
                self.assertIn("deferred=false", self._run(kind)["stdout"])

    def test_the_retry_decision_does_not_name_a_flow_kind(self):
        # Guards the shape of the fix, not only its effect: reintroducing an
        # `execution_kind == "workflow"` test inside _fail_task is what this
        # issue is about, and it would still pass the behavioural assertions
        # above on the goal side alone.
        #
        # The decision may ask whether the run is durable at all — a bare
        # `run_graph` is registered in no store and must never defer — but it
        # must not distinguish `workflow` from `goal`.
        import inspect

        from nodus.orchestration import task_graph

        source = inspect.getsource(task_graph.run_task_graph)
        start = source.index("if task.attempts <= task.max_retries:")
        end = source.index('task.status = "failed"', start)
        retry_decision = source[start:end]
        self.assertIn("_retry_is_swept()", retry_decision)
        self.assertNotIn("execution_kind", retry_decision)
        self.assertNotIn('"workflow"', retry_decision.split("emit_event")[0])

    def test_a_bare_task_graph_never_defers(self):
        # run_graph() results are registered in no workflow store, so a deferred
        # retry there would be lost outright — the #392 failure one layer down.
        source = """
let state = {"n": 0i}
let A = task(fn() {
    state["n"] = state["n"] + 1i
    if (state["n"] < 3i) { throw "boom" }
    return state["n"]
}, { "retries": 2, "retry_delay_ms": 1 })
let r = run_graph([A])
print("attempts=\\(r["attempts"]["task_1"])")
"""
        with _TempProject():
            with retry_sweeper():
                result = NodusRuntime().run_source(source, filename="graph.nd")
        self.assertTrue(result.get("ok"), result)
        self.assertIn("attempts=3", result["stdout"])


# closes: #393
class DeferredRetryStillWorksUnderASweeperTests(unittest.TestCase):
    """Durability is preserved — and now applies to goals too.

    A registered sweeper is the one condition under which `retry_scheduled` is a
    correct answer, so both kinds take it and neither takes it otherwise.
    """

    def _run_deferred(self, kind: str):
        with _TempProject() as project:
            source = _source(kind, driver=True)
            path = project.write(f"{kind}.nd", source)
            with retry_sweeper():
                result = NodusRuntime().run_source(source, filename=path)
            runner = WorkflowFrameworkRunner(_framework_store(project.root))
            records = runner.list_runs()
            return result, [(record.execution_kind, record.status) for record in records]

    def test_workflow_defers_when_a_sweeper_is_registered(self):
        result, records = self._run_deferred("workflow")
        self.assertEqual(_attempts(result["stdout"]), 1)
        self.assertIn("deferred=true", result["stdout"])
        self.assertIn(("workflow", RUN_STATUS_RETRY_SCHEDULED), records)

    def test_goal_defers_when_a_sweeper_is_registered(self):
        # Before the fix a goal retried in-process regardless, so it could never
        # reach the durable store as retry_scheduled.
        result, records = self._run_deferred("goal")
        self.assertEqual(_attempts(result["stdout"]), 1)
        self.assertIn("deferred=true", result["stdout"])
        self.assertIn(("goal", RUN_STATUS_RETRY_SCHEDULED), records)

    def test_registration_is_reentrant_and_withdrawn(self):
        self.assertFalse(retry_sweeper_active())
        with retry_sweeper():
            self.assertTrue(retry_sweeper_active())
            with retry_sweeper():
                self.assertTrue(retry_sweeper_active())
            self.assertTrue(retry_sweeper_active())
        self.assertFalse(retry_sweeper_active())


if __name__ == "__main__":
    unittest.main()
