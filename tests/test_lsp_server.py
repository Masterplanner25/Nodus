import io
import json
import os
import tempfile
import unittest

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


class LspServerTests(unittest.TestCase):
    def test_initialization_handshake(self):
        responses = _run_session(
            [
                {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
                {"jsonrpc": "2.0", "id": 2, "method": "shutdown", "params": {}},
                {"jsonrpc": "2.0", "method": "exit", "params": {}},
            ]
        )
        self.assertEqual(responses[0]["id"], 1)
        capabilities = responses[0]["result"]["capabilities"]
        self.assertEqual(capabilities["textDocumentSync"], 1)
        self.assertTrue(capabilities["hoverProvider"])
        self.assertTrue(capabilities["definitionProvider"])
        self.assertEqual(responses[1]["id"], 2)
        self.assertIsNone(responses[1]["result"])

    def test_invalid_code_publishes_diagnostics(self):
        with tempfile.TemporaryDirectory() as td:
            path = os.path.join(td, "bad.nd")
            uri = f"file:///{path.replace(os.sep, '/')}"
            responses = _run_session(
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
                                "text": "let x =\n",
                            }
                        },
                    },
                    {"jsonrpc": "2.0", "id": 2, "method": "shutdown", "params": {}},
                    {"jsonrpc": "2.0", "method": "exit", "params": {}},
                ]
            )
        diagnostics = [message for message in responses if message.get("method") == "textDocument/publishDiagnostics"][0]
        self.assertEqual(diagnostics["params"]["uri"], uri)
        published = diagnostics["params"]["diagnostics"]
        self.assertEqual(len(published), 1)
        self.assertIn("Unexpected token", published[0]["message"])
        self.assertEqual(published[0]["severity"], 1)
        self.assertIn("line", published[0])
        self.assertIn("column", published[0])

    def test_completion_returns_keywords_and_symbols(self):
        with tempfile.TemporaryDirectory() as td:
            path = os.path.join(td, "main.nd")
            uri = f"file:///{path.replace(os.sep, '/')}"
            source = (
                'import "std:strings" as s\n'
                "fn greet(name: string) -> string {\n"
                "    return name\n"
                "}\n"
                'let local_name = greet("Nodus")\n'
                "print(lo)\n"
                "\n"
            )
            responses = _run_session(
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
                                "text": source,
                            }
                        },
                    },
                    {
                        "jsonrpc": "2.0",
                        "id": 2,
                        "method": "textDocument/completion",
                        "params": {
                            "textDocument": {"uri": uri},
                            "position": {"line": 5, "character": 8},
                        },
                    },
                    {
                        "jsonrpc": "2.0",
                        "id": 3,
                        "method": "textDocument/completion",
                        "params": {
                            "textDocument": {"uri": uri},
                            "position": {"line": 6, "character": 0},
                        },
                    },
                    {"jsonrpc": "2.0", "id": 4, "method": "shutdown", "params": {}},
                    {"jsonrpc": "2.0", "method": "exit", "params": {}},
                ]
            )
        symbol_completion = [message for message in responses if message.get("id") == 2][0]["result"]["items"]
        keyword_completion = [message for message in responses if message.get("id") == 3][0]["result"]["items"]
        symbol_labels = {item["label"] for item in symbol_completion}
        keyword_labels = {item["label"] for item in keyword_completion}
        self.assertIn("local_name", symbol_labels)
        self.assertIn("greet", keyword_labels)
        self.assertIn("s", keyword_labels)
        self.assertIn("let", keyword_labels)

    def test_definition_resolves_imported_symbol(self):
        with tempfile.TemporaryDirectory() as td:
            lib_path = os.path.join(td, "lib.nd")
            main_path = os.path.join(td, "main.nd")
            with open(lib_path, "w", encoding="utf-8") as handle:
                handle.write("export fn greet(name: string) -> string { return name }\n")
            uri = f"file:///{main_path.replace(os.sep, '/')}"
            source = 'import { greet } from "./lib.nd"\nprint(greet("Nodus"))\n'
            responses = _run_session(
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
                                "text": source,
                            }
                        },
                    },
                    {
                        "jsonrpc": "2.0",
                        "id": 2,
                        "method": "textDocument/definition",
                        "params": {
                            "textDocument": {"uri": uri},
                            "position": {"line": 1, "character": 7},
                        },
                    },
                    {"jsonrpc": "2.0", "id": 3, "method": "shutdown", "params": {}},
                    {"jsonrpc": "2.0", "method": "exit", "params": {}},
                ]
            )
        definition = [message for message in responses if message.get("id") == 2][0]["result"]
        self.assertTrue(definition["uri"].endswith("/lib.nd"))
        self.assertEqual(definition["range"]["start"]["line"], 0)


if __name__ == "__main__":
    unittest.main()
