"""The wait/resume value channel, pinned as designed (#404).

A waiting step completes with `nil`, and the resumed value reaches later steps
through `workflow_resume_payload()` — **not** through the step's return value.
`docs/guide/real-world-integration.md` documents exactly this:

    step gate after analyze {
        return workflow_wait("aindy.approval.granted", "approve-aindy", {...})
    }
    step execute after gate {
        let payload = workflow_resume_payload()
        ...
    }

These tests exist because that design is easy to mistake for a bug. Reading
`_pause_for_wait` shows `results[task.task_id] = None`, and a dependent written
the natural way — `step b after a { ... a ... }` — receives `nil`, which looks
like data loss on the durability path. It is not: the dependency edge carries
ordering, and the payload channel carries the value.

Three external architecture audits and one verification pass each reached a
different wrong conclusion about this area (see
`docs/governance/EXTERNAL_AUDIT_LEDGER.md`). Two audits asserted the waiting step
re-executes on resume — it does not. One flagged dependents-see-nil as a probable
correctness bug — it is the design. The purpose of this file is to make the
contract executable so the next reader does not have to re-derive it.
"""

import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO_ROOT / "src"))  # noqa: E402

from nodus.tooling.runner import resume_workflow, run_workflow_code  # noqa: E402
from nodus.vm.vm import VM  # noqa: E402

# The documented shape, from the guide.
DOCUMENTED = """
workflow demo {
    step gate { return workflow_wait("approval.granted", "req-9", {kind: "approval"}) }
    step finish after gate {
        let payload = workflow_resume_payload()
        if (payload == nil) { return "MISSING" }
        return "finish_saw=\\(payload["reviewer"])"
    }
}
"""

# The shape a developer writes by mistake: reading the dependency's value.
VIA_DEPENDENCY = """
workflow demo2 {
    step gate { return workflow_wait("approval.granted", "req-10", {kind: "approval"}) }
    step finish after gate { return "finish_saw=\\(type(gate))" }
}
"""


class _InTempCwd:
    """Graph state is CWD-relative; keep each case's store to itself."""

    def __enter__(self):
        self._prev = os.getcwd()
        self._dir = tempfile.mkdtemp()
        os.chdir(self._dir)
        return self

    def __exit__(self, *exc):
        os.chdir(self._prev)
        shutil.rmtree(self._dir, ignore_errors=True)
        return False


def _start(src, name):
    res, _vm = run_workflow_code(
        VM([], {}, code_locs=[], source_path=None), src, filename=f"{name}.nd", workflow_name=name
    )
    return res.get("result") or {}


def _resume(graph_id, **kwargs):
    out = resume_workflow(graph_id, None, **kwargs)
    if isinstance(out, tuple):
        out = out[0]
    return (out.get("result") or {}) if isinstance(out, dict) else {}


class WaitResumeValueChannelTests(unittest.TestCase):
    # closes: #404
    def test_the_payload_reaches_a_later_step_via_workflow_resume_payload(self):
        """The documented channel. This is how a human decision crosses into a step."""
        with _InTempCwd():
            started = _start(DOCUMENTED, "demo")
            self.assertEqual("waiting", started.get("status"), "setup: must actually be waiting")

            resumed = _resume(
                started["graph_id"], resume_payload={"approved": True, "reviewer": "alice"}
            )
            steps = resumed.get("steps") or {}
            self.assertEqual("finish_saw=alice", steps.get("finish"))

    def test_the_waiting_step_itself_completes_with_nil_by_design(self):
        """`workflow_wait` marks a suspension point; it does not produce a value.

        Pinned deliberately: this looks like data loss and is not. Changing it
        would break the documented pattern above, in which the payload arrives
        through a separate channel.
        """
        with _InTempCwd():
            started = _start(DOCUMENTED, "demo")
            resumed = _resume(started["graph_id"], resume_payload={"approved": True, "reviewer": "bo"})
            steps = resumed.get("steps") or {}
            self.assertIsNone(steps.get("gate"), "the waiting step's own result is nil by design")
            self.assertEqual("finish_saw=bo", steps.get("finish"), "…and the payload still arrives")

    def test_reading_the_dependency_value_instead_yields_nil(self):
        """The mistake this file exists to document.

        A dependent written as `step finish after gate { ... gate ... }` gets nil.
        The dependency edge carries *ordering*; the payload channel carries the
        *value*. Asserted so the behaviour is a recorded decision rather than a
        surprise rediscovered as a bug.
        """
        with _InTempCwd():
            started = _start(VIA_DEPENDENCY, "demo2")
            resumed = _resume(started["graph_id"], resume_payload={"approved": True})
            steps = resumed.get("steps") or {}
            self.assertEqual("finish_saw=nil", steps.get("finish"))

    def test_a_waiting_run_does_not_run_steps_after_the_wait(self):
        """Ordering still holds while suspended."""
        with _InTempCwd():
            started = _start(DOCUMENTED, "demo")
            self.assertEqual("waiting", started.get("status"))
            self.assertIsNone(
                (started.get("steps") or {}).get("finish"),
                "a step after the wait ran before the wait was satisfied",
            )


if __name__ == "__main__":
    unittest.main()
