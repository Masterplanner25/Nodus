"""Tests for third-party .nd module resolution via nodus.nd entry-point group.

Design Doc: docs/guide/library-entry-points.md

The resolver supports four lookup tiers for import "name":
  1. project-root/name.nd (or name/index.nd)
  2. .nodus/modules/name/index.nd    ← local package manager
  3. stdlib/name.nd                  ← std: fallback
  4. nodus.nd entry-point group      ← pip-installed packages  (tested here)

Precedence: local always wins. An installed package is shadowed if a
.nodus/modules/<name>/ directory exists.
"""

import io
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from unittest.mock import patch

sys.path.insert(0, "C:/dev/Coding Language/src")  # noqa: E402

import nodus  # noqa: E402
from nodus.runtime.module_loader import (  # noqa: E402
    ModuleLoader,
    _resolve_installed_package,
    resolve_import_path,
)
from nodus.runtime.diagnostics import LangRuntimeError  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_ep_patch(pkg_name: str, nd_root_path: str):
    """Return a context manager that mocks the entry_points lookup in the loader.

    Patches ``nodus.runtime.module_loader._importlib_entry_points`` — the
    module-level name that ``_resolve_installed_package`` calls — so that
    group='nodus.nd', name=pkg_name returns a single entry point whose
    callable returns nd_root_path.
    """
    from unittest.mock import MagicMock

    mock_ep = MagicMock()
    mock_ep.load.return_value = lambda: nd_root_path

    def fake_entry_points(group=None, name=None, **_kw):
        if group == "nodus.nd" and name == pkg_name:
            return [mock_ep]
        return []

    return patch(
        "nodus.runtime.module_loader._importlib_entry_points",
        side_effect=fake_entry_points,
    )


def _run_script(src: str, *, project_root: str | None = None) -> tuple[str, str]:
    """Execute Nodus source, return (stdout, stderr)."""
    vm = nodus.VM([], {}, code_locs=[], source_path="test.nd")
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        loader = ModuleLoader(project_root=project_root, vm=vm)
        loader.load_module_from_source(src, module_name="test.nd")
    return out.getvalue(), err.getvalue()


# ---------------------------------------------------------------------------
# 1. _resolve_installed_package unit tests
# ---------------------------------------------------------------------------

class ResolveInstalledPackageTests(unittest.TestCase):

    def test_returns_none_when_no_entry_point(self):
        result = _resolve_installed_package("no-such-package-xyz")
        self.assertIsNone(result)

    def _patch_eps(self, pkg_name: str, fn):
        """Patch the loader's entry_points lookup for a specific package name."""
        def fake_eps(group=None, name=None, **_):
            ep = unittest.mock.MagicMock()
            ep.load.return_value = fn
            return [ep] if (group == "nodus.nd" and name == pkg_name) else []
        return patch("nodus.runtime.module_loader._importlib_entry_points",
                     side_effect=fake_eps)

    def test_returns_none_when_entry_point_callable_raises(self):
        def bad_fn():
            raise RuntimeError("broken")
        with self._patch_eps("bad-pkg", bad_fn):
            result = _resolve_installed_package("bad-pkg")
        self.assertIsNone(result)

    def test_returns_none_when_path_does_not_exist(self):
        with self._patch_eps("ghost-pkg", lambda: "/nonexistent/path/nd"):
            result = _resolve_installed_package("ghost-pkg")
        self.assertIsNone(result)

    def test_returns_none_when_callable_returns_non_string(self):
        with self._patch_eps("bad-type", lambda: 42):
            result = _resolve_installed_package("bad-type")
        self.assertIsNone(result)

    def test_returns_path_for_valid_entry_point(self):
        with tempfile.TemporaryDirectory() as nd_root:
            with self._patch_eps("my-pkg", lambda: nd_root):
                result = _resolve_installed_package("my-pkg")
            self.assertEqual(result, nd_root)


# ---------------------------------------------------------------------------
# 2. resolve_import_path: entry-point resolution round-trip
# ---------------------------------------------------------------------------

class EntryPointResolverTests(unittest.TestCase):

    def _make_nd_package(self, tmpdir: str, pkg_name: str, *,
                         extra_modules: dict[str, str] | None = None) -> str:
        """Create a temp nd root with index.nd and optional sub-modules."""
        nd_root = os.path.join(tmpdir, "nd_root")
        os.makedirs(nd_root)
        with open(os.path.join(nd_root, "index.nd"), "w") as f:
            f.write(f'fn pkg_name() {{ return "{pkg_name}" }}\n')
        for mod_name, content in (extra_modules or {}).items():
            with open(os.path.join(nd_root, f"{mod_name}.nd"), "w") as f:
                f.write(content)
        return nd_root

    def test_bare_import_resolves_to_index_nd(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            nd_root = self._make_nd_package(tmpdir, "nodus-mcp")
            state = {"project_root": tmpdir, "loaded": set(), "loading": set(),
                     "exports": {}, "modules": {}, "module_ids": {}}

            with _make_ep_patch("nodus-mcp", nd_root):
                result = resolve_import_path("nodus-mcp", tmpdir, state, None, "<test>")

            expected = os.path.abspath(os.path.join(nd_root, "index.nd"))
            self.assertEqual(os.path.normcase(result), os.path.normcase(expected))

    def test_colon_form_resolves_to_submodule(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            nd_root = self._make_nd_package(
                tmpdir, "nodus-mcp",
                extra_modules={"client": 'fn connect() { return "ok" }\n'},
            )
            state = {"project_root": tmpdir, "loaded": set(), "loading": set(),
                     "exports": {}, "modules": {}, "module_ids": {}}

            with _make_ep_patch("nodus-mcp", nd_root):
                result = resolve_import_path(
                    "nodus-mcp:client", tmpdir, state, None, "<test>"
                )

            expected = os.path.abspath(os.path.join(nd_root, "client.nd"))
            self.assertEqual(os.path.normcase(result), os.path.normcase(expected))

    def test_entry_point_fires_only_after_modules_dir_misses(self):
        """Local .nodus/modules/ MUST shadow a pip-installed package."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Local package: returns "local" from pkg_name()
            local_dir = os.path.join(tmpdir, ".nodus", "modules", "nodus-mcp")
            os.makedirs(local_dir)
            with open(os.path.join(local_dir, "index.nd"), "w") as f:
                f.write('fn pkg_name() { return "local" }\n')

            # Installed package: returns "installed" from pkg_name()
            nd_root = self._make_nd_package(tmpdir, "installed")

            state = {"project_root": tmpdir, "loaded": set(), "loading": set(),
                     "exports": {}, "modules": {}, "module_ids": {}}

            with _make_ep_patch("nodus-mcp", nd_root):
                result = resolve_import_path("nodus-mcp", tmpdir, state, None, "<test>")

            # Must resolve to the local file, NOT the installed one
            expected_local = os.path.abspath(os.path.join(local_dir, "index.nd"))
            self.assertEqual(os.path.normcase(result), os.path.normcase(expected_local))


# ---------------------------------------------------------------------------
# 3. Full execution: import from entry-point package and call exported fn
# ---------------------------------------------------------------------------

class EntryPointExecutionTests(unittest.TestCase):

    def test_import_and_call_works(self):
        """import "nodus-mcp" as mcp; print(mcp.pkg_name()) → nodus-mcp"""
        with tempfile.TemporaryDirectory() as tmpdir:
            nd_root = os.path.join(tmpdir, "nd")
            os.makedirs(nd_root)
            with open(os.path.join(nd_root, "index.nd"), "w") as f:
                f.write('fn pkg_name() { return "nodus-mcp" }\n')

            src = 'import "nodus-mcp" as mcp\nprint(mcp.pkg_name())'
            with _make_ep_patch("nodus-mcp", nd_root):
                stdout, _ = _run_script(src, project_root=tmpdir)

            self.assertEqual(stdout.strip(), "nodus-mcp")

    def test_colon_import_and_call_works(self):
        """import "nodus-mcp:client" as client; print(client.connect()) → ok"""
        with tempfile.TemporaryDirectory() as tmpdir:
            nd_root = os.path.join(tmpdir, "nd")
            os.makedirs(nd_root)
            with open(os.path.join(nd_root, "client.nd"), "w") as f:
                f.write('fn connect() { return "ok" }\n')
            with open(os.path.join(nd_root, "index.nd"), "w") as f:
                f.write("// entry\n")

            src = 'import "nodus-mcp:client" as client\nprint(client.connect())'
            with _make_ep_patch("nodus-mcp", nd_root):
                stdout, _ = _run_script(src, project_root=tmpdir)

            self.assertEqual(stdout.strip(), "ok")

    def test_local_module_shadows_installed(self):
        """A .nodus/modules/nodus-mcp/index.nd overrides the entry-point package."""
        with tempfile.TemporaryDirectory() as tmpdir:
            local_dir = os.path.join(tmpdir, ".nodus", "modules", "nodus-mcp")
            os.makedirs(local_dir)
            with open(os.path.join(local_dir, "index.nd"), "w") as f:
                f.write('fn source() { return "local" }\n')

            nd_root = os.path.join(tmpdir, "nd")
            os.makedirs(nd_root)
            with open(os.path.join(nd_root, "index.nd"), "w") as f:
                f.write('fn source() { return "installed" }\n')

            src = 'import "nodus-mcp" as mcp\nprint(mcp.source())'
            with _make_ep_patch("nodus-mcp", nd_root):
                stdout, _ = _run_script(src, project_root=tmpdir)

            self.assertEqual(stdout.strip(), "local")


# ---------------------------------------------------------------------------
# 4. Error message: ImportError lists all tried paths
# ---------------------------------------------------------------------------

class ImportErrorMessageTests(unittest.TestCase):

    def _attempt_import(self, import_path: str, project_root: str,
                        ep_patch=None) -> str:
        """Attempt import; return the error message string."""
        state = {"project_root": project_root, "loaded": set(), "loading": set(),
                 "exports": {}, "modules": {}, "module_ids": {}}
        ctx = ep_patch or patch(
            "nodus.runtime.module_loader._importlib_entry_points",
            side_effect=lambda **_: [],
        )
        with ctx:
            try:
                resolve_import_path(import_path, project_root, state, None, "<test>")
                return ""
            except LangRuntimeError as e:
                return str(e)

    def test_error_lists_modules_dir_paths(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            msg = self._attempt_import("no-such-pkg", tmpdir)
            modules_dir = os.path.join(tmpdir, ".nodus", "modules")
            # The .nodus/modules/no-such-pkg path must appear in error
            self.assertIn(os.path.join(modules_dir, "no-such-pkg"), msg)

    def test_error_mentions_no_entry_point_when_none_installed(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            msg = self._attempt_import("ghost-package", tmpdir)
            self.assertIn("no nodus.nd entry-point for 'ghost-package'", msg)

    def test_error_lists_entry_point_paths_when_dir_missing(self):
        """When entry point exists but nd root has no index.nd, error lists ep paths."""
        with tempfile.TemporaryDirectory() as tmpdir:
            nd_root = os.path.join(tmpdir, "nd_root_no_index")
            os.makedirs(nd_root)
            # No index.nd — entry point dir exists but is empty

            with tempfile.TemporaryDirectory() as proj:
                msg = self._attempt_import(
                    "partial-pkg", proj, _make_ep_patch("partial-pkg", nd_root)
                )
            # Error should list paths inside nd_root (entry point was found but no .nd)
            self.assertIn(nd_root, msg)

    def test_error_colon_form_lists_both_modules_and_ep_paths(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            nd_root = os.path.join(tmpdir, "nd_root")
            os.makedirs(nd_root)
            # Has index.nd but no sub.nd

            with tempfile.TemporaryDirectory() as proj:
                msg = self._attempt_import(
                    "pkg:sub", proj, _make_ep_patch("pkg", nd_root)
                )
            # Entry-point nd_root path should appear
            self.assertIn(nd_root, msg)

    def test_error_std_import_unchanged(self):
        """std:* imports still produce the same error — no regression."""
        with tempfile.TemporaryDirectory() as tmpdir:
            state = {"project_root": tmpdir, "loaded": set(), "loading": set(),
                     "exports": {}, "modules": {}, "module_ids": {}}
            try:
                resolve_import_path("std:nonexistent_xyz", tmpdir, state, None, "<test>")
            except LangRuntimeError as e:
                msg = str(e)
            self.assertIn("std:nonexistent_xyz", msg)
            # Must NOT mention entry-point group (std: is a separate branch)
            self.assertNotIn("nodus.nd entry-point", msg)


# ---------------------------------------------------------------------------
# 5. Regression: existing import forms unchanged
# ---------------------------------------------------------------------------

class ExistingImportRegressionTests(unittest.TestCase):

    def test_std_test_still_resolves(self):
        """import 'std:test' still finds the bundled stdlib file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            state = {"project_root": tmpdir, "loaded": set(), "loading": set(),
                     "exports": {}, "modules": {}, "module_ids": {}}
            result = resolve_import_path("std:test", tmpdir, state, None, "<test>")
            self.assertTrue(result.endswith("test.nd"))
            self.assertIn("stdlib", result)

    def test_local_modules_dir_still_resolves(self):
        """import 'mypkg' from .nodus/modules/mypkg/index.nd still works."""
        with tempfile.TemporaryDirectory() as tmpdir:
            pkg_dir = os.path.join(tmpdir, ".nodus", "modules", "mypkg")
            os.makedirs(pkg_dir)
            with open(os.path.join(pkg_dir, "index.nd"), "w") as f:
                f.write("// local package\n")
            state = {"project_root": tmpdir, "loaded": set(), "loading": set(),
                     "exports": {}, "modules": {}, "module_ids": {}}
            result = resolve_import_path("mypkg", tmpdir, state, None, "<test>")
            self.assertIn("mypkg", result)
            self.assertIn(".nodus", result)

    def test_relative_import_unchanged(self):
        """import './foo' still resolves relative to the script's base dir."""
        with tempfile.TemporaryDirectory() as tmpdir:
            nd_file = os.path.join(tmpdir, "foo.nd")
            with open(nd_file, "w") as f:
                f.write("// foo\n")
            state = {"project_root": tmpdir, "loaded": set(), "loading": set(),
                     "exports": {}, "modules": {}, "module_ids": {}}
            result = resolve_import_path("./foo", tmpdir, state, None, "<test>")
            self.assertEqual(os.path.normcase(result), os.path.normcase(nd_file))

    def test_std_env_executes_correctly(self):
        """Smoke test: std:env still imports and works after resolver changes."""
        src = 'import "std:env" as env\nprint(type(env.list()))'
        stdout, _ = _run_script(src)
        self.assertEqual(stdout.strip(), "map")


if __name__ == "__main__":
    unittest.main()
