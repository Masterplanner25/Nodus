import io
import json
import os
import tempfile

from nodus.lsp.server import LanguageServer


def _encode_message(payload: dict) -> bytes:
    body = json.dumps(payload).encode("utf-8")
    return f"Content-Length: {len(body)}\r\n\r\n".encode("ascii") + body


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
            raise AssertionError("Invalid LSP framing")
        body = stream.read(length)
        out.append(json.loads(body.decode("utf-8")))
    return out


def _run_session(messages: list[dict]) -> list[dict]:
    input_bytes = b"".join(_encode_message(message) for message in messages)
    output = io.BytesIO()
    server = LanguageServer(io.BytesIO(input_bytes), output)
    server.run()
    return _decode_messages(output.getvalue())


def _diagnostic_notifications(messages: list[dict]) -> list[dict]:
    return [message for message in messages if message.get("method") == "textDocument/publishDiagnostics"]


def _file_uri(path: str) -> str:
    return f"file:///{path.replace(os.sep, '/')}"


def test_syntax_errors_are_reported_with_locations():
    with tempfile.TemporaryDirectory() as td:
        path = os.path.join(td, "bad.nd")
        uri = _file_uri(path)
        messages = _run_session(
            [
                {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
                {
                    "jsonrpc": "2.0",
                    "method": "textDocument/didOpen",
                    "params": {"textDocument": {"uri": uri, "languageId": "nodus", "version": 1, "text": "let x =\n"}},
                },
                {"jsonrpc": "2.0", "id": 2, "method": "shutdown", "params": {}},
                {"jsonrpc": "2.0", "method": "exit", "params": {}},
            ]
        )
    diagnostics = _diagnostic_notifications(messages)
    assert len(diagnostics) == 1
    payload = diagnostics[0]["params"]["diagnostics"][0]
    assert diagnostics[0]["params"]["uri"] == uri
    assert payload["severity"] == 1
    assert payload["source"] == "nodus"
    assert payload["file"].endswith("bad.nd")
    assert payload["line"] == 1
    assert payload["column"] is not None


def test_cross_module_errors_publish_for_imported_file():
    with tempfile.TemporaryDirectory() as td:
        main_path = os.path.join(td, "main.nd")
        lib_path = os.path.join(td, "lib.nd")
        with open(lib_path, "w", encoding="utf-8") as handle:
            handle.write("export fn broken( {\n")
        uri = _file_uri(main_path)
        messages = _run_session(
            [
                {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
                {
                    "jsonrpc": "2.0",
                    "method": "textDocument/didOpen",
                    "params": {
                        "textDocument": {
                            "uri": uri,
                            "languageId": "nodus",
                            "version": 1,
                            "text": 'import "./lib.nd" as lib\nprint(1)\n',
                        }
                    },
                },
                {"jsonrpc": "2.0", "id": 2, "method": "shutdown", "params": {}},
                {"jsonrpc": "2.0", "method": "exit", "params": {}},
            ]
        )
    notifications = _diagnostic_notifications(messages)
    lib_notification = next(item for item in notifications if item["params"]["uri"].endswith("/lib.nd"))
    assert lib_notification["params"]["diagnostics"]
    assert "Expected ID" in lib_notification["params"]["diagnostics"][0]["message"]


def test_diagnostics_clear_after_fix():
    with tempfile.TemporaryDirectory() as td:
        path = os.path.join(td, "main.nd")
        uri = _file_uri(path)
        messages = _run_session(
            [
                {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
                {
                    "jsonrpc": "2.0",
                    "method": "textDocument/didOpen",
                    "params": {"textDocument": {"uri": uri, "languageId": "nodus", "version": 1, "text": "let x =\n"}},
                },
                {
                    "jsonrpc": "2.0",
                    "method": "textDocument/didChange",
                    "params": {
                        "textDocument": {"uri": uri, "version": 2},
                        "contentChanges": [{"text": "let x = 1\nprint(x)\n"}],
                    },
                },
                {"jsonrpc": "2.0", "id": 2, "method": "shutdown", "params": {}},
                {"jsonrpc": "2.0", "method": "exit", "params": {}},
            ]
        )
    notifications = [item for item in _diagnostic_notifications(messages) if item["params"]["uri"] == uri]
    assert notifications[0]["params"]["diagnostics"]
    assert notifications[-1]["params"]["diagnostics"] == []


def test_incremental_diagnostics_update_dependents():
    with tempfile.TemporaryDirectory() as td:
        main_path = os.path.join(td, "main.nd")
        util_path = os.path.join(td, "util.nd")
        main_uri = _file_uri(main_path)
        util_uri = _file_uri(util_path)
        with open(main_path, "w", encoding="utf-8") as handle:
            handle.write('import "./util.nd" as util\nprint(util.value)\n')
        with open(util_path, "w", encoding="utf-8") as handle:
            handle.write("export let value = 1\n")
        messages = _run_session(
            [
                {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
                {
                    "jsonrpc": "2.0",
                    "method": "textDocument/didOpen",
                    "params": {
                        "textDocument": {
                            "uri": main_uri,
                            "languageId": "nodus",
                            "version": 1,
                            "text": 'import "./util.nd" as util\nprint(util.value)\n',
                        }
                    },
                },
                {
                    "jsonrpc": "2.0",
                    "method": "textDocument/didOpen",
                    "params": {
                        "textDocument": {
                            "uri": util_uri,
                            "languageId": "nodus",
                            "version": 1,
                            "text": "export let value = 1\n",
                        }
                    },
                },
                {
                    "jsonrpc": "2.0",
                    "method": "textDocument/didChange",
                    "params": {
                        "textDocument": {"uri": util_uri, "version": 2},
                        "contentChanges": [{"text": "export let other = 1\n"}],
                    },
                },
                {"jsonrpc": "2.0", "id": 2, "method": "shutdown", "params": {}},
                {"jsonrpc": "2.0", "method": "exit", "params": {}},
            ]
        )
    notifications = _diagnostic_notifications(messages)
    main_updates = [item for item in notifications if item["params"]["uri"] == main_uri]
    util_updates = [item for item in notifications if item["params"]["uri"] == util_uri]
    assert main_updates[0]["params"]["diagnostics"] == []
    assert util_updates[0]["params"]["diagnostics"] == []
    dependent_update = next(item for item in reversed(main_updates) if item["params"]["diagnostics"])
    assert "has no member 'value'" in dependent_update["params"]["diagnostics"][0]["message"]
