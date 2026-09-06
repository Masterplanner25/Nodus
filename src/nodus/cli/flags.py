"""Flag parsing for the `nodus` CLI, and the refusal of an undeclared flag.

`nodus.cli.commands` names each command's flags once.  This is the one place
that reads that declaration against an argv, so the declaration *binds*.

It did not, before #791.  `_parse_flags` treated any token it did not
recognise as a positional, so an undeclared flag was dropped in silence and
the command ran as though it were not there.  The consequence that made it
`severity:high` rather than a papercut: `--dry-run` is a flag of
`workflow migrate-store`, not of `workflow cleanup`, so

    nodus workflow cleanup --dry-run --force

*deleted run state* while printing a JSON body that reads exactly like a
preview.  A typo'd `--time-limt 30` on `nodus run` is the same defect in its
quiet form -- the script silently keeps the 200 ms default (SCHED-001).

The rule is the one `nodus.tooling.project.validate_manifest` already states
for `nodus.toml` (#490): *a declaration the runtime accepts must bind, or be
refused at the point of declaration.  "Accepted and ignored" is not a
permitted third state.*

There is deliberately **one** parser rather than a check per command.  `--help`
was fixed four times (#1/#2, #268, #345, #353) because each new subcommand had
to remember its own guard; `nodus test` had already grown a second copy of this
function with its flag names written out again beside it.
"""

from __future__ import annotations

import difflib
from typing import Iterable

__all__ = ["CliUsageError", "UnknownFlagError", "parse_flags"]


class CliUsageError(ValueError):
    """The argv is wrong.  Reported as a message, never as a traceback.

    `main()` catches this; a `ValueError` raised here used to escape it, so
    `nodus run --time-limit` printed a Python stack trace at a user.

    The parser knows the flag but not which command it was typed at, so the
    message is composed by the caller that does -- `main()` labels it from the
    table.  `str(exc)` stays useful for anything that catches this without one.
    """

    def message_for(self, label: str) -> str:
        return str(self)


class UnknownFlagError(CliUsageError):
    """A flag the command does not declare (#791)."""

    def __init__(self, flag: str, known: Iterable[str]) -> None:
        self.flag = flag
        self.known = sorted(known)
        super().__init__(f"unknown flag {flag!r}{self._detail()}")

    def _detail(self) -> str:
        """A hint only when there is one, rather than always guessing (#490)."""
        head, sep, value = self.flag.partition("=")
        if sep and head in self.known:
            # `--time-limit=30` is one token and is not declared, so it reaches
            # here.  Before #791 it became the *positional* instead -- so
            # `nodus run --time-limit=30 x.nd` ran a file named for the flag.
            return (
                " -- nodus does not take `--flag=value`; write it as "
                f"`{head} {value}`"
            )
        close = difflib.get_close_matches(self.flag, self.known, n=1, cutoff=0.7)
        return f" -- did you mean {close[0]!r}?" if close else ""

    def message_for(self, label: str) -> str:
        return f"unknown flag {self.flag!r} for {label!r}{self._detail()}"


class MissingFlagValueError(CliUsageError):
    """A flag that takes a value came last."""

    def __init__(self, flag: str) -> None:
        self.flag = flag
        super().__init__(f"flag {flag!r} needs a value")

    def message_for(self, label: str) -> str:
        return f"flag {self.flag!r} for {label!r} needs a value"


def parse_flags(
    args: list[str],
    flags_with_values: set[str],
    flags_no_values: set[str],
) -> tuple[list[str], dict]:
    """Split `args` into positionals and flags, refusing anything undeclared.

    A token starting with `--` that neither set names is an
    `UnknownFlagError`.  A single-dash token is left as a positional: no
    command in the table declares one, and `-h` is handled centrally in
    `main()` before dispatch.
    """
    positional: list[str] = []
    parsed: dict[str, object] = {}
    idx = 0
    while idx < len(args):
        arg = args[idx]
        if arg in flags_no_values:
            parsed[arg] = True
            idx += 1
            continue
        if arg in flags_with_values:
            if idx + 1 >= len(args):
                raise MissingFlagValueError(arg)
            parsed[arg] = args[idx + 1]
            idx += 2
            continue
        if arg.startswith("--"):
            raise UnknownFlagError(arg, flags_with_values | flags_no_values)
        positional.append(arg)
        idx += 1
    return positional, parsed
