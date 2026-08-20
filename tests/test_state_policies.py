"""A `state` cell can declare how it merges and whether it is durable (D6).

Two axes, not three. An earlier framing had typing here as well, but #479 is about
untyped *step outputs* and hand-written tool schemas and never mentions state --
so the `: type` slot stays free for a separate decision.

    state counter = 0i  with { merge: "once" }
    state conn    = nil with { durable: false }

Both reuse `with { ... }`, the same named-map mechanism steps already use, so
there is no new syntax and the policy stays inspectable data.
"""
import glob
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))  # noqa: E402

from nodus.orchestration.workflow_state import (  # noqa: E402
    DEFAULT_STATE_MERGE,
    STATE_MERGE_POLICIES,
)
from nodus.runtime.embedding import NodusRuntime  # noqa: E402


def _run(source: str, keep: bool = False):
    """Run in a temp dir; optionally hand back the persisted graph state."""
    with tempfile.TemporaryDirectory() as td:
        cwd = os.getcwd()
        os.chdir(td)
        try:
            result = NodusRuntime(timeout_ms=None, max_steps=None).run_source(source)
            persisted = None
            if keep:
                files = [f for f in glob.glob(".nodus/graphs/*.json") if "checkpoint" not in f]
                if files:
                    with open(files[0], encoding="utf-8") as handle:
                        persisted = json.load(handle).get("workflow_state")
            return result, persisted
        finally:
            os.chdir(cwd)


RACE = """
workflow race {{
    state counter = 0i{policy}
    step a {{ let seen = counter; sleep(20i); counter = seen + 1i; return 1i }}
    step b {{ let seen = counter; sleep(20i); counter = seen + 1i; return 2i }}
    step j after a, b {{ return 0i }}
}}
fn main() {{ let r = run_workflow(race); let s = r["state"]; print("STATE=\\(s)") }}
"""


class DeclaringAnySilencesTheWarningTests(unittest.TestCase):
    """The point of `any` being sayable at all.

    An undeclared cell warns, because that warning is the only thing standing
    between a lost update and silence. An explicit `merge: "any"` says the author
    knows the branches agree -- so the warning is quieted by stating intent, not
    by a default nobody wrote.
    """

    def test_an_undeclared_cell_still_warns(self):
        result, _ = _run(RACE.format(policy=""))
        self.assertIn("both wrote state 'counter'", result.get("stderr") or "")

    def test_declaring_any_silences_it(self):
        result, _ = _run(RACE.format(policy=' with { merge: "any" }'))
        self.assertNotIn("both wrote state", result.get("stderr") or "")

    def test_declaring_any_does_not_change_the_value(self):
        """`any` is a statement about intent, not a behaviour change: last write
        still wins, and the update is still lost."""
        result, _ = _run(RACE.format(policy=' with { merge: "any" }'))
        self.assertIn('STATE={"counter": 1}', result.get("stdout") or "")

    def test_the_default_is_any(self):
        self.assertEqual("any", DEFAULT_STATE_MERGE)


class OnceMakesAConcurrentWriteAnErrorTests(unittest.TestCase):
    """Falsifiable: with the policy lookup removed, this run succeeds silently."""

    def test_two_concurrent_writers_fail_the_run(self):
        result, _ = _run(RACE.format(policy=' with { merge: "once" }'))
        error = result.get("error") or {}
        message = error.get("message", "") if isinstance(error, dict) else str(error)
        self.assertIn("merge:", message)
        self.assertIn("counter", message)
        self.assertIn("a", message)
        self.assertIn("b", message)

    def test_a_single_writer_is_fine(self):
        result, _ = _run(
            """
workflow solo {
    state counter = 0i with { merge: "once" }
    step a { counter = 1i; return 1i }
    step b after a { return 2i }
}
fn main() { let r = run_workflow(solo); let s = r["state"]; print("STATE=\\(s)") }
"""
        )
        self.assertIsNone(result.get("error"), msg=result.get("error"))
        self.assertIn('STATE={"counter": 1}', result.get("stdout") or "")

    def test_ordered_writers_are_fine(self):
        """`once` is about *concurrent* writers. A sequential chain writing the
        same cell is ordinary and must not fail."""
        result, _ = _run(
            """
workflow chain {
    state log = "" with { merge: "once" }
    step a { log = "a"; return 1i }
    step b after a { log = "ab"; return 2i }
}
fn main() { let r = run_workflow(chain); let s = r["state"]; print("STATE=\\(s)") }
"""
        )
        self.assertIsNone(result.get("error"), msg=result.get("error"))
        self.assertIn('STATE={"log": "ab"}', result.get("stdout") or "")


class DurableFalseKeepsACellOutOfTheStoreTests(unittest.TestCase):
    """#498: a cell holding a live handle has no meaning after a resume, and there
    was no way to say so -- every cell was persisted, and a value `json` cannot
    encode killed the run at the first persist."""

    SOURCE = """
workflow w {
    state keep = 0i
    state scratch = 0i with { durable: false }
    step a { keep = 7i; scratch = 99i; checkpoint "cp"; return 1i }
}
fn main() { let r = run_workflow(w); let s = r["state"]; print("STATE=\\(s)") }
"""

    def test_the_cell_is_live_in_memory(self):
        result, _ = _run(self.SOURCE)
        self.assertIn('"scratch": 99', result.get("stdout") or "")

    def test_the_cell_is_absent_from_the_persisted_state(self):
        _, persisted = _run(self.SOURCE, keep=True)
        self.assertIsNotNone(persisted, "nothing was persisted")
        self.assertIn("keep", persisted)
        self.assertNotIn("scratch", persisted)

    def test_excluded_rather_than_nulled(self):
        """A cell restored as `nil` would look like a value the workflow had set,
        which is a different lie from the one being fixed."""
        _, persisted = _run(self.SOURCE, keep=True)
        self.assertEqual({"keep": 7}, persisted)


class UnsupportedPoliciesAreRefusedWhereWrittenTests(unittest.TestCase):
    """A declaration the runtime accepts must bind or be refused. `merge: "sum"`
    that quietly still last-write-wins would be the exact failure this area is
    about."""

    def _message(self, policy: str) -> str:
        result, _ = _run(
            """
workflow w {{
    state c = 0i with {{ {policy} }}
    step a {{ c = 1i; return 1i }}
}}
fn main() {{ let r = run_workflow(w); print("ran") }}
""".format(policy=policy)
        )
        error = result.get("error") or {}
        return error.get("message", "") if isinstance(error, dict) else str(error)

    def test_fold_is_refused_and_says_why(self):
        message = self._message('merge: "sum"')
        self.assertIn("unknown policy", message)
        self.assertIn("write-at-join", message)
        self.assertIn("#485", message)

    def test_an_unknown_policy_is_refused(self):
        self.assertIn("unknown policy", self._message('merge: "wibble"'))

    def test_durable_expects_a_boolean(self):
        self.assertIn("true or false", self._message('durable: "yes"'))

    def test_an_unknown_option_key_is_refused_by_the_parser(self):
        message = self._message('mergee: "any"')
        self.assertIn("Unsupported workflow state option", message)

    def test_the_vocabulary_is_only_what_the_runtime_honours(self):
        """Fold waits for the emission model rather than shipping as a name that
        does nothing -- the same bar `skipped` and `omitted` had to clear."""
        self.assertEqual({"any", "once"}, set(STATE_MERGE_POLICIES))


if __name__ == "__main__":
    unittest.main()
