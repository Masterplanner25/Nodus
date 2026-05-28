"""Test runner for Nodus std:test framework."""

from __future__ import annotations

import os
import time as _time
from dataclasses import dataclass, field
from typing import Any

from nodus.runtime.diagnostics import LangRuntimeError
from nodus.vm.vm import Closure, Record, BuiltinMethod, VM


@dataclass
class TestResult:
    suite_path: list[str]    # e.g. ["user validation", "email checks"]
    case_name: str
    status: str              # "pass" | "fail" | "skip" | "error"
    duration_ms: float = 0.0
    failure_message: str = ""
    failure_kind: str = ""
    failure_payload: object = None
    skip_reason: str = ""
    source_path: str = ""


@dataclass
class SuiteResult:
    suite_path: list[str]
    total: int = 0
    passed: int = 0
    failed: int = 0
    skipped: int = 0
    errors: int = 0
    duration_ms: float = 0.0
    results: list[TestResult] = field(default_factory=list)


class TestRunner:
    """Executes a registered test tree and collects results."""

    def __init__(self, root_vm: VM, *, source_path: str = ""):
        self._rvm = root_vm
        self._source_path = source_path
        self._results: list[TestResult] = []

    def run_all(self) -> list[TestResult]:
        """Run all registered suites and return results."""
        state = self._rvm.test_state
        for suite in state.get("top_level_suites", []):
            self._run_suite(suite, parent_path=[], parent_hooks={
                "before_each": [], "after_each": [],
            })
        return self._results

    def _run_suite(self, suite: dict, parent_path: list[str], parent_hooks: dict) -> None:
        path = parent_path + [suite["name"]]
        hooks = suite["hooks"]

        # Accumulate before_each / after_each from parents
        effective_before_each = parent_hooks["before_each"] + hooks["before_each"]
        effective_after_each = hooks["after_each"] + parent_hooks["after_each"]

        child_hooks = {
            "before_each": effective_before_each,
            "after_each": effective_after_each,
        }

        # Run before_all for this suite
        before_all_err = None
        for fn in hooks["before_all"]:
            err = self._run_hook(fn, path, "before_all")
            if err and not before_all_err:
                before_all_err = err

        # Suite-scope fixture cache
        suite_fixture_cache: dict[str, Any] = {}
        suite_fixture_cleanups: list = []

        # Run cases
        for case in suite["cases"]:
            self._run_case(
                case, path, suite, child_hooks,
                suite_fixture_cache, suite_fixture_cleanups,
                before_all_err=before_all_err,
            )

        # Run nested suites
        for nested in suite["suites"]:
            self._run_suite(nested, path, child_hooks)

        # Run suite-scope fixture cleanups
        for fn in reversed(suite_fixture_cleanups):
            self._invoke_fn(fn, [])

        # Run after_all
        for fn in hooks["after_all"]:
            self._run_hook(fn, path, "after_all")

    def _run_case(
        self, case: dict, suite_path: list[str], suite: dict,
        hooks: dict, suite_fixture_cache: dict, suite_fixture_cleanups: list,
        before_all_err=None,
    ) -> None:
        result = TestResult(
            suite_path=suite_path,
            case_name=case["name"],
            status="pass",
            source_path=self._source_path,
        )

        if case.get("skip"):
            result.status = "skip"
            result.skip_reason = case.get("skip_reason") or ""
            self._results.append(result)
            return

        if before_all_err:
            result.status = "error"
            result.failure_message = f"before_all failed: {before_all_err}"
            result.failure_kind = "hook_error"
            self._results.append(result)
            return

        # Snapshot state for isolation
        isolated = suite.get("options", {}).get("isolated", True)
        snapshot = _take_snapshot(self._rvm) if isolated else None

        test_fixture_cache: dict[str, Any] = {}
        test_fixture_cleanups: list = []

        # Build ctx object for fixtures
        ctx = self._make_ctx(
            suite, suite_fixture_cache, suite_fixture_cleanups,
            test_fixture_cache, test_fixture_cleanups,
        )

        t0 = _time.monotonic()
        try:
            # before_each hooks
            for fn in hooks["before_each"]:
                self._invoke_fn(fn, [])

            # Run the test case fn
            fn = case["fn"]
            params = fn.function.params if isinstance(fn, Closure) else []
            args = [ctx] if params else []

            if case.get("async_"):
                self._run_async_case(fn, args)
            else:
                self._rvm.run_closure(fn, args)

        except LangRuntimeError as exc:
            if exc.kind == "test_error":
                payload = exc.payload or {}
                if isinstance(payload, dict) and payload.get("category") == "skip":
                    result.status = "skip"
                    result.skip_reason = payload.get("reason") or str(exc)
                else:
                    result.status = "fail"
                    result.failure_message = str(exc)
                    result.failure_kind = "assertion_failure"
                    result.failure_payload = exc.payload
            else:
                result.status = "error"
                result.failure_message = str(exc)
                result.failure_kind = exc.kind
                result.failure_payload = exc.payload
        except Exception as exc:
            result.status = "error"
            result.failure_message = str(exc)
            result.failure_kind = "python_error"
        finally:
            result.duration_ms = (_time.monotonic() - t0) * 1000

            # after_each hooks (run even on failure)
            for fn in hooks["after_each"]:
                self._run_hook(fn, suite_path, "after_each")

            # Test-scope fixture cleanups (LIFO)
            for fn in reversed(test_fixture_cleanups):
                self._invoke_fn(fn, [])

            # Restore snapshot if isolated
            if isolated and snapshot is not None:
                _restore_snapshot(self._rvm, snapshot)

        self._results.append(result)

    def _run_async_case(self, fn: Closure, args: list) -> None:
        """Run an async test case using the scheduler with virtual clock."""
        from nodus.runtime.coroutine import Coroutine
        from nodus.runtime.runtime_stats import runtime_time_ms
        state = self._rvm.test_state

        # Set up virtual clock (starts at t=0)
        state["virtual_clock_ms"] = 0.0
        self._rvm.scheduler.clock_fn = lambda: state["virtual_clock_ms"]

        # Create coroutine in "created" state; set initial args if any
        coro = Coroutine(fn)
        if args:
            coro.initial_args = list(args)

        # Capture failures thrown inside the coroutine
        failure: list = [None]
        def _on_error(c, err) -> bool:
            failure[0] = err
            return False  # continue running other tasks

        self._rvm.scheduler.spawn(coro)
        self._rvm.scheduler.run_loop(on_error=_on_error)

        # Restore real clock
        self._rvm.scheduler.clock_fn = runtime_time_ms

        if failure[0] is not None:
            raise failure[0]

    def _make_ctx(
        self, suite, suite_fixture_cache, suite_fixture_cleanups,
        test_fixture_cache, test_fixture_cleanups,
    ) -> Record:
        """Build the ctx Record passed to test cases that accept it."""
        runner = self
        rvm = self._rvm
        state = rvm.test_state

        def fixture_fn(name):
            name_str = str(name)
            fixture_def = suite["fixtures"].get(name_str)
            if fixture_def is None:
                raise LangRuntimeError("test_error",
                    f"fixture '{name_str}' is not defined in this suite",
                    payload={"category": "fixture_not_found", "name": name_str})
            scope = fixture_def.get("scope", "test")
            cache = suite_fixture_cache if scope == "suite" else test_fixture_cache
            cleanups = suite_fixture_cleanups if scope == "suite" else test_fixture_cleanups

            if name_str in cache:
                return cache[name_str]

            # Run the fixture fn
            fixture_fn_closure = fixture_def["fn"]
            state["_active_cleanup_list"] = cleanups
            try:
                params = fixture_fn_closure.function.params if isinstance(fixture_fn_closure, Closure) else []
                fix_args = [runner._make_ctx(suite, suite_fixture_cache, suite_fixture_cleanups,
                                             test_fixture_cache, test_fixture_cleanups)] if params else []
                value = rvm.run_closure(fixture_fn_closure, fix_args)
            except LangRuntimeError as exc:
                raise LangRuntimeError("test_error",
                    f"fixture '{name_str}' threw: {exc}",
                    payload={"category": "fixture_error", "name": name_str, "cause": str(exc)}) from exc
            finally:
                state["_active_cleanup_list"] = None

            cache[name_str] = value
            return value

        return Record({"fixture": BuiltinMethod(fixture_fn)})

    def _invoke_fn(self, fn, args: list) -> object | None:
        """Call a Nodus closure, silently ignoring errors."""
        try:
            return self._rvm.run_closure(fn, args)
        except Exception:
            return None

    def _run_hook(self, fn, suite_path: list[str], hook_name: str):
        """Run a lifecycle hook; return error string on failure."""
        try:
            self._rvm.run_closure(fn, [])
            return None
        except LangRuntimeError as exc:
            return str(exc)
        except Exception as exc:
            return str(exc)


# -- Isolation snapshot/restore -------------------------------------------

def _take_snapshot(rvm: VM) -> dict:
    """Snapshot mutable state that tests might change."""
    return {
        "env": dict(os.environ),
        "cwd": os.getcwd(),
        "tool_registry": dict(rvm.tool_registry),
        "tool_deprecated_warned": set(rvm._tool_deprecated_warned),
    }


def _restore_snapshot(rvm: VM, snapshot: dict) -> None:
    """Restore state from a snapshot."""
    # Restore environment variables
    os.environ.clear()
    os.environ.update(snapshot["env"])

    # Restore working directory
    try:
        os.chdir(snapshot["cwd"])
    except OSError:
        pass

    # Restore tool registry
    with rvm._tool_registry_lock:
        rvm.tool_registry.clear()
        rvm.tool_registry.update(snapshot["tool_registry"])
    rvm._tool_deprecated_warned.clear()
    rvm._tool_deprecated_warned.update(snapshot["tool_deprecated_warned"])
