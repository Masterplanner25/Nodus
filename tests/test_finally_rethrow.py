"""`finally` must run when the `catch` block raises, and its pending action must
belong to exactly one coroutine and one region.

Three defects in the same state machine:

- #361 — `finally` was skipped entirely when `catch` rethrew. The gate entry that
  `handle_exception` leaves for a catch-with-finally was skipped during
  propagation, so cleanup was silently dropped on the one path where it matters.
- #370 — a `return` deferred to a `finally` that then raised stayed pending in a
  VM-wide slot and was applied by whatever unrelated `FINALLY_END` ran next.
- #371 — the deferred slot was not part of the per-coroutine context, so two
  coroutines suspended inside a `finally` consumed each other's pending action.

Every test asserts on the **ordered sequence** of markers rather than membership.
The regression test that let #361 ship (`test_finally_after_catch_return.py::
test_finally_runs_when_inner_error_propagates`) printed the same string from the
`catch` and the `finally` and asserted `in stdout`, so the catch alone satisfied
it and the test could not fail. Distinct markers, checked in order, is the point.

Each case runs under the CLI and under embedded `NodusRuntime`: #361 reproduced
identically in both, and the two modes take different paths into the VM.
"""

import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

_REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(_REPO_ROOT / "src"))  # noqa: E402

from nodus.runtime.embedding import NodusRuntime  # noqa: E402

_NODUS_PY = str(_REPO_ROOT / "nodus.py")


def run_cli(source: str) -> tuple[str, str, int]:
    source = textwrap.dedent(source)
    with tempfile.NamedTemporaryFile(mode="w", suffix=".nd", delete=False,
                                     encoding="utf-8") as f:
        f.write(source)
        path = f.name
    try:
        proc = subprocess.run(
            [sys.executable, _NODUS_PY, "run", path],
            capture_output=True, text=True, timeout=30,
        )
        return proc.stdout, proc.stderr, proc.returncode
    finally:
        Path(path).unlink()


def run_embedded(source: str) -> tuple[str, bool, object]:
    result = NodusRuntime(timeout_ms=None, max_steps=None).run_source(
        textwrap.dedent(source)
    )
    return result["stdout"], result["ok"], result["errors"]


class FinallyRethrowTestCase(unittest.TestCase):
    def assert_lines(self, stdout: str, expected: list[str], *, context: str = "") -> None:
        """Assert the exact ordered sequence of output lines."""
        actual = [ln for ln in stdout.splitlines() if ln.strip()]
        self.assertEqual(expected, actual, f"{context}\nstdout={stdout!r}")

    def assert_both_modes(self, source: str, expected: list[str]) -> None:
        stdout, stderr, rc = run_cli(source)
        self.assertEqual(0, rc, f"CLI exit {rc}; stderr={stderr!r}")
        self.assert_lines(stdout, expected, context="CLI")

        stdout, ok, errors = run_embedded(source)
        self.assertTrue(ok, f"embedded run failed: {errors}")
        self.assert_lines(stdout, expected, context="embedded")


# closes: #361
class FinallyRunsOnRethrowTests(FinallyRethrowTestCase):
    def test_finally_runs_between_catch_and_outer_handler(self):
        self.assert_both_modes(
            """
            fn f() {
                try { throw "boom" }
                catch e { print("A caught"); throw e }
                finally { print("B finally") }
            }
            try { f() } catch e2 { print("C outer: \\(e2.message)") }
            """,
            ["A caught", "B finally", "C outer: boom"],
        )

    def test_rethrown_error_reaches_the_outer_handler_intact(self):
        self.assert_both_modes(
            """
            fn f() {
                try { throw "original" }
                catch e { throw e }
                finally { print("cleanup") }
            }
            try { f() } catch e2 { print("got: \\(e2.message)") }
            """,
            ["cleanup", "got: original"],
        )

    def test_catch_may_throw_a_different_error(self):
        self.assert_both_modes(
            """
            fn f() {
                try { throw "first" }
                catch e { throw "second" }
                finally { print("cleanup") }
            }
            try { f() } catch e2 { print("got: \\(e2.message)") }
            """,
            ["cleanup", "got: second"],
        )

    def test_finally_runs_exactly_once(self):
        self.assert_both_modes(
            """
            let count = {"n": 0i}
            fn f() {
                try { throw "a" }
                catch e { throw e }
                finally { count["n"] = count["n"] + 1i }
            }
            try { f() } catch e2 { print("count=\\(count["n"])") }
            """,
            ["count=1"],
        )

    def test_error_from_a_function_called_by_catch_still_runs_finally(self):
        self.assert_both_modes(
            """
            fn boom() { throw "from-callee" }
            fn f() {
                try { throw "a" }
                catch e { boom() }
                finally { print("cleanup") }
            }
            try { f() } catch e2 { print("got: \\(e2.message)") }
            """,
            ["cleanup", "got: from-callee"],
        )

    def test_nested_finallys_run_innermost_first(self):
        self.assert_both_modes(
            """
            fn f() {
                try {
                    try { throw "deep" } catch e { throw e } finally { print("inner finally") }
                } catch e2 { throw e2 } finally { print("outer finally") }
            }
            try { f() } catch e3 { print("got: \\(e3.message)") }
            """,
            ["inner finally", "outer finally", "got: deep"],
        )

    def test_try_nested_inside_the_finally_does_not_swallow_the_rethrow(self):
        self.assert_both_modes(
            """
            fn f() {
                try { throw "outer-err" }
                catch e { throw e }
                finally { try { throw "inner" } catch e2 { print("inner caught") } }
            }
            try { f() } catch e3 { print("got: \\(e3.message)") }
            """,
            ["inner caught", "got: outer-err"],
        )

    def test_an_error_from_the_finally_supersedes_the_rethrow(self):
        self.assert_both_modes(
            """
            fn f() {
                try { throw "a" }
                catch e { throw e }
                finally { throw "b" }
            }
            try { f() } catch e2 { print("got: \\(e2.message)") }
            """,
            ["got: b"],
        )

    def test_uncaught_rethrow_still_runs_finally_before_terminating(self):
        # Exercises the branch where the re-raise finds no handler at all:
        # FINALLY_END must propagate out rather than swallow the error.
        source = """
        fn f() {
            try { throw "boom" }
            catch e { print("catch"); throw e }
            finally { print("cleanup") }
        }
        f()
        print("never")
        """
        stdout, stderr, rc = run_cli(source)
        self.assertEqual(1, rc, f"expected a failing exit; stderr={stderr!r}")
        self.assert_lines(stdout, ["catch", "cleanup"], context="CLI")
        self.assertIn("boom", stderr)

        stdout, ok, errors = run_embedded(source)
        self.assertFalse(ok, "embedded run should report failure")
        self.assert_lines(stdout, ["catch", "cleanup"], context="embedded")

    def test_the_other_four_exit_paths_are_unaffected(self):
        self.assert_both_modes(
            """
            fn from_try() { try { return "try" } catch e { return "catch" } finally { print("f1") } }
            fn from_catch() { try { throw "x" } catch e { return "catch" } finally { print("f2") } }
            print(from_try())
            print(from_catch())
            try { print("body") } catch e { print("catch") } finally { print("f3") }
            try { throw "y" } catch e { print("caught") } finally { print("f4") }
            """,
            ["f1", "try", "f2", "catch", "body", "f3", "caught", "f4"],
        )


# closes: #370
class DeferredReturnDoesNotOutliveItsFinallyTests(FinallyRethrowTestCase):
    def test_return_stranded_by_a_raising_finally_does_not_leak(self):
        # The second try/catch/finally has no return of its own. Before the fix
        # it inherited f's stranded deferred return and died with the internal
        # error "FINALLY_END deferred return outside function".
        self.assert_both_modes(
            """
            fn f() { try { return 1i } catch e { print("f catch") } finally { throw "x" } }
            try { f() } catch e2 { print("caught: \\(e2.message)") }
            try { print("body") } catch e3 { print("e3") } finally { print("fin") }
            print("after")
            """,
            ["caught: x", "body", "fin", "after"],
        )

    def test_a_caught_error_inside_the_finally_keeps_the_deferred_return(self):
        # The guard must not be too eager: an error raised and caught *within*
        # the finally block leaves the region intact, so the return still lands.
        self.assert_both_modes(
            """
            fn f() {
                try { return "kept" }
                catch e { return "wrong" }
                finally { try { throw "inner" } catch e2 { print("inner caught") } }
            }
            print(f())
            """,
            ["inner caught", "kept"],
        )


# closes: #371
class DeferredStateIsPerCoroutineTests(FinallyRethrowTestCase):
    def test_two_coroutines_suspended_in_a_finally_keep_their_own_return(self):
        self.assert_both_modes(
            """
            fn work(tag) {
                try { return "ret-\\(tag)" }
                catch e { print("unexpected") }
                finally { sleep(10); print("\\(tag) finally") }
            }
            let a = coroutine(fn() { print(work("A")) })
            let b = coroutine(fn() { print(work("B")) })
            spawn(a)
            spawn(b)
            run_loop()
            print("done")
            """,
            ["A finally", "ret-A", "B finally", "ret-B", "done"],
        )

    def test_two_coroutines_suspended_in_a_finally_keep_their_own_rethrow(self):
        self.assert_both_modes(
            """
            fn work(tag) {
                try {
                    try { throw "err-\\(tag)" }
                    catch e { throw e }
                    finally { sleep(10); print("\\(tag) finally") }
                } catch outer { print("\\(tag) outer: \\(outer.message)") }
            }
            let a = coroutine(fn() { work("A") })
            let b = coroutine(fn() { work("B") })
            spawn(a)
            spawn(b)
            run_loop()
            print("done")
            """,
            ["A finally", "A outer: err-A", "B finally", "B outer: err-B", "done"],
        )


if __name__ == "__main__":
    unittest.main()
