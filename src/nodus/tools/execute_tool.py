"""Tool wrapper for executing Nodus source."""

from __future__ import annotations

from nodus.result import Result
from nodus.tooling.runner import run_source


TOOL_SPEC = {
    "name": "nodus_execute",
    "description": "Execute Nodus source code and return stdout, result, and errors.",
    "parameters": {
        "type": "object",
        "properties": {
            "code": {"type": "string"},
            "filename": {"type": "string"},
        },
        "required": ["code"],
    },
}


def _input_error(message: str, filename: str | None) -> dict:
    return Result.failure(
        stage="execute",
        filename=filename,
        stdout="",
        stderr="",
        errors=[{"type": "InputError", "message": message}],
        error={"type": "input", "message": message, "path": filename},
    ).to_dict()


def nodus_execute(code: str, filename: str = "<memory>") -> dict:
    if not isinstance(code, str):
        return _input_error("code must be a string", filename)
    if filename is not None and not isinstance(filename, str):
        return _input_error("filename must be a string", filename)
    result, _vm = run_source(code, filename=filename)
    return result
