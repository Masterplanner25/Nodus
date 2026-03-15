"""CLI entrypoints for Nodus."""

from __future__ import annotations

import http.client
import json
import os
import sys
import time
from pathlib import Path
from typing import Callable

from nodus.runtime.errors import format_error_payload
from nodus.runtime.bytecode_cache import clear_bytecode_cache
from nodus.runtime.profiler import Profiler
from nodus.dap.server import run_stdio_server as run_dap_stdio_server
from nodus.lsp.server import run_stdio_server
from nodus.tooling.formatter import format_source
from nodus.tooling import package_manager as _package_manager
from nodus.tooling.project import load_project, load_project_from, project_entry_path
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


def _read_file(path: str) -> str:
    with open(path, "r", encoding="utf-8") as handle:
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


def _resolve_run_target(path: str | None, project_root: str | None) -> tuple[str | None, str | None, str | None]:
    if path is None:
        project = load_project_from(os.getcwd())
        if project is None:
            return None, project_root, "Usage: nodus run <script.nd | project-dir>"
        return project_entry_path(project), project_root or project.root, None
    if os.path.isdir(path):
        try:
            project = load_project(path)
        except Exception as err:
            return None, project_root, str(err)
        return project_entry_path(project), project_root or project.root, None
    resolved_root = project_root
    if resolved_root is None:
        project = load_project_from(os.path.dirname(os.path.abspath(path)) or os.getcwd())
        if project is not None:
            resolved_root = project.root
    return path, resolved_root, None


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


def _render_help() -> str:
    return "\n".join(
        [
            "Usage: nodus <command> [options] [file]",
            "",
            "Commands:",
            "  nodus run [<file|project-dir>] [--trace --trace-no-loc --trace-limit N --trace-filter STR --trace-scheduler --trace-events --dump-bytecode --no-opt --project-root PATH --step-limit N --time-limit SECS --output-limit N]",
            "  nodus check <file> [--project-root PATH]",
            "  nodus fmt <file> [--check] [--keep-trailing]",
            "  nodus ast <file> [--compact]",
            "  nodus dis <file> [--loc]",
            "  nodus debug <file>",
            "  nodus profile <file> [--json] [--project-root PATH] [--allow-paths PATHS]",
            "  nodus test-examples",
            "  nodus graph <file> [--project-root PATH]",
            "  nodus serve [--host HOST --port PORT --trace --worker-sweep-interval-ms N --allow-paths PATHS --auth-token TOKEN --allow-input]",
            "  nodus lsp",
            "  nodus dap",
            "  nodus snapshot <session> [--host HOST --port PORT --auth-token TOKEN]",
            "  nodus snapshots [--host HOST --port PORT --auth-token TOKEN]",
            "  nodus restore <snapshot> [--host HOST --port PORT --auth-token TOKEN]",
            "  nodus worker [--host HOST --port PORT --auth-token TOKEN]",
            "  nodus workflow-run <file> [--workflow NAME]",
            "  nodus workflow-plan <file> [--workflow NAME]",
            "  nodus workflow-resume <graph_id> [--checkpoint LABEL]",
            "  nodus workflow-checkpoints <graph_id>",
            "  nodus goal-run <file> [--goal NAME]",
            "  nodus goal-plan <file> [--goal NAME]",
            "  nodus goal-resume <graph_id> [--checkpoint LABEL]",
            "  nodus tool-call <tool> --json <payload>",
            "  nodus agent-call <agent> --json <payload>",
            "  nodus memory-get <key>",
            "  nodus memory-put <key> --json <value>",
            "  nodus memory-delete <key>",
            "  nodus memory-keys",
            "  nodus package-init [--path PATH]",
            "  nodus install [--path PATH]",
            "  nodus update [--path PATH]",
            "  nodus add <package> [--path PATH]",
            "  nodus remove <package> [--path PATH]",
            "  nodus package-list [--path PATH]",
            "  nodus cache clear [--path PATH]",
            "",
            "Global options:",
            "  --version",
            "  --help",
        ]
    )


def _print_result_output(result: dict) -> None:
    stdout = result.get("stdout") or ""
    stderr = result.get("stderr") or ""
    if stdout:
        print(stdout, end="")
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
    optimize: bool = True,
    dump_bytecode: bool = False,
    project_root: str | None = None,
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
        )
    except ValueError as err:
        _print_stderr(str(err))
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
    except json.JSONDecodeError as err:
        _print_stderr(f"Invalid JSON payload: {err}")
        return 1
    result = tool_call_result(name, args)
    _json_print(result)
    return 0 if result.get("ok", False) else 1


def _agent_call(name: str, payload_json: str) -> int:
    try:
        payload = _json_load(payload_json)
    except json.JSONDecodeError as err:
        _print_stderr(f"Invalid JSON payload: {err}")
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
    except json.JSONDecodeError as err:
        _print_stderr(f"Invalid JSON value: {err}")
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
        if formatted != original:
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


def _package_init(path: str | None) -> int:
    root = path or os.getcwd()
    try:
        _package_manager.init_project(root)
    except Exception as err:
        _print_stderr(str(err))
        return 1
    return 0


def _package_install(path: str | None) -> int:
    root = path or os.getcwd()
    try:
        _package_manager.install_dependencies_for_project(root, update=False)
    except Exception as err:
        _print_stderr(str(err))
        return 1
    return 0


def _package_update(path: str | None) -> int:
    root = path or os.getcwd()
    try:
        _package_manager.install_dependencies_for_project(root, update=True)
    except Exception as err:
        _print_stderr(str(err))
        return 1
    return 0


def _package_list(path: str | None) -> int:
    root = path or os.getcwd()
    try:
        deps = _package_manager.list_dependencies(root)
    except Exception as err:
        _print_stderr(str(err))
        return 1
    for name, status in deps:
        print(f"{name}: {status}")
    return 0


def _package_add(package_name: str, path: str | None) -> int:
    root = path or os.getcwd()
    try:
        _package_manager.add_dependency(root, package_name)
    except Exception as err:
        _print_stderr(str(err))
        return 1
    return 0


def _package_remove(package_name: str, path: str | None) -> int:
    root = path or os.getcwd()
    try:
        _package_manager.remove_dependency(root, package_name)
    except Exception as err:
        _print_stderr(str(err))
        return 1
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

    if "--help" in args or "-h" in args:
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
        "test-examples",
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
        flags_with_values = {"--trace-limit", "--trace-filter", "--trace-file", "--project-root", "--step-limit", "--time-limit", "--output-limit", "--allow-paths"}
        flags_no_values = {
            "--trace",
            "--trace-no-loc",
            "--trace-scheduler",
            "--trace-events",
            "--trace-json",
            "--no-opt",
            "--dump-bytecode",
        }
        positional, flags = _parse_flags(cmd_args, flags_with_values, flags_no_values)
        script = positional[0] if positional else None
        trace_limit = None
        if "--trace-limit" in flags:
            try:
                trace_limit = _parse_int(str(flags["--trace-limit"]), "--trace-limit")
            except ValueError as err:
                _print_stderr(str(err))
                return 1
        step_limit = None
        if "--step-limit" in flags:
            try:
                step_limit = _parse_int(str(flags["--step-limit"]), "--step-limit")
            except ValueError as err:
                _print_stderr(str(err))
                return 1
        time_limit = None
        if "--time-limit" in flags:
            try:
                time_limit = _parse_int(str(flags["--time-limit"]), "--time-limit")
            except ValueError as err:
                _print_stderr(str(err))
                return 1
        output_limit = None
        if "--output-limit" in flags:
            try:
                output_limit = _parse_int(str(flags["--output-limit"]), "--output-limit")
            except ValueError as err:
                _print_stderr(str(err))
                return 1
        project_root, err = _resolve_project_root(flags.get("--project-root"))
        if err:
            _print_stderr(err)
            return 1
        allowed_paths = _resolve_allowed_paths(flags.get("--allow-paths"))
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
            optimize="--no-opt" not in flags,
            dump_bytecode="--dump-bytecode" in flags,
            project_root=project_root,
            max_steps=step_limit,
            timeout_ms=None if time_limit is None else time_limit * 1000,
            max_stdout_chars=output_limit,
            allowed_paths=allowed_paths,
        )

    if command == "check":
        flags_with_values = {"--project-root"}
        flags_no_values = {"--trace", "--trace-no-loc", "--trace-scheduler", "--trace-events", "--trace-json", "--no-opt"}
        positional, flags = _parse_flags(cmd_args, flags_with_values, flags_no_values)
        if not positional:
            _print_stderr("Usage: nodus check <script.nd>")
            return 1
        if any(flag in flags for flag in flags_no_values):
            _print_stderr("Trace flags and --no-opt are not supported with `nodus check`.")
            return 2
        script = positional[0]
        project_root, err = _resolve_project_root(flags.get("--project-root"))
        if err:
            _print_stderr(err)
            return 1
        return check_file(script, project_root=project_root)

    if command == "fmt":
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
        flags_no_values = {"--compact"}
        positional, flags = _parse_flags(cmd_args, set(), flags_no_values)
        if not positional:
            _print_stderr("Usage: nodus ast <script.nd>")
            return 1
        script = positional[0]
        return ast_file(script, compact="--compact" in flags)

    if command == "dis":
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
            except ValueError as err:
                _print_stderr(str(err))
                return 1
        time_limit = None
        if "--time-limit" in flags:
            try:
                time_limit = _parse_int(str(flags["--time-limit"]), "--time-limit")
            except ValueError as err:
                _print_stderr(str(err))
                return 1
        output_limit = None
        if "--output-limit" in flags:
            try:
                output_limit = _parse_int(str(flags["--output-limit"]), "--output-limit")
            except ValueError as err:
                _print_stderr(str(err))
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
        flags_with_values = {"--project-root"}
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
        flags_with_values = {"--host", "--port", "--worker-sweep-interval-ms", "--allow-paths", "--auth-token"}
        flags_no_values = {"--trace", "--allow-input"}
        _positional, flags = _parse_flags(cmd_args, flags_with_values, flags_no_values)
        host, port = _resolve_server_host_port(flags)
        if host is None or port is None:
            return 1
        sweep_ms = WORKER_SWEEP_INTERVAL_MS
        if "--worker-sweep-interval-ms" in flags:
            try:
                sweep_ms = _parse_int(str(flags["--worker-sweep-interval-ms"]), "--worker-sweep-interval-ms")
            except ValueError as err:
                _print_stderr(str(err))
                return 1
        allowed_paths = _resolve_allowed_paths(flags.get("--allow-paths"))
        auth_token = str(flags["--auth-token"]) if "--auth-token" in flags else _server_auth_token_from_env()
        allow_input = "--allow-input" in flags or _server_allow_input_from_env()
        return _run_server(
            host=host,
            port=port,
            trace="--trace" in flags,
            worker_sweep_interval_ms=sweep_ms,
            allowed_paths=allowed_paths,
            allow_input=allow_input,
            auth_token=auth_token,
        )

    if command == "lsp":
        return run_stdio_server()

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
        _positional, flags = _parse_flags(cmd_args, {"--path", "--project-root"}, set())
        path = flags.get("--project-root") or flags.get("--path")
        return _package_init(path)

    if command in {"package-install", "install"}:
        _positional, flags = _parse_flags(cmd_args, {"--path", "--project-root"}, set())
        path = flags.get("--project-root") or flags.get("--path")
        return _package_install(path)

    if command in {"package-update", "update"}:
        _positional, flags = _parse_flags(cmd_args, {"--path", "--project-root"}, set())
        path = flags.get("--project-root") or flags.get("--path")
        return _package_update(path)

    if command in {"package-list", "deps"}:
        _positional, flags = _parse_flags(cmd_args, {"--path", "--project-root"}, set())
        path = flags.get("--project-root") or flags.get("--path")
        return _package_list(path)

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

    _print_stderr(f"Unknown command: {command}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
