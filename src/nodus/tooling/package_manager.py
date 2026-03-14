"""Minimal local-first package management for Nodus."""

import os

from nodus.runtime.project import ProjectConfig, create_project, load_project, read_lockfile, install_dependencies


def ensure_project(root: str) -> ProjectConfig:
    manifest_path = os.path.join(os.path.abspath(root), "nodus.toml")
    if not os.path.isfile(manifest_path):
        raise FileNotFoundError(f"Project manifest not found: {manifest_path}")
    return load_project(root)


def init_project(root: str) -> ProjectConfig:
    return create_project(root)


def install_dependencies_for_project(root: str, *, update: bool = False) -> dict[str, str]:
    project = ensure_project(root)
    resolved = install_dependencies(project, update=update)
    out: dict[str, str] = {}
    for name, dep in resolved.items():
        out[name] = dep.source
    return out


def list_dependencies(root: str) -> list[tuple[str, str]]:
    project = ensure_project(root)
    lock = read_lockfile(project.lock_path)
    out: list[tuple[str, str]] = []
    for name in sorted(project.dependencies):
        status = lock.get(name)
        status_text = status.source if status is not None else "not installed"
        out.append((name, status_text))
    return out
