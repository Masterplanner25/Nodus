"""Closed-issue test for #992: `std:strings.repeat` is linear in its output.

It appended one copy per loop pass, and each `out + s` recopied everything built
so far, so its time was quadratic in the output: two million characters took
536 s on 5.17.0. It now builds the result with one `*`.

Timing is not asserted, because this box's timings drift by tens of percent.
The instruction count is asserted instead. The old loop ran about 13
instructions per copy, so a step budget that the new `repeat` fits in many
times over stops the old one before its first thousand copies. Run against the
loop, the first test fails with a step-limit error.

The rest pins what the loop returned, input by input. The count is the loop's:
one copy for each i in 0, 1, 2, ... with i < n.
"""
import sys
import unittest

sys.path.insert(0, "C:/dev/Coding Language/src")

from nodus.runtime.embedding import NodusRuntime  # noqa: E402


def _run(expr, max_steps=None):
    runtime = NodusRuntime(max_steps=max_steps, timeout_ms=None)
    result = runtime.run_source(f'import "std:strings" as s\nprint({expr})\n')
    return result, runtime.get_execution_stats()["instructions_executed"]


# closes: #992
class RepeatIsOneStep(unittest.TestCase):
    def test_a_long_repeat_fits_a_small_step_budget(self):
        # The loop needed about 13,000,000 instructions for this.
        result, _ = _run('len(s.repeat("ab", 1000000i))', max_steps=500)
        self.assertTrue(result.get("ok"), result.get("error"))
        self.assertEqual(result["stdout"], "2000000\n")

    def test_the_instruction_count_does_not_grow_with_n(self):
        _, small = _run('len(s.repeat("a", 10i))')
        _, large = _run('len(s.repeat("a", 100000i))')
        self.assertEqual(small, large)


class RepeatReturnsWhatTheLoopReturned(unittest.TestCase):
    CASES = [
        ('s.repeat("ab", 3i)', "ababab"),
        ('s.repeat("ab", 3)', "ababab"),  # a float count, as the guide writes it
        ('s.repeat("ab", 1i)', "ab"),
        ('s.repeat("ab", 2.5)', "ababab"),  # rounds up
        ('s.repeat("ab", 0.2)', "ab"),
        ('s.repeat("ab", true)', "ab"),
        ('s.repeat("ab", false)', ""),
        ('s.repeat("ab", 0i)', ""),
        ('s.repeat("ab", -2i)', ""),
        ('s.repeat("", 5i)', ""),
        ('s.repeat(5, 0i)', ""),  # no copies, so `s` is never looked at
        ('s.repeat("→", 2i)', "→→"),
    ]

    def test_each_case(self):
        for expr, expected in self.CASES:
            with self.subTest(expr):
                result, _ = _run(expr)
                self.assertTrue(result.get("ok"), result.get("error"))
                self.assertEqual(result["stdout"], expected + "\n")

    def test_a_non_string_is_still_refused(self):
        # `[1] * 2i` is a list, so a bare `s * n` would have returned one.
        for expr in ('s.repeat([1], 2i)', 's.repeat(5, 3i)', 's.repeat(nil, 2i)',
                     's.repeat("a", "x")', 's.repeat("a", nil)'):
            with self.subTest(expr):
                result, _ = _run(expr)
                self.assertFalse(result.get("ok"), result.get("stdout"))
                self.assertEqual(result["error"].get("kind"), "type")


if __name__ == "__main__":
    unittest.main()
