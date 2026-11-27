"""Closed-issue test for #1004: the memory-limit error is in the host's terms.

`max_memory_mb` bounds growth in process RSS since the run started, and the VM
compares RSS against one absolute number, `baseline + limit`. The error quoted
only that number, so `max_memory_mb=50` read "past its 76 MB ceiling". It now
reports the growth, the limit as set, and the resident figure. The ceiling is
a `MemoryCeiling`: still one `int` on the VM (PyPy's attribute limit, #702),
carrying the two parts for the message.
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
from nodus.runtime.memory import (  # noqa: E402
    MemoryCeiling,
    limit_exceeded_message,
    memory_metering_available,
)
from nodus.vm.vm import VM  # noqa: E402

_MB = 1048576
_BIG = 'let x = "a" * 64000000i\nprint(len(x))\n'


def _message(limit_mb, source=_BIG, **run):
    gc.collect()
    result = NodusRuntime(max_memory_mb=limit_mb, timeout_ms=None, max_steps=None).run_source(
        source, **run)
    assert not result.get("ok"), result.get("stdout")
    assert result["error"]["kind"] == "sandbox", result["error"]
    return result["error"]["message"]


def _numbers(message):
    match = re.fullmatch(r"Memory limit exceeded: this run grew the process by ([\d.]+) MB, "
                         r"past its ([\d.]+) MB limit \((\d+) MB resident\)", message)
    assert match, message
    return float(match.group(1)), match.group(2), int(match.group(3))


# closes: #1004
@unittest.skipUnless(memory_metering_available(), "max_memory_mb is not enforceable here")
class TheMessageQuotesTheLimitTheHostSet(unittest.TestCase):
    def test_the_limit_is_the_number_passed(self):
        grew, limit, resident = _numbers(_message(16))
        self.assertEqual(limit, "16")
        # 64 MB allocated: the growth is about that, and the resident figure
        # includes the baseline, so it is larger again.
        self.assertGreater(grew, 16)
        self.assertGreater(resident, grew)

    def test_a_fractional_limit_is_shown_as_given(self):
        self.assertEqual(_numbers(_message(0.5))[1], "0.5")

    def test_a_module_call_inherits_the_same_terms(self):
        with tempfile.TemporaryDirectory() as directory:
            with open(os.path.join(directory, "m.nd"), "w", encoding="utf-8") as handle:
                handle.write('export fn big() {\n    let x = "a" * 64000000i\n    return len(x)\n}\n')
            cwd = os.getcwd()
            os.chdir(directory)
            try:
                message = _message(16, 'import "./m.nd" as m\nprint(m.big())\n', filename="main.nd")
            finally:
                os.chdir(cwd)
        self.assertEqual(_numbers(message)[1], "16")


class TheCeilingIsStillOneInt(unittest.TestCase):
    def test_it_compares_as_the_sum(self):
        ceiling = MemoryCeiling(100 * _MB, 50 * _MB)
        self.assertEqual(ceiling, 150 * _MB)
        self.assertTrue(151 * _MB > ceiling)
        self.assertFalse(149 * _MB > ceiling)
        self.assertIsInstance(ceiling, int)

    def test_the_runtime_sets_one(self):
        runtime = NodusRuntime(max_memory_mb=64, timeout_ms=None, max_steps=None)
        if not memory_metering_available():
            self.skipTest("max_memory_mb is not enforceable here")
        runtime.run_source("print(1)\n")
        ceiling = runtime.active_vm().max_memory_bytes
        self.assertIsInstance(ceiling, MemoryCeiling)
        self.assertEqual(ceiling.limit, 64 * _MB)

    def test_growth_just_past_the_limit_reads_as_past_it(self):
        # Rounded to nearest, 1.001 MB against 1 MB printed "by 1 MB, past its
        # 1 MB limit". Growth is rounded up, so the figure is always above.
        for limit_mb in (1, 50, 0.5, 0.55):
            with self.subTest(limit_mb=limit_mb):
                limit = int(limit_mb * _MB)
                grew, shown, _ = _numbers(limit_exceeded_message(
                    100 * _MB + limit + 1, MemoryCeiling(100 * _MB, limit)))
                self.assertEqual(float(shown), limit_mb)
                self.assertGreater(grew, float(shown))

    def test_a_plain_int_ceiling_keeps_an_absolute_message(self):
        # Set on a VM directly, with no limit recorded: growth is unknowable.
        message = limit_exceeded_message(221 * _MB, 76 * _MB)
        self.assertEqual(message, "Memory limit exceeded: the process reached 221 MB, "
                                  "past its 76 MB ceiling")

    def test_the_vm_builds_its_message_in_one_place(self):
        source = inspect.getsource(VM._check_memory_limit)
        self.assertIn("limit_exceeded_message(current, ceiling)", source)
        self.assertNotIn("MB ceiling", source)


if __name__ == "__main__":
    unittest.main()
