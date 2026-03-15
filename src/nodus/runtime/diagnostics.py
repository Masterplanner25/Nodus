"""Diagnostics and error formatting for Nodus."""

from __future__ import annotations

from dataclasses import dataclass, field


ERROR_SEVERITY = "error"
WARNING_SEVERITY = "warning"
INFO_SEVERITY = "info"
HINT_SEVERITY = "hint"

LSP_SEVERITY = {
    ERROR_SEVERITY: 1,
    WARNING_SEVERITY: 2,
    INFO_SEVERITY: 3,
    HINT_SEVERITY: 4,
}


@dataclass(frozen=True)
class DiagnosticRelatedInformation:
    message: str
    file: str | None = None
    line: int | None = None
    column: int | None = None

    def to_lsp(self) -> dict:
        filename = self.file or "<memory>"
        start_line = max((self.line or 1) - 1, 0)
        start_col = max((self.column or 1) - 1, 0)
        end_col = start_col + 1
        return {
            "location": {
                "uri": filename if "://" in filename else _path_to_uri(filename),
                "range": {
                    "start": {"line": start_line, "character": start_col},
                    "end": {"line": start_line, "character": end_col},
                },
            },
            "message": self.message,
        }


@dataclass(frozen=True)
class RuntimeDiagnostic:
    message: str
    severity: str = ERROR_SEVERITY
    source: str = "nodus"
    file: str | None = None
    line: int | None = None
    column: int | None = None
    end_column: int | None = None
    related_information: list[DiagnosticRelatedInformation] = field(default_factory=list)

    def to_lsp(self) -> dict:
        start_line = max((self.line or 1) - 1, 0)
        start_col = max((self.column or 1) - 1, 0)
        end_col = max((self.end_column or self.column or 1) - 1, start_col)
        payload = {
            "range": {
                "start": {"line": start_line, "character": start_col},
                "end": {"line": start_line, "character": end_col},
            },
            "severity": LSP_SEVERITY.get(self.severity, 1),
            "source": self.source,
            "message": self.message,
            "line": self.line,
            "column": self.column,
            "file": self.file,
        }
        if self.related_information:
            payload["relatedInformation"] = [item.to_lsp() for item in self.related_information]
        return payload


def _path_to_uri(path: str) -> str:
    try:
        from pathlib import Path

        return Path(path).resolve().as_uri()
    except Exception:
        return path


class LangSyntaxError(SyntaxError):
    def __init__(self, message: str, line: int | None = None, col: int | None = None, path: str | None = None):
        super().__init__(message)
        self.line = line
        self.col = col
        self.path = path


class LangRuntimeError(RuntimeError):
    def __init__(
        self,
        kind: str,
        message: str,
        line: int | None = None,
        col: int | None = None,
        path: str | None = None,
        stack: list[str] | None = None,
        payload: object = None,
    ):
        super().__init__(message)
        self.kind = kind
        self.line = line
        self.col = col
        self.path = path
        self.stack = stack or []
        self.payload = payload


class RuntimeLimitExceeded(LangRuntimeError):
    def __init__(
        self,
        message: str,
        line: int | None = None,
        col: int | None = None,
        path: str | None = None,
        stack: list[str] | None = None,
    ):
        super().__init__("sandbox", message, line=line, col=col, path=path, stack=stack)


def diagnostic_from_error(
    err: Exception,
    *,
    message: str | None = None,
    severity: str = ERROR_SEVERITY,
    source: str = "nodus",
    file: str | None = None,
) -> RuntimeDiagnostic:
    diag_file = getattr(err, "path", None) or getattr(err, "filename", None) or file
    line = getattr(err, "line", None) or getattr(err, "lineno", None)
    column = getattr(err, "col", None) or getattr(err, "column", None) or getattr(err, "offset", None)
    return RuntimeDiagnostic(
        message=message or str(err),
        severity=severity,
        source=source,
        file=diag_file,
        line=line,
        column=column,
        end_column=(column + 1) if column is not None else None,
    )


def format_error(err: Exception, path: str | None = None) -> str:
    err_path = getattr(err, "path", None) or path
    line = getattr(err, "line", None)
    col = getattr(err, "col", None)
    if err_path and line is not None and col is not None:
        location = f"{err_path}:{line}:{col}"
    elif err_path:
        location = err_path
    elif line is not None and col is not None:
        location = f"line {line}, col {col}"
    else:
        location = None

    if isinstance(err, LangSyntaxError):
        if location:
            return f"Syntax error at {location}: {err}"
        return f"Syntax error: {err}"
    if isinstance(err, LangRuntimeError):
        kind = err.kind.capitalize()
        if location:
            base = f"{kind} error at {location}: {err}"
        else:
            base = f"{kind} error: {err}"
        if err.stack:
            return base + "\nStack trace:\n  " + "\n  ".join(err.stack)
        return base
    if isinstance(err, SyntaxError):
        if location:
            return f"Syntax error at {location}: {err}"
        return f"Syntax error: {err}"
    if isinstance(err, NameError):
        if location:
            return f"Name error at {location}: {err}"
        return f"Name error: {err}"
    if isinstance(err, IndexError):
        if location:
            return f"Index error at {location}: {err}"
        return f"Index error: {err}"
    if isinstance(err, KeyError):
        if location:
            return f"Key error at {location}: {err}"
        return f"Key error: {err}"
    if isinstance(err, TypeError):
        if location:
            return f"Type error at {location}: {err}"
        return f"Type error: {err}"
    if isinstance(err, RuntimeError):
        if location:
            return f"Runtime error at {location}: {err}"
        return f"Runtime error: {err}"
    if location:
        return f"Error at {location}: {err}"
    return f"Error: {err}"
