"""A mid-step checkpoint is a re-entry label, and re-entry must be deterministic (#486).

Resuming from a checkpoint re-enters the step that recorded it from the top.
That is the decided semantics -- effects before the checkpoint run again, and
the guide says so -- but re-derivation of *state* must be deterministic:

- a plain assignment re-applies onto the restored base (idempotent), and
- a fold contribution (`merge: "sum"` / `"append"` / `"union"`) re-contributes
  onto the *committed* base it originally contributed to.

The second half broke when 5.2.0 added folds: the checkpoint snapshot
deliberately includes the step's pending contributions (so the value is
observable at the checkpoint), and that same snapshot was also the rollback
base -- so a resume restored the contribution and then re-made it, counting it
twice. `counter += 1i; checkpoint "mid"` gave 1, 2, 3 across resumes, silently.

The fix records `resume_state` -- the committed base without the checkpointing
step's pending fold -- beside `state` on the engine checkpoint, and rollback
prefers it. Older persisted checkpoints have only `state` and keep the old
behaviour rather than becoming unresumable.
"""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))  # noqa: E402

from nodus.runtime.embedding import NodusRuntime  # noqa: E402

RESUME = (
    'fn main() {{ let r = resume_workflow("{gid}", "mid"); '
    'let s = r["state"]; print("STATE=\\(s)") }}'
)


def _gid(stdout: str) -> str:
    for line in (stdout or "").splitlines():
        if line.startswith("GID="):
            return line[4:].split()[0].strip()
    raise AssertionError(f"no graph id in {stdout!r}")


class _CheckpointHarness(unittest.TestCase):
    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self._cwd = os.getcwd()
        os.chdir(self._td.name)
        self.addCleanup(self._restore)

    def _restore(self):
        os.chdir(self._cwd)
        self._td.cleanup()

    def _start(self, source: str) -> str:
        path = os.path.join(self._td.name, "wf.nd")
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(source)
        started = NodusRuntime(timeout_ms=None).run_file(path)
        return _gid(started.get("stdout"))

    def _resume(self, gid: str) -> str:
        resumed = NodusRuntime(timeout_ms=None).run_source(RESUME.format(gid=gid))
        return (resumed.get("stdout") or "").strip()


# closes: #486
class FoldedCellsAreDeterministicAcrossResumesTests(_CheckpointHarness):
    def test_sum_contribution_before_checkpoint_is_not_double_counted(self):
        gid = self._start("""
workflow w {
    state counter = 0i with { merge: "sum" }
    step a { counter += 1i; checkpoint "mid"; return 1i }
    step b after a { return 2i }
}
fn main() {
    let r = run_workflow(w)
    let g = r["graph_id"]
    let s = r["state"]
    print("GID=\\(g) STATE=\\(s)")
}
""")
        self.assertIn('"counter": 1', self._resume(gid))
        # The failure grew with each resume (1, 2, 3), so one resume proving
        # nothing is why there are two.
        self.assertIn('"counter": 1', self._resume(gid))

    def test_append_contribution_before_checkpoint_is_not_duplicated(self):
        gid = self._start("""
workflow w {
    state seen = [] with { merge: "append" }
    step a { seen += ["x"]; checkpoint "mid"; return 1i }
    step b after a { return 2i }
}
fn main() {
    let r = run_workflow(w)
    let g = r["graph_id"]
    let s = r["state"]
    print("GID=\\(g) STATE=\\(s)")
}
""")
        first = self._resume(gid)
        self.assertIn('"seen": ["x"]', first)
        self.assertNotIn('"x", "x"', first)

    def test_plain_cell_semantics_are_unchanged(self):
        """The issue's own control, kept so this is not 'fixed' by mistake:
        a plain assignment after the checkpoint re-derives to the same value."""
        gid = self._start("""
workflow w {
    state passes = 0i
    step a { checkpoint "mid"; passes = passes + 1i; return 1i }
    step b after a { return 2i }
}
fn main() {
    let r = run_workflow(w)
    let g = r["graph_id"]
    let s = r["state"]
    print("GID=\\(g) STATE=\\(s)")
}
""")
        self.assertIn('"passes": 1', self._resume(gid))
        self.assertIn('"passes": 1', self._resume(gid))

    def test_reentry_is_from_the_top_of_the_step(self):
        """Pins the *decided* semantics this issue documents: work before a
        mid-step checkpoint re-executes on resume. A positional-resume design
        would revise this deliberately; nothing should change it by accident."""
        gid = self._start("""
workflow w {
    step a { print("BEFORE"); checkpoint "mid"; print("AFTER"); return 1i }
    step b after a { return 2i }
}
fn main() {
    let r = run_workflow(w)
    let g = r["graph_id"]
    print("GID=\\(g)")
}
""")
        resumed = NodusRuntime(timeout_ms=None).run_source(
            RESUME.format(gid=gid)
        )
        stdout = resumed.get("stdout") or ""
        self.assertIn("BEFORE", stdout)
        self.assertIn("AFTER", stdout)


if __name__ == "__main__":
    unittest.main()
