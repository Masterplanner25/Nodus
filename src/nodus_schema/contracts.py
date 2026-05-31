"""HandlerContract — unified contract type for Nodus handler surfaces."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


VALID_EFFECTS: frozenset[str] = frozenset({
    "pure",
    "reads_state",
    "writes_state",
    "network",
    "filesystem",
    "spawns_task",
})


@dataclass
class HandlerContract:
    """Formal contract for a registered handler (tool, syscall, extension tool, etc.).

    Declares what a handler guarantees: its preconditions (input_schema),
    return shape (returns_schema), and I/O category (effects). Call validate()
    to get a list of structural errors; an empty list means the contract is valid.
    """

    name: str
    description: str
    input_schema: dict[str, Any] = field(default_factory=dict)
    returns_schema: dict[str, Any] = field(default_factory=dict)
    effects: list[str] = field(default_factory=lambda: ["pure"])
    capabilities_required: list[str] = field(default_factory=list)
    version: str = "1.0.0"
    tags: list[str] = field(default_factory=list)
    deprecated: bool = False

    def validate(self) -> list[str]:
        """Return structural validation errors. Empty list means the contract is valid."""
        errors: list[str] = []

        if not isinstance(self.name, str) or not self.name:
            errors.append("name must be a non-empty string")
        elif "." not in self.name:
            errors.append(
                f"name {self.name!r} must use dotted namespacing (e.g. 'myapp.action')"
            )

        if not isinstance(self.description, str) or not self.description.strip():
            errors.append("description must be a non-empty string")

        if not isinstance(self.effects, list) or not self.effects:
            errors.append("effects must be a non-empty list")
        else:
            for e in self.effects:
                if not isinstance(e, str):
                    errors.append(
                        f"each effect must be a string, got {type(e).__name__!r}"
                    )
                elif e not in VALID_EFFECTS:
                    allowed = ", ".join(sorted(VALID_EFFECTS))
                    errors.append(f"unknown effect {e!r} (allowed: {allowed})")
            if "pure" in self.effects and len(self.effects) > 1:
                errors.append("'pure' cannot be combined with other effects")

        return errors
