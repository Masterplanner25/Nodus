"""Project manifest and lockfile helpers for Nodus tooling."""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass


MANIFEST_NAME = "nodus.toml"
LOCKFILE_NAME = "nodus.lock"
NODUS_DIRNAME = ".nodus"
MODULES_DIRNAME = "modules"
SOURCE_DIRNAME = "src"
ENTRYPOINT_NAME = "main.nd"
CACHE_DIRNAME = "cache"

#: Every table `nodus.toml` may contain. A manifest that declares anything else
#: is refused rather than partly read: "accepted and ignored" is the defect class
#: this repo keeps hitting, and a manifest is where it is least visible -- it
#: looks plausible, so nobody re-reads it (#490).
MANIFEST_SECTIONS = ("package", "dependencies")

#: Keys `[package]` may contain.
PACKAGE_KEYS = ("name", "version", "registry_url", "entry")

#: Top-level keys tolerated for the pre-`[package]` manifest form.
LEGACY_TOP_LEVEL_KEYS = ("name", "version")

#: Mistakes worth naming rather than just rejecting. `[project]` is one
#: character from `[package]` and reads as obviously correct, which is exactly
#: why it went unnoticed in a first-party project for months.
SECTION_HINTS = {
    "project": "did you mean [package]?",
    "workflows": "Nodus has no [workflows] table; point `entry` at a file instead",
    "runtime": "Nodus has no [runtime] table",
    "tool": "did you mean [package]?",
}


@dataclass(frozen=True)
class DependencySpec:
    name: str
    kind: str
    value: str


@dataclass(frozen=True)
class LockedPackage:
    name: str
    version: str
    source: str
    hash: str
    path: str | None = None


@dataclass
class ProjectConfig:
    root: str
    manifest_path: str
    lock_path: str
    nodus_dir: str
    modules_dir: str
    name: str
    version: str
    dependencies: dict[str, DependencySpec]
    registry_url: str | None = None
    #: `entry = "..."` from the manifest, relative to the project root. `None`
    #: falls back to the `src/main.nd` convention. Two of the three real
    #: manifests on record declared this key before it existed, and it was
    #: silently ignored along with everything else (#490).
    entry: str | None = None


def find_project_root(start_dir: str) -> str | None:
    current = os.path.abspath(start_dir)
    while True:
        if os.path.isfile(os.path.join(current, MANIFEST_NAME)):
            return current
        parent = os.path.dirname(current)
        if parent == current:
            return None
        current = parent


def load_manifest(path: str) -> dict:
    with open(path, "rb") as handle:
        return tomllib.load(handle)


class ManifestError(ValueError):
    """A manifest declares something Nodus does not read."""


def _did_you_mean(name: str, known) -> str:
    """A hint only when one is actually close, rather than always guessing."""
    import difflib

    close = difflib.get_close_matches(name, list(known), n=1, cutoff=0.7)
    return f"did you mean {close[0]!r}?" if close else ""


def validate_manifest(data: dict, *, path: str = MANIFEST_NAME) -> None:
    """Refuse a manifest that declares anything Nodus will not read.

    The rule this implements is recorded in `CORPUS_SYNTHESIS.md` §6: a
    declaration the runtime accepts must bind, or be refused at the point of
    declaration. "Accepted and ignored" is not a permitted third state.

    A manifest is the worst place for that third state, because it *looks* like
    it worked. A first-party project declared `[project]`, `entry`, `[runtime]`
    and
    `[workflows]` -- none of them read -- and nothing said so for months (#490).
    """
    problems: list[str] = []

    for key in data:
        name = str(key)
        if name in MANIFEST_SECTIONS:
            continue
        if not isinstance(data[key], dict) and name in LEGACY_TOP_LEVEL_KEYS:
            continue
        hint = SECTION_HINTS.get(name) or _did_you_mean(name, MANIFEST_SECTIONS)
        is_table = isinstance(data[key], dict)
        kind = "table" if is_table else "key"
        label = f"[{name}]" if is_table else repr(name)
        problems.append(
            f"  unknown {kind} {label}" + (f" -- {hint}" if hint else "")
        )

    package = data.get("package")
    if isinstance(package, dict):
        for key in package:
            name = str(key)
            if name in PACKAGE_KEYS:
                continue
            hint = _did_you_mean(name, PACKAGE_KEYS)
            problems.append(
                f"  unknown key {name!r} in [package]" + (f" -- {hint}" if hint else "")
            )

    if problems:
        supported = ", ".join(f"[{section}]" for section in MANIFEST_SECTIONS)
        raise ManifestError(
            f"{path} declares things Nodus does not read:\n"
            + "\n".join(problems)
            + f"\n\nnodus.toml supports {supported}, and [package] keys: "
            + ", ".join(PACKAGE_KEYS)
            + "."
        )


def parse_package(data: dict, *, root: str) -> tuple[str, str, str | None, str | None]:
    raw_package = data.get("package")
    if raw_package is not None:
        if not isinstance(raw_package, dict):
            raise ValueError("Manifest [package] must be a table")
        name = str(raw_package.get("name", os.path.basename(root)))
        version = str(raw_package.get("version", "0.1.0"))
        registry_url = str(raw_package.get("registry_url", "") or "") or None
        entry = str(raw_package.get("entry", "") or "") or None
        return name, version, registry_url, entry
    return (
        str(data.get("name", os.path.basename(root))),
        str(data.get("version", "0.1.0")),
        None,
        None,
    )


def parse_dependencies(raw: dict) -> dict[str, DependencySpec]:
    if not isinstance(raw, dict):
        raise ValueError("Manifest [dependencies] must be a table")
    dependencies: dict[str, DependencySpec] = {}
    for raw_name, raw_value in raw.items():
        name = str(raw_name)
        if isinstance(raw_value, str):
            dependencies[name] = DependencySpec(name=name, kind="version", value=raw_value)
            continue
        if isinstance(raw_value, dict) and "path" in raw_value:
            dependencies[name] = DependencySpec(name=name, kind="path", value=str(raw_value["path"]))
            continue
        raise ValueError(f"Unsupported dependency spec for {name}")
    return dependencies


def write_project_manifest(
    path: str,
    *,
    name: str,
    version: str,
    dependencies: dict[str, DependencySpec],
    registry_url: str | None = None,
    entry: str | None = None,
) -> None:
    lines = [
        "[package]",
        f'name = "{_escape(name)}"',
        f'version = "{_escape(version)}"',
    ]
    if registry_url:
        lines.append(f'registry_url = "{_escape(registry_url)}"')
    if entry:
        lines.append(f'entry = "{_escape(entry)}"')
    lines += [
        "",
        "[dependencies]",
    ]
    for dep_name in sorted(dependencies):
        spec = dependencies[dep_name]
        if spec.kind == "version":
            lines.append(f'{dep_name} = "{_escape(spec.value)}"')
            continue
        if spec.kind == "path":
            lines.append(f'{dep_name} = {{ path = "{_escape(spec.value)}" }}')
            continue
        raise ValueError(f"Unsupported dependency spec for {dep_name}")
    text = "\n".join(lines) + "\n"
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(text)


def load_project(root: str) -> ProjectConfig:
    root = os.path.abspath(root)
    manifest_path = os.path.join(root, MANIFEST_NAME)
    data = load_manifest(manifest_path)
    validate_manifest(data, path=manifest_path)
    name, version, registry_url, entry = parse_package(data, root=root)
    dependencies = parse_dependencies(data.get("dependencies", {}))
    nodus_dir = os.path.join(root, NODUS_DIRNAME)
    return ProjectConfig(
        root=root,
        manifest_path=manifest_path,
        lock_path=os.path.join(root, LOCKFILE_NAME),
        nodus_dir=nodus_dir,
        modules_dir=os.path.join(nodus_dir, MODULES_DIRNAME),
        name=name,
        version=version,
        dependencies=dependencies,
        registry_url=registry_url,
        entry=entry,
    )


def load_project_from(start_dir: str) -> ProjectConfig | None:
    root = find_project_root(start_dir)
    if root is None:
        return None
    return load_project(root)


def create_project(root: str, name: str | None = None, version: str = "0.1.0") -> ProjectConfig:
    root = os.path.abspath(root)
    os.makedirs(os.path.join(root, NODUS_DIRNAME, MODULES_DIRNAME), exist_ok=True)
    os.makedirs(os.path.join(root, NODUS_DIRNAME, CACHE_DIRNAME), exist_ok=True)
    src_dir = os.path.join(root, SOURCE_DIRNAME)
    os.makedirs(src_dir, exist_ok=True)
    manifest_path = os.path.join(root, MANIFEST_NAME)
    if not os.path.exists(manifest_path):
        project_name = name or os.path.basename(root)
        write_project_manifest(
            manifest_path,
            name=project_name,
            version=version,
            dependencies={},
        )
    entry_path = os.path.join(src_dir, ENTRYPOINT_NAME)
    if not os.path.exists(entry_path):
        with open(entry_path, "w", encoding="utf-8") as handle:
            handle.write('print("hello from nodus")\n')
    return load_project(root)


def project_entry_path(project: ProjectConfig) -> str:
    """Where `nodus run` starts, honouring a declared `entry`.

    `entry` resolves relative to the project root and must stay inside it. A
    manifest is data, not code -- an `entry = "../../elsewhere.nd"` that ran
    would let a checked-out project reach outside its own tree.
    """
    if project.entry is None:
        return os.path.join(project.root, SOURCE_DIRNAME, ENTRYPOINT_NAME)
    root = os.path.abspath(project.root)
    resolved = os.path.abspath(os.path.join(root, project.entry))
    if os.path.commonpath([root, resolved]) != root:
        raise ManifestError(
            f"{MANIFEST_NAME} entry {project.entry!r} resolves outside the "
            f"project root ({root}); entry must name a file inside the project"
        )
    return resolved


def read_lockfile(path: str) -> dict[str, LockedPackage]:
    if not os.path.isfile(path):
        return {}
    data = load_manifest(path)
    packages = data.get("package", [])
    if not isinstance(packages, list):
        raise ValueError("Lockfile [[package]] entries must be an array of tables")
    locked: dict[str, LockedPackage] = {}
    for entry in packages:
        if not isinstance(entry, dict):
            continue
        name = str(entry.get("name", "")).strip()
        if not name:
            continue
        locked[name] = LockedPackage(
            name=name,
            version=str(entry.get("version", "0.0.0")),
            source=str(entry.get("source", "")),
            hash=str(entry.get("hash", "")),
            path=str(entry["path"]) if "path" in entry else None,
        )
    return locked


def write_lockfile(path: str, packages: dict[str, LockedPackage]) -> None:
    lines: list[str] = []
    for name in sorted(packages):
        package = packages[name]
        lines.append("[[package]]")
        lines.append(f'name = "{_escape(package.name)}"')
        lines.append(f'version = "{_escape(package.version)}"')
        lines.append(f'source = "{_escape(package.source)}"')
        if package.path is not None:
            lines.append(f'path = "{_escape(package.path)}"')
        lines.append(f'hash = "{_escape(package.hash)}"')
        lines.append("")
    text = "\n".join(lines).rstrip()
    if text:
        text += "\n"
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(text)


def dependency_source_path(project: ProjectConfig, dependency: str) -> str:
    return os.path.join(project.modules_dir, dependency)


def _escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')
