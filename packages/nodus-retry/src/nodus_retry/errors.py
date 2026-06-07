class RetryExhaustedError(RuntimeError):
    """Raised when retries are exhausted without a successful result."""


class IdempotencyConflictError(RuntimeError):
    """Raised when a duplicate in-flight effect claim is attempted."""
