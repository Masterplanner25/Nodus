"""Regression tests for closures crossing the `std:`/library module boundary.

Regression guard (ASYNC-MOD-003, #339):
    A module function is dispatched through ``NodusModule.invoke_function``,
    which runs it in a *detached* VM whose ``self.code`` is the module's
    bytecode. ``invoke_function`` wraps top-level ``Closure`` arguments in a
    ``_ClosureProxy`` so they dispatch back through the caller's VM — but it
    only wrapped arguments that were closures *themselves*. A closure nested
    inside a container (the list handed to ``async.parallel``, a map, a record)
    arrived unwrapped, so its ``fn.addr`` — an index into the *caller's*
    bytecode — was executed against the *module's* instructions. The result was
    ``Stack underflow`` / ``'NoneType' object is not subscriptable`` under the
    CLI, and a silent no-op under ``NodusRuntime`` (the task body never ran and
    ``ok`` was still True).

    The fix identifies a foreign closure by FunctionInfo identity against the
    module's own ``functions`` table and routes it back through the caller VM
    at three points: ``CALL_VALUE`` dispatch, ``coroutine()`` creation, and
    ``spawn()``.

Coverage is deliberately CLI-and-embedded for each behavior: the two paths
differed in the original bug (hard error vs. silent drop), so a fix verified in
only one mode proves nothing about the other.

Known still-broken (documented, not covered here): ``async.worker_pool`` and
``async.pipeline`` spawn coroutines onto the detached VM's own scheduler and
return a channel for the *caller* to drive. Nothing drives that scheduler. That
needs VM-agnostic builtins (builtins currently close over the VM that
registered them), tracked with the design gap in #157.
"""

import subprocess
import sys
import textwrap
import unittest
from pathlib import Path

from nodus.runtime.embedding import NodusRuntime

_REPO_ROOT = Path(__file__).resolve().parents[1]
_NODUS_PY = _REPO_ROOT / "nodus.py"
_SRC = _REPO_ROOT / "src"


def _run_cli(source: str, tmpdir: Path, *, time_limit_ms: int | None = None) -> str:
    """Run `source` through the CLI and return stdout. Raises on non-zero exit."""
    script = tmpdir / "main.nd"
    script.write_text(textwrap.dedent(source), encoding="utf-8")
    argv = [sys.executable, str(_NODUS_PY), "run"]
    if time_limit_ms is not None:
        argv += ["--time-limit", str(time_limit_ms)]
    argv.append(str(script))
    env = {"PYTHONPATH": str(_SRC), "SYSTEMROOT": "C:\\Windows", "PATH": ""}
    proc = subprocess.run(argv, capture_output=True, text=True, timeout=60, env=env)
    if proc.returncode != 0:
        raise AssertionError(
            f"CLI run failed (exit {proc.returncode}).\n"
            f"stdout:\n{proc.stdout}\nstderr:\n{proc.stderr}"
        )
    return proc.stdout


def _run_embedded(source: str) -> str:
    rt = NodusRuntime(timeout_ms=None, max_steps=None)
    result = rt.run_source(textwrap.dedent(source))
    if not result["ok"]:
        raise AssertionError(f"embedded run failed: {result['errors']}")
    return result["stdout"]


# closes: #339
class ClosureInContainerCrossesModuleBoundaryTests(unittest.TestCase):
    """A caller closure nested in a container must run in the caller's context."""

    def setUp(self):
        import tempfile
        self._tmp = tempfile.TemporaryDirectory()
        self.tmpdir = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)

    def _write_helper(self) -> None:
        (self.tmpdir / "helper.nd").write_text(
            textwrap.dedent(
                """
                fn call_direct(f) {
                    return f()
                }

                fn call_nested(fns) {
                    return fns[0]()
                }

                fn call_all(fns) {
                    let out = ""
                    let i = 0
                    while (i < len(fns)) {
                        out = out + fns[i]()
                        i = i + 1
                    }
                    return out
                }
                """
            ).strip()
            + "\n",
            encoding="utf-8",
        )

    def test_closure_passed_directly_still_works(self):
        """Guard the pre-existing _ClosureProxy path against regression."""
        self._write_helper()
        out = _run_cli(
            """
            import "./helper" as h
            print(h.call_direct(fn() { return "direct-ok" }))
            """,
            self.tmpdir,
        )
        self.assertIn("direct-ok", out)

    def test_closure_nested_in_list_is_callable(self):
        """The ASYNC-MOD-003 repro: previously raised Stack underflow."""
        self._write_helper()
        out = _run_cli(
            """
            import "./helper" as h
            print(h.call_nested([fn() { return "nested-ok" }]))
            """,
            self.tmpdir,
        )
        self.assertIn("nested-ok", out)
        self.assertNotIn("Stack underflow", out)

    def test_every_closure_in_a_list_is_callable(self):
        """Not just element 0 — each entry must dispatch to the caller."""
        self._write_helper()
        out = _run_cli(
            """
            import "./helper" as h
            print(h.call_all([fn() { return "a" }, fn() { return "b" }, fn() { return "c" }]))
            """,
            self.tmpdir,
        )
        self.assertIn("abc", out)


# closes: #339
class StdAsyncParallelAndSeriesTests(unittest.TestCase):
    """std:async parallel/series must actually run their tasks."""

    def setUp(self):
        import tempfile
        self._tmp = tempfile.TemporaryDirectory()
        self.tmpdir = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)

    PARALLEL_SRC = """
        import "std:async" as async
        async.parallel([fn() { print("a") }, fn() { print("b") }])
        print("done")
    """

    SERIES_SRC = """
        import "std:async" as async
        async.series([fn() { print("s1") }, fn() { print("s2") }])
        print("done")
    """

    COROUTINE_ARG_SRC = """
        import "std:async" as async
        let c1 = coroutine(fn() { print("coro-1") })
        let c2 = coroutine(fn() { print("coro-2") })
        async.parallel([c1, c2])
        print("done")
    """

    def test_parallel_runs_every_task_cli(self):
        out = _run_cli(self.PARALLEL_SRC, self.tmpdir)
        self.assertIn("a", out)
        self.assertIn("b", out)
        self.assertIn("done", out)

    def test_parallel_runs_every_task_embedded(self):
        out = _run_embedded(self.PARALLEL_SRC)
        self.assertIn("a", out)
        self.assertIn("b", out)

    def test_series_runs_tasks_in_order_cli(self):
        out = _run_cli(self.SERIES_SRC, self.tmpdir)
        self.assertLess(out.index("s1"), out.index("s2"))

    def test_series_runs_tasks_in_order_embedded(self):
        out = _run_embedded(self.SERIES_SRC)
        self.assertLess(out.index("s1"), out.index("s2"))

    def test_prebuilt_coroutines_run_cli(self):
        """Coroutines built in the caller and handed to a module function."""
        out = _run_cli(self.COROUTINE_ARG_SRC, self.tmpdir)
        self.assertIn("coro-1", out)
        self.assertIn("coro-2", out)

    def test_prebuilt_coroutines_run_embedded(self):
        out = _run_embedded(self.COROUTINE_ARG_SRC)
        self.assertIn("coro-1", out)
        self.assertIn("coro-2", out)


# closes: #339
class ParallelYieldsAcrossBoundaryTests(unittest.TestCase):
    """A task that sleeps must suspend, not block — proving real interleaving."""

    INTERLEAVE_SRC = """
        import "std:async" as async
        async.parallel([fn() { async.sleep(30); print("slow") }, fn() { print("fast") }])
        print("done")
    """

    def test_sleeping_task_yields_so_fast_task_finishes_first_embedded(self):
        out = _run_embedded(self.INTERLEAVE_SRC)
        self.assertIn("slow", out)
        self.assertIn("fast", out)
        # If the sleeping task blocked instead of yielding, "slow" would print
        # first (tasks are spawned in order).
        self.assertLess(
            out.index("fast"), out.index("slow"),
            f"expected the non-sleeping task to finish first; got:\n{out}",
        )


# closes: #339
class ModuleLocalClosuresUnaffectedTests(unittest.TestCase):
    """The foreign-closure test must not misfire on a module's own closures."""

    def setUp(self):
        import tempfile
        self._tmp = tempfile.TemporaryDirectory()
        self.tmpdir = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)

    def test_module_local_closure_and_spawn_still_run_in_module_context(self):
        (self.tmpdir / "helper2.nd").write_text(
            textwrap.dedent(
                """
                fn spawn_and_drive() {
                    spawn(coroutine(fn() { print("module-local-ran") }))
                    run_loop()
                    return "done"
                }

                fn local_closure() {
                    let f = fn() { return "local-closure-ok" }
                    return f()
                }
                """
            ).strip()
            + "\n",
            encoding="utf-8",
        )
        out = _run_cli(
            """
            import "./helper2" as h
            print(h.local_closure())
            print(h.spawn_and_drive())
            """,
            self.tmpdir,
        )
        self.assertIn("local-closure-ok", out)
        self.assertIn("module-local-ran", out)

    def test_collections_higher_order_functions_still_work(self):
        """std:collections map/filter take closures as direct args (proxy path)."""
        out = _run_embedded(
            """
            import "std:collections" as c
            print(c.map([1i, 2i, 3i], fn(x) { return x * 2i }))
            print(c.filter([1i, 2i, 3i, 4i], fn(x) { return x % 2i == 0i }))
            """
        )
        self.assertIn("[2, 4, 6]", out)
        self.assertIn("[2, 4]", out)


if __name__ == "__main__":
    unittest.main()
