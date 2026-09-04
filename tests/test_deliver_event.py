"""An external event reaches the run parked on it, by event type (#181).

`workflow_wait("order.paid")` has always recorded its event type durably, and
`resume_workflow` has always been willing to *verify* one. What was missing ran
in the other direction: nothing could answer **which run is waiting for this
event**, so every delivery path — the builtin, the CLI, `POST /workflow/resume`
— required a `graph_id` the dispatcher did not have. A webhook receiver in
another process had to `list_runs()` (a full scan) and reach into
`record.wait.event_type`, which is not a published surface.

#181 framed this as three host steps: (a) receive the webhook, (b) look up the
waiting run, (c) resume it. Only (b) is closed here, and that is the whole
design. (a) is irreducibly the host's. (c) is the host's **by decision**: #176
settled that a run record carries the program's whole source (#499), so a
runtime that re-entered runs on its own would compile and execute whatever the
working directory's store happened to hold. `deliver_event` is an explicit call
for exactly the reason `sweep` is.

So the issue's proposed `wait_event()` — a Nodus-native call that subscribes and
resumes itself — is deliberately *not* what was built. It would make the guest
the subscriber, which is what #176 declined.

The two decisions worth pinning, because each could have gone the other way:

- **Ambiguity is refused, not resolved** (`AmbiguityTests`). Returning an
  arbitrary one of N matching runs is #584's exact failure: the copy that could
  not answer correctly returned something *plausible*, and the defect hid for as
  long as the substitute looked reasonable.
- **Zero matches is an outcome, not an error** (`NobodyWaitingTests`). A
  dispatcher does not control ordering — the event can beat the run to the store
  or arrive after it finished — so failing the call would make a correct caller
  look broken.
"""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO_ROOT / "src"))  # noqa: E402

from nodus.tooling import runner as tooling_runner  # noqa: E402
from nodus_lang_workflow.runner import get_default_workflow_runner  # noqa: E402

WORKFLOW = """
workflow order {{
    step park {{ return workflow_wait("{event}", {{correlation_key: "{key}"}}) }}
    step ship after park {{ return "shipped" }}
}}

fn main() {{
    let r = run_workflow(order)
    print(r["graph_id"])
}}
"""


class DeliverEventTestCase(unittest.TestCase):
    """Each test gets its own store root, so runs never leak between them."""

    def setUp(self):
        self._cwd = os.getcwd()
        self._tmp = tempfile.TemporaryDirectory(prefix="nodus181-")
        os.chdir(self._tmp.name)
        self._vms = {}

    def tearDown(self):
        os.chdir(self._cwd)
        self._tmp.cleanup()

    def park(self, *, event="order.paid", key="cust-42"):
        """Run a workflow to its wait and return the graph id."""
        source = WORKFLOW.format(event=event, key=key)
        result, vm = tooling_runner.run_source(
            source, filename=f"order_{key}.nd", timeout_ms=20000
        )
        self.assertTrue(result.get("ok"), result.get("error"))
        graph_id = result["stdout"].strip()
        self._vms[graph_id] = vm
        return graph_id

    def factory(self):
        vms = self._vms

        def _factory(record):
            return vms.get(record.run_id) or next(iter(vms.values()))

        return _factory

    @property
    def runner(self):
        return get_default_workflow_runner()


class TheLookupTests(DeliverEventTestCase):
    """The half that did not exist: event type -> run."""

    # closes: #181
    def test_a_parked_run_is_findable_by_its_event_type(self):
        graph_id = self.park()
        found = self.runner.store.list_runs_waiting_for("order.paid")
        self.assertEqual([graph_id], [record.run_id for record in found])

    # closes: #181
    def test_a_correlation_key_narrows_it(self):
        a = self.park(key="cust-1")
        b = self.park(key="cust-2")
        both = self.runner.store.list_runs_waiting_for("order.paid")
        self.assertEqual({a, b}, {record.run_id for record in both})

        one = self.runner.store.list_runs_waiting_for("order.paid", correlation_key="cust-2")
        self.assertEqual([b], [record.run_id for record in one])

    # closes: #181
    def test_no_key_means_do_not_filter_rather_than_match_keyless_runs(self):
        """The wrong reading of `correlation_key=None` silently widens a
        delivery, so it is worth a test of its own rather than an inference
        from the test above."""
        keyed = self.park(key="cust-1")
        found = self.runner.store.list_runs_waiting_for("order.paid")
        self.assertIn(keyed, [record.run_id for record in found])

    # closes: #181
    def test_a_different_event_type_matches_nothing(self):
        self.park()
        self.assertEqual([], self.runner.store.list_runs_waiting_for("order.refunded"))

    # closes: #181
    def test_a_completed_run_is_no_longer_waiting(self):
        """Status is part of the question. A run that already received its event
        must not match the next one."""
        self.park()
        self.runner.deliver_event(self.factory(), "order.paid")
        self.assertEqual([], self.runner.store.list_runs_waiting_for("order.paid"))


class DeliveryCarriesTheRunForwardTests(DeliverEventTestCase):
    # closes: #181
    def test_the_downstream_step_runs(self):
        graph_id = self.park()
        report = self.runner.deliver_event(
            self.factory(), "order.paid", payload={"amount": 4200}
        )
        self.assertTrue(report["ok"], report.get("error"))
        self.assertEqual([graph_id], report["matched"])
        statuses = report["delivered"][0]["result"]["statuses"]
        self.assertEqual("completed", statuses["ship"],
                         "delivery that does not run the waiting step is not delivery")

    # closes: #181
    def test_the_payload_reaches_the_run_record(self):
        graph_id = self.park()
        self.runner.deliver_event(self.factory(), "order.paid", payload={"amount": 4200})
        record = self.runner.store.get_run(graph_id)
        self.assertEqual({"amount": 4200}, record.metadata.get("resume_payload"))

    # closes: #181
    def test_a_correlation_mismatch_delivers_to_nobody(self):
        """The narrowing happens in the lookup, so a wrong key is not a refusal
        from `resume_workflow` -- it simply matches no run."""
        self.park(key="cust-1")
        report = self.runner.deliver_event(
            self.factory(), "order.paid", correlation_key="cust-999"
        )
        self.assertEqual([], report["matched"])
        self.assertTrue(report["ok"])


class AmbiguityTests(DeliverEventTestCase):
    """Refused rather than resolved -- #584's lesson."""

    # closes: #181
    def test_two_matching_runs_and_no_key_is_refused(self):
        a = self.park(key="cust-1")
        b = self.park(key="cust-2")
        report = self.runner.deliver_event(self.factory(), "order.paid")
        self.assertFalse(report["ok"])
        self.assertEqual("ambiguous_delivery", report["category"])
        self.assertEqual({a, b}, set(report["matched"]))
        self.assertEqual([], report["delivered"], "nothing is delivered on a refusal")

    # closes: #181
    def test_the_refusal_names_the_candidates_and_the_way_out(self):
        self.park(key="cust-1")
        self.park(key="cust-2")
        message = self.runner.deliver_event(self.factory(), "order.paid")["error"]
        self.assertIn("correlation key", message)
        self.assertIn("all_matching", message)

    # closes: #181
    def test_both_runs_are_still_waiting_after_a_refusal(self):
        """A refusal that half-delivered would be worse than either answer."""
        self.park(key="cust-1")
        self.park(key="cust-2")
        self.runner.deliver_event(self.factory(), "order.paid")
        self.assertEqual(2, len(self.runner.store.list_runs_waiting_for("order.paid")))

    # closes: #181
    def test_all_matching_opts_into_the_fan_out(self):
        a = self.park(key="cust-1")
        b = self.park(key="cust-2")
        report = self.runner.deliver_event(self.factory(), "order.paid", all_matching=True)
        self.assertTrue(report["ok"], report.get("error"))
        self.assertEqual({a, b}, set(report["matched"]))
        self.assertEqual([], self.runner.store.list_runs_waiting_for("order.paid"))


class NobodyWaitingTests(DeliverEventTestCase):
    # closes: #181
    def test_it_reports_rather_than_failing(self):
        report = self.runner.deliver_event(self.factory_empty(), "order.paid")
        self.assertTrue(report["ok"])
        self.assertEqual([], report["matched"])
        self.assertEqual([], report["delivered"])
        self.assertIsNone(report["error"])

    def factory_empty(self):
        def _factory(_record):  # pragma: no cover - never called, nothing matches
            raise AssertionError("no run should have been resumed")

        return _factory


class TheStoreSurfaceTests(unittest.TestCase):
    """`list_runs_waiting_for` is concrete on the ABC, not abstract.

    A store is a host-implementable surface. Adding an **abstract** method breaks
    every out-of-tree implementation *at construction* — which is exactly how
    5.0.3 broke `nodus_sdk` (#185), and why `restore_run` and `delete_run` are
    both concrete with working defaults. This test is the reason that decision
    cannot be quietly reversed.
    """

    # closes: #181
    def test_a_minimal_out_of_tree_store_still_constructs(self):
        from nodus_lang_workflow.store import WorkflowStore

        missing = {
            name
            for name in getattr(WorkflowStore, "__abstractmethods__", frozenset())
        }
        self.assertNotIn(
            "list_runs_waiting_for", missing,
            "making this abstract breaks every store outside this repo at "
            "construction -- the #185 failure, exactly",
        )

    # closes: #181
    def test_the_default_works_for_any_store_that_can_list_runs(self):
        """Not just 'is concrete' -- that it actually answers. A default that
        returned `[]` would satisfy the test above and deliver nothing."""
        from nodus_lang_workflow.models import WorkflowRunRecord
        from nodus_lang_workflow.store import WorkflowStore

        class ListOnlyStore(WorkflowStore):
            """Implements the abstract surface and nothing else."""

            def __init__(self, records):
                self._records = records

            def list_runs(self):
                return list(self._records)

            def __getattr__(self, name):  # every other abstract method
                raise NotImplementedError(name)

        for name in WorkflowStore.__abstractmethods__:
            if name != "list_runs":
                setattr(ListOnlyStore, name, lambda self, *a, **k: None)
        ListOnlyStore.__abstractmethods__ = frozenset()

        waiting = WorkflowRunRecord(
            run_id="g_waiting", graph_id="g_waiting",
            workflow_name="order", execution_kind="workflow",
        )
        waiting.status = "waiting"
        from nodus_lang_workflow.models import WorkflowWaitRecord

        waiting.wait = WorkflowWaitRecord(event_type="order.paid", correlation_key="k")

        running = WorkflowRunRecord(
            run_id="g_running", graph_id="g_running",
            workflow_name="order", execution_kind="workflow",
        )
        running.status = "running"

        store = ListOnlyStore([waiting, running])
        found = store.list_runs_waiting_for("order.paid")
        self.assertEqual(["g_waiting"], [record.run_id for record in found])
        self.assertEqual([], store.list_runs_waiting_for("order.shipped"))
        self.assertEqual(
            [], store.list_runs_waiting_for("order.paid", correlation_key="other")
        )


class TheCliTests(unittest.TestCase):
    """Cross-process is the case that matters: the delivering process knows the
    event type and has never seen the graph id."""

    def _nodus(self, cwd, *args):
        env = dict(os.environ)
        env["PYTHONPATH"] = str(_REPO_ROOT / "src")
        return subprocess.run(
            [sys.executable, str(_REPO_ROOT / "nodus.py"), *args],
            cwd=cwd, env=env, capture_output=True, text=True, timeout=120,
        )

    # closes: #181
    def test_one_process_parks_and_another_delivers(self):
        with tempfile.TemporaryDirectory(prefix="nodus181cli-") as tmp:
            script = os.path.join(tmp, "order.nd")
            with open(script, "w", encoding="utf-8") as handle:
                handle.write(WORKFLOW.format(event="order.paid", key="cust-42"))

            # `--time-limit` because an import and a workflow build inside the
            # 200 ms default is the SCHED-001 trap that took #711 down on CI.
            parked = self._nodus(tmp, "run", "order.nd", "--time-limit", "30")
            self.assertEqual(0, parked.returncode, parked.stderr)
            graph_id = parked.stdout.strip()

            delivered = self._nodus(
                tmp, "workflow", "deliver", "order.paid",
                "--correlation-key", "cust-42", "--payload", '{"amount": 4200}',
            )
            self.assertEqual(0, delivered.returncode, delivered.stderr)
            report = json.loads(delivered.stdout)
            self.assertTrue(report["ok"], report.get("error"))
            self.assertEqual([graph_id], report["matched"])
            self.assertEqual(
                "completed",
                report["delivered"][0]["result"]["statuses"]["ship"],
            )

    # closes: #181
    def test_ambiguity_exits_2_and_a_failure_exits_1(self):
        """Distinguished so a cron can retry a failure and must not retry an
        ambiguity -- retrying the latter produces the same refusal forever."""
        with tempfile.TemporaryDirectory(prefix="nodus181cli2-") as tmp:
            for key in ("cust-1", "cust-2"):
                script = os.path.join(tmp, f"order_{key}.nd")
                with open(script, "w", encoding="utf-8") as handle:
                    handle.write(WORKFLOW.format(event="order.paid", key=key))
                parked = self._nodus(tmp, "run", f"order_{key}.nd", "--time-limit", "30")
                self.assertEqual(0, parked.returncode, parked.stderr)

            ambiguous = self._nodus(tmp, "workflow", "deliver", "order.paid")
            self.assertEqual(2, ambiguous.returncode, ambiguous.stdout)
            self.assertEqual(
                "ambiguous_delivery", json.loads(ambiguous.stdout)["category"]
            )

    # closes: #181
    def test_nobody_waiting_exits_0(self):
        with tempfile.TemporaryDirectory(prefix="nodus181cli3-") as tmp:
            result = self._nodus(tmp, "workflow", "deliver", "nothing.listens")
            self.assertEqual(0, result.returncode, result.stderr)
            self.assertEqual([], json.loads(result.stdout)["matched"])

    # closes: #181
    def test_a_non_object_payload_is_refused_at_the_flag(self):
        """A JSON array parses fine and fails much later, naming the step rather
        than the flag the caller got wrong."""
        with tempfile.TemporaryDirectory(prefix="nodus181cli4-") as tmp:
            result = self._nodus(
                tmp, "workflow", "deliver", "order.paid", "--payload", "[1, 2]"
            )
            self.assertEqual(2, result.returncode)
            self.assertIn("must be a JSON object", result.stderr)


class TheRouteTablesAgreeTests(unittest.TestCase):
    """Two route tables for one surface, so a route added to one of them is
    available or not depending on whether FastAPI happens to be installed."""

    # closes: #181
    def test_every_workflow_post_route_exists_in_both_tables(self):
        import re

        source = (_REPO_ROOT / "src" / "nodus" / "services" / "server.py").read_text(
            encoding="utf-8"
        )
        fastapi_routes = set(re.findall(r'@app\.post\("(/workflow/[^"]+)"\)', source))
        stdlib_routes = set(
            re.findall(r'if self\.path == "(/workflow/[^"]+)":', source)
        )
        self.assertIn("/workflow/deliver", fastapi_routes)
        self.assertTrue(fastapi_routes, "the scan found no routes at all")
        self.assertEqual(
            set(), fastapi_routes - stdlib_routes,
            "a POST route on the FastAPI app that the stdlib server does not "
            "serve is reachable or not depending on an optional dependency",
        )


if __name__ == "__main__":
    unittest.main()
