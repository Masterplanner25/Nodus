"""CLI entrypoints for Nodus."""

from __future__ import annotations

import http.client
from importlib import metadata
import json
import os
import sys
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Callable

from nodus.runtime.errors import format_error_payload
from nodus.runtime.bytecode_cache import clear_bytecode_cache
from nodus.runtime.dependency_graph import DependencyGraph
from nodus.runtime.profiler import Profiler
from nodus.dap.server import run_stdio_server as run_dap_stdio_server
from nodus.lsp.server import run_stdio_server
from nodus.tooling.formatter import format_source
from nodus.tooling.repl import run_repl
from nodus.tooling import package_manager as _package_manager
from nodus.tooling.project import load_project, load_project_from, project_entry_path
from nodus.orchestration import task_graph as _task_graph
from nodus.tooling.runner import (
    agent_call_result,
    build_ast,
    check_source,
    debug_source,
    disassemble_source,
    format_disassembly_with_locs,
    memory_delete_result,
    memory_get_result,
    memory_keys_result,
    memory_put_result,
    plan_graph_code,
    plan_goal_code,
    plan_workflow_code,
    replay_workflow,
    resume_goal,
    resume_workflow,
    run_goal_code,
    run_source,
    run_workflow_code,
    tool_call_result,
    workflow_checkpoints,
)
from nodus.services.server import serve, snapshot_session, restore_snapshot, list_snapshots
from nodus.support.config import SERVER_HOST, SERVER_PORT, WORKER_SWEEP_INTERVAL_MS, MAX_STEPS, EXECUTION_TIMEOUT_MS, MAX_STDOUT_CHARS
from nodus.vm.vm import VM
from nodus.support.version import VERSION
from nodus_workflow.runner import get_default_workflow_runner


def _read_file(path: str) -> str:
    with open(path, "r", encoding="utf-8-sig") as handle:
        return handle.read()


def _write_file(path: str, contents: str) -> None:
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(contents)


def _print_stderr(message: str) -> None:
    print(message, file=sys.stderr)


def _project_root_from_env() -> str | None:
    value = os.environ.get("NODUS_PROJECT_ROOT")
    return value if value else None


def _allowed_paths_from_env() -> list[str] | None:
    raw = os.environ.get("NODUS_ALLOWED_PATHS")
    if raw is None:
        return None
    paths = [part.strip() for part in raw.split(os.pathsep) if part.strip()]
    return paths


def _resolve_allowed_paths(value: object | None) -> list[str] | None:
    if value is None:
        return _allowed_paths_from_env()
    if not isinstance(value, str):
        return None
    raw = value.strip()
    if not raw:
        return []
    parts = [part.strip() for part in raw.split(os.pathsep) if part.strip()]
    return parts


def _server_auth_token_from_env() -> str | None:
    value = os.environ.get("NODUS_SERVER_TOKEN")
    return value if value else None


def _workflow_store_backend_from_env() -> str | None:
    value = os.environ.get("NODUS_WORKFLOW_STORE_BACKEND")
    return value if value else None


def _workflow_store_path_from_env() -> str | None:
    value = os.environ.get("NODUS_WORKFLOW_STORE_PATH")
    return value if value else None


def _server_allow_input_from_env() -> bool:
    value = os.environ.get("NODUS_SERVER_ALLOW_INPUT")
    if value is None:
        return False
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _resolve_project_root(path: object | None) -> tuple[str | None, str | None]:
    root = str(path) if path is not None else None
    root = root or _project_root_from_env()
    if root is None:
        return None, None
    if not os.path.isdir(root):
        return None, f"Invalid project root: {root}"
    return root, None


@contextmanager
def _project_root_context(path: str | None):
    if path:
        original = os.getcwd()
        os.chdir(path)
        try:
            yield
        finally:
            os.chdir(original)
    else:
        yield


def _resolve_run_target(path: str | None, project_root: str | None) -> tuple[str | None, str | None, str | None]:
    if path is None:
        project = load_project_from(os.getcwd())
        if project is None:
            return None, project_root, "Usage: nodus run <script.nd | project-dir>"
        return project_entry_path(project), project_root or project.root, None
    if os.path.isdir(path):
        try:
            project = load_project(path)
        except Exception as _e:
            return None, project_root, str(_e)
        return project_entry_path(project), project_root or project.root, None
    return path, project_root, None


def _parse_flags(args: list[str], flags_with_values: set[str], flags_no_values: set[str]) -> tuple[list[str], dict]:
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
                raise ValueError(f"Missing value for {arg}")
            parsed[arg] = args[idx + 1]
            idx += 2
            continue
        positional.append(arg)
        idx += 1
    return positional, parsed


def _parse_int(value: str, flag: str) -> int:
    try:
        return int(value)
    except ValueError as exc:
        raise ValueError(f"Invalid integer for {flag}: {value}") from exc


def _parse_float(value: str, flag: str) -> float:
    try:
        return float(value)
    except ValueError as exc:
        raise ValueError(f"Invalid number for {flag}: {value}") from exc


def _parse_bool_flag(value: str, flag: str) -> bool:
    normalized = str(value).strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"Invalid boolean for {flag}: {value}")


def _render_help() -> str:
    return "\n".join([
        "Usage: nodus <command> [options] [file]",
        "",
        "Execution:",
        "  run [file]        Run a Nodus script or project",
        "  check [file]      Validate syntax and imports without executing",
        "  fmt <file>        Format a source file in-place",
        "  repl              Start an interactive shell (REPL)",
        "  status            Show the project and entry point for the current directory",
        "",
        "Project:",
        "  init              Create a new nodus.toml project",
        "  install           Install dependencies from nodus.toml",
        "  update            Update dependencies to latest compatible versions",
        "  add <pkg>         Add a dependency to the project",
        "  remove <pkg>      Remove a dependency from the project",
        "  deps              Show the dependency graph",
        "  cache clear       Clear the bytecode cache",
        "",
        "Inspection:",
        "  ast <file>        Print the abstract syntax tree",
        "  dis <file>        Disassemble to bytecode listing",
        "  debug <file>      Run under the interactive step debugger",
        "  profile <file>    Profile script execution",
        "",
        "Orchestration:",
        "  workflow <cmd>    Manage workflows (run, list, resume, cleanup)",
        "  goal-run <file>   Run a goal",
        "  graph run <file>  Execute a task graph",
        "",
        "Server:",
        "  serve             Start the Nodus HTTP API server",
        "  worker            Register a worker with a running server",
        "  snapshot          Save a running session snapshot",
        "  snapshots         List available session snapshots",
        "  restore           Restore a session from a snapshot",
        "",
        "Tooling:",
        "  lsp               Start the Language Server Protocol server",
        "  dap               Start the Debug Adapter Protocol server",
        "",
        "Runtime API:",
        "  tool-call         Invoke a registered tool",
        "  agent-call        Invoke a registered agent",
        "  memory-get        Read a value from the memory store",
        "  memory-put        Write a value to the memory store",
        "  memory-delete     Delete a value from the memory store",
        "  memory-keys       List all memory store keys",
        "",
        "Registry:",
        "  login             Save a registry authentication token",
        "  logout            Remove a saved registry token",
        "  publish           Publish a package to the registry",
        "",
        "Global options:",
        "  --version         Print the Nodus version and exit",
        "  --help            Show this help message",
        "",
        "Use 'nodus <command> --help' for options and examples.",
    ])


_COMMAND_HELP: dict[str, str] = {
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
        "  --strict                   Require an explicit file path; disable project auto-discovery",
        "  --trace-imports            Print each resolved import path to stderr at resolution time",
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
        "Catches syntax errors and import resolution failures. Does not check",
        "undefined variable/function references (those are caught at run time).",
        "Exits 0 if no errors are found, 1 otherwise.",
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
}


def _print_result_output(result: dict) -> None:
    stdout = result.get("stdout") or ""
    stderr = result.get("stderr") or ""
    if stdout:
        try:
            print(stdout, end="")
        except UnicodeEncodeError:
            sys.stdout.buffer.write(stdout.encode("utf-8", errors="replace"))
            sys.stdout.buffer.flush()
    if stderr:
        _print_stderr(stderr)


def _print_error(result: dict, *, path: str | None = None) -> None:
    payload = result.get("error")
    if isinstance(payload, dict):
        _print_stderr(format_error_payload(payload))
        return
    err = result.get("errors")
    if isinstance(err, list) and err:
        _print_stderr(format_error_payload(err[0]))
        return
    if "message" in result:
        _print_stderr(str(result["message"]))
        return
    if path:
        _print_stderr(f"Error in {path}")


def run_file(
    path: str | None,
    *,
    trace: bool = False,
    trace_no_loc: bool = False,
    trace_limit: int | None = None,
    trace_filter: str | None = None,
    trace_scheduler: bool = False,
    trace_events: bool = False,
    trace_json: bool = False,
    trace_file: str | None = None,
    trace_imports: bool = False,
    trace_errors: bool = False,
    optimize: bool = True,
    dump_bytecode: bool = False,
    project_root: str | None = None,
    max_steps: int | None = None,
    timeout_ms: int | None = None,
    max_stdout_chars: int | None = None,
    allowed_paths: list[str] | None = None,
) -> int:
    is_project_run = path is None or (path is not None and os.path.isdir(str(path)))
    resolved_path, project_root, err = _resolve_run_target(path, project_root)
    if err:
        _print_stderr(err)
        return 1
    if resolved_path is None or not os.path.isfile(resolved_path):
        _print_stderr(f"File not found: {resolved_path or path}")
        return 1
    path = resolved_path
    if is_project_run and project_root:
        abs_root = os.path.abspath(project_root)
        _print_stderr(f"Running project from: {abs_root}")
        _print_stderr(f"Entry: {os.path.relpath(path, abs_root)}")
    code = _read_file(path)
    if path.endswith(".tl"):
        _print_stderr("Warning: legacy .tl file detected. Consider using .nd.")
    result, _vm = run_source(
        code,
        filename=path,
        trace=trace,
        trace_no_loc=trace_no_loc,
        trace_limit=trace_limit,
        trace_filter=trace_filter,
        trace_scheduler=trace_scheduler,
        trace_events=trace_events,
        trace_json=trace_json,
        trace_file=trace_file,
        trace_imports=trace_imports,
        trace_errors=trace_errors,
        optimize=optimize,
        dump_bytecode=dump_bytecode,
        project_root=project_root,
        max_steps=MAX_STEPS if max_steps is None else max_steps,
        timeout_ms=EXECUTION_TIMEOUT_MS if timeout_ms is None else timeout_ms,
        max_stdout_chars=MAX_STDOUT_CHARS if max_stdout_chars is None else max_stdout_chars,
        allowed_paths=allowed_paths,
    )
    if dump_bytecode and result.get("disassembly"):
        print(result["disassembly"])
    _print_result_output(result)
    if not result.get("ok", False):
        _print_error(result, path=path)
        return 1
    return 0


def _format_profile_report(report: dict, *, max_functions: int = 10, max_opcodes: int = 10) -> str:
    total_ms = report.get("total_time_ms", 0.0)
    functions = report.get("functions", [])
    opcodes = report.get("opcode_counts", {})

    lines = [
        "Nodus Profiling Report",
        "----------------------",
        "",
        f"Total runtime: {total_ms:.3f} ms",
        "",
        "Top Functions:",
        "",
    ]

    if functions:
        func_rows = sorted(
            functions,
            key=lambda item: (-float(item.get("time_ms", 0.0)), -int(item.get("calls", 0)), str(item.get("name", ""))),
        )[:max_functions]
        name_width = max(len(str(item.get("name", ""))) for item in func_rows)
        for item in func_rows:
            name = str(item.get("name", "")).ljust(name_width)
            calls = int(item.get("calls", 0))
            time_ms = float(item.get("time_ms", 0.0))
            lines.append(f"{name}  {calls} call{'s' if calls != 1 else ''}  {time_ms:.3f} ms")
    else:
        lines.append("<none>")

    lines.extend(["", "Top Opcodes:", ""])

    if opcodes:
        opcode_rows = sorted(opcodes.items(), key=lambda item: (-item[1], item[0]))[:max_opcodes]
        name_width = max(len(name) for name, _count in opcode_rows)
        for name, count in opcode_rows:
            lines.append(f"{name.ljust(name_width)}  {count}")
    else:
        lines.append("<none>")

    return "\n".join(lines)


def profile_file(
    path: str,
    *,
    project_root: str | None = None,
    json_output: bool = False,
    optimize: bool = True,
    max_steps: int | None = None,
    timeout_ms: int | None = None,
    max_stdout_chars: int | None = None,
    allowed_paths: list[str] | None = None,
) -> int:
    resolved_path, project_root, err = _resolve_run_target(path, project_root)
    if err:
        _print_stderr(err)
        return 1
    if resolved_path is None or not os.path.isfile(resolved_path):
        _print_stderr(f"File not found: {resolved_path or path}")
        return 1
    path = resolved_path
    code = _read_file(path)
    profiler = Profiler()
    profiler.start()
    try:
        result, _vm = run_source(
            code,
            filename=path,
            optimize=optimize,
            project_root=project_root,
            max_steps=MAX_STEPS if max_steps is None else max_steps,
            timeout_ms=EXECUTION_TIMEOUT_MS if timeout_ms is None else timeout_ms,
            max_stdout_chars=MAX_STDOUT_CHARS if max_stdout_chars is None else max_stdout_chars,
            profiler=profiler,
            allowed_paths=allowed_paths,
        )
    finally:
        profiler.stop()

    if not result.get("ok", False):
        if not json_output:
            _print_result_output(result)
        _print_error(result, path=path)
        return 1

    if not json_output:
        _print_result_output(result)
        print(_format_profile_report(profiler.report()))
        return 0

    report = profiler.report()
    payload = {
        "runtime_ms": float(report.get("total_time_ms", 0.0)),
        "functions": report.get("functions", []),
        "opcodes": report.get("opcode_counts", {}),
    }
    _json_print(payload)
    return 0


def check_file(path: str, *, project_root: str | None = None) -> int:
    if not os.path.isfile(path):
        _print_stderr(f"File not found: {path}")
        return 1
    code = _read_file(path)
    result = check_source(code, filename=path, project_root=project_root)
    if not result.get("ok", False):
        _print_error(result, path=path)
        return 1
    print(f"{path}: OK")
    return 0


def ast_file(path: str, *, compact: bool = False) -> int:
    if not os.path.isfile(path):
        _print_stderr(f"File not found: {path}")
        return 1
    code = _read_file(path)
    result = build_ast(code, filename=path, compact=compact)
    if not result.get("ok", False):
        _print_error(result, path=path)
        return 1
    pretty = result.get("ast_pretty", "")
    print(pretty)
    return 0


def dis_file(path: str, *, include_locs: bool = False, project_root: str | None = None) -> int:
    if not os.path.isfile(path):
        _print_stderr(f"File not found: {path}")
        return 1
    code = _read_file(path)
    result = disassemble_source(code, filename=path, project_root=project_root)
    if not result.get("ok", False):
        _print_error(result, path=path)
        return 1
    text = "\n".join(result.get("dis_pretty", []))
    if include_locs:
        text = format_disassembly_with_locs(text)
    print(text)
    return 0


def debug_file(
    path: str,
    *,
    project_root: str | None = None,
    debugger_input: Callable[[str], str] = input,
    debugger_output: Callable[[str], None] = print,
) -> int:
    if not os.path.isfile(path):
        _print_stderr(f"File not found: {path}")
        return 1
    code = _read_file(path)
    result, _vm = debug_source(
        code,
        filename=path,
        project_root=project_root,
        debugger_input=debugger_input,
        debugger_output=debugger_output,
    )
    _print_result_output(result)
    if not result.get("ok", False):
        _print_error(result, path=path)
        return 1
    return 0


def _json_print(payload) -> None:
    print(json.dumps(payload))


def _json_load(value: str):
    return json.loads(value)


def _resolve_installed_version() -> str:
    try:
        return metadata.version("nodus-lang")
    except Exception:
        return "dev"


def _json_post(host: str, port: int, path: str, payload: dict, *, token: str | None = None):
    conn = http.client.HTTPConnection(host, port, timeout=5)
    body = json.dumps(payload)
    headers = {"Content-Type": "application/json"}
    token = token or _server_auth_token_from_env()
    if token:
        headers["Authorization"] = f"Bearer {token}"
    conn.request("POST", path, body=body, headers=headers)
    resp = conn.getresponse()
    data = resp.read().decode("utf-8")
    conn.close()
    return json.loads(data) if data else {}


def _json_get(host: str, port: int, path: str, *, token: str | None = None):
    conn = http.client.HTTPConnection(host, port, timeout=5)
    headers = {}
    token = token or _server_auth_token_from_env()
    if token:
        headers["Authorization"] = f"Bearer {token}"
    conn.request("GET", path, headers=headers)
    resp = conn.getresponse()
    data = resp.read().decode("utf-8")
    conn.close()
    return json.loads(data) if data else {}


def _resolve_server_host_port(flags: dict) -> tuple[str, int] | tuple[None, None]:
    host = flags.get("--host") or SERVER_HOST
    port = flags.get("--port") or SERVER_PORT
    try:
        return str(host), int(port)
    except ValueError:
        _print_stderr(f"Invalid port: {port}")
        return None, None


def _run_workflow(path: str, workflow_name: str | None = None, *, project_root: str | None = None) -> int:
    if not os.path.isfile(path):
        _print_stderr(f"File not found: {path}")
        return 1
    code = _read_file(path)
    result, _vm = run_workflow_code(VM([], {}, code_locs=[], source_path=None), code, filename=path, workflow_name=workflow_name, project_root=project_root)
    _print_result_output(result)
    if not result.get("ok", False):
        _print_error(result, path=path)
        return 1
    _json_print(result.get("result"))
    return 0


def _plan_workflow(path: str, workflow_name: str | None = None, *, project_root: str | None = None) -> int:
    if not os.path.isfile(path):
        _print_stderr(f"File not found: {path}")
        return 1
    code = _read_file(path)
    result, _vm = plan_workflow_code(VM([], {}, code_locs=[], source_path=None), code, filename=path, workflow_name=workflow_name, project_root=project_root)
    if not result.get("ok", False):
        _print_error(result, path=path)
        return 1
    _json_print(result.get("result"))
    return 0


def _run_goal(path: str, goal_name: str | None = None, *, project_root: str | None = None) -> int:
    if not os.path.isfile(path):
        _print_stderr(f"File not found: {path}")
        return 1
    code = _read_file(path)
    result, _vm = run_goal_code(VM([], {}, code_locs=[], source_path=None), code, filename=path, goal_name=goal_name, project_root=project_root)
    _print_result_output(result)
    if not result.get("ok", False):
        _print_error(result, path=path)
        return 1
    _json_print(result.get("result"))
    return 0


def _plan_goal(path: str, goal_name: str | None = None, *, project_root: str | None = None) -> int:
    if not os.path.isfile(path):
        _print_stderr(f"File not found: {path}")
        return 1
    code = _read_file(path)
    result, _vm = plan_goal_code(VM([], {}, code_locs=[], source_path=None), code, filename=path, goal_name=goal_name, project_root=project_root)
    if not result.get("ok", False):
        _print_error(result, path=path)
        return 1
    _json_print(result.get("result"))
    return 0


def _run_resume_workflow(graph_id: str, checkpoint: str | None) -> int:
    result, _vm = resume_workflow(graph_id, checkpoint)
    if not result.get("ok", False):
        _print_error(result)
        return 1
    _json_print(result.get("result"))
    return 0


def _run_resume_goal(graph_id: str, checkpoint: str | None) -> int:
    result, _vm = resume_goal(graph_id, checkpoint)
    if not result.get("ok", False):
        _print_error(result)
        return 1
    _json_print(result.get("result"))
    return 0


def _default_retention_seconds() -> int | None:
    raw = os.environ.get("NODUS_WORKFLOW_RETENTION_SECONDS")
    if raw is None:
        return None
    try:
        value = int(raw)
    except ValueError:
        return None
    if value < 0:
        return None
    return value


def _workflow_list(project_root: str | None) -> int:
    with _project_root_context(project_root):
        snapshots = _task_graph.list_graph_snapshots_info()
    _json_print(snapshots)
    return 0


def _workflow_resume_cli(graph_id: str, checkpoint: str | None, project_root: str | None) -> int:
    with _project_root_context(project_root):
        return _run_resume_workflow(graph_id, checkpoint)


def _workflow_dead_letters(project_root: str | None) -> int:
    with _project_root_context(project_root):
        runs = [record.to_dict() for record in get_default_workflow_runner().list_dead_lettered_runs()]
    _json_print(runs)
    return 0


def _workflow_runs(
    project_root: str | None,
    statuses: list[str] | None = None,
    *,
    workflow_name: str | None = None,
    execution_kind: str | None = None,
    updated_after_ms: float | None = None,
    updated_before_ms: float | None = None,
    has_retry: bool | None = None,
    has_wait: bool | None = None,
    replay_count_min: int | None = None,
    limit: int | None = None,
    offset: int = 0,
    cursor: str | None = None,
) -> int:
    with _project_root_context(project_root):
        normalized = {status.strip() for status in (statuses or []) if isinstance(status, str) and status.strip()}
        runner = get_default_workflow_runner()
        payload = runner.run_inventory(
            statuses=normalized or None,
            workflow_name=workflow_name,
            execution_kind=execution_kind,
            updated_after_ms=updated_after_ms,
            updated_before_ms=updated_before_ms,
            has_retry=has_retry,
            has_wait=has_wait,
            replay_count_min=replay_count_min,
            limit=limit,
            offset=offset,
            cursor=cursor,
        )
    _json_print(payload)
    return 0


def _workflow_inspect(graph_id: str, project_root: str | None) -> int:
    with _project_root_context(project_root):
        record = get_default_workflow_runner().get_run(graph_id)
    if record is None:
        _print_stderr(f"Workflow run not found: {graph_id}")
        return 1
    _json_print(record.to_dict())
    return 0


def _workflow_replay_cli(
    graph_id: str,
    checkpoint: str | None,
    project_root: str | None,
    *,
    rearm_only: bool = False,
) -> int:
    with _project_root_context(project_root):
        result, _vm = replay_workflow(graph_id, checkpoint, rearm_only=rearm_only)
    if not result.get("ok", False):
        _print_error(result)
        return 1
    _json_print(result.get("result"))
    return 0


def _workflow_migrate_state(project_root: str | None, graph_id: str | None = None) -> int:
    with _project_root_context(project_root):
        if graph_id:
            payload = _task_graph.migrate_graph_snapshot(graph_id)
        else:
            payload = _task_graph.migrate_all_graph_snapshots()
    _json_print(payload)
    return 0


def _workflow_cleanup(project_root: str | None, retention_seconds: int | None, force: bool) -> int:
    now_ms = int(time.time() * 1000)
    threshold = retention_seconds if retention_seconds is not None else _default_retention_seconds()
    removed: list[str] = []
    with _project_root_context(project_root):
        snapshots = _task_graph.list_graph_snapshots_info()
        for snapshot in snapshots:
            graph_id = snapshot.get("graph_id")
            if not graph_id:
                continue
            should_remove = False
            if force:
                should_remove = True
            elif threshold and snapshot.get("status") == "completed":
                updated = snapshot.get("updated_at") or 0
                try:
                    updated_ms = int(updated)
                except (TypeError, ValueError):
                    updated_ms = 0
                if updated_ms and now_ms - updated_ms >= threshold * 1000:
                    should_remove = True
            if should_remove:
                _task_graph.delete_graph_state(graph_id)
                _task_graph.delete_checkpoint(graph_id)
                removed.append(graph_id)
    _json_print({"removed": removed, "retention_seconds": threshold, "force": force})
    return 0


def _run_workflow_checkpoints(graph_id: str) -> int:
    payload = workflow_checkpoints(graph_id)
    if not payload.get("ok", False):
        _print_stderr(payload.get("error", "Workflow checkpoints failed"))
        return 1
    _json_print(payload.get("checkpoints"))
    return 0


def _plan_graph_file(path: str, *, project_root: str | None = None) -> int:
    if not os.path.isfile(path):
        _print_stderr(f"File not found: {path}")
        return 1
    code = _read_file(path)
    result, _vm = plan_graph_code(VM([], {}, code_locs=[], source_path=None), code, filename=path, project_root=project_root)
    if not result.get("ok", False):
        _print_error(result, path=path)
        return 1
    _json_print(result.get("result"))
    return 0


def _run_server(
    *,
    host: str = SERVER_HOST,
    port: int = SERVER_PORT,
    trace: bool = False,
    worker_sweep_interval_ms: int = WORKER_SWEEP_INTERVAL_MS,
    allowed_paths: list[str] | None = None,
    allow_input: bool = False,
    auth_token: str | None = None,
    workflow_store_backend: str | None = None,
    workflow_store_path: str | None = None,
) -> int:
    try:
        serve(
            host=host,
            port=port,
            trace=trace,
            worker_sweep_interval_ms=worker_sweep_interval_ms,
            allowed_paths=allowed_paths,
            allow_input=allow_input,
            auth_token=auth_token,
            workflow_store_backend=workflow_store_backend,
            workflow_store_path=workflow_store_path,
        )
    except ValueError as _e:
        _print_stderr(str(_e))
        return 1
    return 0


def _run_snapshot(session_id: str, *, host: str, port: int, token: str | None = None) -> int:
    payload = snapshot_session(host, port, session_id, token=token)
    _json_print(payload)
    return 0 if "error" not in payload else 1


def _run_snapshots(*, host: str, port: int, token: str | None = None) -> int:
    payload = list_snapshots(host, port, token=token)
    _json_print(payload)
    return 0 if "error" not in payload else 1


def _run_restore(snapshot_id: str, *, host: str, port: int, token: str | None = None) -> int:
    payload = restore_snapshot(host, port, snapshot_id, token=token)
    _json_print(payload)
    return 0 if "error" not in payload else 1


def _run_worker(host: str, port: int, *, poll_interval: float = 0.1, token: str | None = None) -> int:
    register = _json_post(host, port, "/worker/register", {"capabilities": []}, token=token)
    worker_id = register.get("worker_id")
    if not worker_id:
        _print_stderr("Failed to register worker.")
        return 1
    print(f"worker_id={worker_id}")
    try:
        while True:
            job = _json_post(host, port, "/worker/poll", {"worker_id": worker_id}, token=token)
            job_id = job.get("job_id")
            if job_id:
                _json_post(
                    host,
                    port,
                    "/worker/result",
                    {"worker_id": worker_id, "job_id": job_id, "status": "execute"},
                    token=token,
                )
                continue
            time.sleep(poll_interval)
    except KeyboardInterrupt:
        return 0


def _tool_call(name: str, args_json: str) -> int:
    try:
        args = _json_load(args_json)
    except json.JSONDecodeError as _e:
        _print_stderr(f"Invalid JSON payload: {_e}")
        return 1
    result = tool_call_result(name, args)
    _json_print(result)
    return 0 if result.get("ok", False) else 1


def _agent_call(name: str, payload_json: str) -> int:
    try:
        payload = _json_load(payload_json)
    except json.JSONDecodeError as _e:
        _print_stderr(f"Invalid JSON payload: {_e}")
        return 1
    result = agent_call_result(name, payload)
    _json_print(result)
    return 0 if result.get("ok", False) else 1


def _memory_get(key: str) -> int:
    result = memory_get_result(key)
    if not result.get("ok", False):
        _print_error(result)
        return 1
    _json_print(result.get("result"))
    return 0


def _memory_put(key: str, value_json: str) -> int:
    try:
        value = _json_load(value_json)
    except json.JSONDecodeError as _e:
        _print_stderr(f"Invalid JSON value: {_e}")
        return 1
    result = memory_put_result(key, value)
    if not result.get("ok", False):
        _print_error(result)
        return 1
    _json_print(result.get("result"))
    return 0


def _memory_delete(key: str) -> int:
    result = memory_delete_result(key)
    if not result.get("ok", False):
        _print_error(result)
        return 1
    _json_print(result.get("result"))
    return 0


def _memory_keys() -> int:
    result = memory_keys_result()
    if not result.get("ok", False):
        _print_error(result)
        return 1
    _json_print(result.get("result"))
    return 0


def _format_file(path: str, *, check_only: bool = False, keep_trailing: bool = False) -> int:
    if not os.path.isfile(path):
        _print_stderr(f"File not found: {path}")
        return 1
    original = _read_file(path)
    formatted = format_source(original, keep_trailing_comments=keep_trailing)
    if check_only:
        if formatted != original.replace("\r\n", "\n").replace("\r", "\n"):
            _print_stderr(f"File not formatted: {path}")
            return 1
        return 0
    if formatted != original:
        _write_file(path, formatted)
    return 0


def _example_paths() -> list[str]:
    root = Path(__file__).resolve().parents[3]
    examples_dir = root / "examples"
    return [
        str(examples_dir / "hello.nd"),
        str(examples_dir / "features_demo.nd"),
        str(examples_dir / "import_demo.nd"),
        str(examples_dir / "namespace_import_demo.nd"),
        str(examples_dir / "relative_import_demo.nd"),
        str(examples_dir / "stdlib_demo.nd"),
        str(examples_dir / "std_selective_import_demo.nd"),
        str(examples_dir / "file_utils_demo.nd"),
        str(examples_dir / "project_layout_demo" / "main.nd"),
    ]


def _run_examples() -> int:
    failures: list[str] = []
    missing: list[str] = []
    for path in _example_paths():
        if not os.path.isfile(path):
            missing.append(path)
            continue
        exit_code = run_file(path)
        if exit_code != 0:
            failures.append(path)
    if missing:
        _print_stderr("Missing examples:")
        for path in missing:
            _print_stderr(f"  {path}")
    if failures:
        _print_stderr("Examples failed:")
        for path in failures:
            _print_stderr(f"  {path}")
        return 1
    return 0


def _nodus_status() -> int:
    cwd = os.path.abspath(os.getcwd())
    project = load_project_from(cwd)
    if project is None:
        print("No project found in current directory")
        print(f"{'Working dir:':<14}{cwd}")
        return 0
    abs_root = os.path.abspath(project.root)
    entry = project_entry_path(project)
    rel_entry = os.path.relpath(entry, abs_root)
    print(f"{'Project root:':<14}{abs_root}")
    print(f"{'Entry:':<14}{rel_entry}")
    print(f"{'Working dir:':<14}{cwd}")
    return 0


def _package_init(path: str | None) -> int:
    root = path or os.getcwd()
    try:
        _package_manager.init_project(root)
    except Exception as _e:
        _print_stderr(str(_e))
        return 1
    print(f"Initialized Nodus project at {os.path.abspath(root)}/")
    return 0


def _package_install(path: str | None, *, registry_url: str | None = None, registry_token: str | None = None) -> int:
    root = path or os.getcwd()
    try:
        _package_manager.install_dependencies_for_project(root, update=False, registry_url=registry_url, cli_token=registry_token)
    except Exception as _e:
        _print_stderr(str(_e))
        return 1
    return 0


def _package_update(path: str | None) -> int:
    root = path or os.getcwd()
    try:
        _package_manager.install_dependencies_for_project(root, update=True)
    except Exception as _e:
        _print_stderr(str(_e))
        return 1
    return 0


def _package_list(path: str | None) -> int:
    root = path or os.getcwd()
    try:
        deps = _package_manager.list_dependencies(root)
    except Exception as _e:
        _print_stderr(str(_e))
        return 1
    for name, status in deps:
        print(f"{name}: {status}")
    return 0


def _package_add(package_name: str, path: str | None) -> int:
    root = path or os.getcwd()
    try:
        _package_manager.add_dependency(root, package_name)
    except Exception as _e:
        _print_stderr(str(_e))
        return 1
    return 0


def _package_remove(package_name: str, path: str | None) -> int:
    root = path or os.getcwd()
    try:
        _package_manager.remove_dependency(root, package_name)
    except Exception as _e:
        _print_stderr(str(_e))
        return 1
    return 0


def _run_login(registry_url: str | None = None) -> int:
    import getpass
    from nodus.tooling.user_config import UserConfig
    try:
        token = getpass.getpass("Registry token: ")
    except (KeyboardInterrupt, EOFError):
        print("\nLogin cancelled.")
        return 1
    if not token.strip():
        print("Error: token cannot be empty.")
        return 1
    UserConfig().set_registry_token(token.strip(), registry_url=registry_url)
    config_path = str(Path.home() / ".nodus" / "config.toml")
    print(f"Token saved to {config_path}")
    return 0


def _run_logout(registry_url: str | None = None) -> int:
    from nodus.tooling.user_config import UserConfig
    UserConfig().clear_registry_token(registry_url=registry_url)
    config_path = str(Path.home() / ".nodus" / "config.toml")
    print(f"Token removed from {config_path}")
    return 0


def _print_dependency_graph(path: str | None) -> int:
    root = path or os.getcwd()
    graph = DependencyGraph.load(root)
    if graph is None:
        _print_stderr(f"Invalid project root: {root}")
        return 1
    print(json.dumps(graph.to_dict(), indent=2, sort_keys=True))
    return 0


def _cache_clear(path: str | None) -> int:
    root = path
    if root is None:
        project = load_project_from(os.getcwd())
        root = project.root if project is not None else os.getcwd()
    removed = clear_bytecode_cache(root)
    print(f"Cleared {removed} cache entr{'y' if removed == 1 else 'ies'} from {os.path.join(root, '.nodus', 'cache')}")
    return 0


def main(argv: list[str] | None = None) -> int:
    argv = list(argv) if argv is not None else sys.argv
    prog = os.path.basename(argv[0]) if argv else "nodus"
    args = argv[1:]

    if not args:
        print(_render_help())
        return 0

    if args[0] in ("--help", "-h"):
        print(_render_help())
        return 0

    if "--version" in args:
        print(VERSION)
        return 0

    command = args[0]
    cmd_args = args[1:]

    # Backward compat: nodus <file>
    known_commands = {
        "run",
        "check",
        "fmt",
        "ast",
        "dis",
        "debug",
        "profile",
        "test",
        "test-examples",
        "repl",
        "graph",
        "serve",
        "lsp",
        "dap",
        "snapshot",
        "snapshots",
        "restore",
        "worker",
        "workflow-run",
        "workflow-plan",
        "workflow-resume",
        "workflow-checkpoints",
        "workflow",
        "goal-run",
        "goal-plan",
        "goal-resume",
        "tool-call",
        "agent-call",
        "memory-get",
        "memory-put",
        "memory-delete",
        "memory-keys",
        "package-init",
        "package-install",
        "package-update",
        "package-list",
        "cache",
        "add",
        "remove",
        "init",
        "install",
        "update",
        "deps",
        "login",
        "logout",
        "publish",
        "status",
    }

    if command not in known_commands:
        # If argv[0] is language, treat the rest as nodus args.
        if command.endswith(".nd") or command.endswith(".tl") or os.path.isfile(command):
            cmd_args = args
            command = "run"
        elif prog == "language":
            cmd_args = args
            command = "run"
        else:
            _print_stderr(f"Unknown command: {command}")
            _print_stderr("Use --help for usage.")
            return 1

    if command == "run":
        if "--help" in cmd_args or "-h" in cmd_args:
            print(_COMMAND_HELP["run"])
            return 0
        flags_with_values = {"--trace-limit", "--trace-filter", "--trace-file", "--project-root", "--step-limit", "--time-limit", "--output-limit", "--allow-paths"}
        flags_no_values = {
            "--trace",
            "--trace-no-loc",
            "--trace-scheduler",
            "--trace-events",
            "--trace-json",
            "--trace-errors",
            "--no-opt",
            "--dump-bytecode",
            "--strict",
            "--trace-imports",
        }
        positional, flags = _parse_flags(cmd_args, flags_with_values, flags_no_values)
        script = positional[0] if positional else None
        if "--strict" in flags:
            if script is None:
                _print_stderr("Error: --strict mode requires an explicit file path.")
                _print_stderr("Usage: nodus run --strict main.nd")
                return 1
            if os.path.isdir(script):
                _print_stderr("Error: --strict mode requires an explicit file path, not a directory.")
                _print_stderr("Usage: nodus run --strict main.nd")
                return 1
        trace_limit = None
        if "--trace-limit" in flags:
            try:
                trace_limit = _parse_int(str(flags["--trace-limit"]), "--trace-limit")
            except ValueError as _e:
                _print_stderr(str(_e))
                return 1
        step_limit = None
        if "--step-limit" in flags:
            try:
                step_limit = _parse_int(str(flags["--step-limit"]), "--step-limit")
            except ValueError as _e:
                _print_stderr(str(_e))
                return 1
        time_limit = None
        if "--time-limit" in flags:
            try:
                time_limit = _parse_int(str(flags["--time-limit"]), "--time-limit")
            except ValueError as _e:
                _print_stderr(str(_e))
                return 1
        output_limit = None
        if "--output-limit" in flags:
            try:
                output_limit = _parse_int(str(flags["--output-limit"]), "--output-limit")
            except ValueError as _e:
                _print_stderr(str(_e))
                return 1
        project_root, err = _resolve_project_root(flags.get("--project-root"))
        if err:
            _print_stderr(err)
            return 1
        allowed_paths = _resolve_allowed_paths(flags.get("--allow-paths"))
        trace_errors_env = str(os.environ.get("NODUS_TRACE_ERRORS", "")).strip().lower() in {"1", "true", "yes", "on"}
        return run_file(
            script,
            trace="--trace" in flags,
            trace_no_loc="--trace-no-loc" in flags,
            trace_limit=trace_limit,
            trace_filter=flags.get("--trace-filter"),
            trace_scheduler="--trace-scheduler" in flags,
            trace_events="--trace-events" in flags,
            trace_json="--trace-json" in flags,
            trace_file=flags.get("--trace-file"),
            trace_imports="--trace-imports" in flags,
            trace_errors="--trace-errors" in flags or trace_errors_env,
            optimize="--no-opt" not in flags,
            dump_bytecode="--dump-bytecode" in flags,
            project_root=project_root,
            max_steps=step_limit,
            timeout_ms=None if time_limit is None else time_limit * 1000,
            max_stdout_chars=output_limit,
            allowed_paths=allowed_paths,
        )

    if command == "check":
        if "--help" in cmd_args or "-h" in cmd_args:
            print(_COMMAND_HELP["check"])
            return 0
        flags_with_values = {"--project-root"}
        flags_no_values = {"--trace", "--trace-no-loc", "--trace-scheduler", "--trace-events", "--trace-json", "--no-opt"}
        positional, flags = _parse_flags(cmd_args, flags_with_values, flags_no_values)
        if any(flag in flags for flag in flags_no_values):
            _print_stderr("Trace flags and --no-opt are not supported with `nodus check`.")
            return 2
        script = positional[0] if positional else None
        project_root, err = _resolve_project_root(flags.get("--project-root"))
        if err:
            _print_stderr(err)
            return 1
        script, project_root, err = _resolve_run_target(script, project_root)
        if err:
            if script is None and err == "Usage: nodus run <script.nd | project-dir>":
                err = "Usage: nodus check [<script.nd | project-dir>]"
            _print_stderr(err)
            return 1
        return check_file(script, project_root=project_root)

    if command == "fmt":
        if "--help" in cmd_args or "-h" in cmd_args:
            print(_COMMAND_HELP["fmt"])
            return 0
        flags_no_values = {"--check", "--keep-trailing"}
        positional, flags = _parse_flags(cmd_args, set(), flags_no_values)
        if not positional:
            _print_stderr("Usage: nodus fmt <script.nd>")
            return 1
        script = positional[0]
        return _format_file(
            script,
            check_only="--check" in flags,
            keep_trailing="--keep-trailing" in flags,
        )

    if command == "ast":
        if "--help" in cmd_args or "-h" in cmd_args:
            print("Usage: nodus ast <script.nd> [--compact]")
            return 0
        flags_no_values = {"--compact"}
        positional, flags = _parse_flags(cmd_args, set(), flags_no_values)
        if not positional:
            _print_stderr("Usage: nodus ast <script.nd>")
            return 1
        script = positional[0]
        return ast_file(script, compact="--compact" in flags)

    if command == "dis":
        if "--help" in cmd_args or "-h" in cmd_args:
            print("Usage: nodus dis <script.nd> [--loc] [--project-root PATH]")
            return 0
        flags_with_values = {"--project-root"}
        flags_no_values = {"--loc"}
        positional, flags = _parse_flags(cmd_args, flags_with_values, flags_no_values)
        if not positional:
            _print_stderr("Usage: nodus dis <script.nd>")
            return 1
        script = positional[0]
        project_root, err = _resolve_project_root(flags.get("--project-root"))
        if err:
            _print_stderr(err)
            return 1
        return dis_file(script, include_locs="--loc" in flags, project_root=project_root)

    if command == "debug":
        if "--help" in cmd_args or "-h" in cmd_args:
            print(_COMMAND_HELP["debug"])
            return 0
        flags_with_values = {"--project-root"}
        positional, flags = _parse_flags(cmd_args, flags_with_values, set())
        if not positional:
            _print_stderr("Usage: nodus debug <script.nd> [--project-root <path>]")
            return 1
        script = positional[0]
        project_root, err = _resolve_project_root(flags.get("--project-root"))
        if err:
            _print_stderr(err)
            return 1
        return debug_file(script, project_root=project_root)

    if command == "profile":
        flags_with_values = {"--project-root", "--step-limit", "--time-limit", "--output-limit", "--allow-paths"}
        flags_no_values = {"--json", "--no-opt"}
        positional, flags = _parse_flags(cmd_args, flags_with_values, flags_no_values)
        if not positional:
            _print_stderr("Usage: nodus profile <script.nd> [--json] [--project-root <path>]")
            return 1
        script = positional[0]
        step_limit = None
        if "--step-limit" in flags:
            try:
                step_limit = _parse_int(str(flags["--step-limit"]), "--step-limit")
            except ValueError as _e:
                _print_stderr(str(_e))
                return 1
        time_limit = None
        if "--time-limit" in flags:
            try:
                time_limit = _parse_int(str(flags["--time-limit"]), "--time-limit")
            except ValueError as _e:
                _print_stderr(str(_e))
                return 1
        output_limit = None
        if "--output-limit" in flags:
            try:
                output_limit = _parse_int(str(flags["--output-limit"]), "--output-limit")
            except ValueError as _e:
                _print_stderr(str(_e))
                return 1
        project_root, err = _resolve_project_root(flags.get("--project-root"))
        if err:
            _print_stderr(err)
            return 1
        allowed_paths = _resolve_allowed_paths(flags.get("--allow-paths"))
        return profile_file(
            script,
            json_output="--json" in flags,
            project_root=project_root,
            optimize="--no-opt" not in flags,
            max_steps=step_limit,
            timeout_ms=None if time_limit is None else time_limit * 1000,
            max_stdout_chars=output_limit,
            allowed_paths=allowed_paths,
        )

    if command == "test-examples":
        return _run_examples()

    if command == "graph":
        if cmd_args and cmd_args[0] in ("--help", "-h"):
            print("\n".join([
                "Usage: nodus graph <subcommand | file> [options]",
                "",
                "Subcommands:",
                "  run <file> [--project-root PATH]",
                "             Analyze and plan the task graph defined in <file>.",
                "             Equivalent to: nodus graph <file>",
                "",
                "Direct usage (backward-compatible):",
                "  nodus graph <file> [--project-root PATH]",
                "",
                "Examples:",
                "  nodus graph tasks.nd",
                "  nodus graph run tasks.nd",
                "  nodus graph run tasks.nd --project-root /my/project",
            ]))
            return 0
        flags_with_values = {"--project-root"}
        if cmd_args and cmd_args[0] == "run":
            if len(cmd_args) > 1 and cmd_args[1] in ("--help", "-h"):
                print("Usage: nodus graph run <script.nd> [--project-root PATH]")
                return 0
            positional, flags = _parse_flags(cmd_args[1:], flags_with_values, set())
            if not positional:
                _print_stderr("Usage: nodus graph run <script.nd> [--project-root PATH]")
                return 1
            project_root, err = _resolve_project_root(flags.get("--project-root"))
            if err:
                _print_stderr(err)
                return 1
            return _plan_graph_file(positional[0], project_root=project_root)
        positional, flags = _parse_flags(cmd_args, flags_with_values, set())
        if not positional:
            _print_stderr("Usage: nodus graph <script.nd>")
            return 1
        project_root, err = _resolve_project_root(flags.get("--project-root"))
        if err:
            _print_stderr(err)
            return 1
        return _plan_graph_file(positional[0], project_root=project_root)

    if command == "serve":
        flags_with_values = {
            "--host",
            "--port",
            "--worker-sweep-interval-ms",
            "--allow-paths",
            "--auth-token",
            "--workflow-store-backend",
            "--workflow-store-path",
        }
        flags_no_values = {"--trace", "--allow-input"}
        _positional, flags = _parse_flags(cmd_args, flags_with_values, flags_no_values)
        host, port = _resolve_server_host_port(flags)
        if host is None or port is None:
            return 1
        sweep_ms = WORKER_SWEEP_INTERVAL_MS
        if "--worker-sweep-interval-ms" in flags:
            try:
                sweep_ms = _parse_int(str(flags["--worker-sweep-interval-ms"]), "--worker-sweep-interval-ms")
            except ValueError as _e:
                _print_stderr(str(_e))
                return 1
        allowed_paths = _resolve_allowed_paths(flags.get("--allow-paths"))
        auth_token = str(flags["--auth-token"]) if "--auth-token" in flags else _server_auth_token_from_env()
        allow_input = "--allow-input" in flags or _server_allow_input_from_env()
        workflow_store_backend = (
            str(flags["--workflow-store-backend"])
            if "--workflow-store-backend" in flags
            else _workflow_store_backend_from_env()
        )
        workflow_store_path = (
            str(flags["--workflow-store-path"])
            if "--workflow-store-path" in flags
            else _workflow_store_path_from_env()
        )
        return _run_server(
            host=host,
            port=port,
            trace="--trace" in flags,
            worker_sweep_interval_ms=sweep_ms,
            allowed_paths=allowed_paths,
            allow_input=allow_input,
            auth_token=auth_token,
            workflow_store_backend=workflow_store_backend,
            workflow_store_path=workflow_store_path,
        )

    if command == "lsp":
        return run_stdio_server()

    if command == "repl":
        if "--help" in cmd_args or "-h" in cmd_args:
            print(_COMMAND_HELP["repl"])
            return 0
        run_repl(_resolve_installed_version())
        return 0

    if command == "dap":
        return run_dap_stdio_server()

    if command == "snapshot":
        flags_with_values = {"--host", "--port", "--auth-token"}
        positional, flags = _parse_flags(cmd_args, flags_with_values, set())
        if not positional:
            _print_stderr("Usage: nodus snapshot <session>")
            return 1
        host, port = _resolve_server_host_port(flags)
        if host is None or port is None:
            return 1
        token = str(flags["--auth-token"]) if "--auth-token" in flags else _server_auth_token_from_env()
        return _run_snapshot(positional[0], host=host, port=port, token=token)

    if command == "snapshots":
        flags_with_values = {"--host", "--port", "--auth-token"}
        _positional, flags = _parse_flags(cmd_args, flags_with_values, set())
        host, port = _resolve_server_host_port(flags)
        if host is None or port is None:
            return 1
        token = str(flags["--auth-token"]) if "--auth-token" in flags else _server_auth_token_from_env()
        return _run_snapshots(host=host, port=port, token=token)

    if command == "restore":
        flags_with_values = {"--host", "--port", "--auth-token"}
        positional, flags = _parse_flags(cmd_args, flags_with_values, set())
        if not positional:
            _print_stderr("Usage: nodus restore <snapshot>")
            return 1
        host, port = _resolve_server_host_port(flags)
        if host is None or port is None:
            return 1
        token = str(flags["--auth-token"]) if "--auth-token" in flags else _server_auth_token_from_env()
        return _run_restore(positional[0], host=host, port=port, token=token)

    if command == "worker":
        flags_with_values = {"--host", "--port", "--auth-token"}
        _positional, flags = _parse_flags(cmd_args, flags_with_values, set())
        host, port = _resolve_server_host_port(flags)
        if host is None or port is None:
            return 1
        token = str(flags["--auth-token"]) if "--auth-token" in flags else _server_auth_token_from_env()
        return _run_worker(host, port, token=token)

    if command == "workflow":
        if not cmd_args or cmd_args[0] in ("--help", "-h"):
            print("\n".join([
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
                "             Remove old workflow snapshots.",
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
            ]))
            return 0
        subcommand = cmd_args[0]
        sub_args = cmd_args[1:]
        if subcommand == "run":
            if sub_args and sub_args[0] in ("--help", "-h"):
                print("Usage: nodus workflow run <script.nd> [--workflow NAME] [--project-root PATH]")
                return 0
            flags_with_values = {"--workflow", "--project-root"}
            positional, flags = _parse_flags(sub_args, flags_with_values, set())
            if not positional:
                _print_stderr("Usage: nodus workflow run <script.nd> [--workflow <name>]")
                return 1
            script = positional[0]
            if not os.path.isfile(script):
                _print_stderr(f"File not found: {script}")
                return 1
            project_root, err = _resolve_project_root(flags.get("--project-root"))
            if err:
                _print_stderr(err)
                return 1
            return _run_workflow(script, workflow_name=flags.get("--workflow"), project_root=project_root)
        if subcommand == "list":
            positional, flags = _parse_flags(sub_args, {"--path", "--project-root"}, set())
            project_root, err = _resolve_project_root(flags.get("--project-root") or flags.get("--path"))
            if err:
                _print_stderr(err)
                return 1
            return _workflow_list(project_root)
        if subcommand == "resume":
            positional, flags = _parse_flags(sub_args, {"--checkpoint", "--path", "--project-root"}, set())
            if not positional:
                _print_stderr("Usage: nodus workflow resume <graph_id> [--checkpoint <label>] [--project-root <path>]")
                return 1
            project_root, err = _resolve_project_root(flags.get("--project-root") or flags.get("--path"))
            if err:
                _print_stderr(err)
                return 1
            return _workflow_resume_cli(positional[0], flags.get("--checkpoint"), project_root)
        if subcommand == "dead-letters":
            positional, flags = _parse_flags(sub_args, {"--path", "--project-root"}, set())
            project_root, err = _resolve_project_root(flags.get("--project-root") or flags.get("--path"))
            if err:
                _print_stderr(err)
                return 1
            return _workflow_dead_letters(project_root)
        if subcommand == "runs":
            positional, flags = _parse_flags(
                sub_args,
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
                    "--path",
                    "--project-root",
                },
                set(),
            )
            project_root, err = _resolve_project_root(flags.get("--project-root") or flags.get("--path"))
            if err:
                _print_stderr(err)
                return 1
            statuses = None
            if "--status" in flags:
                statuses = [part.strip() for part in str(flags["--status"]).split(",") if part.strip()]
            limit = None
            if "--limit" in flags:
                try:
                    limit = _parse_int(str(flags["--limit"]), "--limit")
                except ValueError as _e:
                    _print_stderr(str(_e))
                    return 1
            offset = 0
            if "--offset" in flags:
                try:
                    offset = _parse_int(str(flags["--offset"]), "--offset")
                except ValueError as _e:
                    _print_stderr(str(_e))
                    return 1
            updated_after_ms = None
            if "--updated-after-ms" in flags:
                try:
                    updated_after_ms = _parse_float(str(flags["--updated-after-ms"]), "--updated-after-ms")
                except ValueError as _e:
                    _print_stderr(str(_e))
                    return 1
            updated_before_ms = None
            if "--updated-before-ms" in flags:
                try:
                    updated_before_ms = _parse_float(str(flags["--updated-before-ms"]), "--updated-before-ms")
                except ValueError as _e:
                    _print_stderr(str(_e))
                    return 1
            has_retry = None
            if "--has-retry" in flags:
                try:
                    has_retry = _parse_bool_flag(str(flags["--has-retry"]), "--has-retry")
                except ValueError as _e:
                    _print_stderr(str(_e))
                    return 1
            has_wait = None
            if "--has-wait" in flags:
                try:
                    has_wait = _parse_bool_flag(str(flags["--has-wait"]), "--has-wait")
                except ValueError as _e:
                    _print_stderr(str(_e))
                    return 1
            replay_count_min = None
            if "--replay-count-min" in flags:
                try:
                    replay_count_min = _parse_int(str(flags["--replay-count-min"]), "--replay-count-min")
                except ValueError as _e:
                    _print_stderr(str(_e))
                    return 1
            workflow_name = str(flags["--workflow"]) if "--workflow" in flags else None
            execution_kind = str(flags["--execution-kind"]) if "--execution-kind" in flags else None
            cursor = str(flags["--cursor"]) if "--cursor" in flags else None
            return _workflow_runs(
                project_root,
                statuses=statuses,
                workflow_name=workflow_name,
                execution_kind=execution_kind,
                updated_after_ms=updated_after_ms,
                updated_before_ms=updated_before_ms,
                has_retry=has_retry,
                has_wait=has_wait,
                replay_count_min=replay_count_min,
                limit=limit,
                offset=offset,
                cursor=cursor,
            )
        if subcommand == "inspect":
            positional, flags = _parse_flags(sub_args, {"--path", "--project-root"}, set())
            if not positional:
                _print_stderr("Usage: nodus workflow inspect <graph_id> [--project-root <path>]")
                return 1
            project_root, err = _resolve_project_root(flags.get("--project-root") or flags.get("--path"))
            if err:
                _print_stderr(err)
                return 1
            return _workflow_inspect(positional[0], project_root)
        if subcommand == "replay":
            positional, flags = _parse_flags(
                sub_args,
                {"--checkpoint", "--path", "--project-root"},
                {"--rearm-only"},
            )
            if not positional:
                _print_stderr("Usage: nodus workflow replay <graph_id> [--checkpoint <label>] [--rearm-only] [--project-root <path>]")
                return 1
            project_root, err = _resolve_project_root(flags.get("--project-root") or flags.get("--path"))
            if err:
                _print_stderr(err)
                return 1
            return _workflow_replay_cli(
                positional[0],
                flags.get("--checkpoint"),
                project_root,
                rearm_only="--rearm-only" in flags,
            )
        if subcommand == "migrate-state":
            positional, flags = _parse_flags(
                sub_args,
                {"--graph-id", "--path", "--project-root"},
                set(),
            )
            if positional:
                _print_stderr("Usage: nodus workflow migrate-state [--graph-id <id>] [--project-root <path>]")
                return 1
            project_root, err = _resolve_project_root(flags.get("--project-root") or flags.get("--path"))
            if err:
                _print_stderr(err)
                return 1
            graph_id = str(flags["--graph-id"]) if "--graph-id" in flags else None
            return _workflow_migrate_state(project_root, graph_id)
        if subcommand == "cleanup":
            flags_with_values = {"--retention-seconds", "--path", "--project-root"}
            flags_no_values = {"--force"}
            positional, flags = _parse_flags(sub_args, flags_with_values, flags_no_values)
            project_root, err = _resolve_project_root(flags.get("--project-root") or flags.get("--path"))
            if err:
                _print_stderr(err)
                return 1
            retention = None
            if "--retention-seconds" in flags:
                try:
                    retention = _parse_int(str(flags["--retention-seconds"]), "--retention-seconds")
                except ValueError as _e:
                    _print_stderr(str(_e))
                    return 1
            force = "--force" in flags
            return _workflow_cleanup(project_root, retention, force)
        _print_stderr(f"Unknown workflow command: {subcommand}")
        return 1

    if command == "workflow-run":
        flags_with_values = {"--workflow", "--project-root"}
        positional, flags = _parse_flags(cmd_args, flags_with_values, set())
        if not positional:
            _print_stderr("Usage: nodus workflow-run <script.nd> [--workflow <name>]")
            return 1
        script = positional[0]
        project_root, err = _resolve_project_root(flags.get("--project-root"))
        if err:
            _print_stderr(err)
            return 1
        return _run_workflow(script, workflow_name=flags.get("--workflow"), project_root=project_root)

    if command == "workflow-plan":
        flags_with_values = {"--workflow", "--project-root"}
        positional, flags = _parse_flags(cmd_args, flags_with_values, set())
        if not positional:
            _print_stderr("Usage: nodus workflow-plan <script.nd> [--workflow <name>]")
            return 1
        script = positional[0]
        project_root, err = _resolve_project_root(flags.get("--project-root"))
        if err:
            _print_stderr(err)
            return 1
        return _plan_workflow(script, workflow_name=flags.get("--workflow"), project_root=project_root)

    if command == "workflow-resume":
        flags_with_values = {"--checkpoint"}
        positional, flags = _parse_flags(cmd_args, flags_with_values, set())
        if not positional:
            _print_stderr("Usage: nodus workflow-resume <graph_id> [--checkpoint <label>]")
            return 1
        return _run_resume_workflow(positional[0], flags.get("--checkpoint"))

    if command == "workflow-checkpoints":
        positional, _flags = _parse_flags(cmd_args, set(), set())
        if not positional:
            _print_stderr("Usage: nodus workflow-checkpoints <graph_id>")
            return 1
        return _run_workflow_checkpoints(positional[0])

    if command == "goal-run":
        flags_with_values = {"--goal", "--project-root"}
        positional, flags = _parse_flags(cmd_args, flags_with_values, set())
        if not positional:
            _print_stderr("Usage: nodus goal-run <script.nd> [--goal <name>]")
            return 1
        script = positional[0]
        project_root, err = _resolve_project_root(flags.get("--project-root"))
        if err:
            _print_stderr(err)
            return 1
        return _run_goal(script, goal_name=flags.get("--goal"), project_root=project_root)

    if command == "goal-plan":
        flags_with_values = {"--goal", "--project-root"}
        positional, flags = _parse_flags(cmd_args, flags_with_values, set())
        if not positional:
            _print_stderr("Usage: nodus goal-plan <script.nd> [--goal <name>]")
            return 1
        script = positional[0]
        project_root, err = _resolve_project_root(flags.get("--project-root"))
        if err:
            _print_stderr(err)
            return 1
        return _plan_goal(script, goal_name=flags.get("--goal"), project_root=project_root)

    if command == "goal-resume":
        flags_with_values = {"--checkpoint"}
        positional, flags = _parse_flags(cmd_args, flags_with_values, set())
        if not positional:
            _print_stderr("Usage: nodus goal-resume <graph_id> [--checkpoint <label>]")
            return 1
        return _run_resume_goal(positional[0], flags.get("--checkpoint"))

    if command == "tool-call":
        flags_with_values = {"--json"}
        positional, flags = _parse_flags(cmd_args, flags_with_values, set())
        if not positional or "--json" not in flags:
            _print_stderr("Usage: nodus tool-call <tool> --json <payload>")
            return 1
        return _tool_call(positional[0], str(flags["--json"]))

    if command == "agent-call":
        flags_with_values = {"--json"}
        positional, flags = _parse_flags(cmd_args, flags_with_values, set())
        if not positional or "--json" not in flags:
            _print_stderr("Usage: nodus agent-call <agent> --json <payload>")
            return 1
        return _agent_call(positional[0], str(flags["--json"]))

    if command == "memory-get":
        positional, _flags = _parse_flags(cmd_args, set(), set())
        if not positional:
            _print_stderr("Usage: nodus memory-get <key>")
            return 1
        return _memory_get(positional[0])

    if command == "memory-put":
        flags_with_values = {"--json"}
        positional, flags = _parse_flags(cmd_args, flags_with_values, set())
        if not positional or "--json" not in flags:
            _print_stderr("Usage: nodus memory-put <key> --json <value>")
            return 1
        return _memory_put(positional[0], str(flags["--json"]))

    if command == "memory-delete":
        positional, _flags = _parse_flags(cmd_args, set(), set())
        if not positional:
            _print_stderr("Usage: nodus memory-delete <key>")
            return 1
        return _memory_delete(positional[0])

    if command == "memory-keys":
        return _memory_keys()

    if command in {"package-init", "init"}:
        if "--help" in cmd_args or "-h" in cmd_args:
            print(_COMMAND_HELP["init"])
            return 0
        _positional, flags = _parse_flags(cmd_args, {"--path", "--project-root"}, set())
        path = flags.get("--project-root") or flags.get("--path")
        return _package_init(path)

    if command in {"package-install", "install"}:
        _positional, flags = _parse_flags(cmd_args, {"--path", "--project-root", "--registry", "--registry-token"}, set())
        path = flags.get("--project-root") or flags.get("--path")
        registry_url = flags.get("--registry") or None
        registry_token = flags.get("--registry-token") or None
        return _package_install(path, registry_url=registry_url, registry_token=registry_token)

    if command in {"package-update", "update"}:
        _positional, flags = _parse_flags(cmd_args, {"--path", "--project-root"}, set())
        path = flags.get("--project-root") or flags.get("--path")
        return _package_update(path)

    if command == "package-list":
        _positional, flags = _parse_flags(cmd_args, {"--path", "--project-root"}, set())
        path = flags.get("--project-root") or flags.get("--path")
        return _package_list(path)

    if command == "deps":
        _positional, flags = _parse_flags(cmd_args, {"--path", "--project-root"}, set())
        path = flags.get("--project-root") or flags.get("--path")
        return _print_dependency_graph(path)

    if command == "add":
        positional, flags = _parse_flags(cmd_args, {"--path", "--project-root"}, set())
        if not positional:
            _print_stderr("Usage: nodus add <package>")
            return 1
        path = flags.get("--project-root") or flags.get("--path")
        return _package_add(positional[0], path)

    if command == "remove":
        positional, flags = _parse_flags(cmd_args, {"--path", "--project-root"}, set())
        if not positional:
            _print_stderr("Usage: nodus remove <package>")
            return 1
        path = flags.get("--project-root") or flags.get("--path")
        return _package_remove(positional[0], path)

    if command == "cache":
        positional, flags = _parse_flags(cmd_args, {"--path", "--project-root"}, set())
        if not positional or positional[0] != "clear":
            _print_stderr("Usage: nodus cache clear [--path <path>]")
            return 1
        path = flags.get("--project-root") or flags.get("--path")
        return _cache_clear(path)

    if command == "login":
        flags_with_values = {"--registry"}
        _positional, flags = _parse_flags(cmd_args, flags_with_values, set())
        registry_url = flags.get("--registry") or None
        return _run_login(registry_url=registry_url)

    if command == "logout":
        flags_with_values = {"--registry"}
        _positional, flags = _parse_flags(cmd_args, flags_with_values, set())
        registry_url = flags.get("--registry") or None
        return _run_logout(registry_url=registry_url)

    if command == "publish":
        flags_with_values = {"--registry", "--registry-token"}
        _positional, flags = _parse_flags(cmd_args, flags_with_values, set())
        registry_url = flags.get("--registry") or None
        registry_token = flags.get("--registry-token") or None
        project_root = flags.get("--project-root") or os.getcwd()
        from nodus.tooling.package_manager import publish_package_to_registry
        return publish_package_to_registry(
            project_root,
            registry_url=registry_url,
            cli_token=registry_token,
        )

    if command == "status":
        if "--help" in cmd_args or "-h" in cmd_args:
            print(_COMMAND_HELP["status"])
            return 0
        return _nodus_status()

    if command == "test":
        from nodus.testing.cli import run_test_command
        return run_test_command(cmd_args)

    _print_stderr(f"Unknown command: {command}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
