"""Every CLI flag the release-claims probes pass is one the command declares (#811).

`tests/eval/release_claims_probe.py` is the Gate 10b harness. At the 5.12.0 cut a
probe went red on a command that works correctly:

    probe_graph_does_not_execute -> cli(["nodus", "graph", str(script), "--allow-paths", td])

`nodus graph` has never declared `--allow-paths`. It was swallowed as a
positional and did nothing, harmlessly, until #791 made an undeclared flag an
error — at which point a correct command started failing a probe. **The identical
line was fixed in `tests/test_graph_static_plan.py` when #791 landed**, because
CI runs tests and did not run the probes.

This is the static half of the fix, and the cheaper one: it needs no wheel, no
venv and no subprocess, and it fails with the command and the flag rather than
with a probe's assertion error two layers down. The behavioural half — running
the probes in CI against the built wheel — is the `Release-claims probes` step in
`.github/workflows/ci.yml`.

It is the same relationship `DocumentedFlagsAreParsedTests` in
`tests/test_cli_command_table.py` already checks for help text: a declaration
that binds. The probes were the last CLI consumer in the tree not subject to it.

**Both invocation forms are covered**, because there are exactly two and a check
that knew about one would be the shape this repo keeps filing issues about: the
in-process `cli([...])` helper (9 sites) and one `subprocess.run` of
`python -m nodus` (1 site). `test_every_invocation_site_is_understood` fails if a
third appears or the count drifts, so a new spelling cannot slip past unchecked.
"""

import ast
import pathlib
import sys
import unittest

REPO = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))  # noqa: E402

from nodus.cli.commands import COMMANDS, flags_for  # noqa: E402

PROBE = REPO / "tests" / "eval" / "release_claims_probe.py"

#: `--help`/`-h` is handled centrally in `main()` before any subcommand body
#: runs (#353), so every command takes it and no command declares it.
UNIVERSAL = {"--help", "-h"}


def _literal_words(node: ast.List) -> list[str | None]:
    """String constants in a list literal; None for anything computed."""
    out: list[str | None] = []
    for element in node.elts:
        if isinstance(element, ast.Constant) and isinstance(element.value, str):
            out.append(element.value)
        else:
            out.append(None)
    return out


def invocation_sites() -> list[tuple[int, str, list[str]]]:
    """(line, form, argv words) for every CLI invocation with a literal argv."""
    tree = ast.parse(PROBE.read_text(encoding="utf-8"))
    sites: list[tuple[int, str, list[str]]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue

        # Form 1: the in-process helper, `cli(["nodus", ...])`.
        if (
            isinstance(node.func, ast.Name)
            and node.func.id == "cli"
            and node.args
            and isinstance(node.args[0], ast.List)
        ):
            words = [w for w in _literal_words(node.args[0]) if w is not None]
            sites.append((node.lineno, "cli", words))
            continue

        # Form 2: `subprocess.run([sys.executable, "-m", "nodus", ...])`.
        if (
            isinstance(node.func, ast.Attribute)
            and node.func.attr == "run"
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id == "subprocess"
            and node.args
            and isinstance(node.args[0], ast.List)
        ):
            words = [w for w in _literal_words(node.args[0]) if w is not None]
            if "nodus" in words:
                sites.append((node.lineno, "subprocess", words))
    return sites


def _argv_after_program(form: str, words: list[str]) -> list[str]:
    """Drop everything up to and including the program, leaving command + args."""
    if form == "cli":
        return words[1:] if words and words[0] == "nodus" else words
    index = words.index("nodus")
    return words[index + 1 :]


def undeclared_flags() -> list[str]:
    problems: list[str] = []
    for lineno, form, words in invocation_sites():
        argv = _argv_after_program(form, words)
        if not argv or argv[0].startswith("-"):
            # `nodus --help` — no command, nothing to resolve against.
            continue
        command = argv[0]
        if command not in COMMANDS:
            problems.append(f"{PROBE.name}:{lineno}: unknown command {command!r}")
            continue

        entry = COMMANDS[command]
        subcommands = getattr(entry, "subcommands", None) or {}
        subcommand = None
        if len(argv) > 1 and not argv[1].startswith("-") and argv[1] in subcommands:
            subcommand = argv[1]

        with_values, no_values = flags_for(command, subcommand)
        declared = with_values | no_values | UNIVERSAL

        where = command if subcommand is None else f"{command} {subcommand}"
        for word in argv[1:]:
            if not word.startswith("-"):
                continue
            name = word.split("=", 1)[0]
            if name not in declared:
                problems.append(
                    f"{PROBE.name}:{lineno}: `nodus {where}` does not declare {name}"
                )
    return problems


class ProbeFlagsAreDeclaredTests(unittest.TestCase):
    # closes: #811
    def test_no_probe_passes_a_flag_its_command_does_not_take(self):
        problems = undeclared_flags()
        self.assertEqual(
            problems,
            [],
            "A release probe passes a flag the command does not declare. Since "
            "#791 that is an error, so the probe fails on a command that works:\n  "
            + "\n  ".join(problems),
        )

    def test_every_invocation_site_is_understood(self):
        """A third invocation form must be added here, not silently unchecked.

        The count is asserted rather than only the forms: a new `cli([...])` call
        is covered by construction, but a probe that builds its argv in a
        variable would parse to nothing and be invisible. If this number moves,
        confirm the new site is one of the two forms before updating it.
        """
        sites = invocation_sites()
        forms = {form for _, form, _ in sites}
        self.assertEqual(forms, {"cli", "subprocess"})
        self.assertEqual(
            len(sites),
            10,
            "the probe's CLI invocation sites changed; check the new one is a "
            "literal argv this test can read before updating the count",
        )

    def test_both_forms_are_actually_present(self):
        """Guards the other direction: a parser matching nothing passes vacuously."""
        sites = invocation_sites()
        self.assertGreaterEqual(sum(1 for _, f, _ in sites if f == "cli"), 8)
        self.assertEqual(sum(1 for _, f, _ in sites if f == "subprocess"), 1)


class CIRunsTheProbesTests(unittest.TestCase):
    """The behavioural half of #811, asserted where it can regress silently.

    Same shape as `test_nd_format_gate.py`'s assertion that CI still calls
    `check_nd_format`: the workflow is the only place this runs, and deleting a
    step is invisible to every other test in the tree.
    """

    def _workflow(self) -> str:
        return (REPO / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")

    def _require(self, needle: str, why: str) -> None:
        # `assertTrue` rather than `assertIn`, which dumps the whole workflow
        # into the failure message and buries the sentence that says what broke.
        self.assertTrue(needle in self._workflow(), f"ci.yml no longer has {needle!r}: {why}")

    def test_ci_runs_the_release_claims_probes(self):
        self._require(
            "release_claims_probe.py",
            "the probes are release-only again, which is what #811 was about",
        )

    def test_ci_runs_them_against_an_installed_package(self):
        """`--require-installed` is the whole point of running them there.

        Without it the run resolves `nodus` through the repo-root shim and
        validates the **source tree** while reporting on the wheel — the trap
        that shipped 5.0.3 past 32 green probes and recurred at 5.5.0 and 5.6.0.
        """
        self._require(
            "--require-installed",
            "the CI probe run would validate the source tree and say it checked the wheel",
        )

    def test_ci_runs_them_from_outside_the_repo(self):
        self._require(
            "cd /tmp",
            "a probe run whose CWD is the checkout resolves `nodus` to src/ via the shim",
        )


class TheCheckCanFireTests(unittest.TestCase):
    """#815's lesson: a negative assertion that cannot fail is worse than none."""

    def _problems_for(self, source: str) -> list[str]:
        import tempfile
        from unittest import mock

        with tempfile.TemporaryDirectory() as td:
            fake = pathlib.Path(td) / "probe.py"
            fake.write_text(source, encoding="utf-8")
            with mock.patch.dict(globals(), {"PROBE": fake}):
                return undeclared_flags()

    def test_the_historical_bug_would_be_caught(self):
        """The exact line from the 5.12.0 cut."""
        problems = self._problems_for(
            'cli(["nodus", "graph", str(script), "--allow-paths", td])\n'
        )
        self.assertEqual(len(problems), 1)
        self.assertIn("`nodus graph` does not declare --allow-paths", problems[0])

    def test_the_equals_form_is_caught_too(self):
        problems = self._problems_for('cli(["nodus", "graph", "--allow-paths=/tmp"])\n')
        self.assertEqual(len(problems), 1)
        self.assertIn("--allow-paths", problems[0])

    def test_a_subcommand_s_own_flags_resolve(self):
        """`workflow migrate-store --dry-run` is declared; `workflow cleanup` is not.

        The pair that #791 was about, and the reason the subcommand has to be
        resolved rather than the flags checked against the parent command.
        """
        self.assertEqual(
            self._problems_for(
                'cli(["nodus", "workflow", "migrate-store", "--dry-run"])\n'
            ),
            [],
        )
        problems = self._problems_for(
            'cli(["nodus", "workflow", "cleanup", "--dry-run"])\n'
        )
        self.assertEqual(len(problems), 1)
        self.assertIn("workflow cleanup", problems[0])

    def test_help_is_allowed_everywhere(self):
        self.assertEqual(self._problems_for('cli(["nodus", "graph", "--help"])\n'), [])

    def test_a_declared_flag_is_not_reported(self):
        """The control. Without it every case above passes for a broken parser."""
        self.assertEqual(
            self._problems_for('cli(["nodus", "graph", "show", "x", "--format", "dot"])\n'),
            [],
        )

    def test_the_subprocess_form_is_checked_as_well(self):
        problems = self._problems_for(
            'subprocess.run([sys.executable, "-m", "nodus", "run", "wf.nd", "--nope"])\n'
        )
        self.assertEqual(len(problems), 1)
        self.assertIn("--nope", problems[0])


if __name__ == "__main__":
    unittest.main()
