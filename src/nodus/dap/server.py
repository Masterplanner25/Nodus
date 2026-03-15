"""Minimal stdio Debug Adapter Protocol server for Nodus."""

from __future__ import annotations

import io
import json
import os
import sys
import threading
from contextlib import redirect_stderr, redirect_stdout
from dataclasses import dataclass
from typing import BinaryIO

from nodus.runtime.debugger import Debugger, DebuggerQuit, PauseState
from nodus.runtime.errors import format_error_payload
from nodus.runtime.module_loader import ModuleLoader
from nodus.vm.vm import VM


def _read_message(stream: BinaryIO) -> dict | None:
    headers: dict[str, str] = {}
    while True:
        line = stream.readline()
        if not line:
            return None
        if line in {b"\r\n", b"\n"}:
            break
        decoded = line.decode("utf-8").strip()
        if ":" not in decoded:
            continue
        key, value = decoded.split(":", 1)
        headers[key.strip().lower()] = value.strip()
    length_text = headers.get("content-length")
    if not length_text:
        return None
    body = stream.read(int(length_text))
    if not body:
        return None
    return json.loads(body.decode("utf-8"))


def _write_message(stream: BinaryIO, payload: dict) -> None:
    body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    header = f"Content-Length: {len(body)}\r\n\r\n".encode("ascii")
    stream.write(header)
    stream.write(body)
    stream.flush()


def _resolve_program_path(params: dict) -> str:
    program = params.get("program")
    if not isinstance(program, str) or not program.strip():
        raise ValueError("launch requires a program path")
    return os.path.abspath(program)


def _resolve_project_root(params: dict) -> str | None:
    project_root = params.get("projectRoot")
    if project_root is None:
        return None
    if not isinstance(project_root, str) or not os.path.isdir(project_root):
        raise ValueError(f"Invalid projectRoot: {project_root}")
    return os.path.abspath(project_root)


def _collect_import_state(project_root: str | None) -> dict | None:
    if project_root is None:
        return None
    return {
        "loaded": set(),
        "loading": set(),
        "exports": {},
        "modules": {},
        "module_ids": {},
        "project_root": project_root,
    }


@dataclass
class _FrameScope:
    kind: str
    values: list[tuple[str, object]]


class _ProtocolWriter(io.TextIOBase):
    def __init__(self, session: "DebugSession", category: str):
        self.session = session
        self.category = category

    def write(self, text: str) -> int:
        if text:
            self.session.server.send_event("output", {"category": self.category, "output": text})
        return len(text)

    def flush(self) -> None:
        return None


class ProgrammaticDebugger(Debugger):
    def __init__(self, session: "DebugSession"):
        super().__init__(input_fn=lambda _prompt: "", output_fn=lambda _line: None, start_paused=True)
        self.session = session
        self.condition = threading.Condition()
        self.current_vm = None
        self.stop_count = 0
        self.terminated = False
        self.last_reason: str | None = None
        self.last_pause_state: PauseState | None = None
        self.waiting = False

    def _pause(self, vm, frame, reason: str) -> None:
        locals_view = self.session.get_locals(vm)
        state = PauseState(
            reason=reason,
            module=frame.module,
            line=frame.line,
            col=frame.col,
            function=frame.function,
            locals=locals_view,
        )
        self.last_pause = state
        with self.condition:
            self.current_vm = vm
            self.last_pause_state = state
            self.last_reason = reason
            self.stop_count += 1
            self.waiting = True
            self.condition.notify_all()
        self.session.on_paused(reason, state)
        with self.condition:
            while self.waiting and not self.terminated:
                self.condition.wait()
            if self.terminated:
                raise DebuggerQuit()

    def mark_terminated(self) -> None:
        with self.condition:
            self.terminated = True
            self.condition.notify_all()

    def wait_for_stop(self, previous_count: int, timeout: float = 1.0) -> bool:
        with self.condition:
            if self.stop_count > previous_count or self.terminated:
                return True
            self.condition.wait(timeout)
            return self.stop_count > previous_count or self.terminated

    def _resume(self, action: str) -> None:
        with self.condition:
            vm = self.current_vm
            if vm is None:
                return
            if action == "continue":
                self.resume_continue(vm)
            elif action == "stepIn":
                self.resume_step_in(vm)
            elif action == "next":
                self.resume_step_over(vm)
            elif action == "stepOut":
                self.resume_step_out(vm)
            self.waiting = False
            self.condition.notify_all()

    def continue_execution(self) -> None:
        self._resume("continue")

    def step_in_execution(self) -> None:
        self._resume("stepIn")

    def step_over_execution(self) -> None:
        self._resume("next")

    def step_out_execution(self) -> None:
        self._resume("stepOut")

    def pause_execution(self) -> None:
        self.request_pause()

    def terminate_execution(self) -> None:
        self.request_terminate()
        with self.condition:
            self.terminated = True
            self.waiting = False
            self.condition.notify_all()


class DebugSession:
    def __init__(self, server: "DebugAdapterServer"):
        self.server = server
        self.program: str | None = None
        self.project_root: str | None = None
        self.vm: VM | None = None
        self.debugger: ProgrammaticDebugger | None = None
        self.thread: threading.Thread | None = None
        self.breakpoint_lines: dict[str, set[int]] = {}
        self.frame_handles: dict[int, int] = {}
        self.scope_handles: dict[int, _FrameScope] = {}
        self.next_scope_handle = 1
        self._terminated_sent = False

    def launch(self, params: dict) -> None:
        program = _resolve_program_path(params)
        if not os.path.isfile(program):
            raise ValueError(f"File not found: {program}")
        project_root = _resolve_project_root(params)
        with open(program, "r", encoding="utf-8") as handle:
            source = handle.read()
        debugger = ProgrammaticDebugger(self)
        for path, lines in self.breakpoint_lines.items():
            for line in lines:
                debugger.set_breakpoint(path, line)
        vm = VM(
            [],
            {},
            code_locs=[],
            source_path=program,
            debug=True,
            debugger=debugger,
        )
        loader = ModuleLoader(project_root=project_root, vm=vm, debugger=debugger)
        bytecode, functions, code_locs = loader.compile_only(
            source,
            module_name=program,
            base_dir=os.path.dirname(os.path.abspath(program)) if program else os.getcwd(),
        )
        vm.reset_program(bytecode, functions, code_locs=code_locs, source_path=program)
        vm.source_code = source
        self.program = program
        self.project_root = project_root
        self.vm = vm
        self.debugger = debugger
        self.thread = threading.Thread(target=self._run_vm, name="nodus-dap", daemon=True)
        self.thread.start()
        debugger.wait_for_stop(0, timeout=1.0)

    def _run_vm(self) -> None:
        if self.vm is None or self.debugger is None:
            return
        stdout_proxy = _ProtocolWriter(self, "stdout")
        stderr_proxy = _ProtocolWriter(self, "stderr")
        try:
            with redirect_stdout(stdout_proxy), redirect_stderr(stderr_proxy):
                self.vm.run()
        except DebuggerQuit:
            pass
        except Exception as err:
            self.server.send_event("output", {"category": "stderr", "output": f"{format_error_payload({'message': str(err)})}\n"})
        finally:
            self.debugger.mark_terminated()
            self._send_terminated()

    def _send_terminated(self) -> None:
        if self._terminated_sent:
            return
        self._terminated_sent = True
        self.server.send_event("terminated", {})

    def on_paused(self, reason: str, state: PauseState) -> None:
        reason_map = {
            "start": "entry",
            "breakpoint": "breakpoint",
            "pause": "pause",
            "step": "step",
            "next": "step",
            "stepOut": "step",
        }
        body = {
            "reason": reason_map.get(reason, "pause"),
            "threadId": 1,
            "allThreadsStopped": True,
        }
        if state.line is not None:
            body["line"] = state.line
        self.server.send_event("stopped", body)

    def disconnect(self) -> None:
        if self.debugger is not None:
            self.debugger.terminate_execution()
        if self.thread is not None:
            self.thread.join(timeout=1.0)
        self._send_terminated()

    def set_breakpoints(self, source_path: str, lines: list[int]) -> list[dict]:
        normalized = os.path.abspath(source_path)
        previous = self.breakpoint_lines.get(normalized, set())
        self.breakpoint_lines[normalized] = set(lines)
        if self.debugger is not None:
            for line in previous - self.breakpoint_lines[normalized]:
                self.debugger.clear_breakpoint(normalized, line)
            for line in self.breakpoint_lines[normalized] - previous:
                self.debugger.set_breakpoint(normalized, line)
        return [{"verified": True, "line": line} for line in lines]

    def continue_execution(self) -> None:
        if self.debugger is not None:
            self.debugger.continue_execution()

    def pause_execution(self) -> None:
        if self.debugger is not None:
            self.debugger.pause_execution()

    def step_in_execution(self) -> None:
        if self.debugger is not None:
            self.debugger.step_in_execution()

    def step_over_execution(self) -> None:
        if self.debugger is not None:
            self.debugger.step_over_execution()

    def step_out_execution(self) -> None:
        if self.debugger is not None:
            self.debugger.step_out_execution()

    def _collect_frames(self) -> list[dict]:
        if self.vm is None:
            return []
        if not self.vm.frames:
            path, line, col = self.vm.current_loc()
            return [{"name": "main", "path": path or self.program, "line": line or 1, "col": col or 1, "locals": self.vm.globals, "params": []}]
        frames = self.vm.reflection_frames()
        out: list[dict] = []
        for index in range(len(frames)):
            frame = frames[-1 - index]
            fn = frame.closure.function if frame.closure is not None else self.vm.functions.get(frame.fn_name)
            module_path = None
            if fn is not None and 0 <= fn.addr < len(self.vm.code_locs):
                module_path = self.vm.code_locs[fn.addr][0]
            if index == 0 and len(frames) == len(self.vm.frames):
                current_path, current_line, current_col = self.vm.current_loc()
                line = current_line
                col = current_col
                path = current_path or module_path or self.program
            else:
                line = frame.call_line
                col = frame.call_col
                path = frame.call_path or module_path or self.program
            # Merge dict-based locals and slot-indexed locals_array for full view
            merged_locals: dict = dict(frame.locals)
            if frame.locals_array is not None and frame.locals_name_to_slot is not None:
                for var_name, slot in frame.locals_name_to_slot.items():
                    arr_val = frame.locals_array[slot]
                    if hasattr(arr_val, "value"):
                        arr_val = arr_val.value
                    merged_locals[var_name] = arr_val
            out.append(
                {
                    "name": self.vm.display_name(frame.fn_name),
                    "path": path or self.program,
                    "line": line or 1,
                    "col": col or 1,
                    "locals": merged_locals,
                    "params": list(fn.params) if fn is not None else [],
                }
            )
        return out

    def stack_trace(self) -> list[dict]:
        frames = self._collect_frames()
        self.frame_handles = {}
        out: list[dict] = []
        for index, frame in enumerate(frames, start=1):
            self.frame_handles[index] = index - 1
            out.append(
                {
                    "id": index,
                    "name": frame["name"],
                    "source": {"path": frame["path"], "name": os.path.basename(frame["path"])},
                    "line": frame["line"],
                    "column": frame["col"],
                }
            )
        return out

    def scopes(self, frame_id: int) -> list[dict]:
        frame_index = self.frame_handles.get(frame_id)
        frames = self._collect_frames()
        if frame_index is None or frame_index >= len(frames):
            raise ValueError(f"Unknown frame id: {frame_id}")
        frame = frames[frame_index]
        values = frame["locals"] or {}
        params = set(frame["params"])
        arguments = [(name, values[name]) for name in frame["params"] if name in values]
        locals_ = [(name, value) for name, value in sorted(values.items()) if name not in params]
        scopes: list[dict] = []
        if arguments:
            handle = self._store_scope("Arguments", arguments)
            scopes.append({"name": "Arguments", "presentationHint": "arguments", "variablesReference": handle, "expensive": False})
        handle = self._store_scope("Locals", locals_)
        scopes.append({"name": "Locals", "presentationHint": "locals", "variablesReference": handle, "expensive": False})
        return scopes

    def _store_scope(self, kind: str, values: list[tuple[str, object]]) -> int:
        handle = self.next_scope_handle
        self.next_scope_handle += 1
        self.scope_handles[handle] = _FrameScope(kind=kind, values=values)
        return handle

    def variables(self, variables_reference: int) -> list[dict]:
        scope = self.scope_handles.get(variables_reference)
        if scope is None:
            raise ValueError(f"Unknown variables reference: {variables_reference}")
        return [
            {
                "name": name,
                "value": self.value_to_string(value),
                "variablesReference": 0,
            }
            for name, value in scope.values
        ]

    def get_locals(self, vm: VM) -> dict:
        values = vm.current_locals()
        if values is None:
            values = vm.globals
        out: dict[str, object] = {}
        for name, value in (values or {}).items():
            out[name] = getattr(value, "value", value)
        return out

    def value_to_string(self, value: object) -> str:
        if self.vm is None:
            return str(value)
        return self.vm.value_to_string(getattr(value, "value", value), quote_strings=True)


class DebugAdapterServer:
    def __init__(self, input_stream: BinaryIO | None = None, output_stream: BinaryIO | None = None):
        self.input_stream = input_stream if input_stream is not None else sys.stdin.buffer
        self.output_stream = output_stream if output_stream is not None else sys.stdout.buffer
        self.output_lock = threading.Lock()
        self.exit_code = 0
        self.seq = 1
        self.session = DebugSession(self)

    def run(self) -> int:
        while True:
            message = _read_message(self.input_stream)
            if message is None:
                break
            if self.handle_message(message):
                break
        return self.exit_code

    def handle_message(self, message: dict) -> bool:
        if message.get("type") != "request":
            return False
        command = message.get("command")
        request_seq = message.get("seq")
        arguments = message.get("arguments", {})
        try:
            if command == "initialize":
                self.send_response(
                    request_seq,
                    command,
                    {
                        "supportsConfigurationDoneRequest": False,
                        "supportsPauseRequest": True,
                        "supportsStepInTargetsRequest": False,
                    },
                )
                self.send_event("initialized", {})
                return False
            if command == "launch":
                self.session.launch(arguments)
                self.send_response(request_seq, command, {})
                return False
            if command == "disconnect":
                self.session.disconnect()
                self.send_response(request_seq, command, {})
                return True
            if command == "setBreakpoints":
                source = arguments.get("source", {})
                source_path = source.get("path")
                if not isinstance(source_path, str) or not source_path:
                    raise ValueError("setBreakpoints requires source.path")
                if "lines" in arguments:
                    lines = [int(line) for line in arguments.get("lines", [])]
                else:
                    lines = [int(entry.get("line")) for entry in arguments.get("breakpoints", []) if entry.get("line") is not None]
                body = {"breakpoints": self.session.set_breakpoints(source_path, lines)}
                self.send_response(request_seq, command, body)
                return False
            if command == "continue":
                self.session.continue_execution()
                self.send_response(request_seq, command, {"allThreadsContinued": True})
                return False
            if command == "pause":
                self.session.pause_execution()
                self.send_response(request_seq, command, {})
                return False
            if command == "next":
                self.session.step_over_execution()
                self.send_response(request_seq, command, {})
                return False
            if command == "stepIn":
                self.session.step_in_execution()
                self.send_response(request_seq, command, {})
                return False
            if command == "stepOut":
                self.session.step_out_execution()
                self.send_response(request_seq, command, {})
                return False
            if command == "stackTrace":
                frames = self.session.stack_trace()
                self.send_response(request_seq, command, {"stackFrames": frames, "totalFrames": len(frames)})
                return False
            if command == "scopes":
                frame_id = int(arguments.get("frameId"))
                self.send_response(request_seq, command, {"scopes": self.session.scopes(frame_id)})
                return False
            if command == "variables":
                variables_reference = int(arguments.get("variablesReference"))
                self.send_response(request_seq, command, {"variables": self.session.variables(variables_reference)})
                return False
            self.send_error(request_seq, command, f"Unsupported command: {command}")
            return False
        except Exception as err:
            self.send_error(request_seq, command, str(err))
            return command == "disconnect"

    def _send(self, payload: dict) -> None:
        with self.output_lock:
            payload = {"seq": self.seq, **payload}
            self.seq += 1
            _write_message(self.output_stream, payload)

    def send_response(self, request_seq: int, command: str, body: dict) -> None:
        self._send(
            {
                "type": "response",
                "request_seq": request_seq,
                "success": True,
                "command": command,
                "body": body,
            }
        )

    def send_error(self, request_seq: int, command: str | None, message: str) -> None:
        self._send(
            {
                "type": "response",
                "request_seq": request_seq,
                "success": False,
                "command": command,
                "message": message,
            }
        )

    def send_event(self, event: str, body: dict) -> None:
        self._send({"type": "event", "event": event, "body": body})


def run_stdio_server() -> int:
    return DebugAdapterServer().run()


if __name__ == "__main__":
    raise SystemExit(run_stdio_server())
