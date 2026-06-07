class SqlStoreError(RuntimeError):
    """Base error for SQL store adapter failures."""


class RecordNotFoundError(SqlStoreError):
    """Raised when a requested record does not exist."""


class OptimisticLockError(SqlStoreError):
    """Raised when an update loses an optimistic concurrency check."""
