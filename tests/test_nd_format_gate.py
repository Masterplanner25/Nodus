"""CI and the pre-commit hook ask one thing, in one place (#741).

*Which `.nd` files get format-checked?* used to have three answers, none of them
agreeing:

- **CI** globbed the tree with `find`, excluding `./.venv/` and nothing else
  shaped like it, so anywhere but CI it also swept every other virtualenv.
- **The pre-commit hook** restated CI's list in its own words, omitted all four
  of its exclusions, and claimed in its own header to be "the same command as
  CI". It blocked commits on `tests/fixtures/fmt/`, where an `_input.nd` is
  unformatted on purpose.
- **`tools/list_fmt_targets.py`** held a third list, excluded no virtualenv, and
  was dead — nothing had called it since the initial commit.

And the hook was **untracked**, so there was nothing to correct once: a fix
helped one checkout and the next clone installed whatever copy it had.

`tools/check_nd_format.py` is the single answer now, and it also does not
reimplement *"is this file formatted"* — that belongs to `nodus fmt --check`, so
`_format_file` is imported and used. A second implementation of the question a
gate is gating is the same defect one layer down.

`TheGateCanFailTests` is the one that earns its place. A format gate that always
exits 0 looks exactly like a tree that is always formatted, and this repo has
already been bitten by a check that went quiet rather than failing.
"""

import os
import subprocess
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

_REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO_ROOT))  # noqa: E402
sys.path.insert(0, str(_REPO_ROOT / "src"))  # noqa: E402

from tools import check_nd_format  # noqa: E402


class TheTargetListComesFromGitTests(unittest.TestCase):
    # closes: #741
    def test_it_lists_the_tracked_nd_files(self):
        paths = check_nd_format.targets()
        self.assertGreater(len(paths), 40, "the sweep collected almost nothing")
        self.assertTrue(all(p.endswith(".nd") for p in paths))

    # closes: #741
    def test_no_virtualenv_is_swept(self):
        """The concrete failure: this checkout holds nine virtualenvs of
        installed stdlib copies. Reading the list from git rather than the
        filesystem drops every gitignored path without enumerating them, so a
        tenth cannot quietly rejoin."""
        for path in check_nd_format.targets():
            with self.subTest(path=path):
                self.assertNotIn("venv", path)
                self.assertNotIn("site-packages", path)

    # closes: #741
    def test_formatter_fixtures_are_excluded(self):
        """A fixture `_input.nd` is unformatted on purpose — a fixture whose
        input is already formatted tests nothing — and the old hook blocked
        commits on exactly those."""
        self.assertTrue(
            any(
                p.startswith("tests/fixtures/fmt/")
                for p in check_nd_format._git("ls-files")
                if p.endswith(".nd")
            ),
            "there should be fixtures to exclude, or this proves nothing",
        )
        self.assertEqual(
            [], [p for p in check_nd_format.targets() if "fixtures/fmt" in p]
        )

    # closes: #741
    def test_the_exclusions_are_named_once(self):
        """Not a list per caller. The whole issue was three lists that had to
        agree and did not."""
        self.assertEqual(("tests/fixtures/fmt/",), check_nd_format.EXCLUDED_PREFIXES)


class TheGateCanFailTests(unittest.TestCase):
    """A gate that cannot fail is indistinguishable from a tree that always
    passes, and costs more, because it is believed."""

    def _run(self, *args: str) -> subprocess.CompletedProcess:
        env = dict(os.environ, PYTHONPATH=str(_REPO_ROOT / "src"))
        return subprocess.run(
            [sys.executable, "-m", "tools.check_nd_format", *args],
            capture_output=True, text=True, cwd=str(_REPO_ROOT), env=env, timeout=600,
        )

    # closes: #741
    def test_a_clean_tree_exits_zero(self):
        self.assertEqual(0, self._run().returncode, self._run().stdout)

    # closes: #741
    def test_an_unformatted_file_exits_one_and_names_it(self):
        """Written to a temp file and checked directly rather than by editing a
        tracked file, so a failure here cannot leave the repo dirty."""
        with TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "unformatted.nd")
            with open(path, "w", encoding="utf-8") as handle:
                handle.write("let a=1\nlet   b  =  2\n")
            failed = check_nd_format.check([path])
        self.assertEqual([path], failed, "an unformatted file must be reported")


class ItDoesNotReimplementTheCheckTests(unittest.TestCase):
    """Which files is this module's question. Whether one is formatted is
    `nodus fmt --check`'s, and stays there."""

    # closes: #741
    def test_it_delegates_to_the_cli_check(self):
        import ast

        source = (_REPO_ROOT / "tools" / "check_nd_format.py").read_text(
            encoding="utf-8"
        )
        tree = ast.parse(source)
        imported = {
            alias.name
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom)
            for alias in node.names
        }
        self.assertIn(
            "_format_file", imported,
            "the gate must use the same check as `nodus fmt --check`, not its own",
        )
        self.assertNotIn(
            "format_source", imported,
            "reading the formatter directly would reimplement the encoding and "
            "line-ending handling that `_format_file` already decides",
        )


class TheHookIsTrackedAndDelegatesTests(unittest.TestCase):
    """The half of #741 that is not about exclusions: there was no canonical
    copy of the hook, so no fix could reach anyone else."""

    HOOK = _REPO_ROOT / "tools" / "hooks" / "pre-commit"

    # closes: #741
    def test_the_hook_is_in_the_repository(self):
        self.assertTrue(self.HOOK.is_file(), "the hook needs a tracked home")
        listed = subprocess.run(
            ["git", "ls-files", "tools/hooks/pre-commit"],
            capture_output=True, text=True, cwd=str(_REPO_ROOT), timeout=120,
        )
        self.assertEqual("tools/hooks/pre-commit", listed.stdout.strip())

    # closes: #741
    def test_the_hook_decides_nothing_itself(self):
        """It must call the module, not restate its filter. Restating it is what
        the previous hook did, and what made its header's claim false."""
        body = self.HOOK.read_text(encoding="utf-8")
        self.assertIn("tools.check_nd_format --staged", body)
        for restated in ("-not -path", "tmp_demo", "fixtures/fmt"):
            with self.subTest(fragment=restated):
                self.assertNotIn(
                    restated, body.split("set -e")[-1],
                    "the hook must not carry its own copy of the file filter",
                )


class CiRunsTheSameModuleTests(unittest.TestCase):
    # closes: #741
    def test_the_workflow_calls_the_shared_checker(self):
        workflow = (_REPO_ROOT / ".github" / "workflows" / "ci.yml").read_text(
            encoding="utf-8"
        )
        self.assertIn("python -m tools.check_nd_format", workflow)

    # closes: #741
    def test_the_workflow_no_longer_globs_the_tree(self):
        """`find . -name "*.nd"` is what swept the virtualenvs. Its absence is
        the assertion, since the module's own tests cover what replaced it."""
        workflow = (_REPO_ROOT / ".github" / "workflows" / "ci.yml").read_text(
            encoding="utf-8"
        )
        self.assertNotIn('find . -name "*.nd"', workflow)


if __name__ == "__main__":
    unittest.main()
