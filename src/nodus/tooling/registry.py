"""Registry metadata access for tooling-side dependency resolution."""

from __future__ import annotations

import os
from dataclasses import dataclass, field

from nodus.tooling.project import NODUS_DIRNAME, load_manifest


REGISTRY_NAME = "registry.toml"


@dataclass(frozen=True)
class RegistryPackage:
    name: str
    version: str
    source: str
    path: str
    dependencies: dict[str, str] = field(default_factory=dict)


class Registry:
    def __init__(self, packages: dict[str, dict[str, RegistryPackage]] | None = None) -> None:
        self._packages = packages or {}

    @classmethod
    def from_project_root(cls, project_root: str) -> "Registry":
        path = os.path.join(project_root, NODUS_DIRNAME, REGISTRY_NAME)
        if not os.path.isfile(path):
            return cls()
        data = load_manifest(path)
        raw_packages = data.get("packages", {})
        packages: dict[str, dict[str, RegistryPackage]] = {}
        if not isinstance(raw_packages, dict):
            raise ValueError("Registry packages must be a table")
        for raw_name, versions in raw_packages.items():
            name = str(raw_name)
            if not isinstance(versions, dict):
                raise ValueError(f"Registry package {name} must define versions as a table")
            package_versions: dict[str, RegistryPackage] = {}
            for raw_version, entry in versions.items():
                version = str(raw_version)
                if not isinstance(entry, dict):
                    raise ValueError(f"Registry package {name}@{version} must be a table")
                raw_path = entry.get("path")
                if raw_path is None:
                    raise ValueError(f"Registry package {name}@{version} is missing path")
                dependencies = entry.get("dependencies", {})
                if not isinstance(dependencies, dict):
                    raise ValueError(f"Registry package {name}@{version} dependencies must be a table")
                package_versions[version] = RegistryPackage(
                    name=name,
                    version=version,
                    source=str(entry.get("source", "registry")),
                    path=_resolve_registry_path(path, str(raw_path)),
                    dependencies={str(dep_name): str(dep_spec) for dep_name, dep_spec in dependencies.items()},
                )
            packages[name] = package_versions
        return cls(packages)

    def available_versions(self, name: str) -> list[RegistryPackage]:
        return [self._packages[name][version] for version in sorted(self._packages.get(name, {}), key=_version_sort_key)]

    def get(self, name: str, version: str) -> RegistryPackage | None:
        return self._packages.get(name, {}).get(version)


def _resolve_registry_path(registry_path: str, raw_path: str) -> str:
    if os.path.isabs(raw_path):
        return os.path.abspath(raw_path)
    return os.path.abspath(os.path.join(os.path.dirname(registry_path), raw_path))


def _version_sort_key(text: str) -> tuple[int, int, int, str]:
    parts = text.split(".")
    numeric = []
    for part in parts[:3]:
        numeric.append(int(part) if part.isdigit() else -1)
    while len(numeric) < 3:
        numeric.append(0)
    return numeric[0], numeric[1], numeric[2], text
