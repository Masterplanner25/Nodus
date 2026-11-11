"""#912: cancelling a durable coroutine from outside its program.

`nodus workflow cancel` (`runner.cancel_run`) already marked any run `cancelled`
-- terminal, and not rehydratable -- and cleared its claim. For a durable run
nobody holds, that was enough: `durable_spawn` and the sweep both leave a
terminal run alone. What was missing was the **live** holder:

- it noticed only when a claim renewal failed, took the lost-claim path, said
  "another process holds it", and stopped **without running its `finally`
  blocks**;
- its writes were read-then-save, so a cancel landing between the two was
  overwritten and the run came back `running`.

Now every durable write goes through `update_claimed_run`, which checks the
claim and the status and writes in one transaction. A holder that finds its run
cancelled unwinds through `cancel(task)`'s own path: `finally` runs, `catch`
does not.
"""

import os
import subprocess
import sys
import tempfile
import textwrap
import time
import unittest
from contextlib import contextmanager
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))  # noqa: E402

from nodus.runtime.durable import run_id_for  # noqa: E402
from nodus.runtime.embedding import NodusRuntime  # noqa: E402
from nodus_lang_workflow.models import (  # noqa: E402
    RUN_STATUS_CANCELLED,
    RUN_STATUS_RUNNING,
)
from nodus_lang_workflow.runner import (  # noqa: E402
    WorkflowFrameworkRunner,
    configure_default_workflow_runner,
    reset_default_workflow_runner,
)
from nodus_lang_workflow.store import LocalWorkflowStore, SQLiteWorkflowStore  # noqa: E402


@contextmanager
def _runner(claim_ttl_ms: float = 30_000.0):
    with tempfile.TemporaryDirectory() as tmp:
        store = SQLiteWorkflowStore(str(Path(tmp) / "runs.db"), claim_ttl_ms=claim_ttl_ms)
        runner = WorkflowFrameworkRunner(store)
        configure_default_workflow_runner(runner=runner)
        try:
            yield runner
        finally:
            reset_default_workflow_runner()


class TheStoreWritesOnlyUnderTheClaimTests(unittest.TestCase):
    """The primitive. Checked on both built-in stores."""

    def _stores(self, tmp):
        return {"sqlite": SQLiteWorkflowStore(str(Path(tmp) / "r.db")),
                "local": LocalWorkflowStore(str(Path(tmp) / "local"))}

    def _held(self, store):
        record = store.create_run(run_id="r", graph_id="r", workflow_name="w",
                                  execution_kind="coroutine")
        record.status = RUN_STATUS_RUNNING
        store.save_run(record)
        return store.claim_run("r", owner="holder")

    def test_a_holder_can_write_and_no_one_else_can(self):
        with tempfile.TemporaryDirectory() as tmp:
            for name, store in self._stores(tmp).items():
                with self.subTest(name):
                    claim = self._held(store)
                    mark = lambda rec: rec.metadata.update(touched=True)  # noqa: E731
                    self.assertIsNotNone(store.update_claimed_run("r", claim.token, mark))
                    self.assertIsNone(store.update_claimed_run("r", "someone-else", mark))

    def test_after_a_cancel_neither_a_write_nor_a_renewal_succeeds(self):
        with tempfile.TemporaryDirectory() as tmp:
            for name, store in self._stores(tmp).items():
                with self.subTest(name):
                    claim = self._held(store)
                    WorkflowFrameworkRunner(store).cancel_run("r")
                    self.assertIsNone(store.update_claimed_run(
                        "r", claim.token, lambda rec: setattr(rec, "status", RUN_STATUS_RUNNING)))
                    self.assertIsNone(store.renew_claim("r", claim.token))
                    self.assertEqual(RUN_STATUS_CANCELLED, store.get_run("r").status)

    def test_a_renewal_cannot_revive_a_cancelled_run(self):
        """The race #912 named, made explicit: the claim comes back (as a
        renewal racing the cancel could have written it), but the run is
        terminal, so the holder is still told it is not its run any more."""
        with tempfile.TemporaryDirectory() as tmp:
            for name, store in self._stores(tmp).items():
                with self.subTest(name):
                    claim = self._held(store)
                    WorkflowFrameworkRunner(store).cancel_run("r")
                    record = store.get_run("r")
                    record.claim = claim
                    store.save_run(record)
                    self.assertIsNone(store.renew_claim("r", claim.token))
                    self.assertIsNone(store.update_claimed_run("r", claim.token, lambda rec: None))


_WORKER = """
fn worker(items) {
    let done = 0i
    try {
        for item in items {
            print("item \\(item)")
            maybe_cancel(item)
            done += 1i
            checkpoint "item-done"
        }
    } catch e {
        print("caught \\(e)")
    } finally {
        print("cleanup after \\(done)")
    }
    print("after the loop")
    return done
}
durable_spawn("job", worker, [["a", "b", "c"]])
run_loop()
"""


class ALiveHolderIsCancelledTests(unittest.TestCase):

    def test_a_cancel_mid_run_stops_it_at_the_next_checkpoint_running_finally(self):
        with _runner() as runner:
            def maybe_cancel(item):
                if item == "b":
                    runner.cancel_run(run_id_for("job"))

            rt = NodusRuntime(timeout_ms=None, max_steps=None)
            rt.register_function("maybe_cancel", maybe_cancel)
            result = rt.run_source(_WORKER)
            record = runner.get_run(run_id_for("job"))
        # "b" was in progress when the cancel landed; its checkpoint is where
        # the coroutine noticed. `finally` ran with the count as it stood; the
        # `catch` did not swallow the cancellation; nothing after ran.
        self.assertEqual("item a\nitem b\ncleanup after 2\n", result["stdout"])
        self.assertIn("was cancelled", result["stderr"])
        self.assertNotIn("lost its claim", result["stderr"])
        self.assertEqual(RUN_STATUS_CANCELLED, record.status)
        self.assertEqual(RUN_STATUS_RUNNING, record.metadata["cancelled_from"])
        self.assertNotIn("result", record.metadata, "a cancelled run recorded a result")

    def test_a_holder_between_checkpoints_notices_at_its_next_claim_renewal(self):
        """No checkpoint after the cancel: the holder finds out when it renews,
        which it does every third of the claim's lifetime as it is resumed."""
        with _runner(claim_ttl_ms=300.0) as runner:
            rt = NodusRuntime(timeout_ms=None, max_steps=None)
            rt.register_function("cancel_it", lambda: runner.cancel_run(run_id_for("slow")))
            result = rt.run_source(textwrap.dedent("""
                fn slow() {
                    let n = 0i
                    try {
                        checkpoint "started"
                        while (n < 100i) {
                            if (n == 2i) { cancel_it() }
                            n += 1i
                            sleep(50i)
                        }
                    } finally {
                        print("cleanup at \\(n)")
                    }
                    return n
                }
                durable_spawn("slow", slow, [])
                run_loop()
                """))
            record = runner.get_run(run_id_for("slow"))
        self.assertEqual(RUN_STATUS_CANCELLED, record.status)
        lines = result["stdout"].splitlines()
        self.assertEqual(1, len(lines), result)
        stopped_at = int(lines[0].split()[-1])
        # Renewal every 100 ms, one iteration every ~50 ms: a handful of
        # iterations after the cancel at 3, never the full hundred.
        self.assertLess(stopped_at, 50, lines)

    def test_a_checkpoint_in_the_finally_does_not_suspend_the_unwind(self):
        with _runner() as runner:
            rt = NodusRuntime(timeout_ms=None, max_steps=None)
            rt.register_function("cancel_it", lambda: runner.cancel_run(run_id_for("fin")))
            result = rt.run_source(textwrap.dedent("""
                fn work() {
                    try {
                        cancel_it()
                        checkpoint "noticed-here"
                    } finally {
                        checkpoint "in-finally"
                        print("finally finished")
                    }
                    return 1i
                }
                durable_spawn("fin", work, [])
                run_loop()
                """))
        self.assertEqual("finally finished\n", result["stdout"])


_SIDE = textwrap.dedent("""
    import os, sys
    sys.path.insert(0, {src!r})
    from nodus.runtime.embedding import NodusRuntime
    def note(line):
        with open(os.environ["DURABLE_LOG"], "a", encoding="utf-8") as fh:
            fh.write(line + "\\n")
    rt = NodusRuntime(timeout_ms=None, max_steps=None)
    rt.register_function("note", note)
    rt.register_function("crash", lambda: os._exit(3))
    result = rt.run_source({program!r})
    sys.stderr.write(result.get("stderr") or "")  # the runtime captures it
    sys.exit(0 if result.get("ok") else 5)
""")


class FromAnotherProcessTests(unittest.TestCase):
    """The operator's case: `nodus workflow cancel --key` against a store a
    different process is using."""

    def _env(self, tmp: Path) -> dict:
        return dict(os.environ, NODUS_WORKFLOW_STORE_BACKEND="sqlite",
                    NODUS_RUN_STATE_ROOT=str(tmp / "state"),
                    DURABLE_LOG=str(tmp / "log.txt"),
                    PYTHONPATH=str(REPO / "src"))

    def _cancel_cli(self, tmp: Path, key: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, str(REPO / "nodus.py"), "workflow", "cancel", "--key", key],
            env=self._env(tmp), cwd=str(tmp), capture_output=True, text=True, timeout=120)

    def _log(self, tmp: Path) -> list[str]:
        path = tmp / "log.txt"
        return path.read_text(encoding="utf-8").splitlines() if path.exists() else []

    # closes: #912
    def test_a_live_run_in_another_process_is_cancelled_by_key(self):
        program = textwrap.dedent("""
            fn worker() {
                let i = 0i
                try {
                    while (i < 200i) {
                        i += 1i
                        note("item \\(i)")
                        checkpoint "item"
                        sleep(100i)
                    }
                } finally {
                    note("cleanup at \\(i)")
                }
                return i
            }
            durable_spawn("live-job", worker, [])
            run_loop()
            """)
        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw)
            side = subprocess.Popen(
                [sys.executable, "-c", _SIDE.format(src=str(REPO / "src"), program=program)],
                env=self._env(tmp), cwd=raw, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            try:
                deadline = time.monotonic() + 60
                while not any(line.startswith("item 2") for line in self._log(tmp)):
                    self.assertIsNone(side.poll(), side.stderr.read() if side.poll() is not None else "")
                    self.assertLess(time.monotonic(), deadline, "the worker never started")
                    time.sleep(0.05)
                cancelled = self._cancel_cli(tmp, "live-job")
                _out, err = side.communicate(timeout=60)
            finally:
                if side.poll() is None:
                    side.kill()
            log = self._log(tmp)
        self.assertEqual(0, cancelled.returncode, cancelled.stderr)
        self.assertIn("stops at its next checkpoint or claim renewal", cancelled.stdout)
        self.assertEqual(0, side.returncode, err)
        self.assertIn("was cancelled", err)
        self.assertTrue(log[-1].startswith("cleanup at "), log)
        stopped_at = int(log[-1].split()[-1])
        self.assertLess(stopped_at, 200, "the cancel was not noticed")

    def test_a_crashed_run_cancelled_by_key_is_never_resumed(self):
        program = textwrap.dedent("""
            fn worker() {
                note("started")
                checkpoint "one"
                crash()
                note("resumed")
                return 1i
            }
            durable_spawn("dead-job", worker, [])
            run_loop()
            """)
        script = _SIDE.format(src=str(REPO / "src"), program=program)
        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw)
            first = subprocess.run([sys.executable, "-c", script], env=self._env(tmp),
                                   cwd=raw, capture_output=True, text=True, timeout=120)
            self.assertEqual(3, first.returncode, first.stderr)
            cancelled = self._cancel_cli(tmp, "dead-job")
            self.assertEqual(0, cancelled.returncode, cancelled.stderr)
            self.assertIn(f"Cancelled {run_id_for('dead-job')} (was running)", cancelled.stdout)
            # Even with the dead process's claim still unexpired, nothing will
            # pick it up: re-running the program is a no-op, and so is a sweep.
            again = subprocess.run([sys.executable, "-c", script], env=self._env(tmp),
                                   cwd=raw, capture_output=True, text=True, timeout=120)
            self.assertEqual(0, again.returncode, again.stderr)
            sweep = subprocess.run([sys.executable, str(REPO / "nodus.py"), "workflow", "sweep"],
                                   env=self._env(tmp), cwd=raw, capture_output=True,
                                   text=True, timeout=120)
            log = self._log(tmp)
        self.assertEqual(["started"], log)
        self.assertIn('"resumed_coroutines": []', sweep.stdout)

    def test_key_and_run_id_are_one_or_the_other(self):
        with tempfile.TemporaryDirectory() as raw:
            proc = subprocess.run(
                [sys.executable, str(REPO / "nodus.py"), "workflow", "cancel", "co_x", "--key", "k"],
                env=self._env(Path(raw)), cwd=raw, capture_output=True, text=True, timeout=120)
        self.assertEqual(1, proc.returncode)
        self.assertIn("--key <durable key>", proc.stderr)


if __name__ == "__main__":
    unittest.main()
