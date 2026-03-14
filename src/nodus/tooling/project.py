"""Project manifest and lock-file helpers for Nodus."""

import os
import tomllib
from dataclasses import dataclass


MANIFEST_NAME = "nodus.toml"
LOCKFILE_NAME = "nodus.lock"
DEPS_DIRNAME = "deps"


@dataclass
class ProjectConfig:
    root: str
    manifest_path: str
    lock_path: str
    deps_dir: str
    name: str
    version: str
    dependencies: dict[str, str]


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


def load_project(root: str) -> ProjectConfig:
    root = os.path.abspath(root)
    manifest_path = os.path.join(root, MANIFEST_NAME)
    data = load_manifest(manifest_path)
    deps = data.get("dependencies", {})
    if not isinstance(deps, dict):
        raise ValueError("Manifest [dependencies] must be a table")
    dependencies = {str(name): str(source) for name, source in deps.items()}
    return ProjectConfig(
        root=root,
        manifest_path=manifest_path,
        lock_path=os.path.join(root, LOCKFILE_NAME),
        deps_dir=os.path.join(root, DEPS_DIRNAME),
        name=str(data.get("name", os.path.basename(root))),
        version=str(data.get("version", "0.1.0")),
        dependencies=dependencies,
    )


def load_project_from(start_dir: str) -> ProjectConfig | None:
    root = find_project_root(start_dir)
    if root is None:
        return None
    return load_project(root)


def read_lockfile(path: str) -> dict[str, str]:
    if not os.path.isfile(path):
        return {}
    data = load_manifest(path)
    return {str(name): str(value) for name, value in data.items()}


def write_lockfile(path: str, resolved: dict[str, str]) -> None:
    lines = []
    for name in sorted(resolved):
        value = resolved[name].replace("\\", "\\\\").replace('"', '\\"')
        lines.append(f'{name} = "{value}"')
    text = "\n".join(lines) + ("\n" if lines else "")
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


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
