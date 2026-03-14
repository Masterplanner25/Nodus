"""Compatibility shim for legacy package_manager imports."""

from __future__ import annotations

import os
import shutil
import subprocess

from nodus.tooling.project import ProjectConfig, create_project, load_project, read_lockfile, write_lockfile


def ensure_project(root: str) -> ProjectConfig:
    manifest_path = os.path.join(os.path.abspath(root), "nodus.toml")
    if not os.path.isfile(manifest_path):
        raise FileNotFoundError(f"Project manifest not found: {manifest_path}")
    return load_project(root)


def init_project(root: str) -> ProjectConfig:
    return create_project(root)


def git_source_from_spec(spec: str) -> str:
    if not spec.startswith("git+"):
        raise ValueError(f"Unsupported dependency source: {spec}")
    return spec[4:]


def run_git(args: list[str], cwd: str | None = None) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def install_dependency(name: str, spec: str, deps_dir: str) -> str:
    source = git_source_from_spec(spec)
    os.makedirs(deps_dir, exist_ok=True)
    dest = os.path.join(deps_dir, name)
    if os.path.isdir(dest):
        shutil.rmtree(dest)
    run_git(["clone", source, dest])
    commit = run_git(["-C", dest, "rev-parse", "HEAD"])
    return f"{spec}@{commit}"


def install_dependencies(root: str) -> dict[str, str]:
    project = ensure_project(root)
    resolved: dict[str, str] = {}
    for name, spec in project.dependencies.items():
        resolved[name] = install_dependency(name, spec, project.deps_dir)
    write_lockfile(project.lock_path, resolved)
    return resolved


def list_dependencies(root: str) -> list[tuple[str, str]]:
    project = ensure_project(root)
    lock = read_lockfile(project.lock_path)
    out: list[tuple[str, str]] = []
    for name in sorted(project.dependencies):
        status = lock.get(name, "not installed")
        out.append((name, status))
    return out


__all__ = [
    "ProjectConfig",
    "ensure_project",
    "init_project",
    "git_source_from_spec",
    "run_git",
    "install_dependency",
    "install_dependencies",
    "list_dependencies",
]
