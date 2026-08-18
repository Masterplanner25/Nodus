"""A directly constructed VM caps call depth by default (#387).

Every existing `max_frames` test goes through `NodusRuntime` or the CLI, which is
exactly why this survived #350: the guard lived in the wrapper, and #350 fixed it
one layer up without asking what happens when a host builds the VM itself.

Something already was. `nodus-jupyter`'s kernel runs every notebook cell on a bare
`VM(...)` and never calls `configure_vm_limits`.

**Why the call-depth cap specifically, and not the others.** VM frames are
heap-allocated, so Python's own recursion limit never fires — measured before the
fix: depth 5,000 completed on a bare VM against a `sys.getrecursionlimit()` of
1,000. Unbounded recursion therefore does not raise, it grows until the OS kills
the process. That is the one limit whose absence costs the host the *process*
rather than the request. `max_steps` and `deadline` stay unbounded on purpose:
`EXECUTION_TIMEOUT_MS` is 200 ms and would break most in-process consumers, and a
step budget is a policy the host should choose.

So the tests below pin both halves — the cap that must be on, and the two that
must stay off. A fix that switched on all three would satisfy "the VM has limits"
and break every embedder running anything non-trivial.
"""

import sys
import unittest

from nodus.runtime.module_loader import ModuleLoader
from nodus.support.config import MAX_STACK_DEPTH
from nodus.vm.vm import VM


def compile_snippet(source: str):
    """Compile with a *fresh* loader.

    Reusing one loader with the same `module_name` returns the first source's
    bytecode (#457), which silently makes every case here test the same program.
    """
    return ModuleLoader().compile_only(source, module_name="<memory>")


def run_snippet(source: str, *, max_frames="default"):
    code, functions, locs = compile_snippet(source)
    vm = VM(code, functions, code_locs=locs)
    if max_frames != "default":
        vm.max_frames = max_frames
    vm.run()
    return vm


RUNAWAY = "fn rec(n) { return rec(n + 1i) }\nlet r = rec(0i)\n"


def bounded(depth: int) -> str:
    return (
        "fn rec(n) { if (n <= 0i) { return 0i }\n return rec(n - 1i) }\n"
        f"let r = rec({depth}i)\n"
    )


class TestBareVmCapsCallDepth(unittest.TestCase):
    # closes: #387
    def test_a_bare_vm_has_the_call_depth_cap_set(self):
        self.assertEqual(VM([("HALT",)], {}).max_frames, MAX_STACK_DEPTH)

    def test_runaway_recursion_raises_instead_of_growing(self):
        """The behaviour that matters: catchable, not fatal.

        Before the fix this did not raise at all — it allocated frames until the
        process died, which a host cannot catch, log, or recover from.

        **Do not run this against an unfixed VM to "check the test fails".** It
        does not fail; it hangs, allocating until something is killed. Verified the
        hard way: the attempt hit a ten-minute timeout and left a stash unpopped.
        Deselect it (`-k "not runaway"`) when checking the rest against an unfixed
        tree — the sibling assertion on `max_frames` covers the same fix safely.
        """
        with self.assertRaises(Exception) as ctx:
            run_snippet(RUNAWAY)
        self.assertIn("Call stack overflow", str(ctx.exception))

    def test_recursion_well_under_the_cap_still_completes(self):
        """Positive control. A cap set absurdly low would pass the test above and
        break every legitimate recursive program."""
        run_snippet(bounded(4000))

    def test_recursion_just_under_the_cap_still_completes(self):
        run_snippet(bounded(MAX_STACK_DEPTH - 100))

    def test_a_host_can_still_opt_out(self):
        """The cap is a default, not a ceiling — same contract as NodusRuntime."""
        run_snippet(bounded(MAX_STACK_DEPTH + 5000), max_frames=10**9)

    def test_a_host_can_still_set_a_tighter_cap(self):
        with self.assertRaises(Exception) as ctx:
            run_snippet(bounded(500), max_frames=100)
        self.assertIn("Call stack overflow", str(ctx.exception))


class TestTheOtherLimitsStayOff(unittest.TestCase):
    """Pinned so "give the VM limits" is not over-applied.

    `EXECUTION_TIMEOUT_MS` is 200 ms; defaulting `deadline` to it would break any
    in-process consumer doing real work, including much of this suite.
    """

    # closes: #387
    def test_max_steps_is_unbounded_on_a_bare_vm(self):
        self.assertIsNone(VM([("HALT",)], {}).max_steps)

    def test_deadline_is_unset_on_a_bare_vm(self):
        self.assertIsNone(VM([("HALT",)], {}).deadline)

    def test_frames_are_heap_allocated_so_python_does_not_bound_them(self):
        """The premise the whole issue rests on, kept honest.

        If some future change made VM calls consume Python stack, the call-depth
        cap would stop being the uniquely unrecoverable one and this reasoning
        would need revisiting.
        """
        depth = sys.getrecursionlimit() * 3
        run_snippet(bounded(depth), max_frames=10**9)


class TestWrapperPathsAreUnchanged(unittest.TestCase):
    """The wrappers already installed this cap; they must keep winning."""

    def test_configure_vm_limits_still_sets_the_cap(self):
        from nodus.tooling.sandbox import configure_vm_limits

        vm = VM([("HALT",)], {})
        configure_vm_limits(vm, max_steps=123, timeout_ms=None)
        self.assertEqual(vm.max_frames, MAX_STACK_DEPTH)
        self.assertEqual(vm.max_steps, 123)

    def test_nodus_runtime_still_honours_an_explicit_max_frames(self):
        from nodus.runtime.embedding import NodusRuntime

        rt = NodusRuntime(timeout_ms=None, max_frames=150)
        try:
            rt.run_source("let x = 1i", filename="t.nd")
            self.assertEqual(rt.active_vm().max_frames, 150)
        finally:
            rt.shutdown()


if __name__ == "__main__":
    unittest.main()
