from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Protocol

from .models import HttpCallMetadata, HttpResponse


class RetryExecutor(Protocol):
    def execute(
        self,
        *,
        operation_name: str,
        metadata: HttpCallMetadata | None,
        fn: Callable[[], HttpResponse],
    ) -> HttpResponse: ...

    async def aexecute(
        self,
        *,
        operation_name: str,
        metadata: HttpCallMetadata | None,
        fn: Callable[[], Awaitable[HttpResponse]],
    ) -> HttpResponse: ...


class CircuitBreaker(Protocol):
    def before_call(self, operation_name: str, metadata: HttpCallMetadata | None) -> None: ...

    def after_success(self, operation_name: str, metadata: HttpCallMetadata | None) -> None: ...

    def after_failure(
        self,
        operation_name: str,
        error: Exception,
        metadata: HttpCallMetadata | None,
    ) -> None: ...


class TracePropagator(Protocol):
    def inject(
        self,
        headers: dict[str, str],
        metadata: HttpCallMetadata | None,
    ) -> dict[str, str]: ...
