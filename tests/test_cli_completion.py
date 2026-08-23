"""`nodus completion <shell>` -- scripts generated from the command table.

Coverage note, stated plainly (tracked in **#536**):

    bash        syntax + behaviour, in this suite
    powershell  syntax + behaviour, BY HAND ONLY -- not asserted here
    zsh         structure and quoting only
    fish        structure and quoting only

`zsh` and `fish` are not installed on the development or CI machines. The
structural assertions catch the failure that actually bites -- an unescaped
separator in a summary containing `(`, `)` or `|` -- but nothing here proves
either script loads. And because the only execution class is guarded on `bash`,
a machine without it verifies nothing executable at all.

Saying so is better than implying four equally verified shells.
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
