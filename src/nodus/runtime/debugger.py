"""Interactive debugger support for the Nodus VM."""

from __future__ import annotations

import os
from dataclasses import dataclass

from nodus.runtime.diagnostics import LangRuntimeError

STEP_IN = "step_in"
STEP_OVER = "step_over"
STEP_OUT = "step_out"
CONTINUE = "continue"


class DebuggerQuit(Exception):
    """Raised when the debugger requests VM termination."""


@dataclass
class PauseState:
    reason: str
    module: str | None
    line: int | None
    col: int | None
    function: str
    locals: dict | None


@dataclass
class DebuggerFrame:
    event: str
    module: str | None
    line: int | None
    col: int | None
    function: str
    locals: dict | None
    depth: int
    ip: int


@dataclass
class StackFrameInfo:
    function: str
    line: int | None
    module: str | None


def get_stack(vm) -> list[StackFrameInfo]:
    current_path, current_line, _current_col = vm.current_loc()
    entries: list[StackFrameInfo] = []
    if not vm.frames:
        entries.append(StackFrameInfo("main", current_line, current_path))
        return entries

    first_call = vm.frames[0]
    entries.append(StackFrameInfo("main", first_call.call_line, first_call.call_path or vm.source_path))
    for i in range(1, len(vm.frames)):
        caller = vm.display_name(vm.frames[i - 1].fn_name)
        entries.append(StackFrameInfo(caller, vm.frames[i].call_line, vm.frames[i].call_path))
    current_name = vm.display_name(vm.frames[-1].fn_name)
    entries.append(StackFrameInfo(current_name, current_line, current_path))
    return entries


def get_locals(vm) -> dict:
    locals_ = vm.current_locals()
    values = locals_ if locals_ is not None else vm.globals
    if not values:
        return {}
    out: dict = {}
    for name, value in values.items():
        if hasattr(value, "value"):
            value = value.value
        out[name] = value
    return out


class Debugger:
    def __init__(self, input_fn=input, output_fn=print, start_paused: bool = False):
        self.input_fn = input_fn
        self.output_fn = output_fn
        self.start_paused = start_paused
        self.started = False
        self.breakpoints: set[tuple[str | None, int]] = set()
        self.mode = CONTINUE
        self.next_depth: int | None = None
        self.next_steps = 0
        self.skip_ip: int | None = None
        self.breakpoint_latch: tuple[str | None, int] | None = None
        self.last_pause: PauseState | None = None
        self.pause_requested = False
        self.terminate_requested = False

    def set_breakpoint(self, module: str | None, line: int) -> None:
        self.breakpoints.add((module, line))

    def clear_breakpoint(self, module: str | None, line: int) -> None:
        self.breakpoints.discard((module, line))

    def resume_continue(self, vm) -> None:
        self.mode = CONTINUE
        self.next_depth = None
        self.next_steps = 0
        self.skip_ip = vm.ip
        self.pause_requested = False

    def resume_step_in(self, vm) -> None:
        self.mode = STEP_IN
        self.next_depth = None
        self.next_steps = 0
        self.skip_ip = vm.ip
        self.pause_requested = False

    def resume_step_over(self, vm) -> None:
        self.mode = STEP_OVER
        self.next_depth = len(vm.frames)
        self.next_steps = 0
        self.skip_ip = vm.ip
        self.pause_requested = False

    def resume_step_out(self, vm) -> None:
        if not vm.frames:
            self.resume_continue(vm)
            return
        self.mode = STEP_OUT
        self.next_depth = max(len(vm.frames) - 1, 0)
        self.next_steps = 0
        self.skip_ip = vm.ip
        self.pause_requested = False

    def request_pause(self) -> None:
        self.pause_requested = True

    def request_terminate(self) -> None:
        self.terminate_requested = True

    def before_instruction(self, vm, instr: tuple) -> None:
        if self.terminate_requested:
            raise DebuggerQuit()
        if self.skip_ip is not None and vm.ip != self.skip_ip:
            self.skip_ip = None

        loc = vm.current_loc()
        module, line, col = loc
        if self.breakpoint_latch != (module, line):
            self.breakpoint_latch = None

        if not self.started:
            self.started = True
            if self.start_paused:
                frame = self._build_frame(vm, module, line, col, event="before")
                self._pause(vm, frame, "start")
                return

        if self.skip_ip == vm.ip:
            return

        frame = self._build_frame(vm, module, line, col, event="before")
        if self.pause_requested:
            self.pause_requested = False
            self._pause(vm, frame, "pause")
            return
        if self.should_pause(frame):
            self._pause(vm, frame, "breakpoint")

    def after_instruction(self, vm, instr: tuple) -> None:
        if self.terminate_requested:
            raise DebuggerQuit()
        module, line, col = vm.current_loc()
        frame = self._build_frame(vm, module, line, col, event="after")
        if self.should_pause(frame):
            if self.mode == STEP_IN:
                reason = "step"
            elif self.mode == STEP_OUT:
                reason = "stepOut"
            else:
                reason = "next"
            self._pause(vm, frame, reason)

    def should_pause(self, frame: DebuggerFrame) -> bool:
        if frame.event == "before":
            if frame.line is not None and (frame.module, frame.line) in self.breakpoints:
                if self.breakpoint_latch != (frame.module, frame.line):
                    self.breakpoint_latch = (frame.module, frame.line)
                    return True
            return False

        if self.mode == STEP_IN:
            return True

        if self.mode == STEP_OVER:
            self.next_steps += 1
            if self.next_depth is not None and self.next_steps >= 1 and frame.depth <= self.next_depth:
                return True
        if self.mode == STEP_OUT:
            self.next_steps += 1
            if self.next_depth is not None and self.next_steps >= 1 and frame.depth <= self.next_depth:
                return True

        return False

    def _build_frame(self, vm, module: str | None, line: int | None, col: int | None, *, event: str) -> DebuggerFrame:
        function = vm.display_name(vm.frames[-1].fn_name) if vm.frames else "main"
        locals_ = vm.current_locals()
        depth = len(vm.frames)
        return DebuggerFrame(
            event=event,
            module=module,
            line=line,
            col=col,
            function=function,
            locals=locals_,
            depth=depth,
            ip=vm.ip,
        )

    def _pause(self, vm, frame: DebuggerFrame, reason: str) -> None:
        locals_view = get_locals(vm)
        state = PauseState(
            reason=reason,
            module=frame.module,
            line=frame.line,
            col=frame.col,
            function=frame.function,
            locals=locals_view,
        )
        self.last_pause = state
        self.output_fn(self.format_pause(state))
        while True:
            raw = self.input_fn("(nodusdb) ")
            cmd = raw.strip()
            if not cmd:
                continue
            if cmd == "step":
                self.resume_step_in(vm)
                return
            if cmd == "next":
                self.resume_step_over(vm)
                return
            if cmd in {"out", "stepout"}:
                self.resume_step_out(vm)
                return
            if cmd in {"continue", "run"}:
                self.resume_continue(vm)
                return
            if cmd == "stack":
                for line_text in self.format_stack(vm):
                    self.output_fn(line_text)
                continue
            if cmd == "locals":
                for line_text in self.format_locals(vm):
                    self.output_fn(line_text)
                continue
            if cmd.startswith("print"):
                expr = cmd[len("print") :].strip()
                if not expr:
                    self.output_fn("Usage: print <variable>")
                    continue
                self.output_fn(self.format_value(vm, expr))
                continue
            if cmd.startswith("break"):
                if self._handle_break(vm, cmd):
                    continue
                self.output_fn("Usage: break <file>:<line> or break <line>")
                continue
            if cmd == "quit":
                raise DebuggerQuit()
            self.output_fn(f"Unknown debugger command: {cmd}")

    def _handle_break(self, vm, cmd: str) -> bool:
        parts = cmd.split(maxsplit=1)
        if len(parts) != 2:
            return False
        target = parts[1].strip()
        if target.isdigit():
            line_no = int(target)
            module = self._current_module(vm)
            if module is None:
                self.output_fn("No current module to bind breakpoint.")
                return True
            self.set_breakpoint(module, line_no)
            self.output_fn(f"Breakpoint set at {module}:{line_no}")
            return True
        file_part, line_no = self._parse_file_line(target)
        if file_part is None or line_no is None:
            return False
        module = self._resolve_module_path(vm, file_part)
        self.set_breakpoint(module, line_no)
        self.output_fn(f"Breakpoint set at {module}:{line_no}")
        return True

    def _parse_file_line(self, target: str) -> tuple[str | None, int | None]:
        if ":" not in target:
            return None, None
        file_text, line_text = target.rsplit(":", 1)
        if not line_text.isdigit():
            return None, None
        return file_text, int(line_text)

    def _current_module(self, vm) -> str | None:
        module, _line, _col = vm.current_loc()
        if module:
            return module
        return vm.source_path

    def _resolve_module_path(self, vm, file_text: str) -> str:
        if file_text.startswith("<") and file_text.endswith(">"):
            return file_text
        if os.path.isabs(file_text):
            return file_text
        base_path = self._current_module(vm)
        if base_path and os.path.isabs(base_path):
            base_dir = os.path.dirname(base_path)
            return os.path.abspath(os.path.join(base_dir, file_text))
        return os.path.abspath(file_text)

    def format_pause(self, state: PauseState) -> str:
        loc = self.format_location(state.module, state.line, state.col)
        return f"[debug] paused ({state.reason}) at {loc} in {state.function}()"

    def format_location(self, module: str | None, line: int | None, col: int | None) -> str:
        if module and line is not None and col is not None:
            return f"{module}:{line}:{col}"
        if module and line is not None:
            return f"{module}:{line}"
        if line is not None:
            return f"line {line}"
        if module:
            return module
        return "<unknown>"

    def format_stack(self, vm) -> list[str]:
        entries = get_stack(vm)
        out: list[str] = []
        for entry in entries:
            out.append(self.describe_frame(entry.function, entry.line, path=entry.module))
        return out

    def describe_frame(self, name: str, line: int | None, path: str | None = None) -> str:
        if path and line is not None:
            return f"{name}() line {line} ({path})"
        if line is not None:
            return f"{name}() line {line}"
        return f"{name}()"

    def format_locals(self, vm) -> list[str]:
        values = get_locals(vm)
        if not values:
            return ["<no locals>"]

        out: list[str] = []
        for name in sorted(values):
            value = values[name]
            out.append(f"{name} = {vm.value_to_string(value, quote_strings=True)}")
        return out

    def format_value(self, vm, name: str) -> str:
        try:
            value = self._resolve_value(vm, name)
        except LangRuntimeError as err:
            return f"<error> {err}"
        return vm.value_to_string(value, quote_strings=True)

    def _resolve_value(self, vm, name: str):
        locals_ = vm.current_locals()
        if locals_ is not None and name in locals_:
            value = locals_[name]
            if hasattr(value, "value"):
                return value.value
            return value
        if name in vm.globals:
            value = vm.globals[name]
            if hasattr(value, "value"):
                return value.value
            return value
        return vm.load_name(name)
