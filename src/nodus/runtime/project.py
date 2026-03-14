"""Compatibility wrappers for tooling-side project helpers."""

from nodus.tooling.installer import install_project
from nodus.tooling.project import (
    DependencySpec,
    LockedPackage as ResolvedDependency,
    ProjectConfig,
    create_project,
    find_project_root,
    load_manifest,
    load_project,
    load_project_from,
    parse_dependencies,
    read_lockfile,
    write_lockfile,
)
from nodus.tooling.registry import Registry
from nodus.tooling.resolver import ResolutionResult, resolve_project_dependencies


def resolve_dependencies(project: ProjectConfig, *, update: bool = False) -> ResolutionResult:
    return resolve_project_dependencies(project, update=update, registry=Registry.from_project_root(project.root))


def install_dependencies(project: ProjectConfig, *, update: bool = False) -> dict[str, ResolvedDependency]:
    resolution = resolve_dependencies(project, update=update)
    return install_project(project, resolution)
