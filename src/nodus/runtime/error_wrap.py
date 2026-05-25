"""Helpers for translating Python exceptions into Nodus err records."""

import json
import sys
import traceback


_JSON_REASON_MAP = [
    ("Expecting property name", "expected property name"),
    ("Expecting value", "expected a value"),
    ("Expecting ',' delimiter", "expected `,` separator"),
    ("Expecting ':' delimiter", "expected `:` after key"),
    ("Unterminated string", "unterminated string"),
    ("Invalid \\escape", "invalid escape sequence"),
    ("Extra data", "unexpected content after JSON value"),
]


def translate_json_decode_error(exc: json.JSONDecodeError) -> str:
    """Translate a JSONDecodeError into a Nodus-voice message."""
    reason = None
    for python_fragment, nodus_text in _JSON_REASON_MAP:
        if python_fragment in exc.msg:
            reason = nodus_text
            break
    line = exc.lineno
    col = exc.colno
    if reason:
        return f"invalid JSON at line {line} column {col}: {reason}"
    return f"invalid JSON at line {line} column {col}"


def print_trace(func_name: str, exc: BaseException) -> None:
    """Print a trace-errors diagnostic to stderr."""
    tb_lines = traceback.format_exception(type(exc), exc, exc.__traceback__)
    tb_text = "".join(tb_lines).rstrip()
    print(
        f"[trace-errors] in {func_name}\n"
        f"  underlying Python exception: {type(exc).__name__}\n"
        f"  {exc}\n"
        f"  Traceback:\n" + "\n".join(f"    {ln}" for ln in tb_text.splitlines()),
        file=sys.stderr,
    )
