"""Semantic version parsing and range matching for Nodus tooling."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, order=True)
class Version:
    major: int
    minor: int = 0
    patch: int = 0

    @classmethod
    def parse(cls, text: str) -> "Version":
        parts = text.strip().split(".")
        if not parts or any(part == "" for part in parts):
            raise ValueError(f"Invalid version: {text}")
        values: list[int] = []
        for part in parts:
            if not part.isdigit():
                raise ValueError(f"Invalid version: {text}")
            values.append(int(part))
        while len(values) < 3:
            values.append(0)
        if len(values) > 3:
            raise ValueError(f"Invalid version: {text}")
        return cls(values[0], values[1], values[2])

    def __str__(self) -> str:
        return f"{self.major}.{self.minor}.{self.patch}"


@dataclass(frozen=True)
class Comparator:
    op: str
    version: Version

    def matches(self, value: Version) -> bool:
        if self.op == "==":
            return value == self.version
        if self.op == ">":
            return value > self.version
        if self.op == ">=":
            return value >= self.version
        if self.op == "<":
            return value < self.version
        if self.op == "<=":
            return value <= self.version
        raise ValueError(f"Unsupported operator: {self.op}")


class VersionRange:
    def __init__(self, comparators: list[Comparator]):
        self.comparators = comparators

    @classmethod
    def parse(cls, text: str) -> "VersionRange":
        raw = text.strip()
        if raw.startswith("^"):
            base = Version.parse(raw[1:])
            return cls([Comparator(">=", base), Comparator("<", _caret_upper(base))])
        if raw.startswith("~"):
            base = Version.parse(raw[1:])
            return cls([Comparator(">=", base), Comparator("<", Version(base.major, base.minor + 1, 0))])

        parts = [part.strip() for part in raw.split(",") if part.strip()]
        if not parts:
            raise ValueError(f"Invalid range: {text}")
        comparators: list[Comparator] = []
        for part in parts:
            op = None
            for candidate in (">=", "<=", ">", "<", "=="):
                if part.startswith(candidate):
                    op = candidate
                    comparators.append(Comparator(candidate, Version.parse(part[len(candidate) :].strip())))
                    break
            if op is None:
                comparators.append(Comparator("==", Version.parse(part)))
        return cls(comparators)

    def matches(self, value: Version) -> bool:
        return all(comp.matches(value) for comp in self.comparators)


def _caret_upper(base: Version) -> Version:
    if base.major > 0:
        return Version(base.major + 1, 0, 0)
    if base.minor > 0:
        return Version(0, base.minor + 1, 0)
    return Version(0, 0, base.patch + 1)
