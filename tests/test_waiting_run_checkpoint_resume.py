"""A checkpoint resume of a genuinely waiting run is refused, not a no-op (#482).

`resume_workflow(id, "checkpoint")` on a waiting run used to re-enter the
waiting step, which hit its `workflow_wait` again -- the run went straight back
to `waiting` behind a healthy-looking result map (`ok` not false, nothing in
`failed`, one more duplicate checkpoint entry as the only trace). With a
payload alongside the checkpoint it was worse: the rollback re-armed the wait
and the payload was silently discarded.

Both combinations are refused now, naming the event the run is waiting on and
the call that advances it. "Genuinely waiting" means the persisted graph state
agrees -- a record marked waiting administratively over a graph that ran past
the wait (a stale registration) still resumes and clears the mark, which
`test_nodus_workflow_framework.py::test_resume_clears_wait_registration` pins.
"""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))  # noqa: E402

from nodus.runtime.embedding import NodusRuntime  # noqa: E402

SOURCE = """
workflow ask {
    step q { checkpoint "started"; print("asking human..."); return workflow_wait("go") }
    step act after q { let a = workflow_resume_payload(); return a["reply"] }
}
fn main() {
    let r = run_workflow(ask)
    let g = r["graph_id"]
    let s = r["status"]
    print("GID=\\(g) STATUS=\\(s)")
}
"""


def _gid(stdout: str) -> str:
    for line in (stdout or "").splitlines():
        if line.startswith("GID="):
            return line[4:].split()[0].strip()
    raise AssertionError(f"no graph id in {stdout!r}")


# closes: #482
class WaitingRunCheckpointResumeTests(unittest.TestCase):
    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self._cwd = os.getcwd()
        os.chdir(self._td.name)
        self.addCleanup(self._restore)
        path = os.path.join(self._td.name, "wf.nd")
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(SOURCE)
        started = NodusRuntime(timeout_ms=None).run_file(path)
        self.gid = _gid(started.get("stdout"))

    def _restore(self):
        os.chdir(self._cwd)
        self._td.cleanup()

    def _resume(self, args: str) -> str:
        resumed = NodusRuntime(timeout_ms=None).run_source(
            'fn main() {{ let r = resume_workflow("{}", {}); '
            'print("R=\\(r)") }}'.format(self.gid, args)
        )
        return resumed.get("stdout") or ""

    def test_checkpoint_only_resume_is_refused_with_the_real_reason(self):
        stdout = self._resume('"started"')
        self.assertIn('"ok": false', stdout)
        self.assertIn("waiting on event 'go'", stdout)
        self.assertIn("pass a payload", stdout)
        self.assertIn("waiting_run_checkpoint_resume", stdout)
        # The refusal happens before any re-execution: the waiting step's
        # pre-wait effect must not fire again. Before the fix it did, and the
        # duplicated checkpoint entry was the trace of each no-op attempt.
        self.assertNotIn("asking human...", stdout)

    def test_checkpoint_with_payload_is_refused_naming_the_discard(self):
        stdout = self._resume('"started", {"reply": "eaten"}')
        self.assertIn('"ok": false', stdout)
        self.assertIn("discards the payload", stdout)
        self.assertIn("drop the checkpoint argument", stdout)
        self.assertNotIn("asking human...", stdout)

    def test_payload_resume_still_advances_the_run(self):
        """Falsifiability control: the refusal must not catch the call that
        works -- and the run must still be advanceable after refused attempts."""
        self._resume('"started"')
        stdout = self._resume('{"reply": "ship it"}')
        self.assertNotIn('"ok": false', stdout)
        self.assertIn('"act": "ship it"', stdout)


if __name__ == "__main__":
    unittest.main()
