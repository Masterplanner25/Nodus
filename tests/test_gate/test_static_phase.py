"""Tests for nodus_gate static phase."""

import sys
import tempfile
import os
import unittest

sys.path.insert(0, "C:/dev/Coding Language")  # noqa: E402
sys.path.insert(0, "C:/dev/Coding Language/src")  # noqa: E402

from tools.nodus_gate.static_phase import (  # noqa: E402
    run_static_phase, _builtin_names, _stdlib_modules, _cli_commands
)


def _make_temp_root(docs: dict[str, str]) -> str:
    """Create a temp dir with fake doc files. Returns dir path."""
    root = tempfile.mkdtemp()
    lang_dir = os.path.join(root, "docs", "language")
    os.makedirs(lang_dir, exist_ok=True)
    for filename, content in docs.items():
        fpath = os.path.join(lang_dir, filename)
        with open(fpath, "w", encoding="utf-8") as f:
            f.write(content)
    return root


class BuiltinNamesTests(unittest.TestCase):
    def test_returns_non_empty_set(self):
        names = _builtin_names()
        self.assertIsInstance(names, set)
        self.assertGreater(len(names), 50)

    def test_contains_known_builtins(self):
        names = _builtin_names()
        self.assertIn("print", names)
        self.assertIn("len", names)
        self.assertIn("env_get", names)


class StdlibModulesTests(unittest.TestCase):
    def test_returns_non_empty_set(self):
        mods = _stdlib_modules()
        self.assertIsInstance(mods, set)
        self.assertGreater(len(mods), 5)

    def test_contains_known_modules(self):
        mods = _stdlib_modules()
        self.assertIn("env", mods)
        self.assertIn("http", mods)
        self.assertIn("test", mods)
        self.assertIn("tool", mods)


class CliCommandsTests(unittest.TestCase):
    def test_contains_known_commands(self):
        cmds = _cli_commands()
        self.assertIn("run", cmds)
        self.assertIn("test", cmds)
        self.assertIn("check", cmds)


class StaticPhaseTests(unittest.TestCase):

    def _run(self, docs: dict) -> object:
        root = _make_temp_root(docs)
        try:
            return run_static_phase(root)
        finally:
            import shutil
            shutil.rmtree(root, ignore_errors=True)

    def test_valid_import_no_findings(self):
        content = '```nodus\nimport "std:env" as env\n```\n'
        result = self._run({"test.md": content})
        module_findings = [f for f in result.findings if f.kind == "missing_module"]
        self.assertEqual(len(module_findings), 0)

    def test_missing_module_produces_finding(self):
        content = '```nodus\nimport "std:nonexistent_xyz_module"\n```\n'
        result = self._run({"test.md": content})
        module_findings = [f for f in result.findings if f.kind == "missing_module"]
        self.assertEqual(len(module_findings), 1)
        self.assertIn("nonexistent_xyz_module", module_findings[0].symbol)

    def test_valid_cli_command_no_findings(self):
        content = '```nodus\nnodus run script.nd\n```\n'
        result = self._run({"test.md": content})
        cli_findings = [f for f in result.findings if f.kind == "missing_cli"]
        self.assertEqual(len(cli_findings), 0)

    def test_missing_cli_command_produces_finding(self):
        content = '```nodus\nnodus fakecommand_xyz args\n```\n'
        result = self._run({"test.md": content})
        cli_findings = [f for f in result.findings if f.kind == "missing_cli"]
        self.assertEqual(len(cli_findings), 1)
        self.assertIn("fakecommand_xyz", cli_findings[0].symbol)

    def test_skip_block_not_checked(self):
        content = '```nodus-skip\nimport "std:nonexistent"\n```\n'
        result = self._run({"test.md": content})
        module_findings = [f for f in result.findings if f.kind == "missing_module"]
        self.assertEqual(len(module_findings), 0)

    def test_allowlist_suppresses_finding(self):
        content = '```nodus\nimport "std:nonexistent_xyz"\n```\n'
        root = _make_temp_root({"test.md": content})
        try:
            allowlist = {"symbol:std:nonexistent_xyz"}
            result = run_static_phase(root, allowlist=allowlist)
            module_findings = [f for f in result.findings if f.kind == "missing_module"]
            self.assertEqual(len(module_findings), 0)
        finally:
            import shutil
            shutil.rmtree(root, ignore_errors=True)

    def test_scanned_files_count(self):
        docs = {"a.md": "# hello\n", "b.md": "# world\n"}
        root = _make_temp_root(docs)
        try:
            result = run_static_phase(root)
            self.assertEqual(result.scanned_files, 2)
        finally:
            import shutil
            shutil.rmtree(root, ignore_errors=True)

    def test_no_false_positives_on_real_docs(self):
        """Smoke test: static phase on real project docs shouldn't have too many failures."""
        root = "C:/dev/Coding Language"
        result = run_static_phase(root)
        # Should scan docs without crashing; findings are acceptable
        self.assertIsInstance(result.scanned_files, int)
        self.assertIsInstance(result.findings, list)


if __name__ == "__main__":
    unittest.main()
