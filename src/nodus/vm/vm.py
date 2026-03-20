"""Stack VM runtime for Nodus."""

import os
import time
from dataclasses import dataclass

from nodus.runtime.coroutine import Coroutine
from nodus.runtime.channel import Channel, ChannelRecvRequest
from nodus.orchestration.task_graph import TaskNode, TaskGraph, run_task_graph, plan_graph, resume_graph, load_graph_state, get_registered_graph
from nodus.builtins.nodus_builtins import BUILTIN_NAMES, BuiltinInfo
from nodus.builtins import BuiltinRegistry
from nodus.compiler.compiler import FunctionInfo, normalize_bytecode
from nodus.runtime.diagnostics import LangRuntimeError, RuntimeLimitExceeded
from nodus.services.agent_runtime import available_agents, call_agent, describe_agent
from nodus.services.memory_runtime import GLOBAL_MEMORY_STORE, MemoryStore, delete_value, get_value, list_keys, put_value
from nodus.runtime.runtime_stats import runtime_time_ms, scheduler_stats, task_snapshot
from nodus.runtime.runtime_events import RuntimeEventBus
from nodus.vm.runtime_values import is_json_safe, payload_keys
from nodus.runtime.scheduler import Scheduler, SleepRequest, SLEEP_KEY, CHANNEL_WAIT_KEY
from nodus.runtime.profiler import Profiler
from nodus.runtime.module import LiveBinding, ModuleFunction, NodusModule
from nodus.services.tool_runtime import available_tools, call_tool, describe_tool
from nodus.orchestration.workflow_lowering import find_goal_value, find_workflow_value, is_goal_value, is_workflow_value, workflow_to_graph
from nodus.orchestration.workflow_state import checkpoints_public


_DEFERRED_NONE = object()  # sentinel: no deferred return pending


class Cell:
    def __init__(self, value=None):
        self.value = value


class Closure:
    def __init__(self, function: FunctionInfo, upvalues: list[Cell]):
        self.function = function
        self.upvalues = upvalues


class _ClosureProxy(Closure):
    """Wraps a Closure so it can be called from a foreign-bytecode VM context.

    When a module function receives a user-defined closure as an argument and
    calls it via CALL_VALUE, the closure's ``fn.addr`` refers to an instruction
    index in the *caller's* bytecode — not the module's.  Wrapping the closure
    in a ``_ClosureProxy`` lets ``_op_call_value`` dispatch the call back
    through ``caller_vm.run_closure`` instead of executing at the wrong
    address in the module VM.

    Inherits from ``Closure`` so that ``isinstance(proxy, Closure)`` checks
    in the VM's reflection builtins behave transparently.
    """

    def __init__(self, closure: Closure, caller_vm: "VM"):
        super().__init__(closure.function, closure.upvalues)
        self._proxied_closure = closure
        self.caller_vm = caller_vm

    def __call__(self, *args):
        return self.caller_vm.run_closure(self._proxied_closure, list(args))


class Record:
    def __init__(self, fields: dict[str, object], kind: str = "record"):
        self.fields = fields
        self.kind = kind

    def __repr__(self) -> str:
        inner = ", ".join(f"{k}: {v!r}" for k, v in self.fields.items())
        return f"Record({{{inner}}})"


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


@dataclass
class Frame:
    return_ip: int | None
    locals: dict
    fn_name: str
    call_line: int | None
    call_col: int | None
    call_path: str | None
    closure: Closure | None = None
    locals_array: list | None = None         # pre-allocated by FRAME_SIZE; slot-indexed locals
    locals_name_to_slot: dict | None = None  # name → slot; set from fn.local_slots at call time


class VM:
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
        self.source_code: str | None = None
        self.trace = trace
        self.trace_no_loc = trace_no_loc
        self.trace_filter = trace_filter
        self.trace_limit = trace_limit
        self.trace_count = 0
        self.debug = debug or debugger is not None
        self.debugger = debugger
        self.handler_stack: list[tuple[int, int, int, int]] = []
        self._deferred_return = _DEFERRED_NONE
        self.current_coroutine: Coroutine | None = None
        self.scheduler = Scheduler(self, trace=trace_scheduler, trace_output=scheduler_output)
        self.event_bus = event_bus or RuntimeEventBus()
        self.profiler = profiler
        self.allowed_paths = self._normalize_allowed_paths(allowed_paths)
        self.memory_store = GLOBAL_MEMORY_STORE
        self.session_id: str | None = None
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
        self.max_frames: int | None = None
        self.max_steps: int | None = None
        self.deadline: float | None = None
        self.trace_scheduler = trace_scheduler
        self.scheduler_output = scheduler_output
        self._task_counter = 0
        self.last_graph_plan: dict | None = None
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
            "run_workflow": BuiltinInfo("run_workflow", 1, self.builtin_run_workflow),
            "plan_workflow": BuiltinInfo("plan_workflow", 1, self.builtin_plan_workflow),
            "resume_workflow": BuiltinInfo("resume_workflow", (1, 2), self.builtin_resume_workflow),
            "run_goal": BuiltinInfo("run_goal", 1, self.builtin_run_goal),
            "plan_goal": BuiltinInfo("plan_goal", 1, self.builtin_plan_goal),
            "resume_goal": BuiltinInfo("resume_goal", (1, 2), self.builtin_resume_goal),
            "workflow_state": BuiltinInfo("workflow_state", 0, self.builtin_workflow_state),
            "workflow_checkpoints": BuiltinInfo("workflow_checkpoints", 1, self.builtin_workflow_checkpoints),
            "current_workflow_id": BuiltinInfo("current_workflow_id", 0, self.builtin_current_workflow_id),
            "emit": BuiltinInfo("emit", (1, 2), self.builtin_emit),
            "tool_call": BuiltinInfo("tool_call", 2, self.builtin_tool_call),
            "tool_available": BuiltinInfo("tool_available", 0, self.builtin_tool_available),
            "tool_describe": BuiltinInfo("tool_describe", 1, self.builtin_tool_describe),
            "memory_get": BuiltinInfo("memory_get", 1, self.builtin_memory_get),
            "memory_put": BuiltinInfo("memory_put", 2, self.builtin_memory_put),
            "memory_delete": BuiltinInfo("memory_delete", 1, self.builtin_memory_delete),
            "memory_keys": BuiltinInfo("memory_keys", 0, self.builtin_memory_keys),
            "recall": BuiltinInfo("recall", (0, 1, 2, 3), self.builtin_recall),
            "remember": BuiltinInfo("remember", (1, 2, 3), self.builtin_remember),
            "suggest": BuiltinInfo("suggest", (0, 1, 2), self.builtin_suggest),
            "record_outcome": BuiltinInfo("record_outcome", 2, self.builtin_record_outcome),
            "recall_from": BuiltinInfo("recall_from", (1, 2, 3, 4), self.builtin_recall_from),
            "recall_all": BuiltinInfo("recall_all", (0, 1, 2, 3), self.builtin_recall_all),
            "share": BuiltinInfo("share", 1, self.builtin_share),
            "__memory_recall": BuiltinInfo("__memory_recall", (0, 1, 2, 3), self.builtin_recall),
            "__memory_remember": BuiltinInfo("__memory_remember", (1, 2, 3), self.builtin_remember),
            "__memory_suggest": BuiltinInfo("__memory_suggest", (0, 1, 2), self.builtin_suggest),
            "__memory_record_outcome": BuiltinInfo("__memory_record_outcome", 2, self.builtin_record_outcome),
            "__memory_recall_from": BuiltinInfo("__memory_recall_from", (1, 2, 3, 4), self.builtin_recall_from),
            "__memory_recall_all": BuiltinInfo("__memory_recall_all", (0, 1, 2, 3), self.builtin_recall_all),
            "__memory_share": BuiltinInfo("__memory_share", 1, self.builtin_share),
            "agent_call": BuiltinInfo("agent_call", 2, self.builtin_agent_call),
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

    def runtime_error(self, kind: str, message: str, payload: object = None):
        err = self.build_runtime_error(kind, message, payload=payload)
        self.emit_runtime_error(err)
        raise err

    def build_runtime_error(self, kind: str, message: str, payload: object = None) -> LangRuntimeError:
        path, line, col = self.current_loc()
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

        return LangRuntimeError(kind, message, line=line, col=col, path=path or self.source_path, stack=stack, payload=payload)

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

    def handle_exception(self, err: LangRuntimeError) -> bool:
        if not self.handler_stack:
            return False
        handler_ip, _finally_ip, stack_depth, frame_depth = self.handler_stack.pop()
        while len(self.frames) > frame_depth:
            frame = self.frames.pop()
            self._profiler_exit_frame(frame)
        while self.handler_stack and self.handler_stack[-1][3] > len(self.frames):
            self.handler_stack.pop()
        if len(self.stack) > stack_depth:
            self.stack = self.stack[:stack_depth]
        err_fields = {
            "kind": err.kind,
            "message": str(err),
            "path": err.path,
            "line": err.line,
            "column": err.col,
            "stack": list(err.stack) if err.stack else [],
        }
        if getattr(err, "payload", None) is not None:
            err_fields["payload"] = err.payload
        err_record = Record(err_fields, kind="error")
        self.stack.append(err_record)
        self.ip = handler_ip
        return True

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
            roots.append(os.path.normcase(os.path.abspath(path)))
        return roots

    def _path_within_root(self, path: str, root: str) -> bool:
        try:
            return os.path.commonpath([path, root]) == root
        except ValueError:
            return False

    def _ensure_path_allowed(self, path: str, op_name: str) -> None:
        if self.allowed_paths is None:
            return
        if not self.allowed_paths:
            self.runtime_error("sandbox", f"{op_name} is not permitted")
        normalized = os.path.normcase(os.path.abspath(path))
        for root in self.allowed_paths:
            if self._path_within_root(normalized, root):
                return
        self.runtime_error("sandbox", f"{op_name} blocked for path: {path!r}")

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
        self.runtime_error("name", f"Undefined variable: {name}")

    def store_name(self, name: str, value):
        locals_ = self.current_locals()
        if locals_ is not None:
            if name in locals_ and isinstance(locals_[name], Cell):
                locals_[name].value = value
            elif name in locals_ and isinstance(locals_[name], LiveBinding):
                locals_[name].set(value)
            else:
                locals_[name] = value
        else:
            if name in self.module_globals and isinstance(self.module_globals[name], LiveBinding):
                self.module_globals[name].set(value)
            else:
                self.module_globals[name] = value
        return value

    def load_upvalue(self, index: int):
        if not self.frames:
            self.runtime_error("runtime", "LOAD_UPVALUE used without a call frame")
        closure = self.frames[-1].closure
        if closure is None or index is None or index >= len(closure.upvalues):
            self.runtime_error("runtime", "Invalid upvalue access")
        return closure.upvalues[index].value

    def store_upvalue(self, index: int, value):
        if not self.frames:
            self.runtime_error("runtime", "STORE_UPVALUE used without a call frame")
        closure = self.frames[-1].closure
        if closure is None or index is None or index >= len(closure.upvalues):
            self.runtime_error("runtime", "Invalid upvalue access")
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
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return "number"
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
        )

    def restore_execution_context(self, ctx) -> None:
        (
            self.ip,
            self.stack,
            self.frames,
            self.handler_stack,
            self.current_coroutine,
        ) = ctx

    def load_coroutine_context(self, coroutine: Coroutine) -> None:
        self.stack = coroutine.stack
        self.frames = coroutine.frames
        self.handler_stack = coroutine.handler_stack
        self.current_coroutine = coroutine
        self.ip = coroutine.ip if coroutine.ip is not None else 0

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
        if isinstance(deps, dict):
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
        )

    def builtin_graph(self, tasks):
        if not isinstance(tasks, list):
            self.runtime_error("type", "graph(tasks) expects a list")
        nodes = [self.ensure_task(item, "graph(tasks)") for item in tasks]
        return TaskGraph(nodes)

    def builtin_run_graph(self, graph):
        tg = graph
        if isinstance(graph, list):
            tg = TaskGraph([self.ensure_task(item, "run_graph(tasks)") for item in graph])
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
        return plan

    def builtin_resume_graph(self, graph_id):
        if not isinstance(graph_id, str):
            self.runtime_error("type", "resume_graph(graph_id) expects a string")
        return resume_graph(self, graph_id)

    def builtin_run_workflow(self, workflow):
        if not is_workflow_value(workflow):
            self.runtime_error("type", "run_workflow(workflow) expects a workflow")
        return run_task_graph(self, workflow_to_graph(self, workflow, init_state=True))

    def builtin_plan_workflow(self, workflow):
        if not is_workflow_value(workflow):
            self.runtime_error("type", "plan_workflow(workflow) expects a workflow")
        graph = workflow_to_graph(self, workflow, init_state=False)
        step_plan = self._step_plan_from_graph(graph, label="workflow")
        self.last_graph_plan = step_plan
        self.event_bus.emit_event(
            "graph_plan_created",
            data={"nodes": float(len(step_plan.get("nodes", []))), "workflow": step_plan.get("workflow")},
        )
        return step_plan

    def builtin_resume_workflow(self, graph_id, checkpoint=None):
        if not isinstance(graph_id, str):
            self.runtime_error("type", "resume_workflow(graph_id, checkpoint) expects graph_id as string")
        if checkpoint is None:
            return self.builtin_resume_graph(graph_id)
        if not isinstance(checkpoint, str):
            self.runtime_error("type", "resume_workflow(graph_id, checkpoint) expects checkpoint as string")
        state = load_graph_state(graph_id)
        if state is None:
            return {"ok": False, "error": "Graph state not found"}
        graph = get_registered_graph(graph_id)
        if graph is None:
            graph = self._rebuild_workflow_graph(graph_id, state)
        if graph is None:
            return {"ok": False, "error": "Unknown graph"}
        checkpoints = state.get("checkpoints")
        if not isinstance(checkpoints, list) and isinstance(state.get("metadata"), dict):
            checkpoints = state["metadata"].get("checkpoints")
        entry = None
        if isinstance(checkpoints, list):
            for item in reversed(checkpoints):
                if isinstance(item, dict) and item.get("label") == checkpoint:
                    entry = item
                    break
        if entry is None:
            return {"ok": False, "error": f"Checkpoint not found: {checkpoint}"}
        if "state" in entry:
            state["workflow_state"] = entry.get("state")
        self._rollback_to_checkpoint(graph, state, entry)
        self.event_bus.emit_event("graph_resume", data={"graph_id": graph_id, "checkpoint": checkpoint})
        return run_task_graph(self, graph, resume_state=state)

    def builtin_run_goal(self, goal):
        if not is_goal_value(goal):
            self.runtime_error("type", "run_goal(goal) expects a goal")
        return run_task_graph(self, workflow_to_graph(self, goal, init_state=True))

    def builtin_plan_goal(self, goal):
        if not is_goal_value(goal):
            self.runtime_error("type", "plan_goal(goal) expects a goal")
        graph = workflow_to_graph(self, goal, init_state=False)
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
        if checkpoint is not None:
            if not isinstance(checkpoint, str):
                self.runtime_error("type", "resume_goal(graph_id, checkpoint) expects checkpoint as string")
            return self.builtin_resume_workflow(graph_id, checkpoint)
        state = load_graph_state(graph_id)
        if state is None:
            return {"ok": False, "error": "Graph state not found"}
        graph = get_registered_graph(graph_id)
        if graph is None:
            graph = self._rebuild_workflow_graph(graph_id, state)
        if graph is None:
            return {"ok": False, "error": "Unknown graph"}
        self.event_bus.emit_event("graph_resume", data={"graph_id": graph_id})
        return run_task_graph(self, graph, resume_state=state)

    def _step_plan_from_graph(self, graph: TaskGraph, *, label: str) -> dict:
        plan = plan_graph(graph.tasks, graph=graph)
        step_labels = graph.metadata.get("task_to_step", {}) if isinstance(graph.metadata, dict) else {}
        flow_name = graph.metadata.get("workflow_name") if isinstance(graph.metadata, dict) else None
        step_plan = {
            label: graph.metadata.get("goal_name", flow_name) if isinstance(graph.metadata, dict) else None,
            "graph_id": plan.get("graph_id"),
            "nodes": [step_labels.get(node, node) for node in plan.get("nodes", [])],
            "edges": [[step_labels.get(edge[0], edge[0]), step_labels.get(edge[1], edge[1])] for edge in plan.get("edges", [])],
            "levels": [[step_labels.get(node, node) for node in level] for level in plan.get("levels", [])],
            "parallel_groups": [[step_labels.get(node, node) for node in level] for level in plan.get("parallel_groups", [])],
            "tasks": plan,
        }
        if label != "workflow":
            step_plan["workflow"] = flow_name
        return step_plan

    def _rebuild_workflow_graph(self, graph_id: str, state: dict) -> TaskGraph | None:
        metadata = state.get("metadata") if isinstance(state.get("metadata"), dict) else {}
        workflow_name = metadata.get("workflow_name")
        goal_name = metadata.get("goal_name")
        execution_kind = metadata.get("execution_kind")
        flow_name = goal_name if isinstance(goal_name, str) and goal_name else workflow_name
        if not isinstance(flow_name, str) or not flow_name:
            return None
        source_code = metadata.get("workflow_source_code")
        source_path = metadata.get("workflow_source_path")
        if not isinstance(source_code, str):
            if not isinstance(source_path, str) or not source_path or not os.path.exists(source_path):
                return None
            with open(source_path, "r", encoding="utf-8") as f:
                source_code = f.read()
        rebuild_path = source_path if isinstance(source_path, str) and source_path else None
        try:
            from nodus.runtime.module_loader import ModuleLoader as _ModuleLoader
            _loader = _ModuleLoader(project_root=None)
            code, functions, code_locs = _loader.compile_only(
                source_code,
                module_name=rebuild_path or "<memory>",
            )
        except Exception:
            return None
        worker_dispatcher = getattr(self, "worker_dispatcher", None)
        event_bus = self.event_bus
        rebuilt_globals: dict[str, object] = {}
        self.reset_program(code, functions, code_locs=code_locs, source_path=rebuild_path, module_globals=rebuilt_globals)
        self.event_bus = event_bus
        self.source_code = source_code
        if worker_dispatcher is not None:
            self.worker_dispatcher = worker_dispatcher
        self.run()
        workflow = find_goal_value(self.globals, flow_name) if execution_kind == "goal" else find_workflow_value(self.globals, flow_name)
        if workflow is None:
            return None
        step_to_task = metadata.get("step_to_task") if isinstance(metadata.get("step_to_task"), dict) else None
        graph = workflow_to_graph(self, workflow, init_state=False, task_ids_by_step=step_to_task)
        graph.graph_id = graph_id
        return graph

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
            if isinstance(state.get("checkpoints"), list):
                checkpoints = state.get("checkpoints")
            elif isinstance(state.get("metadata"), dict):
                checkpoints = state["metadata"].get("checkpoints")
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
        except Exception as err:
            if meta is not None:
                fail = dict(meta)
                fail["message"] = str(err)
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

    def builtin_memory_get(self, key):
        try:
            return get_value(key, vm=self)
        except ValueError as err:
            self.runtime_error("type", str(err))

    def builtin_memory_put(self, key, value):
        try:
            return put_value(key, value, vm=self)
        except ValueError as err:
            self.runtime_error("type", str(err))

    def builtin_memory_delete(self, key):
        try:
            return delete_value(key, vm=self)
        except ValueError as err:
            self.runtime_error("type", str(err))

    def builtin_memory_keys(self):
        return list_keys(vm=self)

    def _get_memory_bridge(self):
        if self.host_globals and "memory_bridge" in self.host_globals:
            return self.host_globals.get("memory_bridge")
        if self.module_globals and "memory_bridge" in self.module_globals:
            return self.module_globals.get("memory_bridge")
        return None

    def builtin_recall(self, query=None, tags=None, limit=None):
        bridge = self._get_memory_bridge()
        if bridge is None:
            return []
        try:
            if limit is None:
                return bridge.recall(query=query, tags=tags, limit=3)
            return bridge.recall(query=query, tags=tags, limit=limit)
        except Exception:
            return []

    def builtin_remember(self, content, node_type=None, tags=None):
        bridge = self._get_memory_bridge()
        if bridge is None:
            return None
        try:
            if node_type is None:
                return bridge.remember(content=content, tags=tags)
            return bridge.remember(content=content, node_type=node_type, tags=tags)
        except Exception:
            return None

    def builtin_suggest(self, query=None, tags=None):
        bridge = self._get_memory_bridge()
        if bridge is None:
            return []
        try:
            return bridge.get_suggestions(query=query, tags=tags, limit=3)
        except Exception:
            return []

    def builtin_record_outcome(self, node_id, outcome):
        bridge = self._get_memory_bridge()
        if bridge is None:
            return None
        try:
            bridge.record_outcome(node_id, outcome)
        except Exception:
            return None
        return None

    def builtin_recall_from(self, agent, query=None, tags=None, limit=None):
        bridge = self._get_memory_bridge()
        if bridge is None:
            return []
        if not isinstance(agent, str):
            self.runtime_error("type", "recall_from(agent, ...) expects agent as string")
        try:
            if limit is None:
                return bridge.recall_from(agent_namespace=agent, query=query, tags=tags, limit=3)
            return bridge.recall_from(agent_namespace=agent, query=query, tags=tags, limit=limit)
        except Exception:
            return []

    def builtin_recall_all(self, query=None, tags=None, limit=None):
        bridge = self._get_memory_bridge()
        if bridge is None:
            return {"merged_results": [], "results_by_agent": {}}
        try:
            if limit is None:
                return bridge.recall_all_agents(query=query, tags=tags, limit=5)
            return bridge.recall_all_agents(query=query, tags=tags, limit=limit)
        except Exception:
            return {"merged_results": [], "results_by_agent": {}}

    def builtin_share(self, node_id):
        bridge = self._get_memory_bridge()
        if bridge is None:
            return False
        try:
            return bool(bridge.share(node_id))
        except Exception:
            return False
    def builtin_agent_call(self, name, payload):
        return call_agent(name, payload, vm=self)

    def builtin_action_tool(self, name, args):
        return self._run_goal_action("tool", name, lambda: self.builtin_tool_call(name, args))

    def builtin_action_agent(self, name, payload):
        return self._run_goal_action("agent", name, lambda: self.builtin_agent_call(name, payload))

    def builtin_action_memory_put(self, key, value):
        return self._run_goal_action("memory_put", key, lambda: self.builtin_memory_put(key, value))

    def builtin_action_memory_get(self, key):
        return self._run_goal_action("memory_get", key, lambda: self.builtin_memory_get(key))

    def builtin_action_emit(self, name, payload):
        return self._run_goal_action("emit", name, lambda: self.builtin_emit(name, payload))

    def builtin_agent_available(self):
        return available_agents()

    def builtin_agent_describe(self, name):
        if not isinstance(name, str):
            self.runtime_error("type", "agent_describe(name) expects a string")
        return describe_agent(name)

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

    def builtin_read_file(self, path):
        return self.builtins["read_file"].fn(path)

    def escape_string(self, s: str) -> str:
        return s.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n").replace("\t", "\\t")

    def display_name(self, name: str) -> str:
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

        self.runtime_error("type", "Indexing is only supported on lists and maps")

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
                self.runtime_error("runtime", "sleep(ms) outside coroutine")
            self.current_coroutine.state = "suspended"
            self.save_current_coroutine_state(self.ip + 1)
            return ("yield", {SLEEP_KEY: result.ms})
        if isinstance(result, ChannelRecvRequest):
            return ("yield", {CHANNEL_WAIT_KEY: True})
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
        self.frames.append(frame)
        if self.profiler is not None and self.profiler.enabled:
            self.profiler.enter_function(self.display_name(fn.name))
        self.ip = fn.addr

    def run_closure(self, closure, args: list, workflow_context: dict | None = None):
        if not isinstance(closure, Closure):
            self.runtime_error("call", "Task expects a function")
        ctx = self.save_execution_context()
        try:
            self.stack = []
            self.frames = []
            self.handler_stack = []
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
            self._last_batch_emit = self.instructions_executed
            self.event_bus.emit_event(
                "vm_instruction_batch",
                data={"count": float(count), "total": float(self.instructions_executed)},
            )

    def record_vm_call(self, name: str | None, call_type: str) -> None:
        self.function_calls += 1
        if self.profiler is not None and self.profiler.enabled:
            self.profiler.record_function_call(name)
        self.event_bus.emit_event(
            "vm_call",
            name=name,
            data={"call_type": call_type, "total": float(self.function_calls)},
        )

    def record_vm_return(self, name: str | None) -> None:
        self.returns += 1
        self.event_bus.emit_event(
            "vm_return",
            name=name,
            data={"total": float(self.returns)},
        )

    def record_vm_exception(self, err: Exception) -> None:
        self.exceptions += 1
        data = {"total": float(self.exceptions)}
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
        try:
            self.stack.append(a / b)
        except ZeroDivisionError:
            self.runtime_error("runtime", "Division by zero")
        except TypeError:
            self._binary_type_error("divide", a, b)
        self.ip += 1

    def _op_eq(self, instr):
        b = self.pop()
        a = self.pop()
        self.stack.append(a == b)
        self.ip += 1

    def _op_ne(self, instr):
        b = self.pop()
        a = self.pop()
        self.stack.append(a != b)
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
        self.runtime_error("name", f"Undefined function: {fn_name}")

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
            self.stack.append(callee(*args))
            self.ip += 1
            return None
        for arg in args:
            self.stack.append(arg)
        self.call_closure(callee, arg_count)
        return None

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
        if isinstance(method, ModuleFunction):
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
            # String throw: use as message directly
            self.runtime_error("runtime", value)
        elif isinstance(value, (int, float, bool)):
            # Primitive throw: convert to string message
            self.runtime_error("runtime", self.value_to_string(value))
        else:
            # Structured throw (Record, list, etc.): preserve as payload.
            # The catch block receives err where err.kind == "thrown",
            # err.message is the string form, and err.payload is the original value.
            message = self.value_to_string(value, quote_strings=False)
            self.runtime_error("thrown", message, payload=value)

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
            self.ip = finally_ip
            return
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
            "STORE_UPVALUE":self._op_store_upvalue,
            "STORE_ARG":    self._op_store_arg,
            "POP":          self._op_pop,
            "ADD":          self._op_add,
            "SUB":          self._op_sub,
            "MUL":          self._op_mul,
            "DIV":          self._op_div,
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
                print(self.format_trace(instr))
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
            except LangRuntimeError as err:
                self.record_vm_exception(err)
                self.emit_runtime_error(err)
                if self.handle_exception(err):
                    continue
                raise
            except Exception as err:
                self.record_vm_exception(err)
                wrapped = self.build_runtime_error("runtime", str(err))
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

    def format_trace(self, instr: tuple) -> str:
        op = instr[0]
        operands = instr[1:]
        formatted_ops = []
        for value in operands:
            if isinstance(value, str):
                formatted_ops.append(value)
            else:
                formatted_ops.append(repr(value))
        op_text = " ".join([op] + formatted_ops) if formatted_ops else op
        if self.trace_no_loc:
            return f"[trace] {op_text}"
        loc_text = self.format_loc(self.current_loc())
        return f"[trace] {op_text} ({loc_text})"



