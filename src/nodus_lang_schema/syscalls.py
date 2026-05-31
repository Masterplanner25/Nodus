"""Versioned syscall contract helpers."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .validation import validate_payload


ABI_VERSIONS: frozenset[str] = frozenset({"v1"})
LATEST_STABLE_VERSION = "v1"
SYSCALL_VERSION_FALLBACK = False
SYSCALL_PREFIX = "sys."


@dataclass
class SyscallSpec:
    """Serializable ABI contract for a single syscall."""

    name: str
    version: str
    capability: str = ""
    description: str = ""
    input_schema: dict[str, Any] = field(default_factory=dict)
    output_schema: dict[str, Any] = field(default_factory=dict)
    stable: bool = True
    deprecated: bool = False
    deprecated_since: str | None = None
    replacement: str | None = None

    @property
    def full_name(self) -> str:
        return f"{SYSCALL_PREFIX}{self.version}.{self.name}"

    def deprecation_message(self) -> str | None:
        if not self.deprecated:
            return None
        parts = [f"Syscall '{self.full_name}' is deprecated"]
        if self.deprecated_since:
            parts.append(f"since {self.deprecated_since}")
        if self.replacement:
            parts.append(f"use '{self.replacement}' instead")
        return " ".join(parts) + "."

    def to_dict(self) -> dict[str, Any]:
        return {
            "full_name": self.full_name,
            "name": self.name,
            "version": self.version,
            "capability": self.capability,
            "description": self.description,
            "input_schema": self.input_schema,
            "output_schema": self.output_schema,
            "stable": self.stable,
            "deprecated": self.deprecated,
            "deprecated_since": self.deprecated_since,
            "replacement": self.replacement,
        }


def parse_syscall_name(name: str) -> tuple[str, str]:
    """Parse ``sys.{version}.{domain}.{action}`` into ``(version, action)``."""
    if not name.startswith(SYSCALL_PREFIX):
        raise ValueError(
            f"Syscall name must start with {SYSCALL_PREFIX!r}, got: {name!r}"
        )
    rest = name[len(SYSCALL_PREFIX):]
    dot_index = rest.find(".")
    if dot_index == -1:
        raise ValueError(f"Cannot parse version from {name!r}: missing version segment")
    version = rest[:dot_index]
    action = rest[dot_index + 1 :]
    if not version:
        raise ValueError(f"Empty version segment in {name!r}")
    if not action:
        raise ValueError(f"Empty action segment in {name!r}")
    return version, action


def validate_input(schema: dict[str, Any], payload: dict[str, Any]) -> list[str]:
    return validate_payload(schema, payload)


def validate_output(schema: dict[str, Any], data: dict[str, Any]) -> list[str]:
    return validate_payload(schema, data)


def resolve_version(
    requested: str,
    available: frozenset[str] | set[str],
    fallback: bool = SYSCALL_VERSION_FALLBACK,
) -> str | None:
    """Resolve a requested ABI version against the available versions."""
    available_versions = frozenset(available)
    if requested in available_versions:
        return requested
    if not fallback:
        return None
    stable_candidates = sorted(ABI_VERSIONS & available_versions, reverse=True)
    return stable_candidates[0] if stable_candidates else None
