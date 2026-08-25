"""`step ... with { worker: "name" }` is a declaration about isolation (#492).

With a dispatcher registered, an unsatisfiable name already failed --
`WorkerPool.submit` waits for a worker advertising the capability and raises
"No workers registered with capability: X". Without one, the step fell through
to in-process execution and reported success, so `worker: "hardened-sandbox"`
behaved exactly like no declaration at all.

The check existed; only one of the two paths reached it. That is the shape
recorded in CLAUDE.md, and the reason the test asserts the warning fires from
*both* the CLI and an embedded runtime rather than trusting one to stand for
the other -- they capture stderr differently, which is itself easy to mistake
for the bug.
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
    # closes: #492
    def test_unhonoured_worker_warns(self):
        result = NodusRuntime(timeout_ms=None).run_source(WORKER_SOURCE)
        self.assertTrue(result["ok"])
        self.assertIn(WARNING, result["stderr"])
        self.assertIn("hardened-sandbox", result["stderr"])

    def test_the_warning_names_both_remedies_and_the_flag_day(self):
        """A warning with no remedy is a warning people learn to scroll past."""
        stderr = NodusRuntime(timeout_ms=None).run_source(WORKER_SOURCE)["stderr"]
        self.assertIn("nodus serve", stderr)
        self.assertIn("worker_dispatcher=", stderr)
        self.assertIn("6.0.0", stderr)

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

    def test_a_supplied_dispatcher_silences_the_warning(self):
        dispatcher = RecordingDispatcher()
        result = NodusRuntime(
            timeout_ms=None, worker_dispatcher=dispatcher
        ).run_source(WORKER_SOURCE)
        self.assertNotIn(WARNING, result["stderr"])

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

    # closes: #492
    def test_cli_warns_for_an_unhonoured_worker(self):
        output, code = self.run_source(WORKER_SOURCE)
        self.assertIn(WARNING, output)
        self.assertIn("hardened-sandbox", output)
        self.assertEqual(code, 0, "5.x still runs the step; 6.0.0 refuses it")

    def test_cli_is_silent_without_a_worker(self):
        output, code = self.run_source(PLAIN_SOURCE)
        self.assertNotIn(WARNING, output)
        self.assertEqual(code, 0)


if __name__ == "__main__":
    unittest.main()
