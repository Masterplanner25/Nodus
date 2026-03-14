"""Structured result helpers for runner outputs."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


DEFAULT_FILENAME = "<memory>"


def normalize_filename(filename: str | None) -> str:
    return filename or DEFAULT_FILENAME


@dataclass
class Result:
    ok: bool
    stage: str
    filename: str
    stdout: str = ""
    stderr: str = ""
    result: Any = None
    errors: list[dict] = field(default_factory=list)
    diagnostics: list[dict] = field(default_factory=list)
    error: dict | None = None
    extras: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        payload = {
            "ok": bool(self.ok),
            "stage": self.stage,
            "filename": self.filename,
            "stdout": self.stdout,
            "stderr": self.stderr,
            "result": self.result,
            "errors": list(self.errors),
            "diagnostics": list(self.diagnostics),
            "error": self.error,
        }
        if self.extras:
            payload.update(self.extras)
        return payload

    @classmethod
    def success(
        cls,
        *,
        stage: str,
        filename: str | None = None,
        stdout: str = "",
        stderr: str = "",
        result: Any = None,
        diagnostics: list[dict] | None = None,
        extras: dict[str, Any] | None = None,
    ) -> "Result":
        return cls(
            ok=True,
            stage=stage,
            filename=normalize_filename(filename),
            stdout=stdout,
            stderr=stderr,
            result=result,
            errors=[],
            diagnostics=list(diagnostics or []),
            error=None,
            extras=dict(extras or {}),
        )

    @classmethod
    def failure(
        cls,
        *,
        stage: str,
        filename: str | None = None,
        stdout: str = "",
        stderr: str = "",
        result: Any = None,
        errors: list[dict] | None = None,
        diagnostics: list[dict] | None = None,
        error: dict | None = None,
        extras: dict[str, Any] | None = None,
    ) -> "Result":
        return cls(
            ok=False,
            stage=stage,
            filename=normalize_filename(filename),
            stdout=stdout,
            stderr=stderr,
            result=result,
            errors=list(errors or []),
            diagnostics=list(diagnostics or []),
            error=error,
            extras=dict(extras or {}),
        )
