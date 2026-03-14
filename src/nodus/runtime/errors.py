"""Structured error types for Nodus execution."""

from __future__ import annotations

from dataclasses import dataclass, field

from nodus.runtime.diagnostics import LangRuntimeError, LangSyntaxError


@dataclass
class NodusError(Exception):
    error_type: str = "Error"
    message: str = ""
    line: int | None = None
    column: int | None = None
    filename: str | None = None
    stack: list[str] | None = None
    details: dict | None = None

    def __init__(
        self,
        message: str,
        *,
        line: int | None = None,
        column: int | None = None,
        filename: str | None = None,
        stack: list[str] | None = None,
        details: dict | None = None,
    ):
        super().__init__(message)
        self.message = message
        self.line = line
        self.column = column
        self.filename = filename
        self.stack = stack or None
        self.details = details or None

    def to_dict(self) -> dict:
        payload = {
            "type": self.error_type,
            "message": self.message,
            "line": self.line,
            "column": self.column,
            "filename": self.filename,
            "stack": self.stack,
        }
        if self.details:
            payload["details"] = self.details
        return payload


class NodusRuntimeError(NodusError):
    error_type = "RuntimeError"


class NodusCompileError(NodusError):
    error_type = "CompileError"


class NodusParseError(NodusError):
    error_type = "SyntaxError"


class NodusSandboxError(NodusError):
    error_type = "SandboxError"


class BytecodeVersionError(RuntimeError):
    pass


def coerce_error(err: Exception, *, stage: str | None = None, filename: str | None = None) -> NodusError:
    if isinstance(err, NodusError):
        if err.filename is None and filename is not None:
            err.filename = filename
        return err
    if isinstance(err, LangSyntaxError):
        return NodusParseError(
            str(err),
            line=err.line,
            column=err.col,
            filename=err.path or filename,
        )
    if isinstance(err, LangRuntimeError):
        cls = NodusSandboxError if err.kind == "sandbox" else NodusRuntimeError
        details = {"kind": err.kind}
        return cls(
            str(err),
            line=err.line,
            column=err.col,
            filename=err.path or filename,
            stack=err.stack,
            details=details,
        )
    if isinstance(err, SyntaxError):
        return NodusParseError(
            str(err),
            line=getattr(err, "lineno", None),
            column=getattr(err, "offset", None),
            filename=getattr(err, "filename", None) or filename,
        )
    if stage in {"compile", "check", "disassemble", "ast", "plan", "graph"}:
        return NodusCompileError(str(err), filename=filename)
    if stage == "parse":
        return NodusParseError(str(err), filename=filename)
    return NodusRuntimeError(str(err), filename=filename)


def legacy_error_dict(err: Exception, *, filename: str | None = None) -> dict:
    if isinstance(err, LangRuntimeError):
        return {
            "type": "sandbox" if err.kind == "sandbox" else "runtime",
            "kind": err.kind,
            "message": str(err),
            "path": err.path or filename,
            "line": err.line,
            "column": err.col,
            "stack": err.stack,
        }
    if isinstance(err, LangSyntaxError):
        return {
            "type": "syntax",
            "message": str(err),
            "path": err.path or filename,
            "line": err.line,
            "column": err.col,
        }
    if isinstance(err, SyntaxError):
        return {
            "type": "syntax",
            "message": str(err),
            "path": getattr(err, "filename", None) or filename,
            "line": getattr(err, "lineno", None),
            "column": getattr(err, "offset", None),
        }
    if isinstance(err, TypeError):
        return {
            "type": "type",
            "message": str(err),
            "path": getattr(err, "path", None) or filename,
            "line": getattr(err, "line", None),
            "column": getattr(err, "col", None),
        }
    return {
        "type": "error",
        "message": str(err),
        "path": filename,
    }


def format_error_payload(payload: dict) -> str:
    err_type = payload.get("type")
    kind = payload.get("kind")
    message = payload.get("message", "")
    path = payload.get("path")
    line = payload.get("line")
    column = payload.get("column")

    if path and line is not None and column is not None:
        location = f"{path}:{line}:{column}"
    elif path:
        location = path
    elif line is not None and column is not None:
        location = f"line {line}, col {column}"
    else:
        location = None

    if err_type == "syntax":
        prefix = "Syntax error"
    elif err_type == "sandbox":
        prefix = "Sandbox error"
    elif err_type == "runtime":
        if kind:
            prefix = f"{kind.capitalize()} error"
        else:
            prefix = "Runtime error"
    elif err_type == "error":
        prefix = "Error"
    else:
        prefix = f"{str(err_type).capitalize()} error" if err_type else "Error"

    if location:
        text = f"{prefix} at {location}: {message}"
    else:
        text = f"{prefix}: {message}"

    stack = payload.get("stack")
    if stack:
        return text + "\nStack trace:\n  " + "\n  ".join(stack)
    return text
