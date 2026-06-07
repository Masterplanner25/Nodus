from __future__ import annotations

import pytest

from nodus_http import (
    HttpCallMetadata,
    HttpCircuitOpenError,
    HttpRequest,
    HttpResponse,
    NodusHttpClient,
    RequestOptions,
)
from nodus_http.errors import HttpTimeoutError
from nodus_http.transport import DefaultAsyncTransport, DefaultSyncTransport


class StubSyncTransport(DefaultSyncTransport):
    def __init__(self, response: HttpResponse | None = None, exc: Exception | None = None) -> None:
        self.response = response
        self.exc = exc

    def send(self, request: HttpRequest, *, follow_redirects: bool | None = None) -> HttpResponse:
        _ = request
        _ = follow_redirects
        if self.exc:
            raise self.exc
        assert self.response is not None
        return self.response


class StubAsyncTransport(DefaultAsyncTransport):
    def __init__(self, response: HttpResponse | None = None) -> None:
        self.response = response

    async def send(self, request: HttpRequest, *, follow_redirects: bool | None = None) -> HttpResponse:
        _ = request
        _ = follow_redirects
        assert self.response is not None
        return self.response


class StubRetryExecutor:
    def __init__(self) -> None:
        self.sync_calls = 0
        self.async_calls = 0

    def execute(self, *, operation_name, metadata, fn):
        _ = operation_name
        _ = metadata
        self.sync_calls += 1
        return fn()

    async def aexecute(self, *, operation_name, metadata, fn):
        _ = operation_name
        _ = metadata
        self.async_calls += 1
        return await fn()


class StubBreaker:
    def __init__(self, should_open: bool = False) -> None:
        self.should_open = should_open
        self.successes = 0
        self.failures = 0

    def before_call(self, operation_name, metadata):
        _ = operation_name
        _ = metadata
        if self.should_open:
            raise RuntimeError("open")

    def after_success(self, operation_name, metadata):
        _ = operation_name
        _ = metadata
        self.successes += 1

    def after_failure(self, operation_name, error, metadata):
        _ = operation_name
        _ = error
        _ = metadata
        self.failures += 1


class StubPropagator:
    def inject(self, headers, metadata):
        _ = metadata
        updated = dict(headers)
        updated["x-trace-id"] = "abc"
        return updated


def test_sync_success_uses_retry_and_breaker() -> None:
    response = HttpResponse(200, {"content-type": "application/json"}, b"{}", "{}", {}, None)
    retry = StubRetryExecutor()
    breaker = StubBreaker()
    client = NodusHttpClient(sync_transport=StubSyncTransport(response=response))
    request = HttpRequest(
        method="GET",
        url="https://example.test",
        metadata=HttpCallMetadata(service_name="svc", operation_name="op"),
    )
    result = client.request(request, RequestOptions(retry_executor=retry, circuit_breaker=breaker))
    assert result.status_code == 200
    assert retry.sync_calls == 1
    assert breaker.successes == 1


@pytest.mark.asyncio
async def test_async_success_uses_retry() -> None:
    response = HttpResponse(200, {}, b"ok", "ok", None, None)
    retry = StubRetryExecutor()
    client = NodusHttpClient(async_transport=StubAsyncTransport(response=response))
    request = HttpRequest(method="GET", url="https://example.test")
    result = await client.arequest(request, RequestOptions(retry_executor=retry))
    assert result.text == "ok"
    assert retry.async_calls == 1


def test_trace_propagator_clones_headers() -> None:
    seen: dict[str, str] = {}

    class CaptureTransport(StubSyncTransport):
        def send(self, request: HttpRequest, *, follow_redirects: bool | None = None) -> HttpResponse:
            _ = follow_redirects
            seen.update(request.headers)
            return HttpResponse(200, {}, b"", "", None, request.metadata)

    request = HttpRequest(method="GET", url="https://example.test", headers={"x": "1"})
    client = NodusHttpClient(sync_transport=CaptureTransport())
    client.request(request, RequestOptions(trace_propagator=StubPropagator()))
    assert seen["x"] == "1"
    assert seen["x-trace-id"] == "abc"
    assert request.headers == {"x": "1"}


def test_circuit_open_raises_normalized_error() -> None:
    client = NodusHttpClient(sync_transport=StubSyncTransport(response=HttpResponse(200, {}, b"", "", None, None)))
    request = HttpRequest(method="GET", url="https://example.test")
    with pytest.raises(HttpCircuitOpenError):
        client.request(request, RequestOptions(circuit_breaker=StubBreaker(should_open=True)))


def test_timeout_error_notifies_breaker() -> None:
    breaker = StubBreaker()
    client = NodusHttpClient(sync_transport=StubSyncTransport(exc=HttpTimeoutError("timeout")))
    request = HttpRequest(method="GET", url="https://example.test")
    with pytest.raises(HttpTimeoutError):
        client.request(request, RequestOptions(circuit_breaker=breaker))
    assert breaker.failures == 1
