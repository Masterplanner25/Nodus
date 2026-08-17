"""BuiltinRegistry: collects builtin function registrations from category modules."""

from nodus.builtins.nodus_builtins import BuiltinInfo
from nodus.runtime.capability import ENV, NETWORK, SUBPROCESS


def _denied_reason(what: str, flag: str) -> str:
    """Say how to grant the capability, not merely that it is absent.

    `NodusRuntime` denies these by default (#405 stage 5), so most readers of
    this message never set the flag to False — it was off before they arrived,
    and the useful thing to tell them is how to turn it on.
    """
    return f"{what} is not granted; pass {flag}=True to NodusRuntime to allow it"


def _make_blocked_stub(vm, reason: str, capability: str | None = None):
    """Return a callable that raises a sandbox error for any number of args.

    #405: it now also records the refusal on the event bus. Until this, a denial
    was *raised* and nothing else — so "what did this program try to do that it
    was not allowed to?" had no answer, which is the question an operator running
    generated code actually has. The registration-time gates below
    (`allow_subprocess=False` and friends) are the oldest capability mechanism in
    the runtime and were the least visible.
    """
    def _blocked(*_args):
        from nodus.runtime.capability import CapabilityRequest, emit_denied

        emit_denied(
            getattr(vm, "event_bus", None),
            CapabilityRequest(capability=capability, target=reason, kind="builtin"),
            reason,
        )
        vm.runtime_error("sandbox", f"Blocked: {reason}")
    return _blocked


class BuiltinRegistry:
    """Collects builtin function registrations from category modules.

    VM.__init__ instantiates one BuiltinRegistry, calls register_all(vm) which
    delegates to each category module's register(vm, registry) function, then
    merges .entries into self.builtins.
    """

    def __init__(self) -> None:
        self._entries: dict[str, BuiltinInfo] = {}

    def add(self, name: str, arity: int | tuple, fn) -> None:
        """Register a single builtin by name, arity, and callable."""
        self._entries[name] = BuiltinInfo(name, arity, fn)

    @property
    def entries(self) -> dict[str, BuiltinInfo]:
        return self._entries

    def register_all(self, vm) -> None:
        """Register all extracted builtin category groups onto this registry.

        Called by VM.__init__ before execution begins.  Each category module's
        register(vm, registry) is invoked here so all extracted builtins are
        available to the VM.

        Category module imports are deferred (not module-level) to avoid
        circular imports — the category modules reference VM helper types.
        """
        from nodus.builtins import io as _io
        _io.register(vm, self)
        from nodus.builtins import math as _math_builtins
        _math_builtins.register(vm, self)
        from nodus.builtins import coroutine as _coroutine
        _coroutine.register(vm, self)
        from nodus.builtins import collections as _collections
        _collections.register(vm, self)
        if getattr(vm, "allow_env", True):
            from nodus.builtins import env as _env
            _env.register(vm, self)
        else:
            _blocked = _make_blocked_stub(vm, _denied_reason("environment variable access", "allow_env"), ENV)
            for _name in ("env_get", "env_set", "env_unset", "env_has", "env_list", "env_list_keys"):
                self.add(_name, (0, 1, 2), _blocked)
        from nodus.builtins import time_module as _time
        _time.register(vm, self)
        from nodus.builtins import hash_module as _hash
        _hash.register(vm, self)
        from nodus.builtins import encoding_module as _encoding
        _encoding.register(vm, self)
        from nodus.builtins import secrets_module as _secrets
        _secrets.register(vm, self)
        if getattr(vm, "allow_network", True):
            from nodus.builtins import http_module as _http
            _http.register(vm, self)
        else:
            _blocked = _make_blocked_stub(vm, _denied_reason("network access", "allow_network"), NETWORK)
            for _name in (
                "http_get", "http_post", "http_put", "http_delete", "http_patch",
                "http_head", "http_options_verb", "http_request",
                "http_get_async", "http_post_async", "http_put_async",
                "http_delete_async", "http_patch_async", "http_head_async",
                "http_options_async", "http_request_async",
                "http_stream", "http_sse",
            ):
                self.add(_name, (1, 2, 3), _blocked)
        if getattr(vm, "allow_subprocess", True):
            from nodus.builtins import subprocess_module as _subprocess
            _subprocess.register(vm, self)
        else:
            _blocked = _make_blocked_stub(vm, _denied_reason("subprocess execution", "allow_subprocess"), SUBPROCESS)
            for _name in (
                "subprocess_run", "subprocess_run_async", "subprocess_shell",
                "subprocess_shell_async", "subprocess_spawn", "subprocess_spawn_shell",
                "subprocess_shell_quote",
            ):
                self.add(_name, (1, 2, 3), _blocked)
        from nodus.builtins import tool_module as _tool
        _tool.register(vm, self)
        from nodus.builtins import test_module as _test
        _test.register(vm, self)
        from nodus.builtins import identity_module as _identity
        _identity.register(vm, self)
        from nodus.builtins import memory_module as _memory
        _memory.register(vm, self)
        from nodus.builtins import effects_module as _effects
        _effects.register(vm, self)
        from nodus.builtins import retry_module as _retry
        _retry.register(vm, self)
        from nodus.builtins import circuit_breaker_module as _cb
        _cb.register(vm, self)
