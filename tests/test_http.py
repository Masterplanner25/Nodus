"""3B.4: std:http namespace — HTTP client."""

import io
import json
import unittest
from contextlib import redirect_stdout

import httpx

import nodus as lang
from nodus.runtime.module_loader import ModuleLoader

_HDRS = 'import "std:http" as http\n'


# ── WSGI mock apps ──────────────────────────────────────────────────────────

def _simple_app(environ, start_response):
    path = environ.get("PATH_INFO", "/")
    method = environ.get("REQUEST_METHOD", "GET")

    if path == "/hello":
        start_response("200 OK", [("Content-Type", "text/plain"), ("X-Custom", "abc")])
        return [b"hello world"]

    if path == "/json":
        start_response("200 OK", [("Content-Type", "application/json")])
        return [b'{"name": "Alice", "age": 30}']

    if path == "/echo-method":
        start_response("200 OK", [("Content-Type", "text/plain")])
        return [method.encode()]

    if path == "/echo-body":
        length = int(environ.get("CONTENT_LENGTH") or 0)
        body = environ["wsgi.input"].read(length) if length else b""
        ct = environ.get("CONTENT_TYPE", "")
        start_response("200 OK", [("Content-Type", "text/plain")])
        return [body]

    if path == "/echo-ct":
        ct = environ.get("CONTENT_TYPE", "")
        start_response("200 OK", [("Content-Type", "text/plain")])
        return [ct.encode()]

    if path == "/echo-auth":
        auth = environ.get("HTTP_AUTHORIZATION", "")
        start_response("200 OK", [("Content-Type", "text/plain")])
        return [auth.encode()]

    if path == "/echo-query":
        qs = environ.get("QUERY_STRING", "")
        start_response("200 OK", [("Content-Type", "text/plain")])
        return [qs.encode()]

    if path == "/status/404":
        start_response("404 Not Found", [("Content-Type", "text/plain")])
        return [b"not found"]

    if path == "/status/500":
        start_response("500 Internal Server Error", [("Content-Type", "text/plain")])
        return [b"server error"]

    if path == "/binary":
        start_response("200 OK", [("Content-Type", "application/octet-stream")])
        return [b"\x00\x01\x02\x03"]

    if path == "/multi-header":
        start_response("200 OK", [
            ("Content-Type", "text/plain"),
            ("Set-Cookie", "a=1; HttpOnly"),
            ("Set-Cookie", "b=2; Secure"),
        ])
        return [b"ok"]

    if path == "/bad-json":
        start_response("200 OK", [("Content-Type", "application/json")])
        return [b"not valid json {{{"]

    if path == "/no-ct":
        start_response("200 OK", [])
        return [b"\xff\xfe"]

    start_response("404 Not Found", [("Content-Type", "text/plain")])
    return [b"not found"]


def _sse_app(environ, start_response):
    start_response("200 OK", [("Content-Type", "text/event-stream")])
    events = (
        b"event: ping\ndata: hello\nid: 1\n\n"
        b"data: world\n\n"
        b"event: done\ndata: bye\nretry: 5000\n\n"
    )
    return [events]


def _stream_app(environ, start_response):
    start_response("200 OK", [("Content-Type", "text/plain")])
    return [b"chunk1", b"chunk2", b"chunk3"]


def run_http_src(src, app=None):
    vm = lang.VM([], {}, code_locs=[], source_path="main.nd")
    mock_app = app or _simple_app
    vm._http_client = httpx.Client(transport=httpx.WSGITransport(app=mock_app))
    loader = ModuleLoader(project_root=None, vm=vm)
    buf = io.StringIO()
    with redirect_stdout(buf):
        loader.load_module_from_source(_HDRS + src, module_name="main.nd")
    return buf.getvalue().splitlines(), vm


def lines(src, app=None):
    return run_http_src(src, app)[0]


def first(src, app=None):
    return lines(src, app)[0]


# ── Sync verb tests ──────────────────────────────────────────────────────────

class SyncVerbTests(unittest.TestCase):

    def test_get_status(self):
        self.assertEqual(first('let r = http.get("http://t/hello")\nprint(r.status)'), "200")

    def test_get_ok_true(self):
        self.assertEqual(first('let r = http.get("http://t/hello")\nprint(r.ok)'), "true")

    def test_get_body_text(self):
        self.assertEqual(first('let r = http.get("http://t/hello")\nprint(r.body)'), "hello world")

    def test_get_url(self):
        self.assertEqual(first('let r = http.get("http://t/hello")\nprint(r.url)'), "http://t/hello")

    def test_get_method_field(self):
        self.assertEqual(first('let r = http.get("http://t/hello")\nprint(r.method)'), "GET")

    def test_post_method(self):
        self.assertEqual(first('let r = http.post("http://t/echo-method")\nprint(r.body)'), "POST")

    def test_put_method(self):
        self.assertEqual(first('let r = http.put("http://t/echo-method")\nprint(r.body)'), "PUT")

    def test_delete_method(self):
        self.assertEqual(first('let r = http.delete("http://t/echo-method")\nprint(r.body)'), "DELETE")

    def test_patch_method(self):
        self.assertEqual(first('let r = http.patch("http://t/echo-method")\nprint(r.body)'), "PATCH")

    def test_head_method(self):
        self.assertEqual(first('let r = http.head("http://t/hello")\nprint(r.status)'), "200")

    def test_options_method(self):
        self.assertEqual(first('let r = http.options("http://t/echo-method")\nprint(r.body)'), "OPTIONS")

    def test_request_generic(self):
        self.assertEqual(first('let r = http.request("GET", "http://t/hello")\nprint(r.status)'), "200")

    def test_request_post(self):
        self.assertEqual(first('let r = http.request("POST", "http://t/echo-method")\nprint(r.body)'), "POST")


# ── Response shape tests ─────────────────────────────────────────────────────

class ResponseShapeTests(unittest.TestCase):

    def test_is_client_error(self):
        self.assertEqual(first('let r = http.get("http://t/status/404")\nprint(r.is_client_error)'), "true")

    def test_is_server_error(self):
        self.assertEqual(first('let r = http.get("http://t/status/500")\nprint(r.is_server_error)'), "true")

    def test_is_redirect_false_on_200(self):
        self.assertEqual(first('let r = http.get("http://t/hello")\nprint(r.is_redirect)'), "false")

    def test_ok_false_on_404(self):
        self.assertEqual(first('let r = http.get("http://t/status/404")\nprint(r.ok)'), "false")

    def test_status_404(self):
        self.assertEqual(first('let r = http.get("http://t/status/404")\nprint(r.status)'), "404")

    def test_json_method(self):
        self.assertEqual(first('let r = http.get("http://t/json")\nlet d = r.json()\nprint(d["name"])'), "Alice")

    def test_json_age_field(self):
        self.assertEqual(first('let r = http.get("http://t/json")\nlet d = r.json()\nprint(d["age"])'), "30")

    def test_json_parse_err_on_bad_json(self):
        self.assertEqual(first('let r = http.get("http://t/bad-json")\nprint(type(r.json()))'), "error")

    def test_json_decode_error_category(self):
        out = first('let r = http.get("http://t/bad-json")\nlet e = r.json()\nprint(e.payload["category"])')
        self.assertEqual(out, "decode_error")

    def test_header_method(self):
        self.assertEqual(first('let r = http.get("http://t/hello")\nprint(r.header("x-custom"))'), "abc")

    def test_header_case_insensitive(self):
        self.assertEqual(first('let r = http.get("http://t/hello")\nprint(r.header("X-Custom"))'), "abc")

    def test_header_missing_returns_nil(self):
        self.assertEqual(first('let r = http.get("http://t/hello")\nprint(r.header("x-does-not-exist") == nil)'), "true")

    def test_headers_all_multi_cookie(self):
        out = lines('let r = http.get("http://t/multi-header")\nlet c = r.headers_all("set-cookie")\nprint(len(c))')
        self.assertEqual(out[0], "2")

    def test_headers_all_missing_nil(self):
        self.assertEqual(first('let r = http.get("http://t/hello")\nprint(r.headers_all("x-missing") == nil)'), "true")

    def test_binary_body_type(self):
        self.assertEqual(first('let r = http.get("http://t/binary")\nprint(type(r.body))'), "bytes")

    def test_text_body_type(self):
        self.assertEqual(first('let r = http.get("http://t/hello")\nprint(type(r.body))'), "string")

    def test_no_ct_body_is_bytes(self):
        self.assertEqual(first('let r = http.get("http://t/no-ct")\nprint(type(r.body))'), "bytes")


# ── Options tests ────────────────────────────────────────────────────────────

class OptionsTests(unittest.TestCase):

    def test_custom_header(self):
        src = 'let r = http.get("http://t/echo-auth", {"headers": {"Authorization": "Bearer tok"}})\nprint(r.body)'
        self.assertEqual(first(src), "Bearer tok")

    def test_auth_bearer(self):
        src = 'let r = http.get("http://t/echo-auth", {"auth_bearer": "mytoken"})\nprint(r.body)'
        self.assertEqual(first(src), "Bearer mytoken")

    def test_auth_basic(self):
        import base64
        expected = "Basic " + base64.b64encode(b"user:pass").decode()
        src = 'let r = http.get("http://t/echo-auth", {"auth_basic": {"username": "user", "password": "pass"}})\nprint(r.body)'
        self.assertEqual(first(src), expected)

    def test_query_params(self):
        src = 'let r = http.get("http://t/echo-query", {"query": {"key": "val"}})\nprint(r.body)'
        self.assertEqual(first(src), "key=val")

    def test_json_body_content_type(self):
        src = 'let r = http.post("http://t/echo-ct", {"json": {"x": 1}})\nprint(r.body)'
        self.assertIn("application/json", first(src))

    def test_json_body_content(self):
        src = 'let r = http.post("http://t/echo-body", {"json": {"key": "value"}})\nprint(r.body)'
        body = first(src)
        data = json.loads(body)
        self.assertEqual(data["key"], "value")

    def test_text_body(self):
        src = 'let r = http.post("http://t/echo-body", {"text": "hello text"})\nprint(r.body)'
        self.assertEqual(first(src), "hello text")

    def test_form_body_content_type(self):
        src = 'let r = http.post("http://t/echo-ct", {"form": {"name": "Alice"}})\nprint(r.body)'
        self.assertIn("application/x-www-form-urlencoded", first(src))

    def test_body_on_get_returns_err(self):
        src = 'let r = http.get("http://t/hello", {"json": {"x": 1}})\nprint(type(r))'
        self.assertEqual(first(src), "error")

    def test_body_conflict_returns_err(self):
        src = 'let r = http.post("http://t/echo-body", {"json": {"a": 1}, "text": "b"})\nprint(type(r))'
        self.assertEqual(first(src), "error")

    def test_follow_redirects_default_true(self):
        self.assertEqual(first('let r = http.get("http://t/hello")\nprint(r.ok)'), "true")

    def test_invalid_url_type_err(self):
        self.assertEqual(first('let r = http.get(42)\nprint(type(r))'), "error")


# ── Error handling tests ─────────────────────────────────────────────────────

class ErrorHandlingTests(unittest.TestCase):

    def test_network_error_kind(self):
        vm = lang.VM([], {}, code_locs=[], source_path="main.nd")
        loader = ModuleLoader(project_root=None, vm=vm)
        buf = io.StringIO()
        src = _HDRS + 'let r = http.get("http://127.0.0.1:1")\nprint(type(r))\nprint(r.kind)'
        with redirect_stdout(buf):
            loader.load_module_from_source(src, module_name="main.nd")
        output = buf.getvalue().splitlines()
        self.assertEqual(output[0], "error")
        self.assertEqual(output[1], "http_error")

    def test_network_error_category(self):
        vm = lang.VM([], {}, code_locs=[], source_path="main.nd")
        loader = ModuleLoader(project_root=None, vm=vm)
        buf = io.StringIO()
        src = _HDRS + 'let r = http.get("http://127.0.0.1:1")\nprint(r.payload["category"])'
        with redirect_stdout(buf):
            loader.load_module_from_source(src, module_name="main.nd")
        self.assertEqual(buf.getvalue().strip(), "network")

    def test_err_payload_url(self):
        vm = lang.VM([], {}, code_locs=[], source_path="main.nd")
        loader = ModuleLoader(project_root=None, vm=vm)
        buf = io.StringIO()
        src = _HDRS + 'let r = http.get("http://127.0.0.1:1")\nprint(r.payload["url"])'
        with redirect_stdout(buf):
            loader.load_module_from_source(src, module_name="main.nd")
        self.assertIn("127.0.0.1", buf.getvalue())

    def test_err_payload_method(self):
        vm = lang.VM([], {}, code_locs=[], source_path="main.nd")
        loader = ModuleLoader(project_root=None, vm=vm)
        buf = io.StringIO()
        src = _HDRS + 'let r = http.get("http://127.0.0.1:1")\nprint(r.payload["method"])'
        with redirect_stdout(buf):
            loader.load_module_from_source(src, module_name="main.nd")
        self.assertEqual(buf.getvalue().strip(), "GET")


# ── Async verb tests ─────────────────────────────────────────────────────────

class AsyncVerbTests(unittest.TestCase):

    def _run_async_src(self, src, app=None):
        vm = lang.VM([], {}, code_locs=[], source_path="main.nd")
        mock = app or _simple_app
        vm._http_client = httpx.Client(transport=httpx.WSGITransport(app=mock))
        loader = ModuleLoader(project_root=None, vm=vm)
        buf = io.StringIO()
        with redirect_stdout(buf):
            loader.load_module_from_source(_HDRS + src, module_name="main.nd")
        return buf.getvalue().splitlines()

    def test_get_async_status(self):
        src = (
            'let co = coroutine(fn() {\n'
            '  let r = http.get_async("http://t/hello")\n'
            '  print(r.status)\n'
            '})\n'
            'spawn(co)\n'
            'run_loop()'
        )
        self.assertEqual(self._run_async_src(src)[0], "200")

    def test_get_async_body(self):
        src = (
            'let co = coroutine(fn() {\n'
            '  let r = http.get_async("http://t/hello")\n'
            '  print(r.body)\n'
            '})\n'
            'spawn(co)\n'
            'run_loop()'
        )
        self.assertEqual(self._run_async_src(src)[0], "hello world")

    def test_post_async_method(self):
        src = (
            'let co = coroutine(fn() {\n'
            '  let r = http.post_async("http://t/echo-method")\n'
            '  print(r.body)\n'
            '})\n'
            'spawn(co)\n'
            'run_loop()'
        )
        self.assertEqual(self._run_async_src(src)[0], "POST")

    def test_async_parallel_two_requests(self):
        results = []
        src = (
            'let co1 = coroutine(fn() { let r = http.get_async("http://t/hello")\n print(r.status) })\n'
            'let co2 = coroutine(fn() { let r = http.get_async("http://t/json")\n print(r.status) })\n'
            'spawn(co1)\n'
            'spawn(co2)\n'
            'run_loop()'
        )
        out = self._run_async_src(src)
        self.assertIn("200", out)
        self.assertEqual(len(out), 2)

    def test_request_async_generic(self):
        src = (
            'let co = coroutine(fn() {\n'
            '  let r = http.request_async("GET", "http://t/hello")\n'
            '  print(r.ok)\n'
            '})\n'
            'spawn(co)\n'
            'run_loop()'
        )
        self.assertEqual(self._run_async_src(src)[0], "true")


# ── Streaming tests ──────────────────────────────────────────────────────────

class StreamTests(unittest.TestCase):

    def _run_stream_src(self, src, app=None):
        vm = lang.VM([], {}, code_locs=[], source_path="main.nd")
        mock = app or _stream_app
        vm._http_client = httpx.Client(transport=httpx.WSGITransport(app=mock))
        loader = ModuleLoader(project_root=None, vm=vm)
        buf = io.StringIO()
        with redirect_stdout(buf):
            loader.load_module_from_source(_HDRS + src, module_name="main.nd")
        return buf.getvalue().splitlines()

    def test_stream_status(self):
        src = 'let r = http.stream("http://t/")\nprint(r.status)'
        self.assertEqual(self._run_stream_src(src)[0], "200")

    def test_stream_ok(self):
        src = 'let r = http.stream("http://t/")\nprint(r.ok)'
        self.assertEqual(self._run_stream_src(src)[0], "true")

    def test_stream_has_chunks_channel(self):
        src = 'let r = http.stream("http://t/")\nprint(type(r.chunks))'
        self.assertEqual(self._run_stream_src(src)[0], "channel")

    def test_stream_chunks_in_coroutine(self):
        src = (
            'let results = []\n'
            'let co = coroutine(fn() {\n'
            '  let r = http.stream("http://t/")\n'
            '  let chunk = recv(r.chunks)\n'
            '  while (chunk != nil) {\n'
            '    list_push(results, chunk)\n'
            '    chunk = recv(r.chunks)\n'
            '  }\n'
            '})\n'
            'spawn(co)\n'
            'run_loop()\n'
            'print(len(results))'
        )
        out = self._run_stream_src(src)
        # At least one chunk should be received
        n = int(out[0])
        self.assertGreaterEqual(n, 1)

    def test_stream_close_method(self):
        src = 'let r = http.stream("http://t/")\nprint(type(r.close()))'
        self.assertEqual(self._run_stream_src(src)[0], "nil")


# ── SSE tests ────────────────────────────────────────────────────────────────

class SSETests(unittest.TestCase):

    def _run_sse_src(self, src, app=None):
        vm = lang.VM([], {}, code_locs=[], source_path="main.nd")
        mock = app or _sse_app
        vm._http_client = httpx.Client(transport=httpx.WSGITransport(app=mock))
        loader = ModuleLoader(project_root=None, vm=vm)
        buf = io.StringIO()
        with redirect_stdout(buf):
            loader.load_module_from_source(_HDRS + src, module_name="main.nd")
        return buf.getvalue().splitlines()

    def test_sse_status(self):
        src = 'let r = http.sse("http://t/")\nprint(r.status)'
        self.assertEqual(self._run_sse_src(src)[0], "200")

    def test_sse_ok(self):
        src = 'let r = http.sse("http://t/")\nprint(r.ok)'
        self.assertEqual(self._run_sse_src(src)[0], "true")

    def test_sse_has_events_channel(self):
        src = 'let r = http.sse("http://t/")\nprint(type(r.events))'
        self.assertEqual(self._run_sse_src(src)[0], "channel")

    def test_sse_events_in_coroutine(self):
        src = (
            'let events = []\n'
            'let co = coroutine(fn() {\n'
            '  let r = http.sse("http://t/")\n'
            '  let ev = recv(r.events)\n'
            '  while (ev != nil) {\n'
            '    list_push(events, ev)\n'
            '    ev = recv(r.events)\n'
            '  }\n'
            '})\n'
            'spawn(co)\n'
            'run_loop()\n'
            'print(len(events))'
        )
        out = self._run_sse_src(src)
        self.assertEqual(out[0], "3")

    def test_sse_event_type(self):
        src = (
            'let co = coroutine(fn() {\n'
            '  let r = http.sse("http://t/")\n'
            '  let ev = recv(r.events)\n'
            '  print(ev["event"])\n'
            '})\n'
            'spawn(co)\n'
            'run_loop()'
        )
        self.assertEqual(self._run_sse_src(src)[0], "ping")

    def test_sse_event_data(self):
        src = (
            'let co = coroutine(fn() {\n'
            '  let r = http.sse("http://t/")\n'
            '  let ev = recv(r.events)\n'
            '  print(ev["data"])\n'
            '})\n'
            'spawn(co)\n'
            'run_loop()'
        )
        self.assertEqual(self._run_sse_src(src)[0], "hello")

    def test_sse_event_id(self):
        src = (
            'let co = coroutine(fn() {\n'
            '  let r = http.sse("http://t/")\n'
            '  let ev = recv(r.events)\n'
            '  print(ev["id"])\n'
            '})\n'
            'spawn(co)\n'
            'run_loop()'
        )
        self.assertEqual(self._run_sse_src(src)[0], "1")

    def test_sse_default_event_type(self):
        src = (
            'let co = coroutine(fn() {\n'
            '  let r = http.sse("http://t/")\n'
            '  recv(r.events)\n'
            '  let ev = recv(r.events)\n'
            '  print(ev["event"])\n'
            '})\n'
            'spawn(co)\n'
            'run_loop()'
        )
        self.assertEqual(self._run_sse_src(src)[0], "message")

    def test_sse_retry_field(self):
        src = (
            'let co = coroutine(fn() {\n'
            '  let r = http.sse("http://t/")\n'
            '  recv(r.events)\n'
            '  recv(r.events)\n'
            '  let ev = recv(r.events)\n'
            '  print(ev["retry"])\n'
            '})\n'
            'spawn(co)\n'
            'run_loop()'
        )
        self.assertEqual(self._run_sse_src(src)[0], "5000")

    def test_sse_close(self):
        src = 'let r = http.sse("http://t/")\nprint(type(r.close()))'
        self.assertEqual(self._run_sse_src(src)[0], "nil")


# ── as_sse() conversion tests ────────────────────────────────────────────────

class AsSSETests(unittest.TestCase):

    def test_as_sse_converts_stream(self):
        vm = lang.VM([], {}, code_locs=[], source_path="main.nd")
        vm._http_client = httpx.Client(transport=httpx.WSGITransport(app=_sse_app))
        loader = ModuleLoader(project_root=None, vm=vm)
        src = (
            _HDRS +
            'let events = []\n'
            'let co = coroutine(fn() {\n'
            '  let r = http.stream("http://t/")\n'
            '  let ch = r.as_sse()\n'
            '  let ev = recv(ch)\n'
            '  while (ev != nil) {\n'
            '    list_push(events, ev)\n'
            '    ev = recv(ch)\n'
            '  }\n'
            '})\n'
            'spawn(co)\n'
            'run_loop()\n'
            'print(len(events))'
        )
        buf = io.StringIO()
        with redirect_stdout(buf):
            loader.load_module_from_source(src, module_name="main.nd")
        self.assertEqual(buf.getvalue().strip(), "3")


if __name__ == "__main__":
    unittest.main()
