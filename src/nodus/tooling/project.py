"""Project manifest and lockfile helpers for Nodus tooling."""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass


MANIFEST_NAME = "nodus.toml"
LOCKFILE_NAME = "nodus.lock"
NODUS_DIRNAME = ".nodus"
MODULES_DIRNAME = "modules"


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


def load_project(root: str) -> ProjectConfig:
    root = os.path.abspath(root)
    manifest_path = os.path.join(root, MANIFEST_NAME)
    data = load_manifest(manifest_path)
    dependencies = parse_dependencies(data.get("dependencies", {}))
    nodus_dir = os.path.join(root, NODUS_DIRNAME)
    return ProjectConfig(
        root=root,
        manifest_path=manifest_path,
        lock_path=os.path.join(root, LOCKFILE_NAME),
        nodus_dir=nodus_dir,
        modules_dir=os.path.join(nodus_dir, MODULES_DIRNAME),
        name=str(data.get("name", os.path.basename(root))),
        version=str(data.get("version", "0.1.0")),
        dependencies=dependencies,
    )


def load_project_from(start_dir: str) -> ProjectConfig | None:
    root = find_project_root(start_dir)
    if root is None:
        return None
    return load_project(root)


def create_project(root: str, name: str | None = None, version: str = "0.1.0") -> ProjectConfig:
    root = os.path.abspath(root)
    os.makedirs(os.path.join(root, NODUS_DIRNAME, MODULES_DIRNAME), exist_ok=True)
    manifest_path = os.path.join(root, MANIFEST_NAME)
    if not os.path.exists(manifest_path):
        project_name = name or os.path.basename(root)
        with open(manifest_path, "w", encoding="utf-8") as handle:
            handle.write(f'name = "{project_name}"\n')
            handle.write(f'version = "{version}"\n\n')
            handle.write("[dependencies]\n")
    return load_project(root)


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
