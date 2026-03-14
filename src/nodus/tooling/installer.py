"""Dependency installation for Nodus tooling."""

from __future__ import annotations

import hashlib
import os
import shutil

from nodus.tooling.project import LockedPackage, ProjectConfig, write_lockfile
from nodus.tooling.resolver import ResolutionResult


def install_resolved_dependencies(project: ProjectConfig, resolution: ResolutionResult) -> dict[str, LockedPackage]:
    os.makedirs(project.modules_dir, exist_ok=True)
    installed: dict[str, LockedPackage] = {}
    for name in resolution.install_order:
        package = resolution.packages[name]
        destination = os.path.join(project.modules_dir, name)
        if os.path.isdir(destination):
            shutil.rmtree(destination)
        shutil.copytree(package.path, destination)
        installed[name] = LockedPackage(
            name=package.name,
            version=package.version,
            source=package.source,
            hash=_hash_tree(destination),
        )
    write_lockfile(project.lock_path, installed)
    return installed


def install_project(project: ProjectConfig, resolution: ResolutionResult) -> dict[str, LockedPackage]:
    return install_resolved_dependencies(project, resolution)


def _hash_tree(path: str) -> str:
    digest = hashlib.sha256()
    for root, dirs, files in os.walk(path):
        dirs.sort()
        files.sort()
        rel_root = os.path.relpath(root, path).replace("\\", "/")
        digest.update(rel_root.encode("utf-8"))
        for filename in files:
            file_path = os.path.join(root, filename)
            rel_path = os.path.relpath(file_path, path).replace("\\", "/")
            digest.update(rel_path.encode("utf-8"))
            with open(file_path, "rb") as handle:
                digest.update(handle.read())
    return f"sha256:{digest.hexdigest()}"
