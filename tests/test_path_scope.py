"""`allowed_paths` gains a write dimension (#467).

The jail was a single flat list: a path was reachable for everything or for
nothing. `_ensure_path_allowed(path, op_name)` took the operation's name and used
it *only to phrase the error message*, never to decide -- so "these files are
editable, these are read-only context", which is the two-tier model every coding
agent wants, could not be said.

The driver is Aider's split: files added to the chat are editable, repo-map files
are read-only context.

Additive by decision: `writable_paths=None` means "everything readable", which is
every release through 5.2.0. Flipping that to deny-by-default is a major-version
change, the way `allow_subprocess` was at 5.0.0.
"""

import ast
import os
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))  # noqa: E402

from nodus.runtime.capability import AUTHORITY_ATTRIBUTES  # noqa: E402
from nodus.runtime.embedding import NodusRuntime  # noqa: E402


REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SRC_ROOT = os.path.join(REPO_ROOT, "src")

PROGRAM = """
fn main() {
    print("read ctx  -> \\(len(read_file("ctx/readme.txt")))")
    write_file("src/out.txt", "wrote")
    print("write src -> ok")
    write_file("ctx/out.txt", "nope")
    print("write ctx -> ok")
}
"""

NOT_WRITABLE = "readable but not writable"


class WorkspaceTestCase(unittest.TestCase):
    """A readable tree with an editable subtree inside it."""

    def setUp(self):
        self._dir = tempfile.TemporaryDirectory()
        self.root = os.path.realpath(self._dir.name)
        self.addCleanup(self._dir.cleanup)
        os.makedirs(os.path.join(self.root, "ctx"))
        os.makedirs(os.path.join(self.root, "src"))
        with open(os.path.join(self.root, "ctx", "readme.txt"), "w") as handle:
            handle.write("hi")
        self._cwd = os.getcwd()
        os.chdir(self.root)
        self.addCleanup(os.chdir, self._cwd)

    @property
    def editable(self):
        return os.path.join(self.root, "src")


class WriteScopeTests(WorkspaceTestCase):
    # closes: #467
    def test_a_readable_path_outside_the_writable_set_refuses_writes(self):
        result = NodusRuntime(
            timeout_ms=None, allowed_paths=[self.root], writable_paths=[self.editable]
        ).run_source(PROGRAM)
        self.assertIn("read ctx  -> 2", result["stdout"])
        self.assertIn("write src -> ok", result["stdout"])
        self.assertNotIn("write ctx -> ok", result["stdout"])
        self.assertEqual(result["error"]["kind"], "sandbox")
        self.assertIn(NOT_WRITABLE, result["error"]["message"])

    # closes: #467
    def test_omitting_writable_paths_changes_nothing(self):
        """The 5.2.0 behaviour, which is what makes this additive."""
        result = NodusRuntime(
            timeout_ms=None, allowed_paths=[self.root]
        ).run_source(PROGRAM)
        self.assertTrue(result["ok"], result.get("error"))
        self.assertIn("write ctx -> ok", result["stdout"])

    def test_an_empty_writable_list_refuses_every_write(self):
        """`[]` is a statement, not an omission -- same as `allowed_paths=[]`."""
        result = NodusRuntime(
            timeout_ms=None, allowed_paths=[self.root], writable_paths=[]
        ).run_source(PROGRAM)
        self.assertEqual(result["error"]["kind"], "sandbox")
        self.assertIn("no path is writable", result["error"]["message"])
        self.assertIn("read ctx  -> 2", result["stdout"], "reads must still work")

    def test_writes_still_obey_the_read_jail(self):
        """A writable path grants nothing on its own; both checks run."""
        result = NodusRuntime(
            timeout_ms=None,
            allowed_paths=[self.editable],
            writable_paths=[self.editable],
        ).run_source('fn main() { write_file("../ctx/out.txt", "x") }')
        self.assertEqual(result["error"]["kind"], "sandbox")

    def test_a_writable_path_outside_the_read_jail_is_refused_at_construction(self):
        """Declared-or-refused: it could never grant anything, so say so."""
        with self.assertRaises(ValueError) as caught:
            NodusRuntime(
                allowed_paths=[self.editable],
                writable_paths=[os.path.join(self.root, "ctx")],
            )
        self.assertIn("outside allowed_paths", str(caught.exception))

    def test_writable_paths_without_a_read_jail_still_scopes_writes(self):
        """`allowed_paths=None` is unrestricted reads; writes can still be scoped."""
        result = NodusRuntime(
            timeout_ms=None, allowed_paths=None, writable_paths=[self.editable]
        ).run_source(PROGRAM)
        self.assertIn("write src -> ok", result["stdout"])
        self.assertIn(NOT_WRITABLE, result["error"]["message"])

    def test_every_write_builtin_is_scoped(self):
        """Not just write_file. Each of these reaches the same decision point."""
        for source in (
            'fn main() { write_file("ctx/a.txt", "x") }',
            'fn main() { append_file("ctx/a.txt", "x") }',
            'fn main() { mkdir("ctx/sub") }',
        ):
            with self.subTest(source=source):
                result = NodusRuntime(
                    timeout_ms=None,
                    allowed_paths=[self.root],
                    writable_paths=[self.editable],
                ).run_source(source)
                self.assertEqual(result["error"]["kind"], "sandbox", source)
                self.assertIn(NOT_WRITABLE, result["error"]["message"])

    def test_read_builtins_are_unaffected_by_the_write_scope(self):
        for source in (
            'fn main() { let _ = read_file("ctx/readme.txt") }',
            'fn main() { let _ = list_dir("ctx") }',
            'fn main() { let _ = path_exists("ctx/readme.txt") }',
        ):
            with self.subTest(source=source):
                result = NodusRuntime(
                    timeout_ms=None,
                    allowed_paths=[self.root],
                    writable_paths=[self.editable],
                ).run_source(source)
                self.assertTrue(result["ok"], result.get("error"))


class OneDecisionPointTests(unittest.TestCase):
    """Assert on the source, so a new fs builtin cannot ship unscoped.

    A behaviour test only covers the builtins somebody thought to write a case
    for. This covers the ones nobody has written yet, which is the failure that
    actually happens -- `_ensure_path_allowed` accumulated twelve callers over
    five major versions and none of them could say what they were doing.
    """

    def _calls(self):
        for directory, _dirs, files in os.walk(SRC_ROOT):
            for filename in files:
                if not filename.endswith(".py"):
                    continue
                path = os.path.join(directory, filename)
                # utf-8-sig: at least one file in the tree carries a BOM, and
                # plain utf-8 leaves it in place for ast.parse to choke on.
                with open(path, encoding="utf-8-sig") as handle:
                    tree = ast.parse(handle.read(), filename=path)
                for node in ast.walk(tree):
                    if not isinstance(node, ast.Call):
                        continue
                    func = node.func
                    if isinstance(func, ast.Attribute) and func.attr == "_ensure_path_allowed":
                        yield path, node

    # closes: #467
    def test_every_caller_states_its_operation_class(self):
        found = 0
        for path, node in self._calls():
            found += 1
            keywords = {kw.arg for kw in node.keywords}
            self.assertIn(
                "write",
                keywords,
                f"{os.path.relpath(path, REPO_ROOT)}:{node.lineno} calls "
                f"_ensure_path_allowed without saying whether it is a write",
            )
            value = next(kw.value for kw in node.keywords if kw.arg == "write")
            self.assertIsInstance(
                value,
                ast.Constant,
                f"{os.path.relpath(path, REPO_ROOT)}:{node.lineno} passes a "
                f"computed write= ; the classification must be readable here",
            )
        self.assertGreaterEqual(found, 10, "the AST scan found suspiciously few callers")

    # closes: #467
    def test_the_keyword_has_no_default(self):
        """A default would let a new fs builtin be misclassified in silence.

        That is this codebase's signature defect -- a decision that one path
        supplies and another inherits by omission.
        """
        import inspect

        from nodus.vm.vm import VM

        parameter = inspect.signature(VM._ensure_path_allowed).parameters["write"]
        self.assertIs(parameter.default, inspect.Parameter.empty)
        self.assertIs(parameter.kind, inspect.Parameter.KEYWORD_ONLY)


class AuthorityPropagationTests(unittest.TestCase):
    # closes: #467
    def test_writable_paths_is_an_authority_attribute(self):
        """A derived VM must not shed it -- #405's instance of the same shape."""
        self.assertIn("writable_paths", AUTHORITY_ATTRIBUTES)

    def test_a_derived_vm_inherits_the_write_scope(self):
        from nodus.runtime.capability import inherit_authority
        from nodus.vm.vm import VM

        parent = VM([], {}, code_locs=[], allowed_paths=["/a"], writable_paths=["/a/b"])
        child = VM([], {}, code_locs=[])
        inherit_authority(child, parent)
        self.assertEqual(child.writable_paths, parent.writable_paths)


class CliWriteScopeTests(WorkspaceTestCase):
    """The CLI builds a VM directly and never constructs a NodusRuntime.

    Two enforcement paths, so both are checked -- the security-boundary rule in
    `TECH_DEBT.md § Testing Methodology`.
    """

    def run_nodus(self, *args):
        path = os.path.join(self.root, "w.nd")
        with open(path, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(PROGRAM)
        env = dict(os.environ)
        env["PYTHONPATH"] = SRC_ROOT
        completed = subprocess.run(
            [sys.executable, os.path.join(REPO_ROOT, "nodus.py"), "run", path, *args],
            capture_output=True, cwd=self.root, env=env, timeout=180,
        )
        return (completed.stdout + completed.stderr).decode("utf-8", "replace")

    # closes: #467
    def test_cli_writable_paths_scopes_writes(self):
        output = self.run_nodus("--allow-paths", self.root,
                                "--writable-paths", self.editable)
        self.assertIn("write src -> ok", output)
        self.assertIn(NOT_WRITABLE, output)
        self.assertNotIn("write ctx -> ok", output)

    def test_cli_without_the_flag_is_unchanged(self):
        output = self.run_nodus("--allow-paths", self.root)
        self.assertIn("write ctx -> ok", output)
        self.assertNotIn(NOT_WRITABLE, output)

    def test_the_flag_is_documented_where_it_is_parsed(self):
        env = dict(os.environ)
        env["PYTHONPATH"] = SRC_ROOT
        completed = subprocess.run(
            [sys.executable, os.path.join(REPO_ROOT, "nodus.py"), "run", "--help"],
            capture_output=True, cwd=self.root, env=env, timeout=120,
        )
        self.assertIn("--writable-paths", completed.stdout.decode("utf-8", "replace"))


class NoEnvironmentFallbackTests(WorkspaceTestCase):
    """A deliberate asymmetry with `NODUS_ALLOWED_PATHS`, not an oversight.

    That variable widens a *default* jail when the caller passed nothing. There
    is nothing to widen here -- unset already means "everything readable" -- so a
    variable could only narrow, and write confinement that moves with ambient
    state produces a program that works locally and is refused in production with
    no difference in the code.
    """

    # closes: #467
    def test_no_env_var_narrows_the_write_scope(self):
        os.environ["NODUS_WRITABLE_PATHS"] = self.editable
        self.addCleanup(os.environ.pop, "NODUS_WRITABLE_PATHS", None)
        result = NodusRuntime(
            timeout_ms=None, allowed_paths=[self.root]
        ).run_source(PROGRAM)
        self.assertTrue(result["ok"], "an env var must not silently scope writes")
        self.assertIn("write ctx -> ok", result["stdout"])


if __name__ == "__main__":
    unittest.main()
