"""HTTP registry client for Nodus package manager."""
from __future__ import annotations

import fnmatch
import hashlib
import io
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

    def __init__(self, registry_url: str, token: str | None = None) -> None:
        self.registry_url = registry_url.rstrip("/")
        self._token = token

    def _auth_headers(self) -> dict:
        if self._token:
            return {"Authorization": f"Bearer {self._token}"}
        return {}

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
            req = urllib.request.Request(url, headers=self._auth_headers())
            with urllib.request.urlopen(req, timeout=30) as response:
                data = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as err:
            if err.code == 404:
                raise RegistryError(f"Package '{name}' not found in registry at {self.registry_url}")
            if err.code == 401:
                raise RegistryError(
                    f"Registry authentication failed for {self.registry_url}. "
                    "Run 'nodus login' or set NODUS_REGISTRY_TOKEN."
                )
            if err.code == 403:
                raise RegistryError(
                    f"Registry access forbidden for {self.registry_url}. "
                    "Check token permissions."
                )
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
            req = urllib.request.Request(url, headers=self._auth_headers())
            with urllib.request.urlopen(req, timeout=60) as response:
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

    def publish_package(self, name: str, version: str, archive_path: Path, sha256: str) -> dict:
        """
        POST the archive to {registry_url}/packages/{name}/{version}.

        Requires a token — raises RegistryError if none is set.
        Returns the registry's 201 success response dict.
        Raises RegistryError on 401, 403, 409, 422, or network/parse failure.
        """
        if not self._token:
            raise RegistryError(
                f"No token configured for {self.registry_url}. "
                "Run 'nodus login' or set NODUS_REGISTRY_TOKEN."
            )

        url = f"{self.registry_url}/packages/{name}/{version}"
        archive_bytes = Path(archive_path).read_bytes()
        headers = {
            **self._auth_headers(),
            "Content-Type": "application/octet-stream",
            "X-SHA256": sha256,
        }
        req = urllib.request.Request(url, data=archive_bytes, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=120) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as err:
            body = ""
            try:
                body = err.read().decode("utf-8", errors="replace")
            except Exception:
                pass
            if err.code == 401:
                raise RegistryError(
                    f"Registry authentication failed for {self.registry_url}. "
                    "Run 'nodus login' or set NODUS_REGISTRY_TOKEN."
                )
            if err.code == 403:
                raise RegistryError(
                    f"Registry access forbidden for {self.registry_url}. "
                    "Check that your token has publish permission."
                )
            if err.code == 409:
                raise RegistryError(
                    f"Version {version} of '{name}' already exists in the registry. "
                    "Published versions are immutable. Use a new version number."
                )
            raise RegistryError(
                f"Publish failed: HTTP {err.code} from {self.registry_url}. "
                f"Response: {body[:200]}"
            )
        except urllib.error.URLError as err:
            raise RegistryError(f"Publish connection failed for {self.registry_url}: {err.reason}")

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


# Files/directories excluded from published archives
_PUBLISH_EXCLUDE = frozenset([
    ".nodus", "__pycache__", ".git", ".gitignore", ".github",
    "*.pyc", "*.pyo", "nodus.lock",
])


def _should_exclude(name: str) -> bool:
    """Return True if name matches a publish exclusion pattern."""
    for pattern in _PUBLISH_EXCLUDE:
        if fnmatch.fnmatch(name, pattern):
            return True
    return False


def create_package_archive(source_dir: Path, output_path: Path, *, name: str, version: str) -> str:
    """
    Create a .tar.gz archive of source_dir at output_path.

    The archive root is named {name}-{version}/.
    Excludes: .nodus/, __pycache__/, .git/, *.pyc, nodus.lock, .gitignore.

    Returns the SHA-256 hex digest of the created archive.
    Raises RegistryError if source_dir does not contain nodus.toml.
    """
    source_dir = Path(source_dir)
    if not (source_dir / "nodus.toml").exists():
        raise RegistryError(f"No nodus.toml found in {source_dir}")

    archive_root = f"{name}-{version}"

    with tarfile.open(output_path, "w:gz") as tar:
        for item in sorted(source_dir.rglob("*")):
            # Check each path component for exclusion
            rel = item.relative_to(source_dir)
            parts = rel.parts
            if any(_should_exclude(part) for part in parts):
                continue
            arcname = f"{archive_root}/{rel.as_posix()}"
            tar.add(item, arcname=arcname, recursive=False)

    digest = hashlib.sha256(Path(output_path).read_bytes()).hexdigest()
    return digest
