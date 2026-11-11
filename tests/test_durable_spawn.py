"""#180 stage 4b: `durable_spawn` and the checkpoint that persists.

Design: `docs/design/v5/08a-durable-coroutines-stage4.md` (D1, D2, D4, D5).
`durable_spawn(key, fn, args)` runs `fn` as a coroutine backed by a run record.
Each `checkpoint "label"` is written to the record before the coroutine goes on.
Calling `durable_spawn` again with the key, after a crash, resumes the run from
its last checkpoint; after it finishes, does nothing.

The test that matters most is `AfterARealCrashTests`. It kills a real process
with `os._exit` between two checkpoints, and shows that the next process resumes
at the checkpoint: the work before it does not run again, and the work after it
does. Everything else here is the edges of that.
"""

import json
import os
import subprocess
import sys
import tempfile
import textwrap
import time
import unittest
from contextlib import contextmanager
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO_ROOT / "src"))  # noqa: E402

from nodus.runtime.continuation import decode_values  # noqa: E402
from nodus.runtime.durable import CHECKPOINT_NOT_DURABLE, run_id_for  # noqa: E402
from nodus.runtime.embedding import NodusRuntime  # noqa: E402
from nodus_lang_workflow.models import (  # noqa: E402
    RUN_STATUS_COMPLETED,
    RUN_STATUS_FAILED,
    RUN_STATUS_RUNNING,
)
from nodus_lang_workflow.runner import (  # noqa: E402
    WorkflowFrameworkRunner,
    configure_default_workflow_runner,
    reset_default_workflow_runner,
)
from nodus_lang_workflow.store import LocalWorkflowStore, SQLiteWorkflowStore  # noqa: E402


@contextmanager
def _store(kind: str = "sqlite", *, claim_ttl_ms: float = 30_000.0):
    with tempfile.TemporaryDirectory() as tmp:
        if kind == "sqlite":
            store = SQLiteWorkflowStore(str(Path(tmp) / "runs.db"), claim_ttl_ms=claim_ttl_ms)
        else:
            store = LocalWorkflowStore(tmp)
        configure_default_workflow_runner(runner=WorkflowFrameworkRunner(store))
        try:
            yield store
        finally:
            reset_default_workflow_runner()


def _run(src: str, **host):
    runtime = NodusRuntime(timeout_ms=None, max_steps=None)
    for name, fn in host.items():
        runtime.register_function(name, fn)
    return runtime.run_source(textwrap.dedent(src))


def _text(result) -> str:
    return (str(result.get("error") or "") + (result.get("stderr") or "")
            + str(result.get("spawned_errors") or ""))


_WORKER = """
fn worker(job) {
    print("start \\(job)")
    let done = []
    list_push(done, "fetched")
    checkpoint "fetched"
    print("after fetched \\(done)")
    list_push(done, "uploaded")
    checkpoint "uploaded"
    print("finished \\(done)")
    return len(done)
}
"""


class ItRunsAndRecordsTests(unittest.TestCase):

    def test_a_durable_run_completes_and_its_record_says_so(self):
        with _store() as store:
            result = _run(_WORKER + 'print(durable_spawn("k1", worker, ["j"]))\nrun_loop()\n')
            self.assertTrue(result.get("ok"), result)
            record = store.get_run(run_id_for("k1"))
        self.assertEqual(run_id_for("k1") + "\nstart j\nafter fetched [\"fetched\"]\n"
                         "finished [\"fetched\", \"uploaded\"]\n", result["stdout"])
        self.assertEqual(RUN_STATUS_COMPLETED, record.status)
        self.assertEqual("coroutine", record.execution_kind)
        self.assertEqual("uploaded", record.current_checkpoint)
        self.assertEqual(2, record.metadata["checkpoints_reached"])
        self.assertEqual([2], decode_values(record.metadata["result"]))
        self.assertNotIn("continuation", record.metadata, "a finished run keeps no continuation")
        self.assertIsNone(record.claim)

    def test_each_checkpoint_is_in_the_store_before_the_coroutine_goes_on(self):
        """D2's guarantee, observed from inside: right after a checkpoint, the
        record already holds a continuation at that label."""
        seen = []
        with _store() as store:
            def look():
                record = store.get_run(run_id_for("k2"))
                seen.append((record.current_checkpoint,
                             "continuation" in record.metadata))
            result = _run("""
                fn worker() {
                    checkpoint "one"
                    look()
                    checkpoint "two"
                    look()
                    return 1i
                }
                durable_spawn("k2", worker, [])
                run_loop()
                """, look=look)
        self.assertTrue(result.get("ok"), result)
        self.assertEqual([("one", True), ("two", True)], seen)

    def test_a_failure_is_recorded(self):
        with _store() as store:
            result = _run("""
                fn worker() {
                    checkpoint "before"
                    throw "boom"
                }
                durable_spawn("k3", worker, [])
                run_loop()
                """)
            record = store.get_run(run_id_for("k3"))
        self.assertIn("boom", _text(result))
        self.assertEqual(RUN_STATUS_FAILED, record.status)
        self.assertIn("boom", record.last_error)

    def test_a_finished_key_does_not_run_again(self):
        with _store():
            first = _run(_WORKER + 'durable_spawn("k4", worker, ["j"])\nrun_loop()\n')
            second = _run(_WORKER + 'durable_spawn("k4", worker, ["j"])\nrun_loop()\n')
        self.assertIn("start j", first["stdout"])
        self.assertEqual("", second["stdout"])
        # Finished is not "held elsewhere". Without its own check a finished run
        # falls through to `claim_run`, which refuses it, and the caller is told
        # a live process holds a run that is done.
        self.assertNotIn("held by another process", second["stderr"])

    def test_the_arguments_are_a_copy_not_the_callers_value(self):
        """The coroutine gets the arguments as stored, so a first run and a
        resumed run see the same data, and the caller's later mutation of the
        list it passed is not seen."""
        with _store():
            result = _run("""
                fn worker(xs) { sleep(0i); print("worker sees \\(xs)"); return 1i }
                let xs = [1i]
                durable_spawn("k5", worker, [xs])
                list_push(xs, 2i)
                run_loop()
                """)
        self.assertEqual("worker sees [1]\n", result["stdout"])


class ItRefusesAtTheCallTests(unittest.TestCase):
    """Each refusal is at `durable_spawn`, the line that made the mistake (D1),
    not at a checkpoint deep inside a program that already ran."""

    def _refused(self, body: str, phrase: str, kind: str = "sqlite"):
        with _store(kind):
            result = _run(body)
        self.assertFalse(result.get("ok"), result)
        self.assertIn(phrase, _text(result))

    def test_bad_arguments(self):
        cases = {
            "an empty key": ('fn w() { return 1i }\ndurable_spawn("", w, [])', "key must be a non-empty string"),
            "args not a list": ('fn w() { return 1i }\ndurable_spawn("k", w, 1i)', "args must be a list"),
            "wrong arity": ('fn w(a, b) { return 1i }\ndurable_spawn("k", w, [1i])', "takes 2 argument(s), got 1"),
            "an argument that cannot be written down": (
                'fn w(c) { return 1i }\ndurable_spawn("k", w, [channel()])', "argument `c`"),
        }
        for name, (body, phrase) in cases.items():
            with self.subTest(name):
                self._refused(body, phrase)

    def test_an_entry_that_could_not_be_found_again(self):
        cases = {
            "anonymous": ('durable_spawn("k", fn() { return 1i }, [])', "anonymous function"),
            "a closure": ('fn mk(b) { return fn() { return b } }\ndurable_spawn("k", mk(1i), [])',
                          "anonymous function"),
            "nested": ('fn outer() { fn inner() { return 1i }\n return inner }\n'
                       'durable_spawn("k", outer(), [])', "inside another function"),
        }
        for name, (body, phrase) in cases.items():
            with self.subTest(name):
                self._refused(body, phrase)

    def test_a_store_whose_claims_are_not_exclusive(self):
        self._refused('fn w() { return 1i }\ndurable_spawn("k", w, [])',
                      "NODUS_WORKFLOW_STORE_BACKEND=sqlite", kind="local")

    def test_one_key_names_one_run(self):
        with _store():
            _run('fn w(a) { return a }\ndurable_spawn("same", w, [1i])\nrun_loop()\n')
            result = _run('fn w(a) { return a }\ndurable_spawn("same", w, [2i])\nrun_loop()\n')
        self.assertIn("with different arguments", _text(result))


class TheCheckpointTests(unittest.TestCase):

    def test_outside_a_durable_coroutine_it_says_so(self):
        result = _run("""
            fn plain() { checkpoint "x"; return 1i }
            print(plain())
            """)
        self.assertIn(CHECKPOINT_NOT_DURABLE, _text(result))

    def test_inside_a_for_loop_the_refusal_is_catchable_and_names_the_workaround(self):
        with _store() as store:
            result = _run("""
                fn worker() {
                    for x in [1i, 2i] {
                        try {
                            checkpoint "in-loop"
                        } catch e {
                            print("caught: \\(e)")
                        }
                    }
                    return 1i
                }
                durable_spawn("kf", worker, [])
                run_loop()
                """)
            record = store.get_run(run_id_for("kf"))
        self.assertTrue(result.get("ok"), result)
        self.assertEqual(2, result["stdout"].count("caught:"))
        self.assertIn("`for` loop's iterator", result["stdout"])
        self.assertIn("with `while` over an index", result["stdout"])
        self.assertEqual(RUN_STATUS_COMPLETED, record.status, "the coroutine carried on")

    def test_the_refusal_says_where_the_checkpoint_is(self):
        """The refusal is built by the scheduler, not by a VM instruction, so it
        had no position: the guide's example printed `loop.nd:` and no line."""
        with _store():
            result = _run("""
                fn worker() {
                    for x in [1i] {
                        checkpoint "in-loop"
                    }
                    return 1i
                }
                durable_spawn("kl", worker, [])
                run_loop()
                """)
        (error,) = result["spawned_errors"]
        self.assertIn("cannot be made durable", error["message"])
        self.assertEqual((4, 9), (error["line"], error["column"]))

    def test_a_checkpoint_in_a_helper_the_worker_calls_is_durable(self):
        """D1 kept checkpoints legal in helpers, which is why it rejected a
        `durable fn` modifier. Stage 3 restores a suspend in a nested call."""
        with _store() as store:
            result = _run("""
                fn helper(n) { checkpoint "in-helper"; return n * 2i }
                fn worker() { let v = helper(21i); return v }
                durable_spawn("kh", worker, [])
                run_loop()
                """)
            record = store.get_run(run_id_for("kh"))
        self.assertTrue(result.get("ok"), result)
        self.assertEqual("in-helper", record.current_checkpoint)
        self.assertEqual([42], decode_values(record.metadata["result"]))


class ClaimsTests(unittest.TestCase):

    def test_a_run_held_elsewhere_is_left_alone_and_the_caller_is_told(self):
        with _store() as store:
            run_id = run_id_for("held")
            store.create_run(run_id=run_id, graph_id=run_id, workflow_name="w",
                             execution_kind="coroutine",
                             metadata={"durable_key": "held", "entry": "w",
                                       "args": {"values": [], "heap": []}})
            claim = store.claim_run(run_id, owner="someone-else")
            self.assertIsNotNone(claim)
            result = _run('fn w() { print("ran"); return 1i }\ndurable_spawn("held", w, [])\nrun_loop()\n')
        self.assertTrue(result.get("ok"), result)
        self.assertNotIn("ran", result["stdout"])
        self.assertIn("held by another process (someone-else)", result["stderr"])
        self.assertIn("expires in", result["stderr"])

    def test_a_copy_that_loses_its_claim_stops_and_does_not_write(self):
        """Another process took the run (the claim expired and was re-claimed).
        This copy must stop at its next renewal, before doing more work, and
        must not overwrite the new owner's record."""
        with _store(claim_ttl_ms=60_000.0) as store:
            run_id = run_id_for("stolen")

            def steal():
                record = store.get_run(run_id)
                store.release_claim(run_id, record.claim.token)
                store.claim_run(run_id, owner="thief")

            result = _run("""
                fn worker() {
                    checkpoint "one"
                    steal()
                    checkpoint "two"
                    print("should not run")
                    return 1i
                }
                durable_spawn("stolen", worker, [])
                run_loop()
                """, steal=steal)
            record = store.get_run(run_id)
        self.assertNotIn("should not run", result["stdout"])
        self.assertIn("lost its claim", result["stderr"])
        self.assertEqual("thief", record.claim.owner)
        self.assertEqual(RUN_STATUS_RUNNING, record.status)
        self.assertEqual("one", record.current_checkpoint)


_SIDE = textwrap.dedent("""
    import os, sys
    sys.path.insert(0, {src!r})
    from nodus.runtime.embedding import NodusRuntime
    from nodus_lang_workflow.runner import WorkflowFrameworkRunner, configure_default_workflow_runner
    from nodus_lang_workflow.store import SQLiteWorkflowStore
    configure_default_workflow_runner(runner=WorkflowFrameworkRunner(
        SQLiteWorkflowStore(os.environ["DURABLE_DB"], claim_ttl_ms=200.0)))

    def maybe_crash(where):
        if os.environ.get("CRASH_AT") == where:
            os._exit(3)

    def note(line):
        # Straight to a file, unbuffered: what a killed process did must be
        # readable after it is gone, and its captured stdout is not.
        with open(os.environ["DURABLE_LOG"], "a", encoding="utf-8") as fh:
            fh.write(line + "\\n")

    rt = NodusRuntime(timeout_ms=None, max_steps=None)
    rt.register_function("maybe_crash", maybe_crash)
    rt.register_function("note", note)
    result = rt.run_source({program!r})
    assert result.get("ok"), result.get("error")
""")

_CRASHING_PROGRAM = """
fn worker(job) {
    note("start")
    let total = 0i
    total += 10i
    maybe_crash("before-first-checkpoint")
    checkpoint "fetched"
    note("after fetched, total=\\(total)")
    total += 5i
    maybe_crash("between-checkpoints")
    checkpoint "uploaded"
    note("finished, total=\\(total)")
    return total
}
durable_spawn("job-1", worker, ["job-1"])
run_loop()
"""


class AfterARealCrashTests(unittest.TestCase):
    """The design's testing bar for stage 4: kill a process, not a coroutine."""

    def _process(self, tmp: Path, crash_at: str | None) -> int:
        script = _SIDE.format(src=str(_REPO_ROOT / "src"), program=_CRASHING_PROGRAM)
        env = dict(os.environ, DURABLE_DB=str(tmp / "runs.db"), DURABLE_LOG=str(tmp / "log.txt"))
        env.pop("CRASH_AT", None)
        if crash_at:
            env["CRASH_AT"] = crash_at
        proc = subprocess.run([sys.executable, "-c", script], env=env, cwd=str(tmp),
                              capture_output=True, text=True, timeout=120)
        if proc.returncode not in (0, 3):
            raise AssertionError(proc.stderr[-1500:])
        return proc.returncode

    def _log(self, tmp: Path) -> list[str]:
        path = tmp / "log.txt"
        return path.read_text(encoding="utf-8").splitlines() if path.exists() else []

    def _after_claim_expiry(self):
        time.sleep(0.5)  # the dead process's 200 ms claim must lapse

    def test_a_crash_between_checkpoints_resumes_at_the_last_one(self):
        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw)
            self.assertEqual(3, self._process(tmp, "between-checkpoints"))
            self.assertEqual(["start", "after fetched, total=10"], self._log(tmp))
            self._after_claim_expiry()
            self.assertEqual(0, self._process(tmp, None))
            # Resumed at "fetched": `start` did not run again, and `total`
            # came back as 10 -- the 5 added after the checkpoint was lost
            # with the process and is added again (at-least-once).
            self.assertEqual(["start", "after fetched, total=10",
                              "after fetched, total=10", "finished, total=15"], self._log(tmp))
            self.assertEqual(0, self._process(tmp, None))
            self.assertEqual(4, len(self._log(tmp)), "a finished run ran again")
            store = SQLiteWorkflowStore(str(tmp / "runs.db"))
            record = store.get_run(run_id_for("job-1"))
            self.assertEqual(RUN_STATUS_COMPLETED, record.status)
            self.assertEqual(1, record.resume_count)
            self.assertEqual([15], decode_values(record.metadata["result"]))

    def test_a_crash_before_the_first_checkpoint_starts_again_from_the_top(self):
        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw)
            self.assertEqual(3, self._process(tmp, "before-first-checkpoint"))
            self.assertEqual(["start"], self._log(tmp))
            self._after_claim_expiry()
            self.assertEqual(0, self._process(tmp, None))
            self.assertEqual(["start", "start", "after fetched, total=10",
                              "finished, total=15"], self._log(tmp))

    def test_the_record_is_plain_json_between_processes(self):
        """What the second process reads is what the first wrote, as data."""
        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw)
            self._process(tmp, "between-checkpoints")
            store = SQLiteWorkflowStore(str(tmp / "runs.db"))
            record = store.get_run(run_id_for("job-1"))
            self.assertEqual("fetched", record.current_checkpoint)
            self.assertEqual(record.metadata["continuation"],
                             json.loads(json.dumps(record.metadata["continuation"])))


if __name__ == "__main__":
    unittest.main()
