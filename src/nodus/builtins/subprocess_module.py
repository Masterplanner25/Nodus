"""std:subprocess — subprocess builtins for Nodus VM."""

import os
import shlex
import signal as _signal
import subprocess
import sys
import threading
import time as _time

from nodus.runtime.channel import Channel, ChannelRecvRequest
from nodus.runtime.runtime_events import RuntimeEvent
from nodus.runtime.runtime_stats import runtime_time_ms
from nodus.vm.vm import BuiltinMethod, Record

_TRUNCATE_LIMIT = 65536  # 64KB per err record field


def _root_vm(vm):
    root = vm
    while True:
        parent = getattr(root, "_caller_vm", None)
        if parent is None:
            return root
        root = parent


def _get_scheduler(vm):
    return getattr(_root_vm(vm), "scheduler", None)


def _opts_dict(options):
    if options is None:
        return {}
    if hasattr(options, "fields"):
        return options.fields
    if isinstance(options, dict):
        return options
    return {}


def _make_subprocess_err(vm, message, *, category, command, pid=None,
                          exit_code=None, signal_name=None,
                          stdout_bytes=b"", stderr_bytes=b"",
                          duration_ms=0, grace_duration_ms=None):
    stdout_trunc = len(stdout_bytes) > _TRUNCATE_LIMIT
    stderr_trunc = len(stderr_bytes) > _TRUNCATE_LIMIT
    stdout_val = stdout_bytes[:_TRUNCATE_LIMIT].decode("utf-8", errors="replace")
    stderr_val = stderr_bytes[:_TRUNCATE_LIMIT].decode("utf-8", errors="replace")
    return vm.make_err("subprocess_error", message, payload={
        "category": category,
        "command": command,
        "pid": pid,
        "exit_code": exit_code,
        "signal": signal_name,
        "stdout": stdout_val,
        "stderr": stderr_val,
        "stdout_truncated": stdout_trunc,
        "stderr_truncated": stderr_trunc,
        "duration_ms": duration_ms,
        "grace_duration_ms": grace_duration_ms,
    })


def _make_result_record(stdout_bytes, stderr_bytes, exit_code, duration_ms, command, encoding):
    if encoding == "bytes":
        stdout_val = stdout_bytes or b""
        stderr_val = stderr_bytes or b""
    else:
        stdout_val = (stdout_bytes or b"").decode(encoding, errors="replace")
        stderr_val = (stderr_bytes or b"").decode(encoding, errors="replace")
    return Record({
        "stdout": stdout_val,
        "stderr": stderr_val,
        "exit_code": exit_code,
        "duration_ms": duration_ms,
        "command": command,
    }, kind="subprocess_result")


def _to_str_dict(value):
    """Convert a Nodus Record or Python dict to a str→str dict."""
    if value is None:
        return {}
    if hasattr(value, "fields"):
        return {str(k): str(v) for k, v in value.fields.items() if v is not None}
    if isinstance(value, dict):
        return {str(k): str(v) for k, v in value.items() if v is not None}
    return {}


def _build_env(opts):
    env_inherit = opts.get("env_inherit", True)
    env_overlay = _to_str_dict(opts.get("env"))
    env_passthrough_raw = opts.get("env_passthrough") or []
    env_passthrough = list(env_passthrough_raw) if isinstance(env_passthrough_raw, list) else []
    if env_inherit:
        env = dict(os.environ)
        env.update(env_overlay)
        return env
    env = {}
    for k in env_passthrough:
        if isinstance(k, str) and k in os.environ:
            env[k] = os.environ[k]
    env.update(env_overlay)
    return env


def _stream_arg(mode, default):
    m = mode if mode is not None else default
    if m == "capture":
        return subprocess.PIPE
    if m == "inherit":
        return None
    if m == "ignore":
        return subprocess.DEVNULL
    return subprocess.PIPE


def _is_file_redirect(mode):
    return (mode is not None and isinstance(mode, str)
            and mode not in ("capture", "inherit", "ignore"))


def _open_redirect(path_str):
    if path_str.startswith(">>"):
        return open(path_str[2:], "ab")
    return open(path_str, "wb")


def _do_run(argv_or_cmd, opts, vm, is_shell=False):
    """Execute subprocess synchronously, return result or err Record."""
    _cmd_display = argv_or_cmd if isinstance(argv_or_cmd, str) else (argv_or_cmd[0] if argv_or_cmd else "")
    vm.event_bus.emit(RuntimeEvent(
        "capability_use", runtime_time_ms(),
        data={"kind": "subprocess_run", "cmd": _cmd_display, "shell": is_shell},
    ))
    default_out = opts.get("output", "capture")
    stdout_mode = opts.get("stdout")
    stderr_mode = opts.get("stderr")
    encoding = opts.get("output_encoding", "utf-8")
    stdin_data = opts.get("stdin")
    timeout_ms = opts.get("timeout_ms")
    kill_grace_ms = opts.get("kill_grace_ms", 5000)
    check = opts.get("check", True)
    process_group = opts.get("process_group", True)
    cwd = opts.get("cwd")
    env = _build_env(opts)

    popen_kw = {
        "args": argv_or_cmd,
        "shell": is_shell,
        "env": env,
    }
    if cwd:
        if isinstance(cwd, str):
            vm._ensure_path_allowed(cwd, "subprocess cwd")
        popen_kw["cwd"] = cwd
    if is_shell and opts.get("shell_exe"):
        popen_kw["executable"] = opts["shell_exe"]
    if process_group:
        if sys.platform == "win32":
            popen_kw["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
        else:
            popen_kw["start_new_session"] = True

    stdout_file = None
    stderr_file = None
    if _is_file_redirect(stdout_mode):
        redirect_path = stdout_mode[2:] if stdout_mode.startswith(">>") else stdout_mode
        vm._ensure_path_allowed(redirect_path, "subprocess stdout redirect")
        stdout_file = _open_redirect(stdout_mode)
        popen_kw["stdout"] = stdout_file
    else:
        popen_kw["stdout"] = _stream_arg(stdout_mode, default_out)

    if _is_file_redirect(stderr_mode):
        redirect_path = stderr_mode[2:] if stderr_mode.startswith(">>") else stderr_mode
        vm._ensure_path_allowed(redirect_path, "subprocess stderr redirect")
        stderr_file = _open_redirect(stderr_mode)
        popen_kw["stderr"] = stderr_file
    else:
        popen_kw["stderr"] = _stream_arg(stderr_mode, default_out)

    if stdin_data is not None:
        popen_kw["stdin"] = subprocess.PIPE

    timeout_s = timeout_ms / 1000.0 if timeout_ms is not None else None
    start = _time.monotonic()

    try:
        stdin_bytes = None
        if stdin_data is not None:
            if isinstance(stdin_data, str):
                stdin_bytes = stdin_data.encode("utf-8")
            else:
                stdin_bytes = bytes(stdin_data)

        proc = subprocess.Popen(**popen_kw)
        pid = proc.pid

        try:
            stdout_raw, stderr_raw = proc.communicate(input=stdin_bytes, timeout=timeout_s)
        except subprocess.TimeoutExpired:
            elapsed_ms = int((_time.monotonic() - start) * 1000)
            proc.terminate()
            grace_s = kill_grace_ms / 1000.0
            try:
                stdout_raw, stderr_raw = proc.communicate(timeout=grace_s)
            except subprocess.TimeoutExpired:
                proc.kill()
                stdout_raw, stderr_raw = proc.communicate()
            grace_ms = int((_time.monotonic() - start) * 1000) - elapsed_ms
            return _make_subprocess_err(
                vm, f"process timed out after {timeout_ms}ms",
                category="timeout", command=argv_or_cmd, pid=pid,
                exit_code=proc.returncode, signal_name=None,
                stdout_bytes=stdout_raw or b"", stderr_bytes=stderr_raw or b"",
                duration_ms=elapsed_ms, grace_duration_ms=grace_ms,
            )

        duration_ms = int((_time.monotonic() - start) * 1000)
        rc = proc.returncode

        if rc is not None and rc < 0 and sys.platform != "win32":
            try:
                sig_name = _signal.Signals(-rc).name
            except ValueError:
                sig_name = str(-rc)
            return _make_subprocess_err(
                vm, f"process killed by signal {sig_name}",
                category="signal", command=argv_or_cmd, pid=pid,
                exit_code=None, signal_name=sig_name,
                stdout_bytes=stdout_raw or b"", stderr_bytes=stderr_raw or b"",
                duration_ms=duration_ms,
            )

        if rc != 0 and check:
            return _make_subprocess_err(
                vm, f"process exited with code {rc}",
                category="exit_code", command=argv_or_cmd, pid=pid,
                exit_code=rc, signal_name=None,
                stdout_bytes=stdout_raw or b"", stderr_bytes=stderr_raw or b"",
                duration_ms=duration_ms,
            )

        return _make_result_record(stdout_raw, stderr_raw, rc, duration_ms, argv_or_cmd, encoding)

    except FileNotFoundError as exc:
        duration_ms = int((_time.monotonic() - start) * 1000)
        return _make_subprocess_err(
            vm, f"failed to start process: {exc}",
            category="spawn_error", command=argv_or_cmd,
            stdout_bytes=b"", stderr_bytes=b"", duration_ms=duration_ms,
        )
    except PermissionError as exc:
        duration_ms = int((_time.monotonic() - start) * 1000)
        return _make_subprocess_err(
            vm, f"permission denied: {exc}",
            category="spawn_error", command=argv_or_cmd,
            stdout_bytes=b"", stderr_bytes=b"", duration_ms=duration_ms,
        )
    except OSError as exc:
        duration_ms = int((_time.monotonic() - start) * 1000)
        return _make_subprocess_err(
            vm, f"OS error starting process: {exc}",
            category="spawn_error", command=argv_or_cmd,
            stdout_bytes=b"", stderr_bytes=b"", duration_ms=duration_ms,
        )
    finally:
        if stdout_file:
            stdout_file.close()
        if stderr_file:
            stderr_file.close()


def _pump_stream(pipe, ch: Channel, chunk_mode: str, encoding: str) -> None:
    """Background thread: reads pipe output into channel ch."""
    try:
        if chunk_mode == "lines":
            remainder = b""
            while True:
                chunk = pipe.read(4096)
                if not chunk:
                    if remainder:
                        line = remainder.rstrip(b"\r")
                        ch.queue.append(
                            line.decode(encoding, errors="replace")
                            if encoding != "bytes" else line
                        )
                    break
                data = remainder + chunk
                parts = data.split(b"\n")
                remainder = parts.pop()
                for raw_line in parts:
                    line = raw_line.rstrip(b"\r")
                    ch.queue.append(
                        line.decode(encoding, errors="replace")
                        if encoding != "bytes" else line
                    )
        else:
            while True:
                chunk = pipe.read(4096)
                if not chunk:
                    break
                ch.queue.append(chunk)
    except Exception:
        pass  # pipe closed or broken — stop pumping


_UNIX_SIGNALS: dict[str, int] = {}
if sys.platform != "win32":
    for _sname in ("SIGHUP", "SIGUSR1", "SIGUSR2", "SIGQUIT"):
        if hasattr(_signal, _sname):
            _UNIX_SIGNALS[_sname] = getattr(_signal, _sname)


def _do_spawn(argv_or_cmd, opts, vm, is_shell=False):
    """Start subprocess and return a process handle Record."""
    encoding = opts.get("output_encoding", "utf-8")
    chunk_mode = opts.get("chunk_mode", "lines")
    process_group = opts.get("process_group", True)
    cwd = opts.get("cwd")
    env = _build_env(opts)

    popen_kw = {
        "args": argv_or_cmd,
        "shell": is_shell,
        "env": env,
        "stdin": subprocess.PIPE,
        "stdout": subprocess.PIPE,
        "stderr": subprocess.PIPE,
    }
    if cwd:
        if isinstance(cwd, str):
            vm._ensure_path_allowed(cwd, "subprocess cwd")
        popen_kw["cwd"] = cwd
    if is_shell and opts.get("shell_exe"):
        popen_kw["executable"] = opts["shell_exe"]
    if process_group:
        if sys.platform == "win32":
            popen_kw["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
        else:
            popen_kw["start_new_session"] = True

    try:
        proc = subprocess.Popen(**popen_kw)
    except FileNotFoundError as exc:
        return _make_subprocess_err(
            vm, f"failed to start process: {exc}",
            category="spawn_error", command=argv_or_cmd,
            stdout_bytes=b"", stderr_bytes=b"", duration_ms=0,
        )
    except PermissionError as exc:
        return _make_subprocess_err(
            vm, f"permission denied: {exc}",
            category="spawn_error", command=argv_or_cmd,
            stdout_bytes=b"", stderr_bytes=b"", duration_ms=0,
        )
    except OSError as exc:
        return _make_subprocess_err(
            vm, f"OS error starting process: {exc}",
            category="spawn_error", command=argv_or_cmd,
            stdout_bytes=b"", stderr_bytes=b"", duration_ms=0,
        )

    stdout_ch = Channel()
    stderr_ch = Channel()

    sched = _get_scheduler(vm)
    if sched is not None:
        sched._io_channels.append(stdout_ch)
        sched._io_channels.append(stderr_ch)

    # Build BuiltinMethod closures — process_record defined below
    def _wait():
        proc.wait()
        rc = proc.returncode
        process_record.fields["exit_code"] = rc
        return rc

    def _wait_async():
        scheduler = _get_scheduler(vm)
        coroutine = getattr(vm, "current_coroutine", None)
        if (scheduler is None or coroutine is None or
                coroutine is not getattr(scheduler, "current_task", None)):
            return _wait()
        result_ch: Channel = Channel()

        def _worker() -> None:
            proc.wait()
            rc = proc.returncode
            process_record.fields["exit_code"] = rc
            result_ch.queue.append(rc)
            result_ch.closed = True

        threading.Thread(target=_worker, daemon=True).start()
        scheduler._io_channels.append(result_ch)
        coroutine.state = "suspended"
        coroutine.blocked_on = result_ch
        coroutine.blocked_reason = "subprocess_wait_async"
        vm.stack.append(None)
        vm.save_current_coroutine_state(vm.ip + 1)
        result_ch.waiting_receivers.append(coroutine)
        return ChannelRecvRequest(result_ch)

    def _is_alive():
        return proc.poll() is None

    def _terminate():
        try:
            if sys.platform != "win32" and process_group:
                try:
                    os.killpg(os.getpgid(proc.pid), _signal.SIGTERM)
                    return None
                except ProcessLookupError:
                    pass
            proc.terminate()
        except Exception:
            pass
        return None

    def _kill():
        try:
            if sys.platform != "win32" and process_group:
                try:
                    os.killpg(os.getpgid(proc.pid), _signal.SIGKILL)
                    return None
                except ProcessLookupError:
                    pass
            proc.kill()
        except Exception:
            pass
        return None

    def _interrupt():
        try:
            if sys.platform == "win32":
                proc.send_signal(_signal.CTRL_C_EVENT)
            else:
                proc.send_signal(_signal.SIGINT)
        except Exception:
            pass
        return None

    _signal_map = {}
    for _sname in ("SIGTERM", "SIGKILL", "SIGINT"):
        if hasattr(_signal, _sname):
            _signal_map[_sname] = getattr(_signal, _sname)
    _signal_map.update(_UNIX_SIGNALS)

    def _do_signal(name):
        if not isinstance(name, str):
            return vm.make_err("subprocess_error", "signal name must be a string",
                               payload={"category": "spawn_error"})
        sig = _signal_map.get(name.upper())
        if sig is None:
            if sys.platform == "win32":
                return vm.make_err("subprocess_error",
                                   f"signal {name!r} not supported on Windows",
                                   payload={"category": "spawn_error"})
            return vm.make_err("subprocess_error", f"unknown signal: {name!r}",
                               payload={"category": "spawn_error"})
        try:
            proc.send_signal(sig)
            return None
        except Exception as exc:
            return vm.make_err("subprocess_error", str(exc),
                               payload={"category": "io_error"})

    def _stdin_write(data):
        if proc.stdin is None or proc.stdin.closed:
            return vm.make_err("subprocess_error", "stdin is already closed",
                               payload={"category": "io_error"})
        try:
            if isinstance(data, str):
                proc.stdin.write(data.encode("utf-8"))
            else:
                proc.stdin.write(bytes(data))
            proc.stdin.flush()
            return None
        except Exception as exc:
            return vm.make_err("subprocess_error", f"stdin write error: {exc}",
                               payload={"category": "io_error"})

    def _stdin_close():
        try:
            if proc.stdin and not proc.stdin.closed:
                proc.stdin.close()
        except Exception:
            pass
        return None

    stdin_record = Record({
        "send": BuiltinMethod(_stdin_write),
        "close": BuiltinMethod(_stdin_close),
    }, kind="stdin_handle")

    fields = {
        "pid": proc.pid,
        "command": argv_or_cmd,
        "exit_code": None,
        "stdout": stdout_ch,
        "stderr": stderr_ch,
        "stdin": stdin_record,
        "wait": BuiltinMethod(_wait),
        "wait_async": BuiltinMethod(_wait_async),
        "is_alive": BuiltinMethod(_is_alive),
        "terminate": BuiltinMethod(_terminate),
        "kill": BuiltinMethod(_kill),
        "interrupt": BuiltinMethod(_interrupt),
        "signal": BuiltinMethod(_do_signal),
    }
    process_record = Record(fields, kind="subprocess_process")

    def _pump_stdout_thread():
        _pump_stream(proc.stdout, stdout_ch, chunk_mode, encoding)
        stdout_ch.closed = True

    def _pump_stderr_thread():
        _pump_stream(proc.stderr, stderr_ch, chunk_mode, encoding)
        stderr_ch.closed = True
        proc.wait()
        process_record.fields["exit_code"] = proc.returncode

    t_out = threading.Thread(target=_pump_stdout_thread, daemon=True)
    t_err = threading.Thread(target=_pump_stderr_thread, daemon=True)
    t_out.start()
    t_err.start()
    root = _root_vm(vm)
    root._spawned_handles.append((proc, t_out, t_err))

    return process_record


def _do_shell_quote(s, vm):
    if not isinstance(s, str):
        return vm.make_err("subprocess_error", "shell_quote requires a string",
                           payload={"category": "spawn_error"})
    if sys.platform == "win32":
        return subprocess.list2cmdline([s])
    return shlex.quote(s)


def _do_async_run(argv_or_cmd, opts, vm, is_shell=False):
    """Run subprocess in a daemon thread; suspend calling coroutine until done.

    Same thread+channel pattern as http_module._do_async_request.  Falls back
    to blocking _do_run when called outside a coroutine/scheduler context.
    """
    from nodus.runtime.channel import Channel, ChannelRecvRequest

    scheduler = _get_scheduler(vm)
    coroutine = getattr(vm, "current_coroutine", None)

    # Only take the async path when running inside the scheduler's own coroutine
    # loop.  Module-function calls use invoke_function → run_closure → execute(),
    # which does not support yield; the current_task check catches that path and
    # falls back to sync, preventing "Task yielded during graph execution" errors.
    if (scheduler is None or coroutine is None or
            coroutine is not getattr(scheduler, "current_task", None)):
        return _do_run(argv_or_cmd, opts, vm, is_shell=is_shell)

    result_ch: Channel = Channel()

    def _worker() -> None:
        result = _do_run(argv_or_cmd, opts, vm, is_shell=is_shell)
        result_ch.queue.append(result)
        result_ch.closed = True

    threading.Thread(target=_worker, daemon=True).start()
    scheduler._io_channels.append(result_ch)

    coroutine.state = "suspended"
    coroutine.blocked_on = result_ch
    coroutine.blocked_reason = "subprocess_async"
    vm.stack.append(None)
    vm.save_current_coroutine_state(vm.ip + 1)
    result_ch.waiting_receivers.append(coroutine)

    return ChannelRecvRequest(result_ch)


def register(vm, registry) -> None:
    """Register subprocess_* builtins onto the registry."""

    def subprocess_run(argv, options=None):
        opts = _opts_dict(options)
        if not isinstance(argv, list):
            return _make_subprocess_err(vm, "argv must be a list",
                                        category="spawn_error", command=argv)
        return _do_run(argv, opts, vm)

    def subprocess_run_async(argv, options=None):
        opts = _opts_dict(options)
        if not isinstance(argv, list):
            return _make_subprocess_err(vm, "argv must be a list",
                                        category="spawn_error", command=argv)
        return _do_async_run(argv, opts, vm)

    def subprocess_shell(command, options=None):
        opts = _opts_dict(options)
        if not isinstance(command, str):
            return _make_subprocess_err(vm, "shell command must be a string",
                                        category="spawn_error", command=command)
        return _do_run(command, opts, vm, is_shell=True)

    def subprocess_shell_async(command, options=None):
        opts = _opts_dict(options)
        if not isinstance(command, str):
            return _make_subprocess_err(vm, "shell command must be a string",
                                        category="spawn_error", command=command)
        return _do_async_run(command, opts, vm, is_shell=True)

    def subprocess_spawn(argv, options=None):
        opts = _opts_dict(options)
        if not isinstance(argv, list):
            return _make_subprocess_err(vm, "argv must be a list",
                                        category="spawn_error", command=argv)
        return _do_spawn(argv, opts, vm)

    def subprocess_spawn_shell(command, options=None):
        opts = _opts_dict(options)
        if not isinstance(command, str):
            return _make_subprocess_err(vm, "shell command must be a string",
                                        category="spawn_error", command=command)
        return _do_spawn(command, opts, vm, is_shell=True)

    def subprocess_shell_quote(s):
        return _do_shell_quote(s, vm)

    arity_1_2 = (1, 2)

    registry.add("subprocess_run",          arity_1_2, subprocess_run)
    registry.add("subprocess_run_async",    arity_1_2, subprocess_run_async)
    registry.add("subprocess_shell",        arity_1_2, subprocess_shell)
    registry.add("subprocess_shell_async",  arity_1_2, subprocess_shell_async)
    registry.add("subprocess_spawn",        arity_1_2, subprocess_spawn)
    registry.add("subprocess_spawn_shell",  arity_1_2, subprocess_spawn_shell)
    registry.add("subprocess_shell_quote",  1,          subprocess_shell_quote)
