"""sys.v1.* syscall dispatch — versioned, schema-validated, uniform envelope."""

from __future__ import annotations

from nodus.runtime.capability import ALL_CAPABILITIES
from nodus_lang_schema.syscalls import SyscallSpec, parse_syscall_name, validate_input
from nodus_lang_schema.validation import normalize_schema

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
    """Register a syscall, refusing a capability nothing can enforce (#478).

    `SyscallSpec.capability` used to be inert: declared on every syscall,
    published by `syscall_list()`, and read by nothing. A public field named
    `capability` will be taken for an access-control decision, and a host reading
    the registry to discover what it is dealing with was told there was a model
    where there was none.

    Now that `call_syscall` enforces it, the field has to be something the policy
    layer can actually name -- so an unknown or missing capability is refused
    here, at the point of declaration, rather than accepted and quietly skipped
    at dispatch. That would be the same defect one layer along.
    """
    capability = (spec.capability or "").strip()
    if not capability:
        raise ValueError(
            f"syscall {spec.full_name!r} declares no capability; every syscall "
            f"reaches the runtime, so it must name the authority it needs. "
            f"Known: {sorted(ALL_CAPABILITIES)}"
        )
    if capability not in ALL_CAPABILITIES:
        raise ValueError(
            f"syscall {spec.full_name!r} declares unknown capability "
            f"{capability!r}; known: {sorted(ALL_CAPABILITIES)}. Capability "
            f"names are a closed set so the whole authority surface stays "
            f"reviewable; adding one means adding it to ALL_CAPABILITIES."
        )
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

    # #478: the spec's declared capability, enforced. Before this, `capability`
    # was serialized into `syscall_list()` and consulted nowhere, so a policy
    # denying `memory.write` watched `sys.v1.memory.put` succeed.
    #
    # This is the second gate on the path, not a replacement for the first: the
    # `syscall` builtin carries the `syscall` capability (#473), so a policy can
    # refuse syscalls wholesale there, or allow them and refuse *this* one here.
    # Both requests reach the policy, which is the point -- "no syscalls" and
    # "no memory writes, however you spell them" are different intents.
    #
    # A refusal raises rather than returning an error envelope. `kind ==
    # "sandbox"` is the pinned denial contract, and a capability refusal dressed
    # as a handler failure would be classified as one downstream.
    if vm is not None and hasattr(vm, "check_capability"):
        vm.check_capability(spec.capability, name, "syscall", (payload,))

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
