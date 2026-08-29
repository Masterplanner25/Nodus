"""`nodus completion <shell>` -- scripts generated from the command table.

Coverage, stated plainly (#536):

    bash        structure + syntax + completes candidates
    fish        structure + loads + completes candidates
    powershell  structure + syntax + completes candidates
    zsh         structure + syntax + loads and defines the completer

Every execution class is guarded on the shell being present, so this file still
passes on a machine with none of them — the structural assertions are what runs
there, and they are not redundant: they catch the failure that actually bites,
an unescaped separator in a summary containing `(`, `)` or `|`, on all four
shells at once. **Do not delete them when adding execution coverage.**

CI installs `zsh` and `fish` (see `.github/workflows/ci.yml`) so their classes
run there; a developer box without them skips those and keeps the rest.

One gap remains and is deliberate: **zsh is not driven through an actual
completion.** It has no non-interactive entry point comparable to fish's
`complete -C`, and doing it properly needs a `zpty` harness — a large amount of
fragile machinery for one assertion. What is asserted instead is that the script
loads under a real `compinit` and defines `_nodus`, which is what a `compdef`
arity error or an unbalanced `_arguments` would break.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))  # noqa: E402

from nodus.cli.commands import COMMANDS  # noqa: E402
from nodus.cli.completion import SHELLS, CompletionError, generate  # noqa: E402

VISIBLE = [e for e in COMMANDS.values() if not e.hidden]
HIDDEN = [e for e in COMMANDS.values() if e.hidden]


class EveryShellTests(unittest.TestCase):
    # closes: #536
    def test_every_emitted_shell_has_an_execution_class(self):
        """Every shell the CLI emits must be executed somewhere, not just parsed.

        This is the regression guard for #536 itself. Structure-only coverage is
        what let two of four shells ship unverified for a whole release, and the
        failure was **silent** — the suite was green the entire time. A fifth
        shell added to `SHELLS` with structural assertions only would repeat it
        exactly, so this fails until that shell has an execution class.

        It runs unguarded, unlike the execution classes it checks for: the point
        is to notice a *missing* class, which cannot depend on whether the shell
        that class needs happens to be installed.
        """
        module = sys.modules[__name__]
        classes = {
            name.lower()
            for name, obj in vars(module).items()
            if isinstance(obj, type) and name.endswith("ExecutionTests")
        }
        missing = [
            shell for shell in SHELLS
            if f"{shell}executiontests" not in classes
        ]
        self.assertEqual(
            missing, [],
            f"these shells are emitted but never executed: {missing}. "
            f"Add a <Shell>ExecutionTests class, guarded on the shell being "
            f"present, and install the shell in CI.",
        )

    def test_every_declared_shell_generates(self):
        for shell in SHELLS:
            script = generate(shell)
            self.assertTrue(script.strip(), f"{shell} generated an empty script")

    def test_unknown_shell_is_rejected(self):
        with self.assertRaises(CompletionError):
            generate("csh")

    def test_every_visible_command_is_offered(self):
        for shell in SHELLS:
            script = generate(shell)
            for entry in VISIBLE:
                self.assertIn(
                    entry.name, script, f"{entry.name} missing from {shell} completion"
                )

    def test_hidden_commands_are_not_offered(self):
        """Legacy aliases still work when typed; suggesting them is noise."""
        for shell in SHELLS:
            script = generate(shell)
            for entry in HIDDEN:
                self.assertNotIn(
                    f'"{entry.name}"', script, f"hidden {entry.name} offered in {shell}"
                )
                self.assertNotIn(f"'{entry.name}'", script)

    def test_subcommands_are_offered(self):
        for shell in SHELLS:
            script = generate(shell)
            self.assertIn("dead-letters", script, f"{shell} omits workflow subcommands")
            self.assertIn("migrate-state", script)

    def test_flags_are_offered(self):
        for shell in SHELLS:
            script = generate(shell)
            self.assertIn("trace-scheduler", script, f"{shell} omits run flags")
            self.assertIn("retention-seconds", script, f"{shell} omits subcommand flags")

    def test_no_unsubstituted_placeholders(self):
        for shell in SHELLS:
            script = generate(shell)
            self.assertNotIn("{}", script, f"{shell} has an empty format slot")
            self.assertNotIn("@@", script)


class QuotingTests(unittest.TestCase):
    """Summaries contain `(`, `)`, `|`, `*` and `.` -- they must not break out."""

    def test_zsh_escapes_the_description_separator(self):
        script = generate("zsh")
        # `completion <shell>`'s summary is the one with pipes and parens.
        self.assertIn("bash|zsh|fish|powershell", script)
        for line in script.splitlines():
            stripped = line.strip()
            if not (stripped.startswith("'") and stripped.endswith("'")):
                continue
            body = stripped[1:-1]
            # Exactly one unescaped ':' -- the name/description separator.
            unescaped = sum(
                1
                for i, ch in enumerate(body)
                if ch == ":" and (i == 0 or body[i - 1] != "\\")
            )
            self.assertEqual(unescaped, 1, f"bad zsh spec quoting: {line!r}")

    def test_fish_descriptions_are_double_quoted_and_escaped(self):
        for line in generate("fish").splitlines():
            if "-d " not in line:
                continue
            description = line.split("-d ", 1)[1].strip()
            self.assertTrue(description.startswith('"'), line)
            self.assertTrue(description.endswith('"'), line)
            inner = description[1:-1]
            unescaped = sum(
                1
                for i, ch in enumerate(inner)
                if ch == '"' and (i == 0 or inner[i - 1] != "\\")
            )
            self.assertEqual(unescaped, 0, f"unescaped quote in fish line: {line!r}")

    def test_powershell_doubles_single_quotes(self):
        script = generate("powershell")
        for line in script.splitlines():
            if "=" not in line or "'" not in line:
                continue
            # An odd number of quotes means one is unbalanced.
            self.assertEqual(line.count("'") % 2, 0, f"unbalanced quote: {line!r}")


@unittest.skipIf(shutil.which("bash") is None, "bash not available")
class BashExecutionTests(unittest.TestCase):
    def _bash(self, args: list[str], stdin: str):
        """Run bash with the script on stdin rather than as a path.

        Two Windows hazards avoided here, both of which made this test lie
        before: `shutil.which("bash")` can resolve to WSL, which cannot see a
        `C:\\...` temp file at all; and `text=True` would encode the script
        with CRLF endings, which bash rejects outright. Bytes in, bytes out.
        """
        result = subprocess.run(
            ["bash", *args],
            input=stdin.encode("utf-8"),
            capture_output=True,
            timeout=30,
        )
        return subprocess.CompletedProcess(
            result.args,
            result.returncode,
            result.stdout.decode("utf-8", "replace"),
            result.stderr.decode("utf-8", "replace"),
        )

    def test_bash_script_is_valid_syntax(self):
        result = self._bash(["-n"], generate("bash"))
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_bash_completes_a_command_prefix(self):
        driver = (
            generate("bash")
            + "\nCOMP_WORDS=(nodus wo); COMP_CWORD=1; _nodus_complete\n"
            'printf "%s\\n" "${COMPREPLY[@]}"\n'
        )
        result = self._bash(["-s"], driver)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("workflow", result.stdout)
        self.assertIn("worker", result.stdout)

    def test_bash_completes_a_subcommand_flag(self):
        driver = (
            generate("bash")
            + "\nCOMP_WORDS=(nodus graph --for); COMP_CWORD=2; _nodus_complete\n"
            'printf "%s\\n" "${COMPREPLY[@]}"\n'
        )
        result = self._bash(["-s"], driver)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("--format", result.stdout)

    def test_bash_completes_a_workflow_subcommand(self):
        driver = (
            generate("bash")
            + "\nCOMP_WORDS=(nodus workflow dead); COMP_CWORD=2; _nodus_complete\n"
            'printf "%s\\n" "${COMPREPLY[@]}"\n'
        )
        result = self._bash(["-s"], driver)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("dead-letters", result.stdout)


@unittest.skipIf(shutil.which("zsh") is None, "zsh not available")
class ZshExecutionTests(unittest.TestCase):
    """zsh loads the script and defines the completer (#536).

    Sourcing alone is not enough to prove much, but it is not nothing: the file
    ends with `compdef _nodus nodus`, which fails outright unless the completion
    system is initialised — so this exercises `compinit` + the real `#compdef`
    header, and a `compdef` arity error or an unbalanced `_arguments` cannot pass.

    **Driving an actual completion is deliberately not attempted.** zsh has no
    non-interactive completion entry point comparable to fish's `complete -C`;
    doing it properly needs a pty harness (`zpty`), which is a large amount of
    fragile machinery for one assertion. Stated rather than silently skipped, so
    the coverage table above stays honest.
    """

    def _zsh(self, body: str):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            script = root / "_nodus"
            script.write_text(generate("zsh"), encoding="utf-8")
            return subprocess.run(
                ["zsh", "-c", body.format(script=script, dump=root / "zcompdump")],
                capture_output=True,
                text=True,
                timeout=120,
            )

    def test_zsh_script_is_valid_syntax(self):
        result = self._zsh("zsh -n {script}")
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_zsh_loads_and_defines_the_completer(self):
        result = self._zsh(
            "autoload -Uz compinit && compinit -u -d {dump} && "
            "source {script} && "
            "typeset -f _nodus >/dev/null && echo DEFINED"
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("DEFINED", result.stdout)


@unittest.skipIf(shutil.which("fish") is None, "fish not available")
class FishExecutionTests(unittest.TestCase):
    """fish loads the script and completes from it (#536).

    fish is the one non-bash shell with a clean non-interactive completion
    entry point — `complete -C <line>` returns exactly what a Tab press would —
    so this asserts on candidates rather than on loading.
    """

    def _fish(self, body: str):
        with tempfile.TemporaryDirectory() as td:
            script = Path(td) / "nodus.fish"
            script.write_text(generate("fish"), encoding="utf-8")
            return subprocess.run(
                ["fish", "-c", body.format(script=script)],
                capture_output=True,
                text=True,
                timeout=120,
            )

    def _candidates(self, line: str) -> list[str]:
        result = self._fish("source {script}; complete -C '" + line + "'")
        self.assertEqual(result.returncode, 0, result.stderr)
        # `complete -C` prints "candidate<TAB>description".
        return [row.split("\t", 1)[0].strip() for row in result.stdout.splitlines() if row.strip()]

    def test_fish_script_loads(self):
        result = self._fish("source {script}; echo LOADED")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("LOADED", result.stdout)

    def test_fish_completes_a_command_prefix(self):
        candidates = self._candidates("nodus wo")
        self.assertIn("workflow", candidates)
        self.assertIn("worker", candidates)

    def test_fish_completes_a_subcommand(self):
        self.assertIn("dead-letters", self._candidates("nodus workflow dead"))


def _powershell() -> str | None:
    """pwsh if present, else Windows PowerShell. Either can host the completer."""
    return shutil.which("pwsh") or shutil.which("powershell")


#: Parses the generated script, then optionally drives one completion through
#: `TabExpansion2` — the entry point PowerShell itself uses for a Tab press, so
#: this exercises the same path a user does rather than invoking the registered
#: script block directly.
_PS_DRIVER = r"""
param([string]$ScriptPath, [string]$Line)
$errors = $null
$tokens = $null
$null = [System.Management.Automation.Language.Parser]::ParseFile(
    $ScriptPath, [ref]$tokens, [ref]$errors)
if ($errors -and $errors.Count -gt 0) {
    Write-Output "PARSE_ERRORS=$($errors.Count)"
    foreach ($e in $errors) { Write-Output "  $($e.Message)" }
    exit 1
}
Write-Output 'PARSE_OK'
if (-not $Line) { exit 0 }
. $ScriptPath
$res = TabExpansion2 -inputScript $Line -cursorColumn $Line.Length
foreach ($m in $res.CompletionMatches) { Write-Output "M:$($m.CompletionText)" }
"""


@unittest.skipIf(_powershell() is None, "no powershell available")
class PowerShellExecutionTests(unittest.TestCase):
    """Syntax and behaviour for the PowerShell script (#536).

    This verification existed before — done by hand during #534 and written down
    nowhere — so it did not survive the session that produced it. A hand-run
    check is not coverage. It also closes the hole where a machine without
    `bash` ran no executable check at all, since that was the only such class.
    """

    def _complete(self, line: str | None):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            completion = root / "nodus_completion.ps1"
            driver = root / "driver.ps1"
            # utf-8-sig: Windows PowerShell 5.1 reads a BOM-less UTF-8 file as
            # the ANSI code page, so a non-ASCII character in a command summary
            # would be mangled before the parser ever saw it — and the test
            # would blame the emitter.
            completion.write_text(generate("powershell"), encoding="utf-8-sig")
            driver.write_text(_PS_DRIVER, encoding="utf-8-sig")
            args = [
                _powershell(),
                "-NoProfile",
                "-NonInteractive",
                "-ExecutionPolicy", "Bypass",
                "-File", str(driver),
                "-ScriptPath", str(completion),
            ]
            if line is not None:
                args += ["-Line", line]
            return subprocess.run(args, capture_output=True, text=True, timeout=120)

    def _matches(self, line: str) -> list[str]:
        result = self._complete(line)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return [
            row[2:].strip()
            for row in result.stdout.splitlines()
            if row.startswith("M:")
        ]

    def test_powershell_script_is_valid_syntax(self):
        result = self._complete(None)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("PARSE_OK", result.stdout)

    def test_powershell_completes_a_command_prefix(self):
        matches = self._matches("nodus wo")
        self.assertIn("workflow", matches)
        self.assertIn("worker", matches)

    def test_powershell_completes_a_subcommand(self):
        self.assertIn("dead-letters", self._matches("nodus workflow dead"))

    def test_powershell_completes_a_flag(self):
        self.assertIn("--format", self._matches("nodus graph --for"))

    def test_powershell_offers_no_hidden_command(self):
        """The emitter filters hidden commands; prove it survives to the shell."""
        matches = self._matches("nodus ")
        for entry in HIDDEN:
            self.assertNotIn(entry.name, matches)


class CliTests(unittest.TestCase):
    def test_command_requires_a_shell_argument(self):
        from nodus.cli.cli import main

        self.assertEqual(main(["nodus", "completion"]), 1)

    def test_unknown_shell_exits_nonzero(self):
        from nodus.cli.cli import main

        self.assertEqual(main(["nodus", "completion", "csh"]), 1)

    def test_emitted_script_keeps_lf_line_endings(self):
        """`nodus completion bash > f` must not produce a CRLF file.

        bash rejects one outright: `syntax error near unexpected token $'{\\r'`.
        Text-mode stdout on Windows would introduce exactly that, so the
        command writes bytes.
        """
        from nodus.cli.cli import main

        for shell in SHELLS:
            with tempfile.TemporaryDirectory() as tmp:
                target = Path(tmp) / f"out.{shell}"
                with open(target, "wb") as handle:
                    stdout, sys.stdout = sys.stdout, _ByteSink(handle)
                    try:
                        code = main(["nodus", "completion", shell])
                    finally:
                        sys.stdout = stdout
                self.assertEqual(code, 0)
                raw = target.read_bytes()
                self.assertNotIn(b"\r\n", raw, f"{shell} script written with CRLF")
                self.assertIn(b"\n", raw)


class _ByteSink:
    """Minimal stdout stand-in exposing a real `.buffer`, like a piped stdout."""

    def __init__(self, handle):
        self.buffer = handle

    def write(self, text: str) -> int:  # pragma: no cover - buffer path is used
        return self.buffer.write(text.encode("utf-8"))

    def flush(self) -> None:
        self.buffer.flush()


if __name__ == "__main__":
    unittest.main()
