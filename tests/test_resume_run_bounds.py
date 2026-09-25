"""A resume cannot exceed the budget the host set on the caller (#873).

`_resume_target_vm` builds a child VM when a resume needs a rebuild (#328). #868
taught that child what it may *do* and who it works *for*, and deliberately left
the third question — *how much may it consume* — for its own decision, because a
budget is a quantity rather than a setting.

Measured before this, with every bound set non-default, **five** were lost:
`max_steps`, `deadline` and `max_memory_bytes` to `None`, and `max_frames` from a
host's tighter cap back to the 10,000 default. So a guest escaped every bound by
parking and resuming:

    300 ms budget  -> 8 resumes, ~800 ms of work, PASSED
    5,000 steps    -> ~270,000 instructions,      PASSED

**The caller's own deadline does not rescue it**, which is the assumption these
tests exist to have falsified: a `deadline` is absolute, so it looked like time
spent in the child was already charged. It is only consulted every 100
instructions, and a program doing eight `resume_workflow` calls never executes
100 more, so it is never re-checked.

**Two kinds of bound.** A ceiling copies straight across. `max_steps` is a
counter, so the child gets the remainder and its usage is charged back — without
the charge-back every resume is handed a fresh allowance and the split is
decorative. That is what `RepeatedResumesAccumulate` pins.

Assertions here are on instruction counts, not wall clock: an instruction count
is deterministic, so these cannot join the timing-sensitive set this box already
struggles with.
"""

import os
import sys
import unittest

sys.path.insert(0, "C:/dev/Coding Language/src")

from nodus.runtime.capability import (  # noqa: E402
    CONSUMABLE_BOUND_ATTRIBUTE,
    RUN_BOUND_ATTRIBUTES,
    charge_run_bounds,
    inherit_run_bounds,
)
from nodus.runtime.embedding import NodusRuntime  # noqa: E402
from nodus.vm.vm import VM  # noqa: E402

# ~34,000 instructions in the resumed step: far enough over any budget below that
# a partial escape is still a failure, and deterministic.
PARKED = '''
workflow w {
    step a { return workflow_wait("go", "k1", {}) }
    step b after a {
        let n = 0i
        let i = 0i
        while (i < 3000i) { n = n + i; i = i + 1i }
        return {"n": n}
    }
}
'''


class _Harness(unittest.TestCase):
    def setUp(self):
        self._previous = os.environ.get("NODUS_WORKFLOW_STORE_BACKEND")
        os.environ["NODUS_WORKFLOW_STORE_BACKEND"] = "sqlite"
        self.captured: dict = {}

    def tearDown(self):
        if self._previous is None:
            os.environ.pop("NODUS_WORKFLOW_STORE_BACKEND", None)
        else:
            os.environ["NODUS_WORKFLOW_STORE_BACKEND"] = self._previous

    def _park(self):
        """Park a run and return its id, without a host function.

        The id comes back through `print` rather than a registered callback on
        purpose: a resume re-executes the persisted source to rebind the
        declarations, so a parked program that calls a host function can only be
        resumed by a runtime that also registers it. Parking with `_cap(...)` in
        the source made every resume below fail with `Undefined function: _cap`
        and report no `steps` at all.
        """
        runtime = NodusRuntime(timeout_ms=None, max_steps=None)
        out = runtime.run_source(PARKED + (
            'fn main() {\n'
            '    let r = run_workflow(w)\n'
            '    let g = r["graph_id"]\n'
            '    let s = r["status"]\n'
            '    print("GID=\\(g) STATUS=\\(s)")\n'
            '}\n'
        ))
        self.assertTrue(out.get("ok"), str(out.get("error"))[:200])
        stdout = out.get("stdout") or ""
        self.assertIn("STATUS=waiting", stdout, f"expected a parked run: {stdout}")
        return stdout.split("GID=")[1].split()[0]


# closes: #873
class TheResumeChildInheritsEveryBound(_Harness):
    """Structural: read the bounds off the child the diversion returns."""

    def _loaded_parent(self):
        runtime = NodusRuntime(timeout_ms=None, max_steps=None)
        runtime.run_source(PARKED)
        vm = runtime._get_active_vm()
        # Every value non-default, so an uninherited bound shows as a difference
        # rather than coincidentally matching. The first survey of this had six
        # rows comparing None to None.
        vm.max_steps = 1_000_000
        vm.deadline = 1e18
        vm.max_frames = 4321
        vm.max_memory_bytes = 999_999_999
        return vm

    def test_every_ceiling_is_carried(self):
        parent = self._loaded_parent()
        child = parent._resume_target_vm(self._park())
        self.assertIsNot(child, parent, "expected a derived VM for this case")
        lost = {
            name: (getattr(parent, name, None), getattr(child, name, None))
            for name in RUN_BOUND_ATTRIBUTES
            if getattr(parent, name, None) != getattr(child, name, None)
        }
        self.assertEqual(lost, {}, f"bounds lost when deriving a VM: {lost}")

    def test_the_memory_ceiling_specifically_is_carried(self):
        # Named on its own because the list-driven test above iterates
        # RUN_BOUND_ATTRIBUTES: deleting a name removes the propagation and the
        # comparison together, so it cannot fail on its own.
        parent = self._loaded_parent()
        child = parent._resume_target_vm(self._park())
        self.assertEqual(child.max_memory_bytes, 999_999_999)

    def test_a_tighter_frame_cap_is_not_reset_to_the_default(self):
        # The subtlest of the five: this one did not go to None, it went back to
        # MAX_STACK_DEPTH, so a host that had asked for less silently got more.
        parent = self._loaded_parent()
        child = parent._resume_target_vm(self._park())
        self.assertEqual(child.max_frames, 4321)
        self.assertNotEqual(child.max_frames, VM([], {}).max_frames)

    def test_the_step_budget_is_the_remainder_not_a_fresh_allowance(self):
        parent = self._loaded_parent()
        spent = parent.instructions_executed
        self.assertGreater(spent, 0, "the parent has run nothing; the test proves nothing")
        child = parent._resume_target_vm(self._park())
        self.assertEqual(
            getattr(child, CONSUMABLE_BOUND_ATTRIBUTE), 1_000_000 - spent)

    def test_the_schedulers_slice_budget_is_not_inherited(self):
        # `task_step_budget` is the scheduler's per-coroutine fairness allowance,
        # not a host bound. A VM starting fresh work is not inside a slice.
        parent = self._loaded_parent()
        parent.task_step_budget = 777
        child = parent._resume_target_vm(self._park())
        self.assertIsNone(child.task_step_budget)


# closes: #873
class TheChildsUsageIsChargedBack(_Harness):
    def test_the_parent_counter_grows_by_what_the_resume_spent(self):
        runtime = NodusRuntime(timeout_ms=None, max_steps=1_000_000)
        runtime.run_source(PARKED)
        vm = runtime._get_active_vm()
        before = vm.instructions_executed
        result = runtime._to_host_value(
            vm.builtin_resume_workflow(self._park(), None, {"ok": True}))
        self.assertIsNotNone(result["steps"]["b"], "the resume did not run")
        self.assertGreater(
            vm.instructions_executed - before, 10_000,
            "the resumed step ran ~34,000 instructions and none were charged to "
            "the caller, so every resume gets a fresh allowance",
        )


# closes: #873
class RepeatedResumesAccumulate(_Harness):
    """The point of the charge-back, and what a per-call split cannot give.

    A budget that comfortably covers one resume must not cover many.
    """

    def test_a_budget_for_one_resume_does_not_cover_six(self):
        graph_ids = [self._park() for _ in range(6)]
        program = PARKED + "fn main() {\n" + "".join(
            f'    let r{i} = resume_workflow("{g}", {{"ok": true}})\n'
            for i, g in enumerate(graph_ids)
        ) + '    print("ALL SIX RAN")\n}\n'

        # 120k comfortably covers one ~34k resume and cannot cover six.
        out = NodusRuntime(timeout_ms=None, max_steps=120_000).run_source(program)
        self.assertNotIn(
            "ALL SIX RAN", out.get("stdout") or "",
            "six resumes fitted a budget sized for one, so consumption is not "
            "accumulating across calls",
        )

    def test_the_control_one_resume_fits_the_same_budget(self):
        # Without this, the test above passes on a build where any resume fails.
        graph_id = self._park()
        program = PARKED + (
            'fn main() {\n'
            f'    let r = resume_workflow("{graph_id}", {{"ok": true}})\n'
            '    print("ONE RAN")\n}\n'
        )
        out = NodusRuntime(timeout_ms=None, max_steps=120_000).run_source(program)
        self.assertIn("ONE RAN", out.get("stdout") or "", str(out.get("error"))[:200])


# closes: #873
class TheHelpersThemselves(unittest.TestCase):
    def test_an_exhausted_parent_hands_down_zero_not_unlimited(self):
        # `or None` here would turn "no budget left" into "unbounded", which is
        # the bug this fixes rather than a tidier spelling of it.
        parent = VM([], {})
        parent.max_steps = 100
        parent.instructions_executed = 500
        child = VM([], {})
        inherit_run_bounds(child, parent)
        self.assertEqual(child.max_steps, 0)

    def test_an_unbounded_parent_stays_unbounded(self):
        parent = VM([], {})
        parent.max_steps = None
        child = VM([], {})
        child.max_steps = 42
        inherit_run_bounds(child, parent)
        self.assertEqual(child.max_steps, 42, "a bound was invented from None")

    def test_inheriting_onto_self_is_a_no_op(self):
        vm = VM([], {})
        vm.max_steps = 100
        vm.instructions_executed = 10
        inherit_run_bounds(vm, vm)
        self.assertEqual(vm.max_steps, 100, "the VM split its own budget")

    def test_charging_to_self_is_a_no_op(self):
        vm = VM([], {})
        vm.instructions_executed = 10
        charge_run_bounds(vm, vm)
        self.assertEqual(vm.instructions_executed, 10, "the VM charged itself twice")


if __name__ == "__main__":
    unittest.main()
