"""A persist failure names the workflow, the place, and the remedy (#498).

Workflow state and step returns must be serializable to the workflow store.
The failure used to be json's own -- `Object of type Closure is not JSON
serializable`, attributed to the `run_workflow(...)` call site, naming neither
the offending cell nor the step. The persist path now walks the snapshot for
the culprit and says what it is, where it is, and what to do -- the seam that
assignment-time rejection or a wider format would attach to (recorded on the
issue as the explicitly deferred halves).
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))  # noqa: E402

from nodus.runtime.embedding import NodusRuntime  # noqa: E402


def _run(source: str) -> dict:
    return NodusRuntime(timeout_ms=None).run_source(source)


# closes: #498
class PersistErrorNamingTests(unittest.TestCase):
    def test_channel_in_state_names_the_cell(self):
        result = _run(
            "workflow nocp {\n"
            "    state ch = 0i\n"
            "    step a { ch = channel(); return 1i }\n"
            "}\n"
            "fn main() { let r = run_workflow(nocp) }\n"
        )
        self.assertFalse(result["ok"])
        text = str(result)
        self.assertIn("workflow 'nocp' could not be persisted", text)
        self.assertIn("state cell 'ch'", text)
        self.assertIn("Channel", text)
        self.assertIn("durable: false", text)

    def test_step_returning_a_closure_names_the_step(self):
        result = _run(
            "workflow retfn {\n"
            "    step a { return fn(x) { return x + 1i } }\n"
            "    step b after a { return 0i }\n"
            "}\n"
            "fn main() { let r = run_workflow(retfn) }\n"
        )
        self.assertFalse(result["ok"])
        text = str(result)
        self.assertIn("workflow 'retfn' could not be persisted", text)
        self.assertIn("step 'a'", text)
        self.assertIn("Closure", text)

    def test_record_in_state_suggests_a_map(self):
        result = _run(
            "workflow recs {\n"
            "    state r = 0i\n"
            "    step a { r = record { x: 1i }; return 1i }\n"
            "}\n"
            "fn main() { let r = run_workflow(recs) }\n"
        )
        self.assertFalse(result["ok"])
        text = str(result)
        self.assertIn("state cell 'r'", text)
        self.assertIn("Record", text)
        self.assertIn("map instead of a record", text)

    def test_durable_false_survives_a_checkpoint_snapshot(self):
        """The sibling paths this issue's control test exposed: the metadata
        copy of the state and the checkpoint snapshots carried non-durable
        cells even though the top-level `workflow_state` filtered them, so
        `durable: false` did not actually protect a live value from the
        persist. Every copy applies the same rule now."""
        result = _run(
            "workflow live {\n"
            "    state ch = 0i with { durable: false }\n"
            '    step a { ch = channel(); checkpoint "cp"; return 1i }\n'
            "}\n"
            "fn main() {\n"
            "    let r = run_workflow(live)\n"
            '    let f = r["failed"]\n'
            '    print("FAILED=\\(f)")\n'
            "}\n"
        )
        self.assertTrue(result["ok"], result.get("error"))
        self.assertIn("FAILED=[]", result.get("stdout") or "")

    def test_durable_false_cell_still_opts_out_entirely(self):
        """Falsifiability control and the shipped remedy: a cell declared
        `durable: false` (5.2.0, this issue's declared-durability half) holds
        a live value and the run completes."""
        result = _run(
            "workflow live {\n"
            "    state ch = 0i with { durable: false }\n"
            "    step a { ch = channel(); return 1i }\n"
            "}\n"
            "fn main() {\n"
            "    let r = run_workflow(live)\n"
            '    let f = r["failed"]\n'
            '    print("FAILED=\\(f)")\n'
            "}\n"
        )
        self.assertTrue(result["ok"], result.get("error"))
        self.assertIn("FAILED=[]", result.get("stdout") or "")


if __name__ == "__main__":
    unittest.main()
