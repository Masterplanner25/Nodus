"""`--help` must print usage and never run the command (#353).

`--help` used to be each subcommand's own responsibility, so every new subcommand
shipped unguarded and the fixes landed one command at a time — #1/#2 (`check`,
`ast`, `dis`), then #268 (`serve`, `worker`), then #345 (`test`), then the entire
package-manager group. On v4.1.1:

    $ nodus logout --help
    Token removed from ~/.nodus/config.toml     # it performed the logout

    $ nodus publish --help
    FileNotFoundError: ... nodus.toml           # unhandled traceback

`nodus login --help` blocked on stdin, and `install` / `add` / `remove` /
`update` / `deps` / `test` all just ran. `--help` is the flag people type when
they are unsure what a command does, which is exactly when a side effect is least
expected.

`main()` now handles `--help` centrally before any subcommand body runs, so these
tests are table-driven over `KNOWN_COMMANDS` rather than one case per command: a
subcommand added tomorrow is covered without anyone remembering to add a test.

The sweep runs **out of process with a timeout**. Against the unfixed CLI,
`login --help` blocks on input even with stdin at /dev/null, so an in-process
table test would hang the suite instead of failing it.
"""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

_REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(_REPO_ROOT / "src"))  # noqa: E402

from nodus.cli.cli import KNOWN_COMMANDS, _command_help  # noqa: E402

_NODUS_PY = str(_REPO_ROOT / "nodus.py")

_SENTINEL_CONFIG = '[registry]\ntoken = "SENTINEL-TOKEN"\n'

# Runs every command's --help in one interpreter and reports as it goes, so a
# hang still identifies the command that hung.
_SWEEP = """
import io, json, sys
from contextlib import redirect_stdout, redirect_stderr
from nodus.cli.cli import KNOWN_COMMANDS, main

for cmd in sorted(KNOWN_COMMANDS):
    out, err = io.StringIO(), io.StringIO()
    try:
        with redirect_stdout(out), redirect_stderr(err):
            rc = main(["nodus", cmd, sys.argv[1]])
        exc = None
    except BaseException as e:
        rc, exc = None, "%s: %s" % (type(e).__name__, e)
    print("__ROW__" + json.dumps({
        "cmd": cmd, "rc": rc, "exc": exc,
        "stdout": out.getvalue(), "stderr": err.getvalue(),
    }), flush=True)
"""


class HelpGuardTestCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        root = Path(self._tmp.name)
        self.home = root / "home"
        self.cwd = root / "cwd"
        (self.home / ".nodus").mkdir(parents=True)
        self.cwd.mkdir()
        self.config = self.home / ".nodus" / "config.toml"
        self.config.write_text(_SENTINEL_CONFIG, encoding="utf-8")

    def _env(self) -> dict:
        env = dict(os.environ)
        src = str(_REPO_ROOT / "src")
        env["PYTHONPATH"] = src + (
            os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else ""
        )
        # Redirect the registry config away from the real one. Path.home() reads
        # USERPROFILE on Windows and HOME elsewhere.
        env["HOME"] = str(self.home)
        env["USERPROFILE"] = str(self.home)
        return env

    def sweep(self, flag: str = "--help") -> list[dict]:
        try:
            proc = subprocess.run(
                [sys.executable, "-c", _SWEEP, flag],
                capture_output=True, text=True, timeout=120,
                cwd=str(self.cwd), env=self._env(), stdin=subprocess.DEVNULL,
            )
        except subprocess.TimeoutExpired as exc:
            done = [
                json.loads(ln[len("__ROW__"):])["cmd"]
                for ln in (exc.stdout or "").splitlines()
                if ln.startswith("__ROW__")
            ]
            self.fail(
                f"`{flag}` hung. Completed: {done}. "
                f"The next command after those blocked instead of printing usage."
            )
        rows = [
            json.loads(ln[len("__ROW__"):])
            for ln in proc.stdout.splitlines() if ln.startswith("__ROW__")
        ]
        self.assertEqual(
            len(KNOWN_COMMANDS), len(rows),
            f"sweep did not finish (rc={proc.returncode})\n{proc.stdout[-2000:]}\n"
            f"{proc.stderr[-2000:]}",
        )
        return rows


# closes: #353
# closes: #345
class HelpPrintsUsageForEveryCommandTests(HelpGuardTestCase):
    def test_every_command_exits_zero(self):
        bad = [(r["cmd"], r["rc"], r["exc"]) for r in self.sweep() if r["rc"] != 0]
        self.assertEqual([], bad)

    def test_every_command_prints_usage_to_stdout(self):
        bad = [
            (r["cmd"], r["stdout"][:60])
            for r in self.sweep()
            if not r["stdout"].startswith("Usage:")
        ]
        self.assertEqual([], bad)

    def test_no_command_raises(self):
        bad = [(r["cmd"], r["exc"]) for r in self.sweep() if r["exc"] is not None]
        self.assertEqual([], bad)

    def test_short_flag_behaves_the_same(self):
        bad = [
            (r["cmd"], r["rc"], r["exc"])
            for r in self.sweep("-h")
            if r["rc"] != 0 or not r["stdout"].startswith("Usage:")
        ]
        self.assertEqual([], bad)


# closes: #353
class HelpHasNoSideEffectsTests(HelpGuardTestCase):
    def test_logout_help_does_not_delete_the_saved_token(self):
        # The reason this issue is not cosmetic: it deleted a real token.
        proc = subprocess.run(
            [sys.executable, _NODUS_PY, "logout", "--help"],
            capture_output=True, text=True, timeout=60,
            cwd=str(self.cwd), env=self._env(), stdin=subprocess.DEVNULL,
        )
        self.assertEqual(0, proc.returncode, proc.stderr)
        self.assertTrue(proc.stdout.startswith("Usage: nodus logout"), proc.stdout)
        self.assertEqual(_SENTINEL_CONFIG,
                         self.config.read_text(encoding="utf-8"))

    def test_publish_help_does_not_raise_a_traceback(self):
        proc = subprocess.run(
            [sys.executable, _NODUS_PY, "publish", "--help"],
            capture_output=True, text=True, timeout=60,
            cwd=str(self.cwd), env=self._env(), stdin=subprocess.DEVNULL,
        )
        self.assertEqual(0, proc.returncode, proc.stderr)
        self.assertNotIn("Traceback", proc.stderr)

    def test_sweeping_every_command_leaves_the_config_untouched(self):
        self.sweep()
        self.assertEqual(_SENTINEL_CONFIG,
                         self.config.read_text(encoding="utf-8"))

    def test_sweeping_every_command_creates_no_files(self):
        self.sweep()
        self.assertEqual([], sorted(p.name for p in self.cwd.iterdir()))


# closes: #353
class CommandHelpTextTests(unittest.TestCase):
    """The pure half — no subprocess needed, so it is cheap to keep honest."""

    def test_every_known_command_has_usage_text(self):
        missing = [
            cmd for cmd in sorted(KNOWN_COMMANDS)
            if not _command_help(cmd).startswith("Usage: nodus ")
        ]
        self.assertEqual([], missing)

    def test_fallback_help_is_derived_from_the_command_list(self):
        # `profile` has no hand-written entry; its usage and description come
        # from the global help, so the two cannot drift.
        text = _command_help("profile")
        self.assertTrue(text.startswith("Usage: nodus profile <file>"), text)
        self.assertIn("Profile script execution.", text)

    def test_unlisted_command_still_gets_usage(self):
        text = _command_help("workflow-checkpoints")
        self.assertTrue(text.startswith("Usage: nodus workflow-checkpoints"), text)


if __name__ == "__main__":
    unittest.main()
