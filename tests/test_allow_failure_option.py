"""`with { allow_failure: true }`: a step may fail without failing the run (#475).

The last inexpressible piece of #475's failure semantics. Question 1 (a failure
poisons descendants, not the graph) shipped in 5.1.0; question 2 (what a join
does with a failed source) is answered by `upstream_failed` plus `on: [...]`.
What remained was tolerance: the status vocabulary describes what happened, but
nothing let a step say what the run will tolerate.

Semantics, decided:
- the step's *status* stays `failed` -- history is not rewritten;
- dependents are poisoned (`upstream_failed`) or satisfied (`on: ["failed"]`)
  exactly as for any failure -- tolerance is the run's verdict, not readiness;
- the run completes; the step appears under `tolerated`, not `failed`;
- retries run first: tolerance applies to an exhausted step, not each attempt.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))  # noqa: E402

from nodus.runtime.embedding import NodusRuntime  # noqa: E402


def _run(source: str) -> dict:
    return NodusRuntime(timeout_ms=None).run_source(source)


# closes: #475
class AllowFailureTests(unittest.TestCase):
    def test_tolerated_failure_completes_the_run(self):
        result = _run(
            "workflow w {\n"
            '    step flaky with { allow_failure: true } { throw "boom" }\n'
            "    step solid { return 1i }\n"
            "}\n"
            "fn main() {\n"
            "    let r = run_workflow(w)\n"
            '    print("R=\\(r)")\n'
            "}\n"
        )
        self.assertTrue(result["ok"], result.get("error"))
        stdout = result.get("stdout") or ""
        self.assertIn('"failed": []', stdout)
        self.assertIn('"tolerated": ["flaky"]', stdout)
        self.assertIn('"flaky": "failed"', stdout)  # statuses tell the truth
        self.assertIn('"solid": "completed"', stdout)

    def test_dependents_are_still_poisoned(self):
        """Tolerance is the run's verdict, not downstream readiness: the value
        still does not exist, so a default join is upstream_failed."""
        result = _run(
            "workflow w {\n"
            '    step flaky with { allow_failure: true } { throw "boom" }\n'
            "    step needs_it after flaky { return 1i }\n"
            "}\n"
            "fn main() {\n"
            "    let r = run_workflow(w)\n"
            '    print("R=\\(r)")\n'
            "}\n"
        )
        stdout = result.get("stdout") or ""
        self.assertIn('"needs_it": "upstream_failed"', stdout)
        self.assertIn('"failed": []', stdout)

    def test_an_on_failed_join_still_fires(self):
        result = _run(
            "workflow w {\n"
            '    step flaky with { allow_failure: true } { throw "boom" }\n'
            '    step recover after flaky with { on: ["failed"] } { return "recovered" }\n'
            "}\n"
            "fn main() {\n"
            "    let r = run_workflow(w)\n"
            '    print("R=\\(r)")\n'
            "}\n"
        )
        stdout = result.get("stdout") or ""
        self.assertIn('"recover": "recovered"', stdout)
        self.assertIn('"failed": []', stdout)

    def test_without_the_option_the_run_still_fails(self):
        """Falsifiability control: tolerance must be declared, never inferred."""
        result = _run(
            "workflow w {\n"
            '    step flaky { throw "boom" }\n'
            "    step solid { return 1i }\n"
            "}\n"
            "fn main() {\n"
            "    let r = run_workflow(w)\n"
            '    print("R=\\(r)")\n'
            "}\n"
        )
        stdout = result.get("stdout") or ""
        self.assertIn('"failed": ["flaky"]', stdout)
        self.assertNotIn("tolerated", stdout)

    def test_retries_run_before_tolerance(self):
        result = _run(
            "workflow w {\n"
            "    step flaky with { allow_failure: true, retries: 2, retry_delay_ms: 1 } "
            '{ throw "boom" }\n'
            "}\n"
            "fn main() {\n"
            "    let r = run_workflow(w)\n"
            '    let a = r["attempts"]\n'
            '    print("R=\\(r)")\n'
            "}\n"
        )
        stdout = result.get("stdout") or ""
        self.assertIn('"tolerated": ["flaky"]', stdout)
        self.assertIn('"task_1": 3.0', stdout)  # 1 + 2 retries, then tolerated


if __name__ == "__main__":
    unittest.main()
