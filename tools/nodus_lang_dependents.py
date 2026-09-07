"""The one list of companions that declare a nodus-lang dependency (#810).

Gate 10a and Stage 6's range check each kept their own. They drifted: Gate 10a
had six names, Stage 6 had seven, and the true set is **eight**. So a published
first-party dependent could have neither its suite run before an upload nor its
range checked after one, which is exactly what happened to `nodus-a2a-wire` —
absent from both — and to `nodus-workflow-ai`, absent from the first.

The manifest is `nodus_lang_dependents.json`. This module is the only reader, so
neither gate keeps a copy; `tests/test_dependent_registry.py` asserts on their
source that they do not.

**The criterion is `declares`, not `imports`.** A package that generates Nodus
source or shells out to the CLI can be broken by a nodus-lang change without
importing anything — the syntax it emits stops parsing, or a flag it passes is
refused (#791's shape, shipped in 5.12.0). `nodus-workflow-ai` is exactly that
package, which is why the narrower criterion excluded it *correctly* and still
left a hole.
"""

from __future__ import annotations

import json
import os

MANIFEST = os.path.join(os.path.dirname(os.path.abspath(__file__)), "nodus_lang_dependents.json")


class DependentRegistryError(RuntimeError):
    """The manifest is missing or malformed.

    Raised rather than defaulted, for the reason the flake and shape manifests
    give: a check may not pass by being unable to run.
    """


def load() -> dict[str, dict]:
    """Every declared dependent: name -> {path, published, note?}."""
    try:
        with open(MANIFEST, encoding="utf-8") as handle:
            data = json.load(handle)
    except OSError as exc:
        raise DependentRegistryError(f"cannot read {MANIFEST}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise DependentRegistryError(f"{MANIFEST} is not valid JSON: {exc}") from exc

    entries = data.get("dependents")
    if not isinstance(entries, dict) or not entries:
        raise DependentRegistryError(f"{MANIFEST} has no 'dependents' object")

    for name, entry in entries.items():
        if not isinstance(entry, dict) or not isinstance(entry.get("path"), str):
            raise DependentRegistryError(f"{MANIFEST}: '{name}' has no string 'path'")
        if not isinstance(entry.get("published"), bool):
            raise DependentRegistryError(f"{MANIFEST}: '{name}' has no boolean 'published'")
    return entries


def checkouts() -> dict[str, str]:
    """name -> local checkout path, for the gate that runs their suites."""
    return {name: entry["path"] for name, entry in load().items()}


def published_names() -> list[str]:
    """Names that resolve on PyPI, for the gate that resolves their ranges."""
    return sorted(name for name, entry in load().items() if entry["published"])


def unregistered_nearby() -> list[tuple[str, str]]:
    """Checkouts beside the registered ones that declare nodus-lang and are absent.

    This is the check that would have found `nodus-a2a-wire`. The registry is a
    hand-maintained list, and the failure mode is not an entry going *wrong* —
    it is one never being added, which no amount of reading the list reveals.

    Scans the parent directory of each registered checkout, so it follows the
    registry rather than hardcoding `C:\\dev` and `C:\\codev`; adding a dependent
    in a third root extends the sweep by construction.

    Returns [(name, path)] for anything found. An empty list also means "found
    nothing", which is why the caller reports how many roots it could actually
    read — a sweep over directories that do not exist is not evidence.
    """
    entries = load()
    known = {name.lower() for name in entries}
    known_paths = {_key(entry["path"]) for entry in entries.values()}
    ignored = {_key(path) for path in _ignored()}
    # This repo declares nodus-lang because it *is* nodus-lang.
    ignored.add(_key(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
    roots = {os.path.dirname(os.path.normpath(entry["path"])) for entry in entries.values()}

    missing: list[tuple[str, str]] = []
    for root in sorted(roots):
        if not os.path.isdir(root):
            continue
        for child in sorted(os.listdir(root)):
            path = os.path.join(root, child)
            if _key(path) in known_paths or _key(path) in ignored:
                continue
            manifest = os.path.join(path, "pyproject.toml")
            if not os.path.isfile(manifest):
                continue
            try:
                with open(manifest, encoding="utf-8") as handle:
                    text = handle.read()
            except (OSError, UnicodeDecodeError):
                continue
            if "nodus-lang" not in text:
                continue
            name = _distribution_name(text) or child
            if name.lower() in known:
                continue
            missing.append((name, path))
    return missing


def readable_roots() -> tuple[int, int]:
    """(roots that exist, roots the registry names) — so a vacuous sweep is visible."""
    roots = {os.path.dirname(os.path.normpath(entry["path"])) for entry in load().values()}
    return sum(1 for root in roots if os.path.isdir(root)), len(roots)


def _ignored() -> dict[str, str]:
    """Paths that declare nodus-lang and are deliberately not first-party.

    Each carries a reason in the manifest, the way `shape_manifest.json` and
    `dependent_flakes.json` require one. An exclusion with no stated reason is
    indistinguishable from an oversight, which is the whole subject of #810.
    """
    with open(MANIFEST, encoding="utf-8") as handle:
        data = json.load(handle)
    entries = data.get("ignored", {})
    if not isinstance(entries, dict):
        raise DependentRegistryError(f"{MANIFEST}: 'ignored' must be an object")
    for path, reason in entries.items():
        if not isinstance(reason, str) or not reason.strip():
            raise DependentRegistryError(f"{MANIFEST}: ignored '{path}' has no reason")
    return entries


def _key(path: str) -> str:
    return os.path.normcase(os.path.normpath(os.path.abspath(path)))


def _distribution_name(pyproject_text: str) -> str | None:
    for line in pyproject_text.split("\n"):
        stripped = line.strip()
        if stripped.startswith("name") and "=" in stripped:
            value = stripped.split("=", 1)[1].strip()
            if len(value) >= 2 and value[0] in "\"'" and value[-1] == value[0]:
                return value[1:-1]
    return None
