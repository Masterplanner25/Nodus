"""Circuit breaker stdlib builtins — wraps nodus-circuit-breaker (optional dep)."""

from __future__ import annotations

try:
    from nodus_circuit_breaker.breaker import CircuitBreaker, CircuitOpenError
    _CB_AVAILABLE = True
except ImportError:
    _CB_AVAILABLE = False

from nodus.vm.types import Closure, _ClosureProxy

_DEPENDENCY_ERR = {"kind": "dependency_error", "message": "nodus-circuit-breaker package not installed"}


def _state_str(cb) -> str:
    return str(cb.state).split(".")[-1].lower()


def register(vm, registry) -> None:
    def cb_available():
        return _CB_AVAILABLE

    def cb_create(name, failure_threshold, recovery_timeout_secs):
        if not _CB_AVAILABLE:
            return _DEPENDENCY_ERR
        if not isinstance(name, str) or not name:
            vm.runtime_error("type", "cb_create(name, ...) expects a non-empty string name")
        threshold = int(failure_threshold) if failure_threshold is not None else 3
        timeout = int(recovery_timeout_secs) if recovery_timeout_secs is not None else 60
        cb = CircuitBreaker(name, failure_threshold=threshold, recovery_timeout_secs=timeout)
        vm.circuit_breakers[name] = cb
        return name

    def cb_call(name, fn_value):
        if not _CB_AVAILABLE:
            return _DEPENDENCY_ERR
        if not isinstance(name, str):
            vm.runtime_error("type", "cb_call(name, fn) expects a string name")
        if not isinstance(fn_value, Closure):
            vm.runtime_error("type", "cb_call(name, fn) expects a function")
        cb = vm.circuit_breakers.get(name)
        if cb is None:
            vm.runtime_error("key", f"No circuit breaker registered with name: {name!r}")
        def _invoke():
            if isinstance(fn_value, _ClosureProxy):
                return fn_value.caller_vm.run_closure(fn_value._proxied_closure, [])
            return vm.run_closure(fn_value, [])
        try:
            return cb.call(_invoke)
        except CircuitOpenError:
            return {"kind": "circuit_open", "message": f"Circuit '{name}' is open"}
        except Exception as exc:
            return {"kind": "error", "message": str(exc)}

    def cb_state(name):
        if not _CB_AVAILABLE:
            return "unavailable"
        cb = vm.circuit_breakers.get(name)
        if cb is None:
            vm.runtime_error("key", f"No circuit breaker registered with name: {name!r}")
        return _state_str(cb)

    def cb_reset(name):
        if not _CB_AVAILABLE:
            return _DEPENDENCY_ERR
        cb = vm.circuit_breakers.get(name)
        if cb is None:
            vm.runtime_error("key", f"No circuit breaker registered with name: {name!r}")
        cb.reset()
        return None

    registry.add("cb_available", 0, cb_available)
    registry.add("cb_create", 3, cb_create)
    registry.add("cb_call", 2, cb_call)
    registry.add("cb_state", 1, cb_state)
    registry.add("cb_reset", 1, cb_reset)
