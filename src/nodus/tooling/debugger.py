"""Interactive debugger support for the Nodus VM."""

from dataclasses import dataclass


class DebuggerQuit(Exception):
    """Raised when the debugger requests VM termination."""


@dataclass
class PauseState:
    reason: str
    path: str | None
    line: int | None
    col: int | None


class Debugger:
    def __init__(self, input_fn=input, output_fn=print, start_paused: bool = False):
        self.input_fn = input_fn
        self.output_fn = output_fn
        self.start_paused = start_paused
        self.started = False
        self.breakpoints: set[int] = set()
        self.mode = "continue"
        self.next_depth: int | None = None
        self.next_steps = 0
        self.skip_ip: int | None = None
        self.breakpoint_latch: int | None = None

    def before_instruction(self, vm, instr: tuple):
        if self.skip_ip is not None and vm.ip != self.skip_ip:
            self.skip_ip = None

        loc = vm.current_loc()
        line = loc[1]
        if line != self.breakpoint_latch:
            self.breakpoint_latch = None

        if not self.started:
            self.started = True
            if self.start_paused:
                self.pause(vm, "start")
                return

        if self.skip_ip == vm.ip:
            return

        if line is not None and line in self.breakpoints and self.breakpoint_latch != line:
            self.breakpoint_latch = line
            self.pause(vm, f"breakpoint line {line}")

    def after_instruction(self, vm, instr: tuple):
        if self.mode == "step":
            self.pause(vm, "step")
            return

        if self.mode == "next":
            self.next_steps += 1
            if self.next_depth is not None and self.next_steps >= 1 and len(vm.frames) <= self.next_depth:
                self.pause(vm, "next")

    def pause(self, vm, reason: str):
        path, line, col = vm.current_loc()
        state = PauseState(reason=reason, path=path, line=line, col=col)
        self.output_fn(self.format_pause(state))
        while True:
            raw = self.input_fn("(nodusdb) ")
            cmd = raw.strip()
            if not cmd:
                continue
            if cmd == "step":
                self.mode = "step"
                self.next_depth = None
                self.next_steps = 0
                self.skip_ip = vm.ip
                return
            if cmd == "next":
                self.mode = "next"
                self.next_depth = len(vm.frames)
                self.next_steps = 0
                self.skip_ip = vm.ip
                return
            if cmd == "continue":
                self.mode = "continue"
                self.next_depth = None
                self.next_steps = 0
                self.skip_ip = vm.ip
                return
            if cmd == "stack":
                for line_text in self.format_stack(vm):
                    self.output_fn(line_text)
                continue
            if cmd == "locals":
                for line_text in self.format_locals(vm):
                    self.output_fn(line_text)
                continue
            if cmd.startswith("break"):
                parts = cmd.split()
                if len(parts) != 2 or not parts[1].isdigit():
                    self.output_fn("Usage: break <line>")
                    continue
                line_no = int(parts[1])
                self.breakpoints.add(line_no)
                self.output_fn(f"Breakpoint set at line {line_no}")
                continue
            if cmd == "quit":
                raise DebuggerQuit()
            self.output_fn(f"Unknown debugger command: {cmd}")

    def format_pause(self, state: PauseState) -> str:
        loc = self.format_location(state.path, state.line, state.col)
        return f"[debug] paused ({state.reason}) at {loc}"

    def format_location(self, path: str | None, line: int | None, col: int | None) -> str:
        if path and line is not None and col is not None:
            return f"{path}:{line}:{col}"
        if path and line is not None:
            return f"{path}:{line}"
        if line is not None:
            return f"line {line}"
        if path:
            return path
        return "<unknown>"

    def format_stack(self, vm) -> list[str]:
        current_path, current_line, _current_col = vm.current_loc()
        entries: list[str] = []
        if not vm.frames:
            entries.append(self.describe_frame("main", current_line))
            return entries

        first_call = vm.frames[0]
        entries.append(self.describe_frame("main", first_call.call_line))
        for i in range(1, len(vm.frames)):
            caller = vm.display_name(vm.frames[i - 1].fn_name)
            entries.append(self.describe_frame(caller, vm.frames[i].call_line))
        current_name = vm.display_name(vm.frames[-1].fn_name)
        entries.append(self.describe_frame(current_name, current_line, path=current_path))
        return entries

    def describe_frame(self, name: str, line: int | None, path: str | None = None) -> str:
        if path and line is not None:
            return f"{name}() line {line} ({path})"
        if line is not None:
            return f"{name}() line {line}"
        return f"{name}()"

    def format_locals(self, vm) -> list[str]:
        locals_ = vm.current_locals()
        if locals_ is None:
            values = vm.globals
        else:
            values = locals_
        if not values:
            return ["<no locals>"]

        out: list[str] = []
        for name in sorted(values):
            value = values[name]
            if hasattr(value, "value"):
                value = value.value
            out.append(f"{name} = {vm.value_to_string(value, quote_strings=True)}")
        return out
