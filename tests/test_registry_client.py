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

        def mock_urlopen(req_or_url, timeout=None):
            mock_response = MagicMock()
            mock_response.__enter__ = lambda s: s
            mock_response.__exit__ = MagicMock(return_value=False)
            url_str = req_or_url.full_url if hasattr(req_or_url, "full_url") else str(req_or_url)
            if "/packages/" in url_str:
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


class TestCreatePackageArchive(unittest.TestCase):
    def test_creates_valid_tarball(self):
        from nodus.tooling.registry_client import create_package_archive
        with tempfile.TemporaryDirectory() as td:
            src = Path(td) / "mypkg"
            src.mkdir()
            (src / "nodus.toml").write_text('[package]\nname="mypkg"\nversion="1.0.0"\n')
            (src / "main.nd").write_text('print("hi")\n')
            out = Path(td) / "mypkg-1.0.0.tar.gz"
            sha = create_package_archive(src, out, name="mypkg", version="1.0.0")
            self.assertTrue(out.exists())
            self.assertTrue(sha.startswith("") and len(sha) == 64)  # hex sha256
            with tarfile.open(out, "r:gz") as tar:
                names = tar.getnames()
            self.assertIn("mypkg-1.0.0/nodus.toml", names)
            self.assertIn("mypkg-1.0.0/main.nd", names)

    def test_excludes_nodus_dir(self):
        from nodus.tooling.registry_client import create_package_archive
        with tempfile.TemporaryDirectory() as td:
            src = Path(td) / "mypkg"
            src.mkdir()
            (src / "nodus.toml").write_text('[package]\nname="mypkg"\nversion="1.0.0"\n')
            nodus_dir = src / ".nodus"
            nodus_dir.mkdir()
            (nodus_dir / "cache.json").write_text("{}")
            out = Path(td) / "out.tar.gz"
            create_package_archive(src, out, name="mypkg", version="1.0.0")
            with tarfile.open(out, "r:gz") as tar:
                names = tar.getnames()
            self.assertFalse(any(".nodus" in n for n in names))

    def test_excludes_pycache(self):
        from nodus.tooling.registry_client import create_package_archive
        with tempfile.TemporaryDirectory() as td:
            src = Path(td) / "mypkg"
            src.mkdir()
            (src / "nodus.toml").write_text('[package]\nname="mypkg"\nversion="1.0.0"\n')
            pycache = src / "__pycache__"
            pycache.mkdir()
            (pycache / "foo.pyc").write_bytes(b"")
            out = Path(td) / "out.tar.gz"
            create_package_archive(src, out, name="mypkg", version="1.0.0")
            with tarfile.open(out, "r:gz") as tar:
                names = tar.getnames()
            self.assertFalse(any("__pycache__" in n for n in names))

    def test_returns_correct_sha256(self):
        from nodus.tooling.registry_client import create_package_archive
        with tempfile.TemporaryDirectory() as td:
            src = Path(td) / "mypkg"
            src.mkdir()
            (src / "nodus.toml").write_text('[package]\nname="mypkg"\nversion="1.0.0"\n')
            out = Path(td) / "out.tar.gz"
            sha = create_package_archive(src, out, name="mypkg", version="1.0.0")
            expected = hashlib.sha256(out.read_bytes()).hexdigest()
            self.assertEqual(sha, expected)

    def test_raises_if_no_manifest(self):
        from nodus.tooling.registry_client import create_package_archive, RegistryError
        with tempfile.TemporaryDirectory() as td:
            src = Path(td) / "empty"
            src.mkdir()
            out = Path(td) / "out.tar.gz"
            with self.assertRaises(RegistryError):
                create_package_archive(src, out, name="x", version="1.0.0")


class TestPublishPackage(unittest.TestCase):
    def _make_archive(self, td: str) -> tuple:
        src = Path(td) / "mypkg"
        src.mkdir()
        (src / "nodus.toml").write_text('[package]\nname="mypkg"\nversion="1.0.0"\n')
        (src / "main.nd").write_text('print("hi")\n')
        from nodus.tooling.registry_client import create_package_archive
        out = Path(td) / "mypkg-1.0.0.tar.gz"
        sha = create_package_archive(src, out, name="mypkg", version="1.0.0")
        return out, sha

    def test_publish_sends_post_to_correct_endpoint(self):
        import urllib.error
        captured = {}
        with tempfile.TemporaryDirectory() as td:
            archive, sha = self._make_archive(td)

            def mock_urlopen(req, timeout=None):
                captured["url"] = req.full_url
                captured["method"] = req.method
                captured["headers"] = dict(req.headers)
                mock_response = MagicMock()
                mock_response.read.return_value = json.dumps(
                    {"name": "mypkg", "version": "1.0.0", "url": "https://x/mypkg-1.0.0.tar.gz"}
                ).encode()
                mock_response.__enter__ = lambda s: s
                mock_response.__exit__ = MagicMock(return_value=False)
                return mock_response

            with patch("urllib.request.urlopen", side_effect=mock_urlopen):
                client = RegistryClient("https://registry.example.com", token="tok")
                result = client.publish_package("mypkg", "1.0.0", archive, sha)
        self.assertIn("/packages/mypkg/1.0.0", captured["url"])
        self.assertEqual(captured["method"], "POST")
        self.assertIn("Authorization", captured["headers"])

    def test_publish_raises_on_409_conflict(self):
        import urllib.error
        with tempfile.TemporaryDirectory() as td:
            archive, sha = self._make_archive(td)
            with patch("urllib.request.urlopen",
                       side_effect=urllib.error.HTTPError(None, 409, "Conflict", {}, None)):
                client = RegistryClient("https://registry.example.com", token="tok")
                with self.assertRaises(RegistryError) as ctx:
                    client.publish_package("mypkg", "1.0.0", archive, sha)
            self.assertIn("already exists", str(ctx.exception))

    def test_publish_raises_if_no_token(self):
        with tempfile.TemporaryDirectory() as td:
            archive, sha = self._make_archive(td)
            client = RegistryClient("https://registry.example.com")
            with self.assertRaises(RegistryError) as ctx:
                client.publish_package("mypkg", "1.0.0", archive, sha)
            self.assertIn("token", str(ctx.exception).lower())

    def test_publish_401_does_not_leak_token(self):
        import urllib.error
        token = "supersecretpublishtoken"
        with tempfile.TemporaryDirectory() as td:
            archive, sha = self._make_archive(td)
            with patch("urllib.request.urlopen",
                       side_effect=urllib.error.HTTPError(None, 401, "Unauthorized", {}, None)):
                client = RegistryClient("https://registry.example.com", token=token)
                with self.assertRaises(RegistryError) as ctx:
                    client.publish_package("mypkg", "1.0.0", archive, sha)
            self.assertNotIn(token, str(ctx.exception))


class TestRegistryClientAuth(unittest.TestCase):
    def test_token_sends_auth_header(self):
        """Client with token sends Authorization: Bearer header."""
        payload = json.dumps({"name": "lib", "versions": []}).encode()
        captured_request = {}

        def mock_urlopen(req, timeout=None):
            captured_request["headers"] = dict(req.headers) if hasattr(req, "headers") else {}
            mock_response = MagicMock()
            mock_response.read.return_value = payload
            mock_response.__enter__ = lambda s: s
            mock_response.__exit__ = MagicMock(return_value=False)
            return mock_response

        with patch("urllib.request.urlopen", side_effect=mock_urlopen):
            client = RegistryClient("https://registry.example.com", token="mytoken")
            try:
                client.fetch_package_index("lib")
            except RegistryError:
                pass
        # Header keys are title-cased by urllib
        auth = captured_request.get("headers", {}).get("Authorization", "")
        self.assertEqual(auth, "Bearer mytoken")

    def test_no_token_sends_no_auth_header(self):
        """Client without token sends no Authorization header."""
        payload = json.dumps({"name": "lib", "versions": []}).encode()
        captured_request = {}

        def mock_urlopen(req, timeout=None):
            captured_request["headers"] = dict(req.headers) if hasattr(req, "headers") else {}
            mock_response = MagicMock()
            mock_response.read.return_value = payload
            mock_response.__enter__ = lambda s: s
            mock_response.__exit__ = MagicMock(return_value=False)
            return mock_response

        with patch("urllib.request.urlopen", side_effect=mock_urlopen):
            client = RegistryClient("https://registry.example.com")
            try:
                client.fetch_package_index("lib")
            except RegistryError:
                pass
        auth = captured_request.get("headers", {}).get("Authorization", "")
        self.assertEqual(auth, "")

    def test_401_raises_registry_error_without_token(self):
        """401 response raises RegistryError; token not in error message."""
        import urllib.error
        token = "supersecrettoken"
        with patch("urllib.request.urlopen",
                   side_effect=urllib.error.HTTPError(None, 401, "Unauthorized", {}, None)):
            client = RegistryClient("https://registry.example.com", token=token)
            with self.assertRaises(RegistryError) as ctx:
                client.fetch_package_index("pkg")
        self.assertNotIn(token, str(ctx.exception))

    def test_403_raises_registry_error(self):
        """403 response raises RegistryError."""
        import urllib.error
        with patch("urllib.request.urlopen",
                   side_effect=urllib.error.HTTPError(None, 403, "Forbidden", {}, None)):
            client = RegistryClient("https://registry.example.com", token="tok")
            with self.assertRaises(RegistryError):
                client.fetch_package_index("pkg")


class TestGetRegistryToken(unittest.TestCase):
    def test_cli_token_takes_priority(self):
        from nodus.tooling.package_manager import get_registry_token
        with patch.dict(os.environ, {"NODUS_REGISTRY_TOKEN": "envtoken"}):
            result = get_registry_token(cli_token="clitoken")
        self.assertEqual(result, "clitoken")

    def test_env_var_used_when_no_cli_token(self):
        from nodus.tooling.package_manager import get_registry_token
        with patch.dict(os.environ, {"NODUS_REGISTRY_TOKEN": "envtoken"}):
            result = get_registry_token()
        self.assertEqual(result, "envtoken")

    def test_returns_none_when_no_token(self):
        from nodus.tooling.package_manager import get_registry_token
        env = {k: v for k, v in os.environ.items() if k != "NODUS_REGISTRY_TOKEN"}
        with patch.dict(os.environ, env, clear=True):
            with patch("nodus.tooling.user_config.UserConfig.get_registry_token", return_value=None):
                result = get_registry_token()
        self.assertIsNone(result)


class TestUserConfig(unittest.TestCase):
    def test_set_and_get_global_token(self):
        from nodus.tooling.user_config import UserConfig
        with tempfile.TemporaryDirectory() as td:
            cfg_path = Path(td) / "config.toml"
            cfg = UserConfig(config_path=cfg_path)
            cfg.set_registry_token("mytoken")
            cfg2 = UserConfig(config_path=cfg_path)
            self.assertEqual(cfg2.get_registry_token(), "mytoken")

    def test_set_and_get_url_specific_token(self):
        from nodus.tooling.user_config import UserConfig
        with tempfile.TemporaryDirectory() as td:
            cfg_path = Path(td) / "config.toml"
            cfg = UserConfig(config_path=cfg_path)
            cfg.set_registry_token("urltoken", registry_url="https://reg.example.com")
            cfg2 = UserConfig(config_path=cfg_path)
            self.assertEqual(cfg2.get_registry_token("https://reg.example.com"), "urltoken")
            self.assertIsNone(cfg2.get_registry_token("https://other.example.com"))

    def test_clear_token(self):
        from nodus.tooling.user_config import UserConfig
        with tempfile.TemporaryDirectory() as td:
            cfg_path = Path(td) / "config.toml"
            cfg = UserConfig(config_path=cfg_path)
            cfg.set_registry_token("mytoken")
            cfg.clear_registry_token()
            cfg2 = UserConfig(config_path=cfg_path)
            self.assertIsNone(cfg2.get_registry_token())

    def test_missing_config_returns_none(self):
        from nodus.tooling.user_config import UserConfig
        with tempfile.TemporaryDirectory() as td:
            cfg_path = Path(td) / "nonexistent.toml"
            cfg = UserConfig(config_path=cfg_path)
            self.assertIsNone(cfg.get_registry_token())


if __name__ == "__main__":
    unittest.main()
