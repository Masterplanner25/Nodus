"""Runtime registry and dispatch for agent calls."""

from __future__ import annotations

from nodus.result import Result, normalize_filename
from nodus.vm.runtime_values import clone_json_value, is_json_safe, payload_keys


AGENT_REGISTRY: dict[str, dict] = {}


def register_agent(name: str, handler, *, description: str | None = None, payload_schema: dict | None = None) -> None:
    AGENT_REGISTRY[name] = {
        "handler": handler,
        "spec": {
            "name": name,
            "description": description or f"Agent handler for {name}",
            "parameters": payload_schema or {"type": "object"},
        },
    }


def unregister_agent(name: str) -> None:
    AGENT_REGISTRY.pop(name, None)


def available_agents() -> list[str]:
    return sorted(AGENT_REGISTRY.keys())


def describe_agent(name: str):
    if not isinstance(name, str):
        return None
    entry = AGENT_REGISTRY.get(name)
    if entry is None:
        return None
    return dict(entry["spec"])


def call_agent(name, payload, *, vm=None) -> dict:
    filename = normalize_filename(getattr(vm, "source_path", None))
    if not isinstance(name, str) or not name:
        return _agent_error("Agent name must be a non-empty string", filename, name=name)
    if not is_json_safe(payload):
        return _agent_error("Agent payload must be JSON-safe", filename, name=name)

    _emit(vm, "agent_call_start", name=name, payload=payload)
    entry = AGENT_REGISTRY.get(name)
    if entry is None:
        result = _agent_error(f"No handler registered for agent '{name}'", filename, name=name)
        _emit(vm, "agent_call_fail", name=name, payload=payload, ok=False, error=_error_message(result))
        return result

    try:
        handler_result = entry["handler"](clone_json_value(payload))
    except Exception as err:
        result = _agent_error(str(err), filename, name=name)
        _emit(vm, "agent_call_fail", name=name, payload=payload, ok=False, error=_error_message(result))
        return result

    if not is_json_safe(handler_result):
        result = _agent_error("Agent handler returned a non-serializable value", filename, name=name)
        _emit(vm, "agent_call_fail", name=name, payload=payload, ok=False, error=_error_message(result))
        return result

    result = Result.success(
        stage="agent_call",
        filename=filename,
        stdout="",
        stderr="",
        result=clone_json_value(handler_result),
    ).to_dict()
    _emit(vm, "agent_call_complete", name=name, payload=payload, ok=True)
    return result


def _agent_error(message: str, filename: str, *, name: str | None = None) -> dict:
    legacy = {"type": "agent", "message": message, "path": filename}
    if name is not None:
        legacy["agent"] = name
    return Result.failure(
        stage="agent_call",
        filename=filename,
        stdout="",
        stderr="",
        errors=[{"type": "AgentError", "message": message, "agent": name}],
        error=legacy,
    ).to_dict()


def _error_message(result: dict | None) -> str:
    if not isinstance(result, dict):
        return "Agent call failed"
    err = result.get("error")
    if isinstance(err, dict):
        return str(err.get("message", "Agent call failed"))
    return "Agent call failed"


def _emit(vm, event_type: str, *, name: str, payload, ok: bool | None = None, error: str | None = None) -> None:
    if vm is None or getattr(vm, "event_bus", None) is None:
        return
    data = {"payload_keys": payload_keys(payload)}
    if hasattr(vm, "runtime_adapter_event_data"):
        data.update(vm.runtime_adapter_event_data(payload, ok=ok, error=error))
    vm.event_bus.emit_event(event_type, name=name, data=data)
