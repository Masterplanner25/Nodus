"""Retry stdlib builtins — wraps nodus-retry (optional dep)."""

from __future__ import annotations

try:
    from nodus_retry import execute_with_retry, RetryPolicy
    from nodus_retry.policy import resolve_retry_policy
    _RETRY_AVAILABLE = True
except ImportError:
    _RETRY_AVAILABLE = False

from nodus.vm.vm import Closure, _ClosureProxy

_DEPENDENCY_ERR = {"kind": "dependency_error", "message": "nodus-retry package not installed"}


def _policy_from_map(policy_map: dict) -> "RetryPolicy":
    if not _RETRY_AVAILABLE:
        raise ImportError("nodus-retry not available")
    name = policy_map.get("name")
    if isinstance(name, str):
        return resolve_retry_policy(name.upper())
    return RetryPolicy(
        max_attempts=int(policy_map.get("max_attempts", 1)),
        backoff_ms=int(policy_map.get("backoff_ms", 0)),
        exponential_backoff=bool(policy_map.get("exponential_backoff", False)),
        high_risk_immediate_fail=bool(policy_map.get("high_risk_immediate_fail", False)),
    )


def register(vm, registry) -> None:
    def retry_available():
        return _RETRY_AVAILABLE

    def retry_call(fn_value, policy_map):
        if not _RETRY_AVAILABLE:
            return _DEPENDENCY_ERR
        if not isinstance(fn_value, Closure):
            vm.runtime_error("type", "retry_call(fn, policy) expects a function as first argument")
        if not isinstance(policy_map, dict):
            vm.runtime_error("type", "retry_call(fn, policy) expects a map as second argument")
        try:
            policy = _policy_from_map(policy_map)
        except Exception as exc:
            vm.runtime_error("type", f"retry_call: invalid policy: {exc}")

        def execute_fn():
            if isinstance(fn_value, _ClosureProxy):
                return fn_value.caller_vm.run_closure(fn_value._proxied_closure, [])
            return vm.run_closure(fn_value, [])

        return execute_with_retry(execute_fn, policy=policy)

    registry.add("retry_available", 0, retry_available)
    registry.add("retry_call", 2, retry_call)
