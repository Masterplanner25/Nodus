from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class HttpCallMetadata:
    service_name: str
    operation_name: str
    endpoint_name: str | None = None
    trace_id: str | None = None
    correlation_id: str | None = None
    tags: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class HttpRequest:
    method: str
    url: str
    headers: dict[str, str] = field(default_factory=dict)
    query: dict[str, str | int | float | bool | None] = field(default_factory=dict)
    json_body: Any | None = None
    body: bytes | str | None = None
    timeout_seconds: float | None = None
    metadata: HttpCallMetadata | None = None

    def __post_init__(self) -> None:
        if self.json_body is not None and self.body is not None:
            raise ValueError("HttpRequest may define only one of json_body or body.")


@dataclass(frozen=True, slots=True)
class RequestOptions:
    retry_executor: Any | None = None
    circuit_breaker: Any | None = None
    trace_propagator: Any | None = None
    follow_redirects: bool | None = None


@dataclass(frozen=True, slots=True)
class HttpResponse:
    status_code: int
    headers: dict[str, str]
    body: bytes
    text: str
    json_value: Any | None
    metadata: HttpCallMetadata | None = None

    @property
    def is_success(self) -> bool:
        return 200 <= self.status_code < 300
