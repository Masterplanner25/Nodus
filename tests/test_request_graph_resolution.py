"""A graph response names the graph *this request* produced, or none (#584).

`_graph_metadata` fell back to `latest_graph_state()` when it could not resolve a
graph id. That helper read the process-global `.nodus/graphs/`, sorted the
filenames, and returned the last one — but graph ids are `uuid4().hex[:8]`, so
sorting them lexicographically orders them by nothing. It returned an arbitrary
graph and called it "latest".

Two consequences, and the second is the one that matters:

  - the name was wrong: `latest_graph_state()` disagreed with the genuinely
    newest graph as soon as the directory held more than one, with probability
    1 - 1/n;
  - a request that declared **no graph at all** was answered with another
    request's graph id, status and full task map — step return values included.

So sorting by mtime would not have been a fix. It would have picked a different
stranger. The question "which graph is newest on this disk" is not the question
`graph_run` is asking, which is "which graph did *I* just produce".

The fallback was also doing a second job nobody had noticed: in `services/api.py`
it was the *only* thing that resolved a `run_workflow`'s graph, because
`last_graph_plan` is set by `plan_workflow` and not by `run_workflow`. It gave
the right answer whenever the directory happened to hold exactly one graph.
Deleting it alone therefore broke the feature while closing the leak — which is
why the positive control below is not decoration.
"""

import os
import pathlib
import sys
import tempfile
import unittest

REPO = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "src"))

from nodus.services.api import ExecutionState  # noqa: E402
from nodus.services.graph_metadata import (  # noqa: E402
    graph_metadata,
    resolve_request_graph_id,
)


WORKFLOW = """
workflow secret_pipeline {
    step gather { return "customer-records" }
    step ship after gather { return "sent-to-vendor" }
}
let r = run_workflow(secret_pipeline)
"""

NO_GRAPH = 'print("just arithmetic: \\(1i + 1i)")'


class _InTempCwd(unittest.TestCase):
    """The graph store is CWD-relative, so each test gets its own."""

    def setUp(self):
        self._previous = os.getcwd()
        self._tmp = tempfile.TemporaryDirectory()
        os.chdir(self._tmp.name)

    def tearDown(self):
        os.chdir(self._previous)
        try:
            self._tmp.cleanup()
        except OSError:
            pass  # a sweeper thread may still hold a file; the dir is temp anyway


# closes: #584
class RequestGraphResolutionTests(_InTempCwd):

    def test_a_run_reports_its_own_graph(self):
        """The positive control, and it is load-bearing.

        Removing the leaking fallback without adding request-scoped resolution
        left this returning `graph_id: None` for a workflow that had just run —
        the leak closed by breaking the feature. Observed, then fixed.
        """
        state = ExecutionState()
        result = state.graph_run({"code": WORKFLOW, "filename": "a.nd"})
        self.assertIsNotNone(result.get("graph_id"))
        self.assertEqual(2, len(result.get("tasks") or {}))
        self.assertEqual("completed", result.get("graph_status"))

    def test_a_request_with_no_graph_gets_no_graph(self):
        state = ExecutionState()
        state.graph_run({"code": WORKFLOW, "filename": "a.nd"})
        second = state.graph_run({"code": NO_GRAPH, "filename": "b.nd"})
        self.assertIsNone(second.get("graph_id"))
        self.assertEqual({}, second.get("tasks"))
        self.assertIsNone(second.get("graph_status"))

    def test_no_step_result_from_another_request_appears_in_the_response(self):
        """The leak, stated as what a reader would actually lose.

        Before the fix, `second` carried `"customer-records"` and
        `"sent-to-vendor"` — the first request's step return values.
        """
        state = ExecutionState()
        first = state.graph_run({"code": WORKFLOW, "filename": "a.nd"})
        self.assertIn("customer-records", repr(first.get("tasks")),
                      "the control never ran; this test would pass vacuously")

        second = state.graph_run({"code": NO_GRAPH, "filename": "b.nd"})
        rendered = repr(second)
        self.assertNotIn("customer-records", rendered)
        self.assertNotIn("sent-to-vendor", rendered)
        self.assertNotIn(first["graph_id"], rendered)

    def test_a_plan_still_resolves_through_last_graph_plan(self):
        state = ExecutionState()
        result = state.graph_plan({
            "code": "workflow w { step s { return 1i } }\nlet p = plan_workflow(w)",
            "filename": "p.nd",
        })
        self.assertIsNotNone(result.get("graph_id"))

    def test_an_explicit_graph_id_still_wins(self):
        state = ExecutionState()
        first = state.graph_run({"code": WORKFLOW, "filename": "a.nd"})
        again = graph_metadata(None, first["graph_id"])
        self.assertEqual(first["graph_id"], again["graph_id"])
        self.assertEqual(2, len(again["tasks"]))


class ResolutionReadsOnlyThisRequestTests(_InTempCwd):

    def test_resolution_returns_none_without_a_vm(self):
        self.assertIsNone(resolve_request_graph_id(None))

    def test_resolution_never_reads_the_shared_graph_directory(self):
        """The property that makes this a fix rather than a better guess.

        With graphs on disk and a VM that produced none, resolution must still
        answer None. A version that sorted `.nodus/graphs/` by mtime would pass
        every other test in this file and fail this one.
        """
        state = ExecutionState()
        state.graph_run({"code": WORKFLOW, "filename": "a.nd"})

        graphs = pathlib.Path(".nodus", "graphs")
        on_disk = [p for p in graphs.iterdir() if p.suffix == ".json"] if graphs.is_dir() else []
        self.assertTrue(on_disk, "no graph was persisted, so this proves nothing")

        class _Bare:
            last_graph_plan = None
            event_bus = None

        self.assertIsNone(resolve_request_graph_id(_Bare()))
        self.assertEqual(
            {"graph_id": None, "tasks": {}, "graph_status": None},
            graph_metadata(_Bare()),
        )


class OneImplementationTests(unittest.TestCase):
    """`api.py` and `server.py` each had a copy and they had drifted — the
    server scanned the VM's own graph events and the api did not, which is why
    the api needed a global fallback at all. Keep it to one."""

    def test_neither_service_resolves_a_graph_id_of_its_own(self):
        for rel in ("src/nodus/services/api.py", "src/nodus/services/server.py"):
            body = (REPO / rel).read_text(encoding="utf-8")
            with self.subTest(module=rel):
                self.assertIn("from nodus.services.graph_metadata import graph_metadata", body)
                self.assertNotIn("last_graph_plan", body,
                                 f"{rel} resolves a graph id itself again")
                self.assertNotIn("graph_persist", body,
                                 f"{rel} scans graph events itself again")

    def test_the_leaking_helper_is_gone(self):
        task_graph = (REPO / "src/nodus/orchestration/task_graph.py").read_text(encoding="utf-8")
        self.assertNotIn("def latest_graph_state", task_graph)

        offenders = []
        for path in (REPO / "src").rglob("*.py"):
            if "latest_graph_state" in path.read_text(encoding="utf-8"):
                offenders.append(path.relative_to(REPO).as_posix())
        self.assertEqual(
            ["src/nodus/services/graph_metadata.py"], offenders,
            "`latest_graph_state` is referenced outside the note explaining its removal",
        )


if __name__ == "__main__":
    unittest.main()
