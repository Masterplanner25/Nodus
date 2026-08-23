"""`nodus completion <shell>` -- completion scripts generated from the table.

Every word emitted here comes out of :mod:`nodus.cli.commands`, so a command or
flag added to the table is completable without anyone remembering to update a
second list.  That is the whole reason the table had to come first: generating
completion from a 48-arm `if/elif` ladder is not possible, and hand-maintaining
a parallel list is the drift this change set exists to remove.

Hidden commands are deliberately not offered.  They still work when typed --
they are legacy aliases -- but suggesting both `install` and `package-install`
would present two spellings of one thing as if they were different commands.
"""

from __future__ import annotations

from nodus.cli.commands import COMMANDS, Command

SHELLS: tuple[str, ...] = ("bash", "zsh", "fish", "powershell")


class CompletionError(ValueError):
    """Unknown shell."""


def _visible() -> list[Command]:
    return [entry for entry in COMMANDS.values() if not entry.hidden]


def _all_flags(entry: Command) -> list[str]:
    """Every flag a command accepts, including its subcommands'.

    Completion is a suggestion, not a validator: offering a subcommand's flag
    one word early is harmless, while omitting it is the thing users notice.
    """
    flags = set(entry.with_values) | set(entry.no_values)
    for with_values, no_values in entry.subcommands.values():
        flags |= set(with_values) | set(no_values)
    return sorted(flags)


def _subcommands(entry: Command) -> list[str]:
    return sorted(entry.subcommands)


# --------------------------------------------------------------------------
# bash
# --------------------------------------------------------------------------
def _bash() -> str:
    names = " ".join(entry.name for entry in _visible())
    arms = []
    for entry in _visible():
        words = " ".join(_subcommands(entry) + _all_flags(entry))
        if not words:
            continue
        arms.append(f'        {entry.name})\n            words="{words}" ;;')
    arm_text = "\n".join(arms)
    return f"""# nodus completion for bash
# install:  source <(nodus completion bash)
_nodus_complete() {{
    local cur cmd words
    cur="${{COMP_WORDS[COMP_CWORD]}}"
    cmd="${{COMP_WORDS[1]}}"

    if [ "$COMP_CWORD" -eq 1 ]; then
        COMPREPLY=( $(compgen -W "{names}" -- "$cur") )
        return 0
    fi

    words=""
    case "$cmd" in
{arm_text}
    esac

    if [[ "$cur" == -* ]]; then
        COMPREPLY=( $(compgen -W "$words" -- "$cur") )
    else
        # Subcommand names first, then fall back to paths -- most nodus
        # commands take a .nd file as their positional.
        COMPREPLY=( $(compgen -W "$words" -- "$cur") $(compgen -f -- "$cur") )
    fi
    return 0
}}
complete -F _nodus_complete nodus
"""


# --------------------------------------------------------------------------
# zsh
# --------------------------------------------------------------------------
def _zsh_escape(text: str) -> str:
    # ':' separates the value from its description in a _describe spec, and
    # "'" would close the quoted string.
    return text.replace("\\", "\\\\").replace(":", "\\:").replace("'", "'\\''")


def _zsh() -> str:
    specs = "\n".join(
        f"        '{_zsh_escape(entry.name)}:{_zsh_escape(entry.summary)}'"
        for entry in _visible()
    )
    arms = []
    for entry in _visible():
        words = _subcommands(entry) + _all_flags(entry)
        if not words:
            continue
        joined = " ".join(words)
        arms.append(f"        {entry.name})\n            _values 'option' {joined} ;;")
    arm_text = "\n".join(arms)
    return f"""#compdef nodus
# nodus completion for zsh
# install:  nodus completion zsh > "${{fpath[1]}}/_nodus"
_nodus() {{
    local -a commands
    commands=(
{specs}
    )

    if (( CURRENT == 2 )); then
        _describe -t commands 'nodus command' commands
        return
    fi

    case "${{words[2]}}" in
{arm_text}
        *)
            _files ;;
    esac
}}
compdef _nodus nodus
"""


# --------------------------------------------------------------------------
# fish
# --------------------------------------------------------------------------
def _fish_escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace('"', '\\"').replace("$", "\\$")


def _fish() -> str:
    lines = [
        "# nodus completion for fish",
        "# install:  nodus completion fish > ~/.config/fish/completions/nodus.fish",
        "",
        "# Only offer files where a command actually takes one.",
        "complete -c nodus -f",
        "",
    ]
    for entry in _visible():
        lines.append(
            f'complete -c nodus -n "__fish_use_subcommand" '
            f'-a "{entry.name}" -d "{_fish_escape(entry.summary)}"'
        )
    lines.append("")
    for entry in _visible():
        condition = f'__fish_seen_subcommand_from {entry.name}'
        for sub in _subcommands(entry):
            lines.append(
                f'complete -c nodus -n "{condition}" -a "{sub}" -d "{entry.name} {sub}"'
            )
        for flag in _all_flags(entry):
            lines.append(f'complete -c nodus -n "{condition}" -l {flag.lstrip("-")}')
        # A command whose signature names a file should still complete paths.
        if "<file>" in entry.signature or "[file]" in entry.signature or "[path]" in entry.signature:
            lines.append(f'complete -c nodus -n "{condition}" -F')
    lines.append("")
    return "\n".join(lines)


# --------------------------------------------------------------------------
# powershell
# --------------------------------------------------------------------------
def _ps_escape(text: str) -> str:
    return text.replace("'", "''")


def _powershell() -> str:
    command_rows = "\n".join(
        f"        '{_ps_escape(entry.name)}' = '{_ps_escape(entry.summary)}'"
        for entry in _visible()
    )
    flag_rows = []
    for entry in _visible():
        words = _subcommands(entry) + _all_flags(entry)
        if not words:
            continue
        joined = ", ".join(f"'{w}'" for w in words)
        flag_rows.append(f"        '{entry.name}' = @({joined})")
    flag_text = "\n".join(flag_rows)
    return f"""# nodus completion for PowerShell
# install:  nodus completion powershell | Out-String | Invoke-Expression
#           (add that line to $PROFILE to persist)
Register-ArgumentCompleter -Native -CommandName nodus -ScriptBlock {{
    param($wordToComplete, $commandAst, $cursorPosition)

    $commands = @{{
{command_rows}
    }}

    $options = @{{
{flag_text}
    }}

    $tokens = $commandAst.CommandElements | Select-Object -Skip 1 |
        ForEach-Object {{ $_.ToString() }}

    if ($tokens.Count -le 1) {{
        $commands.GetEnumerator() |
            Where-Object {{ $_.Key -like "$wordToComplete*" }} |
            Sort-Object Key |
            ForEach-Object {{
                [System.Management.Automation.CompletionResult]::new(
                    $_.Key, $_.Key, 'ParameterValue', $_.Value)
            }}
        return
    }}

    $verb = $tokens[0]
    if ($options.ContainsKey($verb)) {{
        $options[$verb] |
            Where-Object {{ $_ -like "$wordToComplete*" }} |
            ForEach-Object {{
                [System.Management.Automation.CompletionResult]::new(
                    $_, $_, 'ParameterName', $_)
            }}
    }}
}}
"""


_GENERATORS = {
    "bash": _bash,
    "zsh": _zsh,
    "fish": _fish,
    "powershell": _powershell,
}


def generate(shell: str) -> str:
    """The completion script for `shell`, which must be one of :data:`SHELLS`."""
    try:
        return _GENERATORS[shell]()
    except KeyError:
        raise CompletionError(
            f"unknown shell {shell!r}; expected one of {', '.join(SHELLS)}"
        ) from None
