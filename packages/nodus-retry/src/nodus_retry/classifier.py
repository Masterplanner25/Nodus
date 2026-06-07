from __future__ import annotations

from .backoff import compute_backoff_delay
from .models import ExecutionGuarantee, RetryDecision, RetryPolicy


def classify_exception(
    exception: BaseException,
    *,
    attempt_number: int,
    policy: RetryPolicy,
    guarantee: ExecutionGuarantee,
    operation_name: str,
) -> RetryDecision:
    _ = guarantee
    _ = operation_name
    if policy.high_risk_no_retry:
        return RetryDecision(False, attempt_number, None, "high_risk_no_retry")

    if isinstance(exception, policy.non_retryable_exceptions):
        return RetryDecision(False, attempt_number, None, "non_retryable_exception")

    if policy.retryable_exceptions and not isinstance(exception, policy.retryable_exceptions):
        return RetryDecision(False, attempt_number, None, "not_classified_retryable")

    if attempt_number >= policy.max_attempts:
        return RetryDecision(False, attempt_number, None, "max_attempts_reached")

    return RetryDecision(
        True,
        attempt_number,
        compute_backoff_delay(policy.backoff, attempt_number=attempt_number),
        "retryable_exception",
    )
