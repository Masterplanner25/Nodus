"""What a resumed step re-executes, and what it observes (#494, I-WFLOW-06/07).

Resume works by **re-executing**. Nothing records what the original execution
observed, so a fresh read — the clock, randomness, the environment, a file, an
HTTP response — returns a different value on the replay. Checkpointed `state` is
restored faithfully; that is the whole of what holds.

Nodus has never claimed replay determinism and this is not a bug: re-execution is
what makes checkpoint-restore cheap. It is pinned because it was undocumented,
undetectable and unavoidable, and because a future change could silently narrow
or widen it.

**Both halves are asserted deliberately.** A test that only checked "the fresh
read moved" would still pass on a runtime that had frozen the entire step, and a
test that only checked "the checkpointed value held" would pass on one that
replayed nothing at all. Neither alone describes the boundary.

The re-execution scope was also wrong in the invariants doc until this landed:
I-WFLOW-06 claimed completed steps are never re-run, naming **both** resume
forms. True of the plain form; false of the labelled one, which is the form a
debugging loop reaches for.
"""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))  # noqa: E402

from nodus.runtime.embedding import NodusRuntime  # noqa: E402

# Three completed steps, the checkpoint in the middle one. `print` is the probe
# rather than workflow `state`: state is re-derived from the checkpoint on
# resume, so a counter written into it cannot measure whether a step re-ran.
THREE_STEPS = """
workflow w {
    step a { print("A"); return 1i }
    step b after a { print("B"); checkpoint "mid"; print("B2"); return 2i }
    step c after b { print("C"); return 3i }
}
fn main() {
    let r = run_workflow(w)
    %(resume)s
}
"""


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


class WhatARelabelledResumeReExecutesTests(unittest.TestCase):
    # closes: #494
    def test_a_labelled_resume_reruns_the_label_step_and_everything_after(self):
        """I-WFLOW-06's scope. Completed status does not protect a step here."""
        out = _run(THREE_STEPS % {"resume": 'resume_workflow(r["graph_id"], "mid")'})
        self.assertEqual(out.count("A"), 1, "an upstream step must not re-run")
        self.assertEqual(out.count("B2"), 2, "the checkpoint's own step re-runs from the top")
        self.assertEqual(out.count("C"), 2, "a downstream step re-runs")

    def test_a_plain_resume_reruns_nothing(self):
        """The form I-WFLOW-06 is actually true of."""
        out = _run(THREE_STEPS % {"resume": 'resume_workflow(r["graph_id"])'})
        for marker in ("A", "B2", "C"):
            self.assertEqual(out.count(marker), 1, f"{marker} re-ran on a plain resume")


class WhatAReplayedStepObservesTests(unittest.TestCase):
    SOURCE = """
import "std:time" as time

workflow report {
    state started_at = 0i
    step gather {
        let now = time.now().epoch_ms
        if (started_at == 0i) { started_at = now }
        print("fresh=\\(now) held=\\(started_at)")
        checkpoint "gathered"
        return now
    }
}
fn main() {
    let r = run_workflow(report)
    let again = resume_workflow(r["graph_id"], "gathered")
    print("returned=\\(again["steps"]["gather"])")
}
"""

    def _readings(self):
        out = _run(self.SOURCE)
        fresh, held, returned = [], [], None
        for line in out.splitlines():
            if line.startswith("fresh="):
                head, _, tail = line.partition(" held=")
                fresh.append(int(head[len("fresh="):]))
                held.append(int(tail))
            elif line.startswith("returned="):
                returned = int(line[len("returned="):])
        return fresh, held, returned

    def test_a_fresh_read_moves_across_the_replay(self):
        fresh, _held, _returned = self._readings()
        self.assertEqual(len(fresh), 2, "the step did not re-execute")
        self.assertNotEqual(
            fresh[0], fresh[1],
            "the replayed step observed the first run's clock — if this is now "
            "intended, I-WFLOW-07 and the guide both need rewriting, not this test "
            "deleting",
        )

    def test_a_checkpointed_read_holds_across_the_replay(self):
        """The other half, and the supported answer for authors who need one."""
        _fresh, held, _returned = self._readings()
        self.assertEqual(len(held), 2)
        self.assertEqual(held[0], held[1], "checkpointed state did not survive the replay")

    def test_the_step_result_is_the_replays_observation(self):
        """A caller reading `steps[...]` after a resume gets the second reading.

        Easy to miss, and it is what a host reporting "when did this run?" from a
        resumed result would get wrong.
        """
        fresh, _held, returned = self._readings()
        self.assertEqual(returned, fresh[1])
        self.assertNotEqual(returned, fresh[0])


if __name__ == "__main__":
    unittest.main()
