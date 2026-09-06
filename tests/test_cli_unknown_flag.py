"""An undeclared flag is refused, for every command (#791).

`nodus.cli.commands` declared each command's flag set correctly and nothing
consulted the declaration at dispatch, so an unknown flag was dropped in
silence.  The consequence: `--dry-run` belongs to `workflow migrate-store`,
not to `workflow cleanup`, so `nodus workflow cleanup --dry-run --force`
*deleted* run state while printing a body that reads like a preview.

`CommandCoverageTests` is the one that matters.  It drives off `COMMANDS`
rather than naming commands, so a command added later cannot ship unguarded --
which is exactly how `--help` had to be fixed four times (#1/#2, #268, #345,
#353) before it was made central.
"""

from __future__ import annotations

import io
import sys
import unittest
from contextlib import redirect_stderr
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))  # noqa: E402

from nodus.cli import cli as cli_module  # noqa: E402
from nodus.cli.commands import COMMANDS, flags_for  # noqa: E402
from nodus.cli.flags import (  # noqa: E402
    MissingFlagValueError,
    UnknownFlagError,
    parse_flags,
)

# Not close to any real flag, so no command can declare it and `difflib`
# cannot offer it as a suggestion for something else.
UNDECLARED = "--zzz-not-a-flag"


def _run(argv: list[str]) -> tuple[int, str]:
    buffer = io.StringIO()
    with redirect_stderr(buffer):
        code = cli_module.main(["nodus", *argv])
    return code, buffer.getvalue()


class ParserTests(unittest.TestCase):
    def test_an_undeclared_flag_is_refused(self):
        with self.assertRaises(UnknownFlagError):
            parse_flags([UNDECLARED], set(), set())

    def test_a_declared_flag_still_parses(self):
        positional, parsed = parse_flags(
            ["file.nd", "--time-limit", "5"], *flags_for("run")
        )
        self.assertEqual(positional, ["file.nd"])
        self.assertEqual(parsed["--time-limit"], "5")

    def test_a_flag_value_may_itself_look_like_a_flag(self):
        """Values are taken by position, so `--filter --x` is a value."""
        _, parsed = parse_flags(["--filter", "--x"], *flags_for("test"))
        self.assertEqual(parsed["--filter"], "--x")

    def test_a_single_dash_token_is_still_positional(self):
        """No command declares one, and `-h` is handled before dispatch."""
        positional, _ = parse_flags(["-5"], set(), set())
        self.assertEqual(positional, ["-5"])

    def test_a_missing_value_is_a_usage_error_not_a_bare_value_error(self):
        with self.assertRaises(MissingFlagValueError):
            parse_flags(["--time-limit"], *flags_for("run"))


class MessageTests(unittest.TestCase):
    def test_a_near_miss_is_suggested(self):
        error = UnknownFlagError("--forse", {"--force", "--path"})
        self.assertIn("did you mean '--force'?", error.message_for("nodus x"))

    def test_a_distant_flag_gets_no_invented_suggestion(self):
        """#490's rule: a hint only when one is actually close."""
        error = UnknownFlagError(UNDECLARED, {"--force", "--path"})
        self.assertNotIn("did you mean", error.message_for("nodus x"))

    def test_equals_syntax_names_the_flag_it_meant(self):
        """`--time-limit=30` used to be swallowed as the *positional*."""
        error = UnknownFlagError("--time-limit=30", {"--time-limit"})
        self.assertIn("`--time-limit 30`", error.message_for("nodus run"))

    def test_the_message_names_the_subcommand_not_just_the_command(self):
        code, stderr = _run(["workflow", "cleanup", UNDECLARED])
        self.assertEqual(code, 1)
        self.assertIn("nodus workflow cleanup", stderr)


class DryRunTests(unittest.TestCase):
    """The reported bug, verbatim."""

    # closes: #791
    def test_cleanup_refuses_dry_run_rather_than_deleting(self):
        code, stderr = _run(["workflow", "cleanup", "--dry-run", "--force"])
        self.assertEqual(code, 1)
        self.assertIn("--dry-run", stderr)
        self.assertIn("unknown flag", stderr)

    def test_migrate_store_still_takes_dry_run(self):
        """The flag is real -- it belongs to the neighbouring subcommand."""
        _, no_values = flags_for("workflow", "migrate-store")
        self.assertIn("--dry-run", no_values)


class UsageErrorsAreNotTracebacks(unittest.TestCase):
    def test_a_missing_value_prints_a_message_and_exits_one(self):
        """`nodus run --time-limit` used to raise out of `main()`."""
        code, stderr = _run(["run", "--time-limit"])
        self.assertEqual(code, 1)
        self.assertIn("needs a value", stderr)
        self.assertNotIn("Traceback", stderr)


class CommandCoverageTests(unittest.TestCase):
    """One check for every command, or it recurs per-command like `--help`."""

    def _targets(self):
        """`(label, argv_prefix)` for every command and subcommand."""
        for name, entry in COMMANDS.items():
            if entry.subcommands:
                for sub in entry.subcommands:
                    yield f"{name} {sub}", [name, sub]
            else:
                yield name, [name]

    def test_every_command_refuses_an_undeclared_flag(self):
        survivors = []
        for label, prefix in self._targets():
            code, stderr = _run([*prefix, UNDECLARED])
            if code != 1 or "unknown flag" not in stderr:
                survivors.append((label, code, stderr.strip()[:120]))
        self.assertEqual(
            survivors,
            [],
            "these accepted an undeclared flag instead of refusing it: "
            f"{survivors}",
        )

    def test_no_command_reaches_its_body_before_the_refusal(self):
        """A refusal after the work has run is not a refusal.

        `workflow cleanup` is the case that proves it: the deletion happened
        and *then* the output was printed, so a check anywhere but before the
        body would still have destroyed state.
        """
        code, stderr = _run(["workflow", "cleanup", UNDECLARED, "--force"])
        self.assertEqual(code, 1)
        self.assertEqual(stderr.count("\n"), 2, stderr)
        self.assertNotIn("removed", stderr)


class NoSecondParserTests(unittest.TestCase):
    """The flag names live in the table, and the parser in one module.

    A source assertion, because a behaviour test passes on whichever copy is
    already correct.  `nodus/testing/cli.py` held a second `_parse_flags` with
    `nodus test`'s flag names written out beside it; they agreed with the
    table, and the copy silently accepted an undeclared flag.
    """

    SOURCES = (
        Path(cli_module.__file__),
        Path(cli_module.__file__).parent.parent / "testing" / "cli.py",
    )

    def test_no_module_defines_its_own_flag_parser(self):
        offenders = [
            str(path)
            for path in self.SOURCES
            if "def _parse_flags(" in path.read_text(encoding="utf-8")
        ]
        self.assertEqual(
            offenders,
            [],
            f"a second flag parser; use nodus.cli.flags.parse_flags: {offenders}",
        )

    def test_the_test_command_parses_from_the_table(self):
        source = (
            Path(cli_module.__file__).parent.parent / "testing" / "cli.py"
        ).read_text(encoding="utf-8")
        self.assertIn('flags_for("test")', source)
        # The reads (`flags.get("--coverage-min")`) stay; the *declaration*
        # must not come back.
        self.assertNotIn("flags_with_values = {", source)
        self.assertNotIn("flags_no_values = {", source)


if __name__ == "__main__":
    unittest.main()
