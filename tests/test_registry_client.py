"""Tests for the HTTP registry client."""
from __future__ import annotations

import hashlib
import json
import os
import tarfile
import tempfile
import unittest
from io import BytesIO
from pathlib import Path
from unittest.mock import MagicMock, patch

from nodus.tooling.registry_client import RegistryClient, RegistryError


def _make_tarball(contents: dict[str, str]) -> bytes:
    """Create an in-memory tar.gz archive from {filename: content} dict."""
    buf = BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        for name, content in contents.items():
            data = content.encode("utf-8")
            info = tarfile.TarInfo(name=name)
            info.size = len(data)
            tar.addfile(info, BytesIO(data))
    return buf.getvalue()


class TestRegistryClientFetchIndex(unittest.TestCase):
    def test_fetch_returns_version_list(self):
        payload = json.dumps({
            "name": "mylib",
            "versions": [
                {"version": "1.0.0", "url": "https://example.com/mylib-1.0.0.tar.gz", "sha256": "abc"},
                {"version": "1.1.0", "url": "https://example.com/mylib-1.1.0.tar.gz", "sha256": "def"},
            ]
        }).encode()
        mock_response = MagicMock()
        mock_response.read.return_value = payload
        mock_response.__enter__ = lambda s: s
        mock_response.__exit__ = MagicMock(return_value=False)
        with patch("urllib.request.urlopen", return_value=mock_response):
            client = RegistryClient("https://registry.example.com")
            versions = client.fetch_package_index("mylib")
        self.assertEqual(len(versions), 2)
        self.assertEqual(versions[0]["version"], "1.0.0")

    def test_fetch_404_raises_registry_error(self):
        import urllib.error
        with patch("urllib.request.urlopen", side_effect=urllib.error.HTTPError(None, 404, "Not Found", {}, None)):
            client = RegistryClient("https://registry.example.com")
            with self.assertRaises(RegistryError) as ctx:
                client.fetch_package_index("missing")
        self.assertIn("not found", str(ctx.exception).lower())

    def test_fetch_network_failure_raises_registry_error(self):
        import urllib.error
        with patch("urllib.request.urlopen", side_effect=urllib.error.URLError("connection refused")):
            client = RegistryClient("https://registry.example.com")
            with self.assertRaises(RegistryError):
                client.fetch_package_index("anylib")


class TestRegistryClientResolveVersion(unittest.TestCase):
    def _mock_index(self, versions: list[str]):
        payload = json.dumps({
            "name": "lib",
            "versions": [{"version": v, "url": f"https://x/{v}.tar.gz", "sha256": v} for v in versions]
        }).encode()
        mock_response = MagicMock()
        mock_response.read.return_value = payload
        mock_response.__enter__ = lambda s: s
        mock_response.__exit__ = MagicMock(return_value=False)
        return mock_response

    def test_caret_constraint(self):
        with patch("urllib.request.urlopen", return_value=self._mock_index(["1.0.0", "1.1.0", "2.0.0"])):
            client = RegistryClient("https://registry.example.com")
            result = client.resolve_version("lib", "^1.0.0")
        self.assertEqual(result["version"], "1.1.0")

    def test_tilde_constraint(self):
        with patch("urllib.request.urlopen", return_value=self._mock_index(["1.0.0", "1.0.5", "1.1.0"])):
            client = RegistryClient("https://registry.example.com")
            result = client.resolve_version("lib", "~1.0.0")
        self.assertEqual(result["version"], "1.0.5")

    def test_exact_constraint(self):
        with patch("urllib.request.urlopen", return_value=self._mock_index(["1.0.0", "1.1.0"])):
            client = RegistryClient("https://registry.example.com")
            result = client.resolve_version("lib", "1.0.0")
        self.assertEqual(result["version"], "1.0.0")

    def test_gte_constraint(self):
        with patch("urllib.request.urlopen", return_value=self._mock_index(["1.0.0", "2.0.0", "3.0.0"])):
            client = RegistryClient("https://registry.example.com")
            result = client.resolve_version("lib", ">=2.0.0")
        self.assertEqual(result["version"], "3.0.0")

    def test_no_matching_version_raises(self):
        with patch("urllib.request.urlopen", return_value=self._mock_index(["1.0.0"])):
            client = RegistryClient("https://registry.example.com")
            with self.assertRaises(RegistryError):
                client.resolve_version("lib", "^2.0.0")


class TestRegistryClientDownload(unittest.TestCase):
    def test_download_verifies_sha256(self):
        content = b"package content"
        sha = hashlib.sha256(content).hexdigest()
        mock_response = MagicMock()
        mock_response.read.return_value = content
        mock_response.__enter__ = lambda s: s
        mock_response.__exit__ = MagicMock(return_value=False)
        with tempfile.TemporaryDirectory() as td:
            dest = Path(td) / "pkg.tar.gz"
            with patch("urllib.request.urlopen", return_value=mock_response):
                client = RegistryClient("https://registry.example.com")
                client.download_package("https://example.com/pkg.tar.gz", sha, dest)
            self.assertTrue(dest.exists())
            self.assertEqual(dest.read_bytes(), content)

    def test_checksum_mismatch_raises(self):
        content = b"package content"
        wrong_sha = "0" * 64
        mock_response = MagicMock()
        mock_response.read.return_value = content
        mock_response.__enter__ = lambda s: s
        mock_response.__exit__ = MagicMock(return_value=False)
        with tempfile.TemporaryDirectory() as td:
            dest = Path(td) / "pkg.tar.gz"
            with patch("urllib.request.urlopen", return_value=mock_response):
                client = RegistryClient("https://registry.example.com")
                with self.assertRaises(RegistryError) as ctx:
                    client.download_package("https://example.com/pkg.tar.gz", wrong_sha, dest)
            self.assertIn("mismatch", str(ctx.exception).lower())


class TestRegistryClientInstall(unittest.TestCase):
    def test_install_extracts_to_modules_dir(self):
        contents = {
            "mylib/module.nd": 'export fn greet(x) { return "hello " + x }\n',
        }
        archive_bytes = _make_tarball(contents)
        sha = hashlib.sha256(archive_bytes).hexdigest()

        version_entry = {
            "version": "1.0.0",
            "url": "https://example.com/mylib-1.0.0.tar.gz",
            "sha256": sha,
        }

        mock_response = MagicMock()
        mock_response.read.return_value = archive_bytes
        mock_response.__enter__ = lambda s: s
        mock_response.__exit__ = MagicMock(return_value=False)

        with tempfile.TemporaryDirectory() as td:
            modules_dir = Path(td) / ".nodus" / "modules"
            modules_dir.mkdir(parents=True)
            with patch("urllib.request.urlopen", return_value=mock_response):
                client = RegistryClient("https://registry.example.com")
                tree_hash = client.install_package("mylib", version_entry, modules_dir)
            installed_dir = modules_dir / "mylib"
            self.assertTrue(installed_dir.is_dir())
            self.assertTrue((installed_dir / "module.nd").is_file())
            self.assertTrue(tree_hash.startswith("sha256:"))


class TestRegistryIntegration(unittest.TestCase):
    """Integration tests for registry install -> lockfile flow."""

    def test_install_updates_lockfile_with_registry_source(self):
        """Full install flow: registry dep resolved -> lockfile has source=registry."""
        contents = {"strings.nd": 'export fn upper(x) { return x }\n'}
        archive_bytes = _make_tarball(contents)
        sha = hashlib.sha256(archive_bytes).hexdigest()

        index_payload = json.dumps({
            "name": "utils",
            "versions": [{"version": "1.0.0", "url": "https://pkg.example.com/utils-1.0.0.tar.gz", "sha256": sha}]
        }).encode()

        call_count = [0]

        def mock_urlopen(url, timeout=None):
            mock_response = MagicMock()
            mock_response.__enter__ = lambda s: s
            mock_response.__exit__ = MagicMock(return_value=False)
            if "/packages/" in url:
                mock_response.read.return_value = index_payload
            else:
                mock_response.read.return_value = archive_bytes
            call_count[0] += 1
            return mock_response

        with tempfile.TemporaryDirectory() as td:
            with open(os.path.join(td, "nodus.toml"), "w") as f:
                f.write('[package]\nname = "demo"\nversion = "0.1.0"\n\n')
                f.write('[dependencies]\nutils = "^1.0.0"\n')

            with patch("urllib.request.urlopen", side_effect=mock_urlopen):
                from nodus.tooling.package_manager import install_dependencies_for_project
                install_dependencies_for_project(td, registry_url="https://registry.example.com")

            lock_path = os.path.join(td, "nodus.lock")
            self.assertTrue(os.path.isfile(lock_path))
            with open(lock_path) as f:
                lock_text = f.read()
            self.assertIn('name = "utils"', lock_text)
            self.assertIn('source = "registry"', lock_text)
            self.assertIn('hash = "sha256:', lock_text)


if __name__ == "__main__":
    unittest.main()
