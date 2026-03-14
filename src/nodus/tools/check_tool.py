"""Tool wrapper for checking Nodus source."""

from __future__ import annotations

from nodus.result import Result
from nodus.tooling.runner import check_source


TOOL_SPEC = {
    "name": "nodus_check",
    "description": "Parse and compile Nodus source code to return diagnostics.",
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
        stage="check",
        filename=filename,
        stdout="",
        stderr="",
        errors=[{"type": "InputError", "message": message}],
        error={"type": "input", "message": message, "path": filename},
    ).to_dict()


def nodus_check(code: str, filename: str = "<memory>") -> dict:
    if not isinstance(code, str):
        return _input_error("code must be a string", filename)
    if filename is not None and not isinstance(filename, str):
        return _input_error("filename must be a string", filename)
    return check_source(code, filename=filename)
