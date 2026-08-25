"""Source persistence is disclosed and controllable (#499).

Every workflow run persists the whole module source into `.nodus/graphs/` --
it is the cross-process rebuild handle, so it cannot simply be removed. What
this issue demanded is disclosure and control:

- the guide and SECURITY_POSTURE.md now say it happens (not testable here);
- `nodus workflow cleanup` has a finite default retention (30 days) instead of
  "unset means forever";
- an embedder can opt out per runtime with
  `NodusRuntime(persist_workflow_source=False)`, with resume degrading as
  documented -- a `run_file` run rebuilds from the file as it is on disk, a
  `run_source` run is not resumable across processes.
"""
import io
import json
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stdout

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))  # noqa: E402

from nodus.cli.cli import DEFAULT_WORKFLOW_RETENTION_SECONDS, _default_retention_seconds, main  # noqa: E402
from nodus.runtime.embedding import NodusRuntime  # noqa: E402

SOURCE = """
workflow w {
    step a { checkpoint "cp"; return 1i }
    step b after a { return 2i }
}
fn main() {
    let r = run_workflow(w)
    let g = r["graph_id"]
    print("GID=\\(g)")
}
"""


def _gid(stdout: str) -> str:
    for line in (stdout or "").splitlines():
        if line.startswith("GID="):
            return line[4:].strip()
    raise AssertionError(f"no graph id in {stdout!r}")


class _Harness(unittest.TestCase):
    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self._cwd = os.getcwd()
        os.chdir(self._td.name)
        self.addCleanup(self._restore)

    def _restore(self):
        os.chdir(self._cwd)
        self._td.cleanup()

    def _run(self, **runtime_kwargs) -> str:
        path = os.path.join(self._td.name, "wf.nd")
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(SOURCE)
        started = NodusRuntime(timeout_ms=None, **runtime_kwargs).run_file(path)
        return _gid(started.get("stdout"))

    def _state(self, gid: str) -> dict:
        with open(
            os.path.join(self._td.name, ".nodus", "graphs", f"{gid}.json"),
            encoding="utf-8",
        ) as handle:
            return json.load(handle)


# closes: #499
class SourcePersistencePolicyTests(_Harness):
    def test_default_still_persists_the_source(self):
        """Falsifiability control: the opt-out must not become the default --
        the stored source is what cross-process resume rebuilds from."""
        gid = self._run()
        meta = self._state(gid)["metadata"]
        self.assertIn("workflow w", meta["workflow_source_code"])
        self.assertNotIn("workflow_source_persisted", meta)

    def test_opt_out_stores_no_source_and_says_so(self):
        gid = self._run(persist_workflow_source=False)
        meta = self._state(gid)["metadata"]
        self.assertIsNone(meta["workflow_source_code"])
        self.assertIs(meta["workflow_source_persisted"], False)
        # The whole point: the program text is not in the persisted state.
        self.assertNotIn("fn main", json.dumps(self._state(gid)))

    def test_opted_out_run_file_still_resumes_from_disk(self):
        gid = self._run(persist_workflow_source=False)
        resumed = NodusRuntime(timeout_ms=None).run_source(
            'fn main() {{ let r = resume_workflow("{}", "cp"); '
            'let s = r["steps"]; print("STEPS=\\(s)") }}'.format(gid)
        )
        stdout = resumed.get("stdout") or ""
        self.assertIn("STEPS=", stdout)
        stderr = resumed.get("stderr") or ""
        self.assertIn("opted out of source persistence", stderr)
        self.assertNotIn("predates source recording", stderr)

    def test_default_retention_is_finite(self):
        old = os.environ.pop("NODUS_WORKFLOW_RETENTION_SECONDS", None)
        try:
            self.assertEqual(
                _default_retention_seconds(), DEFAULT_WORKFLOW_RETENTION_SECONDS
            )
            os.environ["NODUS_WORKFLOW_RETENTION_SECONDS"] = "60"
            self.assertEqual(_default_retention_seconds(), 60)
            os.environ["NODUS_WORKFLOW_RETENTION_SECONDS"] = "0"
            self.assertEqual(_default_retention_seconds(), 0)
            os.environ["NODUS_WORKFLOW_RETENTION_SECONDS"] = "junk"
            self.assertEqual(
                _default_retention_seconds(), DEFAULT_WORKFLOW_RETENTION_SECONDS
            )
        finally:
            if old is None:
                os.environ.pop("NODUS_WORKFLOW_RETENTION_SECONDS", None)
            else:
                os.environ["NODUS_WORKFLOW_RETENTION_SECONDS"] = old

    def test_cleanup_removes_old_terminal_runs_by_default(self):
        """Unset retention used to mean *forever* -- cleanup removed nothing
        without --force or an env var."""
        import time

        gid = self._run()
        state_path = os.path.join(self._td.name, ".nodus", "graphs", f"{gid}.json")
        # Backdate the snapshot past the default retention window. Age is the
        # state file's mtime -- the stored `updated_at` is process-monotonic
        # and unusable for wall-clock retention.
        ancient = time.time() - DEFAULT_WORKFLOW_RETENTION_SECONDS - 3600
        os.utime(state_path, (ancient, ancient))

        old = os.environ.pop("NODUS_WORKFLOW_RETENTION_SECONDS", None)
        try:
            out = io.StringIO()
            with redirect_stdout(out):
                code = main(["nodus", "workflow", "cleanup"])
        finally:
            if old is not None:
                os.environ["NODUS_WORKFLOW_RETENTION_SECONDS"] = old
        self.assertEqual(code, 0)
        payload = json.loads(out.getvalue().strip())
        self.assertEqual(payload["retention_seconds"], DEFAULT_WORKFLOW_RETENTION_SECONDS)
        self.assertIn(gid, payload["removed"])
        self.assertFalse(os.path.exists(state_path))

    def test_cleanup_leaves_fresh_terminal_runs(self):
        """The control that catches the age bug: `updated_at` is
        process-monotonic, so comparing it to wall-clock time made every run
        look ancient -- a default retention would then have removed runs
        finished seconds ago. Age is file mtime now."""
        gid = self._run()
        state_path = os.path.join(self._td.name, ".nodus", "graphs", f"{gid}.json")
        old = os.environ.pop("NODUS_WORKFLOW_RETENTION_SECONDS", None)
        try:
            out = io.StringIO()
            with redirect_stdout(out):
                code = main(["nodus", "workflow", "cleanup"])
        finally:
            if old is not None:
                os.environ["NODUS_WORKFLOW_RETENTION_SECONDS"] = old
        self.assertEqual(code, 0)
        payload = json.loads(out.getvalue().strip())
        self.assertNotIn(gid, payload["removed"])
        self.assertTrue(os.path.exists(state_path))


if __name__ == "__main__":
    unittest.main()
