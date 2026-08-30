"""`retry.until` — retry on a predicate, not on failure (#466).

`retry.call` re-attempts when a call **errors**. A call that returns successfully
but returns something *wrong* — a malformed edit, a schema-invalid payload, a
plan that fails its own check — is not a retry trigger for it. That shape existed
only at the workflow altitude (`goal … over … { until … }`, #409), so a caller
wanting a bounded validated retry around one call had to stand up a workflow.

Three things get more than a happy-path assertion, because each is a place a
plausible implementation still passes:

* **the carrier.** The failing result must reach the next attempt. Without it the
  retry is a blind re-roll, which is precisely the thing the pattern exists to
  avoid — and a test that only checks the final value passes on an
  implementation that discards it.
* **the bound that cannot be omitted.** A predicate that never holds is an
  unbounded loop. `budget` grew the same guarantee in #488, where mutation
  testing found that removing it hung the suite.
* **exhaustion is an outcome, not an error.** A caller has to be able to tell
  "the predicate held" from "we ran out of attempts", and both from a thrown
  error.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))  # noqa: E402

from nodus.runtime.embedding import NodusRuntime  # noqa: E402

PRELUDE = 'import "std:retry" as retry\n'


def run(body: str) -> dict:
    return NodusRuntime(timeout_ms=None).run_source(PRELUDE + "fn main() {\n" + body + "\n}\n")


def out(body: str) -> str:
    result = run(body)
    assert result["ok"], result.get("error")
    return result.get("stdout") or ""


# closes: #466
class SatisfiedTests(unittest.TestCase):
    def test_it_stops_as_soon_as_the_predicate_holds(self):
        text = out(
            '    let n = {"v": 0i}\n'
            '    let r = retry.until(fn() { n["v"] = n["v"] + 1i; return n["v"] }, '
            'fn(v) { return v >= 3i }, {"max_attempts": 10i})\n'
            '    print("\\(r["value"]) \\(r["satisfied"]) \\(r["attempts"])")'
        )
        self.assertIn("3 true 3", text)

    def test_a_predicate_true_on_the_first_call_runs_once(self):
        """Not "at least twice". A validated retry whose value is already good
        must not call again — the call may have side effects."""
        text = out(
            '    let n = {"v": 0i}\n'
            '    let r = retry.until(fn() { n["v"] = n["v"] + 1i; return 99i }, '
            'fn(v) { return true }, {"max_attempts": 5i})\n'
            '    print("calls=\\(n["v"]) attempts=\\(r["attempts"])")'
        )
        self.assertIn("calls=1 attempts=1", text)


# closes: #466
class CarrierTests(unittest.TestCase):
    """The failing result reaches the next attempt. This is the whole point:
    re-sending the error is what distinguishes a validated retry from a re-roll."""

    def test_a_one_argument_function_receives_the_previous_result(self):
        text = out(
            "    let seen = []\n"
            '    retry.until(fn(prev) { seen = list_push(seen, prev); return len(seen) }, '
            'fn(v) { return v >= 3i }, {"max_attempts": 5i})\n'
            '    print(seen)'
        )
        self.assertIn("nil", text)
        self.assertIn("1", text)
        self.assertIn("2", text)

    def test_the_first_attempt_receives_nil(self):
        """There is no previous result on attempt one, and inventing one would
        be worse than saying so."""
        text = out(
            '    let first = {"v": "unset"}\n'
            '    retry.until(fn(prev) { if (first["v"] == "unset") { first["v"] = type(prev) } return 1i }, '
            'fn(v) { return true }, {"max_attempts": 2i})\n'
            '    print(first["v"])'
        )
        self.assertIn("nil", text)

    def test_a_zero_argument_function_still_works(self):
        """Accommodating both arities keeps the simple case simple. Forcing every
        caller to accept a parameter it ignores would be noise."""
        text = out(
            '    let r = retry.until(fn() { return 7i }, fn(v) { return v == 7i }, {"max_attempts": 3i})\n'
            '    print("\\(r["value"]) \\(r["satisfied"])")'
        )
        self.assertIn("7 true", text)


# closes: #466
class BoundTests(unittest.TestCase):
    def test_exhaustion_reports_rather_than_raises(self):
        """A caller must be able to tell "held" from "ran out" — and both from a
        thrown error. Raising would make the ordinary case exceptional."""
        result = run(
            '    let r = retry.until(fn() { return 1i }, fn(v) { return false }, '
            '{"max_attempts": 2i})\n'
            '    print("\\(r["satisfied"]) \\(r["attempts"]) \\(r["value"])")'
        )
        self.assertTrue(result["ok"], result.get("error"))
        self.assertIn("false 2 1", result.get("stdout") or "")

    def test_max_attempts_is_respected_exactly(self):
        text = out(
            '    let n = {"v": 0i}\n'
            '    retry.until(fn() { n["v"] = n["v"] + 1i; return 0i }, fn(v) { return false }, '
            '{"max_attempts": 4i})\n'
            '    print(n["v"])'
        )
        self.assertIn("4", text)

    def test_a_never_holding_predicate_with_no_policy_still_terminates(self):
        """The implicit cap. A predicate that never holds and a caller who
        declared no bound is an unbounded loop — the failure `budget` grew its
        own implicit cap to prevent (#488), where mutation testing found that
        removing it hung the suite.

        The runtime step limit is what would otherwise stop this, and a step
        limit firing is not the same as a bound being honoured.
        """
        result = NodusRuntime(timeout_ms=None, max_steps=5_000_000).run_source(
            PRELUDE
            + "fn main() {\n"
            '    let n = {"v": 0i}\n'
            '    let r = retry.until(fn() { n["v"] = n["v"] + 1i; return 0i }, '
            "fn(v) { return false }, nil)\n"
            '    print("attempts=\\(r["attempts"]) satisfied=\\(r["satisfied"])")\n'
            "}\n"
        )
        self.assertTrue(result["ok"], result.get("error"))
        self.assertIn("attempts=10000", result.get("stdout") or "")
        self.assertIn("satisfied=false", result.get("stdout") or "")


# closes: #466
class VocabularyTests(unittest.TestCase):
    """The bound names match `budget`'s so the two altitudes read alike — the
    design note asks for exactly this, and divergent spellings for one concept
    is the shape this codebase catalogues."""

    def test_the_policy_keys_match_the_goal_budget_keys(self):
        import pathlib

        source = (pathlib.Path(__file__).resolve().parents[1]
                  / "src" / "nodus" / "stdlib" / "retry.nd").read_text(encoding="utf-8")
        self.assertIn("max_attempts", source)
        self.assertIn("deadline_ms", source)
        self.assertNotIn("maxAttempts", source)
        self.assertNotIn("timeout_ms", source,
                         "`deadline_ms` is the budget vocabulary; `timeout_ms` is a "
                         "step option and means something else")

    def test_deadline_ms_is_honoured(self):
        """Bounded by time rather than count. Asserted loosely — this box's clock
        ticks at ~15.6 ms, so an exact attempt count would be a timing
        assertion, which CLAUDE.md warns never to write here."""
        result = run(
            '    let r = retry.until(fn() { return 0i }, fn(v) { return false }, '
            '{"deadline_ms": 30})\n'
            '    print("satisfied=\\(r["satisfied"])")'
        )
        self.assertTrue(result["ok"], result.get("error"))
        self.assertIn("satisfied=false", result.get("stdout") or "")


if __name__ == "__main__":
    unittest.main()
