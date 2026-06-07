class HttpCallError(RuntimeError):
    """Base error for normalized outbound HTTP failures."""


class HttpTimeoutError(HttpCallError):
    """Raised when the underlying transport times out."""


class HttpCircuitOpenError(HttpCallError):
    """Raised when a configured circuit breaker rejects a call."""
