"""Diagnostics and error formatting for Nodus."""


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
    ):
        super().__init__(message)
        self.kind = kind
        self.line = line
        self.col = col
        self.path = path
        self.stack = stack or []


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
