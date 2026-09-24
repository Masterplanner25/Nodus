"""Rejecting a draft and replaying it with feedback (#870).

A reviewer looking at a parked run wants one of two things, and the checkpoint
argument is what distinguishes them:

| Call | Meaning |
|---|---|
| `resume_workflow(id, {...})` | approve: satisfy the wait, run the rest |
| `resume_workflow(id, "cp", {...})` | reject: replay from `cp` with feedback, park again |
| `resume_workflow(id, "cp")` | refused — nothing would change |

#482 (5.5.0) refused the middle row along with the last, because it believed the
payload was "silently discarded" by the rollback. It was not: measured on 4.0.8,
where the spelling worked, the payload reached `workflow_resume_payload()` in the
replayed step. What it did not do was *satisfy the wait* — which is the whole
point of a rejection.

The capability was never removed, only its spelling. The refusal's condition
includes `event_type is None`, so passing that **verification** argument to the
Python runner skipped it the whole time. These tests pin the two paths to the
same answer so the `.nd` spelling cannot drift back into relying on an accident.

The last class is the one that keeps #482: a checkpoint with no payload really
is a no-op and must stay refused.
"""

import sys
import unittest

sys.path.insert(0, "C:/dev/Coding Language/src")

from nodus.runtime.embedding import NodusRuntime  # noqa: E402

SOURCE = '''
workflow w {
    step draft {
        checkpoint "before_draft"
        let p = workflow_resume_payload()
        return {"fb": str(p)}
    }
    step gate after draft { return workflow_wait("approve", "k1", {}) }
    step publish after gate {
        checkpoint "after_wait"
        return {"published": true}
    }
}
'''


class _Harness(unittest.TestCase):
    def setUp(self):
        self.captured: dict = {}

    def _runtime(self):
        runtime = NodusRuntime(timeout_ms=None)
        runtime.register_function(
            "_cap", lambda v: self.captured.__setitem__("r", v), arity=1)
        return runtime

    def _parked_run(self):
        runtime = self._runtime()
        runtime.run_source(SOURCE + "\n_cap(run_workflow(w))\n")
        started = runtime._to_host_value(self.captured["r"])
        self.assertEqual(started["status"], "waiting", "expected a parked run")
        return started["graph_id"]

    def _resume(self, graph_id, checkpoint, payload):
        runtime = self._runtime()
        runtime.run_source(SOURCE)
        vm = runtime._get_active_vm()
        return runtime._to_host_value(
            vm.builtin_resume_workflow(graph_id, checkpoint, payload))


# closes: #870
class RejectAndRevise(_Harness):
    def test_a_checkpoint_with_feedback_replays_and_parks_again(self):
        result = self._resume(self._parked_run(), "before_draft", {"feedback": "redo"})

        self.assertIsNot(
            result.get("ok"), False,
            f"reject-and-revise was refused: {result.get('error')}",
        )
        self.assertEqual(result["status"], "waiting", "the run did not park again")

    def test_the_replayed_step_reads_the_feedback(self):
        result = self._resume(self._parked_run(), "before_draft", {"feedback": "redo"})
        self.assertIn(
            "redo", result["steps"]["draft"]["fb"],
            "the payload did not reach workflow_resume_payload() in the replayed "
            "step — which is the claim #482 was refused on",
        )

    def test_post_wait_steps_do_not_fire_on_a_rejection(self):
        # The reason this beats the two-phase workaround. Satisfying the wait
        # first runs `publish`, so a side-effecting step fires on a rejection
        # unless it gates on the payload itself.
        result = self._resume(self._parked_run(), "before_draft", {"feedback": "redo"})
        self.assertNotIn(
            "publish", {k for k, v in result["steps"].items() if v is not None},
            "a post-wait step ran during a rejection",
        )

    def test_a_rejected_run_can_then_be_approved(self):
        # The cycle a reviewer actually performs, not just one leg of it.
        graph_id = self._parked_run()
        self._resume(graph_id, "before_draft", {"feedback": "redo"})
        approved = self._resume(graph_id, None, {"approved": True})
        self.assertEqual(approved["steps"]["publish"], {"published": True})


# closes: #870
class TheRefusalThatStays(_Harness):
    def test_a_checkpoint_with_no_payload_is_still_refused(self):
        result = self._resume(self._parked_run(), "before_draft", None)
        self.assertIs(result.get("ok"), False)
        self.assertEqual(result.get("category"), "waiting_run_checkpoint_resume")

    def test_the_refusal_names_both_recipes(self):
        # It used to name only the advancing one, which is the opposite of what
        # a rejecting reviewer wants.
        result = self._resume(self._parked_run(), "before_draft", None)
        message = str(result.get("error"))
        self.assertIn("pass a payload to satisfy it", message)
        self.assertIn("reject and replay", message)

    def test_the_refusal_no_longer_claims_the_payload_is_discarded(self):
        # The false premise itself. It was in the message as well as the
        # changelog, so a reader hit it twice.
        result = self._resume(self._parked_run(), "before_draft", None)
        self.assertNotIn("discards the payload", str(result.get("error")))

    def test_a_checkpoint_the_run_has_not_reached_is_refused(self):
        result = self._resume(self._parked_run(), "after_wait", {"feedback": "x"})
        self.assertIs(result.get("ok"), False)
        self.assertIn("Checkpoint not found", str(result.get("error")))

    def test_a_typo_is_refused(self):
        result = self._resume(self._parked_run(), "no_such_checkpoint", {"feedback": "x"})
        self.assertIs(result.get("ok"), False)
        self.assertIn("Checkpoint not found", str(result.get("error")))

    def test_a_payload_alone_still_advances_the_run(self):
        # The control. Without it every test above passes on a build where
        # resume is broken in general.
        result = self._resume(self._parked_run(), None, {"approved": True})
        self.assertEqual(result["steps"]["publish"], {"published": True})


# closes: #870
class BothPathsAgree(_Harness):
    """The `.nd` spelling and the accidental `event_type=` escape hatch.

    `event_type` is a *verification* argument — "refuse unless the run is waiting
    on this event". It suppressed the #482 refusal only because the condition
    included `event_type is None`. Pinning the two to the same answer is what
    stops the supported spelling drifting back into depending on that.
    """

    def _resume_via_runner(self, graph_id, checkpoint, payload):
        runtime = self._runtime()
        runtime.run_source(SOURCE)
        vm = runtime._get_active_vm()
        return runtime._to_host_value(vm.resolve_workflow_runner().resume_workflow(
            vm, graph_id, checkpoint,
            resume_payload=payload,
            event_type="approve",
            rebuild_graph=vm._rebuild_workflow_graph,
        ))

    def test_the_nd_builtin_matches_the_event_type_path(self):
        through_builtin = self._resume(
            self._parked_run(), "before_draft", {"feedback": "redo"})
        through_runner = self._resume_via_runner(
            self._parked_run(), "before_draft", {"feedback": "redo"})

        self.assertEqual(through_builtin["status"], through_runner["status"])
        self.assertEqual(
            through_builtin["steps"]["draft"], through_runner["steps"]["draft"])


if __name__ == "__main__":
    unittest.main()
