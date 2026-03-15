"""Execution helpers for Nodus service mode."""

from __future__ import annotations

import os

from nodus.frontend.ast.ast_printer import format_ast
from nodus.frontend.ast.ast_serializer import ast_to_dict
from nodus.compiler.compiler import format_bytecode, build_disassembly
from nodus.runtime.diagnostics import LangSyntaxError
from nodus.runtime.errors import coerce_error, legacy_error_dict, NodusRuntimeError
from nodus.runtime.module_loader import ModuleLoader
from nodus.tooling.debugger import Debugger, DebuggerQuit
from nodus.frontend.parser import Parser
from nodus.frontend.lexer import tokenize
from nodus.vm.vm import VM
from nodus.support.config import EXECUTION_TIMEOUT_MS, MAX_STEPS, MAX_STDOUT_CHARS
from nodus.orchestration.task_graph import set_default_dispatcher, load_graph_state, get_registered_vm
from nodus.runtime.runtime_events import RuntimeEventBus, HumanReadableEventSink, JsonEventSink
from nodus.tooling.sandbox import capture_output, configure_vm_limits
from nodus.result import Result, normalize_filename
from nodus.orchestration.workflow_lowering import find_goal_value, find_workflow_value, goal_name_candidates, workflow_name_candidates
from nodus.orchestration.workflow_state import checkpoints_public
from nodus.services.tool_runtime import call_tool
from nodus.services.agent_runtime import call_agent
from nodus.services.memory_runtime import delete_value, export_memory, get_value, list_keys, put_value


def _resolve_import_state(import_state: dict | None, project_root: str | None) -> dict | None:
    if import_state is None and project_root is None:
        return None
    if import_state is None:
        return {
            "loaded": set(),
            "loading": set(),
            "exports": {},
            "modules": {},
            "module_ids": {},
            "project_root": project_root,
        }
    if project_root is not None:
        import_state["project_root"] = project_root
    elif "project_root" not in import_state:
        import_state["project_root"] = None
    return import_state


def _prepare_event_bus(
    *,
    trace_events: bool = False,
    trace_json: bool = False,
    trace_file: str | None = None,
):
    if not (trace_events or trace_json or trace_file):
        return None, None
    event_bus = RuntimeEventBus()
    event_file = None

    def stdout_writer(line: str) -> None:
        print(line)

    if trace_events:
        event_bus.add_sink(HumanReadableEventSink(stdout_writer))
    if trace_json:
        event_bus.add_sink(JsonEventSink(stdout_writer))

    if trace_file:
        event_file = open(trace_file, "w", encoding="utf-8")

        def file_writer(line: str) -> None:
            event_file.write(line + "\n")

        if trace_json or not trace_events:
            event_bus.add_sink(JsonEventSink(file_writer))
        else:
            event_bus.add_sink(HumanReadableEventSink(file_writer))

    return event_bus, event_file


def _compile_stage(err: Exception) -> str:
    if isinstance(err, LangSyntaxError):
        return "parse"
    if isinstance(err, SyntaxError):
        return "parse"
    return "compile"


def _error_result(
    *,
    stage: str,
    filename: str | None,
    stdout: str,
    stderr: str,
    err: Exception,
    extras: dict | None = None,
    result: object | None = None,
) -> dict:
    normalized = normalize_filename(filename)
    structured = coerce_error(err, stage=stage, filename=normalized).to_dict()
    legacy = legacy_error_dict(err, filename=filename)
    return Result.failure(
        stage=stage,
        filename=normalized,
        stdout=stdout,
        stderr=stderr,
        result=result,
        errors=[structured],
        error=legacy,
        extras=extras,
    ).to_dict()


def _success_result(
    *,
    stage: str,
    filename: str | None,
    stdout: str,
    stderr: str,
    result: object | None = None,
    extras: dict | None = None,
):
    normalized = normalize_filename(filename)
    return Result.success(
        stage=stage,
        filename=normalized,
        stdout=stdout,
        stderr=stderr,
        result=result,
        extras=extras,
    ).to_dict()


def run_source(
    code: str,
    filename: str | None = None,
    *,
    trace: bool = False,
    trace_no_loc: bool = False,
    trace_filter: str | None = None,
    trace_limit: int | None = None,
    trace_scheduler: bool = False,
    scheduler_output=print,
    trace_events: bool = False,
    trace_json: bool = False,
    trace_file: str | None = None,
    optimize: bool = True,
    dump_bytecode: bool = False,
    max_steps: int = MAX_STEPS,
    timeout_ms: int = EXECUTION_TIMEOUT_MS,
    max_stdout_chars: int = MAX_STDOUT_CHARS,
    import_state: dict | None = None,
    project_root: str | None = None,
    profiler=None,
    allowed_paths: list[str] | None = None,
    input_fn=None,
):
    event_bus, event_file = _prepare_event_bus(
        trace_events=trace_events,
        trace_json=trace_json,
        trace_file=trace_file,
    )
    import_state = _resolve_import_state(import_state, project_root)
    disassembly = None
    disassembly_lines = None
    vm = VM(
        [],
        {},
        code_locs=[],
        source_path=filename,
        trace=trace,
        trace_no_loc=trace_no_loc,
        trace_filter=trace_filter,
        trace_limit=trace_limit,
        trace_scheduler=trace_scheduler,
        scheduler_output=scheduler_output,
        event_bus=event_bus,
        profiler=profiler,
        allowed_paths=allowed_paths,
        input_fn=input_fn,
    )
    configure_vm_limits(vm, max_steps=max_steps, timeout_ms=timeout_ms)
    loader = ModuleLoader(project_root=project_root, vm=vm)

    try:
        if dump_bytecode:
            module_name = os.path.abspath(filename) if filename else "<memory>"
            base_dir = os.path.dirname(module_name) if filename else os.getcwd()
            raw_code, raw_functions, raw_locs = loader.compile_only(code, module_name=module_name, base_dir=base_dir)
            disassembly = format_bytecode(raw_code, raw_locs, raw_functions)
            disassembly_lines = disassembly.splitlines()
    except Exception as err:
        stage = _compile_stage(err)
        return (
            _error_result(
                stage=stage,
                filename=filename,
                stdout="",
                stderr="",
                err=err,
            ),
            None,
        )

    extras = {}
    if disassembly is not None:
        extras["disassembly"] = disassembly
        extras["disassembly_lines"] = disassembly_lines

    try:
        with capture_output(max_stdout_chars=max_stdout_chars) as (stdout, stderr):
            try:
                vm.source_code = code
                module_name = os.path.abspath(filename) if filename is not None else "<memory>"
                base_dir = os.path.dirname(module_name) if filename is not None else os.getcwd()
                loader.load_module_from_source(code, module_name=module_name, base_dir=base_dir)
            except Exception as err:
                stage = _compile_stage(err)
                if stage not in {"parse", "compile"}:
                    stage = "execute"
                return (
                    _error_result(
                        stage=stage,
                        filename=filename,
                        stdout=stdout.getvalue(),
                        stderr=stderr.getvalue(),
                        err=err,
                        extras=extras,
                    ),
                    vm,
                )
    finally:
        if event_file is not None:
            event_file.close()

    return (
        _success_result(
            stage="execute",
            filename=filename,
            stdout=stdout.getvalue(),
            stderr=stderr.getvalue(),
            result=None,
            extras=extras,
        ),
        vm,
    )


def run_in_vm(
    vm: VM,
    code: str,
    filename: str | None = None,
    *,
    trace: bool = False,
    trace_no_loc: bool = False,
    trace_filter: str | None = None,
    trace_limit: int | None = None,
    trace_scheduler: bool = False,
    scheduler_output=print,
    max_steps: int = MAX_STEPS,
    timeout_ms: int = EXECUTION_TIMEOUT_MS,
    max_stdout_chars: int = MAX_STDOUT_CHARS,
    import_state: dict | None = None,
    project_root: str | None = None,
    event_bus: RuntimeEventBus | None = None,
):
    vm.last_graph_plan = None
    worker_dispatcher = getattr(vm, "worker_dispatcher", None)
    if worker_dispatcher is not None:
        set_default_dispatcher(worker_dispatcher)
    if worker_dispatcher is not None:
        vm.worker_dispatcher = worker_dispatcher
    if event_bus is not None:
        vm.event_bus = event_bus
    vm.trace = trace
    vm.trace_no_loc = trace_no_loc
    vm.trace_filter = trace_filter
    vm.trace_limit = trace_limit
    vm.trace_scheduler = trace_scheduler
    vm.scheduler_output = scheduler_output
    configure_vm_limits(vm, max_steps=max_steps, timeout_ms=timeout_ms)
    existing_globals = dict(vm.globals) if isinstance(getattr(vm, "globals", None), dict) else {}
    vm.source_code = code
    loader = ModuleLoader(project_root=project_root, vm=vm)
    with capture_output(max_stdout_chars=max_stdout_chars) as (stdout, stderr):
        try:
            module_name = os.path.abspath(filename) if filename is not None else "<memory>"
            base_dir = os.path.dirname(module_name) if filename is not None else os.getcwd()
            loader.load_module_from_source(code, module_name=module_name, base_dir=base_dir, initial_globals=existing_globals)
        except Exception as err:
            stage = _compile_stage(err)
            if stage not in {"parse", "compile"}:
                stage = "execute"
            return (
                _error_result(
                    stage=stage,
                    filename=filename,
                    stdout=stdout.getvalue(),
                    stderr=stderr.getvalue(),
                    err=err,
                ),
                vm,
            )

    return (
        _success_result(
            stage="execute",
            filename=filename,
            stdout=stdout.getvalue(),
            stderr=stderr.getvalue(),
        ),
        vm,
    )


def debug_source(
    code: str,
    filename: str | None = None,
    *,
    project_root: str | None = None,
    debugger_input=input,
    debugger_output=print,
    max_steps: int = MAX_STEPS,
    timeout_ms: int = EXECUTION_TIMEOUT_MS,
    max_stdout_chars: int = MAX_STDOUT_CHARS,
):
    debugger = Debugger(input_fn=debugger_input, output_fn=debugger_output, start_paused=True)
    vm = VM(
        [],
        {},
        code_locs=[],
        source_path=filename,
        debug=True,
        debugger=debugger,
    )
    loader = ModuleLoader(project_root=project_root, vm=vm, debugger=debugger)
    configure_vm_limits(vm, max_steps=max_steps, timeout_ms=timeout_ms)
    with capture_output(max_stdout_chars=max_stdout_chars) as (stdout, stderr):
        try:
            module_name = os.path.abspath(filename) if filename is not None else "<memory>"
            base_dir = os.path.dirname(module_name) if filename is not None else os.getcwd()
            loader.load_module_from_source(code, module_name=module_name, base_dir=base_dir)
        except DebuggerQuit:
            return (
                _success_result(
                    stage="debug",
                    filename=filename,
                    stdout=stdout.getvalue(),
                    stderr=stderr.getvalue(),
                    extras={"debug_quit": True},
                ),
                vm,
            )
        except Exception as err:
            stage = _compile_stage(err)
            if stage not in {"parse", "compile"}:
                stage = "execute"
            return (
                _error_result(
                    stage=stage,
                    filename=filename,
                    stdout=stdout.getvalue(),
                    stderr=stderr.getvalue(),
                    err=err,
                ),
                vm,
            )
    return (
        _success_result(
            stage="debug",
            filename=filename,
            stdout=stdout.getvalue(),
            stderr=stderr.getvalue(),
        ),
        vm,
    )


def check_source(
    code: str,
    filename: str | None = None,
    *,
    import_state: dict | None = None,
    project_root: str | None = None,
):
    from nodus.tooling.analyzer import analyze_program
    from nodus.runtime.module_loader import set_module_on_tree
    from nodus.compiler.compiler import Compiler, wrap_bytecode
    from nodus.builtins.nodus_builtins import BUILTIN_NAMES
    project_root_val = import_state.get("project_root") if import_state else None
    try:
        tokens = tokenize(code)
        ast = Parser(tokens).parse()
        module_id = os.path.abspath(filename) if filename else "<memory>"
        set_module_on_tree(ast, module_id)
        analyze_program(ast)
        base_dir = os.path.dirname(os.path.abspath(filename)) if filename else os.getcwd()
        loader = ModuleLoader(project_root=project_root or project_root_val)
        # Build metadata for root module and all dependencies (validates imports)
        metadata = loader._build_metadata(module_id, base_dir=base_dir, source=code, source_path=filename or None)
        # Build module_defs_index from all resolved metadata to enable private-symbol checks
        module_defs_index: dict[str, set[str]] = {}
        for path, meta in loader._metadata.items():
            for name in meta.module_info.defs:
                module_defs_index.setdefault(name, set()).add(path)
        # Compile with full cross-module visibility
        module_info = metadata.module_info
        module_info.imports = {name: name for name in metadata.import_names}
        module_info.qualified = {name: name for name in module_info.defs}
        compiler = Compiler(
            module_infos={module_id: module_info},
            module_defs_index=module_defs_index,
            builtin_names=set(BUILTIN_NAMES),
        )
        compiler.compile_program(ast)
        return _success_result(stage="check", filename=filename, stdout="", stderr="")
    except Exception as err:
        stage = _compile_stage(err)
        return _error_result(stage=stage, filename=filename, stdout="", stderr="", err=err)


def build_ast(code: str, filename: str | None = None, *, compact: bool = False):
    try:
        tokens = tokenize(code)
        ast = Parser(tokens).parse()
        pretty = format_ast(ast, compact=compact)
        extras = {"ast_pretty": pretty, "ast": ast_to_dict(ast)}
        return _success_result(stage="ast", filename=filename, stdout="", stderr="", extras=extras)
    except Exception as err:
        stage = _compile_stage(err)
        return _error_result(stage=stage, filename=filename, stdout="", stderr="", err=err)


def disassemble_source(
    code: str,
    filename: str | None = None,
    *,
    import_state: dict | None = None,
    project_root: str | None = None,
):
    project_root_val = import_state.get("project_root") if import_state else None
    try:
        loader = ModuleLoader(project_root=project_root or project_root_val)
        bytecode, functions, code_locs = loader.compile_only(
            code,
            module_name=filename or "<memory>",
            base_dir=os.path.dirname(os.path.abspath(filename)) if filename else os.getcwd(),
        )
        disassembly, dis_lines, dis_struct = build_disassembly(bytecode, code_locs, functions)
        extras = {
            "disassembly": disassembly,
            "disassembly_lines": dis_lines,
            "dis_pretty": dis_lines,
            "dis": dis_struct,
        }
        return _success_result(stage="disassemble", filename=filename, stdout="", stderr="", extras=extras)
    except Exception as err:
        stage = _compile_stage(err)
        return _error_result(stage=stage, filename=filename, stdout="", stderr="", err=err)


def run_graph_code(
    vm: VM,
    code: str,
    filename: str | None = None,
    *,
    trace: bool = False,
    trace_no_loc: bool = False,
    trace_filter: str | None = None,
    trace_limit: int | None = None,
    trace_scheduler: bool = False,
    scheduler_output=print,
    max_steps: int = MAX_STEPS,
    timeout_ms: int = EXECUTION_TIMEOUT_MS,
    max_stdout_chars: int = MAX_STDOUT_CHARS,
    import_state: dict | None = None,
    project_root: str | None = None,
    event_bus: RuntimeEventBus | None = None,
):
    return run_in_vm(
        vm,
        code,
        filename,
        trace=trace,
        trace_no_loc=trace_no_loc,
        trace_filter=trace_filter,
        trace_limit=trace_limit,
        trace_scheduler=trace_scheduler,
        scheduler_output=scheduler_output,
        max_steps=max_steps,
        timeout_ms=timeout_ms,
        max_stdout_chars=max_stdout_chars,
        import_state=import_state,
        project_root=project_root,
        event_bus=event_bus,
    )


def run_graph_with_workers(
    vm: VM,
    code: str,
    filename: str | None = None,
    *,
    dispatcher=None,
    trace: bool = False,
    trace_no_loc: bool = False,
    trace_filter: str | None = None,
    trace_limit: int | None = None,
    trace_scheduler: bool = False,
    scheduler_output=print,
    max_steps: int = MAX_STEPS,
    timeout_ms: int = EXECUTION_TIMEOUT_MS,
    max_stdout_chars: int = MAX_STDOUT_CHARS,
    import_state: dict | None = None,
    project_root: str | None = None,
    event_bus: RuntimeEventBus | None = None,
):
    vm.worker_dispatcher = dispatcher
    return run_in_vm(
        vm,
        code,
        filename,
        trace=trace,
        trace_no_loc=trace_no_loc,
        trace_filter=trace_filter,
        trace_limit=trace_limit,
        trace_scheduler=trace_scheduler,
        scheduler_output=scheduler_output,
        max_steps=max_steps,
        timeout_ms=timeout_ms,
        max_stdout_chars=max_stdout_chars,
        import_state=import_state,
        project_root=project_root,
        event_bus=event_bus,
    )


def plan_graph_code(
    vm: VM,
    code: str,
    filename: str | None = None,
    *,
    trace: bool = False,
    trace_no_loc: bool = False,
    trace_filter: str | None = None,
    trace_limit: int | None = None,
    trace_scheduler: bool = False,
    scheduler_output=print,
    max_steps: int = MAX_STEPS,
    timeout_ms: int = EXECUTION_TIMEOUT_MS,
    max_stdout_chars: int = MAX_STDOUT_CHARS,
    import_state: dict | None = None,
    project_root: str | None = None,
    event_bus: RuntimeEventBus | None = None,
):
    result, vm = run_in_vm(
        vm,
        code,
        filename,
        trace=trace,
        trace_no_loc=trace_no_loc,
        trace_filter=trace_filter,
        trace_limit=trace_limit,
        trace_scheduler=trace_scheduler,
        scheduler_output=scheduler_output,
        max_steps=max_steps,
        timeout_ms=timeout_ms,
        max_stdout_chars=max_stdout_chars,
        import_state=import_state,
        project_root=project_root,
        event_bus=event_bus,
    )
    if not result["ok"]:
        return result, vm
    if vm.last_graph_plan is None:
        err = NodusRuntimeError("No graph plan produced", filename=normalize_filename(filename))
        legacy = {"type": "graph", "message": "No graph plan produced", "path": filename}
        return (
            Result.failure(
                stage="plan_graph",
                filename=normalize_filename(filename),
                stdout=result.get("stdout", ""),
                stderr=result.get("stderr", ""),
                errors=[err.to_dict()],
                error=legacy,
            ).to_dict(),
            vm,
        )
    plan = vm.last_graph_plan
    return (
        Result.success(
            stage="plan_graph",
            filename=normalize_filename(filename),
            stdout=result.get("stdout", ""),
            stderr=result.get("stderr", ""),
            result=plan,
            extras={"plan": plan},
        ).to_dict(),
        vm,
    )


def resume_graph_in_vm(
    vm: VM,
    graph_id: str,
    *,
    max_stdout_chars: int = MAX_STDOUT_CHARS,
):
    with capture_output(max_stdout_chars=max_stdout_chars) as (stdout, stderr):
        try:
            result = vm.builtin_resume_graph(graph_id)
        except Exception as err:
            return (
                _error_result(
                    stage="resume_graph",
                    filename=vm.source_path,
                    stdout=stdout.getvalue(),
                    stderr=stderr.getvalue(),
                    err=err,
                ),
                vm,
            )
    return (
        _success_result(
            stage="resume_graph",
            filename=vm.source_path,
            stdout=stdout.getvalue(),
            stderr=stderr.getvalue(),
            result=result,
        ),
        vm,
    )


def resume_workflow_in_vm(
    vm: VM,
    graph_id: str,
    checkpoint: str | None = None,
    *,
    max_stdout_chars: int = MAX_STDOUT_CHARS,
):
    with capture_output(max_stdout_chars=max_stdout_chars) as (stdout, stderr):
        try:
            if checkpoint is None:
                result = vm.builtin_resume_workflow(graph_id)
            else:
                result = vm.builtin_resume_workflow(graph_id, checkpoint)
        except Exception as err:
            return (
                _error_result(
                    stage="resume_workflow",
                    filename=vm.source_path,
                    stdout=stdout.getvalue(),
                    stderr=stderr.getvalue(),
                    err=err,
                ),
                vm,
            )
    return (
        _success_result(
            stage="resume_workflow",
            filename=vm.source_path,
            stdout=stdout.getvalue(),
            stderr=stderr.getvalue(),
            result=result,
        ),
        vm,
    )


def resume_goal_in_vm(
    vm: VM,
    graph_id: str,
    checkpoint: str | None = None,
    *,
    max_stdout_chars: int = MAX_STDOUT_CHARS,
):
    with capture_output(max_stdout_chars=max_stdout_chars) as (stdout, stderr):
        try:
            if checkpoint is None:
                result = vm.builtin_resume_goal(graph_id)
            else:
                result = vm.builtin_resume_goal(graph_id, checkpoint)
        except Exception as err:
            return (
                _error_result(
                    stage="resume_goal",
                    filename=vm.source_path,
                    stdout=stdout.getvalue(),
                    stderr=stderr.getvalue(),
                    err=err,
                ),
                vm,
            )
    return (
        _success_result(
            stage="resume_goal",
            filename=vm.source_path,
            stdout=stdout.getvalue(),
            stderr=stderr.getvalue(),
            result=result,
        ),
        vm,
    )


def plan_graph_source(
    code: str,
    filename: str | None = None,
    *,
    trace: bool = False,
    trace_no_loc: bool = False,
    trace_filter: str | None = None,
    trace_limit: int | None = None,
    trace_scheduler: bool = False,
    scheduler_output=print,
    max_steps: int = MAX_STEPS,
    timeout_ms: int = EXECUTION_TIMEOUT_MS,
    max_stdout_chars: int = MAX_STDOUT_CHARS,
    import_state: dict | None = None,
    project_root: str | None = None,
    event_bus: RuntimeEventBus | None = None,
):
    vm = VM([], {}, code_locs=[], source_path=None)
    return plan_graph_code(
        vm,
        code,
        filename,
        trace=trace,
        trace_no_loc=trace_no_loc,
        trace_filter=trace_filter,
        trace_limit=trace_limit,
        trace_scheduler=trace_scheduler,
        scheduler_output=scheduler_output,
        max_steps=max_steps,
        timeout_ms=timeout_ms,
        max_stdout_chars=max_stdout_chars,
        import_state=import_state,
        project_root=project_root,
        event_bus=event_bus,
    )


def _resolve_workflow_from_vm(vm: VM, workflow_name: str | None):
    workflow = find_workflow_value(vm.globals, workflow_name)
    if workflow is not None:
        return workflow
    names = workflow_name_candidates(vm.globals)
    if workflow_name is not None:
        raise NodusRuntimeError(f"Workflow not found: {workflow_name}", filename=normalize_filename(vm.source_path))
    if not names:
        raise NodusRuntimeError("No workflow definition found", filename=normalize_filename(vm.source_path))
    raise NodusRuntimeError(
        f"Multiple workflows found: {', '.join(names)}. Specify one by name.",
        filename=normalize_filename(vm.source_path),
    )


def _resolve_goal_from_vm(vm: VM, goal_name: str | None):
    goal = find_goal_value(vm.globals, goal_name)
    if goal is not None:
        return goal
    names = goal_name_candidates(vm.globals)
    if goal_name is not None:
        raise NodusRuntimeError(f"Goal not found: {goal_name}", filename=normalize_filename(vm.source_path))
    if not names:
        raise NodusRuntimeError("No goal definition found", filename=normalize_filename(vm.source_path))
    raise NodusRuntimeError(
        f"Multiple goals found: {', '.join(names)}. Specify one by name.",
        filename=normalize_filename(vm.source_path),
    )


def run_workflow_code(
    vm: VM,
    code: str,
    filename: str | None = None,
    *,
    workflow_name: str | None = None,
    trace: bool = False,
    trace_no_loc: bool = False,
    trace_filter: str | None = None,
    trace_limit: int | None = None,
    trace_scheduler: bool = False,
    scheduler_output=print,
    max_steps: int = MAX_STEPS,
    timeout_ms: int = EXECUTION_TIMEOUT_MS,
    max_stdout_chars: int = MAX_STDOUT_CHARS,
    import_state: dict | None = None,
    project_root: str | None = None,
    event_bus: RuntimeEventBus | None = None,
):
    result, vm = run_in_vm(
        vm,
        code,
        filename,
        trace=trace,
        trace_no_loc=trace_no_loc,
        trace_filter=trace_filter,
        trace_limit=trace_limit,
        trace_scheduler=trace_scheduler,
        scheduler_output=scheduler_output,
        max_steps=max_steps,
        timeout_ms=timeout_ms,
        max_stdout_chars=max_stdout_chars,
        import_state=import_state,
        project_root=project_root,
        event_bus=event_bus,
    )
    if not result["ok"]:
        return result, vm
    with capture_output(max_stdout_chars=max_stdout_chars) as (stdout, stderr):
        try:
            workflow = _resolve_workflow_from_vm(vm, workflow_name)
            workflow_result = vm.builtin_run_workflow(workflow)
        except Exception as err:
            return (
                _error_result(
                    stage="run_workflow",
                    filename=filename,
                    stdout=result.get("stdout", "") + stdout.getvalue(),
                    stderr=result.get("stderr", "") + stderr.getvalue(),
                    err=err,
                ),
                vm,
            )
    return (
        _success_result(
            stage="run_workflow",
            filename=filename,
            stdout=result.get("stdout", "") + stdout.getvalue(),
            stderr=result.get("stderr", "") + stderr.getvalue(),
            result=workflow_result,
        ),
        vm,
    )


def plan_workflow_code(
    vm: VM,
    code: str,
    filename: str | None = None,
    *,
    workflow_name: str | None = None,
    trace: bool = False,
    trace_no_loc: bool = False,
    trace_filter: str | None = None,
    trace_limit: int | None = None,
    trace_scheduler: bool = False,
    scheduler_output=print,
    max_steps: int = MAX_STEPS,
    timeout_ms: int = EXECUTION_TIMEOUT_MS,
    max_stdout_chars: int = MAX_STDOUT_CHARS,
    import_state: dict | None = None,
    project_root: str | None = None,
    event_bus: RuntimeEventBus | None = None,
):
    result, vm = run_in_vm(
        vm,
        code,
        filename,
        trace=trace,
        trace_no_loc=trace_no_loc,
        trace_filter=trace_filter,
        trace_limit=trace_limit,
        trace_scheduler=trace_scheduler,
        scheduler_output=scheduler_output,
        max_steps=max_steps,
        timeout_ms=timeout_ms,
        max_stdout_chars=max_stdout_chars,
        import_state=import_state,
        project_root=project_root,
        event_bus=event_bus,
    )
    if not result["ok"]:
        return result, vm
    try:
        workflow = _resolve_workflow_from_vm(vm, workflow_name)
        plan = vm.builtin_plan_workflow(workflow)
    except Exception as err:
        return (
            _error_result(
                stage="plan_workflow",
                filename=filename,
                stdout=result.get("stdout", ""),
                stderr=result.get("stderr", ""),
                err=err,
            ),
            vm,
        )
    return (
        Result.success(
            stage="plan_workflow",
            filename=normalize_filename(filename),
            stdout=result.get("stdout", ""),
            stderr=result.get("stderr", ""),
            result=plan,
            extras={"plan": plan},
        ).to_dict(),
        vm,
    )


def run_goal_code(
    vm: VM,
    code: str,
    filename: str | None = None,
    *,
    goal_name: str | None = None,
    trace: bool = False,
    trace_no_loc: bool = False,
    trace_filter: str | None = None,
    trace_limit: int | None = None,
    trace_scheduler: bool = False,
    scheduler_output=print,
    max_steps: int = MAX_STEPS,
    timeout_ms: int = EXECUTION_TIMEOUT_MS,
    max_stdout_chars: int = MAX_STDOUT_CHARS,
    import_state: dict | None = None,
    project_root: str | None = None,
    event_bus: RuntimeEventBus | None = None,
):
    result, vm = run_in_vm(
        vm,
        code,
        filename,
        trace=trace,
        trace_no_loc=trace_no_loc,
        trace_filter=trace_filter,
        trace_limit=trace_limit,
        trace_scheduler=trace_scheduler,
        scheduler_output=scheduler_output,
        max_steps=max_steps,
        timeout_ms=timeout_ms,
        max_stdout_chars=max_stdout_chars,
        import_state=import_state,
        project_root=project_root,
        event_bus=event_bus,
    )
    if not result["ok"]:
        return result, vm
    with capture_output(max_stdout_chars=max_stdout_chars) as (stdout, stderr):
        try:
            goal = _resolve_goal_from_vm(vm, goal_name)
            goal_result = vm.builtin_run_goal(goal)
        except Exception as err:
            return (
                _error_result(
                    stage="run_goal",
                    filename=filename,
                    stdout=result.get("stdout", "") + stdout.getvalue(),
                    stderr=result.get("stderr", "") + stderr.getvalue(),
                    err=err,
                ),
                vm,
            )
    return (
        _success_result(
            stage="run_goal",
            filename=filename,
            stdout=result.get("stdout", "") + stdout.getvalue(),
            stderr=result.get("stderr", "") + stderr.getvalue(),
            result=goal_result,
        ),
        vm,
    )


def plan_goal_code(
    vm: VM,
    code: str,
    filename: str | None = None,
    *,
    goal_name: str | None = None,
    trace: bool = False,
    trace_no_loc: bool = False,
    trace_filter: str | None = None,
    trace_limit: int | None = None,
    trace_scheduler: bool = False,
    scheduler_output=print,
    max_steps: int = MAX_STEPS,
    timeout_ms: int = EXECUTION_TIMEOUT_MS,
    max_stdout_chars: int = MAX_STDOUT_CHARS,
    import_state: dict | None = None,
    project_root: str | None = None,
    event_bus: RuntimeEventBus | None = None,
):
    result, vm = run_in_vm(
        vm,
        code,
        filename,
        trace=trace,
        trace_no_loc=trace_no_loc,
        trace_filter=trace_filter,
        trace_limit=trace_limit,
        trace_scheduler=trace_scheduler,
        scheduler_output=scheduler_output,
        max_steps=max_steps,
        timeout_ms=timeout_ms,
        max_stdout_chars=max_stdout_chars,
        import_state=import_state,
        project_root=project_root,
        event_bus=event_bus,
    )
    if not result["ok"]:
        return result, vm
    try:
        goal = _resolve_goal_from_vm(vm, goal_name)
        plan = vm.builtin_plan_goal(goal)
    except Exception as err:
        return (
            _error_result(
                stage="plan_goal",
                filename=filename,
                stdout=result.get("stdout", ""),
                stderr=result.get("stderr", ""),
                err=err,
            ),
            vm,
        )
    return (
        Result.success(
            stage="plan_goal",
            filename=normalize_filename(filename),
            stdout=result.get("stdout", ""),
            stderr=result.get("stderr", ""),
            result=plan,
            extras={"plan": plan},
        ).to_dict(),
        vm,
    )


def resume_graph(
    graph_id: str,
    *,
    max_stdout_chars: int = MAX_STDOUT_CHARS,
):
    vm = get_registered_vm(graph_id) or VM([], {}, code_locs=[], source_path=None)
    return resume_graph_in_vm(vm, graph_id, max_stdout_chars=max_stdout_chars)


def resume_workflow(
    graph_id: str,
    checkpoint: str | None = None,
    *,
    max_stdout_chars: int = MAX_STDOUT_CHARS,
):
    vm = get_registered_vm(graph_id) or VM([], {}, code_locs=[], source_path=None)
    return resume_workflow_in_vm(vm, graph_id, checkpoint, max_stdout_chars=max_stdout_chars)


def resume_goal(
    graph_id: str,
    checkpoint: str | None = None,
    *,
    max_stdout_chars: int = MAX_STDOUT_CHARS,
):
    vm = get_registered_vm(graph_id) or VM([], {}, code_locs=[], source_path=None)
    return resume_goal_in_vm(vm, graph_id, checkpoint, max_stdout_chars=max_stdout_chars)


def workflow_checkpoints(graph_id: str) -> dict:
    state = load_graph_state(graph_id)
    if state is None:
        return {"ok": False, "error": "Graph state not found", "checkpoints": []}
    checkpoints = state.get("checkpoints")
    if not isinstance(checkpoints, list) and isinstance(state.get("metadata"), dict):
        checkpoints = state["metadata"].get("checkpoints")
    return {"ok": True, "checkpoints": checkpoints_public(checkpoints or [])}


def format_disassembly_with_locs(text: str) -> str:
    lines = []
    for line in text.splitlines():
        if " (" in line and line.endswith(")"):
            head, tail = line.rsplit(" (", 1)
            loc = tail[:-1]
            parts = loc.split(":")
            if len(parts) >= 2 and parts[-1].isdigit() and parts[-2].isdigit():
                loc = f"{parts[-2]}:{parts[-1]}"
            lines.append(f"{head} [{loc}]")
        else:
            lines.append(line)
    return "\n".join(lines)


def tool_call_result(name: str, args: dict, *, vm: VM | None = None) -> dict:
    return call_tool(name, args, vm=vm)


def agent_call_result(name: str, payload, *, vm: VM | None = None) -> dict:
    return call_agent(name, payload, vm=vm)


def memory_get_result(key: str, *, vm: VM | None = None) -> dict:
    try:
        value = get_value(key, vm=vm)
        return Result.success(stage="memory_get", filename=normalize_filename(getattr(vm, "source_path", None)), result=value).to_dict()
    except Exception as err:
        return _error_result(stage="memory_get", filename=getattr(vm, "source_path", None), stdout="", stderr="", err=err)


def memory_put_result(key: str, value, *, vm: VM | None = None) -> dict:
    try:
        stored = put_value(key, value, vm=vm)
        return Result.success(stage="memory_put", filename=normalize_filename(getattr(vm, "source_path", None)), result=stored).to_dict()
    except Exception as err:
        return _error_result(stage="memory_put", filename=getattr(vm, "source_path", None), stdout="", stderr="", err=err)


def memory_delete_result(key: str, *, vm: VM | None = None) -> dict:
    try:
        deleted = delete_value(key, vm=vm)
        return Result.success(stage="memory_delete", filename=normalize_filename(getattr(vm, "source_path", None)), result=deleted).to_dict()
    except Exception as err:
        return _error_result(stage="memory_delete", filename=getattr(vm, "source_path", None), stdout="", stderr="", err=err)


def memory_keys_result(*, vm: VM | None = None) -> dict:
    return Result.success(
        stage="memory_keys",
        filename=normalize_filename(getattr(vm, "source_path", None)),
        result=list_keys(vm=vm),
        extras={"memory": export_memory(vm=vm)},
    ).to_dict()
