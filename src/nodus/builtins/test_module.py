"""std:test — test framework builtins for Nodus VM (v4.0 Design Docs 07+08)."""

import difflib
import math

from nodus.runtime.diagnostics import LangRuntimeError
from nodus.vm.vm import Closure, Record


# -- Sentinel for zero-duration yield used by test.flush_async() ----------

class _FlushAsyncRequest:
    """Returned by test.flush_async() to yield to the scheduler."""


FLUSH_ASYNC_SENTINEL = _FlushAsyncRequest()


# -- Root-VM traversal (same pattern as tool_module) ----------------------

def _root_vm(vm):
    """Follow _caller_vm chain to the root VM (where test_state lives).

    Same pattern as tool_module._root_vm — see that function for the full
    explanation of why this traversal is required for stdlib builtins.
    """
    root = vm
    while True:
        parent = getattr(root, "_caller_vm", None)
        if parent is None:
            return root
        root = parent


# -- Test state helpers ----------------------------------------------------

def _init_state(rvm) -> dict:
    """Lazily initialise and return the root VM's test_state."""
    if not rvm.test_state:
        rvm.test_state = {
            "_suite_counter": 0,
            "_case_counter": 0,
            "_suite_stack": [],      # suites being registered (stack)
            "top_level_suites": [],  # completed registrations
            # Execution helpers (set by the runner before invoking fixtures)
            "_active_cleanup_list": None,
            # Virtual clock (test.advance_clock / test.flush_async)
            "virtual_clock_ms": 0.0,
        }
    return rvm.test_state


def _current_suite(state: dict):
    return state["_suite_stack"][-1] if state["_suite_stack"] else None


# -- Value display ---------------------------------------------------------

def _nodus_repr(value, depth: int = 0) -> str:
    """Convert a Nodus runtime value to a human-readable string."""
    indent = "  " * depth
    inner = "  " * (depth + 1)
    if value is None:
        return "nil"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, float):
        return str(int(value)) if value == int(value) else str(value)
    if isinstance(value, int):
        return str(value)
    if isinstance(value, str):
        return repr(value)
    if isinstance(value, list):
        if not value:
            return "[]"
        items = ",\n".join(inner + _nodus_repr(v, depth + 1) for v in value)
        return f"[\n{items}\n{indent}]"
    if isinstance(value, Record):
        if not value.fields:
            return "{}"
        pairs = ",\n".join(
            f"{inner}{k}: {_nodus_repr(v, depth + 1)}"
            for k, v in value.fields.items()
        )
        return f"{{\n{pairs}\n{indent}}}"
    if isinstance(value, dict):
        if not value:
            return "{}"
        pairs = ",\n".join(
            f"{inner}{k}: {_nodus_repr(v, depth + 1)}"
            for k, v in value.items()
        )
        return f"{{\n{pairs}\n{indent}}}"
    return repr(value)


def _format_diff(actual, expected) -> str:
    """Return a compact line-diff between the repr of actual and expected."""
    a_lines = _nodus_repr(actual).splitlines(keepends=True)
    e_lines = _nodus_repr(expected).splitlines(keepends=True)
    diff = list(difflib.unified_diff(
        a_lines, e_lines,
        fromfile="actual", tofile="expected",
        lineterm="",
    ))
    if not diff:
        return ""
    # Truncate long diffs
    if len(diff) > 50:
        diff = diff[:50]
        diff.append("... (diff truncated)")
    return "\n  " + "\n  ".join(line.rstrip() for line in diff)


def _is_err_record(value) -> bool:
    return isinstance(value, Record) and value.kind == "error"


def _is_truthy(value) -> bool:
    if value is None or value is False:
        return False
    if isinstance(value, (int, float)) and value == 0:
        return False
    if isinstance(value, str) and value == "":
        return False
    if isinstance(value, list) and len(value) == 0:
        return False
    if isinstance(value, (dict, Record)) and len(getattr(value, "fields", value) if isinstance(value, Record) else value) == 0:
        return False
    return True


# -- Assertion failure helper ----------------------------------------------

def _fail(rvm, assertion: str, detail: str, msg=None, payload_extra: dict | None = None):
    """Raise a test assertion failure."""
    full_msg = f"{assertion} failed: {detail}"
    if msg:
        full_msg += f" | {msg}"
    payload = {"category": "assertion_failure", "assertion": assertion, "detail": detail}
    if payload_extra:
        payload.update(payload_extra)
    raise LangRuntimeError("test_error", full_msg, payload=payload)


# -- Main register function ------------------------------------------------

def register(vm, registry) -> None:
    """Register all test_* builtins onto the registry."""

    # -----------------------------------------------------------------
    # Assertions
    # -----------------------------------------------------------------

    def builtin_test_assert(condition, msg=None):
        rvm = _root_vm(vm)
        if not _is_truthy(condition):
            _fail(rvm, "assert", f"condition was falsy: {_nodus_repr(condition)}", msg)
        return condition

    def builtin_test_assert_eq(actual, expected, msg=None):
        rvm = _root_vm(vm)
        if actual != expected:
            diff = _format_diff(actual, expected)
            detail = (
                f"\n  actual:   {_nodus_repr(actual)}"
                f"\n  expected: {_nodus_repr(expected)}"
                + (f"\n  diff:{diff}" if diff else "")
            )
            _fail(rvm, "assert_eq", detail, msg,
                  payload_extra={"actual": str(actual), "expected": str(expected)})
        return actual

    def builtin_test_assert_neq(actual, expected, msg=None):
        rvm = _root_vm(vm)
        if actual == expected:
            _fail(rvm, "assert_neq",
                  f"both values equal: {_nodus_repr(actual)}", msg)
        return actual

    def builtin_test_assert_err(value, msg=None):
        rvm = _root_vm(vm)
        if not _is_err_record(value):
            _fail(rvm, "assert_err",
                  f"expected an error record, got: {_nodus_repr(value)}", msg)
        return value

    def builtin_test_assert_ok(value, msg=None):
        rvm = _root_vm(vm)
        if _is_err_record(value):
            err_msg = value.fields.get("message", "")
            err_kind = value.fields.get("kind", "")
            _fail(rvm, "assert_ok",
                  f"expected non-error value, got err(kind={err_kind!r}): {err_msg!r}", msg)
        return value

    def builtin_test_assert_kind(err, kind_str, msg=None):
        rvm = _root_vm(vm)
        if not _is_err_record(err):
            _fail(rvm, "assert_kind",
                  f"expected an error record, got: {_nodus_repr(err)}", msg)
        actual_kind = err.fields.get("kind", "")
        if actual_kind != kind_str:
            _fail(rvm, "assert_kind",
                  f"expected kind={kind_str!r}, got kind={actual_kind!r}", msg)
        return err

    def builtin_test_assert_throws(fn, msg=None):
        rvm = _root_vm(vm)
        if not isinstance(fn, Closure):
            _fail(rvm, "assert_throws", "argument must be a function", msg)
        thrown = None
        try:
            rvm.run_closure(fn, [])
        except LangRuntimeError as exc:
            thrown = exc
        if thrown is None:
            _fail(rvm, "assert_throws",
                  "expected function to throw, but it returned normally", msg)
        return rvm.make_err(thrown.kind, str(thrown), payload=thrown.payload)

    def builtin_test_assert_close(actual, expected, epsilon, msg=None):
        rvm = _root_vm(vm)
        if not isinstance(actual, (int, float)) or not isinstance(expected, (int, float)):
            _fail(rvm, "assert_close",
                  f"assert_close requires numeric values, got {type(actual).__name__} and {type(expected).__name__}", msg)
        if math.isnan(actual) or math.isnan(expected):
            _fail(rvm, "assert_close",
                  "NaN values are never close to any value", msg)
        diff = abs(actual - expected)
        if diff >= epsilon:
            _fail(rvm, "assert_close",
                  f"|{actual} - {expected}| = {diff} >= epsilon {epsilon}", msg,
                  payload_extra={"actual": actual, "expected": expected, "epsilon": epsilon})

    def builtin_test_assert_contains(collection, item, msg=None):
        rvm = _root_vm(vm)
        if isinstance(collection, list):
            if item not in collection:
                _fail(rvm, "assert_contains",
                      f"{_nodus_repr(item)} not found in list", msg)
        elif isinstance(collection, str):
            if not isinstance(item, str) or item not in collection:
                _fail(rvm, "assert_contains",
                      f"{_nodus_repr(item)} not found as substring in {_nodus_repr(collection)}", msg)
        elif isinstance(collection, (dict, Record)):
            fields = collection.fields if isinstance(collection, Record) else collection
            if item not in fields:
                _fail(rvm, "assert_contains",
                      f"key {_nodus_repr(item)} not found in map/record", msg)
        else:
            _fail(rvm, "assert_contains",
                  f"cannot check containment in type {type(collection).__name__}", msg)
        return collection

    def builtin_test_assert_has_key(mapping, key, msg=None):
        rvm = _root_vm(vm)
        fields = mapping.fields if isinstance(mapping, Record) else (mapping if isinstance(mapping, dict) else None)
        if fields is None:
            _fail(rvm, "assert_has_key", f"expected a map or record, got {type(mapping).__name__}", msg)
        if key not in fields:
            _fail(rvm, "assert_has_key", f"key {_nodus_repr(key)} not found in map/record", msg)
        return mapping

    def builtin_test_assert_in_range(actual, min_val, max_val, msg=None):
        rvm = _root_vm(vm)
        if not (min_val <= actual <= max_val):
            _fail(rvm, "assert_in_range",
                  f"{actual} not in range [{min_val}, {max_val}]", msg,
                  payload_extra={"actual": actual, "min": min_val, "max": max_val})

    # -----------------------------------------------------------------
    # Suite / case registration
    # -----------------------------------------------------------------

    def builtin_test_suite(name, fn, opts=None):
        rvm = _root_vm(vm)
        state = _init_state(rvm)
        suite = {
            "id": state["_suite_counter"],
            "name": str(name),
            "options": {"isolated": True},
            "cases": [],
            "suites": [],
            "fixtures": {},
            "hooks": {
                "before_all": [], "after_all": [],
                "before_each": [], "after_each": [],
            },
        }
        state["_suite_counter"] += 1
        if opts is not None:
            d = opts.fields if isinstance(opts, Record) else (opts if isinstance(opts, dict) else {})
            if "isolated" in d:
                suite["options"]["isolated"] = bool(d["isolated"])

        parent = _current_suite(state)
        state["_suite_stack"].append(suite)
        try:
            rvm.run_closure(fn, [])
        finally:
            state["_suite_stack"].pop()

        if parent is not None:
            parent["suites"].append(suite)
        else:
            state["top_level_suites"].append(suite)

    def builtin_test_case(name, fn):
        rvm = _root_vm(vm)
        state = _init_state(rvm)
        suite = _current_suite(state)
        if suite is None:
            raise LangRuntimeError("test_error",
                "test.case() called outside a test.suite() block",
                payload={"category": "invalid_usage"})
        suite["cases"].append({
            "id": state["_case_counter"],
            "name": str(name),
            "fn": fn,
            "async_": False,
            "skip": False,
            "skip_reason": None,
        })
        state["_case_counter"] += 1

    def builtin_test_case_async(name, fn):
        rvm = _root_vm(vm)
        state = _init_state(rvm)
        suite = _current_suite(state)
        if suite is None:
            raise LangRuntimeError("test_error",
                "test.case_async() called outside a test.suite() block",
                payload={"category": "invalid_usage"})
        suite["cases"].append({
            "id": state["_case_counter"],
            "name": str(name),
            "fn": fn,
            "async_": True,
            "skip": False,
            "skip_reason": None,
        })
        state["_case_counter"] += 1

    def builtin_test_skip(reason=None):
        raise LangRuntimeError("test_error",
            f"skipped: {reason}" if reason else "skipped",
            payload={"category": "skip", "reason": reason})

    # -----------------------------------------------------------------
    # Lifecycle hooks
    # -----------------------------------------------------------------

    def _register_hook(hook_name, fn):
        rvm = _root_vm(vm)
        state = _init_state(rvm)
        suite = _current_suite(state)
        if suite is None:
            raise LangRuntimeError("test_error",
                f"test.{hook_name}() called outside a test.suite() block",
                payload={"category": "invalid_usage"})
        suite["hooks"][hook_name].append(fn)

    def builtin_test_before_all(fn): _register_hook("before_all", fn)
    def builtin_test_after_all(fn): _register_hook("after_all", fn)
    def builtin_test_before_each(fn): _register_hook("before_each", fn)
    def builtin_test_after_each(fn): _register_hook("after_each", fn)

    # -----------------------------------------------------------------
    # Fixtures
    # -----------------------------------------------------------------

    def builtin_test_fixture(name, fn, scope=None):
        rvm = _root_vm(vm)
        state = _init_state(rvm)
        suite = _current_suite(state)
        if suite is None:
            raise LangRuntimeError("test_error",
                "test.fixture() called outside a test.suite() block",
                payload={"category": "invalid_usage"})
        scope_str = "test"
        if scope is not None:
            scope_str = str(scope) if not isinstance(scope, str) else scope
        suite["fixtures"][str(name)] = {"fn": fn, "scope": scope_str}

    def builtin_test_cleanup(fn):
        rvm = _root_vm(vm)
        state = _init_state(rvm)
        cleanup_list = state.get("_active_cleanup_list")
        if cleanup_list is None:
            return  # no-op outside fixture context
        cleanup_list.append(fn)

    # -----------------------------------------------------------------
    # Parameterized tests
    # -----------------------------------------------------------------

    def builtin_test_parameterize(rows, fn):
        rvm = _root_vm(vm)
        if not isinstance(rows, list) or not rows:
            return
        first = rows[0]
        is_list_form = isinstance(first, list)
        is_map_form = isinstance(first, (dict, Record))
        if not (is_list_form or is_map_form):
            raise LangRuntimeError("test_error",
                "test.parameterize: rows must be lists of lists or lists of maps",
                payload={"category": "invalid_parameterize"})
        for i, row in enumerate(rows):
            if is_list_form and not isinstance(row, list):
                raise LangRuntimeError("test_error",
                    "test.parameterize: mixed row types (all lists or all maps)",
                    payload={"category": "invalid_parameterize"})
            if is_map_form and not isinstance(row, (dict, Record)):
                raise LangRuntimeError("test_error",
                    "test.parameterize: mixed row types (all lists or all maps)",
                    payload={"category": "invalid_parameterize"})
        if is_list_form:
            for row in rows:
                rvm.run_closure(fn, row)
        else:
            for row in rows:
                rvm.run_closure(fn, [row])

    # -----------------------------------------------------------------
    # Async control
    # -----------------------------------------------------------------

    def builtin_test_advance_clock(duration):
        rvm = _root_vm(vm)
        state = _init_state(rvm)
        ms = _duration_to_ms(duration)
        state["virtual_clock_ms"] = state.get("virtual_clock_ms", 0.0) + ms
        new_time = state["virtual_clock_ms"]
        rvm.scheduler.clock_fn = lambda: new_time
        # Drain timers immediately so newly-woken tasks enter ready_queue
        rvm.scheduler._drain_timers()

    def builtin_test_flush_async():
        """Synchronously run one step of all currently-ready tasks (not current)."""
        rvm = _root_vm(vm)
        sched = rvm.scheduler
        current_task = sched.current_task

        from nodus.runtime.scheduler import SLEEP_KEY
        # Copy ready queue; skip current task; run each one step
        tasks_to_run = []
        skipped = []
        while sched.ready_queue:
            coro = sched.ready_queue.popleft()
            if coro is current_task or coro.state == "finished":
                skipped.append(coro)
            else:
                tasks_to_run.append(coro)
        # Put skipped tasks back
        for c in skipped:
            sched.ready_queue.appendleft(c)

        for coro in tasks_to_run:
            try:
                result = rvm.builtin_coroutine_resume(coro)
                if coro.state == "suspended":
                    if isinstance(result, dict):
                        if SLEEP_KEY in result:
                            sched._schedule_sleep(coro, float(result[SLEEP_KEY]))
                            continue
                    # Re-add to ready queue for next flush
                    sched.ready_queue.append(coro)
            except Exception:
                coro.state = "finished"

        # Drain timers again after running tasks (they may have slept)
        sched._drain_timers()

    # -----------------------------------------------------------------
    # Registration
    # -----------------------------------------------------------------

    registry.add("test_assert", (1, 2), builtin_test_assert)
    registry.add("test_assert_eq", (2, 3), builtin_test_assert_eq)
    registry.add("test_assert_neq", (2, 3), builtin_test_assert_neq)
    registry.add("test_assert_err", (1, 2), builtin_test_assert_err)
    registry.add("test_assert_ok", (1, 2), builtin_test_assert_ok)
    registry.add("test_assert_kind", (2, 3), builtin_test_assert_kind)
    registry.add("test_assert_throws", (1, 2), builtin_test_assert_throws)
    registry.add("test_assert_close", (3, 4), builtin_test_assert_close)
    registry.add("test_assert_contains", (2, 3), builtin_test_assert_contains)
    registry.add("test_assert_has_key", (2, 3), builtin_test_assert_has_key)
    registry.add("test_assert_in_range", (3, 4), builtin_test_assert_in_range)

    registry.add("test_suite", (2, 3), builtin_test_suite)
    registry.add("test_case", 2, builtin_test_case)
    registry.add("test_case_async", 2, builtin_test_case_async)
    registry.add("test_skip", (0, 1), builtin_test_skip)

    registry.add("test_before_all", 1, builtin_test_before_all)
    registry.add("test_after_all", 1, builtin_test_after_all)
    registry.add("test_before_each", 1, builtin_test_before_each)
    registry.add("test_after_each", 1, builtin_test_after_each)

    registry.add("test_fixture", (2, 3), builtin_test_fixture)
    registry.add("test_cleanup", 1, builtin_test_cleanup)

    registry.add("test_parameterize", 2, builtin_test_parameterize)

    registry.add("test_advance_clock", 1, builtin_test_advance_clock)
    registry.add("test_flush_async", 0, builtin_test_flush_async)


# -- Duration conversion helper -------------------------------------------

def _duration_to_ms(value) -> float:
    """Convert a Nodus duration value or plain number to milliseconds."""
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, Record):
        # std:time duration record has total_ms field
        total = value.fields.get("total_ms")
        if total is not None:
            return float(total)
    return 0.0
