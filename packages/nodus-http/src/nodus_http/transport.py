from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

import httpx

from .errors import HttpCallError, HttpTimeoutError
from .models import HttpRequest, HttpResponse


def _normalize_error(exc: Exception) -> HttpCallError:
    if isinstance(exc, httpx.TimeoutException):
        return HttpTimeoutError(str(exc))
    return HttpCallError(str(exc))


def _response_from_httpx(response: httpx.Response, request: HttpRequest) -> HttpResponse:
    json_value: Any | None = None
    try:
        json_value = response.json()
    except (ValueError, json.JSONDecodeError):
        json_value = None
    return HttpResponse(
        status_code=response.status_code,
        headers=dict(response.headers),
        body=response.content,
        text=response.text,
        json_value=json_value,
        metadata=request.metadata,
    )


@dataclass(slots=True)
class DefaultSyncTransport:
    client: httpx.Client | None = None

    def send(self, request: HttpRequest, *, follow_redirects: bool | None = None) -> HttpResponse:
        client = self.client or httpx.Client()
        close_when_done = self.client is None
        try:
            response = client.request(
                method=request.method,
                url=request.url,
                headers=dict(request.headers),
                params=dict(request.query),
                json=request.json_body,
                content=request.body,
                timeout=request.timeout_seconds,
                follow_redirects=follow_redirects if follow_redirects is not None else False,
            )
            return _response_from_httpx(response, request)
        except Exception as exc:
            raise _normalize_error(exc) from exc
        finally:
            if close_when_done:
                client.close()


@dataclass(slots=True)
class DefaultAsyncTransport:
    client: httpx.AsyncClient | None = None

    async def send(self, request: HttpRequest, *, follow_redirects: bool | None = None) -> HttpResponse:
        client = self.client or httpx.AsyncClient()
        close_when_done = self.client is None
        try:
            response = await client.request(
                method=request.method,
                url=request.url,
                headers=dict(request.headers),
                params=dict(request.query),
                json=request.json_body,
                content=request.body,
                timeout=request.timeout_seconds,
                follow_redirects=follow_redirects if follow_redirects is not None else False,
            )
            return _response_from_httpx(response, request)
        except Exception as exc:
            raise _normalize_error(exc) from exc
        finally:
            if close_when_done:
                await client.aclose()
