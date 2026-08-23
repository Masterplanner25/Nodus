"""The concurrent-write warning fires only when something was actually lost.

#485 step 4 asks whether an undeclared cell should default to `once`. It should
not, yet: `workflow`/`step` are Mostly Stable, and turning working programs into
errors is not the "minor refinement" that tier permits. What it *can* do in a
minor release is make the warning precise, and announce the error for 6.0.0.

Two signals, and the second one exists because the first is not enough:

* the writers disagreed -- different values, one was overwritten;
* a writer **read the cell before writing it** -- a read-modify-write, which is
  a lost update whatever the values are.

`test_agreement_alone_does_not_mean_nothing_was_lost` is the one to read. Value
comparison was implemented first, on its own, and this issue's own reproduction
falsified it: two branches doing `counter = seen + 1i` from the same base both
write `1`, so the values agree *precisely because* an update was lost.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))  # noqa: E402

from nodus.orchestration.workflow_state import (  # noqa: E402
    TrackedState,
    concurrent_write_conflicts,
    writers_agree,
)
from nodus.runtime.embedding import NodusRuntime  # noqa: E402


def _run(src: str):
    result = NodusRuntime(timeout_ms=None, max_steps=None).run_source(src, filename="<cp>")
    assert result.get("ok"), result.get("errors")
    return (result.get("stdout") or "").strip(), (result.get("stderr") or "")


RACE = """
workflow w {{
    state x = 0i{policy}
    step a {{ sleep(10i); {a}; return 1i }}
    step b {{ sleep(10i); {b}; return 2i }}
    step j after a, b {{ return 0i }}
}}
fn main() {{ let r = run_workflow(w); print("X=\\(r["state"]["x"])") }}
"""


def _race(a: str, b: str, policy: str = ""):
    return _run(RACE.format(a=a, b=b, policy=policy))


class WhatWarnsTests(unittest.TestCase):
    def test_agreeing_constant_writes_are_silent(self):
        """Both branches set the same value and neither read it first."""
        out, err = _race("x = 5i", "x = 5i")
        self.assertIn("X=5", out)
        self.assertNotIn("both wrote state", err)

    def test_disagreeing_writes_warn(self):
        out, err = _race("x = 7i", "x = 9i")
        self.assertIn("both wrote state 'x'", err)
        self.assertIn("different values", err)

    def test_a_read_modify_write_warns_even_when_the_values_agree(self):
        """The case value-comparison alone gets wrong.

        The suspension has to sit *between* the read and the write -- that is
        what opens the window. Sleeping first and then doing the whole
        read-modify-write without yielding lets the scheduler serialise them, and
        the answer comes out right, which is the trap this issue is about.
        """
        out, err = _run(
            """
workflow w {
    state x = 0i
    step a { let seen = x; sleep(20i); x = seen + 1i; return 1i }
    step b { let seen = x; sleep(20i); x = seen + 1i; return 2i }
    step j after a, b { return 0i }
}
fn main() { let r = run_workflow(w); print("X=\\(r["state"]["x"])") }
"""
        )
        self.assertIn("X=1", out, "the update is still lost")
        self.assertIn("both wrote state 'x'", err)
        self.assertIn("read it before writing", err)

    def test_the_serialised_read_modify_write_still_warns(self):
        """Right answer today, wrong the moment either step yields.

        Warning here is the whole point -- it arrives before the step grows its
        first `sleep` or agent call, which is the only moment it is cheap to act
        on.
        """
        out, err = _race("let seen = x; x = seen + 1i", "let seen = x; x = seen + 1i")
        self.assertIn("X=2", out, "serialised, so the answer happens to be right")
        self.assertIn("read it before writing", err)

    def test_the_warning_names_the_fix_and_the_flag_day(self):
        _out, err = _race("x = 7i", "x = 9i")
        self.assertIn('merge: "sum"', err)
        self.assertIn('merge: "any"', err)
        self.assertIn("6.0.0", err)

    def test_declaring_any_still_silences_it(self):
        _out, err = _race("x = 7i", "x = 9i", policy=' with { merge: "any" }')
        self.assertNotIn("both wrote state", err)

    def test_a_fold_is_silent_and_correct(self):
        out, err = _race("x += 1i", "x += 1i", policy=' with { merge: "sum" }')
        self.assertIn("X=2", out)
        self.assertNotIn("both wrote state", err)


class SignalTests(unittest.TestCase):
    """The detector, without a workflow around it."""

    def _state(self, task):
        state = TrackedState({"k": 0})
        state.track_writes_with(lambda: task[0])
        return state

    def _conflicts(self, state):
        return concurrent_write_conflicts(state, lambda a, b: False)

    def test_disagreement_is_a_lost_update(self):
        task = ["t1"]
        state = self._state(task)
        state["k"] = 1
        task[0] = "t2"
        state["k"] = 2
        conflict = self._conflicts(state)[0]
        self.assertTrue(conflict["lost_update"])
        self.assertEqual(conflict["read_modify_write"], [])

    def test_agreement_with_no_read_is_not(self):
        task = ["t1"]
        state = self._state(task)
        state["k"] = 5
        task[0] = "t2"
        state["k"] = 5
        self.assertFalse(self._conflicts(state)[0]["lost_update"])

    # closes: #485
    def test_agreement_alone_does_not_mean_nothing_was_lost(self):
        """Two read-modify-writes from the same base agree, and lose an update.

        This is the assertion that killed value-comparison as a standalone
        signal, and it is the issue's own reproduction in miniature.
        """
        task = ["t1"]
        state = self._state(task)
        state["k"]           # t1 reads
        task[0] = "t2"
        state["k"]           # t2 reads
        task[0] = "t1"
        state["k"] = 1       # both compute the same value
        task[0] = "t2"
        state["k"] = 1
        conflict = self._conflicts(state)[0]
        self.assertTrue(
            writers_agree(state.written_values()["k"], ["t1", "t2"]),
            "the values do agree -- that is the trap",
        )
        self.assertTrue(conflict["lost_update"], "and an update was still lost")
        self.assertEqual(conflict["read_modify_write"], ["t1", "t2"])

    def test_a_read_after_the_task_s_own_write_is_not_a_read_modify_write(self):
        """`x = 5i; print(x)` must not look like an increment."""
        task = ["t1"]
        state = self._state(task)
        state["k"] = 5
        state["k"]
        task[0] = "t2"
        state["k"] = 5
        self.assertFalse(self._conflicts(state)[0]["lost_update"])

    def test_a_single_writer_is_never_a_conflict(self):
        task = ["t1"]
        state = self._state(task)
        state["k"]
        state["k"] = 1
        self.assertEqual(self._conflicts(state), [])

    def test_ordered_tasks_are_never_a_conflict(self):
        """A path between them means they cannot have run at the same time."""
        task = ["t1"]
        state = self._state(task)
        state["k"] = 1
        task[0] = "t2"
        state["k"] = 2
        self.assertEqual(concurrent_write_conflicts(state, lambda a, b: True), [])


class WritersAgreeTests(unittest.TestCase):
    def test_equal_values_agree(self):
        self.assertTrue(writers_agree({"a": 1, "b": 1}, ["a", "b"]))

    def test_different_values_do_not(self):
        self.assertFalse(writers_agree({"a": 1, "b": 2}, ["a", "b"]))

    def test_a_missing_writer_is_disagreement(self):
        """Unknown must never be reported as agreement."""
        self.assertFalse(writers_agree({"a": 1}, ["a", "b"]))

    def test_an_uncomparable_value_is_disagreement(self):
        class Hostile:
            def __eq__(self, other):
                raise RuntimeError("no")

        self.assertFalse(writers_agree({"a": Hostile(), "b": Hostile()}, ["a", "b"]))

    def test_structural_values_compare_by_value(self):
        self.assertTrue(writers_agree({"a": [1, 2], "b": [1, 2]}, ["a", "b"]))
        self.assertFalse(writers_agree({"a": [1, 2], "b": [2, 1]}, ["a", "b"]))


if __name__ == "__main__":
    unittest.main()
