"""std:http — HTTP client builtins for Nodus VM."""

import base64
import json
import threading
import time as _time

import httpx

from nodus.runtime.channel import Channel
from nodus.vm.vm import BuiltinMethod, Record

_TEXT_CONTENT_TYPES = (
    "text/",
    "application/json",
    "application/xml",
    "application/javascript",
    "application/x-www-form-urlencoded",
    "application/xhtml+xml",
    "application/ld+json",
)

_BODY_KEYS = frozenset(["json", "form", "multipart", "bytes", "text"])
_NO_BODY_METHODS = frozenset(["GET", "HEAD", "OPTIONS"])


def _is_text_ct(content_type: str) -> bool:
    ct = content_type.lower().split(";")[0].strip()
    return any(ct.startswith(t) or ct == t.rstrip("/") for t in _TEXT_CONTENT_TYPES)


def _decode_response_body(resp: httpx.Response) -> object:
    ct = resp.headers.get("content-type", "")
    if _is_text_ct(ct):
        charset = "utf-8"
        for part in ct.split(";")[1:]:
            part = part.strip()
            if part.startswith("charset="):
                charset = part[len("charset="):].strip().strip('"')
                break
        try:
            return resp.content.decode(charset)
        except (UnicodeDecodeError, LookupError):
            return resp.content
    return resp.content


def _build_headers_map(resp: httpx.Response) -> dict:
    result = {}
    for k, v in resp.headers.multi_items():
        key = k.lower()
        if key not in result:
            result[key] = []
        result[key].append(v)
    return result


def _make_http_err(vm, message: str, *, status=None, url="", method="", category="network",
                   body=None, body_truncated=False, bytes_received=None) -> Record:
    MAX_BODY = 64 * 1024
    if isinstance(body, (str, bytes)) and len(body) > MAX_BODY:
        body = body[:MAX_BODY]
        body_truncated = True
    return vm.make_err("http_error", message, payload={
        "status": status,
        "url": url,
        "method": method,
        "category": category,
        "body": body,
        "body_truncated": body_truncated,
        "bytes_received": bytes_received,
    })


def _make_response_record(resp: httpx.Response, method: str, vm) -> Record:
    headers_map = _build_headers_map(resp)
    body = _decode_response_body(resp)
    status = resp.status_code

    raw_body = resp.content

    def r_json():
        try:
            return json.loads(raw_body)
        except (json.JSONDecodeError, ValueError) as exc:
            return _make_http_err(vm, f"JSON decode error: {exc}",
                                  status=status, url=str(resp.url), method=method,
                                  category="decode_error")

    def r_header(name):
        vals = headers_map.get(name.lower()) if isinstance(name, str) else None
        return vals[0] if vals else None

    def r_headers_all(name):
        return headers_map.get(name.lower()) if isinstance(name, str) else None

    return Record({
        "status": status,
        "headers": headers_map,
        "body": body,
        "url": str(resp.url),
        "method": method,
        "ok": 200 <= status < 300,
        "is_redirect": 300 <= status < 400,
        "is_client_error": 400 <= status < 500,
        "is_server_error": 500 <= status < 600,
        "json": BuiltinMethod(r_json),
        "header": BuiltinMethod(r_header),
        "headers_all": BuiltinMethod(r_headers_all),
    }, kind="http_response")


def _make_stream_record(resp: httpx.Response, method: str, chunks_ch: Channel, vm,
                        close_fn) -> Record:
    headers_map = _build_headers_map(resp)
    status = resp.status_code

    def r_header(name):
        vals = headers_map.get(name.lower()) if isinstance(name, str) else None
        return vals[0] if vals else None

    def r_headers_all(name):
        return headers_map.get(name.lower()) if isinstance(name, str) else None

    def r_close():
        close_fn()
        return None

    def r_as_sse():
        sse_ch = Channel()
        _s = _get_scheduler(vm)
        if _s is not None:
            _s._io_channels.append(sse_ch)

        def _worker():
            _pump_sse(chunks_ch, sse_ch)

        threading.Thread(target=_worker, daemon=True).start()
        return sse_ch

    return Record({
        "status": status,
        "headers": headers_map,
        "url": str(resp.url),
        "method": method,
        "chunks": chunks_ch,
        "ok": 200 <= status < 300,
        "is_redirect": 300 <= status < 400,
        "is_client_error": 400 <= status < 500,
        "is_server_error": 500 <= status < 600,
        "header": BuiltinMethod(r_header),
        "headers_all": BuiltinMethod(r_headers_all),
        "close": BuiltinMethod(r_close),
        "as_sse": BuiltinMethod(r_as_sse),
    }, kind="http_stream_response")


def _make_sse_record(resp: httpx.Response, method: str, events_ch: Channel, vm,
                     close_fn, last_id_box: list) -> Record:
    headers_map = _build_headers_map(resp)
    status = resp.status_code

    def r_header(name):
        vals = headers_map.get(name.lower()) if isinstance(name, str) else None
        return vals[0] if vals else None

    def r_headers_all(name):
        return headers_map.get(name.lower()) if isinstance(name, str) else None

    def r_close():
        close_fn()
        return None

    def r_last_event_id():
        return last_id_box[0]

    return Record({
        "status": status,
        "headers": headers_map,
        "url": str(resp.url),
        "method": method,
        "events": events_ch,
        "ok": 200 <= status < 300,
        "is_redirect": 300 <= status < 400,
        "is_client_error": 400 <= status < 500,
        "is_server_error": 500 <= status < 600,
        "last_event_id": BuiltinMethod(r_last_event_id),
        "header": BuiltinMethod(r_header),
        "headers_all": BuiltinMethod(r_headers_all),
        "close": BuiltinMethod(r_close),
    }, kind="http_sse_response")


def _get_chunk_blocking(ch: Channel) -> object:
    """Block the current Python thread until ch has an item or is closed."""
    while not ch.queue and not ch.closed:
        _time.sleep(0.001)
    return ch.queue.popleft() if ch.queue else None


def _pump_sse(chunks_ch: Channel, sse_ch: Channel) -> None:
    """Parse SSE events from chunks_ch and put them into sse_ch."""
    buf = ""
    try:
        while True:
            chunk = _get_chunk_blocking(chunks_ch)
            if chunk is None:
                break
            if isinstance(chunk, bytes):
                chunk = chunk.decode("utf-8", errors="replace")
            buf += chunk
            while "\n\n" in buf:
                event_text, buf = buf.split("\n\n", 1)
                event = _parse_sse_event(event_text)
                if event is not None:
                    sse_ch.queue.append(event)
    finally:
        sse_ch.closed = True


def _parse_sse_event(text: str) -> dict | None:
    """Parse one SSE event block into a plain dict (indexable with ["key"])."""
    fields: dict = {}
    data_lines: list = []
    for line in text.splitlines():
        if not line or line.startswith(":"):
            continue
        if ":" in line:
            key, _, value = line.partition(":")
            value = value.lstrip(" ")
        else:
            key, value = line, ""
        if key == "data":
            data_lines.append(value)
        elif key == "event":
            fields["event"] = value
        elif key == "id":
            fields["id"] = value
        elif key == "retry":
            try:
                fields["retry"] = int(value)
            except ValueError:
                pass
    if not data_lines and "event" not in fields:
        return None
    fields["data"] = "\n".join(data_lines)
    if "event" not in fields:
        fields["event"] = "message"
    return fields


def _parse_options(method: str, url: str, options, vm) -> dict | Record:
    """Parse the Nodus options map into httpx request kwargs. Returns a dict or err Record."""
    if options is None:
        options = {}
    if isinstance(options, Record):
        options = options.fields
    if not isinstance(options, dict):
        return _make_http_err(vm, "http options must be a map",
                              url=url, method=method, category="client_error")

    kwargs: dict = {}

    # Headers
    req_headers: dict = {}
    raw_headers = options.get("headers")
    if raw_headers is not None:
        if isinstance(raw_headers, dict):
            req_headers = {str(k): str(v) for k, v in raw_headers.items()}
        elif isinstance(raw_headers, Record):
            req_headers = {str(k): str(v) for k, v in raw_headers.fields.items()}

    # Auth shortcuts
    auth_bearer = options.get("auth_bearer")
    auth_basic = options.get("auth_basic")

    if auth_bearer is not None:
        auth_key = next((k for k in req_headers if k.lower() == "authorization"), None)
        if auth_key:
            return _make_http_err(vm, "auth_bearer conflicts with explicit Authorization header",
                                  url=url, method=method, category="client_error")
        req_headers["Authorization"] = f"Bearer {auth_bearer}"

    if auth_basic is not None:
        auth_key = next((k for k in req_headers if k.lower() == "authorization"), None)
        if auth_key:
            return _make_http_err(vm, "auth_basic conflicts with explicit Authorization header",
                                  url=url, method=method, category="client_error")
        fields = auth_basic.fields if isinstance(auth_basic, Record) else auth_basic
        user = str(fields.get("username", ""))
        pw = str(fields.get("password", ""))
        cred = base64.b64encode(f"{user}:{pw}".encode()).decode()
        req_headers["Authorization"] = f"Basic {cred}"

    if req_headers:
        kwargs["headers"] = req_headers

    # Query params
    query = options.get("query")
    if query is not None:
        raw_q = query.fields if isinstance(query, Record) else query
        if isinstance(raw_q, dict):
            params: dict = {}
            for k, v in raw_q.items():
                if isinstance(v, list):
                    params[k] = [str(i) for i in v]
                else:
                    params[k] = str(v)
            kwargs["params"] = params

    # Body keys (mutually exclusive)
    present = [k for k in _BODY_KEYS if k in options]
    if len(present) > 1:
        return _make_http_err(vm, f"Multiple body keys: {', '.join(present)}",
                              url=url, method=method, category="client_error")
    if present:
        bk = present[0]
        m_upper = method.upper()
        if m_upper in _NO_BODY_METHODS:
            return _make_http_err(vm, f"Method {m_upper} does not accept a request body",
                                  url=url, method=method, category="client_error")
        val = options[bk]
        if isinstance(val, Record):
            val = val.fields
        if bk == "json":
            kwargs["json"] = val
        elif bk == "form":
            data = val.fields if isinstance(val, Record) else val
            kwargs["data"] = {str(k): str(v) for k, v in data.items()}
        elif bk == "text":
            text_val = val if isinstance(val, str) else str(val)
            kwargs["content"] = text_val.encode("utf-8")
        elif bk == "bytes":
            kwargs["content"] = val if isinstance(val, bytes) else bytes(val)
        elif bk == "multipart":
            files: dict = {}
            raw_mp = val.fields if isinstance(val, Record) else val
            for k, v in raw_mp.items():
                if isinstance(v, Record):
                    fn = v.fields.get("filename", k)
                    data = v.fields.get("data", b"")
                    ct = v.fields.get("content_type", "application/octet-stream")
                    files[k] = (fn, data, ct)
                elif isinstance(v, dict):
                    files[k] = (v.get("filename", k), v.get("data", b""), v.get("content_type", "application/octet-stream"))
                elif isinstance(v, bytes):
                    files[k] = v
                else:
                    files[k] = str(v).encode()
            kwargs["files"] = files

    # Timeouts
    t_total = options.get("timeout_ms")
    t_conn = options.get("connect_timeout_ms")
    t_read = options.get("read_timeout_ms")
    if t_total is not None or t_conn is not None or t_read is not None:
        total_s = t_total / 1000 if t_total is not None else None
        conn_s = t_conn / 1000 if t_conn is not None else (30.0 if total_s is None else total_s)
        read_s = t_read / 1000 if t_read is not None else total_s
        kwargs["timeout"] = httpx.Timeout(timeout=total_s, connect=conn_s, read=read_s)

    # Redirects
    follow = options.get("follow_redirects")
    if follow is not None:
        kwargs["follow_redirects"] = bool(follow)
    else:
        kwargs["follow_redirects"] = True

    # TLS
    verify = options.get("verify_tls")
    if verify is not None:
        kwargs["verify"] = verify

    # Proxy (httpx doesn't support per-request proxy, so we skip)

    return kwargs


def _root_vm(vm):
    """Return the root-most VM in the _caller_vm chain."""
    root = vm
    while True:
        parent = getattr(root, "_caller_vm", None)
        if parent is None:
            return root
        root = parent


def _get_or_create_client(vm) -> httpx.Client:
    # Walk up the _caller_vm chain: module functions run in a fresh sub-VM
    # whose _caller_vm points back to the VM that called it.  Find or create
    # the shared httpx.Client on the root-most VM in the chain.
    root = _root_vm(vm)
    client = getattr(root, "_http_client", None)
    if not client:
        client = httpx.Client(follow_redirects=True, max_redirects=10)
        root._http_client = client
    if root is not vm:
        vm._http_client = client  # cache on sub-VM for next call
    return client


def _get_scheduler(vm):
    """Return the root VM's scheduler (the one that runs run_loop)."""
    return getattr(_root_vm(vm), "scheduler", None)


def _do_sync_request(method: str, url: str, options, vm) -> Record:
    if not isinstance(url, str):
        return _make_http_err(vm, f"URL must be a string, got {vm.builtin_type(url)}",
                              url="", method=method, category="client_error")
    kwargs = _parse_options(method, url, options, vm)
    if isinstance(kwargs, Record):  # err record
        return kwargs
    client = _get_or_create_client(vm)
    try:
        resp = client.request(method, url, **kwargs)
        return _make_response_record(resp, method, vm)
    except httpx.TooManyRedirects as exc:
        return _make_http_err(vm, f"Too many redirects: {exc}",
                              url=url, method=method, category="redirect_error")
    except httpx.TimeoutException as exc:
        return _make_http_err(vm, f"Request timed out: {exc}",
                              url=url, method=method, category="timeout")
    except httpx.TransportError as exc:
        return _make_http_err(vm, f"Network error: {exc}",
                              url=url, method=method, category="network")
    except httpx.HTTPError as exc:
        return _make_http_err(vm, f"HTTP error: {exc}",
                              url=url, method=method, category="network")


def _do_stream_request(method: str, url: str, options, vm) -> Record:
    if not isinstance(url, str):
        return _make_http_err(vm, f"URL must be a string, got {vm.builtin_type(url)}",
                              url="", method=method, category="client_error")
    kwargs = _parse_options(method, url, options, vm)
    if isinstance(kwargs, Record):
        return kwargs

    chunks_ch = Channel()
    closed = [False]
    resp_holder = [None]
    err_holder = [None]
    ready = threading.Event()

    client = _get_or_create_client(vm)

    def _worker():
        try:
            with client.stream(method, url, **kwargs) as resp:
                resp_holder[0] = resp
                ready.set()
                ct = resp.headers.get("content-type", "")
                is_text = _is_text_ct(ct)
                try:
                    for chunk in resp.iter_bytes(chunk_size=4096):
                        if not chunk:
                            continue
                        if is_text:
                            chunks_ch.queue.append(chunk.decode("utf-8", errors="replace"))
                        else:
                            chunks_ch.queue.append(chunk)
                        if closed[0]:
                            break
                except Exception as exc:
                    chunks_ch.queue.append(_make_http_err(
                        vm, f"Stream read error: {exc}",
                        status=resp.status_code, url=url, method=method, category="network",
                    ))
        except httpx.TooManyRedirects as exc:
            err_holder[0] = _make_http_err(vm, f"Too many redirects: {exc}",
                                           url=url, method=method, category="redirect_error")
            ready.set()
        except httpx.TimeoutException as exc:
            err_holder[0] = _make_http_err(vm, f"Request timed out: {exc}",
                                           url=url, method=method, category="timeout")
            ready.set()
        except httpx.TransportError as exc:
            err_holder[0] = _make_http_err(vm, f"Network error: {exc}",
                                           url=url, method=method, category="network")
            ready.set()
        finally:
            chunks_ch.closed = True

    t = threading.Thread(target=_worker, daemon=True)
    t.start()
    ready.wait(timeout=30.0)

    if err_holder[0] is not None:
        return err_holder[0]
    if resp_holder[0] is None:
        return _make_http_err(vm, "Stream request timed out before headers received",
                              url=url, method=method, category="timeout")

    resp = resp_holder[0]
    scheduler = _get_scheduler(vm)
    if scheduler is not None:
        scheduler._io_channels.append(chunks_ch)

    _sched = _get_scheduler(vm)

    def close_fn():
        closed[0] = True
        chunks_ch.closed = True
        if _sched is not None and chunks_ch in _sched._io_channels:
            _sched._io_channels.remove(chunks_ch)

    return _make_stream_record(resp, method, chunks_ch, vm, close_fn)


def _do_sse_request(method: str, url: str, options, vm) -> Record:
    if not isinstance(url, str):
        return _make_http_err(vm, f"URL must be a string, got {vm.builtin_type(url)}",
                              url="", method=method, category="client_error")
    kwargs = _parse_options(method, url, options, vm)
    if isinstance(kwargs, Record):
        return kwargs

    events_ch = Channel()
    last_id_box = [""]
    closed = [False]
    resp_holder = [None]
    err_holder = [None]
    ready = threading.Event()

    client = _get_or_create_client(vm)

    def _worker():
        try:
            with client.stream(method, url, **kwargs) as resp:
                resp_holder[0] = resp
                ready.set()
                buf = ""
                try:
                    for chunk in resp.iter_text():
                        if closed[0]:
                            break
                        buf += chunk
                        while "\n\n" in buf:
                            event_text, buf = buf.split("\n\n", 1)
                            event = _parse_sse_event(event_text)
                            if event is not None:
                                if "id" in event:
                                    last_id_box[0] = event["id"]
                                events_ch.queue.append(event)
                except Exception as exc:
                    events_ch.queue.append(_make_http_err(
                        vm, f"SSE stream error: {exc}",
                        status=resp.status_code, url=url, method=method, category="network",
                    ))
        except httpx.TooManyRedirects as exc:
            err_holder[0] = _make_http_err(vm, f"Too many redirects: {exc}",
                                           url=url, method=method, category="redirect_error")
            ready.set()
        except httpx.TimeoutException as exc:
            err_holder[0] = _make_http_err(vm, f"Request timed out: {exc}",
                                           url=url, method=method, category="timeout")
            ready.set()
        except httpx.TransportError as exc:
            err_holder[0] = _make_http_err(vm, f"Network error: {exc}",
                                           url=url, method=method, category="network")
            ready.set()
        finally:
            events_ch.closed = True

    t = threading.Thread(target=_worker, daemon=True)
    t.start()
    ready.wait(timeout=30.0)

    if err_holder[0] is not None:
        return err_holder[0]
    if resp_holder[0] is None:
        return _make_http_err(vm, "SSE request timed out before headers received",
                              url=url, method=method, category="timeout")

    resp = resp_holder[0]
    scheduler = _get_scheduler(vm)
    if scheduler is not None:
        scheduler._io_channels.append(events_ch)

    _sched = _get_scheduler(vm)

    def close_fn():
        closed[0] = True
        events_ch.closed = True
        if _sched is not None and events_ch in _sched._io_channels:
            _sched._io_channels.remove(events_ch)

    return _make_sse_record(resp, method, events_ch, vm, close_fn, last_id_box)


def _do_async_request(method: str, url: str, options, vm) -> object:
    # Phase 3B: async variants are synchronous at the I/O level.
    # Parallelism is achieved by spawning multiple Nodus coroutines via the
    # scheduler (task step budget) — not by suspending on async I/O here.
    # True async I/O bridging is a Phase 3C enhancement.
    return _do_sync_request(method, url, options, vm)


def register(vm, registry) -> None:
    """Register http_* builtins onto the registry."""

    # Sync verbs
    def http_get(url, options=None): return _do_sync_request("GET", url, options, vm)
    def http_post(url, options=None): return _do_sync_request("POST", url, options, vm)
    def http_put(url, options=None): return _do_sync_request("PUT", url, options, vm)
    def http_delete(url, options=None): return _do_sync_request("DELETE", url, options, vm)
    def http_patch(url, options=None): return _do_sync_request("PATCH", url, options, vm)
    def http_head(url, options=None): return _do_sync_request("HEAD", url, options, vm)
    def http_options(url, options=None): return _do_sync_request("OPTIONS", url, options, vm)
    def http_request(method, url, options=None): return _do_sync_request(method, url, options, vm)

    # Async verbs
    def http_get_async(url, options=None): return _do_async_request("GET", url, options, vm)
    def http_post_async(url, options=None): return _do_async_request("POST", url, options, vm)
    def http_put_async(url, options=None): return _do_async_request("PUT", url, options, vm)
    def http_delete_async(url, options=None): return _do_async_request("DELETE", url, options, vm)
    def http_patch_async(url, options=None): return _do_async_request("PATCH", url, options, vm)
    def http_head_async(url, options=None): return _do_async_request("HEAD", url, options, vm)
    def http_options_async(url, options=None): return _do_async_request("OPTIONS", url, options, vm)
    def http_request_async(method, url, options=None): return _do_async_request(method, url, options, vm)

    # Stream and SSE
    def http_stream(url, options=None): return _do_stream_request("GET", url, options, vm)
    def http_sse(url, options=None): return _do_sse_request("GET", url, options, vm)

    arity_1_2 = (1, 2)
    arity_2_3 = (2, 3)

    registry.add("http_get",    arity_1_2, http_get)
    registry.add("http_post",   arity_1_2, http_post)
    registry.add("http_put",    arity_1_2, http_put)
    registry.add("http_delete", arity_1_2, http_delete)
    registry.add("http_patch",  arity_1_2, http_patch)
    registry.add("http_head",   arity_1_2, http_head)
    registry.add("http_options_verb", arity_1_2, http_options)
    registry.add("http_request", arity_2_3, http_request)

    registry.add("http_get_async",    arity_1_2, http_get_async)
    registry.add("http_post_async",   arity_1_2, http_post_async)
    registry.add("http_put_async",    arity_1_2, http_put_async)
    registry.add("http_delete_async", arity_1_2, http_delete_async)
    registry.add("http_patch_async",  arity_1_2, http_patch_async)
    registry.add("http_head_async",   arity_1_2, http_head_async)
    registry.add("http_options_async", arity_1_2, http_options_async)
    registry.add("http_request_async", arity_2_3, http_request_async)

    registry.add("http_stream", arity_1_2, http_stream)
    registry.add("http_sse",    arity_1_2, http_sse)
