"""Stack VM runtime for Nodus."""

import os
import secrets
import sys
try:
    from nodus_retry.effect import InMemoryEffectStore
except ImportError:
    import threading as _threading
    from typing import Optional as _Optional

    class InMemoryEffectStore:  # type: ignore[no-redef]
        """Minimal fallback used when nodus-retry is not installed."""

        def __init__(self) -> None:
            self._records: dict = {}
            self._lock = _threading.Lock()

        def resolve(self, action_id: str) -> tuple[bool, _Optional[dict]]:
            with self._lock:
                rec = self._records.get(action_id)
            if rec is not None and rec.get("status") == "success":
                return True, rec.get("result")
            return False, None

        def pending(self, action_id: str, input_hash: str) -> None:
            with self._lock:
                if action_id not in self._records:
                    self._records[action_id] = {"status": "pending", "input_hash": input_hash}

        def complete(self, action_id: str, status: str, result: _Optional[dict]) -> None:
            with self._lock:
                if action_id in self._records:
                    self._records[action_id].update({"status": status, "result": result})

        def __len__(self) -> int:
            with self._lock:
                return len(self._records)

import threading
import time
from typing import Any, Callable, cast

from nodus.runtime.coroutine import Coroutine, DEFERRED_NONE
from nodus.runtime.channel import Channel, ChannelRecvRequest
from nodus.orchestration.task_graph import TaskNode, TaskGraph, WorkflowRebuildError, run_task_graph, plan_graph, resume_graph, load_graph_state, step_name_metadata
from nodus.builtins.nodus_builtins import BUILTIN_CALL_PREFIX, BuiltinInfo
from nodus.support.config import MAX_STACK_DEPTH
from nodus.builtins import BuiltinRegistry
from nodus.compiler.compiler import FunctionInfo, normalize_bytecode
from nodus.runtime.diagnostics import LangRuntimeError, RuntimeLimitExceeded, HostFunctionError
from nodus.services.agent_runtime import (
    available_agents,
    call_agent,
    describe_agent,
    _effective_timeout_ms,  # #596: read the step budget before suspending
)
from nodus.services.memory_runtime import GLOBAL_MEMORY_STORE, MemoryStore, delete_value, get_value, has_value, list_keys, put_value
from nodus.runtime.runtime_stats import runtime_time_ms, scheduler_stats, task_snapshot
from nodus.runtime.runtime_events import RuntimeEventBus
from nodus.runtime.capability import ALLOW, ASK, BUILTIN_CAPABILITIES, DEFAULT_FLOOR, ApprovalChannel, CapabilityPolicy, CapabilityRequest, emit_denied, inherit_authority
from nodus.vm.runtime_values import is_json_safe, payload_keys
from nodus.runtime.scheduler import Scheduler, SleepRequest, SLEEP_KEY, CHANNEL_WAIT_KEY
from nodus.runtime.profiler import Profiler
from nodus.runtime.module import LiveBinding, ModuleFunction, NodusModule
from nodus.services.tool_runtime import available_tools, call_tool, describe_tool
from nodus.orchestration.workflow_lowering import find_goal_value, find_workflow_value, graph_topology, is_goal_pursuit_value, is_goal_value, is_workflow_value, workflow_to_graph
from nodus.orchestration.workflow_state import checkpoints_public

_DEFERRED_NONE = DEFERRED_NONE  # sentinel: no deferred return / re-raise pending
_FINALLY_GATE = -1         # handler_ip sentinel: RETURN and THROW inside a catch defer to finally

from nodus.vm.types import Cell, Closure, _ClosureProxy, Record, BuiltinMethod, Frame  # noqa: E402


def _dict_to_record(d: dict[str, Any]) -> "Record":
    """Recursively convert a plain dict to a Nodus Record for field-access."""
    converted: dict[str, object] = {}
    for k, v in d.items():
        if isinstance(v, dict):
            converted[k] = _dict_to_record(v)
        else:
            converted[k] = v
    return Record(converted)


class ListIterator:
    def __init__(self, values: list):
        self.values = values
        self.index = 0


class Iterator:
    """First-class iterator object produced by GET_ITER.

    Wraps either a builtin list (via index-based advance) or a user-defined
    ``__next__`` closure.  ITER_NEXT always calls ``.advance()`` on this object —
    no pending flags needed.

    ``advance_fn`` is a zero-argument callable that returns ``(value, exhausted: bool)``.
    It returns ``(value, False)`` when a value is available, and ``(None, True)``
    when the iterator is exhausted.
    """

    __slots__ = ("_advance_fn", "_exhausted")

    def __init__(self, advance_fn):
        self._advance_fn = advance_fn
        self._exhausted = False

    def advance(self):
        """Return ``(value, exhausted: bool)``.

        Once exhausted, always returns ``(None, True)`` without calling advance_fn again.
        """
        if self._exhausted:
            return None, True
        value, exhausted = self._advance_fn()
        if exhausted:
            self._exhausted = True
        return value, exhausted

    @property
    def exhausted(self):
        return self._exhausted


def _is_stdlib_path(path: str | None) -> bool:
    if not path:
        return False
    normalized = path.replace("\\", "/")
    return "/stdlib/" in normalized and normalized.endswith(".nd")


#: Hard cap on a goal loop that declares no iteration or deadline bound (#488).
#: `limits` alone is a legitimate budget, but it is only a bound while the host's
#: meter actually moves; a stuck counter would otherwise loop forever, which is
#: precisely what `budget` exists to prevent. Deliberately large enough that no
#: real spend-bounded goal reaches it, and reported distinctly when it fires.
IMPLICIT_GOAL_ITERATION_CAP = 10_000


class VM:
    """The Nodus bytecode virtual machine.

    **Constructing a `VM` directly opts out of most limits.** Only the call-depth
    cap is on by default (`max_frames`, `MAX_STACK_DEPTH`); `max_steps` and
    `deadline` default to `None`, meaning unbounded, and the capability flags
    (`allow_subprocess`, `allow_network`, `allow_env`) default to permissive —
    the opposite of `NodusRuntime`, which denies them (#405).

    That asymmetry is deliberate. `NodusRuntime` is the supported embedding entry
    point and is where a host's threat model is expressed; the VM is the execution
    engine underneath it, and the CLI builds one directly on purpose because a
    developer running a script they just wrote is not the threat model
    deny-by-default exists for.

    So: hosting code you did not author means using `NodusRuntime`, or installing
    limits yourself with `tooling.sandbox.configure_vm_limits(vm, ...)`. The
    call-depth cap is the one exception (#387) because its absence is
    unrecoverable rather than merely permissive — frames are heap-allocated, so
    runaway recursion grows until the OS kills the process instead of raising
    something a host could catch.
    """

    def __init__(
        self,
        code: list[tuple],
        functions: dict[str, FunctionInfo],
        code_locs: list[tuple[str | None, int | None, int | None]] | None = None,
        initial_globals: dict | None = None,
        module_globals: dict | None = None,
        host_globals: dict | None = None,
        input_fn=None,
        source_path: str | None = None,
        source_code: str | None = None,
        trace: bool = False,
        trace_no_loc: bool = False,
        trace_filter: str | None = None,
        trace_limit: int | None = None,
        debug: bool = False,
        debugger=None,
        trace_scheduler: bool = False,
        scheduler_output=print,
        event_bus: RuntimeEventBus | None = None,
        profiler: Profiler | None = None,
        allowed_paths: list[str] | None = None,
        writable_paths: list[str] | None = None,
        fs_root: str | None = None,
        allow_subprocess: bool = True,
        allow_network: bool = True,
        allow_env: bool = True,
        allowed_commands: list[str] | None = None,
        allowed_hosts: list[str] | None = None,
    ):
        version, instructions = normalize_bytecode(code)
        self.bytecode_version = version
        self.code = instructions
        self.functions = functions
        self.code_locs = code_locs or [(None, None, None)] * len(self.code)
        self.stack: list = []
        self.frames: list[Frame] = []
        self.module_globals: dict[str, object] = module_globals if module_globals is not None else dict(initial_globals or {})
        self.host_globals: dict[str, object] = host_globals if host_globals is not None else {}
        self.globals: dict[str, object] = self.module_globals
        self.ip = 0
        self.input_fn = input_fn if input_fn is not None else input
        self.source_path = source_path
        # Keep this beside `source_path`: the two are the run's rebuild handle and
        # a resume needs at least one of them. `source_code` used to be
        # assignable only after construction, so an entry point that passed
        # `source_path` looked complete while recording no source at all -- which
        # is how embedded runs became unresumable (#469). Both are parameters now
        # so a new entry point meets them together.
        self.source_code: str | None = source_code
        # #629: set on a child VM built for a resume, carrying what the
        # drift check needs about the module that drove it. None on a VM
        # running its own program.
        self._resume_origin: dict | None = None
        self.trace = trace
        self.trace_no_loc = trace_no_loc
        self.trace_filter = trace_filter
        self.trace_limit = trace_limit
        self.trace_count = 0
        self.debug = debug or debugger is not None
        self.debugger = debugger
        self.handler_stack: list[tuple[int, int, int, int]] = []
        # Pending actions owed to a finally block, with the handler-stack depth
        # each was deferred at so _discard_stale_deferrals can tell whether an
        # exception has escaped the region that owes it.
        self._deferred_return = _DEFERRED_NONE
        self._deferred_return_depth = 0
        self._deferred_error = _DEFERRED_NONE
        self._deferred_error_depth = 0
        self.current_coroutine: Coroutine | None = None
        # ASYNC-MOD-003: set by NodusModule.invoke_function on a detached module
        # VM. Declared here so the CALL_VALUE hot path is a plain attribute read
        # instead of a missing-attribute getattr on every call.
        self._caller_vm = None
        self.scheduler = Scheduler(self, trace=trace_scheduler, trace_output=scheduler_output)
        self.event_bus = event_bus or RuntimeEventBus()
        self.profiler = profiler
        self.allowed_paths = self._normalize_allowed_paths(allowed_paths)
        # #467: the writable subset. None means "whatever is readable",
        # which is every prior release's behaviour and keeps this additive.
        self.writable_paths = self._normalize_allowed_paths(writable_paths)
        self.fs_root = os.path.normcase(os.path.realpath(fs_root)) if fs_root else None
        self.allow_subprocess = allow_subprocess
        self.allow_network = allow_network
        self.allow_env = allow_env
        # Default deadline for host agent handlers, ms (#424). None = unbounded.
        # A step's `timeout_ms` still wins when tighter; this covers agent_call()
        # made outside any step, where there is no step budget to inherit.
        self.agent_timeout_ms: float | None = None
        # #499: whether a workflow run persists the module source into
        # `.nodus/graphs/` as its rebuild handle. On by default everywhere;
        # `NodusRuntime(persist_workflow_source=False)` turns it off for a
        # runtime running code its host did not author.
        self.persist_workflow_source: bool = True
        # #405. `None` means no policy — the default, and a single attribute test
        # on the dispatch path rather than a call into an allow-everything object.
        self.capability_policy: "CapabilityPolicy | None" = None
        # The floor is on by default and is not part of the "no policy set, no
        # behaviour change" contract: it refuses guest writes into `.nodus/`,
        # which a program has no legitimate reason to make and which lets it
        # forge run records. Set to None only if you mean to remove that.
        self.capability_floor = DEFAULT_FLOOR
        self.approval_channel: "ApprovalChannel | None" = None
        self.allowed_commands = allowed_commands
        self.allowed_hosts = allowed_hosts
        self.memory_store = GLOBAL_MEMORY_STORE
        # Per-VM agent registry (#185). None = fall back to the process-global
        # one, which is what the CLI and a bare VM want. `NodusRuntime` installs
        # its own so two runtimes in a process cannot see each other's agents.
        self.agent_registry: dict | None = None
        # #488: accountants for `goal … budget { limits: { … } }`, set by the
        # embedding runtime. A bare VM has none, and a goal declaring a limit on
        # one is refused rather than left unbounded.
        self.budget_meters: dict | None = None
        # The workflow runner this VM belongs to (#390). None = fall back to the
        # process-global one, which is what the CLI and a bare VM want.
        self.workflow_runner = None
        self.effect_store = InMemoryEffectStore()
        self.circuit_breakers: dict = {}
        self.session_id: str | None = None
        self.execution_unit_id: str = secrets.token_hex(8)
        self.trace_id: str | None = None
        self.task_step_budget: int | None = None
        self._budget_exceeded: bool = False
        self.instructions_executed = 0
        self.function_calls = 0
        self.returns = 0
        self.exceptions = 0
        self._instruction_batch_size = 100
        self._last_batch_emit = 0
        self._deadline_check_interval = 100
        self._last_deadline_check = 0
        # Call-depth cap, on by default (#387). See the class docstring.
        #
        # Deliberately the *only* limit defaulted here. `max_steps` and `deadline`
        # stay `None` because they are host policy: `EXECUTION_TIMEOUT_MS` is
        # 200 ms, which would break any in-process consumer running something
        # non-trivial, and `MAX_STEPS` is a budget the host should choose.
        #
        # The call-depth cap is different in kind. VM frames are heap-allocated, so
        # Python's own recursion limit never fires — measured: depth 5,000 completes
        # on a bare VM against a `sys.getrecursionlimit()` of 1,000. Unbounded
        # recursion therefore does not raise; it grows until the OS kills the
        # process. That is the one limit whose absence costs the host the process
        # rather than the request, and so the one that cannot sensibly default off.
        self.max_frames: int | None = MAX_STACK_DEPTH
        self.max_steps: int | None = None
        self.deadline: float | None = None
        self.trace_errors: bool = False
        self.trace_scheduler = trace_scheduler
        self.scheduler_output = scheduler_output
        self._task_counter = 0
        self.last_graph_plan: dict | None = None
        self.tool_registry: dict = {}
        self._tool_deprecated_warned: set = set()
        self._tool_registry_lock = threading.RLock()
        self._spawned_handles: list = []  # (proc, stdout_thread, stderr_thread) per subprocess_spawn
        self.test_state: dict = {}
        self.on_error: Callable | None = None
        self.coroutine_timeout_ms: int | None = None
        self._bare_import_hints: dict[str, str] = {}
        # #664: names this program declared `extern`. Diagnostics only -- nothing
        # dispatches on it. The CLI cannot register host functions, so a declared
        # extern reaches a call site undefined, and the pre-#489 message
        # ("Undefined function: notify") told a user who had just written
        # `extern notify(...)` nothing about why. Populated by the module loader,
        # which is the only place that has seen the AST; a union across loaded
        # modules, because the answer only shapes a sentence.
        self.declared_externs: set[str] = set()
        self.builtins: dict[str, BuiltinInfo] = {
            "clock": BuiltinInfo("clock", 0, lambda: time.time()),
            "type": BuiltinInfo("type", 1, self.builtin_type),
            "runtime_typeof": BuiltinInfo("runtime_typeof", 1, self.builtin_runtime_typeof),
            "runtime_fn_name": BuiltinInfo("runtime_fn_name", 1, self.builtin_runtime_fn_name),
            "runtime_fn_arity": BuiltinInfo("runtime_fn_arity", 1, self.builtin_runtime_fn_arity),
            "runtime_fn_module": BuiltinInfo("runtime_fn_module", 1, self.builtin_runtime_fn_module),
            "runtime_fields": BuiltinInfo("runtime_fields", 1, self.builtin_runtime_fields),
            "runtime_has": BuiltinInfo("runtime_has", 2, self.builtin_runtime_has),
            "runtime_module_fields": BuiltinInfo("runtime_module_fields", 1, self.builtin_runtime_module_fields),
            "runtime_stack_depth": BuiltinInfo("runtime_stack_depth", 0, self.builtin_runtime_stack_depth),
            "runtime_stack_frame": BuiltinInfo("runtime_stack_frame", 1, self.builtin_runtime_stack_frame),
            "runtime_tasks": BuiltinInfo("runtime_tasks", 0, self.builtin_runtime_tasks),
            "runtime_task": BuiltinInfo("runtime_task", 1, self.builtin_runtime_task),
            "runtime_scheduler_stats": BuiltinInfo("runtime_scheduler_stats", 0, self.builtin_runtime_scheduler_stats),
            "runtime_time": BuiltinInfo("runtime_time", 0, self.builtin_runtime_time),
            "runtime_events": BuiltinInfo("runtime_events", 0, self.builtin_runtime_events),
            "runtime_clear_events": BuiltinInfo("runtime_clear_events", 0, self.builtin_runtime_clear_events),
            "runtime_event_count": BuiltinInfo("runtime_event_count", 0, self.builtin_runtime_event_count),
            "task": BuiltinInfo("task", 2, self.builtin_task),
            "graph": BuiltinInfo("graph", 1, self.builtin_graph),
            "run_graph": BuiltinInfo("run_graph", 1, self.builtin_run_graph),
            "plan_graph": BuiltinInfo("plan_graph", 1, self.builtin_plan_graph),
            "resume_graph": BuiltinInfo("resume_graph", 1, self.builtin_resume_graph),
            "run_workflow": BuiltinInfo("run_workflow", (1, 2), self.builtin_run_workflow),
            "plan_workflow": BuiltinInfo("plan_workflow", 1, self.builtin_plan_workflow),
            "resume_workflow": BuiltinInfo("resume_workflow", (1, 2, 3), self.builtin_resume_workflow),
            "run_goal": BuiltinInfo("run_goal", (1, 2), self.builtin_run_goal),
            "plan_goal": BuiltinInfo("plan_goal", 1, self.builtin_plan_goal),
            "resume_goal": BuiltinInfo("resume_goal", (1, 2), self.builtin_resume_goal),
            "workflow_state": BuiltinInfo("workflow_state", 0, self.builtin_workflow_state),
            "workflow_arg": BuiltinInfo("workflow_arg", 1, self.builtin_workflow_arg),
            "state_contribute": BuiltinInfo("state_contribute", 2, self.builtin_state_contribute),
            "workflow_resume_payload": BuiltinInfo("workflow_resume_payload", 0, self.builtin_workflow_resume_payload),
            "workflow_wait": BuiltinInfo("workflow_wait", (1, 2, 3, 4), self.builtin_workflow_wait),
            "workflow_checkpoints": BuiltinInfo("workflow_checkpoints", 1, self.builtin_workflow_checkpoints),
            "current_workflow_id": BuiltinInfo("current_workflow_id", 0, self.builtin_current_workflow_id),
            "emit": BuiltinInfo("emit", (1, 2), self.builtin_emit),
            "tool_call": BuiltinInfo("tool_call", 2, self.builtin_tool_call),
            "tool_available": BuiltinInfo("tool_available", 0, self.builtin_tool_available),
            "tool_describe": BuiltinInfo("tool_describe", 1, self.builtin_tool_describe),
            "syscall": BuiltinInfo("syscall", 2, self.builtin_syscall),
            "syscall_list": BuiltinInfo("syscall_list", 0, self.builtin_syscall_list),
            "agent_call": BuiltinInfo("agent_call", 2, self.builtin_agent_call),
            "agent_call_async": BuiltinInfo("agent_call_async", 2, self.builtin_agent_call_async),
            "agent_available": BuiltinInfo("agent_available", 0, self.builtin_agent_available),
            "agent_describe": BuiltinInfo("agent_describe", 1, self.builtin_agent_describe),
            "__action_tool": BuiltinInfo("__action_tool", 2, self.builtin_action_tool),
            "__action_agent": BuiltinInfo("__action_agent", 2, self.builtin_action_agent),
            "__action_memory_put": BuiltinInfo("__action_memory_put", 2, self.builtin_action_memory_put),
            "__action_memory_get": BuiltinInfo("__action_memory_get", 1, self.builtin_action_memory_get),
            "__action_emit": BuiltinInfo("__action_emit", 2, self.builtin_action_emit),
            "__workflow_checkpoint": BuiltinInfo("__workflow_checkpoint", 1, self.builtin_workflow_checkpoint),
        }
        # Merge any builtins registered by extracted category modules.
        _registry = BuiltinRegistry()
        _registry.register_all(self)
        self.builtins.update(_registry.entries)
        self._dispatch = self._build_dispatch_table()

    def pop(self):
        if not self.stack:
            self.runtime_error("runtime", "Stack underflow")
        return self.stack.pop()

    def current_loc(self) -> tuple[str | None, int | None, int | None]:
        if self.ip < 0 or self.ip >= len(self.code_locs):
            return (self.source_path, None, None)
        return self.code_locs[self.ip]

    def format_loc(self, loc: tuple[str | None, int | None, int | None]) -> str:
        path, line, col = loc
        if path and line is not None and col is not None:
            return f"{path}:{line}:{col}"
        if path:
            return path
        if line is not None and col is not None:
            return f"{line}:{col}"
        return "<unknown>"

    def runtime_error(self, kind: str, message: str, payload: object = None, origin: str = "vm"):
        err = self.build_runtime_error(kind, message, payload=payload, origin=origin)
        self.emit_runtime_error(err)
        raise err

    def build_runtime_error(self, kind: str, message: str, payload: object = None, origin: str = "vm") -> LangRuntimeError:
        path, line, col = self.current_loc()
        if _is_stdlib_path(path):
            promoted = False
            for frame in reversed(self.frames):
                if frame.call_line is not None and frame.call_col is not None:
                    call_path = frame.call_path or self.source_path or "<repl>"
                    if not _is_stdlib_path(call_path):
                        path, line, col = call_path, frame.call_line, frame.call_col
                        promoted = True
                        break
            if not promoted:
                caller_vm = getattr(self, "_caller_vm", None)
                if caller_vm is not None:
                    caller_path, caller_line, caller_col = caller_vm.current_loc()
                    if caller_line is not None and not _is_stdlib_path(caller_path):
                        path, line, col = caller_path or "<repl>", caller_line, caller_col
        stack = self._build_error_stack(path, line, col)
        return LangRuntimeError(kind, message, line=line, col=col, path=path or self.source_path, stack=stack, payload=payload, origin=origin)

    def _build_error_stack(self, path, line, col) -> list:
        current_fn = self.frames[-1].fn_name if self.frames else "<main>"
        stack = [f"at {self.display_name(current_fn)} ({self.format_loc((path, line, col))})"]
        for i in range(len(self.frames) - 1, -1, -1):
            frame = self.frames[i]
            caller = self.frames[i - 1].fn_name if i - 1 >= 0 else "<main>"
            if frame.call_line is not None and frame.call_col is not None:
                call_path = frame.call_path or self.source_path or "<repl>"
                stack.append(
                    f"called from {self.display_name(caller)} ({self.format_loc((call_path, frame.call_line, frame.call_col))})"
                )
        return stack

    def _augment_stdlib_err(self, result: "Record") -> "Record":
        """Add path/line/column/stack/origin to a stdlib-returned err record."""
        path, line, col = self.current_loc()
        if _is_stdlib_path(path):
            for frame in reversed(self.frames):
                if frame.call_line is not None and frame.call_col is not None:
                    candidate = frame.call_path or self.source_path or "<repl>"
                    if not _is_stdlib_path(candidate):
                        path, line, col = candidate, frame.call_line, frame.call_col
                        break
        path = path or self.source_path or "<repl>"
        stack = self._build_error_stack(path, line, col)
        new_fields = dict(result.fields)
        new_fields["path"] = path
        new_fields["line"] = line
        new_fields["column"] = col
        new_fields["stack"] = stack
        new_fields["origin"] = "stdlib"
        if "payload" not in new_fields:
            new_fields["payload"] = None
        return Record(new_fields, kind="error")

    def make_err(self, kind: str, message: str, payload=None) -> "Record":
        """Return an err record value (does not throw)."""
        return Record({"kind": kind, "message": message, "payload": payload}, kind="error")

    def _make_vm_err(self, kind: str, message: str, payload=None) -> "Record":
        """Return an err record with VM location fields (origin='vm')."""
        path, line, col = self.current_loc()
        path = path or self.source_path or "<repl>"
        stack = self._build_error_stack(path, line, col)
        return Record({
            "kind": kind, "message": message, "payload": payload,
            "path": path, "line": line, "column": col,
            "stack": stack, "origin": "vm",
        }, kind="error")

    def emit_runtime_error(self, err: LangRuntimeError) -> None:
        if getattr(err, "_event_emitted", False):
            return
        coroutine_id = None
        name = None
        if self.current_coroutine is not None:
            coroutine_id = self.current_coroutine.id
            name = self.current_coroutine.name
        data = {
            "kind": err.kind,
            "message": str(err),
            "path": err.path,
            "line": err.line,
            "column": err.col,
        }
        self.event_bus.emit_event("runtime_error", coroutine_id=coroutine_id, name=name, data=data)
        setattr(err, "_event_emitted", True)

    def _unwind_to(self, frame_depth: int, stack_depth: int) -> None:
        """Drop frames, handlers and stack values below a handler's recorded depths."""
        while len(self.frames) > frame_depth:
            frame = self.frames.pop()
            if frame.cross_module_ctx is not None:
                self._restore_module_ctx(frame.cross_module_ctx)  # ASYNC-MOD-001: restore on unwind
            self._profiler_exit_frame(frame)
        while self.handler_stack and self.handler_stack[-1][3] > len(self.frames):
            self.handler_stack.pop()
        if len(self.stack) > stack_depth:
            self.stack = self.stack[:stack_depth]

    def _discard_stale_deferrals(self) -> None:
        """Drop deferred state owned by a finally block we just unwound out of.

        A deferred return and a deferred re-raise each belong to exactly one
        finally region, and are acted on when that region reaches its
        `FINALLY_END`. If the exception now being delivered escaped that region —
        the handler receiving it sits outside the region's enclosing handlers —
        the region never reaches its `FINALLY_END` and the pending action is
        superseded by this exception. Left set, it is acted on by whatever
        unrelated `FINALLY_END` runs next: before this guard,
        `fn f() { try { return 1 } catch e {} finally { throw "x" } }` left the
        return pending, and the next `finally` in the program died with the
        internal error "FINALLY_END deferred return outside function" (#370).
        """
        depth = len(self.handler_stack)
        if self._deferred_error is not _DEFERRED_NONE and depth < self._deferred_error_depth:
            self._deferred_error = _DEFERRED_NONE
        if self._deferred_return is not _DEFERRED_NONE and depth < self._deferred_return_depth:
            self._deferred_return = _DEFERRED_NONE

    def handle_exception(self, err: LangRuntimeError) -> bool:
        # #502: while unwinding a cancellation, `finally` runs and `catch` does not.
        # A timeout that a `catch` could swallow would not be a timeout -- the step
        # would carry on past the deadline that was supposed to bound it. So every
        # handler is treated the way a finally-gate already is: jump into the
        # finally if there is one, re-raise at FINALLY_END, and never hand the
        # error to guest code as a catchable value.
        cancelling = getattr(self, "_cancelling", False)
        while self.handler_stack:
            handler_ip, _finally_ip, stack_depth, frame_depth = self.handler_stack.pop()
            if cancelling and handler_ip != _FINALLY_GATE:
                if _finally_ip == 0:
                    continue  # nothing to run for this scope; keep unwinding
                self._unwind_to(frame_depth, stack_depth)
                self._deferred_error = err
                self._deferred_error_depth = len(self.handler_stack)
                self.ip = _finally_ip
                return True
            if handler_ip == _FINALLY_GATE:
                # Finally-gate entries are left by a catch block that has a finally.
                # RETURN inside the catch consumes them (see _op_return); reaching
                # one here means the catch block itself raised. The finally must
                # still run before the exception continues outward (#361), so jump
                # into it and re-raise at FINALLY_END rather than skipping past.
                self._unwind_to(frame_depth, stack_depth)
                self._deferred_error = err
                self._deferred_error_depth = len(self.handler_stack)
                self.ip = _finally_ip
                return True
            self._unwind_to(frame_depth, stack_depth)
            self._discard_stale_deferrals()
            err_fields = {
                "kind": err.kind,
                "message": str(err),
                "path": err.path,
                "line": err.line,
                "column": err.col,
                "stack": list(err.stack) if err.stack else [],
                "origin": getattr(err, "origin", "vm"),
            }
            err_fields["payload"] = err.payload  # always present; nil when no payload
            err_record = Record(err_fields, kind="error")
            self.stack.append(err_record)
            if _finally_ip != 0:
                # Push a finally-gate so RETURN inside the catch block defers to
                # finally, and so a raise inside it still runs finally (#361).
                # Its stack_depth is the depth the finally block should start
                # from: the catch's first instruction stores the error record
                # just pushed, so that is one below the current depth.
                self.handler_stack.append(
                    (_FINALLY_GATE, _finally_ip, len(self.stack) - 1, len(self.frames))
                )
            self.ip = handler_ip
            return True
        return False

    def setup_try(self, handler_ip: int, finally_ip: int = 0):
        self.handler_stack.append((handler_ip, finally_ip, len(self.stack), len(self.frames)))

    def pop_try(self) -> int:
        if not self.handler_stack:
            self.runtime_error("runtime", "POP_TRY without handler")
        _, finally_ip, _, _ = self.handler_stack.pop()
        return finally_ip

    def current_locals(self) -> dict | None:
        if not self.frames:
            return None
        return self.frames[-1].locals

    def _normalize_allowed_paths(self, allowed_paths: list[str] | None) -> list[str] | None:
        if allowed_paths is None:
            return None
        roots: list[str] = []
        for path in allowed_paths:
            if not path:
                continue
            roots.append(os.path.normcase(os.path.realpath(path)))
        return roots

    def _path_within_root(self, path: str, root: str) -> bool:
        try:
            return os.path.commonpath([path, root]) == root
        except ValueError:
            return False

    def _ensure_path_allowed(self, path: str, op_name: str, *, write: bool) -> None:
        """The one filesystem decision point. `write` is required, deliberately.

        `op_name` used to be the only thing distinguishing a read from a write
        here, and it was used solely to phrase the error message -- so the jail
        could not express "this tree is readable context, that subtree is
        editable", which is the two-tier model every coding agent wants (#467).

        The keyword has **no default**. A default would mean a new filesystem
        builtin that forgot to say gets one of the two classifications by
        accident, silently, which is the shape this codebase keeps hitting. With
        no default it is a TypeError at the call site, and
        `tests/test_path_scope.py` additionally asserts on the source that every
        caller passes an explicit literal.
        """
        normalized = os.path.normcase(os.path.realpath(path))
        if write:
            self._ensure_path_writable(normalized, path, op_name)
        if self.allowed_paths is None:
            if self.fs_root is not None and not self._path_within_root(normalized, self.fs_root):
                self.runtime_error(
                    "sandbox",
                    f"{op_name} blocked: path {path!r} escapes the project root",
                )
            return
        if not self.allowed_paths:
            self.runtime_error("sandbox", f"{op_name} is not permitted")
        for root in self.allowed_paths:
            if self._path_within_root(normalized, root):
                return
        self.runtime_error("sandbox", f"{op_name} blocked for path: {path!r}")

    def _ensure_path_writable(self, normalized: str, path: str, op_name: str) -> None:
        """Check the write half, if a writable subset was declared.

        `writable_paths is None` means "whatever is readable" -- every release
        before 5.3.0, and what a runtime that never asks for the split still
        gets. The read check still runs afterwards either way, so a writable path
        outside `allowed_paths` grants nothing on its own.
        """
        if self.writable_paths is None:
            return
        if not self.writable_paths:
            self.runtime_error("sandbox", f"{op_name} blocked: no path is writable")
        for root in self.writable_paths:
            if self._path_within_root(normalized, root):
                return
        self.runtime_error(
            "sandbox",
            f"{op_name} blocked: path {path!r} is readable but not writable",
        )

    def load_name(self, name: str):
        """Resolve a variable name to its runtime value.

        Lookup order (first match wins):
        1. `locals_` — the current frame's local variable dict (unwraps Cell and
           LiveBinding).
        2. `module_globals` — module-level globals for the currently executing module
           (unwraps Cell and LiveBinding).
        3. `functions` — the VM's compiled function table.  Returns a zero-upvalue
           Closure so callers can treat the result uniformly as a callable value.
        4. `host_globals` — variables injected by the embedding host (unwraps Cell and
           LiveBinding).

        Raises a runtime "name" error if the name is not found in any scope.

        Why four separate scopes rather than a single unified dict?
        -----------------------------------------------------------
        - `locals_` lives in a Frame, so it is naturally per-call-stack-frame and
          automatically cleaned up when the frame is popped.
        - `module_globals` is per-module-object, allowing multiple modules to coexist
          in one VM without polluting each other's namespaces.
        - `functions` is a separate dict because function definitions are compiled
          into their own FunctionInfo records (with a fixed bytecode address) before
          execution begins.  Separating them avoids name collisions with data variables
          that happen to have the same name.
        - `host_globals` is injected by the embedding layer and must remain separate
          so the host can update its bindings without touching module state.

        LOAD_LOCAL bypasses this method entirely: the compiler emits LOAD_LOCAL only
        when the symbol is confirmed local-scope, and the VM reads `frame.locals[name]`
        directly, skipping the three-level fallback.
        """
        locals_ = self.current_locals()
        if locals_ is not None and name in locals_:
            value = locals_[name]
            if isinstance(value, Cell):
                return value.value
            if isinstance(value, LiveBinding):
                return value.get()
            return value
        if name in self.module_globals:
            value = self.module_globals[name]
            if isinstance(value, Cell):
                return value.value
            if isinstance(value, LiveBinding):
                return value.get()
            return value
        if name in self.functions:
            return Closure(self.functions[name], [])
        if name in self.host_globals:
            value = self.host_globals[name]
            if isinstance(value, Cell):
                return value.value
            if isinstance(value, LiveBinding):
                return value.get()
            return value
        if name in ("await", "async"):
            self.runtime_error(
                "name",
                f'"{name}" is not a keyword in Nodus; '
                f"async builtins (http_get_async, subprocess_run_async) return their result directly — no await needed",
            )
        if name in self._bare_import_hints:
            import_path = self._bare_import_hints[name]
            self.runtime_error(
                "name",
                f"Undefined variable: {name!r}. "
                f"Module '{import_path}' was imported without an alias — "
                f"add 'as {name}' to the import to use '{name}.method()' syntax",
            )
        self.runtime_error("name", f"Undefined variable: {name}{self.extern_hint(name)}")

    def extern_hint(self, name: str) -> str:
        """The trailing sentence for a name this program declared `extern` (#664).

        Empty for every other name, so the two undefined-name messages keep their
        existing wording. Written once and called from both sites: the whole point
        of the declaration is that the user has already said what they expect, and
        a message that ignores it is the pre-#489 message.
        """
        if name not in self.declared_externs:
            return ""
        return (
            f" -- declared `extern` in this program, but nothing has registered it. "
            f"`nodus run` does not register host functions; run it from a host that "
            f'calls register_function("{name}", ...), or remove the declaration.'
        )

    def binding_namespace(self, name: str) -> dict | None:
        """The mutable namespace that currently binds `name`, or None (#671).

        One rule, so `load_name` and `store_name` cannot answer *where does this
        name live* differently. They used to: `load_name` walked
        `locals -> module_globals -> functions -> host_globals`, `store_name`
        stopped at `locals`. So a function assigning a module-top-level `let`
        had its write captured by whatever frame happened to be on the stack,
        and the global silently kept its old value.

        Only the two **writable** namespaces are here. `functions` and
        `host_globals` are readable sources a program may not assign through, so
        they stay in `load_name` alone — the asymmetry that remains is
        deliberate, and `tests/test_name_resolution_agreement.py` pins exactly
        that boundary rather than requiring the two to be identical.
        """
        locals_ = self.current_locals()
        if locals_ is not None and name in locals_:
            return locals_
        if name in self.module_globals:
            return self.module_globals
        return None

    def store_name(self, name: str, value):
        target = self.binding_namespace(name)
        if target is None:
            # Unbound: define it where execution currently is. Inside a frame
            # that is a new local; at module level it is a new global.
            locals_ = self.current_locals()
            target = self.module_globals if locals_ is None else locals_
            target[name] = value
            return value
        existing = target[name]
        if isinstance(existing, Cell):
            existing.value = value
        elif isinstance(existing, LiveBinding):
            cast("LiveBinding", existing).set(value)
        else:
            target[name] = value
        return value

    def load_upvalue(self, index: int):
        if not self.frames:
            self.runtime_error("runtime", "LOAD_UPVALUE used without a call frame")
        closure = self.frames[-1].closure
        if closure is None or index is None or index >= len(closure.upvalues):
            self.runtime_error("runtime", "Invalid upvalue access")
        assert closure is not None
        return closure.upvalues[index].value

    def store_upvalue(self, index: int, value):
        if not self.frames:
            self.runtime_error("runtime", "STORE_UPVALUE used without a call frame")
        closure = self.frames[-1].closure
        if closure is None or index is None or index >= len(closure.upvalues):
            self.runtime_error("runtime", "Invalid upvalue access")
        assert closure is not None
        closure.upvalues[index].value = value
        return value

    def capture_local(self, frame: Frame, name: str) -> Cell:
        # Prefer locals_array when available (slot-indexed path)
        if frame.locals_array is not None and frame.locals_name_to_slot is not None:
            slot = frame.locals_name_to_slot.get(name)
            if slot is not None:
                existing = frame.locals_array[slot]
                if isinstance(existing, Cell):
                    return existing
                cell = Cell(existing if existing is not None else None)
                frame.locals_array[slot] = cell
                # Also sync to dict for any code still using the dict path
                frame.locals[name] = cell
                return cell
        # Fallback: dict-based locals (old path)
        if name in frame.locals:
            value = frame.locals[name]
            if isinstance(value, Cell):
                return value
            cell = Cell(value)
            frame.locals[name] = cell
            return cell
        cell = Cell(None)
        frame.locals[name] = cell
        return cell

    def is_truthy(self, value) -> bool:
        if value is None:
            return False
        if isinstance(value, bool):
            return value
        return bool(value)

    def builtin_type(self, value):
        if value is None:
            return "nil"
        if isinstance(value, bool):
            return "bool"
        if isinstance(value, int) and not isinstance(value, bool):
            return "int"
        if isinstance(value, float):
            return "float"
        if isinstance(value, str):
            return "string"
        if isinstance(value, list):
            return "list"
        if isinstance(value, dict):
            return "map"
        if isinstance(value, Record):
            return value.kind
        if isinstance(value, Closure):
            return "function"
        if isinstance(value, Coroutine):
            return "coroutine"
        if isinstance(value, Channel):
            return "channel"
        if isinstance(value, TaskNode):
            return "task"
        if isinstance(value, TaskGraph):
            return "graph"
        if isinstance(value, bytes):
            return "bytes"
        return "unknown"

    def builtin_runtime_typeof(self, value):
        if value is None:
            return "nil"
        if isinstance(value, bool):
            return "bool"
        if isinstance(value, int) and not isinstance(value, bool):
            return "int"
        if isinstance(value, float):
            return "int" if value.is_integer() else "float"
        if isinstance(value, str):
            return "string"
        if isinstance(value, list):
            return "list"
        if isinstance(value, NodusModule):
            return "module"
        if isinstance(value, Record):
            return value.kind
        if isinstance(value, Closure):
            return "function"
        if isinstance(value, Coroutine):
            return "coroutine"
        if isinstance(value, Channel):
            return "channel"
        if isinstance(value, TaskNode):
            return "task"
        if isinstance(value, TaskGraph):
            return "graph"
        if isinstance(value, dict):
            return "map"
        return "unknown"

    def ensure_string(self, value, name: str):
        if not isinstance(value, str):
            self.runtime_error("type", f"{name} expects a string")

    def ensure_number(self, value, name: str):
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            self.runtime_error("type", f"{name} expects a number")
        return value

    def _type_name(self, value) -> str:
        return self.builtin_type(value)

    def _binary_type_error(self, op: str, a, b) -> None:
        self.runtime_error("type", f"Cannot {op} {self._type_name(a)} and {self._type_name(b)}")

    def _compare_type_error(self, a, b) -> None:
        self.runtime_error("type", f"Cannot compare {self._type_name(a)} and {self._type_name(b)}")

    def _unary_type_error(self, op: str, value) -> None:
        self.runtime_error("type", f"Cannot {op} {self._type_name(value)}")

    def ensure_function(self, value, name: str) -> Closure:
        if not isinstance(value, Closure):
            self.runtime_error("type", f"{name} expects a function")
        return value

    def guard_step_entry(self, closure, *, authorized: bool = False) -> None:
        """Refuse to enter a workflow/goal step body the graph runner did not start (#394).

        A lowered flow is an ordinary map, its `steps` an ordinary list, and each
        step's `fn` an ordinary callable — so `build["steps"][1]["fn"](nil)` ran a
        step whose dependency never ran. Ordering was a very good *default*, not
        the invariant `I-WFLOW-04` claimed.

        The decision lives here and only here. It is deliberately **not** "is a
        workflow context active": a step body calling a sibling's `fn` would pass
        that test, and gating on `run_closure` vs `call_closure` would have been
        worse still — `run_closure` has two dozen callers (`std:retry`, `std:test`,
        tool handlers, the iterator protocol), any of which a guest can hand a step
        closure to. Authorization is therefore a positive capability the runner
        grants for one specific entry, not a property of the calling path.

        Four sites can enter a caller-supplied closure and each calls this:
        `call_closure`, `run_closure`, `_call_foreign_closure` and the coroutine's
        first resume in `builtins/coroutine.py`. `tests/test_step_entry_guard.py`
        drives off that tuple, so a fifth door fails the suite rather than
        silently reopening this.
        """
        fn = getattr(closure, "function", None)
        owner = getattr(fn, "step_owner", None)
        if owner is None or authorized:
            return
        self.runtime_error(
            "runtime",
            f"Workflow step '{owner}' cannot be called directly — a step body runs "
            f"only as part of its workflow, in dependency order. Use run_workflow() "
            f"(or run_goal()) to execute the flow.",
        )

    def ensure_coroutine(self, value, name: str) -> Coroutine:
        if not isinstance(value, Coroutine):
            self.runtime_error("type", f"{name} expects a coroutine")
        return value

    def ensure_channel(self, value, name: str) -> Channel:
        if not isinstance(value, Channel):
            self.runtime_error("type", f"{name} expects a channel")
        return value

    def ensure_task(self, value, name: str) -> TaskNode:
        if not isinstance(value, TaskNode):
            self.runtime_error("type", f"{name} expects a task")
        return value

    def ensure_graph(self, value, name: str) -> TaskGraph:
        if not isinstance(value, TaskGraph):
            self.runtime_error("type", f"{name} expects a graph")
        return value

    def ensure_record(self, value, name: str) -> Record:
        if isinstance(value, NodusModule):
            self.runtime_error("type", f"{name} expects a record")
        if not isinstance(value, Record):
            self.runtime_error("type", f"{name} expects a record")
        return value

    def ensure_module(self, value, name: str):
        if isinstance(value, NodusModule):
            return value
        record = self.ensure_record(value, name)
        if record.kind != "module":
            self.runtime_error("type", f"{name} expects a module")
        return record

    def builtin_runtime_fn_name(self, value):
        closure = self.ensure_function(value, "runtime.fn_name(fn)")
        return closure.function.display_name

    def builtin_runtime_fn_arity(self, value):
        closure = self.ensure_function(value, "runtime.fn_arity(fn)")
        return float(len(closure.function.params))

    def builtin_runtime_fn_module(self, value):
        closure = self.ensure_function(value, "runtime.fn_module(fn)")
        # When the closure is a proxy from a foreign-bytecode context, use the
        # caller VM's code_locs so the path reflects the closure's origin module.
        if isinstance(value, _ClosureProxy):
            code_locs = value.caller_vm.code_locs
            source_path = value.caller_vm.source_path
        else:
            code_locs = self.code_locs
            source_path = self.source_path
        path, _line, _col = code_locs[closure.function.addr]
        return path or source_path

    def builtin_runtime_fields(self, value):
        record = self.ensure_record(value, "runtime.fields(value)")
        return list(record.fields.keys())

    def builtin_runtime_has(self, value, name):
        self.ensure_string(name, "runtime.has(value, name)")
        module = self.ensure_module(value, "runtime.has(value, name)") if isinstance(value, NodusModule) else None
        if module is not None:
            return module.has_export(name)
        record = self.ensure_record(value, "runtime.has(value, name)")
        return name in record.fields

    def builtin_runtime_module_fields(self, value):
        module = self.ensure_module(value, "runtime.module_fields(module)")
        return list(module.export_names()) if isinstance(module, NodusModule) else list(module.fields.keys())

    def reflection_frames(self) -> list[Frame]:
        if not self.frames:
            return []
        top = self.frames[-1]
        fn = top.closure.function if top.closure is not None else self.functions.get(top.fn_name)
        if fn is None:
            return self.frames
        path, _line, _col = self.code_locs[fn.addr]
        if path is None:
            return self.frames
        normalized = path.replace("\\", "/")
        if normalized.endswith("/std/runtime.nd") or normalized.endswith("/stdlib/runtime.nd"):
            if fn.display_name in {"stack_depth", "stack_frame"}:
                return self.frames[:-1]
        return self.frames

    def builtin_runtime_stack_depth(self):
        # When running as an isolated module VM invoked from a caller, delegate
        # to the caller's reflection context if this VM has no user frames.
        caller = getattr(self, "_caller_vm", None)
        if caller is not None and not self.reflection_frames():
            return caller.builtin_runtime_stack_depth()
        return float(len(self.reflection_frames()))

    def frame_to_record(self, index: int) -> Record:
        frames = self.reflection_frames()
        frame = frames[-1 - index]
        fn = frame.closure.function if frame.closure is not None else self.functions.get(frame.fn_name)
        module_path = None
        if fn is not None and 0 <= fn.addr < len(self.code_locs):
            module_path = self.code_locs[fn.addr][0]
        if index == 0 and len(frames) == len(self.frames):
            current_path, current_line, current_col = self.current_loc()
            line = current_line
            col = current_col
            path = current_path or module_path or self.source_path
        else:
            line = frame.call_line
            col = frame.call_col
            path = frame.call_path or module_path or self.source_path
        return Record(
            {
                "name": self.display_name(frame.fn_name),
                "module": module_path or self.source_path,
                "path": path,
                "line": float(line) if line is not None else None,
                "column": float(col) if col is not None else None,
            },
            kind="record",
        )

    def builtin_runtime_stack_frame(self, value):
        index = self.to_list_index(value)
        # When running as an isolated module VM invoked from a caller, delegate
        # to the caller's reflection context if this VM has no user frames.
        caller = getattr(self, "_caller_vm", None)
        if caller is not None and not self.reflection_frames():
            return caller.builtin_runtime_stack_frame(value)
        frames = self.reflection_frames()
        if index < 0 or index >= len(frames):
            self.runtime_error("index", f"Stack frame out of range: {index}")
        return self.frame_to_record(index)

    def builtin_runtime_tasks(self):
        tasks = [task_snapshot(task) for task in sorted(self.scheduler.tasks.values(), key=lambda t: t.id or 0)]
        if self.scheduler.current_task is not None and self.scheduler.current_task.id not in self.scheduler.tasks:
            tasks.append(task_snapshot(self.scheduler.current_task))
        return tasks

    def builtin_runtime_task(self, value):
        task_id = self.to_list_index(value)
        task = self.scheduler.tasks.get(task_id)
        if task is None:
            return None
        return task_snapshot(task)

    def builtin_runtime_scheduler_stats(self):
        return scheduler_stats(self.scheduler)

    def builtin_runtime_time(self):
        return runtime_time_ms()

    def builtin_runtime_events(self):
        return [event.to_dict() for event in self.event_bus.events()]

    def builtin_runtime_clear_events(self):
        self.event_bus.clear()
        return None

    def builtin_runtime_event_count(self):
        return float(len(self.event_bus.events()))

    def export_state(self) -> dict:
        return {
            "globals": self.globals,
            "functions": self.functions,
            "code_locs": self.code_locs,
            "source_path": self.source_path,
            "memory_store": self.memory_store.snapshot() if isinstance(self.memory_store, MemoryStore) else {},
        }

    def import_state(self, state: dict) -> None:
        self.globals = dict(state.get("globals", {}))
        self.functions = state.get("functions", {})
        self.code_locs = state.get("code_locs", [(None, None, None)] * len(self.code))
        self.source_path = state.get("source_path")
        memory_state = state.get("memory_store", {})
        if not isinstance(self.memory_store, MemoryStore):
            self.memory_store = MemoryStore()
        self.memory_store.load_snapshot(memory_state)

    def save_execution_context(self):
        return (
            self.ip,
            self.stack,
            self.frames,
            self.handler_stack,
            self.current_coroutine,
            self._deferred_return,
            self._deferred_return_depth,
            self._deferred_error,
            self._deferred_error_depth,
        )

    def restore_execution_context(self, ctx) -> None:
        (
            self.ip,
            self.stack,
            self.frames,
            self.handler_stack,
            self.current_coroutine,
            self._deferred_return,
            self._deferred_return_depth,
            self._deferred_error,
            self._deferred_error_depth,
        ) = ctx

    def load_coroutine_context(self, coroutine: Coroutine) -> None:
        self.stack = coroutine.stack
        self.frames = coroutine.frames
        self.handler_stack = coroutine.handler_stack
        # #371: a coroutine suspended inside a finally block is owed a return or a
        # re-raise. Carry it with the coroutine, or the next one to reach a
        # FINALLY_END acts on an action that belongs to someone else.
        self._deferred_return = coroutine.deferred_return
        self._deferred_return_depth = coroutine.deferred_return_depth
        self._deferred_error = coroutine.deferred_error
        self._deferred_error_depth = coroutine.deferred_error_depth
        # #502: cancellation is a property of the coroutine being unwound, not of
        # the VM, so it swaps in and out with everything else -- two coroutines,
        # one cancelling and one not, must not see each other's state (#371).
        self._cancelling = coroutine.cancelling is not None
        self.current_coroutine = coroutine
        self.ip = coroutine.ip if coroutine.ip is not None else 0
        # ASYNC-MOD-001: restore the module context this coroutine runs in, so a
        # coroutine that suspended inside a cross-module call resumes correctly
        # and coroutines never inherit another's swapped context.
        if coroutine.module_ctx is not None:
            self._restore_module_ctx(coroutine.module_ctx)

    def _profiler_exit_frame(self, frame: Frame) -> None:
        profiler = self.profiler
        if profiler is None or not profiler.enabled:
            return
        profiler.exit_function(self.display_name(frame.fn_name))

    def reset_program(
        self,
        code: list[tuple] | dict,
        functions: dict[str, FunctionInfo],
        code_locs: list[tuple[str | None, int | None, int | None]] | None = None,
        source_path: str | None = None,
        module_globals: dict | None = None,
        host_globals: dict | None = None,
    ) -> None:
        version, instructions = normalize_bytecode(code)
        self.bytecode_version = version
        self.code = instructions
        self.functions = functions
        self.code_locs = code_locs or [(None, None, None)] * len(self.code)
        self.source_path = source_path
        if module_globals is not None:
            self.module_globals = module_globals
            self.globals = module_globals
        if host_globals is not None:
            self.host_globals = host_globals
        self.ip = 0
        self.stack = []
        self.frames = []
        self.handler_stack = []
        self._deferred_return = _DEFERRED_NONE
        self._deferred_return_depth = 0
        self._deferred_error = _DEFERRED_NONE
        self._deferred_error_depth = 0
        self.current_coroutine = None
        self.scheduler = Scheduler(self, trace=self.trace_scheduler, trace_output=self.scheduler_output)
        self._last_batch_emit = 0
        self._last_deadline_check = 0
        self.task_step_budget = None
        self._budget_exceeded = False

    def save_current_coroutine_state(self, next_ip: int | None) -> None:
        coroutine = self.current_coroutine
        if coroutine is None:
            return
        coroutine.ip = next_ip
        coroutine.stack = self.stack
        coroutine.frames = self.frames
        coroutine.handler_stack = self.handler_stack
        coroutine.deferred_return = self._deferred_return
        coroutine.deferred_return_depth = self._deferred_return_depth
        coroutine.deferred_error = self._deferred_error
        coroutine.deferred_error_depth = self._deferred_error_depth
        self._cancelling = False
        # ASYNC-MOD-001: remember the module context this coroutine suspended in,
        # so it is restored on resume (not whatever another coroutine left).
        coroutine.module_ctx = self._capture_module_ctx()

    def builtin_task(self, fn, deps):
        closure = self.ensure_function(fn, "task(fn, deps)")
        dependencies: list[TaskNode] = []
        timeout_ms = None
        max_retries = 0
        retry_delay_ms = 0.0
        cache = False
        cache_key = None
        worker = None
        worker_timeout_ms = None
        step_name = None
        if isinstance(deps, dict):
            # #679: the slot already existed on TaskNode and nothing could reach
            # it, so every generated step was `task_N` and the run result's
            # `steps` map came back empty.
            step_name = deps.get("name")
            if step_name is not None and not isinstance(step_name, str):
                self.runtime_error("type", "task(fn, deps) name option expects a string")
            if isinstance(step_name, str) and not step_name.strip():
                self.runtime_error("value", "task(fn, deps) name option cannot be blank")
            timeout_ms = deps.get("timeout_ms")
            max_retries = deps.get("retries", 0) or 0
            retry_delay_ms = deps.get("retry_delay_ms", 0.0) or 0.0
            cache = bool(deps.get("cache", False))
            cache_key = deps.get("cache_key")
            worker = deps.get("worker")
            if worker is not None and not isinstance(worker, str):
                self.runtime_error("type", "task(fn, deps) worker option expects a string")
            worker_timeout_ms = deps.get("worker_timeout_ms")
            if worker_timeout_ms is not None:
                worker_timeout_ms = self.ensure_number(worker_timeout_ms, "task(fn, deps) worker_timeout_ms option")
            dep_value = deps.get("deps")
            if dep_value is None:
                dependencies = []
            elif isinstance(dep_value, list):
                for item in dep_value:
                    dependencies.append(self.ensure_task(item, "task(fn, deps)"))
            else:
                dependencies.append(self.ensure_task(dep_value, "task(fn, deps)"))
        elif deps is None:
            dependencies = []
        elif isinstance(deps, list):
            for item in deps:
                dependencies.append(self.ensure_task(item, "task(fn, deps)"))
        else:
            dependencies.append(self.ensure_task(deps, "task(fn, deps)"))
        self._task_counter += 1
        task_id = f"task_{self._task_counter}"
        return TaskNode(
            task_id=task_id,
            function=closure,
            dependencies=dependencies,
            timeout_ms=timeout_ms,
            max_retries=int(max_retries),
            retry_delay_ms=float(retry_delay_ms),
            cache=cache,
            cache_key=cache_key,
            worker=worker,
            worker_timeout_ms=worker_timeout_ms,
            step_name=step_name,
        )

    def _graph_from_nodes(self, nodes: list) -> TaskGraph:
        """Build a guest-facing graph, carrying step names into its metadata (#679).

        One helper because there are two construction sites -- `graph(tasks)` and
        `run_graph([...])` -- and filling the mapping in only one of them is the
        sibling-path shape: the same program would report its step results or not
        depending on which spelling it used.
        """
        graph = TaskGraph(nodes)
        try:
            mapping = step_name_metadata(nodes)
        except ValueError as err:
            self.runtime_error("value", str(err))
        if mapping:
            graph.metadata = dict(graph.metadata or {})
            graph.metadata["task_to_step"] = mapping
        return graph

    def builtin_graph(self, tasks):
        if not isinstance(tasks, list):
            self.runtime_error("type", "graph(tasks) expects a list")
        nodes = [self.ensure_task(item, "graph(tasks)") for item in tasks]
        return self._graph_from_nodes(nodes)

    def builtin_run_graph(self, graph):
        tg = graph
        if isinstance(graph, list):
            tg = self._graph_from_nodes(
                [self.ensure_task(item, "run_graph(tasks)") for item in graph]
            )
        else:
            tg = self.ensure_graph(graph, "run_graph(graph)")
        return run_task_graph(self, tg)

    def builtin_plan_graph(self, tasks):
        if isinstance(tasks, TaskGraph):
            graph_tasks = tasks.tasks
            graph = tasks
        elif isinstance(tasks, list):
            graph_tasks = [self.ensure_task(item, "plan_graph(tasks)") for item in tasks]
            graph = TaskGraph(graph_tasks)
        else:
            self.runtime_error("type", "plan_graph(tasks) expects a list or graph")
        plan = plan_graph(graph_tasks, graph=graph)
        self.last_graph_plan = plan
        self.event_bus.emit_event("graph_plan_created", data={"nodes": float(len(plan.get("nodes", [])))})
        # #679: a named generated step should read the same here as a declared
        # one does in `plan_workflow`. Names come from the graph metadata that
        # `graph()` now fills; an unnamed graph relabels to itself.
        step_labels = graph.metadata.get("task_to_step", {}) if isinstance(graph.metadata, dict) else {}
        return self._relabel_plan(plan, step_labels if isinstance(step_labels, dict) else {})

    def builtin_resume_graph(self, graph_id):
        if not isinstance(graph_id, str):
            self.runtime_error("type", "resume_graph(graph_id) expects a string")
        return resume_graph(self, graph_id)

    def _suppressed_flow_result(self) -> dict:
        """A benign, index-safe empty result returned by run_workflow/run_goal while
        a module is being re-executed only to re-bind its definitions during
        resume-rebuild (#322). Carries the keys top-level code commonly reads so a
        `let r = run_workflow(x)` followed by `r["steps"]` etc. does not crash the
        rebuild.

        **Every key any real result can carry must appear here.** Nodus maps raise
        on a missing key, so one absent key turns a resume into a hard failure —
        and #399 was exactly that: `status`, `wait`, `retry` and `error` were
        missing, which are the keys present precisely when a run *defers*. So the
        one shape a script inspects before resuming was the one shape this could
        not survive, and the resulting `Missing map key: "status"` was swallowed
        and reported as `Unknown graph`.

        `test_resume_rebuild.py` asserts this key set covers every shape
        `run_task_graph` actually returns, so adding a result key without adding it
        here fails the suite instead of breaking resume silently.
        """
        return {
            "steps": {}, "failed": [], "tasks": {}, "timings": {}, "attempts": {},
            "cache_hits": [], "graph_id": "", "state": {}, "checkpoints": [],
            "workflow": "", "goal": "",
            # Per-task outcome report, carried on every real result.
            "statuses": {}, "task_statuses": {},
            # Deferral / failure keys — absent from a completed result, present on
            # exactly the runs a resume is issued for (#399).
            "status": "", "wait": {}, "retry": {}, "error": "",
        }

    def resolve_workflow_runner(self):
        """The workflow runner that owns this VM's runs (#390).

        Every workflow builtin used to call `get_default_workflow_runner()`
        directly, so the VM had no handle on which runner it belonged to and any
        two participants in a process — a service, an embedded runtime, a test —
        shared one store, one graph registry and one sweeper thread with no way to
        tell whose run was whose. Four separate bugs in #376 traced back to that,
        and each was fixed with a timing defence rather than by ownership.

        Resolving from the VM keeps the fallback intact: a bare VM or the CLI still
        gets the process-global runner, so nothing that worked before changes.
        """
        if self.workflow_runner is not None:
            return self.workflow_runner
        from nodus_lang_workflow.runner import get_default_workflow_runner

        return get_default_workflow_runner()

    def builtin_run_workflow(self, workflow, args=None):
        if not is_workflow_value(workflow):
            self.runtime_error("type", "run_workflow(workflow) expects a workflow")
        if getattr(self, "_suppress_flow_execution", False):
            # Resume-rebuild is re-running this module ONLY to re-bind the
            # workflow/fn definitions and imports (#322). Executing the flow here
            # would spawn a spurious fresh graph and re-run steps (duplicating side
            # effects), which is the bug this guard fixes. Skip it.
            return self._suppressed_flow_result()
        graph = workflow_to_graph(self, workflow, init_state=True, args=args)
        return self.resolve_workflow_runner().start_graph(self, graph)

    def builtin_plan_workflow(self, workflow):
        if not is_workflow_value(workflow):
            self.runtime_error("type", "plan_workflow(workflow) expects a workflow")
        graph = workflow_to_graph(self, workflow, init_state=False, require_args=False)
        step_plan = self._step_plan_from_graph(graph, label="workflow")
        self.last_graph_plan = step_plan
        self.event_bus.emit_event(
            "graph_plan_created",
            data={"nodes": float(len(step_plan.get("nodes", []))), "workflow": step_plan.get("workflow")},
        )
        return step_plan

    def _resume_target_vm(self, graph_id: str):
        """Pick the VM a resume should run on (#328).

        If the graph is still registered for THIS vm, resume reuses it in place —
        no rebuild — so return self. Otherwise a rebuild is required, and the
        rebuild `reset_program`s its execution target. If this vm is running its
        own program (a `.nd` script that called `resume_workflow` and has more
        statements to run), rebuilding on it would clobber that program and the
        caller's continuation would be lost. In that case run the resume on a
        dedicated child VM instead, inheriting host state (host functions, shared
        memory, event bus, worker dispatcher) so the resumed steps still resolve.

        A bare resume VM (e.g. the Python runner's ``VM([], {})``) has no program
        to clobber, so it keeps using self — leaving the runner/CLI/HTTP paths
        unchanged.
        """
        from nodus.orchestration.task_graph import get_registered_graph, get_registered_vm
        graph = get_registered_graph(graph_id)
        registered_vm = get_registered_vm(graph_id)
        needs_rebuild = graph is None or (registered_vm is not None and registered_vm is not self)
        if not needs_rebuild or not self.code:
            return self
        child = VM([], {}, code_locs=[], host_globals=self.host_globals,
                   source_path=self.source_path, event_bus=self.event_bus)
        # #629: the drift check runs during the rebuild, on this child — which
        # has the caller's `source_path` but neither its globals nor its source,
        # so the "what is the caller holding?" referent is unreachable from
        # there. Snapshot it here, while the caller is still intact.
        child._resume_origin = self._resume_origin_snapshot()
        # #405: a resume must not be a way out of the jail. This child was
        # inheriting host_globals, memory_store, the dispatcher and the builtins
        # — and none of the sandbox: `allowed_paths` went from a jail to None and
        # `allow_subprocess` from False to True.
        inherit_authority(child, self)
        child.memory_store = self.memory_store
        if getattr(self, "worker_dispatcher", None) is not None:
            child.worker_dispatcher = self.worker_dispatcher
        for name, info in self.builtins.items():
            child.builtins.setdefault(name, info)   # carry host builtins; core already bound to child
        return child

    def builtin_resume_workflow(self, graph_id, checkpoint=None, resume_payload=None):
        if not isinstance(graph_id, str):
            self.runtime_error("type", "resume_workflow(graph_id, checkpoint) expects graph_id as string")
        if isinstance(checkpoint, Record) and resume_payload is None:
            resume_payload = dict(checkpoint.fields)
            checkpoint = None
        elif isinstance(checkpoint, dict) and resume_payload is None:
            resume_payload = dict(checkpoint)
            checkpoint = None
        if isinstance(resume_payload, Record):
            resume_payload = dict(resume_payload.fields)
        if checkpoint is not None and not isinstance(checkpoint, str):
            self.runtime_error("type", "resume_workflow(graph_id, checkpoint, payload) expects checkpoint as string or nil")
        if resume_payload is not None and not isinstance(resume_payload, dict):
            self.runtime_error("type", "resume_workflow(graph_id, checkpoint, payload) expects payload as map or nil")
        target = self._resume_target_vm(graph_id)
        return self.resolve_workflow_runner().resume_workflow(
            target,
            graph_id,
            checkpoint,
            resume_payload=resume_payload,
            rebuild_graph=target._rebuild_workflow_graph,
        )

    # --- goal as a stopping condition (#409 Part A) -----------------------

    @staticmethod
    def _evaluate_goal_predicate(node, reached: set[str]) -> bool:
        """Walk the lowered `until` map against the checkpoints reached so far.

        The predicate is data (see `lower_goal_pursuit_ast`), so this is a small
        interpreter rather than a call into compiled code — which is what keeps a
        goal's stopping condition readable before it runs.
        """
        if not isinstance(node, dict):
            raise ValueError(f"goal predicate node is not a map: {node!r}")
        op = node.get("op")
        if op == "reached":
            return node.get("label") in reached
        if op == "not":
            return not VM._evaluate_goal_predicate(node.get("operand"), reached)
        if op == "and":
            return VM._evaluate_goal_predicate(node.get("left"), reached) and VM._evaluate_goal_predicate(node.get("right"), reached)
        if op == "or":
            return VM._evaluate_goal_predicate(node.get("left"), reached) or VM._evaluate_goal_predicate(node.get("right"), reached)
        # Not `return False`. An unrecognised operator would read as "condition not
        # yet met", so the goal would run to its budget and report exhaustion —
        # blaming the workflow for a malformed predicate. Say which it is.
        raise ValueError(f"unsupported goal predicate operator: {op!r}")

    @staticmethod
    def _checkpoint_labels(result) -> list[str]:
        entries = result.get("checkpoints") if isinstance(result, dict) else None
        if not isinstance(entries, list):
            return []
        return [e["label"] for e in entries if isinstance(e, dict) and isinstance(e.get("label"), str)]

    def _breached_budget_meter(self, declared_limits: dict):
        """First meter at or over its declared limit, or (None, None, None).

        A reader that raises is treated as a breach rather than ignored: a host
        whose accountant is broken has lost the ability to bound the loop, and
        continuing would be the silently-unbounded run this feature exists to
        prevent.
        """
        if not declared_limits:
            return None, None, None
        meters = getattr(self, "budget_meters", None) or {}
        for name, limit in declared_limits.items():
            reader = meters.get(name)
            if reader is None:
                continue
            try:
                value = reader()
            except Exception:
                return name, None, limit
            if isinstance(value, (int, float)) and isinstance(limit, (int, float)):
                if value >= limit:
                    return name, value, limit
        return None, None, None

    def builtin_run_goal_pursuit(self, pursuit):
        """Run a workflow repeatedly until the goal's predicate holds or its budget runs out.

        The loop is `run_workflow` then `resume_workflow(graph_id, label)`, which
        re-executes forward carrying the state captured at that checkpoint. No new
        execution mode is involved — that mechanism has been there all along.
        """
        if getattr(self, "_suppress_flow_execution", False):
            return self._suppressed_flow_result()   # resume-rebuild (#322/#399)

        goal_name = pursuit.get("name")
        flow_name = pursuit.get("workflow")
        workflow = find_workflow_value(self.globals, flow_name)
        if workflow is None:
            return self.make_err(
                "goal_error",
                f"goal '{goal_name}' pursues workflow '{flow_name}', which is not defined here",
                payload={"category": "unknown_workflow", "goal": goal_name, "workflow": flow_name},
            )

        budget = pursuit.get("budget") if isinstance(pursuit.get("budget"), dict) else {}
        max_iterations = int(budget.get("max_iterations") or 0)
        deadline_ms = float(budget.get("deadline_ms") or 0)
        # #488: host-registered meters. Checked once here, before the first
        # iteration, so a goal declaring a bound nobody can measure fails fast
        # rather than after the spend it was meant to cap.
        declared_limits = budget.get("limits") if isinstance(budget.get("limits"), dict) else {}
        # #488: `max_iterations` and `deadline_ms` are optional now, so a goal can
        # be bounded by meters alone. That reintroduces the hang this construct
        # exists to prevent -- a meter that never moves (a stuck host counter, a
        # miscounted unit) is an unbounded loop, and before #488 the mandatory
        # iteration cap was what made that impossible. The implicit cap restores
        # the guarantee without forcing a spend-bounded goal to invent a number.
        # Found by mutation testing: removing the meter check hung the suite.
        implicit_cap = 0
        if max_iterations <= 0 and deadline_ms <= 0:
            implicit_cap = IMPLICIT_GOAL_ITERATION_CAP
        meters = getattr(self, "budget_meters", None) or {}
        unregistered = sorted(name for name in declared_limits if name not in meters)
        if unregistered:
            return self.make_err(
                "goal_error",
                f"goal '{goal_name}' declares budget limit(s) "
                f"{', '.join(repr(n) for n in unregistered)} but no accountant is "
                f"registered for them. Register one on the runtime "
                f"(`runtime.register_meter(name, reader)`) or drop the limit. A "
                f"declared bound nobody can measure is not a bound.",
                payload={
                    "category": "unregistered_meter",
                    "goal": goal_name,
                    "workflow": flow_name,
                    "meters": unregistered,
                },
            )
        until = pursuit.get("until")
        retry_from = pursuit.get("retry_from")

        started_at = runtime_time_ms()
        runner = self.resolve_workflow_runner()
        reached: set[str] = set()
        history: list[str] = []
        iterations = 0

        # #481: `goal … over …` names the workflow it pursues; there is no slot
        # in that form to bind arguments, and `run_goal(pursuit)` takes none.
        # Refused here, where the situation can be described accurately — left to
        # the binder it reported "pass them to run_workflow(tune, {…})", which
        # names a call the author did not write and cannot reach from here.
        _declared = workflow.get("params") if isinstance(workflow, dict) else None
        if isinstance(_declared, list) and _declared:
            self.runtime_error(
                "call",
                f"goal '{goal_name}' pursues workflow '{flow_name}', which declares "
                f"parameter(s) {', '.join(repr(n) for n in _declared)}. A goal has no "
                f"way to bind them. Either drop the parameters, or run the workflow "
                f"directly with run_workflow('{flow_name}', {{…}}).",
            )
        self.event_bus.emit_event(
            "goal_start",
            data={"goal": goal_name, "workflow": flow_name,
                  "max_iterations": float(max_iterations), "deadline_ms": deadline_ms},
        )
        graph = workflow_to_graph(self, workflow, init_state=True)
        result = runner.start_graph(self, graph)
        if getattr(result, "kind", None) == "error":
            return result
        graph_id = result.get("graph_id") if isinstance(result, dict) else None

        while True:
            iterations += 1
            pass_labels = self._checkpoint_labels(result)
            reached.update(pass_labels)
            history.extend(pass_labels)

            # #642: a pass that ended `failed` cannot satisfy `until`. The loop
            # already retries a failed pass — a workflow that throws on pass 1
            # and succeeds on pass 2 reports satisfied at iteration 2 — so
            # stopping on a failed pass, only because its checkpoint happened to
            # be recorded before the throw, made termination depend on statement
            # order inside a failing step.
            #
            # This skips the *evaluation*, not the loop. "A failed pass does not
            # satisfy" is not "a failed pass ends the goal": ending it here would
            # pass the bug case and break the retry case, which is current and
            # correct behaviour.
            #
            # `failed` is empty for a tolerated failure (`allow_failure`), which
            # completes the run — so tolerance needs no special case.
            pass_failed = bool(result.get("failed")) if isinstance(result, dict) else False

            if not pass_failed and self._evaluate_goal_predicate(until, reached):
                payload = dict(result) if isinstance(result, dict) else {}
                payload.update({
                    "goal": goal_name,
                    "goal_satisfied": True,
                    "iterations": float(iterations),
                    "reached": sorted(reached),
                })
                self.event_bus.emit_event(
                    "goal_complete",
                    data={"goal": goal_name, "workflow": flow_name, "graph_id": graph_id,
                          "iterations": float(iterations)},
                )
                return payload

            elapsed = runtime_time_ms() - started_at
            # #488: the loop-altitude bound. A single iteration can make many
            # host calls, so a runaway *pass* is still unbounded -- that is the
            # host's to cap, at the altitude that owns the meter. Nodus bounds
            # the loop, which is the thing it can see.
            breached_meter, breached_value, breached_limit = self._breached_budget_meter(declared_limits)
            hit_implicit_cap = implicit_cap > 0 and iterations >= implicit_cap
            over_budget = (
                (max_iterations > 0 and iterations >= max_iterations)
                or (deadline_ms > 0 and elapsed >= deadline_ms)
                or breached_meter is not None
                or hit_implicit_cap
            )
            if over_budget:
                # A goal that ran out of budget has NOT met its objective, and must
                # never return a success-shaped result — that is the defect class
                # this cycle exists to close (#392, #376, #399).
                self.event_bus.emit_event(
                    "goal_fail",
                    data={"goal": goal_name, "workflow": flow_name, "graph_id": graph_id,
                          "iterations": float(iterations), "reason": "budget_exhausted"},
                )
                if breached_meter is not None:
                    _why = (
                        f"meter '{breached_meter}' reached {breached_value} of "
                        f"{breached_limit}"
                    )
                elif hit_implicit_cap:
                    # Named as the safety net it is, so an author does not read
                    # it as their own bound and go looking for the wrong thing.
                    _why = (
                        f"no declared bound was reached in "
                        f"{IMPLICIT_GOAL_ITERATION_CAP} iterations, so the "
                        f"implicit cap stopped it -- check that the declared "
                        f"meter(s) are actually moving"
                    )
                else:
                    _why = f"after {iterations} iteration(s)"
                return self.make_err(
                    "goal_error",
                    f"goal '{goal_name}' exhausted its budget ({_why}) "
                    f"without satisfying its condition",
                    payload={
                        "category": "budget_exhausted",
                        "implicit_cap": hit_implicit_cap,
                        "meter": breached_meter,
                        "meter_value": breached_value,
                        "meter_limit": breached_limit,
                        "goal": goal_name,
                        "workflow": flow_name,
                        "graph_id": graph_id,
                        "iterations": float(iterations),
                        "reached": sorted(reached),
                        "max_iterations": float(max_iterations),
                        "deadline_ms": deadline_ms,
                        "elapsed_ms": elapsed,
                    },
                )

            resume_label = retry_from if isinstance(retry_from, str) else (history[-1] if history else None)
            if resume_label is None:
                # Nothing to re-enter from: without a checkpoint there is no
                # carried state, so another pass would repeat this one exactly.
                # Say so rather than spin until the budget runs out.
                return self.make_err(
                    "goal_error",
                    f"goal '{goal_name}' cannot advance: '{flow_name}' recorded no "
                    f"checkpoint on this pass, so there is no point to resume the "
                    f"next pass from. Add a `checkpoint` that runs on every pass "
                    f"(#500).",
                    payload={"category": "no_checkpoint_reached", "goal": goal_name,
                             "workflow": flow_name, "graph_id": graph_id},
                )

            result = runner.resume_workflow(
                self, graph_id, resume_label, rebuild_graph=self._rebuild_workflow_graph
            )
            if getattr(result, "kind", None) == "error":
                return result
            if isinstance(result, dict) and result.get("ok") is False:
                return self.make_err(
                    "goal_error",
                    f"goal '{goal_name}' could not resume '{flow_name}': {result.get('error')}",
                    payload={"category": "resume_failed", "goal": goal_name,
                             "workflow": flow_name, "graph_id": graph_id,
                             "iterations": float(iterations)},
                )

    def builtin_run_goal(self, goal, args=None):
        if is_goal_pursuit_value(goal):
            if args is not None:
                # `goal … over …` names the workflow it pursues; parameters
                # belong to that workflow, not to the pursuit (#481).
                self.runtime_error(
                    "call",
                    "run_goal(pursuit) takes no arguments — declare parameters on "
                    "the workflow the goal pursues and bind them there",
                )
            return self.builtin_run_goal_pursuit(goal)
        if not is_goal_value(goal):
            self.runtime_error("type", "run_goal(goal) expects a goal")
        if getattr(self, "_suppress_flow_execution", False):
            return self._suppressed_flow_result()   # resume-rebuild — see run_workflow (#322)
        graph = workflow_to_graph(self, goal, init_state=True, args=args)
        return self.resolve_workflow_runner().start_graph(self, graph)

    def builtin_plan_goal(self, goal):
        if not is_goal_value(goal):
            self.runtime_error("type", "plan_goal(goal) expects a goal")
        graph = workflow_to_graph(self, goal, init_state=False, require_args=False)
        step_plan = self._step_plan_from_graph(graph, label="goal")
        self.last_graph_plan = step_plan
        self.event_bus.emit_event(
            "graph_plan_created",
            data={"nodes": float(len(step_plan.get("nodes", []))), "goal": step_plan.get("goal")},
        )
        return step_plan

    def builtin_resume_goal(self, graph_id, checkpoint=None):
        if not isinstance(graph_id, str):
            self.runtime_error("type", "resume_goal(graph_id, checkpoint) expects graph_id as string")
        if checkpoint is not None and not isinstance(checkpoint, str):
            self.runtime_error("type", "resume_goal(graph_id, checkpoint) expects checkpoint as string")
        target = self._resume_target_vm(graph_id)
        return self.resolve_workflow_runner().resume_workflow(
            target,
            graph_id,
            checkpoint,
            rebuild_graph=target._rebuild_workflow_graph,
        )

    @staticmethod
    def _relabel_plan(plan: dict, step_labels: dict) -> dict:
        """Rewrite a raw plan's task ids to step names (#679).

        One helper, because `plan_workflow` and `plan_graph` both need it and
        two spellings of "map ids to names" is how one of them ends up missing a
        field. Ids without a name pass through unchanged, so a partly-named
        graph is legible rather than half-blank.
        """
        if not step_labels:
            return dict(plan)
        def _name(node):
            return step_labels.get(node, node)
        relabelled = dict(plan)
        relabelled["nodes"] = [_name(n) for n in plan.get("nodes", [])]
        relabelled["edges"] = [[_name(a), _name(b)] for a, b in plan.get("edges", [])]
        relabelled["levels"] = [[_name(n) for n in level] for level in plan.get("levels", [])]
        relabelled["parallel_groups"] = [
            [_name(n) for n in level] for level in plan.get("parallel_groups", [])
        ]
        relabelled["conditional_edges"] = [
            [_name(a), _name(b)] for a, b in plan.get("conditional_edges", [])
        ]
        relabelled["edge_conditions"] = {
            f"{_name(key.split('->')[0])}->{_name(key.split('->')[1])}": value
            for key, value in plan.get("edge_conditions", {}).items()
        }
        return relabelled

    def _step_plan_from_graph(self, graph: TaskGraph, *, label: str) -> dict:
        plan = plan_graph(graph.tasks, graph=graph)
        step_labels = graph.metadata.get("task_to_step", {}) if isinstance(graph.metadata, dict) else {}
        flow_name = graph.metadata.get("workflow_name") if isinstance(graph.metadata, dict) else None
        step_plan = {
            label: graph.metadata.get("goal_name", flow_name) if isinstance(graph.metadata, dict) else None,
            "graph_id": plan.get("graph_id"),
            "nodes": [step_labels.get(node, node) for node in plan.get("nodes", [])],
            "edges": [[step_labels.get(edge[0], edge[0]), step_labels.get(edge[1], edge[1])] for edge in plan.get("edges", [])],
            "conditional_edges": [
                [step_labels.get(edge[0], edge[0]), step_labels.get(edge[1], edge[1])]
                for edge in plan.get("conditional_edges", [])
            ],
            "edge_conditions": {
                f"{step_labels.get(key.split('->')[0], key.split('->')[0])}"
                f"->{step_labels.get(key.split('->')[1], key.split('->')[1])}": value
                for key, value in plan.get("edge_conditions", {}).items()
            },
            "levels": [[step_labels.get(node, node) for node in level] for level in plan.get("levels", [])],
            "parallel_groups": [[step_labels.get(node, node) for node in level] for level in plan.get("parallel_groups", [])],
            "tasks": plan,
        }
        if label != "workflow":
            step_plan["workflow"] = flow_name
        return step_plan

    def _warn_on_source_drift(
        self, flow_name: str, source_path, stored_source: str, graph_id: str
    ) -> bool:
        """Say so when the file has changed since the run was planned.

        A resume replays the source stored with the run, so edits made in between
        have no effect. That is the right rule -- re-executing against the program
        the run was planned for is what makes checkpoint-restore mean anything --
        but it is a trap when it happens quietly, because the natural debugging
        loop is *the workflow failed, so edit the step and resume*, and the edit
        appears to do nothing.

        Reported rather than refused: a resume that stops working because someone
        touched the file would be worse than one that explains itself. Returns
        whether drift was found, for tests.

        **There are two ways the caller's view can differ from what runs, and for
        a long time only one was checked (#629):**

        1. the recorded file has been edited since the run started;
        2. the resume is driven from a *different* file that has its own copy of
           the flow.

        Case 2 replayed stale source and reported no drift at all, so the signal
        depended on which file the caller happened to be sitting in rather than
        on anything about the run. Both referents are checked here, and both
        report through one helper -- the question "is what runs what the caller
        thinks they are running?" gets one answer, not one per referent.
        """
        origin = getattr(self, "_resume_origin", None)
        if isinstance(origin, dict):
            # A resume that rebuilds runs on a child VM (`_resume_target_vm`), so
            # the caller's own program is only reachable through this snapshot.
            caller_path = origin.get("path")
            caller_source = origin.get("source")
            caller_declares = (origin.get("flows") or {}).get(flow_name)
        else:
            # Same-VM resume, or a bare runner VM with no program of its own.
            caller_path = getattr(self, "source_path", None)
            caller_source = getattr(self, "source_code", None)
            caller_declares = self._flow_declarations(caller_source).get(flow_name)
        recorded_known = isinstance(source_path, str) and bool(source_path)
        same_file = (
            recorded_known
            and isinstance(caller_path, str)
            and bool(caller_path)
            and os.path.abspath(source_path) == os.path.abspath(caller_path)
        )

        # Referent 1 -- the recorded path's current contents.
        if recorded_known:
            try:
                with open(source_path, "r", encoding="utf-8") as handle:
                    current = handle.read()
            except OSError:
                # The file has moved or gone. The run is still resumable from its
                # stored source, and a missing file is not drift.
                current = None
            if current is not None and current != stored_source:
                self._report_source_drift(
                    flow_name, graph_id, source_path, "recorded_path",
                    f"resume: '{flow_name}' is replaying the source stored when the run "
                    f"started; {source_path} has changed since and those edits are not in "
                    f"this run. Start a new run to pick them up.",
                )
                return True

        # Referent 2 -- the module driving this resume (#629).
        if same_file or caller_source == stored_source:
            return False
        if caller_declares is None:
            # A driver script that only calls resume_workflow() holds no competing
            # copy of the flow, so there is nothing for the caller to be wrong
            # about. Without this, every resume from a helper script would warn.
            return False
        # Compared at the *flow*, not the file. A resume driver necessarily
        # differs from the recorded program somewhere -- it has the
        # `resume_workflow(...)` call the original did not -- so a file-level
        # comparison would warn whenever someone copied the workflow verbatim
        # into their driver, and the message claims specifically that the flow
        # differs. Rendering both through the formatter makes that claim true:
        # `format_stmt` is the same renderer CI's `fmt --check` uses, and
        # `test_formatter_completeness` walks the AST node list, so a
        # declaration form it cannot render fails the suite rather than
        # silently comparing unequal here.
        stored_declares = self._flow_declarations(stored_source).get(flow_name)
        if stored_declares is None or stored_declares == caller_declares:
            return False
        self._report_source_drift(
            flow_name, graph_id, source_path, "resuming_module",
            f"resume: '{flow_name}' is replaying the source stored when the run "
            f"started, from {source_path or '<unrecorded>'} — not the '{flow_name}' "
            f"declared in {caller_path or 'the resuming module'}, which differs. "
            f"Errors from this run name the recorded file. Start a new run to use "
            f"the version you have.",
        )
        return True

    def _resume_origin_snapshot(self) -> dict:
        """What the drift check needs about the module driving a resume (#629).

        Captured on the caller because the resume may run on a child VM that has
        neither the caller's globals nor its source — `_resume_target_vm` builds
        one precisely so the rebuild cannot clobber the caller's program.

        Only names and text are copied. Handing the child the caller's globals
        would put the caller's bindings inside a VM that is about to be
        `reset_program`ed for someone else's run.
        """
        source = getattr(self, "source_code", None)
        return {
            "path": getattr(self, "source_path", None),
            "source": source,
            "flows": self._flow_declarations(source),
        }

    @staticmethod
    def _flow_declarations(source) -> dict[str, str]:
        """Every flow this source declares, name -> canonical rendering.

        One helper for both referents, so "what does this program say `w` is?"
        is answered in a single voice rather than once per call site.

        Returns `{}` for anything unparseable: a caller whose source cannot be
        read is a caller we know nothing about, and guessing there would produce
        exactly the spurious warning the flow-level comparison exists to avoid.
        """
        if not isinstance(source, str) or not source:
            return {}
        try:
            from nodus.frontend.ast.ast_nodes import GoalDef, GoalPursuit, WorkflowDef
            from nodus.frontend.lexer import tokenize
            from nodus.frontend.parser import Parser
            from nodus.tooling.formatter import format_stmt
            stmts = Parser(tokenize(source)).parse()
        except Exception:
            return {}
        found: dict[str, str] = {}
        for stmt in stmts:
            if not isinstance(stmt, (WorkflowDef, GoalDef, GoalPursuit)):
                continue
            name = getattr(stmt, "name", None)
            if not isinstance(name, str):
                continue
            try:
                found[name] = "\n".join(format_stmt(stmt, 0))
            except Exception:
                continue
        return found

    def _report_source_drift(
        self, flow_name: str, graph_id: str, source_path, referent: str, message: str
    ) -> None:
        """The single place a drift is announced, for either referent."""
        print(message, file=sys.stderr)
        self.event_bus.emit_event(
            "workflow_source_drift",
            data={
                "workflow": flow_name,
                "graph_id": graph_id,
                "source_path": source_path,
                # Which referent disagreed, so a consumer can tell "the file was
                # edited" from "you are resuming with a different program".
                "referent": referent,
            },
        )

    def _rebuild_workflow_graph(self, graph_id: str, state: dict) -> TaskGraph | None:
        _meta_raw = state.get("metadata")
        metadata: dict[str, Any] = _meta_raw if isinstance(_meta_raw, dict) else {}
        workflow_name = metadata.get("workflow_name")
        goal_name = metadata.get("goal_name")
        execution_kind = metadata.get("execution_kind")
        flow_name = goal_name if isinstance(goal_name, str) and goal_name else workflow_name
        if not isinstance(flow_name, str) or not flow_name:
            raise WorkflowRebuildError(
                "persisted run names no workflow or goal to rebuild"
            )
        source_code = metadata.get("workflow_source_code")
        source_path = metadata.get("workflow_source_path")
        self._last_resume_source_drift = False
        if not isinstance(source_code, str):
            # Runs persisted before every entry point recorded its source (#469).
            # Re-reading the file means the rebuild uses whatever is on disk now,
            # which is the opposite of the pinned rule below -- kept only so those
            # older runs stay resumable at all.
            if not isinstance(source_path, str) or not source_path or not os.path.exists(source_path):
                raise WorkflowRebuildError(
                    f"no source to rebuild '{flow_name}' from — the run stored no "
                    f"source code and its path is missing or unreadable "
                    f"({source_path!r})"
                )
            with open(source_path, "r", encoding="utf-8") as f:
                source_code = f.read()
            # #497: this branch used to be the silent half of the fork -- an
            # unpinned rebuild picked up edits with no signal at all, while the
            # pinned branch warned. Say which rule is in effect -- and why the
            # source is missing: a run that opted out of persisting it (#499)
            # did not "predate" anything.
            if metadata.get("workflow_source_persisted") is False:
                reason = "opted out of source persistence (persist_workflow_source=False)"
            else:
                reason = "predates source recording"
            print(
                f"resume: run '{graph_id}' {reason}, so "
                f"'{flow_name}' is rebuilt from {source_path} as it is now; edits "
                f"made since the run started are in this resume.",
                file=sys.stderr,
            )
            self.event_bus.emit_event(
                "workflow_rebuild_unpinned",
                data={
                    "workflow": flow_name,
                    "graph_id": graph_id,
                    "source_path": source_path,
                },
            )
        else:
            self._last_resume_source_drift = self._warn_on_source_drift(
                flow_name, source_path, source_code, graph_id
            )
        rebuild_path = source_path if isinstance(source_path, str) and source_path else None
        worker_dispatcher = getattr(self, "worker_dispatcher", None)
        event_bus = self.event_bus
        try:
            from nodus.runtime.module_loader import ModuleLoader as _ModuleLoader
            # Rebuild through the normal module-load path with THIS vm as the
            # execution target, so the workflow's `import` statements are re-bound
            # exactly as on first run: flat exports land in module_globals and
            # bare-namespace imports (e.g. `json` from `import "std:json"`)
            # populate this vm's _bare_import_hints. The previous compile_only
            # path was import-blind, leaving the rebuilt vm without tool/mem/json
            # bound — a post-wait step referencing them failed with "Undefined
            # variable: <name>", surfaced only in spawned_errors while the run
            # still reported ok: True (so cross-process resume silently no-op'd).
            #
            # Host-injected (non-import) globals are NOT reconstructable from
            # source; reset_program preserves self.host_globals, and the embedder
            # must re-supply them on the rehydrating runtime.
            _loader = _ModuleLoader(
                project_root=None,
                vm=self,
                host_globals=getattr(self, "host_globals", None),
            )
            module_name = rebuild_path or "<memory>"
            base_dir = os.path.dirname(rebuild_path) if rebuild_path else os.getcwd()
            # #322: this re-execution exists only to re-bind the workflow/fn
            # definitions and imports. Suppress top-level run_workflow/run_goal so a
            # self-invoking module does not spawn a spurious fresh graph and re-run
            # its steps. The flag rides on `self` (reset_program preserves it) and is
            # cleared in finally, so the actual resume run that follows is unaffected.
            # While `_suppress_flow_execution` is set, run_workflow/run_goal are
            # skipped (above) and `print` is a no-op (see builtin_print) — so the
            # rebuild's re-run of pure top-level statements (e.g. a
            # `print("init: \(r["steps"])")` after the driver) is silent and does not
            # leak into the resumed run's output (#328 facet 2). The real resume run
            # happens after this returns, with the flag cleared, and prints normally.
            _prev_suppress = getattr(self, "_suppress_flow_execution", False)
            self._suppress_flow_execution = True
            try:
                _loader.load_module_from_source(source_code, module_name=module_name, base_dir=base_dir)
            finally:
                self._suppress_flow_execution = _prev_suppress
        except WorkflowRebuildError:
            raise
        except Exception as err:
            # #399: this used to be `except Exception: return None`, and the caller
            # turned None into "Unknown graph" — so a rebuild that failed for any
            # reason reported that the run did not exist, and the actual cause was
            # discarded. Carry it instead; the diagnosis is the whole value here.
            raise WorkflowRebuildError(
                f"re-executing the module to rebuild '{flow_name}' failed",
                cause=err,
            ) from err
        self.event_bus = event_bus
        self.source_code = source_code
        if worker_dispatcher is not None:
            self.worker_dispatcher = worker_dispatcher
        workflow = find_goal_value(self.globals, flow_name) if execution_kind == "goal" else find_workflow_value(self.globals, flow_name)
        if workflow is None:
            kind_word = "goal" if execution_kind == "goal" else "workflow"
            raise WorkflowRebuildError(
                f"{kind_word} '{flow_name}' is not defined by the rebuilt module — "
                f"it may have been renamed or removed since the run started"
            )
        _stt_raw = metadata.get("step_to_task")
        step_to_task: dict[str, Any] | None = _stt_raw if isinstance(_stt_raw, dict) else None
        _stored_args = metadata.get("workflow_args")
        graph = workflow_to_graph(
            self, workflow, init_state=False, task_ids_by_step=step_to_task,
            prebound_args=_stored_args if isinstance(_stored_args, dict) else {},
        )
        graph.graph_id = graph_id
        # #501: the child list is cumulative across resumes. The rebuilt graph's
        # metadata is fresh, so without this each resume's persist would keep
        # only the children that resume spawned, dropping earlier ones from the
        # parent side of the link (the child -> parent half is durable either
        # way).
        _prior_children = metadata.get("child_graph_ids")
        if isinstance(_prior_children, list) and _prior_children and isinstance(graph.metadata, dict):
            graph.metadata["child_graph_ids"] = list(_prior_children)
        kind_word = "goal" if execution_kind == "goal" else "workflow"
        self._validate_rebuilt_topology(graph, metadata, flow_name, kind_word, graph_id)
        return graph

    def _validate_rebuilt_topology(
        self, graph: TaskGraph, metadata: dict, flow_name: str, kind_word: str, graph_id: str
    ) -> None:
        """Refuse a rebuild whose shape is not the shape the run was planned for.

        The persisted state is per-task bookkeeping keyed to the planned graph;
        applying it to a different graph manufactures false diagnoses -- a step
        inserted between two others collides with a stored task id and surfaces
        as `Dependency cycle detected: z -> z` in source with no cycle (#470).
        Name the real cause instead, before any of that machinery runs.

        Structure only, deliberately: a body or `when` edit does not refuse (see
        `graph_topology`). Runs that predate the stored topology are checked on
        step names alone, from `step_to_task` -- edges were not recorded, so an
        edge-only rewire on such a run is still undetectable.
        """
        rebuilt = graph_topology(graph.tasks)
        stored = metadata.get("workflow_topology")
        if not isinstance(stored, dict):
            stt = metadata.get("step_to_task")
            if not isinstance(stt, dict) or not stt:
                return
            stored = {"steps": sorted(str(key) for key in stt)}
        stored_steps = stored.get("steps")
        problems: list[str] = []
        if isinstance(stored_steps, list):
            added = sorted(set(rebuilt["steps"]) - set(stored_steps))
            removed = sorted(set(stored_steps) - set(rebuilt["steps"]))
            if added:
                problems.append(f"steps added: {', '.join(added)}")
            if removed:
                problems.append(f"steps removed: {', '.join(removed)}")
        stored_edges = stored.get("edges")
        if not problems and isinstance(stored_edges, list):
            stored_pairs = {tuple(edge) for edge in stored_edges if isinstance(edge, list)}
            rebuilt_pairs = {tuple(edge) for edge in rebuilt["edges"]}
            if stored_pairs != rebuilt_pairs:
                problems.append("dependencies re-wired")
        if problems:
            raise WorkflowRebuildError(
                f"run '{graph_id}' was planned against a different version of "
                f"{kind_word} '{flow_name}': its step structure has changed since "
                f"the run started ({'; '.join(problems)}). A resume replays the "
                f"planned structure; start a new run to use the edited {kind_word}."
            )

    def _rollback_to_checkpoint(self, graph: TaskGraph, state: dict, entry: dict) -> None:
        if graph is None or not isinstance(state, dict) or not isinstance(entry, dict):
            return
        tasks_state = state.get("tasks")
        if not isinstance(tasks_state, dict):
            return
        task_id = entry.get("task_id")
        if not isinstance(task_id, str):
            step_name = entry.get("step")
            if isinstance(step_name, str) and isinstance(graph.metadata, dict):
                step_to_task = graph.metadata.get("step_to_task", {})
                if isinstance(step_to_task, dict):
                    task_id = step_to_task.get(step_name)
        if not isinstance(task_id, str):
            return
        by_id = {task.task_id: task for task in graph.tasks}
        if task_id not in by_id:
            return
        dependents: dict[str, list[str]] = {}
        for task in graph.tasks:
            for dep in task.dependencies:
                dependents.setdefault(dep.task_id, []).append(task.task_id)
        reset: set[str] = set()
        stack = [task_id]
        while stack:
            current = stack.pop()
            if current in reset:
                continue
            reset.add(current)
            for nxt in dependents.get(current, []):
                stack.append(nxt)
        for tid in reset:
            saved = tasks_state.get(tid)
            if not isinstance(saved, dict):
                continue
            saved["state"] = "pending"
            saved["attempts"] = 0
            saved.pop("result", None)
            saved.pop("last_error", None)

    def builtin_workflow_state(self):
        ctx = self.current_workflow_context()
        if ctx is None:
            return None
        return ctx.get("state")

    def builtin_workflow_arg(self, name):
        """Read a bound workflow parameter (#481).

        Emitted by the workflow lowering as the prelude of every step body, one
        `let` per declared parameter. A program does not write this call; the
        argument arrives from the run, which is what makes a parameter durable
        by construction — on a resume it is read back from the run record
        rather than re-derived, so it cannot quietly become a different value
        the way a module-level `let` read inside a step could.

        Reached only through `builtin_call` (#411), so binding the name in guest
        code cannot intercept a step's own parameter reads.
        """
        if not isinstance(name, str):
            self.runtime_error("type", "workflow_arg(name) expects name as string")
        ctx = self.current_workflow_context()
        if not isinstance(ctx, dict):
            return None
        args = ctx.get("args")
        if not isinstance(args, dict):
            return None
        return args.get(name)

    def builtin_state_contribute(self, key, value):
        """Contribute to a folded workflow-state cell (#485).

        Emitted by the workflow lowering for `cell += expr` where `cell` declares
        `merge: "sum"` or `merge: "append"`. It records the contribution and does
        **not** touch the cell: it is the read-modify-write on the shared cell
        that loses updates, and a contribution never reads it.

        Reached only through `builtin_call` (#411), so a program cannot bind the
        name and intercept its own state writes.
        """
        from nodus.orchestration.workflow_state import (
            FOLD_CONTRIBUTION_KINDS,
            TrackedState,
            check_contribution,
        )

        ctx = self.current_workflow_context()
        if not isinstance(ctx, dict):
            self.runtime_error(
                "workflow_error",
                "state contribution outside a workflow step",
            )
        state = ctx.get("state")
        task_id = ctx.get("task_id")
        if not isinstance(state, TrackedState) or not isinstance(task_id, str):
            self.runtime_error(
                "workflow_error",
                f"state '{key}' cannot be contributed to outside a tracked workflow run",
            )
        merge = state.merge_policy(key)
        problem = check_contribution(merge, value)
        if problem is not None:
            self.runtime_error(
                "type",
                f"state '{key}' is declared merge: \"{merge}\", but {problem}. "
                f"Under a fold policy `{key} += expr` contributes "
                f"{FOLD_CONTRIBUTION_KINDS.get(merge, 'a value')}.",
            )
        step = state.open_step(task_id)
        if step is None:
            # No open record: the step is not running under the graph runner that
            # opens one. Falling back to a direct write would silently reintroduce
            # the lost update this whole mechanism exists to remove.
            self.runtime_error(
                "workflow_error",
                f"state '{key}' contribution has no open step record to land in",
            )
        step.contribute(key, value)
        return None

    def builtin_workflow_resume_payload(self):
        ctx = self.current_workflow_context()
        if ctx is None:
            return None
        return ctx.get("resume_payload")

    #: Options `workflow_wait`'s map form accepts. Closed and checked, like the
    #: `budget` and step-option vocabularies -- an unknown key is a mistake the
    #: author can fix now, not a silently discarded declaration (#490's rule).
    WAIT_OPTION_KEYS = ("correlation_key", "payload", "deadline_ms", "schema")

    def builtin_workflow_wait(self, event_type, correlation_key=None, payload=None, deadline_ms=None):
        if not isinstance(event_type, str) or not event_type:
            self.runtime_error("type", "workflow_wait(event_type, ...) expects event_type as non-empty string")
        # #472: argument 2 type-dispatches. A **string** is `correlation_key`, as
        # it has always been; a **map** is an options map carrying every option
        # including `schema`. All four positions were already named, so there was
        # no free slot -- and this caps positional growth rather than adding a
        # fifth argument to a signature that was one option from unwritable.
        schema = None
        if isinstance(correlation_key, (dict, Record)):
            options = dict(correlation_key.fields) if isinstance(correlation_key, Record) else dict(correlation_key)
            unknown = sorted(k for k in options if k not in self.WAIT_OPTION_KEYS)
            if unknown:
                self.runtime_error(
                    "type",
                    f"workflow_wait: unknown option(s) {', '.join(repr(k) for k in unknown)}. "
                    f"Known options: {', '.join(self.WAIT_OPTION_KEYS)}.",
                )
            if payload is not None or deadline_ms is not None:
                self.runtime_error(
                    "type",
                    "workflow_wait(event_type, options) takes the options map alone — "
                    "put correlation_key, payload and deadline_ms inside it rather than "
                    "mixing the two forms",
                )
            correlation_key = options.get("correlation_key")
            payload = options.get("payload")
            deadline_ms = options.get("deadline_ms")
            schema = self._normalize_wait_schema(options.get("schema"))
        if correlation_key is not None and not isinstance(correlation_key, str):
            self.runtime_error("type", "workflow_wait(..., correlation_key, ...) expects correlation_key as string or nil")
        if isinstance(payload, Record):
            payload = dict(payload.fields)
        if payload is not None and not isinstance(payload, dict):
            self.runtime_error("type", "workflow_wait(..., payload, ...) expects payload as map or nil")
        if deadline_ms is not None:
            if isinstance(deadline_ms, bool) or not isinstance(deadline_ms, (int, float)):
                self.runtime_error("type", "workflow_wait(..., deadline_ms) expects deadline_ms as number or nil")
            deadline_ms = float(deadline_ms)
        wait = {
            "__workflow_wait__": True,
            "event_type": event_type,
            "correlation_key": correlation_key,
            "payload": payload or {},
            "deadline_ms": deadline_ms,
        }
        if schema:
            # Only when declared, so a wait without one persists exactly the
            # record it always did.
            wait["schema"] = schema
        return wait

    def _normalize_wait_schema(self, schema):
        """Normalise a declared resume-payload schema, refusing a bad one here.

        Refused at the **wait site** rather than at the resume: that is where the
        mistake is, and a schema that only failed when someone tried to resume
        would be a declaration nobody validated — the shape this cluster keeps
        removing.

        Uses the runtime schema dialect (`runtime/schema_contract.py`), the same
        one `std:tool` and `register_function` use, rather than
        `nodus_lang_schema`. The design note for this predates that module and
        named the ABI validator; the payload is a *runtime* value that may arrive
        as a `Record` from an in-language resume, which the ABI validator does not
        model — and sharing this one keeps the failure wording identical across
        all three typed boundaries.
        """
        if schema is None:
            return None
        from nodus.runtime.schema_contract import normalize_runtime_schema

        normalized, err = normalize_runtime_schema(schema)
        if err is not None:
            self.runtime_error("type", f"workflow_wait: schema {err}")
        return normalized

    def builtin_current_workflow_id(self):
        ctx = self.current_workflow_context()
        if ctx is None:
            return None
        return ctx.get("graph_id")

    def builtin_emit(self, name, payload=None):
        if not isinstance(name, str) or not name:
            self.runtime_error("type", "emit(name, payload) expects name as string")
        if payload is None:
            payload = {}
        if not isinstance(payload, dict):
            self.runtime_error("type", "emit(name, payload) expects payload as a map")
        if not is_json_safe(payload):
            self.runtime_error("type", "emit payload must be JSON-safe")
        data = dict(payload)
        data.update(self.runtime_adapter_event_data(payload))
        self.event_bus.emit_event(name, data=data)
        return payload

    def runtime_adapter_event_data(self, payload=None, *, ok: bool | None = None, error: str | None = None) -> dict:
        data = {}
        ctx = self.current_workflow_context()
        if isinstance(ctx, dict):
            workflow = ctx.get("workflow")
            graph_id = ctx.get("graph_id")
            goal = ctx.get("goal")
            step = ctx.get("step")
            if workflow is not None:
                data["workflow"] = workflow
            if goal is not None:
                data["goal"] = goal
            if graph_id is not None:
                data["graph_id"] = graph_id
            if step is not None:
                data["step"] = step
        if self.session_id is not None:
            data["session"] = self.session_id
        if self.trace_id is not None:
            data["trace_id"] = self.trace_id
        data["execution_unit_id"] = self.execution_unit_id
        if ok is not None:
            data["ok"] = bool(ok)
        if error is not None:
            data["error"] = error
        if payload is not None:
            data["payload_keys"] = payload_keys(payload)
        return data

    def builtin_workflow_checkpoints(self, graph_id):
        checkpoints = None
        if graph_id is None:
            ctx = self.current_workflow_context()
            if ctx is not None:
                checkpoints = ctx.get("checkpoints")
        else:
            if not isinstance(graph_id, str):
                self.runtime_error("type", "workflow_checkpoints(graph_id) expects a string or nil")
            state = load_graph_state(graph_id)
            if state is None:
                return []
            checkpoints = state.get("checkpoints")
        return checkpoints_public(checkpoints or [])

    def builtin_workflow_checkpoint(self, label):
        if not isinstance(label, str):
            self.runtime_error("type", "checkpoint label must be a string")
        ctx = self.current_workflow_context()
        if ctx is None:
            self.runtime_error("runtime", "checkpoint used outside workflow execution")
        handler = ctx.get("checkpoint")
        if not callable(handler):
            self.runtime_error("runtime", "checkpoint handler unavailable")
        handler(label)
        return None

    def current_workflow_context(self):
        if self.current_coroutine is not None:
            ctx = getattr(self.current_coroutine, "workflow_context", None)
            if ctx is not None:
                return ctx
        return None

    def _goal_action_meta(self, kind: str, target: str | None) -> dict | None:
        ctx = self.current_workflow_context()
        if not isinstance(ctx, dict):
            return None
        goal = ctx.get("goal")
        if not isinstance(goal, str) or not goal:
            return None
        return {
            "goal": goal,
            "workflow": ctx.get("workflow"),
            "graph_id": ctx.get("graph_id"),
            "step": ctx.get("step"),
            "action_kind": kind,
            "action_target": target,
        }

    def _run_goal_action(self, kind: str, target: str | None, fn):
        meta = self._goal_action_meta(kind, target)
        if meta is not None:
            self.event_bus.emit_event("goal_action_start", name=target, data=meta)
        try:
            result = fn()
        except Exception as _e:
            if meta is not None:
                fail = dict(meta)
                fail["message"] = str(_e)
                self.event_bus.emit_event("goal_action_fail", name=target, data=fail)
            raise
        ok = not (isinstance(result, dict) and result.get("ok") is False)
        if meta is not None:
            event_type = "goal_action_complete" if ok else "goal_action_fail"
            data = dict(meta)
            if not ok:
                err = result.get("error") if isinstance(result, dict) else None
                if isinstance(err, dict):
                    data["message"] = err.get("message")
            self.event_bus.emit_event(event_type, name=target, data=data)
        return result

    def builtin_tool_call(self, name, args):
        return call_tool(name, args, vm=self)

    def builtin_tool_available(self):
        return available_tools()

    def builtin_tool_describe(self, name):
        if not isinstance(name, str):
            self.runtime_error("type", "tool_describe(name) expects a string")
        return describe_tool(name)

    def builtin_syscall(self, name, payload):
        from nodus.services.syscall_runtime import call_syscall
        if not isinstance(payload, dict):
            payload = {}
        result = call_syscall(name, payload, vm=self)
        return _dict_to_record(result)

    def builtin_syscall_list(self):
        from nodus.services.syscall_runtime import list_syscalls
        return list_syscalls()

    def builtin_memory_get(self, key):
        try:
            return get_value(key, vm=self)
        except ValueError as _e:
            self.runtime_error("type", str(_e))

    def builtin_memory_put(self, key, value):
        try:
            return put_value(key, value, vm=self)
        except ValueError as _e:
            self.runtime_error("type", str(_e))

    def builtin_memory_delete(self, key):
        try:
            return delete_value(key, vm=self)
        except ValueError as _e:
            self.runtime_error("type", str(_e))

    def builtin_memory_keys(self):
        return list_keys(vm=self)

    def builtin_memory_has(self, key):
        try:
            return has_value(key, vm=self)
        except ValueError as _e:
            self.runtime_error("type", str(_e))

    def builtin_agent_call(self, name, payload):
        return call_agent(name, payload, vm=self)

    def builtin_agent_call_async(self, name, payload):
        """Async variant of agent_call (#294)."""
        return self._dispatch_agent_async(name, payload)

    def _dispatch_agent_async(self, name, payload, on_complete=None):
        """Run an agent handler off the scheduler thread and suspend until it lands.

        Runs the handler on a daemon thread and suspends the calling coroutine, so
        concurrent agent calls overlap instead of serializing on the single
        scheduler thread. Mirrors the thread + ``_io_channels`` pattern of
        ``subprocess_run_async`` / ``http_*_async``.

        Falls back to the synchronous ``call_agent`` when not running inside the
        scheduler's own coroutine — same guard as ``_do_async_run``.

        Note for anyone reading #398: an earlier revision of this docstring said
        the fallback covers "module-function or **graph contexts**", and the issue
        took that to mean workflow steps could not use this path. Measured, they
        can: ``spawn_task`` runs a step body as a scheduler coroutine, so the
        guard passes and two independent agent steps overlap by a full second.

        ``on_complete`` is invoked exactly once with the handler's result, on
        whichever path is taken — the worker thread when suspended, inline when
        not. It exists so a caller that emits paired start/complete events can
        emit the completion when the result actually arrives rather than when the
        call suspends.
        """
        scheduler = getattr(self, "scheduler", None)
        coroutine = getattr(self, "current_coroutine", None)
        if (scheduler is None or coroutine is None or
                coroutine is not getattr(scheduler, "current_task", None)):
            result = call_agent(name, payload, vm=self)
            if on_complete is not None:
                on_complete(result)
            return result

        # #596: capture the step's deadline HERE, on the scheduler thread, while
        # `scheduler.current_task` is still this coroutine. The worker below runs
        # after the coroutine suspends, and `_effective_timeout_ms` reads exactly
        # the state that suspension clears — so computing it there returned None
        # and #424's bound silently did not apply to `action agent` at all. The
        # guard above is what makes this the right place: past it, the budget is
        # readable by construction.
        deadline_ms = _effective_timeout_ms(self)

        result_ch = Channel()

        def _worker() -> None:
            result = call_agent(name, payload, vm=self, timeout_ms=deadline_ms)
            if on_complete is not None:
                # Before publishing to the channel, so the completion event cannot
                # be observed after the value it describes has been consumed.
                try:
                    on_complete(result)
                except Exception:
                    pass
            result_ch.queue.append(result)
            result_ch.closed = True

        threading.Thread(target=_worker, daemon=True).start()
        scheduler._io_channels.append(result_ch)

        coroutine.state = "suspended"
        coroutine.blocked_on = result_ch
        coroutine.blocked_reason = "agent_async"
        self.stack.append(None)
        self.save_current_coroutine_state(self.ip + 1)
        result_ch.waiting_receivers.append(coroutine)
        return ChannelRecvRequest(result_ch)

    def builtin_action_tool(self, name, args):
        return self._run_goal_action("tool", name, lambda: self.builtin_tool_call(name, args))

    def builtin_action_agent(self, name, payload):
        """#398: dispatch the handler off the scheduler thread so independent
        steps that call agents actually overlap.

        Not `_run_goal_action`, because that emits the completion event around
        `fn()` returning — and when the call suspends, `fn()` returns a
        suspension marker rather than the handler's result. That would fire
        `goal_action_complete` at suspend time, carrying the marker, and nothing
        when the value really arrived. Paired start/complete events are one of the
        few guarantees this boundary actually makes, so the completion is emitted
        from the worker instead, via `on_complete`.
        """
        meta = self._goal_action_meta("agent", name)
        if meta is not None:
            self.event_bus.emit_event("goal_action_start", name=name, data=meta)

        def _complete(result):
            if meta is None:
                return
            ok = not (isinstance(result, dict) and result.get("ok") is False)
            data = dict(meta)
            if not ok:
                err = result.get("error") if isinstance(result, dict) else None
                if isinstance(err, dict):
                    data["message"] = err.get("message")
            self.event_bus.emit_event(
                "goal_action_complete" if ok else "goal_action_fail",
                name=name,
                data=data,
            )

        try:
            return self._dispatch_agent_async(name, payload, on_complete=_complete)
        except Exception as _e:
            if meta is not None:
                fail = dict(meta)
                fail["message"] = str(_e)
                self.event_bus.emit_event("goal_action_fail", name=name, data=fail)
            raise

    def builtin_action_memory_put(self, key, value):
        return self._run_goal_action("memory_put", key, lambda: self.builtin_memory_put(key, value))

    def builtin_action_memory_get(self, key):
        return self._run_goal_action("memory_get", key, lambda: self.builtin_memory_get(key))

    def builtin_action_emit(self, name, payload):
        return self._run_goal_action("emit", name, lambda: self.builtin_emit(name, payload))

    def builtin_agent_available(self):
        return available_agents(self)

    def builtin_agent_describe(self, name):
        if not isinstance(name, str):
            self.runtime_error("type", "agent_describe(name) expects a string")
        return describe_agent(name, self)

    # Backward-compatible wrappers for methods accessed directly in tests or
    # internal callers (e.g. scheduler.py).
    def builtin_coroutine_resume(self, value):
        """Resume a suspended coroutine and run it until its next yield or completion.

        This is a thin wrapper around the `resume` builtin registered by
        `builtins/coroutine.py`.  It exists for backward-compatibility: tests and
        the scheduler call `vm.builtin_coroutine_resume(coro)` directly rather than
        going through the CALL opcode.

        Pre-conditions (enforced by the `resume` builtin):
        - `value` must be a Coroutine instance.
        - The coroutine must be in `state == "suspended"`.  Calling on a finished or
          already-running coroutine raises a runtime error.

        Caller's stack during resume:
        - The VM saves its own execution context (ip, stack, frames, handler_stack,
          pending flags) before swapping in the coroutine's saved context.
        - The coroutine's saved stack becomes the active stack for the duration of
          the resume.
        - On return (YIELD or RETURN), the VM restores the caller's context.

        Error propagation:
        - If the coroutine raises a runtime error that is not caught inside the
          coroutine body, the error propagates out of `execute()` and up to the
          scheduler or `run_closure()` caller.  The coroutine is left in its
          error state; the caller is responsible for deciding whether to re-raise.

        Returns the yielded value (on YIELD) or the final return value (on coroutine
        completion).
        """
        return self.builtins["resume"].fn(value)

    def unwind_cancelled_coroutine(self, coroutine, err) -> None:
        """Run a timed-out coroutine's pending `finally` blocks, then let the error out.

        The scheduler used to drop a timed-out coroutine where it stood. Its
        `finally` blocks never ran, so a step holding a lock, an open transaction
        or a spawned subprocess lost its release -- and runtime invariant I-VM-06
        states that `finally` always executes (#502).

        Resuming it once more with `cancelling` set unwinds through the finallys
        and nothing else: `handle_exception` refuses to enter a `catch` while
        cancelling, so the step cannot swallow its own deadline and keep running.
        The error then propagates out of the resume exactly as it did before, so
        the caller's error handling is unchanged.

        Bounded by the same `task_step_budget` as any other resume -- a `finally`
        that loops forever must not turn a timeout into a hang.
        """
        coroutine.cancelling = err
        # Save the caller's context first. `load_coroutine_context` overwrites the
        # VM's stack, frames and ip wholesale -- the `resume` builtin pairs it with
        # a save for exactly this reason, and skipping that here destroyed the
        # frames of whatever called into the scheduler.
        ctx = self.save_execution_context()
        try:
            self.load_coroutine_context(coroutine)
            if not self.handle_exception(err):
                return  # nothing pending; caller delivers the error as before
            self.execute()
        finally:
            coroutine.cancelling = None
            self._cancelling = False
            coroutine.state = "finished"
            self.restore_execution_context(ctx)

    def builtin_read_file(self, path):
        return self.builtins["read_file"].fn(path)

    def escape_string(self, s: str) -> str:
        return s.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n").replace("\t", "\\t")

    def display_name(self, name: str) -> str:
        # Compiler-emitted builtin call sites (#411) are an implementation detail of
        # the lowering; a trace or stack frame should say `effect_resolve`, not the
        # mangled call site the reader never wrote.
        if name.startswith(BUILTIN_CALL_PREFIX):
            return name[len(BUILTIN_CALL_PREFIX):]
        if "__fn" in name:
            name = name.split("__fn", 1)[0]
        if name.startswith("__mod") and "__" in name[5:]:
            parts = name.split("__", 2)
            if len(parts) == 3 and parts[2]:
                return parts[2]
        return name

    def value_to_string(self, value, quote_strings: bool = False) -> str:
        if value is None:
            return "nil"
        if isinstance(value, bool):
            return "true" if value else "false"
        if isinstance(value, str):
            if quote_strings:
                return f"\"{self.escape_string(value)}\""
            return value
        if isinstance(value, list):
            inner = ", ".join(self.value_to_string(v, quote_strings=True) for v in value)
            return f"[{inner}]"
        if isinstance(value, dict):
            parts = []
            for k, v in value.items():
                key_s = self.value_to_string(k, quote_strings=True)
                val_s = self.value_to_string(v, quote_strings=True)
                parts.append(f"{key_s}: {val_s}")
            return "{" + ", ".join(parts) + "}"
        if isinstance(value, Record):
            if value.kind == "error":
                message = value.fields.get("message")
                if isinstance(message, str):
                    return message
            parts = []
            for k, v in value.fields.items():
                key_s = self.value_to_string(k, quote_strings=True)
                val_s = self.value_to_string(v, quote_strings=True)
                parts.append(f"{key_s}: {val_s}")
            return "record {" + ", ".join(parts) + "}"
        if isinstance(value, NodusModule):
            return f"<module {value.path}>"
        if isinstance(value, Coroutine):
            return f"<coroutine {value.state}>"
        if isinstance(value, Channel):
            return "<channel>"
        if isinstance(value, TaskNode):
            return f"<task {value.task_id} {value.status}>"
        if isinstance(value, TaskGraph):
            return f"<graph {len(value.tasks)} tasks>"
        if isinstance(value, bytes):
            return value.hex()
        if isinstance(value, BuiltinMethod):
            return "<builtin-method>"
        return str(value)

    def to_list_index(self, value):
        if isinstance(value, bool):
            self.runtime_error("index", "List index must be an integer")
        if isinstance(value, int):
            return value
        if isinstance(value, float) and value.is_integer():
            return int(value)
        self.runtime_error("index", "List index must be an integer")

    def is_valid_map_key(self, value):
        if isinstance(value, bool):
            return False
        return isinstance(value, (str, int, float))

    def read_index(self, seq, idx):
        if isinstance(seq, list):
            i = self.to_list_index(idx)
            if i < 0 or i >= len(seq):
                self.runtime_error("index", f"List index out of range: {i}")
            return seq[i]

        if isinstance(seq, dict):
            if not self.is_valid_map_key(idx):
                self.runtime_error("type", "Map keys must be strings or numbers")
            if idx not in seq:
                self.runtime_error("key", f"Missing map key: {self.value_to_string(idx, quote_strings=True)}")
            return seq[idx]

        if isinstance(seq, str):
            i = self.to_list_index(idx)
            if i < 0 or i >= len(seq):
                self.runtime_error("index", f"String index out of range: {i}")
            return seq[i]

        hint = ""
        if isinstance(seq, Record) and seq.kind == "error" and seq.fields.get("kind") == "thrown":
            hint = "; this is a caught thrown value — access the original via e.payload"
        self.runtime_error("type", "Indexing is only supported on lists, maps, and strings" + hint)

    def write_index(self, seq, idx, value):
        if isinstance(seq, list):
            i = self.to_list_index(idx)
            if i < 0 or i >= len(seq):
                self.runtime_error("index", f"List index out of range: {i}")
            seq[i] = value
            return value

        if isinstance(seq, dict):
            if not self.is_valid_map_key(idx):
                self.runtime_error("type", "Map keys must be strings or numbers")
            seq[idx] = value
            return value

        self.runtime_error("type", "Index assignment is only supported on lists and maps")

    def check_capability(self, capability: str | None, target: str, kind: str, args=()) -> None:
        """Consult the capability policy, or return immediately if there is none.

        Raises a sandbox error on refusal, after recording it on the event bus —
        a denial that is only raised cannot be audited, and "what did this program
        try that it was not allowed to?" is the question an operator running
        generated code actually has (#405).
        """
        policy = self.capability_policy
        floor = self.capability_floor
        if policy is None and floor is None:
            return
        request = CapabilityRequest(
            capability=capability, target=target, kind=kind, args=tuple(args)
        )

        # The floor is consulted FIRST and can only restrict — it has no way to
        # return `allow`, so it can never grant what the policy would refuse.
        # Ordering it ahead of the policy is the whole point: it must hold
        # regardless of what any policy, or any future bypass switch, says.
        decision = floor.check(request) if floor is not None else None
        if decision is None and policy is not None:
            decision = policy.check(request)
        if decision is None or decision.outcome == ALLOW:
            return

        if decision.outcome == ASK:
            channel = self.approval_channel
            if channel is not None and channel.request(request, decision.reason):
                return
            # Nobody to ask, or asked and refused. An unanswered question is not
            # permission.
            reason = decision.reason or f"{capability or target} requires approval"
            suffix = "" if channel is not None else " (no approval channel configured)"
            emit_denied(self.event_bus, request, reason + suffix)
            self.runtime_error("sandbox", f"Blocked: {reason}{suffix}")

        reason = decision.reason or f"{capability or target} is not granted"
        emit_denied(self.event_bus, request, reason)
        self.runtime_error("sandbox", f"Blocked: {reason}")

    def call_builtin(self, fn_name: str, arg_count: int):
        builtin = self.builtins[fn_name]
        expected = builtin.arity
        if isinstance(expected, tuple):
            if arg_count not in expected:
                expected_text = ", ".join(str(value) for value in expected)
                self.runtime_error("call", f"{fn_name} expected {expected_text} args, got {arg_count}")
        elif arg_count != expected:
            self.runtime_error("call", f"{fn_name} expected {expected} args, got {arg_count}")
        args = [self.pop() for _ in range(arg_count)]
        args.reverse()
        # #405: the builtin dispatch site is one of the two chokepoints a guest
        # cannot route around. Only capability-bearing builtins consult the
        # policy — `len` and `push` carry no authority, and making the hottest
        # path in the interpreter pay a policy lookup for them would cost real
        # time for nothing. See BUILTIN_CAPABILITIES.
        _cap = BUILTIN_CAPABILITIES.get(fn_name)
        if _cap is not None:
            self.check_capability(_cap, fn_name, "builtin", args)
        profiler = self.profiler
        if profiler is not None and profiler.enabled:
            profiler.enter_function(fn_name)
            try:
                result = builtin.fn(*args)
            finally:
                profiler.exit_function(fn_name)
        else:
            result = builtin.fn(*args)
        if isinstance(result, SleepRequest):
            self.stack.append(None)
            if self.current_coroutine is None:
                self.runtime_error(
                    "runtime",
                    "sleep(ms) outside coroutine — "
                    "wrap your code in spawn(coroutine(fn() { ... })) and call run_loop()",
                )
            assert self.current_coroutine is not None
            self.current_coroutine.state = "suspended"
            self.save_current_coroutine_state(self.ip + 1)
            return ("yield", {SLEEP_KEY: result.ms})
        if isinstance(result, ChannelRecvRequest):
            return ("yield", {CHANNEL_WAIT_KEY: True})
        if isinstance(result, Record) and result.kind == "error":
            result = self._augment_stdlib_err(result)
        self.stack.append(result)
        return None

    def call_closure(self, callee, arg_count: int):
        """Set up a call frame and transfer control to a closure's bytecode.

        This method does NOT invoke `execute()`.  It modifies VM state (pushes a frame,
        sets `self.ip`) so that the currently running `execute()` loop continues directly
        into the closure's bytecode on its next iteration.  This is how the VM achieves
        efficient function calls without Python-level recursion.

        Upvalue capture:
        - Upvalues are already attached to `callee.upvalues` when the Closure was created
          by the MAKE_CLOSURE opcode.  Each upvalue is a `Cell` object.
        - When the closure reads a captured variable via LOAD_UPVALUE, it reads
          `closure.upvalues[index].value`.
        - When the closure writes via STORE_UPVALUE, it writes `closure.upvalues[index].value`.
        - `Cell` boxing allows two closures capturing the same variable to share one
          Cell, so mutations are visible across all closures that captured it.

        Cell vs direct locals:
        - Variables that are captured by any closure are stored as `Cell` objects in
          the enclosing frame's `locals` dict.
        - Variables that are never captured remain plain values in `locals`.
        - The compiler decides at compile time (via SymbolTable) which variables need
          Cell boxing.  The VM never needs to inspect capture lists at runtime.

        Frame stack and tail calls:
        - Nodus does not implement tail-call elimination.  Every call_closure() pushes
          a new Frame.  Deep recursive programs will eventually hit `max_frames` (if
          configured) or Python's own recursion limit.
        - The frame's `return_ip` is set to `self.ip + 1` (the instruction after the
          CALL opcode), so RETURN knows where to resume the caller.

        Args:
            callee: A Closure value.  Raises a runtime "call" error if not a Closure.
            arg_count: Number of arguments already pushed onto the stack.  Must match
                the closure's declared parameter count.
        """
        if not isinstance(callee, Closure):
            self.runtime_error("call", f"Cannot call non-function: {self.value_to_string(callee, quote_strings=True)}")
        fn = callee.function
        if arg_count != len(fn.params):
            self.runtime_error("call", f"{self.display_name(fn.name)} expected {len(fn.params)} args, got {arg_count}")
        self.guard_step_entry(callee)  # #394: door 1 of 4, never authorized
        call_path, call_line, call_col = self.current_loc()
        frame = Frame(
            return_ip=self.ip + 1,
            locals={},
            fn_name=fn.name,
            call_line=call_line,
            call_col=call_col,
            call_path=call_path,
            closure=callee,
        )
        if fn.local_slots:
            frame.locals_name_to_slot = fn.local_slots
        if self.max_frames is not None and len(self.frames) + 1 > self.max_frames:
            self.runtime_error("sandbox", "Call stack overflow")
        # #691: `fn.addr` indexes the chunk the closure was COMPILED against. If
        # that is not the chunk currently loaded, swap the origin context in for
        # the duration of the frame -- otherwise we jump into unrelated
        # instructions. This is the one place that decides it, because this is
        # the one place that jumps to `fn.addr`.
        origin = self._foreign_closure_origin(callee)
        if origin is not None:
            frame.cross_module_ctx = self._capture_module_ctx()
            self._restore_module_ctx(origin)
        self.frames.append(frame)
        if self.profiler is not None and self.profiler.enabled:
            self.profiler.enter_function(self.display_name(fn.name))
        self.ip = fn.addr

    def run_closure(self, closure, args: list, workflow_context: dict | None = None,
                    step_authorized: bool = False):
        if not isinstance(closure, Closure):
            self.runtime_error("call", "Task expects a function")
        # #394: door 2 of 4. `step_authorized` is passed only by the graph
        # runner's worker path; every other caller of this method -- std:retry,
        # std:test, tool handlers, the iterator protocol -- leaves it False.
        self.guard_step_entry(closure, authorized=step_authorized)
        # #691: the second site that jumps to `fn.addr`, and it asks the same
        # question `call_closure` does. Resolved BEFORE the frames are cleared,
        # because that is where the answer is written down. A builtin handed a
        # callback -- `retry_call`, a tool handler, the iterator protocol --
        # reaches this with whatever chunk the VM happens to be running.
        origin = self._foreign_closure_origin(closure)
        saved_module_ctx = None
        if origin is not None:
            saved_module_ctx = self._capture_module_ctx()
            self._restore_module_ctx(origin)
        ctx = self.save_execution_context()
        try:
            self.stack = []
            self.frames = []
            self.handler_stack = []
            self._deferred_return = _DEFERRED_NONE
            self._deferred_return_depth = 0
            self._deferred_error = _DEFERRED_NONE
            self._deferred_error_depth = 0
            temp_coroutine = Coroutine(closure)
            temp_coroutine.state = "running"
            temp_coroutine.workflow_context = workflow_context
            self.current_coroutine = temp_coroutine
            for arg in args:
                self.stack.append(arg)
            fn = closure.function
            run_frame = Frame(
                return_ip=None,
                locals={},
                fn_name=fn.name,
                call_line=None,
                call_col=None,
                call_path=None,
                closure=closure,
            )
            if fn.local_slots:
                run_frame.locals_name_to_slot = fn.local_slots
            self.frames.append(run_frame)
            if self.profiler is not None and self.profiler.enabled:
                self.profiler.enter_function(self.display_name(fn.name))
            self.ip = fn.addr
            status, result = self.execute()
            if status == "yield":
                self.runtime_error("runtime", "Task yielded during graph execution")
            return result
        finally:
            self.restore_execution_context(ctx)
            if saved_module_ctx is not None:
                self._restore_module_ctx(saved_module_ctx)

    def record_instruction(self) -> None:
        self.instructions_executed += 1
        if self.task_step_budget is not None:
            self.task_step_budget -= 1
            if self.task_step_budget <= 0:
                self._budget_exceeded = True
        if self.deadline is not None:
            if self.instructions_executed - self._last_deadline_check >= self._deadline_check_interval:
                self._last_deadline_check = self.instructions_executed
                if time.monotonic() >= self.deadline:
                    err = RuntimeLimitExceeded("Execution timed out")
                    self.emit_runtime_error(err)
                    raise err
        if self.max_steps is not None and self.instructions_executed > self.max_steps:
            err = RuntimeLimitExceeded("Execution step limit exceeded")
            self.emit_runtime_error(err)
            raise err
        if self.instructions_executed - self._last_batch_emit >= self._instruction_batch_size:
            count = self.instructions_executed - self._last_batch_emit
            # Advanced whether or not the event is emitted: leaving it behind
            # would make the threshold test above true on every subsequent
            # instruction instead of every hundredth.
            self._last_batch_emit = self.instructions_executed
            if self.event_bus.wants("vm_instruction_batch"):
                self.event_bus.emit_event(
                    "vm_instruction_batch",
                    data={"count": float(count), "total": float(self.instructions_executed)},
                )

    # The three sites below ask `event_bus.wants(...)` rather than deciding for
    # themselves (#522). The counters are maintained unconditionally, because
    # `get_execution_stats()` reports them and they are what makes suppressing
    # the per-event detail lossless in aggregate.

    def record_vm_call(self, name: str | None, call_type: str) -> None:
        self.function_calls += 1
        if self.profiler is not None and self.profiler.enabled:
            self.profiler.record_function_call(name)
        if self.event_bus.wants("vm_call"):
            self.event_bus.emit_event(
                "vm_call",
                name=name,
                data={"call_type": call_type, "total": float(self.function_calls)},
            )

    def record_vm_return(self, name: str | None) -> None:
        self.returns += 1
        if self.event_bus.wants("vm_return"):
            self.event_bus.emit_event(
                "vm_return",
                name=name,
                data={"total": float(self.returns)},
            )

    def record_vm_exception(self, err: Exception) -> None:
        self.exceptions += 1
        data: dict[str, Any] = {"total": float(self.exceptions)}
        if isinstance(err, LangRuntimeError):
            data["kind"] = err.kind
            data["message"] = str(err)
        else:
            data["message"] = str(err)
        self.event_bus.emit_event("vm_exception", data=data)

    # ---------------------------------------------------------------------------
    # Opcode handlers — called from execute() via self._dispatch dict
    # ---------------------------------------------------------------------------

    def _op_push_const(self, instr):
        self.stack.append(instr[1])
        self.ip += 1

    def _op_load(self, instr):
        self.stack.append(self.load_name(instr[1]))
        self.ip += 1

    def _op_frame_size(self, instr):
        """Pre-allocate the frame's slot-indexed locals array.

        Emitted as the first instruction of every compiled function body.
        Operand: number of local variable slots needed for this function.
        Stack effect: none.
        """
        n = instr[1]
        self.frames[-1].locals_array = [None] * n
        self.ip += 1

    def _op_load_local(self, instr):
        # LOAD_LOCAL was removed from the VM dispatch table in v1.0.
        # The compiler no longer emits this opcode — all local variable loads
        # use LOAD_LOCAL_IDX (slot-indexed) instead.
        # If this handler is ever reached, it means either:
        #   (a) old cached bytecode (version < 3) bypassed the version check, or
        #   (b) there is a compiler bug emitting LOAD_LOCAL unexpectedly.
        # In both cases, recompiling the source file will fix it.
        name = instr[1] if len(instr) > 1 else "<unknown>"
        raise RuntimeError(
            f"LOAD_LOCAL opcode encountered for variable '{name}' at runtime. "
            f"This opcode was removed in Nodus v1.0. "
            f"Recompile your source to regenerate bytecode using LOAD_LOCAL_IDX. "
            f"If you see this error on freshly compiled source, please file a bug."
        )

    def _op_load_local_idx(self, instr):
        """Slot-indexed fast path for local variable loads.

        Uses frame.locals_array[slot] instead of frame.locals[name], eliminating
        the hash computation from the dict-keyed LOAD_LOCAL path.
        Supersedes LOAD_LOCAL for variables whose slot index is known at compile time.
        """
        slot = instr[1]
        value = self.frames[-1].locals_array[slot]
        if isinstance(value, Cell):
            value = value.value
        elif isinstance(value, LiveBinding):
            value = value.get()
        self.stack.append(value)
        self.ip += 1

    def _op_store_local_idx(self, instr):
        """Slot-indexed fast path for local variable stores.

        Writes value → frame.locals_array[slot]. Handles Cell boxing for
        captured variables (upvalue capture via MAKE_CLOSURE).
        """
        slot = instr[1]
        value = self.pop()
        arr = self.frames[-1].locals_array
        existing = arr[slot]
        if isinstance(existing, Cell):
            existing.value = value
        else:
            arr[slot] = value
        self.ip += 1

    def _op_reset_local_idx(self, instr):
        """Detach any Cell at a local slot by replacing it with a plain None.

        Emitted at the start of each for-loop iteration (for the loop variable)
        and before each `let` binding (for any variable inside a loop body) so
        that MAKE_CLOSURE creates a fresh per-iteration Cell rather than reusing
        the Cell from a previous iteration. No stack effect.
        """
        self.frames[-1].locals_array[instr[1]] = None
        self.ip += 1

    def _op_load_upvalue(self, instr):
        self.stack.append(self.load_upvalue(instr[1]))
        self.ip += 1

    def _op_store(self, instr):
        self.store_name(instr[1], self.pop())
        self.ip += 1

    def _op_store_upvalue(self, instr):
        self.store_upvalue(instr[1], self.pop())
        self.ip += 1

    def _op_store_arg(self, instr):
        name = instr[1]
        value = self.pop()
        locals_ = self.current_locals()
        if locals_ is None:
            self.runtime_error("runtime", "STORE_ARG used without a call frame")
        if name in locals_ and isinstance(locals_[name], Cell):
            locals_[name].value = value
        else:
            locals_[name] = value
        # Also sync parameter value into locals_array for LOAD_LOCAL_IDX access
        frame = self.frames[-1]
        if frame.locals_array is not None and frame.locals_name_to_slot is not None:
            slot = frame.locals_name_to_slot.get(name)
            if slot is not None:
                frame.locals_array[slot] = value
        self.ip += 1

    def _op_pop(self, instr):
        self.pop()
        self.ip += 1

    def _op_add(self, instr):
        b = self.pop()
        a = self.pop()
        try:
            self.stack.append(a + b)
        except TypeError:
            self._binary_type_error("add", a, b)
        self.ip += 1

    def _op_sub(self, instr):
        b = self.pop()
        a = self.pop()
        try:
            self.stack.append(a - b)
        except TypeError:
            self._binary_type_error("subtract", a, b)
        self.ip += 1

    def _op_mul(self, instr):
        b = self.pop()
        a = self.pop()
        try:
            self.stack.append(a * b)
        except TypeError:
            self._binary_type_error("multiply", a, b)
        self.ip += 1

    def _op_div(self, instr):
        b = self.pop()
        a = self.pop()
        a_int = isinstance(a, int) and not isinstance(a, bool)
        b_int = isinstance(b, int) and not isinstance(b, bool)
        if a_int and b_int:
            if b == 0:
                self.runtime_error("math", "Integer division by zero")
            else:
                self.stack.append(a // b)
        elif not isinstance(a, (int, float)) or not isinstance(b, (int, float)):
            self._binary_type_error("divide", a, b)
        else:
            fb = float(b)
            if fb == 0.0:
                self.runtime_error("math", "Float division by zero")
            else:
                self.stack.append(float(a) / fb)
        self.ip += 1

    def _op_mod(self, instr):
        b = self.pop()
        a = self.pop()
        a_int = isinstance(a, int) and not isinstance(a, bool)
        b_int = isinstance(b, int) and not isinstance(b, bool)
        if a_int and b_int:
            if b == 0:
                self.runtime_error("math", "Integer modulo by zero")
            else:
                self.stack.append(a % b)
        elif not isinstance(a, (int, float)) or not isinstance(b, (int, float)):
            self._binary_type_error("modulo", a, b)
        else:
            fb = float(b)
            if fb == 0.0:
                self.runtime_error("math", "Float modulo by zero")
            else:
                self.stack.append(float(a) % fb)
        self.ip += 1

    @staticmethod
    def _nodus_eq(a, b) -> bool:
        """v4.0 equality: numeric coercion (int↔float) only; no bool/str coercions."""
        # Number family: int or float (not bool) — coerce to float for comparison
        a_num = isinstance(a, (int, float)) and not isinstance(a, bool)
        b_num = isinstance(b, (int, float)) and not isinstance(b, bool)
        if a_num and b_num:
            return float(a) == float(b)
        # All other types: exact Python __eq__ — but guard against bool/int subclass
        if isinstance(a, bool) or isinstance(b, bool):
            return type(a) is type(b) and a == b
        return a == b

    def _op_eq(self, instr):
        b = self.pop()
        a = self.pop()
        self.stack.append(self._nodus_eq(a, b))
        self.ip += 1

    def _op_ne(self, instr):
        b = self.pop()
        a = self.pop()
        self.stack.append(not self._nodus_eq(a, b))
        self.ip += 1

    def _op_lt(self, instr):
        b = self.pop()
        a = self.pop()
        try:
            self.stack.append(a < b)
        except TypeError:
            self._compare_type_error(a, b)
        self.ip += 1

    def _op_gt(self, instr):
        b = self.pop()
        a = self.pop()
        try:
            self.stack.append(a > b)
        except TypeError:
            self._compare_type_error(a, b)
        self.ip += 1

    def _op_le(self, instr):
        b = self.pop()
        a = self.pop()
        try:
            self.stack.append(a <= b)
        except TypeError:
            self._compare_type_error(a, b)
        self.ip += 1

    def _op_ge(self, instr):
        b = self.pop()
        a = self.pop()
        try:
            self.stack.append(a >= b)
        except TypeError:
            self._compare_type_error(a, b)
        self.ip += 1

    def _op_jump(self, instr):
        self.ip = instr[1]

    def _op_jump_if_false(self, instr):
        cond = self.pop()
        if not self.is_truthy(cond):
            self.ip = instr[1]
        else:
            self.ip += 1

    def _op_jump_if_true(self, instr):
        cond = self.pop()
        if self.is_truthy(cond):
            self.ip = instr[1]
        else:
            self.ip += 1

    def _make_record_iterator(self, iterator_record: "Record") -> "Iterator":
        """Wrap a Nodus Record (with a ``__next__`` closure) in an ``Iterator``.

        Called by ``_op_get_iter`` for both the ``__iter__``-closure path and the
        ``__next__``-only path.  Each call to ``advance()`` invokes the ``__next__``
        closure synchronously via ``run_closure`` and interprets a ``None`` return
        value as iterator exhaustion.
        """
        def _adv_record(_rec=iterator_record):
            next_fn = _rec.fields["__next__"]
            result = self.run_closure(next_fn, [_rec])
            if result is None:
                return None, True
            return result, False
        return Iterator(_adv_record)

    def _op_get_iter(self, instr):
        value = self.pop()
        if isinstance(value, list):
            # List path: wrap in Iterator with index-based advance.
            list_iter = ListIterator(value)
            def _adv_list(_it=list_iter):
                if _it.index >= len(_it.values):
                    return None, True
                v = _it.values[_it.index]
                _it.index += 1
                return v, False
            self.stack.append(Iterator(_adv_list))
            self.ip += 1
            return None
        if isinstance(value, Record):
            if "__iter__" in value.fields:
                # Call __iter__ synchronously; its return value is the iterator record.
                iterator_fn = value.fields["__iter__"]
                iterator_record = self.run_closure(iterator_fn, [value])
                if isinstance(iterator_record, list):
                    list_iter = ListIterator(iterator_record)
                    def _adv_from_list(_it=list_iter):
                        if _it.index >= len(_it.values):
                            return None, True
                        v = _it.values[_it.index]
                        _it.index += 1
                        return v, False
                    self.stack.append(Iterator(_adv_from_list))
                elif isinstance(iterator_record, Record) and "__next__" in iterator_record.fields:
                    self.stack.append(self._make_record_iterator(iterator_record))
                else:
                    self.runtime_error("type", "__iter__ must return a list or a record with __next__")
                self.ip += 1
                return None
            if "__next__" in value.fields:
                # Record is its own iterator — wrap directly.
                self.stack.append(self._make_record_iterator(value))
                self.ip += 1
                return None
        if isinstance(value, dict):
            self.runtime_error("type", "maps are not directly iterable; use 'for k in keys(m)' to iterate keys or 'for v in values(m)' for values")
        self.runtime_error("type", "Value is not iterable")

    def _op_iter_next(self, instr):
        end_ip = instr[1]
        if not self.stack:
            self.runtime_error("runtime", "ITER_NEXT without iterator")
        iterator = self.stack[-1]
        if isinstance(iterator, Iterator):
            # All paths now produce Iterator objects; advance() is always valid.
            item, exhausted = iterator.advance()
            if exhausted:
                self.stack.pop()
                self.ip = end_ip
            else:
                self.stack.append(item)
                self.ip += 1
        else:
            self.runtime_error("type", "Iterator is not supported")

    def _op_setup_try(self, instr):
        finally_ip = instr[2] if len(instr) > 2 else 0
        self.setup_try(instr[1], finally_ip)
        self.ip += 1

    def _op_pop_try(self, instr):
        finally_ip = self.pop_try()
        if finally_ip != 0:
            self.ip = finally_ip
        else:
            self.ip += 1

    def _op_finally_end(self, instr):
        # Deferred re-raise first, and before touching the handler stack:
        # handle_exception already popped this region's finally-gate, so the top
        # entry now belongs to an enclosing catch and must not be consumed here.
        if self._deferred_error is not _DEFERRED_NONE:
            # The catch block raised and this finally ran on the way out (#361).
            # Cleanup has happened; resume propagation.
            err = self._deferred_error
            self._deferred_error = _DEFERRED_NONE
            if self.handle_exception(err):
                return None
            raise err
        # On the normal catch-exit path (JUMP finally_ip), the finally-gate pushed
        # by handle_exception was not consumed by _op_return. Pop it now so it
        # doesn't pollute the outer handler stack.
        # On the deferred-return path, _op_return already popped the gate.
        if self.handler_stack and self.handler_stack[-1][0] == _FINALLY_GATE:
            self.handler_stack.pop()
        if self._deferred_return is not _DEFERRED_NONE:
            ret_value = self._deferred_return
            self._deferred_return = _DEFERRED_NONE
            if not self.frames:
                self.runtime_error("runtime", "FINALLY_END deferred return outside function")
            frame = self.frames.pop()
            self._profiler_exit_frame(frame)
            self.record_vm_return(self.display_name(frame.fn_name))
            while self.handler_stack and self.handler_stack[-1][3] > len(self.frames):
                self.handler_stack.pop()
            if self.current_coroutine is not None and frame.return_ip is None:
                self.current_coroutine.state = "finished"
                self.current_coroutine.ip = None
                self.current_coroutine.stack = []
                self.current_coroutine.frames = []
                self.current_coroutine.handler_stack = []
                return ("return", ret_value)
            self.stack.append(ret_value)
            self.ip = frame.return_ip
        else:
            self.ip += 1

    def _op_to_bool(self, instr):
        self.stack.append(self.is_truthy(self.pop()))
        self.ip += 1

    def _op_not(self, instr):
        self.stack.append(not self.is_truthy(self.pop()))
        self.ip += 1

    def _op_neg(self, instr):
        value = self.pop()
        try:
            self.stack.append(-value)
        except TypeError:
            self._unary_type_error("negate", value)
        self.ip += 1

    def _op_build_list(self, instr):
        count = instr[1]
        items = [self.pop() for _ in range(count)]
        items.reverse()
        self.stack.append(items)
        self.ip += 1

    def _op_build_map(self, instr):
        count = instr[1]
        pairs = []
        for _ in range(count):
            value = self.pop()
            key = self.pop()
            if not self.is_valid_map_key(key):
                self.runtime_error("type", "Map keys must be strings or numbers")
            pairs.append((key, value))
        pairs.reverse()
        d = {}
        for key, value in pairs:
            d[key] = value
        self.stack.append(d)
        self.ip += 1

    def _op_build_record(self, instr):
        count = instr[1]
        pairs = []
        for _ in range(count):
            value = self.pop()
            key = self.pop()
            if not isinstance(key, str):
                self.runtime_error("type", "Record keys must be strings")
            pairs.append((key, value))
        pairs.reverse()
        fields = {}
        for key, value in pairs:
            fields[key] = value
        self.stack.append(Record(fields))
        self.ip += 1

    def _op_build_module(self, instr):
        count = instr[1]
        pairs = []
        for _ in range(count):
            value = self.pop()
            key = self.pop()
            if not isinstance(key, str):
                self.runtime_error("type", "Module keys must be strings")
            pairs.append((key, value))
        pairs.reverse()
        fields = {}
        for key, value in pairs:
            fields[key] = value
        self.stack.append(Record(fields, kind="module"))
        self.ip += 1

    def _op_index(self, instr):
        idx = self.pop()
        seq = self.pop()
        self.stack.append(self.read_index(seq, idx))
        self.ip += 1

    def _op_index_set(self, instr):
        value = self.pop()
        idx = self.pop()
        seq = self.pop()
        self.stack.append(self.write_index(seq, idx, value))
        self.ip += 1

    def _op_load_field(self, instr):
        name = instr[1]
        obj = self.pop()
        if isinstance(obj, NodusModule):
            if not obj.has_export(name):
                self.runtime_error("key", f"Missing module export: {name}")
            self.stack.append(obj.get_export(name))
            self.ip += 1
            return None
        if not isinstance(obj, Record):
            self.runtime_error("type", "Field access is only supported on records")
        if name not in obj.fields:
            self.runtime_error("key", f"Missing record field: {name}")
        self.stack.append(obj.fields[name])
        self.ip += 1

    def _op_store_field(self, instr):
        name = instr[1]
        value = self.pop()
        obj = self.pop()
        if isinstance(obj, NodusModule):
            if not obj.has_export(name):
                self.runtime_error("key", f"Missing module export: {name}")
            self.stack.append(obj.set_export(name, value))
            self.ip += 1
            return None
        if not isinstance(obj, Record):
            self.runtime_error("type", "Field assignment is only supported on records")
        obj.fields[name] = value
        self.stack.append(value)
        self.ip += 1

    def _op_call(self, instr):
        fn_name = instr[1]
        arg_count = instr[2]

        # Compiler-emitted builtin call site (#411). Checked FIRST, before the
        # user-function lookup below, because that ordering is the whole bug: an
        # annotation or workflow lowering that resolves through normal scoping lets
        # the program supply the machinery the compiler injected into its own code.
        #
        # The prefix cannot appear in source — `Compiler.reject_reserved_name`
        # refuses it — so reaching here means the compiler emitted it.
        #
        # Resolved here rather than pre-aliased into `self.builtins` at construction
        # so there is no ordering dependency: builtins merged later (host builtins,
        # module loading) are reachable too. Measured cost of the added `startswith`
        # is ~81 ns/call — 0.08% of a call-heavy loop, i.e. immaterial. An earlier
        # reading of ~8% was machine noise; this box's timing instability is
        # documented in CLAUDE.md and was active during the measurement.
        if fn_name.startswith(BUILTIN_CALL_PREFIX):
            builtin_name = fn_name[len(BUILTIN_CALL_PREFIX):]
            self.record_vm_call(builtin_name, "call")
            if builtin_name in self.builtins:
                status = self.call_builtin(builtin_name, arg_count)
                if status is not None:
                    return status
                self.ip += 1
                return None
            # Only reachable if a lowering names a builtin this VM lacks. Name the
            # builtin, not the mangled call site.
            self.runtime_error(
                "name",
                f"Undefined function: {builtin_name} "
                "(required by a compiler-generated call)",
            )

        self.record_vm_call(self.display_name(fn_name), "call")

        if fn_name in self.functions:
            fn = self.functions[fn_name]
            if arg_count != len(fn.params):
                self.runtime_error("call", f"{fn_name} expected {len(fn.params)} args, got {arg_count}")
            if fn.upvalues:
                self.runtime_error("call", f"{self.display_name(fn_name)} requires a closure")
            call_path, call_line, call_col = self.current_loc()
            frame = Frame(
                return_ip=self.ip + 1,
                locals={},
                fn_name=fn_name,
                call_line=call_line,
                call_col=call_col,
                call_path=call_path,
                closure=None,
            )
            if fn.local_slots:
                frame.locals_name_to_slot = fn.local_slots
            if self.max_frames is not None and len(self.frames) + 1 > self.max_frames:
                self.runtime_error("sandbox", "Call stack overflow")
            self.frames.append(frame)
            if self.profiler is not None and self.profiler.enabled:
                self.profiler.enter_function(self.display_name(fn_name))
            self.ip = fn.addr
            return None  # pending_after set by execute()

        if fn_name in self.builtins:
            status = self.call_builtin(fn_name, arg_count)
            if status is not None:
                return status  # yield/channel tuple — propagate to execute() caller
            self.ip += 1
            return None

        locals_ = self.current_locals()
        if (locals_ is not None and fn_name in locals_) or fn_name in self.globals:
            callee = self.load_name(fn_name)
            if isinstance(callee, ModuleFunction):
                args = [self.pop() for _ in range(arg_count)]
                args.reverse()
                self.stack.append(callee.module.invoke_function(callee.name, args, caller_vm=self))
                self.ip += 1
                return None
            self.call_closure(callee, arg_count)
            return None
        self.runtime_error("name", f"Undefined function: {fn_name}{self.extern_hint(fn_name)}")

    def _op_call_value(self, instr):
        arg_count = instr[1]
        args = [self.pop() for _ in range(arg_count)]
        args.reverse()
        callee = self.pop()
        call_name = callee.function.display_name if isinstance(callee, Closure) else None
        self.record_vm_call(call_name, "call_value")
        if isinstance(callee, ModuleFunction):
            self.stack.append(callee.module.invoke_function(callee.name, args, caller_vm=self))
            self.ip += 1
            return None
        if isinstance(callee, _ClosureProxy):
            # #339: inside a coroutine, run it in this loop so it can suspend.
            if self._try_enter_foreign_closure(callee.origin_ctx,
                                               callee._proxied_closure, args):
                return None
            self.stack.append(callee(*args))
            self.ip += 1
            return None
        if self._caller_vm is not None and self._is_foreign_closure(callee):
            # ASYNC-MOD-003: a caller closure that reached this module VM nested
            # inside a container (list/map/record) was never wrapped in a
            # _ClosureProxy, so its fn.addr points into the *caller's* bytecode.
            # Executing it here would run the module's instructions at that
            # address (Stack underflow / NoneType errors). Dispatch it back
            # through the caller VM, exactly as a proxy would.
            if self._try_enter_foreign_closure(self._caller_module_ctx(), callee, args):
                return None
            self.stack.append(self._caller_vm.run_closure(callee, args))
            self.ip += 1
            return None
        for arg in args:
            self.stack.append(arg)
        self.call_closure(callee, arg_count)
        return None

    def _caller_module_ctx(self):
        """The calling VM's module context, or None when there is no caller."""
        caller = self._caller_vm
        return caller._capture_module_ctx() if caller is not None else None

    def _try_enter_foreign_closure(self, origin_ctx, closure, args: list) -> bool:
        """Run a closure from another chunk IN THIS LOOP, not a nested one.

        The fallback for a foreign closure is ``caller_vm.run_closure``, which
        starts a nested ``execute()``. That works for synchronous callbacks and
        fails for anything that suspends: a ``worker_pool`` worker calling
        ``async.sleep`` died with "Task yielded during graph execution", because
        the yield had nowhere to go (#339). Async primitives whose callbacks
        cannot await are of little use.

        Pushing a frame with the closure's own context swapped in keeps execution
        in the current coroutine's loop, so a yield reaches the scheduler as it
        would from any other code. ``frame.cross_module_ctx`` restores the
        context on return and on unwind — the same mechanism
        ``_try_enter_module_call`` uses in the other direction.

        Returns False (caller falls back) outside a scheduler-managed coroutine,
        without an origin context, or on arity mismatch — ``run_closure`` owns
        the canonical arity error.
        """
        if origin_ctx is None:
            return False
        scheduler = getattr(self, "scheduler", None)
        coroutine = self.current_coroutine
        if (coroutine is None or scheduler is None
                or coroutine is not getattr(scheduler, "current_task", None)):
            return False
        fn_info = getattr(closure, "function", None)
        if fn_info is None or len(args) != len(fn_info.params):
            return False
        self.guard_step_entry(closure)  # #394: door 3 of 4, never authorized

        saved = self._capture_module_ctx()
        self._restore_module_ctx(origin_ctx)
        if self.max_frames is not None and len(self.frames) + 1 > self.max_frames:
            self._restore_module_ctx(saved)
            self.runtime_error("sandbox", "Call stack overflow")
        frame = Frame(
            return_ip=self.ip + 1,
            locals={},
            fn_name=fn_info.name,
            call_line=None,
            call_col=None,
            call_path=None,
            closure=closure,
        )
        frame.cross_module_ctx = saved
        if fn_info.local_slots:
            frame.locals_name_to_slot = fn_info.local_slots
        self.frames.append(frame)
        for arg in args:
            self.stack.append(arg)
        self.ip = fn_info.addr
        return True

    def _is_foreign_closure(self, callee) -> bool:
        """True if ``callee`` is a Closure compiled against a different chunk.

        A closure is local to the running chunk when its FunctionInfo is the one
        registered under its name in ``self.functions`` — including mangled
        anonymous entries such as ``__anon_1__fn2``. Identity, not the name: two
        chunks routinely both hold an ``__anon_1``.
        """
        # `call_closure` runs this on every value call, so it stays free of
        # `getattr` defaults: `Closure` always carries a `FunctionInfo`, and a
        # `FunctionInfo` always carries a name.
        if not isinstance(callee, Closure):
            return False
        fn_info = callee.function
        return self.functions.get(fn_info.name) is not fn_info

    def _foreign_closure_origin(self, callee):
        """The context ``callee`` must run in, or None when it is already loaded.

        A ``Closure`` is an address plus upvalues, and the address means nothing
        without the chunk it was compiled against. The VM runs someone else's
        chunk in two situations, and #691 is what it cost to answer this in only
        one of them:

        * a **detached module VM** (``invoke_function``), where the caller lives
          in another VM entirely — its arguments are wrapped in ``_ClosureProxy``
          on the way in, and the proxy carries the context;
        * a **cross-module frame in this same VM** (``_try_enter_module_call``,
          the #105 fast path taken inside a scheduler coroutine), where nothing
          was wrapped and nothing was checked. A workflow step body always takes
          this path, which is why `m.f(fn() { ... })` ran the module's
          instructions at the callback's address — silently, because a short
          module chunk simply ran off its end and halted.

        The frame walk asks which saved context *owns* this FunctionInfo rather
        than taking the nearest one. Nearest is wrong as soon as a closure is
        passed through two modules: with ``main -> outer.forward(f) ->
        inner.run_it(f)``, the innermost boundary saved `outer`, and `f` was
        compiled in `main`. Ownership is identity on the ``functions`` table, so
        it names the right frame however many boundaries the value crossed, and
        it costs nothing on the common path -- a local closure never gets here.

        **#696 is the same question in the other direction**: a closure a module
        *returned*. Every source above records a context that a call is still
        inside of, and by the time the returned closure is called there is no
        such context — the proxy was for an argument, the cross-module frame has
        been popped, and there is no caller VM. Nothing marks the value on the
        way out.

        Marking it would mean a hook at each exit, and closures also leave
        nested in lists, maps and records — which is exactly the case #339 found
        the *entry* side had missed. So the resolution is ownership again, over
        the modules this VM can see rather than over its frames: a module holds
        its `functions` table for its whole life, so the answer is available
        long after every frame is gone, and it needs no mark, no walk of
        returned containers, and no new module-scope registry.

        Returns None when nothing claims the closure, which leaves the call to
        behave as it did before this existed.
        """
        if not self._is_foreign_closure(callee):
            return None
        # A `_ClosureProxy` was wrapped at the boundary it crossed and carries
        # the exact context; prefer it over any inference.
        origin = getattr(callee, "origin_ctx", None)
        if origin is not None:
            return origin
        fn_info = callee.function
        for frame in reversed(self.frames):
            saved = getattr(frame, "cross_module_ctx", None)
            if saved is not None and self._ctx_functions(saved).get(fn_info.name) is fn_info:
                return saved
        if self._caller_vm is not None:
            return self._caller_module_ctx()
        module = self._module_owning(fn_info)
        if module is not None:
            return self.module_ctx(module)
        return None

    def _module_owning(self, fn_info):
        """The loaded module whose `functions` table holds ``fn_info``, or None.

        Breadth-first over the `NodusModule` values this VM can reach: the ones
        its own namespaces bind, then the ones *those* modules bind, so a
        closure returned from a transitively imported module is found too
        (`main` imports `outer`, `outer` imports `inner`, and only `outer` is
        bound here).

        Reachability, deliberately, rather than a process-wide registry of every
        module ever loaded. A global would be the module-scope-state shape that
        produced #185 and #390 — shared by every participant in the process —
        and it would let one tenant's VM resolve another's chunk. What a program
        can call, it can see.

        Only reached for a closure already known foreign, which is rare; the
        common path never gets here.
        """
        seen: set[int] = set()
        queue: list[NodusModule] = []

        def enqueue(namespace) -> None:
            for value in namespace.values():
                if isinstance(value, NodusModule) and id(value) not in seen:
                    seen.add(id(value))
                    queue.append(value)

        enqueue(self.module_globals)
        enqueue(self.host_globals)
        index = 0
        while index < len(queue):
            module = queue[index]
            index += 1
            if module.functions.get(getattr(fn_info, "name", None)) is fn_info:
                return module
            enqueue(module.globals)
        return None

    def module_ctx(self, module) -> tuple:
        """A module's execution context, in `_capture_module_ctx` layout.

        One definition, consulted by both places that need to *be* a module:
        `_try_enter_module_call` on the way in, and `_foreign_closure_origin`
        for a closure the module handed back. Two hand-built copies of this
        tuple would be two answers to "what is this module's context", which is
        the shape this file keeps getting bitten by.
        """
        version, instructions = normalize_bytecode(module.bytecode)
        builtins = self.builtins
        if getattr(module, "host_builtins", None):
            builtins = {**builtins, **module.host_builtins}
        host_globals = self.host_globals
        if getattr(module, "host_globals", None) is not None:
            host_globals = module.host_globals
        return (
            instructions,
            module.functions,
            module.globals,
            module.globals,
            module.code_locs or [(None, None, None)] * len(instructions),
            module.path,
            builtins,
            host_globals,
            version,
        )

    def _op_make_closure(self, instr):
        fn_name = instr[1]
        if fn_name not in self.functions:
            self.runtime_error("runtime", f"Unknown function for closure: {fn_name}")
        fn = self.functions[fn_name]
        upvalues = []
        for upvalue in fn.upvalues:
            if upvalue.is_local:
                if not self.frames:
                    self.runtime_error("runtime", "Closure capture without frame")
                cell = self.capture_local(self.frames[-1], upvalue.name)
            else:
                if not self.frames or self.frames[-1].closure is None:
                    self.runtime_error("runtime", "Closure capture missing outer closure")
                cell = self.frames[-1].closure.upvalues[upvalue.index]
            upvalues.append(cell)
        self.stack.append(Closure(fn, upvalues))
        self.ip += 1

    def _capture_module_ctx(self):
        """Snapshot the current module execution context (ASYNC-MOD-001)."""
        return (self.code, self.functions, self.module_globals, self.globals,
                self.code_locs, self.source_path, self.builtins,
                self.host_globals, self.bytecode_version)

    @staticmethod
    def _ctx_functions(saved) -> dict:
        """The ``functions`` table of a context captured by `_capture_module_ctx`.

        Named here, beside the tuple it indexes, so the layout is stated once.
        """
        return saved[1]

    def _restore_module_ctx(self, saved) -> None:
        """Restore a module context captured by _capture_module_ctx."""
        (self.code, self.functions, self.module_globals, self.globals,
         self.code_locs, self.source_path, self.builtins,
         self.host_globals, self.bytecode_version) = saved

    def _try_enter_module_call(self, module, name: str, args: list) -> bool:
        """Dispatch a module function IN THE CALLER VM instead of a detached VM.

        ASYNC-MOD-001 (#105): module functions were dispatched via
        ``invoke_function``, which spins up a fresh VM and calls ``run_closure``;
        that VM's ``execute`` raises on yield, so async builtins (``http_get_async``,
        ``subprocess_run_async``) inside a stdlib wrapper (e.g. ``http.get_async``)
        fall back to synchronous execution and lose concurrency.

        When we are inside a scheduler-managed coroutine, run the module function
        in the *current* VM by swapping in the module's compiled context and
        pushing a cross-module frame. Execution stays in the same coroutine and
        the same ``execute`` loop, so a ``ChannelRecvRequest`` yield from an async
        builtin propagates to the scheduler and overlaps. The saved context is
        restored when the frame pops (see _op_return / handle_exception).

        Returns True if the cross-module frame was set up (caller must return),
        or False to fall back to ``invoke_function`` (unchanged behavior outside
        a coroutine, for unknown functions, or on arity mismatch).
        """
        scheduler = getattr(self, "scheduler", None)
        coroutine = self.current_coroutine
        if (coroutine is None or scheduler is None
                or coroutine is not getattr(scheduler, "current_task", None)):
            return False
        functions = getattr(module, "functions", None)
        if not functions or name not in functions:
            return False
        fn_info = functions[name]
        expected = len(fn_info.params)
        if len(args) > expected:
            return False  # let invoke_function raise the canonical arity error
        padded = list(args) + [None] * (expected - len(args))

        saved = self._capture_module_ctx()
        # #696: `module_ctx` is the one definition of what it means to *be* this
        # module, shared with `_foreign_closure_origin` so entering a module and
        # re-entering a closure it returned cannot drift apart.
        self._restore_module_ctx(self.module_ctx(module))

        if self.max_frames is not None and len(self.frames) + 1 > self.max_frames:
            self._restore_module_ctx(saved)
            self.runtime_error("sandbox", "Call stack overflow")
        closure = Closure(fn_info, [])
        frame = Frame(
            return_ip=self.ip + 1,
            locals={},
            fn_name=fn_info.name,
            call_line=None,
            call_col=None,
            call_path=None,
            closure=closure,
        )
        frame.cross_module_ctx = saved
        if fn_info.local_slots:
            frame.locals_name_to_slot = fn_info.local_slots
        self.frames.append(frame)
        for arg in padded:
            self.stack.append(arg)
        self.ip = fn_info.addr
        return True

    def _op_call_method(self, instr):
        name = instr[1]
        arg_count = instr[2]
        args = [self.pop() for _ in range(arg_count)]
        args.reverse()
        obj = self.pop()
        if isinstance(obj, NodusModule):
            if not obj.has_export(name):
                self.runtime_error("key", f"Missing module export: {name}")
            method = obj.get_export(name)
            self.record_vm_call(name, "call_method")
            if isinstance(method, ModuleFunction):
                # ASYNC-MOD-001 (#105): run in-VM when inside a coroutine so async
                # builtins in the module function can overlap; else fall back.
                if self._try_enter_module_call(method.module, method.name, args):
                    return None
                self.stack.append(method.module.invoke_function(method.name, args, caller_vm=self))
                self.ip += 1
                return None
            for arg in args:
                self.stack.append(arg)
            self.call_closure(method, arg_count)
            return None
        if not isinstance(obj, Record):
            self.runtime_error("type", "Method calls are only supported on records")
        if name not in obj.fields:
            self.runtime_error("key", f"Missing record field: {name}")
        method = obj.fields[name]
        self.record_vm_call(name, "call_method")
        if isinstance(method, BuiltinMethod):
            result = method._fn(*args)
            # ASYNC-MOD-001: a method-style builtin (e.g. handle.wait_async)
            # may return a suspend sentinel — propagate it as a yield like
            # call_builtin does, instead of pushing it as a value.
            if isinstance(result, SleepRequest):
                self.stack.append(None)
                if self.current_coroutine is None:
                    self.runtime_error(
                        "runtime",
                        "sleep(ms) outside coroutine — "
                        "wrap your code in spawn(coroutine(fn() { ... })) and call run_loop()",
                    )
                self.current_coroutine.state = "suspended"
                self.save_current_coroutine_state(self.ip + 1)
                return ("yield", {SLEEP_KEY: result.ms})
            if isinstance(result, ChannelRecvRequest):
                return ("yield", {CHANNEL_WAIT_KEY: True})
            if isinstance(result, Record) and result.kind == "error":
                result = self._augment_stdlib_err(result)
            self.stack.append(result)
            self.ip += 1
            return None
        if isinstance(method, ModuleFunction):
            if self._try_enter_module_call(method.module, method.name, args):
                return None
            self.stack.append(method(*args))
            self.ip += 1
            return None
        if obj.kind != "module":
            self.stack.append(obj)
            for arg in args:
                self.stack.append(arg)
            self.call_closure(method, arg_count + 1)
        else:
            for arg in args:
                self.stack.append(arg)
            self.call_closure(method, arg_count)
        return None

    def _op_throw(self, instr):
        # _op_throw: preserve structured values (records, lists) as payload
        # rather than stringifying. Strings become message directly.
        # Primitives (int/float/bool) are converted to string message.
        # Structured values are stored in err.payload in the catch block.
        # See TECH_DEBT.md — was previously always stringifying.
        value = self.pop()
        if isinstance(value, str):
            self.runtime_error("thrown", value, origin="user")
        elif isinstance(value, (int, float, bool)):
            self.runtime_error("thrown", self.value_to_string(value), origin="user")
        else:
            # Structured throw (Record, list, etc.): preserve as payload.
            # The catch block receives err where err.kind == "thrown",
            # err.message is the string form, and err.payload is the original value.
            message = self.value_to_string(value, quote_strings=False)
            self.runtime_error("thrown", message, payload=value, origin="user")

    def _op_yield(self, instr):
        value = self.pop()
        if self.current_coroutine is None:
            self.runtime_error("runtime", "yield outside coroutine")
        self.current_coroutine.state = "suspended"
        self.save_current_coroutine_state(self.ip + 1)
        return ("yield", value)

    def _op_return(self, instr):
        ret_value = self.pop()
        if not self.frames:
            self.runtime_error("runtime", "RETURN outside function")
        # If a finally block is pending in the current frame, defer the return.
        if (self.handler_stack and
                self.handler_stack[-1][3] == len(self.frames) and
                self.handler_stack[-1][1] != 0):
            _, finally_ip, _, _ = self.handler_stack.pop()
            self._deferred_return = ret_value
            self._deferred_return_depth = len(self.handler_stack)
            self.ip = finally_ip
            return
        frame = self.frames.pop()
        if frame.cross_module_ctx is not None:
            self._restore_module_ctx(frame.cross_module_ctx)  # ASYNC-MOD-001: restore caller module context
        self._profiler_exit_frame(frame)
        self.record_vm_return(self.display_name(frame.fn_name))
        while self.handler_stack and self.handler_stack[-1][3] > len(self.frames):
            self.handler_stack.pop()
        if self.current_coroutine is not None and frame.return_ip is None:
            self.current_coroutine.state = "finished"
            self.current_coroutine.ip = None
            self.current_coroutine.stack = []
            self.current_coroutine.frames = []
            self.current_coroutine.handler_stack = []
            return ("return", ret_value)
        self.stack.append(ret_value)
        self.ip = frame.return_ip

    def _op_halt(self, instr):
        return ("halt", None)

    def _build_dispatch_table(self) -> dict:
        """Build the opcode -> handler mapping used by execute().

        Dict dispatch is O(1) vs O(n) for the if/elif chain, giving a measurable
        speedup for compute-heavy workloads.

        Benchmark (2026-03-15):
          Before (if/elif): 388ms
          After  (dict):    260ms
          Improvement:      33%
        """
        return {
            "PUSH_CONST":   self._op_push_const,
            "FRAME_SIZE":   self._op_frame_size,
            "LOAD":         self._op_load,
            "LOAD_LOCAL_IDX": self._op_load_local_idx,
            "LOAD_UPVALUE":   self._op_load_upvalue,
            "STORE":          self._op_store,
            "STORE_LOCAL_IDX":self._op_store_local_idx,
            "RESET_LOCAL_IDX":self._op_reset_local_idx,
            "STORE_UPVALUE":self._op_store_upvalue,
            "STORE_ARG":    self._op_store_arg,
            "POP":          self._op_pop,
            "ADD":          self._op_add,
            "SUB":          self._op_sub,
            "MUL":          self._op_mul,
            "DIV":          self._op_div,
            "MOD":          self._op_mod,
            "EQ":           self._op_eq,
            "NE":           self._op_ne,
            "LT":           self._op_lt,
            "GT":           self._op_gt,
            "LE":           self._op_le,
            "GE":           self._op_ge,
            "JUMP":         self._op_jump,
            "JUMP_IF_FALSE":self._op_jump_if_false,
            "JUMP_IF_TRUE": self._op_jump_if_true,
            "GET_ITER":     self._op_get_iter,
            "ITER_NEXT":    self._op_iter_next,
            "SETUP_TRY":    self._op_setup_try,
            "POP_TRY":      self._op_pop_try,
            "FINALLY_END":  self._op_finally_end,
            "TO_BOOL":      self._op_to_bool,
            "NOT":          self._op_not,
            "NEG":          self._op_neg,
            "BUILD_LIST":   self._op_build_list,
            "BUILD_MAP":    self._op_build_map,
            "BUILD_RECORD": self._op_build_record,
            "BUILD_MODULE": self._op_build_module,
            "INDEX":        self._op_index,
            "INDEX_SET":    self._op_index_set,
            "LOAD_FIELD":   self._op_load_field,
            "STORE_FIELD":  self._op_store_field,
            "CALL":         self._op_call,
            "CALL_VALUE":   self._op_call_value,
            "MAKE_CLOSURE": self._op_make_closure,
            "CALL_METHOD":  self._op_call_method,
            "THROW":        self._op_throw,
            "YIELD":        self._op_yield,
            "RETURN":       self._op_return,
            "HALT":         self._op_halt,
        }

    def execute(self):
        """Run bytecode from the current instruction pointer until the program ends or a
        suspend signal is returned.

        Stack discipline
        ----------------
        At entry the stack may be non-empty if this call resumes a coroutine that was
        previously suspended by YIELD.  At a clean program exit (HALT or end-of-code)
        the stack is typically empty.  At a coroutine suspend (YIELD) the full stack
        is snapshotted into the Coroutine object and the value passed to YIELD is
        returned to the caller.

        Frame layout
        ------------
        `self.frames` is a stack of Frame objects.  Each Frame holds:
        - `return_ip`: instruction address to resume after RETURN (None for coroutine
          entry frames — a RETURN with return_ip=None signals coroutine completion).
        - `locals_`: variable dict for the current function scope.
        - `fn_name`: internal name used for stack-trace display.
        - `call_line/call_col/call_path`: source location of the call site.
        - `closure`: the Closure object if this frame runs a closure (None for plain
          functions defined at module top-level with no captured variables).

        Frames are pushed by CALL / CALL_VALUE / CALL_METHOD / call_closure() and
        popped by RETURN.

        Coroutine suspend/resume protocol
        ----------------------------------
        Handlers return a `(status, value)` tuple to signal out-of-band events:
        - `("yield", value)`: YIELD opcode — coroutine suspends.  The scheduler receives
          `value` as the yielded payload.
        - `("yield", {"__task_step_budget__": True})`: scheduler budget exhausted — the
          task is re-enqueued for fair-sharing.
        - `("return", value)`: coroutine's entry frame returned — coroutine finished.
          `value` is the final return value.
        - `("halt", None)`: HALT opcode or end of bytecode — program terminates.

        Dispatch table
        --------------
        Each opcode is looked up in `self._dispatch` (built by `_build_dispatch_table()`
        at construction time).  Unknown opcodes raise a runtime error immediately.
        Handlers return None (normal advance) or a (status, value) tuple (suspend / halt).
        """
        pending_after = None
        while self.ip < len(self.code):
            if self._budget_exceeded:
                self._budget_exceeded = False
                self.task_step_budget = None
                if self.current_coroutine is not None:
                    self.current_coroutine.state = "suspended"
                    self.save_current_coroutine_state(self.ip)
                return ("yield", {"__task_step_budget__": True})
            if self.debug and self.debugger is not None and pending_after is not None:
                self.debugger.after_instruction(self, pending_after)
                pending_after = None

            instr = self.code[self.ip]
            op = instr[0]
            if self.profiler is not None and self.profiler.enabled:
                self.profiler.record_opcode(op)
            if self.debug and self.debugger is not None:
                self.debugger.before_instruction(self, instr)
            self.record_instruction()
            if self.trace and self.should_trace(instr):
                print(self.format_trace(instr), file=sys.stderr)
                self.trace_count += 1
            try:
                handler = self._dispatch.get(op)
                if handler is None:
                    self.runtime_error("runtime", f"Unknown opcode: {op}")
                rv = handler(instr)
                if rv is None:
                    pending_after = instr
                else:
                    return rv  # (status, result) from YIELD / RETURN / HALT
            except LangRuntimeError as _e:
                self.record_vm_exception(_e)
                self.emit_runtime_error(_e)
                if self.handle_exception(_e):
                    continue
                raise
            except HostFunctionError:
                raise
            except Exception as _e:
                self.record_vm_exception(_e)
                wrapped = self.build_runtime_error("runtime", str(_e))
                self.emit_runtime_error(wrapped)
                if self.handle_exception(wrapped):
                    continue
                raise wrapped

        return ("halt", None)

    def run(self):
        self.execute()

    def should_trace(self, instr: tuple) -> bool:
        if self.trace_limit is not None and self.trace_count >= self.trace_limit:
            return False
        if self.trace_filter is None:
            return True
        op = instr[0]
        current_fn = self.frames[-1].fn_name if self.frames else "<main>"
        loc = self.current_loc()
        haystack = f"{self.display_name(current_fn)} {op} {self.format_loc(loc)}"
        return self.trace_filter in haystack

    def _trace_context(self, instr: tuple) -> str:
        op = instr[0]
        if op == "CALL" and len(instr) > 1:
            return f"fn={self.display_name(str(instr[1]))}"
        if op in {"LOAD", "STORE"} and len(instr) > 1:
            return f"name={instr[1]}"
        if op in {"LOAD_FIELD", "STORE_FIELD"} and len(instr) > 1:
            return f"field={instr[1]}"
        if op == "PUSH_CONST" and len(instr) > 1:
            return f"val={instr[1]!r}"
        if op == "JUMP" and len(instr) > 1:
            return f"target={instr[1]}"
        return ""

    def format_trace(self, instr: tuple) -> str:
        op = instr[0]
        op_padded = op.ljust(14)
        if self.trace_no_loc:
            ctx = self._trace_context(instr)
            if ctx:
                return f"[trace] {op_padded}  {ctx}"
            return f"[trace] {op}"
        _, line, _ = self.current_loc()
        line_str = f"line {line}" if line is not None else "line ?"
        ctx = self._trace_context(instr)
        if ctx:
            return f"[trace] {op_padded}  {line_str}  {ctx}"
        return f"[trace] {op_padded}  {line_str}"



