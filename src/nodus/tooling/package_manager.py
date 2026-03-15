"""Package management entrypoints for Nodus tooling."""

import os
import tempfile
from pathlib import Path

from nodus.tooling.installer import install_project
from nodus.tooling.project import (
    DependencySpec,
    ProjectConfig,
    create_project,
    load_project,
    read_lockfile,
    write_project_manifest,
)
from nodus.tooling.registry import Registry
from nodus.tooling.resolver import resolve_project_dependencies


def get_registry_token(registry_url: str | None = None, cli_token: str | None = None) -> str | None:
    """
    Resolve a registry token using three-tier priority:
    1. cli_token (from --registry-token flag) — highest priority
    2. NODUS_REGISTRY_TOKEN environment variable
    3. ~/.nodus/config.toml (UserConfig)
    Returns None if no token is found.
    """
    if cli_token:
        return cli_token
    env_token = os.environ.get("NODUS_REGISTRY_TOKEN")
    if env_token:
        return env_token
    from nodus.tooling.user_config import UserConfig
    return UserConfig().get_registry_token(registry_url)


def ensure_project(root: str) -> ProjectConfig:
    manifest_path = os.path.join(os.path.abspath(root), "nodus.toml")
    if not os.path.isfile(manifest_path):
        raise FileNotFoundError(f"Project manifest not found: {manifest_path}")
    return load_project(root)


def init_project(root: str) -> ProjectConfig:
    return create_project(root)


def install_dependencies_for_project(
    root: str,
    *,
    update: bool = False,
    registry_url: str | None = None,
    cli_token: str | None = None,
) -> dict[str, str]:
    from nodus.tooling.registry_client import RegistryClient

    project = ensure_project(root)

    # Resolve registry URL: parameter > env var > project config
    resolved_url = (
        registry_url
        or os.environ.get("NODUS_REGISTRY_URL", "").strip() or None
        or project.registry_url
    )

    if resolved_url:
        token = get_registry_token(resolved_url, cli_token=cli_token)
        registry_client: RegistryClient | None = RegistryClient(resolved_url, token=token)
        registry = None
    else:
        registry_client = None
        registry = Registry.from_project_root(project.root)

    resolution = resolve_project_dependencies(
        project,
        update=update,
        registry=registry,
        registry_client=registry_client,
    )
    resolved = install_project(project, resolution)
    out: dict[str, str] = {}
    for name, dep in resolved.items():
        out[name] = dep.path if dep.path is not None else dep.source
    return out


def list_dependencies(root: str) -> list[tuple[str, str]]:
    project = ensure_project(root)
    lock = read_lockfile(project.lock_path)
    out: list[tuple[str, str]] = []
    for name in sorted(project.dependencies):
        status = lock.get(name)
        if status is None:
            status_text = "not installed"
        elif status.source == "path" and status.path is not None:
            status_text = f"path:{status.path}"
        else:
            status_text = status.source
        out.append((name, status_text))
    return out


def add_dependency(root: str, package_name: str) -> ProjectConfig:
    project = ensure_project(root)
    registry = Registry.from_project_root(project.root)
    versions = registry.available_versions(package_name)
    if not versions:
        raise ValueError(f"Dependency {package_name} is not available in the local registry")
    latest = versions[-1]
    dependencies = dict(project.dependencies)
    dependencies[package_name] = DependencySpec(name=package_name, kind="version", value=latest.version)
    write_project_manifest(
        project.manifest_path,
        name=project.name,
        version=project.version,
        dependencies=dependencies,
    )
    install_dependencies_for_project(project.root, update=True)
    return load_project(project.root)


def remove_dependency(root: str, package_name: str) -> ProjectConfig:
    project = ensure_project(root)
    if package_name not in project.dependencies:
        raise ValueError(f"Dependency not declared: {package_name}")
    dependencies = dict(project.dependencies)
    dependencies.pop(package_name, None)
    write_project_manifest(
        project.manifest_path,
        name=project.name,
        version=project.version,
        dependencies=dependencies,
    )
    install_dependencies_for_project(project.root, update=True)
    return load_project(project.root)


def publish_package_to_registry(
    project_dir: str,
    registry_url: str | None = None,
    cli_token: str | None = None,
) -> int:
    """
    Build and publish the current project to the registry.
    Returns 0 on success, 1 on failure.
    """
    from nodus.tooling.registry_client import RegistryClient, RegistryError, create_package_archive

    project = load_project(project_dir)

    # Resolve registry URL
    resolved_url = (
        registry_url
        or os.environ.get("NODUS_REGISTRY_URL")
        or project.registry_url
    )
    if not resolved_url:
        print(
            "Error: No registry configured. Use --registry or set "
            "registry_url in nodus.toml."
        )
        return 1

    # Resolve token
    token = get_registry_token(resolved_url, cli_token=cli_token)
    if not token:
        print(
            "Error: No registry token found. Run 'nodus login' or "
            "set NODUS_REGISTRY_TOKEN."
        )
        return 1

    name = project.name
    version = project.version
    if not name or not version:
        print("Error: nodus.toml must have [package] name and version.")
        return 1

    client = RegistryClient(resolved_url, token=token)
    tmp_dir = tempfile.mkdtemp(prefix="nodus_publish_")
    archive_path = Path(tmp_dir) / f"{name}-{version}.tar.gz"
    try:
        print(f"Building archive for {name}@{version}...")
        sha256 = create_package_archive(
            Path(project_dir), archive_path, name=name, version=version
        )
        print(f"Publishing to {resolved_url}...")
        result = client.publish_package(name, version, archive_path, sha256)
        published_url = result.get("url", resolved_url)
        print(f"Published {name}@{version} → {published_url}")
        return 0
    except RegistryError as err:
        print(f"Publish failed: {err}")
        return 1
    finally:
        import shutil
        shutil.rmtree(tmp_dir, ignore_errors=True)
