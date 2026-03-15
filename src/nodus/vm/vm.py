"""Stack VM runtime for Nodus."""

import json
import math
import os
import random
import time
from dataclasses import dataclass

from nodus.runtime.coroutine import Coroutine
from nodus.runtime.channel import Channel, ChannelRecvRequest
from nodus.orchestration.task_graph import TaskNode, TaskGraph, run_task_graph, plan_graph, resume_graph, load_graph_state, get_registered_graph
from nodus.builtins.nodus_builtins import BUILTIN_NAMES, BuiltinInfo
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


class Cell:
    def __init__(self, value=None):
        self.value = value


class Closure:
    def __init__(self, function: FunctionInfo, upvalues: list[Cell]):
        self.function = function
        self.upvalues = upvalues


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


@dataclass
class Frame:
    return_ip: int | None
    locals: dict
    fn_name: str
    call_line: int | None
    call_col: int | None
    call_path: str | None
    closure: Closure | None = None


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
        self.handler_stack: list[tuple[int, int, int]] = []
        self.pending_iter_next: int | None = None
        self.pending_get_iter: bool = False
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
            "coroutine": BuiltinInfo("coroutine", 1, self.builtin_coroutine_create),
            "resume": BuiltinInfo("resume", 1, self.builtin_coroutine_resume),
            "coroutine_status": BuiltinInfo("coroutine_status", 1, self.builtin_coroutine_status),
            "spawn": BuiltinInfo("spawn", 1, self.builtin_spawn),
            "run_loop": BuiltinInfo("run_loop", 0, self.builtin_run_loop),
            "sleep": BuiltinInfo("sleep", 1, self.builtin_sleep),
            "__sleep": BuiltinInfo("__sleep", 1, self.builtin_sleep),
            "channel": BuiltinInfo("channel", 0, self.builtin_channel),
            "send": BuiltinInfo("send", 2, self.builtin_send),
            "recv": BuiltinInfo("recv", 1, self.builtin_recv),
            "close": BuiltinInfo("close", 1, self.builtin_close),
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
            "agent_call": BuiltinInfo("agent_call", 2, self.builtin_agent_call),
            "agent_available": BuiltinInfo("agent_available", 0, self.builtin_agent_available),
            "agent_describe": BuiltinInfo("agent_describe", 1, self.builtin_agent_describe),
            "__action_tool": BuiltinInfo("__action_tool", 2, self.builtin_action_tool),
            "__action_agent": BuiltinInfo("__action_agent", 2, self.builtin_action_agent),
            "__action_memory_put": BuiltinInfo("__action_memory_put", 2, self.builtin_action_memory_put),
            "__action_memory_get": BuiltinInfo("__action_memory_get", 1, self.builtin_action_memory_get),
            "__action_emit": BuiltinInfo("__action_emit", 2, self.builtin_action_emit),
            "__workflow_checkpoint": BuiltinInfo("__workflow_checkpoint", 1, self.builtin_workflow_checkpoint),
            "str": BuiltinInfo("str", 1, lambda x: self.value_to_string(x, quote_strings=False)),
            "len": BuiltinInfo("len", 1, self.builtin_len),
            "collection_len": BuiltinInfo("collection_len", 1, self.builtin_len),
            "str_upper": BuiltinInfo("str_upper", 1, self.builtin_upper),
            "str_lower": BuiltinInfo("str_lower", 1, self.builtin_lower),
            "str_trim": BuiltinInfo("str_trim", 1, self.builtin_trim),
            "str_split": BuiltinInfo("str_split", 2, self.builtin_split),
            "str_contains": BuiltinInfo("str_contains", 2, self.builtin_contains),
            "print": BuiltinInfo("print", 1, self.builtin_print),
            "input": BuiltinInfo("input", 1, self.builtin_input),
            "keys": BuiltinInfo("keys", 1, self.builtin_keys),
            "values": BuiltinInfo("values", 1, self.builtin_values),
            "list_push": BuiltinInfo("list_push", 2, self.builtin_list_push),
            "list_pop": BuiltinInfo("list_pop", 1, self.builtin_list_pop),
            "json_parse": BuiltinInfo("json_parse", 1, self.builtin_json_parse),
            "json_stringify": BuiltinInfo("json_stringify", 1, self.builtin_json_stringify),
            "math_abs": BuiltinInfo("math_abs", 1, self.builtin_math_abs),
            "math_min": BuiltinInfo("math_min", 2, self.builtin_math_min),
            "math_max": BuiltinInfo("math_max", 2, self.builtin_math_max),
            "math_floor": BuiltinInfo("math_floor", 1, self.builtin_math_floor),
            "math_ceil": BuiltinInfo("math_ceil", 1, self.builtin_math_ceil),
            "math_sqrt": BuiltinInfo("math_sqrt", 1, self.builtin_math_sqrt),
            "math_random": BuiltinInfo("math_random", 0, self.builtin_math_random),
            "read_file": BuiltinInfo("read_file", 1, self.builtin_read_file),
            "write_file": BuiltinInfo("write_file", 2, self.builtin_write_file),
            "exists": BuiltinInfo("exists", 1, self.builtin_exists),
            "path_exists": BuiltinInfo("path_exists", 1, self.builtin_exists),
            "append_file": BuiltinInfo("append_file", 2, self.builtin_append_file),
            "mkdir": BuiltinInfo("mkdir", 1, self.builtin_mkdir),
            "list_dir": BuiltinInfo("list_dir", 1, self.builtin_list_dir),
            "path_join": BuiltinInfo("path_join", 2, self.builtin_path_join),
            "path_dirname": BuiltinInfo("path_dirname", 1, self.builtin_path_dirname),
            "path_basename": BuiltinInfo("path_basename", 1, self.builtin_path_basename),
            "path_ext": BuiltinInfo("path_ext", 1, self.builtin_path_ext),
            "path_stem": BuiltinInfo("path_stem", 1, self.builtin_path_stem),
        }

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

    def runtime_error(self, kind: str, message: str):
        err = self.build_runtime_error(kind, message)
        self.emit_runtime_error(err)
        raise err

    def build_runtime_error(self, kind: str, message: str) -> LangRuntimeError:
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

        return LangRuntimeError(kind, message, line=line, col=col, path=path or self.source_path, stack=stack)

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
        handler_ip, stack_depth, frame_depth = self.handler_stack.pop()
        while len(self.frames) > frame_depth:
            frame = self.frames.pop()
            self._profiler_exit_frame(frame)
        while self.handler_stack and self.handler_stack[-1][2] > len(self.frames):
            self.handler_stack.pop()
        if len(self.stack) > stack_depth:
            self.stack = self.stack[:stack_depth]
        err_record = Record(
            {
                "kind": err.kind,
                "message": str(err),
                "path": err.path,
                "line": err.line,
                "column": err.col,
                "stack": list(err.stack) if err.stack else [],
            },
            kind="error",
        )
        self.stack.append(err_record)
        self.ip = handler_ip
        return True

    def setup_try(self, handler_ip: int):
        self.handler_stack.append((handler_ip, len(self.stack), len(self.frames)))

    def pop_try(self):
        if not self.handler_stack:
            self.runtime_error("runtime", "POP_TRY without handler")
        self.handler_stack.pop()

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

    def builtin_len(self, value):
        if isinstance(value, (str, list, dict)):
            return float(len(value))
        self.runtime_error("type", "len(x) expects string, list, or map")

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

    def builtin_upper(self, value):
        self.ensure_string(value, "upper(x)")
        return value.upper()

    def builtin_lower(self, value):
        self.ensure_string(value, "lower(x)")
        return value.lower()

    def builtin_trim(self, value):
        self.ensure_string(value, "trim(x)")
        return value.strip()

    def builtin_split(self, value, delimiter):
        self.ensure_string(value, "split(x, delimiter)")
        self.ensure_string(delimiter, "split(x, delimiter)")
        return value.split(delimiter)

    def builtin_contains(self, value, needle):
        self.ensure_string(value, "contains(x, needle)")
        self.ensure_string(needle, "contains(x, needle)")
        return needle in value

    def builtin_print(self, value):
        print(self.value_to_string(value, quote_strings=False))
        return None

    def builtin_runtime_fn_name(self, value):
        closure = self.ensure_function(value, "runtime.fn_name(fn)")
        return closure.function.display_name

    def builtin_runtime_fn_arity(self, value):
        closure = self.ensure_function(value, "runtime.fn_arity(fn)")
        return float(len(closure.function.params))

    def builtin_runtime_fn_module(self, value):
        closure = self.ensure_function(value, "runtime.fn_module(fn)")
        path, _line, _col = self.code_locs[closure.function.addr]
        return path or self.source_path

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
            self.pending_iter_next,
            self.pending_get_iter,
            self.current_coroutine,
        )

    def restore_execution_context(self, ctx) -> None:
        (
            self.ip,
            self.stack,
            self.frames,
            self.handler_stack,
            self.pending_iter_next,
            self.pending_get_iter,
            self.current_coroutine,
        ) = ctx

    def load_coroutine_context(self, coroutine: Coroutine) -> None:
        self.stack = coroutine.stack
        self.frames = coroutine.frames
        self.handler_stack = coroutine.handler_stack
        self.pending_iter_next = coroutine.pending_iter_next
        self.pending_get_iter = coroutine.pending_get_iter
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
        self.pending_iter_next = None
        self.pending_get_iter = False
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
        coroutine.pending_iter_next = self.pending_iter_next
        coroutine.pending_get_iter = self.pending_get_iter

    def builtin_coroutine_create(self, value):
        closure = self.ensure_function(value, "coroutine(fn)")
        if len(closure.function.params) != 0:
            self.runtime_error("call", "coroutine(fn) expects a zero-argument function")
        return Coroutine(closure)

    def builtin_coroutine_status(self, value):
        coroutine = self.ensure_coroutine(value, "coroutine_status(coroutine)")
        return coroutine.state

    def builtin_coroutine_resume(self, value):
        coroutine = self.ensure_coroutine(value, "resume(coroutine)")
        if coroutine.state == "finished":
            self.runtime_error("runtime", "Cannot resume finished coroutine")
        if coroutine.state == "running":
            self.runtime_error("runtime", "Cannot resume running coroutine")

        caller_context = self.save_execution_context()
        try:
            if coroutine.state == "created":
                call_path, call_line, call_col = self.current_loc()
                coroutine.stack = list(coroutine.initial_args or [])
                coroutine.frames = []
                coroutine.handler_stack = []
                coroutine.pending_iter_next = None
                coroutine.pending_get_iter = False
                self.load_coroutine_context(coroutine)
                coroutine.state = "running"
                fn = coroutine.closure.function
                if self.max_frames is not None and len(self.frames) + 1 > self.max_frames:
                    self.runtime_error("sandbox", "Call stack overflow")
                self.frames.append(
                    Frame(
                        return_ip=None,
                        locals={},
                        fn_name=fn.name,
                        call_line=call_line,
                        call_col=call_col,
                        call_path=call_path,
                        closure=coroutine.closure,
                    )
                )
                if self.profiler is not None and self.profiler.enabled:
                    self.profiler.enter_function(self.display_name(fn.name))
                self.ip = fn.addr
            else:
                self.load_coroutine_context(coroutine)
                coroutine.state = "running"

            try:
                status, result = self.execute()
            except Exception:
                coroutine.state = "finished"
                coroutine.ip = None
                coroutine.stack = []
                coroutine.frames = []
                coroutine.handler_stack = []
                coroutine.pending_iter_next = None
                coroutine.pending_get_iter = False
                raise
            if status in {"yield", "return"}:
                if status == "return":
                    coroutine.last_result = result
                return result
            return None
        finally:
            self.restore_execution_context(caller_context)

    def builtin_spawn(self, value):
        coroutine = self.ensure_coroutine(value, "spawn(coroutine)")
        self.scheduler.spawn(coroutine)
        return None

    def builtin_run_loop(self):
        self.scheduler.run_loop()
        return None

    def builtin_sleep(self, value):
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            self.runtime_error("type", "sleep(ms) expects a number")
        ms = float(value)
        if ms < 0:
            ms = 0.0
        return SleepRequest(ms)

    def builtin_channel(self):
        return Channel()

    def builtin_send(self, channel, value):
        ch = self.ensure_channel(channel, "send(channel, value)")
        if ch.closed:
            self.runtime_error("runtime", "send on closed channel")
        sender_id = self.current_coroutine.id if self.current_coroutine is not None else None
        sender_name = self.current_coroutine.name if self.current_coroutine is not None else None
        if ch.waiting_receivers:
            receiver = ch.waiting_receivers.pop(0)
            if receiver.stack:
                receiver.stack[-1] = value
            receiver.blocked_on = None
            receiver.blocked_reason = None
            self.scheduler.schedule(receiver)
            self.event_bus.emit_event(
                "channel_send",
                coroutine_id=sender_id,
                name=sender_name,
                data={"queue_size": float(len(ch.queue)), "waiting_receivers": float(len(ch.waiting_receivers))},
            )
            self.event_bus.emit_event(
                "channel_recv",
                coroutine_id=receiver.id,
                name=receiver.name,
                data={"from_wait": True},
            )
            self.event_bus.emit_event("channel_wake", coroutine_id=receiver.id, name=receiver.name)
            return None
        ch.queue.append(value)
        self.event_bus.emit_event(
            "channel_send",
            coroutine_id=sender_id,
            name=sender_name,
            data={"queue_size": float(len(ch.queue)), "waiting_receivers": float(len(ch.waiting_receivers))},
        )
        return None

    def builtin_recv(self, channel):
        ch = self.ensure_channel(channel, "recv(channel)")
        if ch.queue:
            value = ch.queue.popleft()
            self.event_bus.emit_event(
                "channel_recv",
                coroutine_id=self.current_coroutine.id if self.current_coroutine is not None else None,
                name=self.current_coroutine.name if self.current_coroutine is not None else None,
                data={"from_queue": True, "queue_size": float(len(ch.queue))},
            )
            return value
        if ch.closed:
            self.event_bus.emit_event(
                "channel_recv",
                coroutine_id=self.current_coroutine.id if self.current_coroutine is not None else None,
                name=self.current_coroutine.name if self.current_coroutine is not None else None,
                data={"closed": True},
            )
            return None
        if self.current_coroutine is None:
            self.runtime_error("runtime", "recv(channel) outside coroutine")
        coroutine = self.current_coroutine
        coroutine.state = "suspended"
        coroutine.blocked_on = ch
        coroutine.blocked_reason = "channel_recv"
        self.stack.append(None)
        self.save_current_coroutine_state(self.ip + 1)
        ch.waiting_receivers.append(coroutine)
        self.event_bus.emit_event(
            "channel_block",
            coroutine_id=coroutine.id,
            name=coroutine.name,
            data={"operation": "recv"},
        )
        return ChannelRecvRequest(ch)

    def builtin_close(self, channel):
        ch = self.ensure_channel(channel, "close(channel)")
        if ch.closed:
            return None
        ch.closed = True
        self.event_bus.emit_event(
            "channel_close",
            coroutine_id=self.current_coroutine.id if self.current_coroutine is not None else None,
            name=self.current_coroutine.name if self.current_coroutine is not None else None,
            data={"waiting_receivers": float(len(ch.waiting_receivers))},
        )
        while ch.waiting_receivers:
            receiver = ch.waiting_receivers.pop(0)
            if receiver.stack:
                receiver.stack[-1] = None
            receiver.blocked_on = None
            receiver.blocked_reason = None
            self.scheduler.schedule(receiver)
            self.event_bus.emit_event("channel_wake", coroutine_id=receiver.id, name=receiver.name)
            self.event_bus.emit_event(
                "channel_recv",
                coroutine_id=receiver.id,
                name=receiver.name,
                data={"closed": True},
            )
        return None

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
            from nodus.tooling.loader import compile_source

            _ast, code, functions, code_locs = compile_source(
                source_code,
                source_path=rebuild_path,
                import_state={"loaded": set(), "loading": set(), "exports": {}, "modules": {}, "module_ids": {}, "project_root": None},
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

    def builtin_input(self, prompt):
        return self.input_fn(self.value_to_string(prompt, quote_strings=False))

    def builtin_keys(self, value):
        if not isinstance(value, dict):
            self.runtime_error("type", "keys(x) expects a map")
        return list(value.keys())

    def builtin_values(self, value):
        if not isinstance(value, dict):
            self.runtime_error("type", "values(x) expects a map")
        return list(value.values())

    def builtin_list_push(self, value, item):
        if not isinstance(value, list):
            self.runtime_error("type", "list_push(list, value) expects a list")
        value.append(item)
        return value

    def builtin_list_pop(self, value):
        if not isinstance(value, list):
            self.runtime_error("type", "list_pop(list) expects a list")
        if not value:
            self.runtime_error("index", "Cannot pop from an empty list")
        return value.pop()

    def from_json_value(self, value):
        if value is None:
            return None
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            return float(value)
        if isinstance(value, str):
            return value
        if isinstance(value, list):
            return [self.from_json_value(item) for item in value]
        if isinstance(value, dict):
            return Record({key: self.from_json_value(item) for key, item in value.items()})
        self.runtime_error("runtime", f"Unsupported JSON value: {value!r}")

    def to_json_value(self, value):
        if value is None:
            return None
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            if isinstance(value, float) and value.is_integer():
                return int(value)
            return value
        if isinstance(value, str):
            return value
        if isinstance(value, list):
            return [self.to_json_value(item) for item in value]
        if isinstance(value, dict):
            return {str(key): self.to_json_value(item) for key, item in value.items()}
        if isinstance(value, Record):
            return {key: self.to_json_value(item) for key, item in value.fields.items()}
        self.runtime_error("type", f"json.stringify cannot encode value of type {self.builtin_type(value)}")

    def builtin_json_parse(self, text):
        self.ensure_string(text, "json_parse(text)")
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError as err:
            self.runtime_error("runtime", f"json_parse failed: {err.msg}")
        return self.from_json_value(parsed)

    def builtin_json_stringify(self, value):
        try:
            return json.dumps(self.to_json_value(value), ensure_ascii=False)
        except LangRuntimeError:
            raise
        except Exception as err:
            self.runtime_error("runtime", f"json_stringify failed: {err}")

    def builtin_math_abs(self, value):
        return abs(self.ensure_number(value, "math_abs(x)"))

    def builtin_math_min(self, a, b):
        self.ensure_number(a, "math_min(a, b)")
        self.ensure_number(b, "math_min(a, b)")
        return min(a, b)

    def builtin_math_max(self, a, b):
        self.ensure_number(a, "math_max(a, b)")
        self.ensure_number(b, "math_max(a, b)")
        return max(a, b)

    def builtin_math_floor(self, value):
        return float(math.floor(self.ensure_number(value, "math_floor(x)")))

    def builtin_math_ceil(self, value):
        return float(math.ceil(self.ensure_number(value, "math_ceil(x)")))

    def builtin_math_sqrt(self, value):
        number = self.ensure_number(value, "math_sqrt(x)")
        if number < 0:
            self.runtime_error("runtime", "math_sqrt(x) expects a non-negative number")
        return math.sqrt(number)

    def builtin_math_random(self):
        return random.random()

    def builtin_read_file(self, path):
        if not isinstance(path, str):
            self.runtime_error("type", "read_file(path) expects a string path")
        self._ensure_path_allowed(path, "read_file(path)")
        try:
            with open(path, "r", encoding="utf-8") as f:
                return f.read()
        except Exception as err:
            self.runtime_error("runtime", f"read_file failed for {path!r}: {err}")

    def builtin_write_file(self, path, content):
        if not isinstance(path, str):
            self.runtime_error("type", "write_file(path, content) expects string path")
        self._ensure_path_allowed(path, "write_file(path, content)")
        text = self.value_to_string(content, quote_strings=False)
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(text)
        except Exception as err:
            self.runtime_error("runtime", f"write_file failed for {path!r}: {err}")
        return None

    def builtin_exists(self, path):
        if not isinstance(path, str):
            self.runtime_error("type", "exists(path) expects a string path")
        self._ensure_path_allowed(path, "exists(path)")
        return os.path.exists(path)

    def builtin_append_file(self, path, content):
        if not isinstance(path, str):
            self.runtime_error("type", "append_file(path, content) expects string path")
        self._ensure_path_allowed(path, "append_file(path, content)")
        text = self.value_to_string(content, quote_strings=False)
        try:
            with open(path, "a", encoding="utf-8") as f:
                f.write(text)
        except Exception as err:
            self.runtime_error("runtime", f"append_file failed for {path!r}: {err}")
        return None

    def builtin_mkdir(self, path):
        if not isinstance(path, str):
            self.runtime_error("type", "mkdir(path) expects a string path")
        self._ensure_path_allowed(path, "mkdir(path)")
        try:
            os.makedirs(path, exist_ok=True)
        except Exception as err:
            self.runtime_error("runtime", f"mkdir failed for {path!r}: {err}")
        return None

    def builtin_list_dir(self, path):
        if not isinstance(path, str):
            self.runtime_error("type", "list_dir(path) expects a string path")
        self._ensure_path_allowed(path, "list_dir(path)")
        try:
            return sorted(os.listdir(path))
        except Exception as err:
            self.runtime_error("runtime", f"list_dir failed for {path!r}: {err}")

    def ensure_path_string(self, value, name: str):
        if not isinstance(value, str):
            self.runtime_error("type", f"{name} expects a string path")

    def builtin_path_join(self, a, b):
        self.ensure_path_string(a, "path_join(a, b)")
        self.ensure_path_string(b, "path_join(a, b)")
        return os.path.join(a, b)

    def builtin_path_dirname(self, path):
        self.ensure_path_string(path, "path_dirname(path)")
        return os.path.dirname(path)

    def builtin_path_basename(self, path):
        self.ensure_path_string(path, "path_basename(path)")
        return os.path.basename(path)

    def builtin_path_ext(self, path):
        self.ensure_path_string(path, "path_ext(path)")
        ext = os.path.splitext(path)[1]
        if ext.startswith("."):
            return ext[1:]
        return ext

    def builtin_path_stem(self, path):
        self.ensure_path_string(path, "path_stem(path)")
        base = os.path.basename(path)
        return os.path.splitext(base)[0]

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
            self.pending_iter_next = None
            self.pending_get_iter = False
            temp_coroutine = Coroutine(closure)
            temp_coroutine.state = "running"
            temp_coroutine.workflow_context = workflow_context
            self.current_coroutine = temp_coroutine
            for arg in args:
                self.stack.append(arg)
            fn = closure.function
            self.frames.append(
                Frame(
                    return_ip=None,
                    locals={},
                    fn_name=fn.name,
                    call_line=None,
                    call_col=None,
                    call_path=None,
                    closure=closure,
                )
            )
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

    def execute(self):
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
                if op == "PUSH_CONST":
                    self.stack.append(instr[1])
                    self.ip += 1
                    pending_after = instr

                elif op == "LOAD":
                    name = instr[1]
                    self.stack.append(self.load_name(name))
                    self.ip += 1
                    pending_after = instr

                elif op == "LOAD_UPVALUE":
                    index = instr[1]
                    self.stack.append(self.load_upvalue(index))
                    self.ip += 1
                    pending_after = instr

                elif op == "STORE":
                    name = instr[1]
                    value = self.pop()
                    self.store_name(name, value)
                    self.ip += 1
                    pending_after = instr

                elif op == "STORE_UPVALUE":
                    index = instr[1]
                    value = self.pop()
                    self.store_upvalue(index, value)
                    self.ip += 1
                    pending_after = instr

                elif op == "STORE_ARG":
                    name = instr[1]
                    value = self.pop()
                    locals_ = self.current_locals()
                    if locals_ is None:
                        self.runtime_error("runtime", "STORE_ARG used without a call frame")
                    if name in locals_ and isinstance(locals_[name], Cell):
                        locals_[name].value = value
                    else:
                        locals_[name] = value
                    self.ip += 1
                    pending_after = instr

                elif op == "POP":
                    self.pop()
                    self.ip += 1
                    pending_after = instr

                elif op == "ADD":
                    b = self.pop()
                    a = self.pop()
                    try:
                        self.stack.append(a + b)
                    except TypeError:
                        self._binary_type_error("add", a, b)
                    self.ip += 1
                    pending_after = instr

                elif op == "SUB":
                    b = self.pop()
                    a = self.pop()
                    try:
                        self.stack.append(a - b)
                    except TypeError:
                        self._binary_type_error("subtract", a, b)
                    self.ip += 1
                    pending_after = instr

                elif op == "MUL":
                    b = self.pop()
                    a = self.pop()
                    try:
                        self.stack.append(a * b)
                    except TypeError:
                        self._binary_type_error("multiply", a, b)
                    self.ip += 1
                    pending_after = instr

                elif op == "DIV":
                    b = self.pop()
                    a = self.pop()
                    try:
                        self.stack.append(a / b)
                    except ZeroDivisionError:
                        self.runtime_error("runtime", "Division by zero")
                    except TypeError:
                        self._binary_type_error("divide", a, b)
                    self.ip += 1
                    pending_after = instr

                elif op == "EQ":
                    b = self.pop()
                    a = self.pop()
                    self.stack.append(a == b)
                    self.ip += 1
                    pending_after = instr

                elif op == "NE":
                    b = self.pop()
                    a = self.pop()
                    self.stack.append(a != b)
                    self.ip += 1
                    pending_after = instr

                elif op == "LT":
                    b = self.pop()
                    a = self.pop()
                    try:
                        self.stack.append(a < b)
                    except TypeError:
                        self._compare_type_error(a, b)
                    self.ip += 1
                    pending_after = instr

                elif op == "GT":
                    b = self.pop()
                    a = self.pop()
                    try:
                        self.stack.append(a > b)
                    except TypeError:
                        self._compare_type_error(a, b)
                    self.ip += 1
                    pending_after = instr

                elif op == "LE":
                    b = self.pop()
                    a = self.pop()
                    try:
                        self.stack.append(a <= b)
                    except TypeError:
                        self._compare_type_error(a, b)
                    self.ip += 1
                    pending_after = instr

                elif op == "GE":
                    b = self.pop()
                    a = self.pop()
                    try:
                        self.stack.append(a >= b)
                    except TypeError:
                        self._compare_type_error(a, b)
                    self.ip += 1
                    pending_after = instr

                elif op == "JUMP":
                    self.ip = instr[1]
                    pending_after = instr

                elif op == "JUMP_IF_FALSE":
                    target = instr[1]
                    cond = self.pop()
                    if not self.is_truthy(cond):
                        self.ip = target
                    else:
                        self.ip += 1
                    pending_after = instr

                elif op == "JUMP_IF_TRUE":
                    target = instr[1]
                    cond = self.pop()
                    if self.is_truthy(cond):
                        self.ip = target
                    else:
                        self.ip += 1
                    pending_after = instr

                elif op == "GET_ITER":
                    value = self.pop()
                    if isinstance(value, list):
                        self.stack.append(ListIterator(value))
                        self.ip += 1
                        pending_after = instr
                        continue
                    if isinstance(value, Record):
                        if "__iter__" in value.fields:
                            iterator_fn = value.fields["__iter__"]
                            self.pending_get_iter = True
                            self.stack.append(value)
                            self.call_closure(iterator_fn, 1)
                            continue
                        if "__next__" in value.fields:
                            self.stack.append(value)
                            self.ip += 1
                            pending_after = instr
                            continue
                    self.runtime_error("type", "Value is not iterable")

                elif op == "ITER_NEXT":
                    end_ip = instr[1]
                    if not self.stack:
                        self.runtime_error("runtime", "ITER_NEXT without iterator")
                    iterator = self.stack[-1]
                    if not isinstance(iterator, ListIterator):
                        if isinstance(iterator, Record) and "__next__" in iterator.fields:
                            method = iterator.fields["__next__"]
                            self.pending_iter_next = end_ip
                            self.stack.append(iterator)
                            self.call_closure(method, 1)
                            continue
                        self.runtime_error("type", "Iterator is not supported")
                    if iterator.index >= len(iterator.values):
                        self.stack.pop()
                        self.ip = end_ip
                    else:
                        value = iterator.values[iterator.index]
                        iterator.index += 1
                        self.stack.append(value)
                        self.ip += 1
                    pending_after = instr

                elif op == "SETUP_TRY":
                    handler_ip = instr[1]
                    self.setup_try(handler_ip)
                    self.ip += 1
                    pending_after = instr

                elif op == "POP_TRY":
                    self.pop_try()
                    self.ip += 1
                    pending_after = instr

                elif op == "TO_BOOL":
                    self.stack.append(self.is_truthy(self.pop()))
                    self.ip += 1
                    pending_after = instr

                elif op == "NOT":
                    self.stack.append(not self.is_truthy(self.pop()))
                    self.ip += 1
                    pending_after = instr

                elif op == "NEG":
                    value = self.pop()
                    try:
                        self.stack.append(-value)
                    except TypeError:
                        self._unary_type_error("negate", value)
                    self.ip += 1
                    pending_after = instr

                elif op == "BUILD_LIST":
                    count = instr[1]
                    items = [self.pop() for _ in range(count)]
                    items.reverse()
                    self.stack.append(items)
                    self.ip += 1
                    pending_after = instr

                elif op == "BUILD_MAP":
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
                    pending_after = instr

                elif op == "BUILD_RECORD":
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
                    pending_after = instr

                elif op == "BUILD_MODULE":
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
                    pending_after = instr

                elif op == "INDEX":
                    idx = self.pop()
                    seq = self.pop()
                    self.stack.append(self.read_index(seq, idx))
                    self.ip += 1
                    pending_after = instr

                elif op == "INDEX_SET":
                    value = self.pop()
                    idx = self.pop()
                    seq = self.pop()
                    self.stack.append(self.write_index(seq, idx, value))
                    self.ip += 1
                    pending_after = instr

                elif op == "LOAD_FIELD":
                    name = instr[1]
                    obj = self.pop()
                    if isinstance(obj, NodusModule):
                        if not obj.has_export(name):
                            self.runtime_error("key", f"Missing module export: {name}")
                        self.stack.append(obj.get_export(name))
                        self.ip += 1
                        pending_after = instr
                        continue
                    if not isinstance(obj, Record):
                        self.runtime_error("type", "Field access is only supported on records")
                    if name not in obj.fields:
                        self.runtime_error("key", f"Missing record field: {name}")
                    self.stack.append(obj.fields[name])
                    self.ip += 1
                    pending_after = instr

                elif op == "STORE_FIELD":
                    name = instr[1]
                    value = self.pop()
                    obj = self.pop()
                    if isinstance(obj, NodusModule):
                        if not obj.has_export(name):
                            self.runtime_error("key", f"Missing module export: {name}")
                        self.stack.append(obj.set_export(name, value))
                        self.ip += 1
                        pending_after = instr
                        continue
                    if not isinstance(obj, Record):
                        self.runtime_error("type", "Field assignment is only supported on records")
                    obj.fields[name] = value
                    self.stack.append(value)
                    self.ip += 1
                    pending_after = instr

                elif op == "CALL":
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
                        if self.max_frames is not None and len(self.frames) + 1 > self.max_frames:
                            self.runtime_error("sandbox", "Call stack overflow")
                        self.frames.append(frame)
                        if self.profiler is not None and self.profiler.enabled:
                            self.profiler.enter_function(self.display_name(fn_name))
                        self.ip = fn.addr
                        pending_after = instr
                        continue

                    if fn_name in self.builtins:
                        status = self.call_builtin(fn_name, arg_count)
                        if status is not None:
                            return status
                        self.ip += 1
                        pending_after = instr
                        continue

                    locals_ = self.current_locals()
                    if (locals_ is not None and fn_name in locals_) or fn_name in self.globals:
                        callee = self.load_name(fn_name)
                        if isinstance(callee, ModuleFunction):
                            args = [self.pop() for _ in range(arg_count)]
                            args.reverse()
                            self.stack.append(callee(*args))
                            self.ip += 1
                            pending_after = instr
                            continue
                        self.call_closure(callee, arg_count)
                        pending_after = instr
                        continue
                    self.runtime_error("name", f"Undefined function: {fn_name}")

                elif op == "CALL_VALUE":
                    arg_count = instr[1]
                    args = [self.pop() for _ in range(arg_count)]
                    args.reverse()
                    callee = self.pop()
                    call_name = callee.function.display_name if isinstance(callee, Closure) else None
                    self.record_vm_call(call_name, "call_value")
                    if isinstance(callee, ModuleFunction):
                        self.stack.append(callee(*args))
                        self.ip += 1
                        pending_after = instr
                        continue
                    for arg in args:
                        self.stack.append(arg)
                    self.call_closure(callee, arg_count)
                    pending_after = instr
                    continue

                elif op == "MAKE_CLOSURE":
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
                    pending_after = instr

                elif op == "CALL_METHOD":
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
                            self.stack.append(method(*args))
                            self.ip += 1
                            pending_after = instr
                            continue
                        for arg in args:
                            self.stack.append(arg)
                        self.call_closure(method, arg_count)
                        pending_after = instr
                        continue
                    if not isinstance(obj, Record):
                        self.runtime_error("type", "Method calls are only supported on records")
                    if name not in obj.fields:
                        self.runtime_error("key", f"Missing record field: {name}")
                    method = obj.fields[name]
                    self.record_vm_call(name, "call_method")
                    if isinstance(method, ModuleFunction):
                        self.stack.append(method(*args))
                        self.ip += 1
                        pending_after = instr
                        continue
                    if obj.kind != "module":
                        self.stack.append(obj)
                        for arg in args:
                            self.stack.append(arg)
                        self.call_closure(method, arg_count + 1)
                    else:
                        for arg in args:
                            self.stack.append(arg)
                        self.call_closure(method, arg_count)
                    pending_after = instr
                    continue

                elif op == "THROW":
                    value = self.pop()
                    message = self.value_to_string(value, quote_strings=False)
                    self.runtime_error("runtime", message)

                elif op == "YIELD":
                    value = self.pop()
                    if self.current_coroutine is None:
                        self.runtime_error("runtime", "yield outside coroutine")
                    self.current_coroutine.state = "suspended"
                    self.save_current_coroutine_state(self.ip + 1)
                    return ("yield", value)

                elif op == "RETURN":
                    ret_value = self.pop()

                    if not self.frames:
                        self.runtime_error("runtime", "RETURN outside function")

                    frame = self.frames.pop()
                    self._profiler_exit_frame(frame)
                    self.record_vm_return(self.display_name(frame.fn_name))
                    while self.handler_stack and self.handler_stack[-1][2] > len(self.frames):
                        self.handler_stack.pop()
                    if self.current_coroutine is not None and frame.return_ip is None:
                        self.current_coroutine.state = "finished"
                        self.current_coroutine.ip = None
                        self.current_coroutine.stack = []
                        self.current_coroutine.frames = []
                        self.current_coroutine.handler_stack = []
                        self.current_coroutine.pending_iter_next = None
                        self.current_coroutine.pending_get_iter = False
                        return ("return", ret_value)
                    self.stack.append(ret_value)
                    self.ip = frame.return_ip
                    if self.pending_get_iter:
                        self.pending_get_iter = False
                        value = self.pop()
                        if isinstance(value, list):
                            self.stack.append(ListIterator(value))
                        elif isinstance(value, Record) and "__next__" in value.fields:
                            self.stack.append(value)
                        else:
                            self.runtime_error("type", "Value is not iterable")
                    if self.pending_iter_next is not None:
                        end_ip = self.pending_iter_next
                        self.pending_iter_next = None
                        value = self.pop()
                        if value is None:
                            if not self.stack:
                                self.runtime_error("runtime", "Iterator stack underflow")
                            self.stack.pop()
                            self.ip = end_ip
                        else:
                            self.stack.append(value)
                    pending_after = instr

                elif op == "HALT":
                    return ("halt", None)

                else:
                    self.runtime_error("runtime", f"Unknown opcode: {op}")
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
