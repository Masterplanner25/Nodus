from __future__ import annotations

from .errors import HttpCallError, HttpCircuitOpenError
from .models import HttpRequest, HttpResponse, RequestOptions
from .transport import DefaultAsyncTransport, DefaultSyncTransport


class NodusHttpClient:
    def __init__(
        self,
        *,
        sync_transport: DefaultSyncTransport | None = None,
        async_transport: DefaultAsyncTransport | None = None,
    ) -> None:
        self._sync_transport = sync_transport or DefaultSyncTransport()
        self._async_transport = async_transport or DefaultAsyncTransport()

    def request(self, request: HttpRequest, options: RequestOptions | None = None) -> HttpResponse:
        options = options or RequestOptions()
        prepared = self._prepare_request(request, options)
        breaker = options.circuit_breaker
        operation_name = prepared.metadata.operation_name if prepared.metadata else prepared.method

        try:
            if breaker is not None:
                try:
                    breaker.before_call(operation_name, prepared.metadata)
                except Exception as exc:
                    raise HttpCircuitOpenError(str(exc)) from exc

            def do_send() -> HttpResponse:
                return self._sync_transport.send(prepared, follow_redirects=options.follow_redirects)

            if options.retry_executor is not None:
                response = options.retry_executor.execute(
                    operation_name=operation_name,
                    metadata=prepared.metadata,
                    fn=do_send,
                )
            else:
                response = do_send()

            if breaker is not None:
                breaker.after_success(operation_name, prepared.metadata)
            return response
        except HttpCallError as exc:
            if breaker is not None:
                breaker.after_failure(operation_name, exc, prepared.metadata)
            raise
        except Exception as exc:
            if breaker is not None:
                breaker.after_failure(operation_name, exc, prepared.metadata)
            raise

    async def arequest(self, request: HttpRequest, options: RequestOptions | None = None) -> HttpResponse:
        options = options or RequestOptions()
        prepared = self._prepare_request(request, options)
        breaker = options.circuit_breaker
        operation_name = prepared.metadata.operation_name if prepared.metadata else prepared.method

        try:
            if breaker is not None:
                try:
                    breaker.before_call(operation_name, prepared.metadata)
                except Exception as exc:
                    raise HttpCircuitOpenError(str(exc)) from exc

            async def do_send() -> HttpResponse:
                return await self._async_transport.send(prepared, follow_redirects=options.follow_redirects)

            if options.retry_executor is not None:
                response = await options.retry_executor.aexecute(
                    operation_name=operation_name,
                    metadata=prepared.metadata,
                    fn=do_send,
                )
            else:
                response = await do_send()

            if breaker is not None:
                breaker.after_success(operation_name, prepared.metadata)
            return response
        except HttpCallError as exc:
            if breaker is not None:
                breaker.after_failure(operation_name, exc, prepared.metadata)
            raise
        except Exception as exc:
            if breaker is not None:
                breaker.after_failure(operation_name, exc, prepared.metadata)
            raise

    @staticmethod
    def _prepare_request(request: HttpRequest, options: RequestOptions) -> HttpRequest:
        headers = dict(request.headers)
        if options.trace_propagator is not None:
            headers = options.trace_propagator.inject(headers, request.metadata)
        return HttpRequest(
            method=request.method,
            url=request.url,
            headers=headers,
            query=dict(request.query),
            json_body=request.json_body,
            body=request.body,
            timeout_seconds=request.timeout_seconds,
            metadata=request.metadata,
        )
