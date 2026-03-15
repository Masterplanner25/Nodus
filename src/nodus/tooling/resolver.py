"""Dependency graph resolution for Nodus tooling."""

from __future__ import annotations

import os
import shutil
from dataclasses import dataclass
from pathlib import Path

from nodus.tooling.project import DependencySpec, LockedPackage, ProjectConfig, load_project, read_lockfile
from nodus.tooling.registry import Registry, RegistryPackage
from nodus.tooling.semver import Version, VersionRange


@dataclass(frozen=True)
class ResolvedPackage:
    name: str
    version: str
    source: str
    path: str
    source_path: str | None
    dependencies: tuple[str, ...]


@dataclass
class ResolutionResult:
    project: ProjectConfig
    packages: dict[str, ResolvedPackage]
    graph: dict[str, tuple[str, ...]]
    install_order: list[str]


def resolve_project_dependencies(
    project: ProjectConfig,
    *,
    update: bool = False,
    registry: Registry | None = None,
    registry_client=None,  # RegistryClient | None
) -> ResolutionResult:
    registry = registry or Registry.from_project_root(project.root)
    locked = {} if update else read_lockfile(project.lock_path)
    packages: dict[str, ResolvedPackage] = {}
    graph: dict[str, tuple[str, ...]] = {}
    visiting: list[str] = []
    install_order: list[str] = []

    # Staging dir for downloaded registry packages; cleaned and recreated each run
    staging_dir: str | None = None
    if registry_client is not None:
        staging_dir = os.path.join(project.nodus_dir, "_staging")
        if os.path.isdir(staging_dir):
            shutil.rmtree(staging_dir)
        os.makedirs(staging_dir, exist_ok=True)

    def resolve_spec(owner_root: str, spec: DependencySpec) -> ResolvedPackage:
        if spec.name in packages:
            package = packages[spec.name]
            _validate_locked_or_resolved(spec, package.version)
            return package

        if spec.name in visiting:
            cycle = " -> ".join(visiting + [spec.name])
            raise ValueError(f"Cyclic dependency detected: {cycle}")

        visiting.append(spec.name)
        try:
            package = _resolve_single_dependency(
                owner_root, spec, locked, registry,
                registry_client=registry_client,
                staging_dir=staging_dir,
            )
            dependencies = _load_dependency_specs(package.path)
            child_names: list[str] = []
            for dep_spec in dependencies.values():
                child = resolve_spec(package.path, dep_spec)
                child_names.append(child.name)
            resolved = ResolvedPackage(
                name=package.name,
                version=package.version,
                source=package.source,
                path=package.path,
                source_path=package.source_path,
                dependencies=tuple(sorted(child_names)),
            )
            packages[resolved.name] = resolved
            graph[resolved.name] = resolved.dependencies
            install_order.append(resolved.name)
            return resolved
        finally:
            visiting.pop()

    for spec in project.dependencies.values():
        resolve_spec(project.root, spec)

    return ResolutionResult(
        project=project,
        packages=packages,
        graph=graph,
        install_order=install_order,
    )


def resolve_locked_packages(project: ProjectConfig) -> dict[str, LockedPackage]:
    return read_lockfile(project.lock_path)


def _resolve_single_dependency(
    owner_root: str,
    spec: DependencySpec,
    locked: dict[str, LockedPackage],
    registry: Registry,
    *,
    registry_client=None,  # RegistryClient | None
    staging_dir: str | None = None,
) -> ResolvedPackage:
    if spec.kind == "path":
        path = _resolve_path(owner_root, spec.value)
        dependency_project = load_project(path)
        return ResolvedPackage(
            name=spec.name,
            version=dependency_project.version,
            source="path",
            path=dependency_project.root,
            source_path=_normalize_source_value(owner_root, path),
            dependencies=tuple(),
        )

    if spec.kind == "version" and registry_client is not None and staging_dir is not None:
        locked_package = locked.get(spec.name)
        if locked_package is not None and locked_package.source == "registry":
            # Re-resolve against the locked version's exact constraint
            constraint = locked_package.version
        else:
            constraint = spec.value
        version_entry = registry_client.resolve_version(spec.name, constraint)
        registry_client.install_package(spec.name, version_entry, Path(staging_dir))
        pkg_path = os.path.join(staging_dir, spec.name)
        return ResolvedPackage(
            name=spec.name,
            version=version_entry["version"],
            source="registry",
            path=pkg_path,
            source_path=None,
            dependencies=tuple(),
        )

    locked_package = locked.get(spec.name)
    if locked_package is not None:
        _validate_locked_or_resolved(spec, locked_package.version)

    selected = _select_registry_package(spec, registry, locked_package)
    return ResolvedPackage(
        name=selected.name,
        version=selected.version,
        source=selected.source,
        path=selected.path,
        source_path=None,
        dependencies=tuple(),
    )


def _load_dependency_specs(path: str) -> dict[str, DependencySpec]:
    manifest_path = os.path.join(path, "nodus.toml")
    if not os.path.isfile(manifest_path):
        return {}
    return load_project(path).dependencies


def _select_registry_package(
    spec: DependencySpec,
    registry: Registry,
    locked_package: LockedPackage | None,
) -> RegistryPackage:
    candidates = registry.available_versions(spec.name)
    if not candidates:
        raise ValueError(f"Dependency {spec.name} is not available in the local registry")

    if locked_package is not None:
        locked = registry.get(spec.name, locked_package.version)
        if locked is None:
            raise ValueError(f"Locked dependency {spec.name}@{locked_package.version} is unavailable")
        _validate_locked_or_resolved(spec, locked.version)
        return locked

    matching = [candidate for candidate in candidates if _matches_requirement(spec.value, candidate.version)]
    if not matching:
        raise ValueError(f"No registry version for {spec.name} satisfies {spec.value}")
    matching.sort(key=lambda item: Version.parse(item.version), reverse=True)
    return matching[0]


def _resolve_path(owner_root: str, raw_path: str) -> str:
    if os.path.isabs(raw_path):
        return os.path.abspath(raw_path)
    return os.path.abspath(os.path.join(owner_root, raw_path))


def _normalize_source_value(owner_root: str, resolved_path: str) -> str:
    relative = os.path.relpath(resolved_path, owner_root)
    return relative.replace("\\", "/")


def _matches_requirement(requirement: str, version: str) -> bool:
    try:
        return VersionRange.parse(requirement).matches(Version.parse(version))
    except ValueError:
        return version == requirement


def _validate_locked_or_resolved(spec: DependencySpec, version: str) -> None:
    if spec.kind != "version":
        return
    if not _matches_requirement(spec.value, version):
        raise ValueError(f"Resolved version {version} does not satisfy {spec.name} {spec.value}")
