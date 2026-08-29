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
from typing import Any, Callable

from nodus.runtime.diagnostics import LangSyntaxError
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
    plan_graph_static,
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
from nodus.cli.commands import (
    KNOWN_COMMANDS,
    command_help as _command_help,
    flags_for,
    render_help as _render_help,
)
from nodus_lang_workflow.runner import get_default_workflow_runner
from nodus_lang_workflow.store import TERMINAL_RUN_STATUSES


def _read_file(path: str) -> str:
    with open(path, "r", encoding="utf-8-sig") as handle:
        return handle.read()


def _write_file(path: str, contents: str) -> None:
    # newline="" disables newline translation so the formatter's LF line
    # endings are written verbatim (no platform CRLF rewrite on Windows),
    # keeping `fmt` output idempotent across platforms.
    with open(path, "w", encoding="utf-8", newline="") as handle:
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


def _resolve_writable_paths(value: object | None) -> list[str] | None:
    """`--writable-paths`, with no environment fallback.

    `NODUS_ALLOWED_PATHS` exists to widen a default jail when the caller passed
    nothing. There is nothing to widen here -- unset means "everything readable"
    -- so an env var could only narrow, and write confinement that moves with
    ambient state is how a program works locally and is refused in production
    with no difference in the code (#467).
    """
    if value is None or not isinstance(value, str):
        return None
    raw = value.strip()
    if not raw:
        return []
    return [part.strip() for part in raw.split(os.pathsep) if part.strip()]


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
    # Delegated, not duplicated (#174): the default runner reads the same two
    # variables, and `nodus serve` honouring a backend the embedded runner
    # ignored is what made this configurable in one half of the product only.
    # Imported lazily -- `nodus_lang_workflow` at module scope here is the
    # CIRC-001 shape.
    from nodus_lang_workflow.store import workflow_store_backend_from_env

    return workflow_store_backend_from_env()


def _workflow_store_path_from_env() -> str | None:
    from nodus_lang_workflow.store import workflow_store_path_from_env

    return workflow_store_path_from_env()


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
        try:
            project = load_project_from(os.getcwd())
        except Exception as _e:
            return None, project_root, str(_e)
        if project is None:
            return None, project_root, "Usage: nodus run <script.nd | project-dir>"
        try:
            entry = project_entry_path(project)
        except Exception as _e:
            return None, project_root, str(_e)
        return entry, project_root or project.root, None
    if os.path.isdir(path):
        try:
            project = load_project(path)
            entry = project_entry_path(project)
        except Exception as _e:
            return None, project_root, str(_e)
        return entry, project_root or project.root, None
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


_HELP_FLAGS = ("--help", "-h")


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
    writable_paths: list[str] | None = None,
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
    # #342: errors that carry their own path already report a resolved one. This
    # is the fallback used by errors that carry none — a sandbox limit, say —
    # and echoing the path as typed there was the last way the same command
    # could print two path conventions depending on how it failed.
    result, _vm = run_source(
        code,
        filename=os.path.abspath(path),
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
        writable_paths=writable_paths,
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
    writable_paths: list[str] | None = None,
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
            writable_paths=writable_paths,
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
    # #342: report the resolved path, matching `nodus run` and every other error
    # site. `check` parses the entry file itself rather than through the module
    # loader, so it was the last place a syntax error echoed the path as typed
    # while the same error from `run` — or from any imported module — printed an
    # absolute one. The success line below still echoes what the user typed; it
    # is not an error location.
    result = check_source(code, filename=os.path.abspath(path), project_root=project_root)
    if not result.get("ok", False):
        _print_error(result, path=os.path.abspath(path))
        return 1
    # #609: warnings do not fail the check. An unknown type name is silently
    # ignored today and becomes an error at 6.0.0, so reporting it now is what
    # gives a project a release to fix it in.
    warnings = result.get("warnings") or []
    for warning in warnings:
        _print_stderr(
            f"{os.path.abspath(path)}:{warning['line']}:{warning['column']}: "
            f"warning: {warning['message']}"
        )
    print(f"{path}: OK" + (f" ({len(warnings)} warning(s))" if warnings else ""))
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


def _run_workflow(
    path: str,
    workflow_name: str | None = None,
    *,
    project_root: str | None = None,
    time_limit_ms: int | None = None,
) -> int:
    if not os.path.isfile(path):
        _print_stderr(f"File not found: {path}")
        return 1
    code = _read_file(path)
    result, _vm = run_workflow_code(
        VM([], {}, code_locs=[], source_path=None),
        code,
        filename=path,
        workflow_name=workflow_name,
        project_root=project_root,
        timeout_ms=EXECUTION_TIMEOUT_MS if time_limit_ms is None else time_limit_ms,
    )
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


# #499: `nodus workflow cleanup` with no retention configured used to remove
# nothing at all -- unset meant *forever*, so the store (which persists every
# run's whole program source) grew without bound unless an operator both knew
# about the env var and set it. A finite default makes the explicit cleanup
# command meaningful out of the box; nothing prunes automatically -- cleanup
# still only runs when invoked. 30 days, matching the store's
# `terminal_max_age_days`. `NODUS_WORKFLOW_RETENTION_SECONDS=0` disables
# retention-based removal (only `--force` removes then); an invalid or
# negative value falls back to the default rather than silently disabling.
DEFAULT_WORKFLOW_RETENTION_SECONDS = 30 * 24 * 60 * 60


def _default_retention_seconds() -> int:
    raw = os.environ.get("NODUS_WORKFLOW_RETENTION_SECONDS")
    if raw is None:
        return DEFAULT_WORKFLOW_RETENTION_SECONDS
    try:
        value = int(raw)
    except ValueError:
        return DEFAULT_WORKFLOW_RETENTION_SECONDS
    if value < 0:
        return DEFAULT_WORKFLOW_RETENTION_SECONDS
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
        payload: Any
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
    records_removed: list[str] = []
    with _project_root_context(project_root):
        store = get_default_workflow_runner().store
        snapshots = _task_graph.list_graph_snapshots_info()
        for snapshot in snapshots:
            graph_id = snapshot.get("graph_id")
            if not graph_id:
                continue
            should_remove = False
            if force:
                should_remove = True
            elif threshold and snapshot.get("status") in ("completed", "failed", "dead_lettered"):
                # #499: age comes from the state file's mtime, not the stored
                # `updated_at` -- that field is `runtime_time_ms()`, monotonic
                # milliseconds since *process start*, so comparing it against
                # wall-clock `now_ms` made every terminal run look ancient and
                # any configured retention removed everything regardless of
                # age. Latent while retention was opt-in-and-unset; load-bearing
                # now that there is a default.
                try:
                    mtime_ms = os.path.getmtime(_task_graph._graph_state_path(graph_id)) * 1000.0
                except OSError:
                    mtime_ms = 0.0
                if mtime_ms and now_ms - mtime_ms >= threshold * 1000:
                    should_remove = True
            if should_remove:
                _task_graph.delete_graph_state(graph_id)
                _task_graph.delete_checkpoint(graph_id)
                removed.append(graph_id)
                # #476: a run is one thing split across two stores; removing the
                # graph state while its run record survives leaves the store's
                # directory growing forever and `workflow runs` listing ghosts.
                # The record goes too -- unless it says the run is still live
                # (a waiting record over a completed snapshot is the
                # administrative `mark_waiting` shape, and live state is not
                # cleanup's to delete without --force).
                record = store.get_run(graph_id)
                if record is not None and (force or record.status in TERMINAL_RUN_STATUSES):
                    if store.delete_run(graph_id):
                        records_removed.append(graph_id)
        # #501: children go with their parent. A nested run records
        # `parent_graph_id`; a child whose parent was just removed is a record
        # nothing can attribute any more, so it cascades (and its children in
        # turn -- hence the fixpoint loop) regardless of its own age.
        removed_set = set(removed)
        progress = bool(removed_set)
        while progress:
            progress = False
            for snapshot in snapshots:
                graph_id = snapshot.get("graph_id")
                parent_id = snapshot.get("parent_graph_id")
                if not graph_id or graph_id in removed_set:
                    continue
                if isinstance(parent_id, str) and parent_id in removed_set:
                    _task_graph.delete_graph_state(graph_id)
                    _task_graph.delete_checkpoint(graph_id)
                    removed.append(graph_id)
                    removed_set.add(graph_id)
                    record = store.get_run(graph_id)
                    if record is not None and (force or record.status in TERMINAL_RUN_STATUSES):
                        if store.delete_run(graph_id):
                            records_removed.append(graph_id)
                    progress = True
    _json_print(
        {
            "removed": removed,
            "run_records_removed": records_removed,
            "retention_seconds": threshold,
            "force": force,
        }
    )
    return 0


def _run_workflow_checkpoints(graph_id: str) -> int:
    payload = workflow_checkpoints(graph_id)
    if not payload.get("ok", False):
        _print_stderr(payload.get("error", "Workflow checkpoints failed"))
        return 1
    _json_print(payload.get("checkpoints"))
    return 0


def _plan_graph_file(path: str, *, project_root: str | None = None, execute: bool = False) -> int:
    if not os.path.isfile(path):
        _print_stderr(f"File not found: {path}")
        return 1
    code = _read_file(path)
    # #400: an inspection command must not run its target. The plan comes from
    # the flow declarations alone unless --execute opts into the old behaviour
    # (needed only for graphs constructed at runtime).
    planner = plan_graph_code if execute else plan_graph_static
    result, _vm = planner(VM([], {}, code_locs=[], source_path=None), code, filename=path, project_root=project_root)
    if not result.get("ok", False):
        _print_error(result, path=path)
        return 1
    _json_print(result.get("result"))
    return 0


def _show_graph_file(
    path: str,
    *,
    fmt: str = "mermaid",
    output: str | None = None,
    project_root: str | None = None,
    execute: bool = False,
) -> int:
    """Render a plan as Mermaid or DOT rather than printing it as JSON.

    Same plan object `graph run` prints -- this only changes the projection.
    """
    from nodus.orchestration.graph_render import FORMATS, GraphRenderError, render

    if fmt not in FORMATS:
        _print_stderr(f"Unknown --format {fmt!r}. Expected one of: {', '.join(FORMATS)}")
        return 1
    if not os.path.isfile(path):
        _print_stderr(f"File not found: {path}")
        return 1
    code = _read_file(path)
    planner = plan_graph_code if execute else plan_graph_static
    result, _vm = planner(
        VM([], {}, code_locs=[], source_path=None), code, filename=path, project_root=project_root
    )
    if not result.get("ok", False):
        _print_error(result, path=path)
        return 1
    plan = result.get("result")
    if not isinstance(plan, dict):
        _print_stderr(f"Graph error at {path}: plan was not a graph object")
        return 1
    try:
        rendered = render(plan, fmt)
    except GraphRenderError as exc:
        _print_stderr(f"Graph error at {path}: {exc}")
        return 1
    if output:
        try:
            _write_file(output, rendered + "\n")
        except OSError as exc:
            _print_stderr(f"Could not write {output}: {exc}")
            return 1
        print(f"Wrote {fmt} graph to {output}")
    else:
        print(rendered)
    return 0


def _run_server(
    *,
    host: str = SERVER_HOST,
    port: int = SERVER_PORT,
    trace: bool = False,
    worker_sweep_interval_ms: int = WORKER_SWEEP_INTERVAL_MS,
    allowed_paths: list[str] | None = None,
    writable_paths: list[str] | None = None,
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
            writable_paths=writable_paths,
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
    try:
        formatted = format_source(original, keep_trailing_comments=keep_trailing)
    except LangSyntaxError as e:
        location = path
        if e.line is not None and e.col is not None:
            location = f"{path}:{e.line}:{e.col}"
        elif e.line is not None:
            location = f"{path}:{e.line}"
        _print_stderr(f"Syntax error at {location}: {e}")
        return 1
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


def _print_stability() -> int:
    """Print the language stability surface index."""
    print("\n".join([
        "Nodus Language Stability Index",
        "=" * 46,
        "",
        "STABLE -- frozen behavior; breaking changes require a major version bump",
        "  Core language:  let, fn, if/while/for, try/catch/finally, throw, return",
        "  Types:          number, int, string, bool, nil, list, map, record",
        "  Operators:      all arithmetic, comparison, logical operators",
        "  Imports/exports: syntax stable; module caching semantics stable",
        "  Error model:    err record shape {kind, message, payload, path, line, column}",
        "  VM:             bytecode format (BYTECODE_VERSION=4), opcode set frozen",
        "  Embedding API:  NodusRuntime constructor, run_source, run_file,",
        "                  register_function, tool_registry, reset, shutdown",
        "  Standard I/O:   std:json, std:fs",
        "",
        "MOSTLY STABLE -- minor refinements may occur; breakage avoided but not guaranteed",
        "  Standard library: std:math, std:strings, std:collections, std:path",
        "  Iteration protocol: for name in iterable",
        "  yield expr",
        "",
        "EXPERIMENTAL -- behavior may change in any release; track CHANGELOG.md",
        "  Coroutines:       coroutine(), spawn(), resume(), run_loop()  [Phase B]",
        "  Channels:         channel(), send(), recv(), close()          [Phase B]",
        "  Workflow DSL:     workflow, step, state, checkpoint            [Phase D]",
        "  Goal DSL:         goal, step, run_goal, resume_goal            [Phase C]",
        "  Static types:     type annotations accepted; no enforcement    [forward: --strict]",
        "  AI-native stdlib: std:tool, std:identity, std:effects, std:sys,",
        "                    std:memory, std:retry, std:circuit_breaker",
        "  Other stdlib:     std:http, std:subprocess, std:time, std:hash,",
        "                    std:encoding, std:secrets, std:test",
        "  Projects/packages: nodus.toml, nodus install (git-backed only)",
        "",
        "NOT YET IMPLEMENTED",
        "  break / continue inside loops",
        "  nodus check --strict (type enforcement)",
        "",
        "Full index: docs/governance/LANGUAGE_STABILITY_INDEX.md",
        "Graduation plan for experimental surfaces: /nodus-scheduler-freeze,",
        "  /nodus-goal-freeze, /nodus-workflow-freeze (see .claude/commands/)",
    ]))
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
    known_commands = KNOWN_COMMANDS

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

    # #353: --help is handled here, centrally, before any subcommand body runs.
    # It used to be each command's own responsibility, so every new subcommand
    # shipped unguarded and the fixes landed one command at a time (#1/#2, then
    # #268, then #345, then the whole package-manager group). That was not a
    # cosmetic problem: `nodus logout --help` performed the logout and deleted
    # the saved registry token, `nodus publish --help` crashed with an unhandled
    # traceback, and `nodus login --help` blocked on stdin. --help must never
    # mutate state. Do not re-add per-command guards below; this one covers them.
    if any(flag in cmd_args for flag in _HELP_FLAGS):
        print(_command_help(command))
        return 0

    if command == "run":
        flags_with_values, flags_no_values = flags_for("run")
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
        writable_paths = _resolve_writable_paths(flags.get("--writable-paths"))
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
            writable_paths=writable_paths,
        )

    if command == "check":
        flags_with_values, flags_no_values = flags_for("check")
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
        if script is None:
            _print_stderr("Usage: nodus check [<script.nd | project-dir>]")
            return 1
        return check_file(script, project_root=project_root)

    if command == "fmt":
        flags_with_values, flags_no_values = flags_for("fmt")
        positional, flags = _parse_flags(cmd_args, flags_with_values, flags_no_values)
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
        flags_with_values, flags_no_values = flags_for("ast")
        positional, flags = _parse_flags(cmd_args, flags_with_values, flags_no_values)
        if not positional:
            _print_stderr("Usage: nodus ast <script.nd>")
            return 1
        script = positional[0]
        return ast_file(script, compact="--compact" in flags)

    if command == "dis":
        flags_with_values, flags_no_values = flags_for("dis")
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
        flags_with_values, flags_no_values = flags_for("debug")
        positional, flags = _parse_flags(cmd_args, flags_with_values, flags_no_values)
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
        flags_with_values, flags_no_values = flags_for("profile")
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
        writable_paths = _resolve_writable_paths(flags.get("--writable-paths"))
        return profile_file(
            script,
            json_output="--json" in flags,
            project_root=project_root,
            optimize="--no-opt" not in flags,
            max_steps=step_limit,
            timeout_ms=None if time_limit is None else time_limit * 1000,
            max_stdout_chars=output_limit,
            allowed_paths=allowed_paths,
            writable_paths=writable_paths,
        )

    if command == "test-examples":
        return _run_examples()

    if command == "graph":
        if cmd_args and cmd_args[0] == "show":
            positional, flags = _parse_flags(cmd_args[1:], *flags_for("graph", "show"))
            if not positional:
                _print_stderr(
                    "Usage: nodus graph show <script.nd> [--format mermaid|dot] [--output FILE]"
                )
                return 1
            project_root, err = _resolve_project_root(flags.get("--project-root"))
            if err:
                _print_stderr(err)
                return 1
            return _show_graph_file(
                positional[0],
                fmt=str(flags.get("--format") or "mermaid"),
                output=flags.get("--output"),  # type: ignore[arg-type]
                project_root=project_root,
                execute="--execute" in flags,
            )
        if cmd_args and cmd_args[0] == "run":
            if len(cmd_args) > 1 and cmd_args[1] in ("--help", "-h"):
                print("Usage: nodus graph run <script.nd> [--project-root PATH]")
                return 0
            positional, flags = _parse_flags(cmd_args[1:], *flags_for("graph", "run"))
            if not positional:
                _print_stderr("Usage: nodus graph run <script.nd> [--project-root PATH]")
                return 1
            project_root, err = _resolve_project_root(flags.get("--project-root"))
            if err:
                _print_stderr(err)
                return 1
            return _plan_graph_file(positional[0], project_root=project_root, execute="--execute" in flags)
        # Backward-compatible bare form: `nodus graph <file>` == `graph run <file>`.
        positional, flags = _parse_flags(cmd_args, *flags_for("graph", "run"))
        if not positional:
            _print_stderr("Usage: nodus graph <script.nd>")
            return 1
        project_root, err = _resolve_project_root(flags.get("--project-root"))
        if err:
            _print_stderr(err)
            return 1
        return _plan_graph_file(positional[0], project_root=project_root, execute="--execute" in flags)

    if command == "serve":
        flags_with_values, flags_no_values = flags_for("serve")
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
        writable_paths = _resolve_writable_paths(flags.get("--writable-paths"))
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
            writable_paths=writable_paths,
            allow_input=allow_input,
            auth_token=auth_token,
            workflow_store_backend=workflow_store_backend,
            workflow_store_path=workflow_store_path,
        )

    if command == "lsp":
        return run_stdio_server()

    if command == "repl":
        run_repl(_resolve_installed_version())
        return 0

    if command == "dap":
        return run_dap_stdio_server()

    if command == "snapshot":
        positional, flags = _parse_flags(cmd_args, *flags_for("snapshot"))
        if not positional:
            _print_stderr("Usage: nodus snapshot <session>")
            return 1
        host, port = _resolve_server_host_port(flags)
        if host is None or port is None:
            return 1
        token = str(flags["--auth-token"]) if "--auth-token" in flags else _server_auth_token_from_env()
        return _run_snapshot(positional[0], host=host, port=port, token=token)

    if command == "snapshots":
        _positional, flags = _parse_flags(cmd_args, *flags_for("snapshots"))
        host, port = _resolve_server_host_port(flags)
        if host is None or port is None:
            return 1
        token = str(flags["--auth-token"]) if "--auth-token" in flags else _server_auth_token_from_env()
        return _run_snapshots(host=host, port=port, token=token)

    if command == "restore":
        positional, flags = _parse_flags(cmd_args, *flags_for("restore"))
        if not positional:
            _print_stderr("Usage: nodus restore <snapshot>")
            return 1
        host, port = _resolve_server_host_port(flags)
        if host is None or port is None:
            return 1
        token = str(flags["--auth-token"]) if "--auth-token" in flags else _server_auth_token_from_env()
        return _run_restore(positional[0], host=host, port=port, token=token)

    if command == "worker":
        _positional, flags = _parse_flags(cmd_args, *flags_for("worker"))
        host, port = _resolve_server_host_port(flags)
        if host is None or port is None:
            return 1
        token = str(flags["--auth-token"]) if "--auth-token" in flags else _server_auth_token_from_env()
        return _run_worker(host, port, token=token)

    if command == "workflow":
        if not cmd_args:
            print(_command_help("workflow"))
            return 0
        subcommand = cmd_args[0]
        sub_args = cmd_args[1:]
        if subcommand == "run":
            if sub_args and sub_args[0] in ("--help", "-h"):
                print("Usage: nodus workflow run <script.nd> [--workflow NAME] [--project-root PATH]")
                return 0
            positional, flags = _parse_flags(sub_args, *flags_for("workflow", "run"))
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
            positional, flags = _parse_flags(sub_args, *flags_for("workflow", "list"))
            project_root, err = _resolve_project_root(flags.get("--project-root") or flags.get("--path"))
            if err:
                _print_stderr(err)
                return 1
            return _workflow_list(project_root)
        if subcommand == "resume":
            positional, flags = _parse_flags(sub_args, *flags_for("workflow", "resume"))
            if not positional:
                _print_stderr("Usage: nodus workflow resume <graph_id> [--checkpoint <label>] [--project-root <path>]")
                return 1
            project_root, err = _resolve_project_root(flags.get("--project-root") or flags.get("--path"))
            if err:
                _print_stderr(err)
                return 1
            return _workflow_resume_cli(positional[0], flags.get("--checkpoint"), project_root)
        if subcommand == "dead-letters":
            positional, flags = _parse_flags(sub_args, *flags_for("workflow", "dead-letters"))
            project_root, err = _resolve_project_root(flags.get("--project-root") or flags.get("--path"))
            if err:
                _print_stderr(err)
                return 1
            return _workflow_dead_letters(project_root)
        if subcommand == "runs":
            positional, flags = _parse_flags(sub_args, *flags_for("workflow", "runs"))
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
            positional, flags = _parse_flags(sub_args, *flags_for("workflow", "inspect"))
            if not positional:
                _print_stderr("Usage: nodus workflow inspect <graph_id> [--project-root <path>]")
                return 1
            project_root, err = _resolve_project_root(flags.get("--project-root") or flags.get("--path"))
            if err:
                _print_stderr(err)
                return 1
            return _workflow_inspect(positional[0], project_root)
        if subcommand == "replay":
            positional, flags = _parse_flags(sub_args, *flags_for("workflow", "replay"))
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
            positional, flags = _parse_flags(sub_args, *flags_for("workflow", "migrate-state"))
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
            positional, flags = _parse_flags(sub_args, *flags_for("workflow", "cleanup"))
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
        flags_with_values, flags_no_values = flags_for("workflow-run")
        positional, flags = _parse_flags(cmd_args, flags_with_values, flags_no_values)
        if not positional:
            _print_stderr("Usage: nodus workflow-run <script.nd> [--workflow <name>] [--time-limit <ms>]")
            return 1
        script = positional[0]
        project_root, err = _resolve_project_root(flags.get("--project-root"))
        if err:
            _print_stderr(err)
            return 1
        # `--time-limit` was missing here while `run`, `check`, `debug` and
        # `profile` all had it, and #392 made that gap bite: step retries are now
        # taken in-process, so a `with { retries: N }` step spends the wall-clock
        # budget it used to defer out of. Three attempts of a trivial step cost
        # ~110 ms against the 200 ms default — measured, idle machine — so a real
        # step with real work exceeds it and there was no flag to raise it.
        time_limit = None
        if "--time-limit" in flags:
            try:
                time_limit = _parse_int(str(flags["--time-limit"]), "--time-limit")
            except ValueError as exc:
                _print_stderr(str(exc))
                return 1
        return _run_workflow(
            script,
            workflow_name=flags.get("--workflow"),
            project_root=project_root,
            time_limit_ms=time_limit,
        )

    if command == "workflow-plan":
        flags_with_values, flags_no_values = flags_for("workflow-plan")
        positional, flags = _parse_flags(cmd_args, flags_with_values, flags_no_values)
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
        flags_with_values, flags_no_values = flags_for("workflow-resume")
        positional, flags = _parse_flags(cmd_args, flags_with_values, flags_no_values)
        if not positional:
            _print_stderr("Usage: nodus workflow-resume <graph_id> [--checkpoint <label>]")
            return 1
        return _run_resume_workflow(positional[0], flags.get("--checkpoint"))

    if command == "workflow-checkpoints":
        positional, _flags = _parse_flags(cmd_args, *flags_for("workflow-checkpoints"))
        if not positional:
            _print_stderr("Usage: nodus workflow-checkpoints <graph_id>")
            return 1
        return _run_workflow_checkpoints(positional[0])

    if command == "goal-run":
        flags_with_values, flags_no_values = flags_for("goal-run")
        positional, flags = _parse_flags(cmd_args, flags_with_values, flags_no_values)
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
        flags_with_values, flags_no_values = flags_for("goal-plan")
        positional, flags = _parse_flags(cmd_args, flags_with_values, flags_no_values)
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
        flags_with_values, flags_no_values = flags_for("goal-resume")
        positional, flags = _parse_flags(cmd_args, flags_with_values, flags_no_values)
        if not positional:
            _print_stderr("Usage: nodus goal-resume <graph_id> [--checkpoint <label>]")
            return 1
        return _run_resume_goal(positional[0], flags.get("--checkpoint"))

    if command == "tool-call":
        flags_with_values, flags_no_values = flags_for("tool-call")
        positional, flags = _parse_flags(cmd_args, flags_with_values, flags_no_values)
        if not positional or "--json" not in flags:
            _print_stderr("Usage: nodus tool-call <tool> --json <payload>")
            return 1
        return _tool_call(positional[0], str(flags["--json"]))

    if command == "agent-call":
        flags_with_values, flags_no_values = flags_for("agent-call")
        positional, flags = _parse_flags(cmd_args, flags_with_values, flags_no_values)
        if not positional or "--json" not in flags:
            _print_stderr("Usage: nodus agent-call <agent> --json <payload>")
            return 1
        return _agent_call(positional[0], str(flags["--json"]))

    if command == "memory-get":
        positional, _flags = _parse_flags(cmd_args, *flags_for("memory-get"))
        if not positional:
            _print_stderr("Usage: nodus memory-get <key>")
            return 1
        return _memory_get(positional[0])

    if command == "memory-put":
        flags_with_values, flags_no_values = flags_for("memory-put")
        positional, flags = _parse_flags(cmd_args, flags_with_values, flags_no_values)
        if not positional or "--json" not in flags:
            _print_stderr("Usage: nodus memory-put <key> --json <value>")
            return 1
        return _memory_put(positional[0], str(flags["--json"]))

    if command == "memory-delete":
        positional, _flags = _parse_flags(cmd_args, *flags_for("memory-delete"))
        if not positional:
            _print_stderr("Usage: nodus memory-delete <key>")
            return 1
        return _memory_delete(positional[0])

    if command == "memory-keys":
        return _memory_keys()

    if command in {"package-init", "init"}:
        _positional, flags = _parse_flags(cmd_args, *flags_for("init"))
        path = flags.get("--project-root") or flags.get("--path")
        return _package_init(path)

    if command in {"package-install", "install"}:
        _positional, flags = _parse_flags(cmd_args, *flags_for("install"))
        path = flags.get("--project-root") or flags.get("--path")
        registry_url = flags.get("--registry") or None
        registry_token = flags.get("--registry-token") or None
        return _package_install(path, registry_url=registry_url, registry_token=registry_token)

    if command in {"package-update", "update"}:
        _positional, flags = _parse_flags(cmd_args, *flags_for("update"))
        path = flags.get("--project-root") or flags.get("--path")
        return _package_update(path)

    if command == "package-list":
        _positional, flags = _parse_flags(cmd_args, *flags_for("package-list"))
        path = flags.get("--project-root") or flags.get("--path")
        return _package_list(path)

    if command == "deps":
        _positional, flags = _parse_flags(cmd_args, *flags_for("deps"))
        path = flags.get("--project-root") or flags.get("--path")
        return _print_dependency_graph(path)

    if command == "add":
        positional, flags = _parse_flags(cmd_args, *flags_for("add"))
        if not positional:
            _print_stderr("Usage: nodus add <package>")
            return 1
        path = flags.get("--project-root") or flags.get("--path")
        return _package_add(positional[0], path)

    if command == "remove":
        positional, flags = _parse_flags(cmd_args, *flags_for("remove"))
        if not positional:
            _print_stderr("Usage: nodus remove <package>")
            return 1
        path = flags.get("--project-root") or flags.get("--path")
        return _package_remove(positional[0], path)

    if command == "cache":
        positional, flags = _parse_flags(cmd_args, *flags_for("cache"))
        if not positional or positional[0] != "clear":
            _print_stderr("Usage: nodus cache clear [--path <path>]")
            return 1
        path = flags.get("--project-root") or flags.get("--path")
        return _cache_clear(path)

    if command == "login":
        flags_with_values, flags_no_values = flags_for("login")
        _positional, flags = _parse_flags(cmd_args, flags_with_values, flags_no_values)
        registry_url = flags.get("--registry") or None
        return _run_login(registry_url=registry_url)

    if command == "logout":
        flags_with_values, flags_no_values = flags_for("logout")
        _positional, flags = _parse_flags(cmd_args, flags_with_values, flags_no_values)
        registry_url = flags.get("--registry") or None
        return _run_logout(registry_url=registry_url)

    if command == "publish":
        flags_with_values, flags_no_values = flags_for("publish")
        _positional, flags = _parse_flags(cmd_args, flags_with_values, flags_no_values)
        registry_url = flags.get("--registry") or None
        registry_token = flags.get("--registry-token") or None
        project_root = flags.get("--project-root") or os.getcwd()
        from nodus.tooling.package_manager import publish_package_to_registry
        return publish_package_to_registry(
            project_root,
            registry_url=registry_url,
            cli_token=registry_token,
        )

    if command == "completion":
        from nodus.cli.completion import SHELLS, CompletionError, generate

        positional, _flags = _parse_flags(cmd_args, *flags_for("completion"))
        if not positional:
            _print_stderr(f"Usage: nodus completion <{'|'.join(SHELLS)}>")
            return 1
        try:
            script = generate(positional[0])
        except CompletionError as exc:
            _print_stderr(f"Error: {exc}")
            return 1
        # Write bytes, not text. On Windows a text-mode stdout rewrites "\n"
        # as "\r\n", and `nodus completion bash > nodus.bash` then produces a
        # file bash rejects with `syntax error near unexpected token $'{\r'`.
        # The shell scripts must keep LF endings on every platform.
        buffer = getattr(sys.stdout, "buffer", None)
        if buffer is not None:
            buffer.write(script.encode("utf-8"))
            buffer.flush()
        else:  # a redirected/captured stdout with no byte layer
            sys.stdout.write(script)
        return 0

    if command == "docs":
        from nodus.cli.docs import format_report as format_docs, report as docs_report

        _positional, flags = _parse_flags(cmd_args, *flags_for("docs"))
        data = docs_report()
        if "--json" in flags:
            _json_print(data)
        else:
            print(format_docs(data))
        return 0

    if command == "doctor":
        from nodus.cli.doctor import format_report, run_checks, to_json

        _positional, flags = _parse_flags(cmd_args, *flags_for("doctor"))
        checks = run_checks()
        report = to_json(checks)
        if "--json" in flags:
            _json_print(report)
        else:
            print(format_report(checks))
        return 0 if report["ok"] else 1

    if command == "status":
        return _nodus_status()

    if command == "test":
        from nodus.testing.cli import run_test_command
        return run_test_command(cmd_args)

    if command == "stability":
        return _print_stability()

    _print_stderr(f"Unknown command: {command}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
