"""`worker_pool` and `pipeline` must actually run their workers (#339).

The other half of ASYNC-MOD-003. `parallel` and `series` were fixed in 4.1.1
(PR #340) by routing caller closures back through the caller's VM; these two were
not, because they are shaped differently: they spawn coroutines **inside** the
module and hand a channel back for the *caller* to drive. Those coroutines landed
on the detached module VM's own scheduler, which nothing ever runs, so every job
was silently dropped — no error, no output, `ok: True`.

The fix is two halves, and each is useless alone:

1. a module VM shares the caller's scheduler, so spawned work is queued where the
   caller's `run_loop()` will find it;
2. every coroutine is resumed on the VM that **spawned** it, not the scheduler's
   own VM. Builtins close over the VM that registered them, so resuming module
   coroutines on the caller's VM gives them the wrong `recv`/`send` and the wrong
   `current_coroutine` — that is what an earlier attempt at (1) alone hit.

Both modes are covered for every behavior: the two runtimes failed *differently*
before (the CLI raised, `NodusRuntime` silently returned `ok: True` with the body
never having run), so a fix verified in one proves nothing about the other.
"""

import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO_ROOT / "src"))  # noqa: E402

from nodus.runtime.embedding import NodusRuntime  # noqa: E402

_NODUS_PY = str(_REPO_ROOT / "nodus.py")
_SRC = str(_REPO_ROOT / "src")


class AsyncBoundaryTestCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmpdir = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)

    def run_cli(self, source: str) -> str:
        script = self.tmpdir / "main.nd"
        script.write_text(textwrap.dedent(source), encoding="utf-8")
        proc = subprocess.run(
            [sys.executable, _NODUS_PY, "run", "--time-limit", "30", str(script)],
            capture_output=True, text=True, timeout=60,
            env={"PYTHONPATH": _SRC, "SYSTEMROOT": "C:\\Windows", "PATH": ""},
        )
        if proc.returncode != 0:
            raise AssertionError(
                f"CLI run failed (exit {proc.returncode}).\n"
                f"stdout:\n{proc.stdout}\nstderr:\n{proc.stderr}"
            )
        self.assertEqual("", proc.stderr, f"unexpected stderr:\n{proc.stderr}")
        return proc.stdout

    def run_embedded(self, source: str) -> str:
        result = NodusRuntime(timeout_ms=None, max_steps=None).run_source(
            textwrap.dedent(source)
        )
        if not result["ok"]:
            raise AssertionError(f"embedded run failed: {result['errors']}")
        # Coroutine errors do not fail the run — they are printed and execution
        # continues — so stderr has to be checked explicitly or a dropped job
        # looks like a pass.
        self.assertEqual("", result["stderr"],
                         f"unexpected stderr:\n{result['stderr']}")
        return result["stdout"]

    def assert_lines_both_modes(self, source: str, expected: list[str]) -> None:
        for mode, out in (("CLI", self.run_cli(source)),
                          ("embedded", self.run_embedded(source))):
            actual = [ln for ln in out.splitlines() if ln.strip()]
            self.assertEqual(expected, actual, f"{mode} output mismatch")

    def assert_sorted_lines_both_modes(self, source: str, expected: list[str]) -> None:
        """For output whose order depends on scheduling."""
        for mode, out in (("CLI", self.run_cli(source)),
                          ("embedded", self.run_embedded(source))):
            actual = sorted(ln for ln in out.splitlines() if ln.strip())
            self.assertEqual(sorted(expected), actual, f"{mode} output mismatch")


# closes: #339
class WorkerPoolTests(AsyncBoundaryTestCase):
    def test_every_sent_item_reaches_a_worker(self):
        self.assert_sorted_lines_both_modes(
            """
            import "std:async" as async
            let jobs = async.worker_pool(fn(item) { print("job: \\(item)") }, 2i)
            send(jobs, "x")
            send(jobs, "y")
            close(jobs)
            run_loop()
            print("done")
            """,
            ["job: x", "job: y", "done"],
        )

    def test_more_items_than_workers_are_all_processed(self):
        self.assert_sorted_lines_both_modes(
            """
            import "std:async" as async
            let jobs = async.worker_pool(fn(item) { print("got \\(item)") }, 2i)
            let i = 0i
            while (i < 6i) {
                send(jobs, i)
                i = i + 1i
            }
            close(jobs)
            run_loop()
            print("done")
            """,
            ["done"] + [f"got {n}" for n in range(6)],
        )

    def test_a_single_worker_processes_items_in_order(self):
        self.assert_lines_both_modes(
            """
            import "std:async" as async
            let jobs = async.worker_pool(fn(item) { print("got \\(item)") }, 1i)
            send(jobs, "a")
            send(jobs, "b")
            send(jobs, "c")
            close(jobs)
            run_loop()
            print("done")
            """,
            ["got a", "got b", "got c", "done"],
        )

    def test_the_worker_closure_can_mutate_caller_state(self):
        # The worker is a caller closure called from inside the module — the
        # boundary this issue is about. A map is used because closures cannot
        # assign outer `let` bindings.
        self.assert_lines_both_modes(
            """
            import "std:async" as async
            let total = {"n": 0i}
            let jobs = async.worker_pool(fn(item) { total["n"] = total["n"] + item }, 1i)
            send(jobs, 1i)
            send(jobs, 2i)
            send(jobs, 39i)
            close(jobs)
            run_loop()
            print("total: \\(total["n"])")
            """,
            ["total: 42"],
        )

    def test_a_sleeping_worker_suspends_rather_than_blocking(self):
        # If the worker blocked the thread instead of suspending, the second
        # worker could not start until the first finished, and "b start" would
        # come after "a done".
        out = self.run_cli(
            """
            import "std:async" as async
            let jobs = async.worker_pool(fn(item) {
                print("\\(item) start")
                async.sleep(20i)
                print("\\(item) done")
            }, 2i)
            send(jobs, "a")
            send(jobs, "b")
            close(jobs)
            run_loop()
            """
        )
        lines = [ln for ln in out.splitlines() if ln.strip()]
        self.assertEqual(4, len(lines), out)
        self.assertLess(lines.index("b start"), lines.index("a done"),
                        f"workers did not interleave:\n{out}")


# closes: #339
class PipelineTests(AsyncBoundaryTestCase):
    _CONSUMER = """
        let consumer = coroutine(fn() {
            let v = recv(p.output)
            while (v != nil) {
                print("out: \\(v)")
                v = recv(p.output)
            }
            print("closed")
        })
        spawn(consumer)
    """

    def test_a_single_stage_transforms_every_item(self):
        self.assert_lines_both_modes(
            """
            import "std:async" as async
            let p = async.pipeline([fn(x) { return x + 1i }])
            """ + self._CONSUMER + """
            send(p.input, 1i)
            send(p.input, 2i)
            close(p.input)
            run_loop()
            """,
            ["out: 2", "out: 3", "closed"],
        )

    def test_stages_compose_in_order(self):
        # (x + 1) * 10, not x + (1 * 10): order matters and is observable.
        self.assert_lines_both_modes(
            """
            import "std:async" as async
            let p = async.pipeline([fn(x) { return x + 1i }, fn(x) { return x * 10i }])
            """ + self._CONSUMER + """
            send(p.input, 1i)
            send(p.input, 2i)
            close(p.input)
            run_loop()
            """,
            ["out: 20", "out: 30", "closed"],
        )

    def test_closing_the_input_closes_the_output(self):
        # The "closed" line only prints if the final stage closed its output, so
        # a consumer is not left blocked forever.
        self.assert_lines_both_modes(
            """
            import "std:async" as async
            let p = async.pipeline([fn(x) { return x }])
            """ + self._CONSUMER + """
            close(p.input)
            run_loop()
            print("done")
            """,
            ["closed", "done"],
        )


# closes: #339
class AnyModuleCanSpawnTests(AsyncBoundaryTestCase):
    """Not a `std:async` bug — any module that spawns had the same hole."""

    def _write_helper(self) -> None:
        (self.tmpdir / "helper.nd").write_text(
            textwrap.dedent(
                """
                fn start_worker(handler) {
                    let ch = channel()
                    spawn(coroutine(fn() {
                        let item = recv(ch)
                        while (item != nil) {
                            handler(item)
                            item = recv(ch)
                        }
                    }))
                    return ch
                }
                """
            ),
            encoding="utf-8",
        )

    def test_a_user_module_can_spawn_and_return_a_channel(self):
        self._write_helper()
        source = """
            import "./helper" as h
            let ch = h.start_worker(fn(item) { print("handled \\(item)") })
            send(ch, "one")
            send(ch, "two")
            close(ch)
            run_loop()
            print("done")
        """
        out = self.run_cli(source)
        self.assertEqual(["handled one", "handled two", "done"],
                         [ln for ln in out.splitlines() if ln.strip()])


# closes: #339
class ParallelAndSeriesStillWorkTests(AsyncBoundaryTestCase):
    """Must-not-regress guards for the half fixed in 4.1.1."""

    def test_parallel_runs_every_task(self):
        self.assert_sorted_lines_both_modes(
            """
            import "std:async" as async
            async.parallel([fn() { print("a") }, fn() { print("b") }])
            print("done")
            """,
            ["a", "b", "done"],
        )

    def test_series_runs_tasks_in_order(self):
        self.assert_lines_both_modes(
            """
            import "std:async" as async
            async.series([fn() { print("1") }, fn() { print("2") }, fn() { print("3") }])
            print("done")
            """,
            ["1", "2", "3", "done"],
        )


if __name__ == "__main__":
    unittest.main()
