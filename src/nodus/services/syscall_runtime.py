"""sys.v1.* syscall dispatch — versioned, schema-validated, uniform envelope."""

from __future__ import annotations

from nodus_schema.syscalls import SyscallSpec, parse_syscall_name, validate_input
from nodus_schema.validation import normalize_schema

# ---------------------------------------------------------------------------
# Envelope helpers
# ---------------------------------------------------------------------------

def _ok(data: dict, *, trace_id: str | None = None) -> dict:
    return {"status": "ok", "data": data, "error": None, "trace_id": trace_id}


def _err(message: str, *, trace_id: str | None = None) -> dict:
    return {"status": "error", "data": None, "error": message, "trace_id": trace_id}


# ---------------------------------------------------------------------------
# Registry and registration helpers
# ---------------------------------------------------------------------------

SYSCALL_REGISTRY: dict[str, dict] = {}
_registry_built = False


def register_syscall(spec: SyscallSpec, handler) -> None:
    SYSCALL_REGISTRY[spec.full_name] = {"spec": spec, "handler": handler}


def _ensure_registry() -> None:
    global _registry_built
    if _registry_built:
        return
    _registry_built = True
    from nodus.services.memory_runtime import get_value, put_value, delete_value, recall_from

    register_syscall(
        SyscallSpec(
            name="memory.get",
            version="v1",
            capability="memory.read",
            description="Read a value from the runtime memory store by key.",
            input_schema={"key": "str"},
            output_schema={"value": "any"},
        ),
        lambda payload, vm=None: {"value": get_value(payload["key"], vm=vm)},
    )

    register_syscall(
        SyscallSpec(
            name="memory.put",
            version="v1",
            capability="memory.write",
            description="Write a value to the runtime memory store.",
            input_schema={"key": "str", "value": "any"},
            output_schema={"value": "any"},
        ),
        lambda payload, vm=None: {"value": put_value(payload["key"], payload["value"], vm=vm)},
    )

    register_syscall(
        SyscallSpec(
            name="memory.delete",
            version="v1",
            capability="memory.write",
            description="Delete a key from the runtime memory store.",
            input_schema={"key": "str"},
            output_schema={"found": "bool"},
        ),
        lambda payload, vm=None: {"found": delete_value(payload["key"], vm=vm)},
    )

    register_syscall(
        SyscallSpec(
            name="memory.recall_from",
            version="v1",
            capability="memory.read",
            description="Recall a value from a namespaced memory store.",
            input_schema={"ns": "str", "key": "str"},
            output_schema={"value": "any"},
        ),
        lambda payload, vm=None: {"value": recall_from(payload["ns"], payload["key"], vm=vm)},
    )


def list_syscalls() -> list[dict]:
    _ensure_registry()
    return [entry["spec"].to_dict() for entry in SYSCALL_REGISTRY.values()]


# ---------------------------------------------------------------------------
# Dispatch
# ---------------------------------------------------------------------------

def call_syscall(name: str, payload: dict, *, vm=None) -> dict:
    """Dispatch a sys.v1.* call and return a uniform envelope."""
    _ensure_registry()

    trace_id = getattr(vm, "trace_id", None)

    if not isinstance(name, str):
        return _err("Syscall name must be a string", trace_id=trace_id)

    try:
        parse_syscall_name(name)
    except ValueError as exc:
        return _err(str(exc), trace_id=trace_id)

    entry = SYSCALL_REGISTRY.get(name)
    if entry is None:
        _emit(vm, "syscall_error", name=name, trace_id=trace_id, error=f"Unknown syscall: {name!r}")
        return _err(f"Unknown syscall: {name!r}", trace_id=trace_id)

    spec: SyscallSpec = entry["spec"]
    handler = entry["handler"]

    if not isinstance(payload, dict):
        payload = {}

    normalized_schema, schema_err = normalize_schema(spec.input_schema)
    if schema_err:
        return _err(f"Bad syscall schema: {schema_err}", trace_id=trace_id)
    errors = validate_input(normalized_schema or {}, payload)
    if errors:
        return _err("; ".join(errors), trace_id=trace_id)

    try:
        data = handler(payload, vm=vm)
    except Exception as exc:
        _emit(vm, "syscall_error", name=name, error=str(exc), trace_id=trace_id)
        return _err(str(exc), trace_id=trace_id)

    _emit(vm, "syscall_complete", name=name, trace_id=trace_id)
    return _ok(data if isinstance(data, dict) else {}, trace_id=trace_id)


# ---------------------------------------------------------------------------
# Event emission
# ---------------------------------------------------------------------------

def _emit(vm, event_type: str, *, name: str, trace_id: str | None = None, error: str | None = None) -> None:
    if vm is None or getattr(vm, "event_bus", None) is None:
        return
    data: dict = {"syscall": name}
    if trace_id is not None:
        data["trace_id"] = trace_id
    if error is not None:
        data["error"] = error
    vm.event_bus.emit_event(event_type, name=name, data=data)
