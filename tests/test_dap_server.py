import io
import json
import os
import tempfile
import time
import unittest

from nodus.dap.server import DebugAdapterServer


def _decode_messages(data: bytes) -> list[dict]:
    out: list[dict] = []
    stream = io.BytesIO(data)
    while True:
        header = stream.readline()
        if not header:
            break
        if not header.strip():
            continue
        length = int(header.decode("ascii").split(":", 1)[1].strip())
        blank = stream.readline()
        if blank not in {b"\r\n", b"\n"}:
            raise AssertionError("Invalid DAP framing")
        body = stream.read(length)
        out.append(json.loads(body.decode("utf-8")))
    return out


class _Client:
    def __init__(self):
        self.output = io.BytesIO()
        self.server = DebugAdapterServer(io.BytesIO(), self.output)
        self.offset = 0
        self.seq = 1

    def request(self, command: str, arguments: dict | None = None) -> list[dict]:
        self.server.handle_message(
            {
                "seq": self.seq,
                "type": "request",
                "command": command,
                "arguments": arguments or {},
            }
        )
        self.seq += 1
        return self.drain()

    def drain(self) -> list[dict]:
        data = self.output.getvalue()
        chunk = data[self.offset :]
        self.offset = len(data)
        return _decode_messages(chunk)


class DapServerTests(unittest.TestCase):
    def test_initialize_handshake(self):
        client = _Client()
        messages = client.request("initialize")
        response = [message for message in messages if message["type"] == "response"][0]
        events = [message for message in messages if message["type"] == "event"]
        self.assertTrue(response["success"])
        self.assertEqual(response["command"], "initialize")
        self.assertTrue(response["body"]["supportsPauseRequest"])
        self.assertTrue(any(message["event"] == "initialized" for message in events))

    def test_breakpoint_registration_and_stop(self):
        with tempfile.TemporaryDirectory() as td:
            path = os.path.join(td, "main.nd")
            with open(path, "w", encoding="utf-8") as handle:
                handle.write("let x = 1\nx = x + 1\nprint(x)\n")

            client = _Client()
            client.request("initialize")
            client.request("launch", {"program": path})
            client.request("setBreakpoints", {"source": {"path": path}, "lines": [2]})

            debugger = client.server.session.debugger
            assert debugger is not None
            previous = debugger.stop_count
            client.request("continue")
            self.assertTrue(debugger.wait_for_stop(previous, timeout=1.0))
            messages = client.drain()

            self.assertIn((os.path.abspath(path), 2), debugger.breakpoints)
            stopped = [message for message in messages if message["type"] == "event" and message["event"] == "stopped"]
            self.assertTrue(stopped)
            self.assertEqual(stopped[-1]["body"]["reason"], "breakpoint")

            client.request("disconnect")

    def test_step_execution_emits_step_stop(self):
        with tempfile.TemporaryDirectory() as td:
            path = os.path.join(td, "step.nd")
            with open(path, "w", encoding="utf-8") as handle:
                handle.write("let x = 1\nx = x + 1\nprint(x)\n")

            client = _Client()
            client.request("initialize")
            client.request("launch", {"program": path})

            debugger = client.server.session.debugger
            assert debugger is not None
            previous = debugger.stop_count
            client.request("stepIn")
            self.assertTrue(debugger.wait_for_stop(previous, timeout=1.0))
            messages = client.drain()

            stopped = [message for message in messages if message["type"] == "event" and message["event"] == "stopped"]
            self.assertTrue(stopped)
            self.assertEqual(stopped[-1]["body"]["reason"], "step")

            client.request("disconnect")

    def test_variable_inspection_exposes_arguments_and_locals(self):
        with tempfile.TemporaryDirectory() as td:
            path = os.path.join(td, "vars.nd")
            with open(path, "w", encoding="utf-8") as handle:
                handle.write(
                    "fn foo(a) {\n"
                    "    let x = a + 1\n"
                    "    print(x)\n"
                    "}\n"
                    "foo(4)\n"
                )

            client = _Client()
            client.request("initialize")
            client.request("launch", {"program": path})
            client.request("setBreakpoints", {"source": {"path": path}, "lines": [3]})

            debugger = client.server.session.debugger
            assert debugger is not None
            previous = debugger.stop_count
            client.request("continue")
            self.assertTrue(debugger.wait_for_stop(previous, timeout=1.0))
            client.drain()

            stack_messages = client.request("stackTrace", {})
            stack_response = [message for message in stack_messages if message["type"] == "response"][0]
            frame_id = stack_response["body"]["stackFrames"][0]["id"]
            self.assertEqual(stack_response["body"]["stackFrames"][0]["name"], "foo")

            scope_messages = client.request("scopes", {"frameId": frame_id})
            scope_response = [message for message in scope_messages if message["type"] == "response"][0]
            scopes = scope_response["body"]["scopes"]
            args_ref = [scope["variablesReference"] for scope in scopes if scope["name"] == "Arguments"][0]
            locals_ref = [scope["variablesReference"] for scope in scopes if scope["name"] == "Locals"][0]

            args_messages = client.request("variables", {"variablesReference": args_ref})
            args_response = [message for message in args_messages if message["type"] == "response"][0]
            local_messages = client.request("variables", {"variablesReference": locals_ref})
            local_response = [message for message in local_messages if message["type"] == "response"][0]

            args = {entry["name"]: entry["value"] for entry in args_response["body"]["variables"]}
            locals_ = {entry["name"]: entry["value"] for entry in local_response["body"]["variables"]}
            self.assertEqual(args["a"], "4.0")
            self.assertEqual(locals_["x"], "5.0")

            client.request("disconnect")


if __name__ == "__main__":
    unittest.main()
