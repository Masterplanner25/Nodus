"""Closed-issue test for #999: `max_memory_mb` is checked before a run can succeed.

The ceiling was sampled every `MEMORY_CHECK_INTERVAL` (256) instructions and
nowhere else. So a run that went past it and then ended within one interval was
never checked, and returned `ok=True` with the oversized value. One
`"a" * n` did that, and so did a doubling loop of a few dozen passes, which is
the case #160 was filed for. `VM.execute` now checks the ceiling once more on
the way out, and every exit from running Nodus code passes through it.

Separately, an allocation Python could not satisfy reached the guest and the
host as a runtime error with an empty message.

64 MB against a 16 MB ceiling: well past it, and small enough for a box short
of memory. `max_memory_mb` exists only on `NodusRuntime`; the CLI has no flag
for it, so there is no CLI half to test (the security-boundary rule in
`CLAUDE.md` asks for both where both exist).
"""
import gc
import inspect
import os
import re
import sys
import tempfile
import unittest

sys.path.insert(0, "C:/dev/Coding Language/src")

from nodus.runtime.embedding import NodusRuntime  # noqa: E402
from nodus.runtime.memory import memory_metering_available  # noqa: E402
from nodus.vm import vm as vm_module  # noqa: E402
from nodus.vm.vm import VM  # noqa: E402

_N = 64_000_000


def _limited():
    # The ceiling is growth in *process* RSS since the run started. An earlier
    # test's runtime still holding its 64 MB string, collected partway through
    # this run, would offset this run's growth by 64 MB: the doubling test
    # passed alone and failed after the others. Collect first, so each run
    # starts from what is really live. (The same offset can happen to a host;
    # SECURITY_POSTURE.md section 5 states that the bound is process RSS.)
    gc.collect()
    return NodusRuntime(max_memory_mb=16, timeout_ms=None, max_steps=None)


def _error(result):
    return result.get("error") or {}


# closes: #999
@unittest.skipUnless(memory_metering_available(), "max_memory_mb is not enforceable here")
class NoExitReportsSuccessPastTheCeiling(unittest.TestCase):
    def assert_stopped(self, result):
        self.assertFalse(result.get("ok"), f"ran past the ceiling: {result.get('stdout')!r}")
        self.assertEqual(_error(result).get("kind"), "sandbox")
        self.assertIn("Memory limit exceeded", _error(result).get("message", ""))

    def test_one_allocation_then_the_program_ends(self):
        self.assert_stopped(_limited().run_source(f'let x = "a" * {_N}i\nprint(len(x))\n'))

    def test_a_short_doubling_loop(self):
        # About 26 passes: well under one sampling interval.
        self.assert_stopped(_limited().run_source(
            f'let x = "a"\nwhile (len(x) < {_N}i) {{ x = x + x }}\nprint(len(x))\n'))

    def test_a_coroutine_that_allocates_and_returns(self):
        self.assert_stopped(_limited().run_source(
            f'fn big() {{\n    let x = "a" * {_N}i\n    return len(x)\n}}\n'
            "spawn(big)\nprint(run_loop())\n"))

    def test_a_module_function_that_allocates_and_returns(self):
        with tempfile.TemporaryDirectory() as directory:
            with open(os.path.join(directory, "m.nd"), "w", encoding="utf-8") as handle:
                handle.write(f'export fn big() {{\n    let x = "a" * {_N}i\n    return len(x)\n}}\n')
            cwd = os.getcwd()
            os.chdir(directory)
            try:
                result = _limited().run_source('import "./m.nd" as m\nprint(m.big())\n',
                                               filename="main.nd")
            finally:
                os.chdir(cwd)
        self.assert_stopped(result)

    def test_the_ceiling_cannot_be_caught_by_the_guest(self):
        result = _limited().run_source(
            f'try {{\n    let x = "a" * {_N}i\n}} catch e {{\n    print("caught")\n}}\n')
        self.assert_stopped(result)
        self.assertNotIn("caught", result.get("stdout") or "")

    def test_the_control_a_run_within_the_ceiling_succeeds(self):
        result = NodusRuntime(max_memory_mb=1024, timeout_ms=None, max_steps=None).run_source(
            f'let x = "a" * {_N}i\nprint(len(x))\n')
        self.assertTrue(result.get("ok"), _error(result))
        self.assertEqual(result["stdout"], f"{_N}\n")


class AnAllocationThatFailsSaysSo(unittest.TestCase):
    _HUGE = 'let x = "a" * 100000000000000i\n'

    def test_the_host_sees_a_message(self):
        result = NodusRuntime(timeout_ms=None, max_steps=None).run_source(self._HUGE)
        self.assertFalse(result.get("ok"))
        self.assertEqual(_error(result).get("kind"), "runtime")
        self.assertIn("Out of memory", _error(result).get("message", ""))

    def test_the_guest_can_still_catch_it_and_sees_the_message(self):
        # Nothing was allocated, so this stays an ordinary runtime error.
        result = NodusRuntime(timeout_ms=None, max_steps=None).run_source(
            "try {\n    " + self._HUGE + "} catch e {\n    print(e.message)\n}\n")
        self.assertTrue(result.get("ok"), _error(result))
        self.assertIn("Out of memory", result["stdout"])

    def test_any_messageless_exception_is_named(self):
        self.assertEqual(vm_module.python_error_message(KeyError()), "KeyError")
        self.assertEqual(vm_module.python_error_message(ValueError("bad")), "bad")


class OnePlaceChecksOnTheWayOut(unittest.TestCase):
    """Asserted on the source. A behaviour test passes on whichever exit is
    already right; these keep every exit on the one checked path."""

    def _code(self, fn):
        source = inspect.getsource(fn)
        # The docstring explains the fix, so it names what the body must do.
        return re.sub(r'"""(.|\n)*?"""', "", source, count=1)

    def test_execute_checks_after_the_loop(self):
        body = self._code(VM.execute)
        self.assertIn("self._execute_loop()", body)
        self.assertIn("self._check_memory_limit()", body)

    def test_nothing_else_enters_the_loop_directly(self):
        src_root = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
            os.path.abspath(__file__)))), "src")
        callers = []
        for directory, _, files in os.walk(src_root):
            for name in files:
                if name.endswith(".py"):
                    path = os.path.join(directory, name)
                    with open(path, encoding="utf-8-sig") as handle:
                        text = handle.read()
                    count = text.count("_execute_loop()")
                    if count:
                        callers.append((os.path.relpath(path, src_root), count))
        self.assertEqual(callers, [(os.path.join("nodus", "vm", "vm.py"), 1)])

    def test_both_loops_word_a_python_error_the_same_way(self):
        source = inspect.getsource(vm_module)
        self.assertNotIn('build_runtime_error("runtime", str(_e))', source)
        self.assertEqual(source.count('build_runtime_error("runtime", python_error_message(_e))'), 2)

    def test_no_ceiling_means_no_extra_check(self):
        calls = []
        saved = VM._check_memory_limit
        VM._check_memory_limit = lambda self: calls.append(1)
        try:
            NodusRuntime(timeout_ms=None, max_steps=None).run_source("print(1)\n")
        finally:
            VM._check_memory_limit = saved
        self.assertEqual(calls, [])


if __name__ == "__main__":
    unittest.main()
