"""The command surface is data, and stays that way.

`main()` used to declare each command's flags inline in its own dispatch
branch.  That is the shape described in `CLAUDE.md` -- a correct declaration on
one path with siblings free to drift -- and it had drifted: `nodus publish`
documented `--project-root PATH` while its parse set was
`{"--registry", "--registry-token"}`, so the flag was swallowed as a positional
and publish ran against the process CWD.

Two of these tests assert on the *source* of `cli.py` rather than on behaviour,
because a behaviour-only test passes on whichever branch is already correct.
Both were checked against the pre-table tree and fail there.
"""

from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))  # noqa: E402

from nodus.cli import cli as cli_module  # noqa: E402
from nodus.cli.commands import (  # noqa: E402
    COMMANDS,
    GROUP_ORDER,
    KNOWN_COMMANDS,
    _DETAILED_HELP,
    command_summary,
    flags_for,
    render_help,
)

CLI_SOURCE = Path(cli_module.__file__).read_text(encoding="utf-8")

# A flag token as it appears at the head of a help "Options:" line.
_HELP_FLAG = re.compile(r"^\s+(--[a-z0-9-]+)")


class CommandTableSourceTests(unittest.TestCase):
    """Nothing may re-declare a flag set outside the table."""

    def test_dispatch_declares_no_inline_flag_literals(self):
        offenders = []
        for lineno, line in enumerate(CLI_SOURCE.splitlines(), start=1):
            stripped = line.strip()
            if stripped.startswith(("flags_with_values = {", "flags_no_values = {")):
                offenders.append((lineno, stripped))
            elif "_parse_flags(" in line and '{"--' in line:
                offenders.append((lineno, stripped))
        self.assertEqual(
            offenders,
            [],
            "flag sets must come from nodus.cli.commands.flags_for(), not a "
            f"literal in the dispatch branch: {offenders}",
        )

    def test_help_is_not_reconstructed_by_scraping_prose(self):
        """`_command_summary` used to regex-scrape `_render_help()` output.

        The table carries `signature` and `summary` as fields, so the scrape is
        gone and `re` is no longer needed by cli.py at all.
        """
        self.assertNotIn("import re", CLI_SOURCE)


class CommandTableShapeTests(unittest.TestCase):
    def test_known_commands_is_derived_from_the_table(self):
        self.assertEqual(KNOWN_COMMANDS, frozenset(COMMANDS))

    def test_every_entry_keys_itself(self):
        for name, entry in COMMANDS.items():
            self.assertEqual(name, entry.name, f"{name} keyed under the wrong name")

    def test_every_visible_command_has_a_known_group(self):
        for name, entry in COMMANDS.items():
            if entry.hidden:
                self.assertIsNone(entry.group, f"hidden command {name} declares a group")
                continue
            self.assertIn(entry.group, GROUP_ORDER, f"{name} has an unlisted group")

    def test_flags_for_returns_mutable_copies(self):
        """Callers pass these into `_parse_flags`; they must not alias the table."""
        with_values, no_values = flags_for("run")
        with_values.add("--injected")
        no_values.add("--injected")
        again, _ = flags_for("run")
        self.assertNotIn("--injected", again)
        self.assertNotIn("--injected", COMMANDS["run"].with_values)

    def test_subcommand_flags_resolve(self):
        with_values, _ = flags_for("workflow", "cleanup")
        self.assertIn("--retention-seconds", with_values)
        _, no_values = flags_for("workflow", "cleanup")
        self.assertIn("--force", no_values)


def _listing_rows() -> list[tuple[str, str]]:
    """`(signature, summary)` pairs from the group sections of the help.

    Only rows inside a `GROUP_ORDER` heading count -- the trailing "Global
    options" and stability-tier blocks are prose and are not command rows.
    """
    rows: list[tuple[str, str]] = []
    current: str | None = None
    for line in render_help().splitlines():
        if line and not line.startswith(" ") and line.endswith(":"):
            heading = line[:-1]
            current = heading if heading in GROUP_ORDER else None
            continue
        if current is None or not line.startswith("  "):
            continue
        signature, _, summary = line[2:].partition("  ")
        rows.append((signature.strip(), summary.strip()))
    return rows


class HelpProjectionTests(unittest.TestCase):
    def test_listing_contains_every_visible_command_exactly_once(self):
        signatures = [signature for signature, _ in _listing_rows()]
        for name, entry in COMMANDS.items():
            occurrences = signatures.count(entry.signature)
            if entry.hidden:
                self.assertEqual(occurrences, 0, f"hidden {name} appears in help")
            else:
                self.assertEqual(occurrences, 1, f"{name} appears {occurrences}x in help")

    def test_listing_has_no_rows_beyond_the_table(self):
        declared = {e.signature for e in COMMANDS.values() if not e.hidden}
        self.assertEqual({s for s, _ in _listing_rows()}, declared)

    def test_groups_render_in_declared_order(self):
        rendered = render_help().splitlines()
        seen = [line[:-1] for line in rendered if line.endswith(":") and not line.startswith(" ")]
        groups = [g for g in seen if g in GROUP_ORDER]
        self.assertEqual(groups, list(GROUP_ORDER))

    def test_summary_is_none_for_hidden_commands(self):
        """Preserves the behaviour of the help-scraping implementation."""
        self.assertIsNone(command_summary("workflow-run"))
        self.assertIsNotNone(command_summary("run"))

    # closes: #533
    def test_group_commands_have_reachable_detailed_help(self):
        """Regression: `graph`/`workflow` help lived in unreachable branches.

        The central #353 guard runs before any dispatch body, so a command whose
        help sits inside its branch prints the generic stub instead. Any command
        with subcommands needs its help in the table, where the guard reads it.
        """
        stub = "No detailed option help has been written"
        for name, entry in COMMANDS.items():
            if not entry.subcommands:
                continue
            rendered = cli_module._command_help(name)
            self.assertNotIn(stub, rendered, f"{name} falls back to the generic stub")
            for sub in entry.subcommands:
                # A single-subcommand command names it in the usage line rather
                # than a "Subcommands:" section; either way it must be mentioned.
                self.assertIn(sub, rendered, f"{name} help omits subcommand {sub}")

    def test_every_row_keeps_a_column_gap(self):
        """A signature at the column width must not butt against its summary."""
        for signature, summary in _listing_rows():
            self.assertTrue(signature, "empty signature in help listing")
            self.assertTrue(summary, f"no summary rendered for {signature!r}")


class DocumentedFlagsAreParsedTests(unittest.TestCase):
    """Every flag a command's help documents must be a flag it actually parses.

    This is the assertion that catches the `publish --project-root` class of
    bug: help text and parse set maintained separately, with nothing checking
    they agree.
    """

    def _documented_flags(self, help_text: str) -> set[str]:
        flags: set[str] = set()
        in_options = False
        for line in help_text.splitlines():
            if line.strip() == "Options:":
                in_options = True
                continue
            if in_options:
                if line.strip() == "" or not line.startswith(" "):
                    in_options = False
                    continue
                match = _HELP_FLAG.match(line)
                if match:
                    flags.add(match.group(1))
        return flags

    def test_documented_flags_are_declared(self):
        problems = []
        for name, help_text in _DETAILED_HELP.items():
            entry = COMMANDS.get(name)
            if entry is None:
                problems.append(f"{name}: has help but is not in the table")
                continue
            declared = set(entry.with_values) | set(entry.no_values)
            for sub_with, sub_no in entry.subcommands.values():
                declared |= set(sub_with) | set(sub_no)
            missing = self._documented_flags(help_text) - declared
            if missing:
                problems.append(f"{name}: documents but does not parse {sorted(missing)}")
        self.assertEqual(problems, [], "\n".join(problems))

    # closes: #532
    def test_publish_parses_the_project_root_it_documents(self):
        """Regression: the flag was documented, unparsed, and published the CWD."""
        with_values, no_values = flags_for("publish")
        self.assertIn("--project-root", with_values)
        positional, parsed = cli_module._parse_flags(
            ["--project-root", "/tmp/proj"], with_values, no_values
        )
        self.assertEqual(positional, [])
        self.assertEqual(parsed.get("--project-root"), "/tmp/proj")


if __name__ == "__main__":
    unittest.main()
