"""Runtime registry and dispatch for built-in tool calls."""

from __future__ import annotations

from nodus.result import Result, normalize_filename
from nodus.vm.runtime_values import is_json_safe, payload_keys


TOOL_REGISTRY: dict[str, dict] = {}


def _ensure_registry() -> None:
    if TOOL_REGISTRY:
        return
    from nodus.tools import (
        AST_TOOL_SPEC,
        CHECK_TOOL_SPEC,
        DIS_TOOL_SPEC,
        EXECUTE_TOOL_SPEC,
        nodus_ast,
        nodus_check,
        nodus_dis,
        nodus_execute,
    )

    TOOL_REGISTRY.update(
        {
            "nodus_execute": {"handler": nodus_execute, "spec": EXECUTE_TOOL_SPEC},
            "nodus_check": {"handler": nodus_check, "spec": CHECK_TOOL_SPEC},
            "nodus_ast": {"handler": nodus_ast, "spec": AST_TOOL_SPEC},
            "nodus_dis": {"handler": nodus_dis, "spec": DIS_TOOL_SPEC},
        }
    )


def available_tools() -> list[str]:
    _ensure_registry()
    return sorted(TOOL_REGISTRY.keys())


def describe_tool(name: str):
    _ensure_registry()
    if not isinstance(name, str):
        return None
    entry = TOOL_REGISTRY.get(name)
    if entry is None:
        return None
    return dict(entry["spec"])


def call_tool(name, args, *, vm=None) -> dict:
    _ensure_registry()
    filename = normalize_filename(getattr(vm, "source_path", None))
    if not isinstance(name, str) or not name:
        return _tool_error("Tool name must be a non-empty string", filename)
    entry = TOOL_REGISTRY.get(name)
    if entry is None:
        return _tool_error(f"Unknown tool: {name}", filename, name=name)
    if not isinstance(args, dict):
        return _tool_error("tool_call(name, args) expects args as a map", filename, name=name)
    if not is_json_safe(args):
        return _tool_error("Tool args must be JSON-safe maps, lists, and primitives", filename, name=name)

    _emit(vm, "tool_call_start", name=name, payload=args)
    try:
        result = entry["handler"](**args)
    except TypeError as err:
        result = _tool_error(str(err), filename, name=name)
    except Exception as err:
        result = _tool_error(str(err), filename, name=name)

    if isinstance(result, dict) and result.get("ok"):
        _emit(vm, "tool_call_complete", name=name, payload=args, ok=True)
        return result

    _emit(vm, "tool_call_fail", name=name, payload=args, ok=False, error=_error_message(result))
    return result if isinstance(result, dict) else _tool_error("Tool returned invalid result", filename, name=name)


def _tool_error(message: str, filename: str, *, name: str | None = None) -> dict:
    legacy = {"type": "tool", "message": message, "path": filename}
    if name is not None:
        legacy["tool"] = name
    return Result.failure(
        stage="tool_call",
        filename=filename,
        stdout="",
        stderr="",
        errors=[{"type": "ToolError", "message": message, "tool": name}],
        error=legacy,
    ).to_dict()


def _error_message(result: dict | None) -> str:
    if not isinstance(result, dict):
        return "Tool call failed"
    err = result.get("error")
    if isinstance(err, dict):
        return str(err.get("message", "Tool call failed"))
    return "Tool call failed"


def _emit(vm, event_type: str, *, name: str, payload: dict, ok: bool | None = None, error: str | None = None) -> None:
    if vm is None or getattr(vm, "event_bus", None) is None:
        return
    data = {"payload_keys": payload_keys(payload)}
    if hasattr(vm, "runtime_adapter_event_data"):
        data.update(vm.runtime_adapter_event_data(payload, ok=ok, error=error))
    vm.event_bus.emit_event(event_type, name=name, data=data)
