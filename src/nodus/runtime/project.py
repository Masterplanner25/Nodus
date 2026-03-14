"""Project manifest and dependency resolution for Nodus."""

from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import tomllib
from dataclasses import dataclass

from nodus.runtime.semver import Version, VersionRange


MANIFEST_NAME = "nodus.toml"
LOCKFILE_NAME = "nodus.lock"
DEPS_DIRNAME = "deps"


@dataclass(frozen=True)
class DependencySpec:
    name: str
    kind: str
    value: str


@dataclass(frozen=True)
class ResolvedDependency:
    name: str
    version: str
    source: str
    path: str | None
    hash: str


@dataclass
class ProjectConfig:
    root: str
    manifest_path: str
    lock_path: str
    deps_dir: str
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
    with open(path, "rb") as f:
        return tomllib.load(f)


def parse_dependencies(raw: dict) -> dict[str, DependencySpec]:
    if not isinstance(raw, dict):
        raise ValueError("Manifest [dependencies] must be a table")
    out: dict[str, DependencySpec] = {}
    for name, value in raw.items():
        if isinstance(value, str):
            if value.startswith("git+"):
                out[str(name)] = DependencySpec(str(name), "git", value[4:])
            else:
                out[str(name)] = DependencySpec(str(name), "version", value)
            continue
        if isinstance(value, dict):
            if "path" in value:
                out[str(name)] = DependencySpec(str(name), "path", str(value["path"]))
                continue
            if "git" in value:
                out[str(name)] = DependencySpec(str(name), "git", str(value["git"]))
                continue
            if "version" in value:
                out[str(name)] = DependencySpec(str(name), "version", str(value["version"]))
                continue
            raise ValueError(f"Unsupported dependency spec for {name}")
        raise ValueError(f"Unsupported dependency spec for {name}")
    return out


def load_project(root: str) -> ProjectConfig:
    root = os.path.abspath(root)
    manifest_path = os.path.join(root, MANIFEST_NAME)
    data = load_manifest(manifest_path)
    deps = parse_dependencies(data.get("dependencies", {}))
    return ProjectConfig(
        root=root,
        manifest_path=manifest_path,
        lock_path=os.path.join(root, LOCKFILE_NAME),
        deps_dir=os.path.join(root, DEPS_DIRNAME),
        name=str(data.get("name", os.path.basename(root))),
        version=str(data.get("version", "0.1.0")),
        dependencies=deps,
    )


def load_project_from(start_dir: str) -> ProjectConfig | None:
    root = find_project_root(start_dir)
    if root is None:
        return None
    return load_project(root)


def create_project(root: str, name: str | None = None, version: str = "0.1.0") -> ProjectConfig:
    root = os.path.abspath(root)
    os.makedirs(root, exist_ok=True)
    os.makedirs(os.path.join(root, DEPS_DIRNAME), exist_ok=True)
    manifest_path = os.path.join(root, MANIFEST_NAME)
    if not os.path.exists(manifest_path):
        project_name = name or os.path.basename(root)
        with open(manifest_path, "w", encoding="utf-8") as f:
            f.write(f'name = "{project_name}"\n')
            f.write(f'version = "{version}"\n\n')
            f.write("[dependencies]\n")
    return load_project(root)


def read_lockfile(path: str) -> dict[str, ResolvedDependency]:
    if not os.path.isfile(path):
        return {}
    data = load_manifest(path)
    deps = data.get("dependencies", {})
    if not isinstance(deps, dict):
        return {}
    resolved: dict[str, ResolvedDependency] = {}
    for name, entry in deps.items():
        if not isinstance(entry, dict):
            continue
        resolved[str(name)] = ResolvedDependency(
            name=str(name),
            version=str(entry.get("version", "0.0.0")),
            source=str(entry.get("source", "")),
            path=str(entry.get("path")) if entry.get("path") else None,
            hash=str(entry.get("hash", "")),
        )
    return resolved


def write_lockfile(path: str, resolved: dict[str, ResolvedDependency]) -> None:
    lines: list[str] = []
    lines.append("[dependencies]")
    for name in sorted(resolved):
        dep = resolved[name]
        lines.append(f'[{_escape_key("dependencies", name)}]')
        lines.append(f'version = "{_escape(dep.version)}"')
        lines.append(f'source = "{_escape(dep.source)}"')
        if dep.path is not None:
            lines.append(f'path = "{_escape(dep.path)}"')
        lines.append(f'hash = "{_escape(dep.hash)}"')
        lines.append("")
    text = "\n".join(lines).rstrip() + "\n"
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


def resolve_dependencies(project: ProjectConfig, *, update: bool = False) -> dict[str, ResolvedDependency]:
    resolved: dict[str, ResolvedDependency] = {}
    lock = {} if update else read_lockfile(project.lock_path)
    for name, spec in project.dependencies.items():
        if spec.kind == "version":
            locked = lock.get(name)
            if locked is None:
                resolved[name] = ResolvedDependency(
                    name=name,
                    version=spec.value,
                    source=f"registry:{spec.value}",
                    path=None,
                    hash="",
                )
            else:
                _validate_version(spec.value, locked.version)
                resolved[name] = locked
            continue
        resolved[name] = _resolve_path_or_git(project, spec)
    return resolved


def install_dependencies(project: ProjectConfig, *, update: bool = False) -> dict[str, ResolvedDependency]:
    resolved: dict[str, ResolvedDependency] = {}
    lock = {} if update else read_lockfile(project.lock_path)
    for name, spec in project.dependencies.items():
        if spec.kind == "version":
            locked = lock.get(name)
            if locked is None:
                raise ValueError(f"Registry dependencies are not supported yet: {name}")
            _validate_version(spec.value, locked.version)
            resolved[name] = locked
            continue
        resolved[name] = _install_dependency(project, spec)
    write_lockfile(project.lock_path, resolved)
    return resolved


def _resolve_path_or_git(project: ProjectConfig, spec: DependencySpec) -> ResolvedDependency:
    if spec.kind == "path":
        path = _resolve_path(project, spec.value)
        version = _read_manifest_version(path)
        return ResolvedDependency(
            name=spec.name,
            version=version,
            source=f"path:{spec.value}",
            path=path,
            hash=_hash_path(path),
        )
    if spec.kind == "git":
        path = os.path.join(project.deps_dir, spec.name)
        return ResolvedDependency(
            name=spec.name,
            version="0.0.0",
            source=f"git:{spec.value}",
            path=path,
            hash="",
        )
    raise ValueError(f"Unsupported dependency type: {spec.kind}")


def _install_dependency(project: ProjectConfig, spec: DependencySpec) -> ResolvedDependency:
    if spec.kind == "path":
        source_path = _resolve_path(project, spec.value)
        dest = os.path.join(project.deps_dir, spec.name)
        os.makedirs(project.deps_dir, exist_ok=True)
        if os.path.isdir(dest):
            shutil.rmtree(dest)
        shutil.copytree(source_path, dest)
        version = _read_manifest_version(dest)
        return ResolvedDependency(
            name=spec.name,
            version=version,
            source=f"path:{spec.value}",
            path=dest,
            hash=_hash_path(dest),
        )
    if spec.kind == "git":
        dest = os.path.join(project.deps_dir, spec.name)
        os.makedirs(project.deps_dir, exist_ok=True)
        if os.path.isdir(dest):
            shutil.rmtree(dest)
        _run_git(["clone", spec.value, dest])
        commit = _run_git(["-C", dest, "rev-parse", "HEAD"])
        return ResolvedDependency(
            name=spec.name,
            version="0.0.0",
            source=f"git:{spec.value}",
            path=dest,
            hash=commit,
        )
    raise ValueError(f"Unsupported dependency type: {spec.kind}")


def _resolve_path(project: ProjectConfig, path_value: str) -> str:
    if os.path.isabs(path_value):
        return os.path.abspath(path_value)
    return os.path.abspath(os.path.join(project.root, path_value))


def _read_manifest_version(path: str) -> str:
    manifest = os.path.join(path, MANIFEST_NAME)
    if not os.path.isfile(manifest):
        return "0.0.0"
    data = load_manifest(manifest)
    return str(data.get("version", "0.0.0"))


def _hash_path(path: str) -> str:
    manifest = os.path.join(path, MANIFEST_NAME)
    if os.path.isfile(manifest):
        with open(manifest, "rb") as f:
            return hashlib.sha256(f.read()).hexdigest()
    return hashlib.sha256(path.encode("utf-8")).hexdigest()


def _run_git(args: list[str]) -> str:
    result = subprocess.run(
        ["git", *args],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def _validate_version(requirement: str, actual: str) -> None:
    try:
        range_spec = VersionRange.parse(requirement)
        value = Version.parse(actual)
        if not range_spec.matches(value):
            raise ValueError(f"Locked version {actual} does not satisfy {requirement}")
    except ValueError:
        # If parsing fails, treat as raw equality.
        if actual != requirement:
            raise ValueError(f"Locked version {actual} does not satisfy {requirement}")


def _escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace('"', '\\"')


def _escape_key(section: str, name: str) -> str:
    return f"{section}.{name}"
