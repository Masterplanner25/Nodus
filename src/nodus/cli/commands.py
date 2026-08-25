"""The nodus command surface, as data.

`main()` in :mod:`nodus.cli.cli` used to declare each command's flags inline in
its own dispatch branch -- 47 `_parse_flags(...)` call sites, several with the
flag names written as bare literals at the call.  That is the recurring shape
described in `CLAUDE.md`: a correct declaration on one path, with siblings free
to drift.  It had already drifted.  `nodus publish` documented
`--project-root PATH` in its help text while its parse set was
`{"--registry", "--registry-token"}`, so the flag was silently swallowed as a
positional and publish always ran against `os.getcwd()` -- against a *registry*.

So the set is named once, here, and everything else is a projection of it:

* the global `nodus --help` listing        -> `render_help()`
* per-command `nodus <cmd> --help`         -> `command_help()`
* flag parsing in every dispatch branch    -> `flags_for()`
* the `--help` guard registry (#353)       -> `KNOWN_COMMANDS`
* shell completion                         -> `nodus.cli.completion`

`tests/test_cli_command_table.py` asserts on the *source* of `cli.py` -- that no
dispatch branch declares its own flag literals again -- because a
behaviour-only test passes on whichever branch is already correct.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping

# Group headings in `nodus --help`, in the order they are printed.  A command
# whose `group` is not in this tuple fails `tests/test_cli_command_table.py`.
GROUP_ORDER: tuple[str, ...] = (
    "Execution",
    "Project",
    "Inspection",
    "Orchestration",
    "Server",
    "Tooling",
    "Runtime API",
    "Registry",
    "Stability",
)

# Column the summary text starts at in the global help listing, minus the
# two-space indent.  Pinned by a byte-comparison test against the pre-table
# help output.
_SIGNATURE_WIDTH = 18


@dataclass(frozen=True)
class Command:
    """One entry in the command surface.

    `with_values` / `no_values` are the flag sets handed to `_parse_flags`.
    `subcommands` carries the same pair for commands that dispatch a second
    level (`workflow`, `graph`), keyed by subcommand name.
    """

    name: str
    signature: str
    summary: str
    group: str | None = None
    with_values: frozenset[str] = frozenset()
    no_values: frozenset[str] = frozenset()
    subcommands: Mapping[str, tuple[frozenset[str], frozenset[str]]] = field(
        default_factory=dict
    )
    #: Not listed in `nodus --help`.  These are the legacy long-form aliases
    #: (`workflow-run` for `workflow run`, `package-install` for `install`)
    #: kept working but not advertised.  Airflow's `ActionCommand.hide`.
    hidden: bool = False
    #: The command forwards its argv untouched to another parser, so `cli.py`
    #: never calls `_parse_flags` for it.  The flags are still declared here --
    #: they are part of the surface, and completion needs them -- but this says
    #: plainly that the table is describing them rather than enforcing them.
    delegates: bool = False

    @property
    def flags(self) -> tuple[frozenset[str], frozenset[str]]:
        return self.with_values, self.no_values


def _c(*args: object, **kwargs: object) -> Command:
    return Command(*args, **kwargs)  # type: ignore[arg-type]


# Repeated flag groups.  Named so a command opts into a set rather than
# restating it -- `--path` / `--project-root` alone appeared inline at ten
# separate call sites.
_PROJECT = frozenset({"--project-root"})
_PROJECT_OR_PATH = frozenset({"--path", "--project-root"})
_SERVER_CONN = frozenset({"--host", "--port", "--auth-token"})
_STORE = frozenset({"--path", "--project-root"})
_TRACE_NO_VALUE = frozenset(
    {
        "--trace",
        "--trace-no-loc",
        "--trace-scheduler",
        "--trace-events",
        "--trace-json",
        "--no-opt",
    }
)


COMMANDS: dict[str, Command] = {
    # -- Execution ---------------------------------------------------------
    "run": _c(
        "run",
        "run [file]",
        "Run a Nodus script or project",
        group="Execution",
        with_values=frozenset(
            {
                "--trace-limit",
                "--trace-filter",
                "--trace-file",
                "--project-root",
                "--step-limit",
                "--time-limit",
                "--output-limit",
                "--allow-paths",
                "--writable-paths",
            }
        ),
        no_values=_TRACE_NO_VALUE
        | frozenset({"--trace-errors", "--dump-bytecode", "--strict", "--trace-imports"}),
    ),
    "check": _c(
        "check",
        "check [file]",
        "Validate syntax and imports without executing",
        group="Execution",
        with_values=_PROJECT,
        no_values=_TRACE_NO_VALUE,
    ),
    "fmt": _c(
        "fmt",
        "fmt <file>",
        "Format a source file in-place",
        group="Execution",
        no_values=frozenset({"--check", "--keep-trailing"}),
    ),
    "test": _c(
        "test",
        "test [path]",
        "Run .nd test files (files matching *_test.nd or test_*.nd)",
        group="Execution",
        # Parsed by `nodus.testing.cli.run_test_command`, not by `cli.py` --
        # see `delegates`.  Listed so completion and the doc-vs-parse check
        # can see the real surface.
        delegates=True,
        with_values=frozenset(
            {
                "--filter",
                "--format",
                "--seed",
                "--parallel",
                "--coverage-output",
                "--coverage-format",
                "--coverage-min",
                "--coverage-include",
                "--coverage-exclude",
            }
        ),
        no_values=frozenset(
            {
                "--bail",
                "--verbose",
                "--quiet",
                "--watch",
                "--coverage",
                "--coverage-per-test",
            }
        ),
    ),
    "repl": _c(
        "repl",
        "repl",
        "Start an interactive shell (REPL)",
        group="Execution",
    ),
    "status": _c(
        "status",
        "status",
        "Show the project and entry point for the current directory",
        group="Execution",
    ),
    # -- Project -----------------------------------------------------------
    "init": _c(
        "init",
        "init",
        "Create a new nodus.toml project",
        group="Project",
        with_values=_PROJECT_OR_PATH,
    ),
    "install": _c(
        "install",
        "install",
        "Install dependencies from nodus.toml",
        group="Project",
        with_values=_PROJECT_OR_PATH | frozenset({"--registry", "--registry-token"}),
    ),
    "update": _c(
        "update",
        "update",
        "Update dependencies to latest compatible versions",
        group="Project",
        with_values=_PROJECT_OR_PATH,
    ),
    "add": _c(
        "add",
        "add <pkg>",
        "Add a dependency to the project",
        group="Project",
        with_values=_PROJECT_OR_PATH,
    ),
    "remove": _c(
        "remove",
        "remove <pkg>",
        "Remove a dependency from the project",
        group="Project",
        with_values=_PROJECT_OR_PATH,
    ),
    "deps": _c(
        "deps",
        "deps",
        "Show the dependency graph",
        group="Project",
        with_values=_PROJECT_OR_PATH,
    ),
    "cache": _c(
        "cache",
        "cache clear",
        "Clear the bytecode cache",
        group="Project",
        with_values=_PROJECT_OR_PATH,
        subcommands={"clear": (_PROJECT_OR_PATH, frozenset())},
    ),
    # -- Inspection --------------------------------------------------------
    "ast": _c(
        "ast",
        "ast <file>",
        "Print the abstract syntax tree",
        group="Inspection",
        no_values=frozenset({"--compact"}),
    ),
    "dis": _c(
        "dis",
        "dis <file>",
        "Disassemble to bytecode listing",
        group="Inspection",
        with_values=_PROJECT,
        no_values=frozenset({"--loc"}),
    ),
    "debug": _c(
        "debug",
        "debug <file>",
        "Run under the interactive step debugger",
        group="Inspection",
        with_values=_PROJECT,
    ),
    "profile": _c(
        "profile",
        "profile <file>",
        "Profile script execution",
        group="Inspection",
        with_values=_PROJECT
        | frozenset({"--step-limit", "--time-limit", "--output-limit", "--allow-paths",
                     "--writable-paths"}),
        no_values=frozenset({"--json", "--no-opt"}),
    ),
    # -- Orchestration -----------------------------------------------------
    "workflow": _c(
        "workflow",
        "workflow <cmd>",
        "Manage workflows (run, list, resume, cleanup)",
        group="Orchestration",
        subcommands={
            "run": (frozenset({"--workflow", "--project-root"}), frozenset()),
            "list": (_STORE, frozenset()),
            "resume": (_STORE | frozenset({"--checkpoint"}), frozenset()),
            "dead-letters": (_STORE, frozenset()),
            "runs": (
                _STORE
                | frozenset(
                    {
                        "--status",
                        "--workflow",
                        "--execution-kind",
                        "--updated-after-ms",
                        "--updated-before-ms",
                        "--has-retry",
                        "--has-wait",
                        "--replay-count-min",
                        "--limit",
                        "--offset",
                        "--cursor",
                    }
                ),
                frozenset(),
            ),
            "inspect": (_STORE, frozenset()),
            "replay": (
                _STORE | frozenset({"--checkpoint"}),
                frozenset({"--rearm-only"}),
            ),
            "migrate-state": (_STORE | frozenset({"--graph-id"}), frozenset()),
            "cleanup": (
                _STORE | frozenset({"--retention-seconds"}),
                frozenset({"--force"}),
            ),
        },
    ),
    "goal-run": _c(
        "goal-run",
        "goal-run <file>",
        "Run a goal",
        group="Orchestration",
        with_values=frozenset({"--goal", "--project-root"}),
    ),
    "graph": _c(
        "graph",
        "graph run <file>",
        "Execute a task graph",
        group="Orchestration",
        with_values=_PROJECT | frozenset({"--format", "--output"}),
        subcommands={
            "run": (_PROJECT, frozenset({"--execute"})),
            "show": (_PROJECT | frozenset({"--format", "--output"}), frozenset({"--execute"})),
        },
    ),
    # -- Server ------------------------------------------------------------
    "serve": _c(
        "serve",
        "serve",
        "Start the Nodus HTTP API server",
        group="Server",
        with_values=frozenset(
            {
                "--host",
                "--port",
                "--worker-sweep-interval-ms",
                "--allow-paths",
                "--writable-paths",
                "--auth-token",
                "--workflow-store-backend",
                "--workflow-store-path",
            }
        ),
        no_values=frozenset({"--trace", "--allow-input"}),
    ),
    "worker": _c(
        "worker",
        "worker",
        "Register a worker with a running server",
        group="Server",
        with_values=_SERVER_CONN,
    ),
    "snapshot": _c(
        "snapshot",
        "snapshot",
        "Save a running session snapshot",
        group="Server",
        with_values=_SERVER_CONN,
    ),
    "snapshots": _c(
        "snapshots",
        "snapshots",
        "List available session snapshots",
        group="Server",
        with_values=_SERVER_CONN,
    ),
    "restore": _c(
        "restore",
        "restore",
        "Restore a session from a snapshot",
        group="Server",
        with_values=_SERVER_CONN,
    ),
    # -- Tooling -----------------------------------------------------------
    "lsp": _c(
        "lsp",
        "lsp",
        "Start the Language Server Protocol server",
        group="Tooling",
    ),
    "dap": _c(
        "dap",
        "dap",
        "Start the Debug Adapter Protocol server",
        group="Tooling",
    ),
    "doctor": _c(
        "doctor",
        "doctor",
        "Check the environment and report what nodus resolves to",
        group="Tooling",
        no_values=frozenset({"--json"}),
    ),
    "completion": _c(
        "completion",
        "completion <shell>",
        "Emit a completion script (bash|zsh|fish|powershell)",
        group="Tooling",
    ),
    # -- Runtime API -------------------------------------------------------
    "tool-call": _c(
        "tool-call",
        "tool-call",
        "Invoke a registered tool",
        group="Runtime API",
        with_values=frozenset({"--json"}),
    ),
    "agent-call": _c(
        "agent-call",
        "agent-call",
        "Invoke a registered agent",
        group="Runtime API",
        with_values=frozenset({"--json"}),
    ),
    "memory-get": _c(
        "memory-get",
        "memory-get",
        "Read a value from the memory store",
        group="Runtime API",
    ),
    "memory-put": _c(
        "memory-put",
        "memory-put",
        "Write a value to the memory store",
        group="Runtime API",
        with_values=frozenset({"--json"}),
    ),
    "memory-delete": _c(
        "memory-delete",
        "memory-delete",
        "Delete a value from the memory store",
        group="Runtime API",
    ),
    "memory-keys": _c(
        "memory-keys",
        "memory-keys",
        "List all memory store keys",
        group="Runtime API",
    ),
    # -- Registry ----------------------------------------------------------
    "login": _c(
        "login",
        "login",
        "Save a registry authentication token",
        group="Registry",
        with_values=frozenset({"--registry"}),
    ),
    "logout": _c(
        "logout",
        "logout",
        "Remove a saved registry token",
        group="Registry",
        with_values=frozenset({"--registry"}),
    ),
    "publish": _c(
        "publish",
        "publish",
        "Publish a package to the registry",
        group="Registry",
        # `--project-root` is here because the help text has always documented
        # it.  It was missing from the parse set, so it was swallowed as a
        # positional and publish ran against the process CWD instead.
        with_values=frozenset({"--registry", "--registry-token", "--project-root"}),
    ),
    # -- Stability ---------------------------------------------------------
    "stability": _c(
        "stability",
        "stability",
        "Show which language surfaces are stable vs experimental",
        group="Stability",
    ),
    # -- Hidden: legacy long-form aliases ---------------------------------
    "test-examples": _c(
        "test-examples",
        "test-examples",
        "Run the bundled example scripts",
        hidden=True,
    ),
    "workflow-run": _c(
        "workflow-run",
        "workflow-run <file>",
        "Run a workflow (legacy form of 'workflow run')",
        hidden=True,
        with_values=frozenset({"--workflow", "--project-root", "--time-limit"}),
    ),
    "workflow-plan": _c(
        "workflow-plan",
        "workflow-plan <file>",
        "Plan a workflow without running it",
        hidden=True,
        with_values=frozenset({"--workflow", "--project-root"}),
    ),
    "workflow-resume": _c(
        "workflow-resume",
        "workflow-resume <graph_id>",
        "Resume a workflow (legacy form of 'workflow resume')",
        hidden=True,
        with_values=frozenset({"--checkpoint"}),
    ),
    "workflow-checkpoints": _c(
        "workflow-checkpoints",
        "workflow-checkpoints <graph_id>",
        "List checkpoints recorded for a workflow run",
        hidden=True,
    ),
    "goal-plan": _c(
        "goal-plan",
        "goal-plan <file>",
        "Plan a goal without running it",
        hidden=True,
        with_values=frozenset({"--goal", "--project-root"}),
    ),
    "goal-resume": _c(
        "goal-resume",
        "goal-resume <graph_id>",
        "Resume a goal run",
        hidden=True,
        with_values=frozenset({"--checkpoint"}),
    ),
    "package-init": _c(
        "package-init",
        "package-init",
        "Create a new nodus.toml project (legacy form of 'init')",
        hidden=True,
        with_values=_PROJECT_OR_PATH,
    ),
    "package-install": _c(
        "package-install",
        "package-install",
        "Install dependencies (legacy form of 'install')",
        hidden=True,
        with_values=_PROJECT_OR_PATH | frozenset({"--registry", "--registry-token"}),
    ),
    "package-update": _c(
        "package-update",
        "package-update",
        "Update dependencies (legacy form of 'update')",
        hidden=True,
        with_values=_PROJECT_OR_PATH,
    ),
    "package-list": _c(
        "package-list",
        "package-list",
        "List installed packages",
        hidden=True,
        with_values=_PROJECT_OR_PATH,
    ),
}


# Kept as a name because the #353 `--help` guard and its tests dispatch off it.
# It is derived now rather than maintained beside the table, so a command that
# exists cannot fail to be guarded.
KNOWN_COMMANDS = frozenset(COMMANDS)


def flags_for(command: str, subcommand: str | None = None) -> tuple[set[str], set[str]]:
    """Flag sets for a dispatch branch.

    Returns mutable copies: `_parse_flags` takes `set[str]`, and a caller that
    mutates its result must not be able to reach back into the table.
    """
    entry = COMMANDS[command]
    if subcommand is not None:
        with_values, no_values = entry.subcommands[subcommand]
    else:
        with_values, no_values = entry.flags
    return set(with_values), set(no_values)


def command_summary(command: str) -> tuple[str, str] | None:
    """`(signature, summary)` for a command listed in the global help.

    `None` for a hidden command, matching the behaviour of the help-scraping
    implementation this replaced.
    """
    entry = COMMANDS.get(command)
    if entry is None or entry.hidden:
        return None
    return entry.signature, entry.summary


# Hand-written per-command help.  Moved verbatim from cli.py; the entries
# are prose, so they stay a literal rather than being generated from the
# table.  `tests/test_cli_command_table.py` cross-checks the flags each
# entry documents against the flags its command actually parses.
_DETAILED_HELP: dict[str, str] = {
    "run": "\n".join([
        "Usage: nodus run [<file|project-dir>] [options]",
        "",
        "Run a Nodus script file or project. Without a file argument, discovers and",
        "runs the project in the current directory.",
        "",
        "Options:",
        "  --trace                    Print each VM instruction to stderr as it executes (high-volume)",
        "  --trace-no-loc             Omit line-number annotations from trace output",
        "  --trace-limit N            Stop tracing after N instructions",
        "  --trace-filter STR         Only show trace lines containing STR",
        "  --trace-scheduler          Include scheduler events in trace output",
        "  --trace-events             Include runtime event bus entries in trace output",
        "  --dump-bytecode            Print compiled bytecode before executing",
        "  --no-opt                   Disable the bytecode optimizer",
        "  --project-root PATH        Override the project root directory",
        "  --step-limit N             Abort after N VM instructions",
        "  --time-limit SECS          Abort after SECS seconds of wall time",
        "  --output-limit N           Truncate stdout after N characters",
        "  --allow-paths PATHS        Restrict file I/O to colon-separated paths",
        "  --writable-paths PATHS     Subset of those that may be written (default: all)",
        "  --strict                   Require an explicit file path; disable project auto-discovery",
        "  --trace-imports            Print each resolved import path to stderr (marked when read from the bytecode cache)",
        "  --trace-errors             Print Python exception details to stderr for stdlib errors (also: NODUS_TRACE_ERRORS=1)",
        "",
        "Examples:",
        "  nodus run main.nd",
        "  nodus run                  (runs project from current directory)",
        "  nodus run src/",
        "  nodus run main.nd --trace",
    ]),
    "repl": "\n".join([
        "Usage: nodus repl",
        "",
        "Start an interactive Nodus REPL (read-eval-print loop).",
        "Type expressions or statements at the prompt; results are printed automatically.",
        "Built-in REPL commands: :help, :quit, :clear, :reset",
        "",
        "Examples:",
        "  nodus repl",
        "  nodus repl    # at the prompt: let x = 42; print(x * 2)",
    ]),
    "init": "\n".join([
        "Usage: nodus init [--path PATH]",
        "",
        "Initialize a new Nodus project in the current directory (or the given path).",
        "Creates a nodus.toml manifest and a src/main.nd entry file.",
        "",
        "Options:",
        "  --path PATH    Directory to initialize (default: current directory)",
        "",
        "Examples:",
        "  nodus init",
        "  nodus init --path ./my-project",
    ]),
    "check": "\n".join([
        "Usage: nodus check [<file|project-dir>] [options]",
        "",
        "Parse and validate a Nodus script or project without executing it.",
        "Exits 0 if no errors are found, 1 otherwise.",
        "",
        "What it catches: syntax errors; import resolution failures; type",
        "annotation violations (function bodies, call sites, and workflow step",
        "bodies — #401); workflow structure (dependency cycles #396, duplicate",
        "steps, unknown deps, goal waypoints #409/#500, step guards #471); and",
        "names that are defined somewhere but unreachable from the use site.",
        "",
        "What it deliberately does not catch: a call to a name defined nowhere.",
        "A host-registered function is indistinguishable from a typo until a",
        "program can declare its host surface (#489), so unknown free names",
        "pass and are caught at run time. `nodus lsp` diagnostics are stricter",
        "(undefined/unused variables, unreachable code, step bodies included).",
        "",
        "Options:",
        "  --project-root PATH    Override the project root directory",
        "",
        "Examples:",
        "  nodus check main.nd",
        "  nodus check            (checks project in current directory)",
    ]),
    "status": "\n".join([
        "Usage: nodus status",
        "",
        "Show the project that would run if `nodus run` were called from the current directory.",
        "Prints the project root, entry file, and current working directory.",
        "Exits 0 whether or not a project is found.",
        "",
        "Examples:",
        "  nodus status",
        "  nodus status    # from a directory with no nodus.toml",
    ]),
    "fmt": "\n".join([
        "Usage: nodus fmt <file> [options]",
        "",
        "Format a Nodus source file in-place according to the standard style.",
        "",
        "Options:",
        "  --check           Check formatting without modifying the file (exits 1 if unformatted)",
        "  --keep-trailing   Preserve trailing comments in their original positions",
        "",
        "Examples:",
        "  nodus fmt main.nd",
        "  nodus fmt main.nd --check",
    ]),
    "debug": "\n".join([
        "Usage: nodus debug <script.nd> [--project-root PATH]",
        "",
        "Run a Nodus script under the interactive step debugger.",
        "",
        "Debugger commands (entered at the (nodus-dbg) prompt):",
        "  step        Execute the next instruction and pause",
        "  next        Execute the next statement (steps over calls)",
        "  continue    Resume until the next breakpoint or end of program",
        "  break <n>   Set a breakpoint at line n",
        "  print <x>   Evaluate expression x and print the result",
        "  locals      Show all local variables in the current frame",
        "  stack       Show the current call stack",
        "  quit        Exit the debugger",
        "",
        "Options:",
        "  --project-root PATH   Override the project root directory",
        "",
        "Examples:",
        "  nodus debug main.nd",
    ]),
    "serve": "\n".join([
        "Usage: nodus serve [options]",
        "",
        "Start the Nodus HTTP server. Exposes a REST API for running scripts,",
        "managing sessions, and coordinating workflow/graph execution.",
        "",
        "Options:",
        "  --host HOST                      Bind address (default: 127.0.0.1)",
        "  --port PORT                      Port to listen on (default: 7477)",
        "  --auth-token TOKEN               Require this token on all requests (recommended for non-local hosts)",
        "  --allow-paths PATHS              Colon-separated list of paths the runtime may access",
        "  --writable-paths PATHS           Subset of those that may be written (default: all)",
        "  --allow-input                    Allow scripts to read from stdin",
        "  --trace                          Log each VM instruction to stderr",
        "  --worker-sweep-interval-ms N     How often to sweep for dead workers (default: 500)",
        "  --workflow-store-backend BACKEND Workflow store backend: local or sqlite (default: local)",
        "  --workflow-store-path PATH       Path for the workflow store",
        "",
        "Examples:",
        "  nodus serve",
        "  nodus serve --host 0.0.0.0 --port 8080 --auth-token mysecret",
    ]),
    "worker": "\n".join([
        "Usage: nodus worker [options]",
        "",
        "Connect to a running Nodus server as a remote worker.",
        "The worker registers with the server, polls for jobs, and executes them locally.",
        "Requires a server started with `nodus serve`.",
        "",
        "Options:",
        "  --host HOST        Server host to connect to (default: 127.0.0.1)",
        "  --port PORT        Server port (default: 7477)",
        "  --auth-token TOKEN Auth token to present to the server",
        "",
        "Examples:",
        "  nodus worker",
        "  nodus worker --host 10.0.0.1 --port 8080 --auth-token mysecret",
    ]),
    "ast": "\n".join([
        "Usage: nodus ast <script.nd> [--compact]",
        "",
        "Print the abstract syntax tree for a source file.",
        "",
        "Options:",
        "  --compact    Print without indentation",
    ]),
    "dis": "\n".join([
        "Usage: nodus dis <script.nd> [--loc] [--project-root PATH]",
        "",
        "Disassemble a source file to a bytecode listing.",
        "",
        "Options:",
        "  --loc                  Annotate each instruction with its source location",
        "  --project-root PATH    Override the project root directory",
    ]),
    "test": "\n".join([
        "Usage: nodus test [path] [options]",
        "",
        "Run .nd test files. Discovers files matching *_test.nd or test_*.nd under",
        "the given path (default: ./tests).",
        "",
        "Options:",
        "  --filter PATTERN           Only run tests whose name contains PATTERN",
        "  --format FMT               Output format: pretty, plain, auto (default: auto)",
        "  --bail                     Stop after the first failing test",
        "  --verbose                  Show each test as it runs",
        "  --quiet                    Show only the summary line",
        "  --watch                    Re-run tests when files change",
        "  --seed N                   Seed for test ordering",
        "  --parallel N               Run tests across N workers",
        "  --coverage                 Collect coverage while running",
        "  --coverage-per-test        Attribute coverage per test",
        "  --coverage-output PATH     Coverage output directory (default: ./coverage)",
        "  --coverage-format FMTS     Comma-separated: json,html (default: json,html)",
        "  --coverage-min PCT         Fail if total coverage is below PCT",
        "  --coverage-include GLOB    Restrict coverage to matching files",
        "  --coverage-exclude GLOB    Exclude matching files from coverage",
        "",
        "Examples:",
        "  nodus test",
        "  nodus test ./tests --bail --verbose",
        "  nodus test --coverage --coverage-min 80",
    ]),
    "install": "\n".join([
        "Usage: nodus install [options]",
        "",
        "Install the dependencies listed in nodus.toml.",
        "",
        "Options:",
        "  --project-root PATH     Project directory (default: current directory)",
        "  --path PATH             Alias for --project-root",
        "  --registry URL          Registry to install from",
        "  --registry-token TOKEN  Token for a private registry",
        "",
        "Examples:",
        "  nodus install",
        "  nodus install --project-root ./my-project",
    ]),
    "update": "\n".join([
        "Usage: nodus update [options]",
        "",
        "Update dependencies to the latest versions allowed by nodus.toml.",
        "",
        "Options:",
        "  --project-root PATH    Project directory (default: current directory)",
        "  --path PATH            Alias for --project-root",
        "",
        "Examples:",
        "  nodus update",
    ]),
    "add": "\n".join([
        "Usage: nodus add <package> [options]",
        "",
        "Add a dependency to nodus.toml and install it.",
        "",
        "Options:",
        "  --project-root PATH    Project directory (default: current directory)",
        "  --path PATH            Alias for --project-root",
        "",
        "Examples:",
        "  nodus add nodus-http",
    ]),
    "remove": "\n".join([
        "Usage: nodus remove <package> [options]",
        "",
        "Remove a dependency from nodus.toml.",
        "",
        "Options:",
        "  --project-root PATH    Project directory (default: current directory)",
        "  --path PATH            Alias for --project-root",
        "",
        "Examples:",
        "  nodus remove nodus-http",
    ]),
    "deps": "\n".join([
        "Usage: nodus deps [options]",
        "",
        "Print the resolved dependency graph as JSON.",
        "",
        "Options:",
        "  --project-root PATH    Project directory (default: current directory)",
        "  --path PATH            Alias for --project-root",
        "",
        "Examples:",
        "  nodus deps",
    ]),
    "cache": "\n".join([
        "Usage: nodus cache clear [options]",
        "",
        "Clear the project's bytecode cache (.nodus/cache/).",
        "",
        "Options:",
        "  --project-root PATH    Project directory (default: current directory)",
        "  --path PATH            Alias for --project-root",
        "",
        "Examples:",
        "  nodus cache clear",
    ]),
    "login": "\n".join([
        "Usage: nodus login [--registry URL]",
        "",
        "Save a registry authentication token to ~/.nodus/config.toml.",
        "Prompts for the token on stdin.",
        "",
        "Options:",
        "  --registry URL    Registry the token belongs to",
        "",
        "Examples:",
        "  nodus login",
        "  nodus login --registry https://registry.example.com",
    ]),
    "logout": "\n".join([
        "Usage: nodus logout [--registry URL]",
        "",
        "Remove the saved registry token from ~/.nodus/config.toml.",
        "This deletes the stored credential; there is no confirmation prompt.",
        "",
        "Options:",
        "  --registry URL    Registry whose token should be removed",
        "",
        "Examples:",
        "  nodus logout",
    ]),
    # `graph` and `workflow` carried these blocks inline in their dispatch
    # branches, where the central #353 `--help` guard made them unreachable --
    # both commands printed the generic "no detailed help" stub instead.  Same
    # shape as the bug #353 fixed: centralising the guard left the per-command
    # text stranded in branches that no longer run.
    "graph": "\n".join([
        "Usage: nodus graph <subcommand | file> [options]",
        "",
        "Subcommands:",
        "  run <file> [--project-root PATH] [--execute]",
        "             Analyze and plan the task graph defined in <file>.",
        "             Equivalent to: nodus graph <file>",
        "  show <file> [--format FMT] [--output FILE] [--project-root PATH] [--execute]",
        "             Render the planned graph as a diagram instead of JSON.",
        "",
        "Options:",
        "  --format FMT       mermaid (default) or dot",
        "  --output FILE      Write to FILE instead of stdout",
        "  --project-root PATH  Project directory used to resolve imports",
        "  --execute          Run the file to obtain the plan (old behaviour).",
        "                     Needed only for graphs constructed at runtime",
        "                     (task() / run_graph, or a dynamically chosen flow).",
        "",
        "By default the file is NOT executed (#400): the plan is built from the",
        "workflow/goal declarations alone -- the last one declared -- so",
        "inspecting an untrusted or LLM-generated file runs none of its code.",
        "",
        "Direct usage (backward-compatible):",
        "  nodus graph <file> [--project-root PATH]",
        "",
        "An edge means 'B depends on A'. A conditional edge is drawn as such:",
        "a non-default `on: [...]` filter labels the edge, and a `when` guard",
        "draws it dashed. An unlabelled solid arrow is the default, `completed`.",
        "",
        "Examples:",
        "  nodus graph tasks.nd",
        "  nodus graph run tasks.nd",
        "  nodus graph show tasks.nd",
        "  nodus graph show tasks.nd --format dot --output graph.dot",
    ]),
    "workflow": "\n".join([
        "Usage: nodus workflow <subcommand> [options]",
        "",
        "Subcommands:",
        "  run <file> [--workflow NAME] [--project-root PATH]",
        "             Run the workflow defined in <file>.",
        "  list [--project-root PATH]",
        "             List saved workflow graph snapshots.",
        "  resume <graph_id> [--checkpoint LABEL] [--project-root PATH]",
        "             Resume a previously saved workflow.",
        "  dead-letters [--project-root PATH]",
        "             List dead-lettered workflow runs.",
        "  runs [--status STATUS] [--workflow NAME] [--execution-kind KIND] [--cursor CURSOR] [--project-root PATH]",
        "             List workflow framework runs with optional filtering.",
        "  inspect <graph_id> [--project-root PATH]",
        "             Show a workflow framework run record.",
        "  replay <graph_id> [--checkpoint LABEL] [--rearm-only] [--project-root PATH]",
        "             Replay or rearm a dead-lettered workflow run.",
        "  migrate-state [--graph-id ID] [--project-root PATH]",
        "             Rewrite persisted workflow state into the normalized format.",
        "  cleanup [--retention-seconds N] [--force] [--project-root PATH]",
        "             Remove old workflow snapshots and their run records.",
        "             Default retention: terminal runs older than 30 days",
        "             (NODUS_WORKFLOW_RETENTION_SECONDS overrides; 0 disables,",
        "             leaving only --force). Children are removed with their",
        "             parent. Snapshots include the run's program source (#499).",
        "",
        "Examples:",
        "  nodus workflow run pipeline.nd",
        "  nodus workflow run pipeline.nd --workflow publish",
        "  nodus workflow list",
        "  nodus workflow resume g_abc123 --checkpoint step2",
        "  nodus workflow dead-letters",
        "  nodus workflow runs --status waiting,retry_scheduled",
        "  nodus workflow runs --workflow demo --limit 10",
        "  nodus workflow runs --has-wait true --updated-after-ms 0 --cursor o:10",
        "  nodus workflow replay g_abc123 --rearm-only",
        "  nodus workflow migrate-state --graph-id g_abc123",
    ]),
    "publish": "\n".join([
        "Usage: nodus publish [options]",
        "",
        "Publish the current package to a registry. Reads nodus.toml from the project",
        "root and uploads the built package.",
        "",
        "Options:",
        "  --registry URL          Registry to publish to",
        "  --registry-token TOKEN  Token to authenticate with (overrides the saved one)",
        "  --project-root PATH     Project directory (default: current directory)",
        "",
        "Examples:",
        "  nodus publish",
        "  nodus publish --registry https://registry.example.com",
    ]),
}


def command_help(command: str) -> str:
    """Help text for a subcommand.

    Commands with no hand-written entry still get usage and a pointer -- the
    point of handling ``--help`` centrally is that a command never *runs*
    because nobody wrote its help yet (#353).
    """
    detailed = _DETAILED_HELP.get(command)
    if detailed is not None:
        return detailed
    summary = command_summary(command)
    if summary is None:
        return "\n".join(
            [
                f"Usage: nodus {command} [options]",
                "",
                "No detailed help has been written for this command.",
                "Run 'nodus --help' for the full command list.",
            ]
        )
    signature, description = summary
    return "\n".join(
        [
            f"Usage: nodus {signature}",
            "",
            description + ".",
            "",
            "No detailed option help has been written for this command yet.",
            "Run 'nodus --help' for the full command list.",
        ]
    )


def render_help() -> str:
    """The global `nodus --help` listing, projected from `COMMANDS`."""
    lines = ["Usage: nodus <command> [options] [file]", ""]
    for group in GROUP_ORDER:
        lines.append(f"{group}:")
        for entry in COMMANDS.values():
            if entry.hidden or entry.group != group:
                continue
            # `ljust` alone would butt the summary against a signature that is
            # already at the column width, so pad to the column *or* two
            # spaces, whichever is wider.
            pad = " " * max(2, _SIGNATURE_WIDTH - len(entry.signature))
            lines.append(f"  {entry.signature}{pad}{entry.summary}")
        lines.append("")
    lines.extend(
        [
            "Global options:",
            "  --version         Print the Nodus version and exit",
            "  --help            Show this help message",
            "",
            "Stability tiers: Stable | Mostly Stable | Experimental",
            "  Orchestration (workflow, goal, coroutine, channel) -- Experimental",
            "  Core language, embedding API, stdlib I/O             -- Stable",
            "  Run 'nodus stability' for the full surface index.",
            "",
            "Use 'nodus <command> --help' for options and examples.",
        ]
    )
    return "\n".join(lines)
