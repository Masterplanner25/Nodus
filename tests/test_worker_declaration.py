"""`step ... with { worker: "name" }` is a declaration about isolation (#492).

With a dispatcher registered, an unsatisfiable name already failed --
`WorkerPool.submit` waits for a worker advertising the capability and raises
"No workers registered with capability: X". Without one, the step fell through
to in-process execution and reported success, so `worker: "hardened-sandbox"`
behaved exactly like no declaration at all.

The check existed; only one of the two paths reached it. That is the shape
recorded in CLAUDE.md, and the reason the tests assert from *both* the CLI and
an embedded runtime rather than trusting one to stand for the other.

5.3.0 through 5.21.0 warned and ran the step in-process. Since 6.0.0 the
workflow is refused before any step runs (#798).
"""

import os
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))  # noqa: E402

from nodus.runtime.embedding import NodusRuntime  # noqa: E402


REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

WORKER_SOURCE = """
workflow w {
    step isolated with { worker: "hardened-sandbox" } {
        return "done"
    }
}

fn main() {
    let r = run_workflow(w)
    print("steps: \\(r["steps"])")
}
"""

PLAIN_SOURCE = """
workflow w {
    step ordinary {
        return "done"
    }
}

fn main() {
    let r = run_workflow(w)
    print("steps: \\(r["steps"])")
}
"""

WARNING = "no worker dispatcher is registered"


def _error(result) -> str:
    error = result.get("error") or {}
    return error.get("message", "") if isinstance(error, dict) else str(error)


class RecordingDispatcher:
    """The minimum a dispatcher is: something with a compatible `.submit`."""

    force_dispatch = True
    event_bus = None

    def __init__(self):
        self.seen: list[tuple] = []

    def submit(self, task_id, args, execute, *, delay_ms=None,
               requirement=None, requirement_timeout_ms=None):
        self.seen.append((task_id, requirement))
        return execute()


class EmbeddedWorkerTests(unittest.TestCase):
    # closes: #798
    def test_an_unhonoured_worker_is_refused_before_the_step_runs(self):
        source = WORKER_SOURCE.replace('return "done"', 'print("BODY RAN")\n        return "done"')
        result = NodusRuntime(timeout_ms=None).run_source(source)
        self.assertFalse(result["ok"])
        self.assertEqual(result["error"]["kind"], "workflow_error")
        self.assertIn(WARNING, _error(result))
        self.assertIn("hardened-sandbox", _error(result))
        self.assertNotIn("BODY RAN", result["stdout"])

    def test_the_refusal_names_every_remedy(self):
        """A refusal with no remedy leaves the reader nowhere to go."""
        message = _error(NodusRuntime(timeout_ms=None).run_source(WORKER_SOURCE))
        self.assertIn("nodus serve", message)
        self.assertIn("worker_dispatcher=", message)
        self.assertIn("remove the declaration", message)

    # closes: #492
    def test_a_dispatcher_can_be_supplied_to_an_embedded_runtime(self):
        """`vm.worker_dispatcher` was set only by services/server.py.

        An embedder therefore could not honour a worker declaration at all --
        which is why the declaration had no reachable meaning outside a server.
        """
        dispatcher = RecordingDispatcher()
        result = NodusRuntime(
            timeout_ms=None, worker_dispatcher=dispatcher
        ).run_source(WORKER_SOURCE)
        self.assertTrue(result["ok"])
        self.assertEqual(
            [requirement for _task, requirement in dispatcher.seen],
            ["hardened-sandbox"],
        )

    def test_a_supplied_dispatcher_is_not_refused(self):
        dispatcher = RecordingDispatcher()
        result = NodusRuntime(
            timeout_ms=None, worker_dispatcher=dispatcher
        ).run_source(WORKER_SOURCE)
        self.assertTrue(result["ok"], result)
        self.assertNotIn(WARNING, result["stderr"] + _error(result))

    def test_a_workflow_with_no_worker_is_silent(self):
        """The warning must not fire for every workflow ever run."""
        result = NodusRuntime(timeout_ms=None).run_source(PLAIN_SOURCE)
        self.assertTrue(result["ok"])
        self.assertNotIn(WARNING, result["stderr"])

    def test_the_default_is_unchanged(self):
        self.assertIsNone(NodusRuntime().worker_dispatcher)


class CliWorkerTests(unittest.TestCase):
    """The CLI builds a VM directly and never constructs a NodusRuntime.

    Two paths, so both are checked -- the same reason the deny-by-default tests
    pin CLI and embedded behaviour separately.
    """

    def setUp(self):
        self._dir = tempfile.TemporaryDirectory()
        self.root = self._dir.name
        self.addCleanup(self._dir.cleanup)

    def run_source(self, source: str) -> tuple[str, int]:
        path = os.path.join(self.root, "w.nd")
        with open(path, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(source)
        env = dict(os.environ)
        env["PYTHONPATH"] = os.path.join(REPO_ROOT, "src")
        completed = subprocess.run(
            [sys.executable, os.path.join(REPO_ROOT, "nodus.py"), "run", path],
            capture_output=True, cwd=self.root, env=env, timeout=120,
        )
        output = (completed.stdout + completed.stderr).decode("utf-8", "replace")
        return output, completed.returncode

    # closes: #798
    def test_cli_refuses_an_unhonoured_worker(self):
        output, code = self.run_source(WORKER_SOURCE)
        self.assertIn(WARNING, output)
        self.assertIn("hardened-sandbox", output)
        self.assertEqual(code, 1, "the step ran in-process: the 5.x behaviour")
        self.assertNotIn("steps:", output)

    def test_cli_is_silent_without_a_worker(self):
        output, code = self.run_source(PLAIN_SOURCE)
        self.assertNotIn(WARNING, output)
        self.assertEqual(code, 0)


if __name__ == "__main__":
    unittest.main()
