"""HTTP registry client for Nodus package manager."""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import tarfile
import tempfile
import urllib.error
import urllib.request
import zipfile
from pathlib import Path


class RegistryError(Exception):
    """Raised for all registry-specific failures."""


class RegistryClient:
    """HTTP client for fetching and installing packages from a remote registry."""

    def __init__(self, registry_url: str) -> None:
        self.registry_url = registry_url.rstrip("/")

    def fetch_package_index(self, name: str) -> list[dict]:
        """
        GET {registry_url}/packages/{name}
        Expected JSON response:
        {
          "name": "pkg-name",
          "versions": [
            {"version": "1.0.0", "url": "https://...", "sha256": "abc..."}
          ]
        }
        Returns list of version dicts.
        Raises RegistryError on failure.
        """
        url = f"{self.registry_url}/packages/{name}"
        try:
            with urllib.request.urlopen(url, timeout=30) as response:
                data = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as err:
            if err.code == 404:
                raise RegistryError(f"Package '{name}' not found in registry at {self.registry_url}")
            raise RegistryError(f"Registry request failed: HTTP {err.code} for {url}")
        except urllib.error.URLError as err:
            raise RegistryError(f"Registry connection failed: {err.reason}")
        except (json.JSONDecodeError, KeyError) as err:
            raise RegistryError(f"Invalid registry response for '{name}': {err}")

        versions = data.get("versions")
        if not isinstance(versions, list):
            raise RegistryError(f"Registry response for '{name}' missing 'versions' list")
        return versions

    def resolve_version(self, name: str, constraint: str) -> dict:
        """
        Fetch index and pick best matching version for a semver constraint.
        Constraint formats: "1.0.0", "^1.0.0", "~1.0.0", ">=1.0.0"
        Returns the matching version entry dict.
        Raises RegistryError if no version matches.
        """
        from nodus.tooling.semver import Version, VersionRange

        versions = self.fetch_package_index(name)
        if not versions:
            raise RegistryError(f"No versions available for '{name}' in registry")

        # Parse constraint
        try:
            version_range = VersionRange.parse(constraint)
        except ValueError:
            raise RegistryError(f"Invalid version constraint '{constraint}' for '{name}'")

        # Filter and sort matching versions
        matching = []
        for entry in versions:
            v_str = entry.get("version", "")
            try:
                v = Version.parse(v_str)
                if version_range.matches(v):
                    matching.append((v, entry))
            except ValueError:
                continue  # skip malformed versions

        if not matching:
            available = [e.get("version", "?") for e in versions]
            raise RegistryError(
                f"No version of '{name}' satisfies constraint '{constraint}'. "
                f"Available: {', '.join(available)}"
            )

        # Pick the highest matching version
        matching.sort(key=lambda pair: pair[0], reverse=True)
        return matching[0][1]

    def download_package(self, url: str, expected_sha256: str, dest_path: Path) -> None:
        """
        Download a package archive to dest_path.
        Verifies SHA-256 integrity after download.
        Raises RegistryError on network failure or checksum mismatch.
        """
        try:
            with urllib.request.urlopen(url, timeout=60) as response:
                content = response.read()
        except urllib.error.URLError as err:
            raise RegistryError(f"Failed to download package from {url}: {err.reason}")

        actual = hashlib.sha256(content).hexdigest()
        if actual != expected_sha256:
            raise RegistryError(
                f"Checksum mismatch for {url}: "
                f"expected {expected_sha256}, got {actual}"
            )

        with open(dest_path, "wb") as f:
            f.write(content)

    def install_package(
        self,
        name: str,
        version_entry: dict,
        modules_dir: Path,
    ) -> str:
        """
        Download and extract a package into modules_dir/name/.
        Returns the sha256 hash of the installed tree.
        Raises RegistryError on any failure.
        """
        url = version_entry.get("url")
        expected_sha256 = version_entry.get("sha256", "")
        if not url:
            raise RegistryError(f"Registry entry for '{name}' missing 'url' field")

        dest_dir = Path(modules_dir) / name
        if dest_dir.exists():
            shutil.rmtree(dest_dir)
        dest_dir.mkdir(parents=True, exist_ok=True)

        with tempfile.TemporaryDirectory() as tmp:
            archive_name = url.split("/")[-1].split("?")[0] or f"{name}.tar.gz"
            archive_path = Path(tmp) / archive_name
            self.download_package(url, expected_sha256, archive_path)
            _extract_archive(archive_path, dest_dir)

        return _hash_tree(str(dest_dir))


def _extract_archive(archive_path: Path, dest_dir: Path) -> None:
    """Extract a tar.gz or zip archive into dest_dir."""
    name = archive_path.name.lower()
    if name.endswith(".tar.gz") or name.endswith(".tgz") or tarfile.is_tarfile(archive_path):
        with tarfile.open(archive_path, "r:*") as tar:
            # Strip leading component if all entries share a top-level dir
            members = tar.getmembers()
            prefix = _common_prefix(m.name for m in members if m.name)
            for member in members:
                if prefix and member.name.startswith(prefix + "/"):
                    member.name = member.name[len(prefix) + 1:]
                if not member.name:
                    continue
                try:
                    tar.extract(member, dest_dir, filter="data")
                except TypeError:
                    tar.extract(member, dest_dir)
    elif name.endswith(".zip") or zipfile.is_zipfile(archive_path):
        with zipfile.ZipFile(archive_path) as zf:
            names = zf.namelist()
            prefix = _common_prefix(names)
            for info in zf.infolist():
                if prefix and info.filename.startswith(prefix + "/"):
                    info.filename = info.filename[len(prefix) + 1:]
                if not info.filename or info.filename.endswith("/"):
                    continue
                zf.extract(info, dest_dir)
    else:
        raise RegistryError(f"Unsupported archive format: {archive_path.name}")


def _common_prefix(names) -> str:
    """Return common leading directory if all names share one, else empty string."""
    parts_list = [n.split("/") for n in names if n]
    if not parts_list:
        return ""
    first = parts_list[0][0]
    if all(p[0] == first for p in parts_list) and all(len(p) > 1 for p in parts_list):
        return first
    return ""


def _hash_tree(path: str) -> str:
    """SHA-256 hash of a directory tree (deterministic)."""
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
