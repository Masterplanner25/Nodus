"""I/O and filesystem builtin functions for the Nodus VM."""

import os

from nodus.runtime.error_wrap import print_trace
from nodus.runtime.runtime_events import RuntimeEvent
from nodus.runtime.runtime_stats import runtime_time_ms


def register(vm, registry) -> None:
    """Register I/O and path builtins onto the registry."""

    def _ensure_path_string(value, name: str):
        if not isinstance(value, str):
            vm.runtime_error("type", f"{name} expects a string path")

    def _emit_cap(kind: str, path: str) -> None:
        vm.event_bus.emit(RuntimeEvent(
            "capability_use", runtime_time_ms(),
            data={"kind": kind, "path": path},
        ))

    def _trace(func_name: str, exc: BaseException) -> None:
        if getattr(vm, "trace_errors", False):
            print_trace(func_name, exc)

    def builtin_print(value):
        # Silence output while a module is being re-executed purely to re-bind its
        # definitions during resume-rebuild (#328): the rebuild re-runs pure
        # top-level statements, whose prints are throwaway noise that must not leak
        # into the resumed run. Scoped per-VM via the flag — never touches global
        # sys.stdout. (run_workflow/run_goal are likewise skipped under this flag.)
        if getattr(vm, "_suppress_flow_execution", False):
            return None
        print(vm.value_to_string(value, quote_strings=False))
        return None

    def builtin_input(prompt):
        return vm.input_fn(vm.value_to_string(prompt, quote_strings=False))

    def builtin_read_file(path):
        if not isinstance(path, str):
            vm.runtime_error("type", "read_file(path) expects a string path")
        vm._ensure_path_allowed(path, "read_file(path)")
        _emit_cap("fs_read", path)
        try:
            with open(path, "r", encoding="utf-8-sig") as f:
                return f.read()
        except FileNotFoundError as exc:
            _trace("fs.read", exc)
            return vm.make_err("io_error", f'file not found: "{path}"')
        except IsADirectoryError as exc:
            _trace("fs.read", exc)
            return vm.make_err("io_error", f'expected a file, got a directory: "{path}"')
        except PermissionError as exc:
            _trace("fs.read", exc)
            if os.path.isdir(path):
                return vm.make_err("io_error", f'expected a file, got a directory: "{path}"')
            return vm.make_err("io_error", f'permission denied: "{path}"')
        except UnicodeDecodeError as exc:
            _trace("fs.read", exc)
            return vm.make_err("io_error", f'file is not valid UTF-8: "{path}"')
        except OSError as exc:
            _trace("fs.read", exc)
            return vm.make_err("io_error", f'cannot read file: "{path}"')
        except Exception as exc:
            _trace("fs.read", exc)
            return vm.make_err("internal_error", 'unexpected internal error in fs.read')

    def builtin_write_file(path, content):
        if not isinstance(path, str):
            vm.runtime_error("type", "write_file(path, content) expects string path")
        vm._ensure_path_allowed(path, "write_file(path, content)")
        _emit_cap("fs_write", path)
        text = vm.value_to_string(content, quote_strings=False)
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(text)
        except PermissionError as exc:
            _trace("fs.write", exc)
            return vm.make_err("io_error", f'permission denied: "{path}"')
        except IsADirectoryError as exc:
            _trace("fs.write", exc)
            return vm.make_err("io_error", f'expected a file, got a directory: "{path}"')
        except FileNotFoundError as exc:
            _trace("fs.write", exc)
            return vm.make_err("io_error", f'cannot write file, parent directory does not exist: "{path}"')
        except OSError as exc:
            _trace("fs.write", exc)
            return vm.make_err("io_error", f'cannot write file: "{path}"')
        except Exception as exc:
            _trace("fs.write", exc)
            return vm.make_err("internal_error", 'unexpected internal error in fs.write')
        return None

    def builtin_exists(path):
        if not isinstance(path, str):
            vm.runtime_error("type", "exists(path) expects a string path")
        vm._ensure_path_allowed(path, "exists(path)")
        _emit_cap("fs_exists", path)
        try:
            return os.path.exists(path)
        except PermissionError as exc:
            _trace("fs.exists", exc)
            return vm.make_err("io_error", f'permission denied: "{path}"')
        except Exception as exc:
            _trace("fs.exists", exc)
            return vm.make_err("internal_error", 'unexpected internal error in fs.exists')

    def builtin_append_file(path, content):
        if not isinstance(path, str):
            vm.runtime_error("type", "append_file(path, content) expects string path")
        vm._ensure_path_allowed(path, "append_file(path, content)")
        _emit_cap("fs_append", path)
        text = vm.value_to_string(content, quote_strings=False)
        try:
            with open(path, "a", encoding="utf-8") as f:
                f.write(text)
        except PermissionError as exc:
            _trace("fs.append", exc)
            return vm.make_err("io_error", f'permission denied: "{path}"')
        except IsADirectoryError as exc:
            _trace("fs.append", exc)
            return vm.make_err("io_error", f'expected a file, got a directory: "{path}"')
        except FileNotFoundError as exc:
            _trace("fs.append", exc)
            return vm.make_err("io_error", f'cannot write file, parent directory does not exist: "{path}"')
        except OSError as exc:
            _trace("fs.append", exc)
            return vm.make_err("io_error", f'cannot write file: "{path}"')
        except Exception as exc:
            _trace("fs.append", exc)
            return vm.make_err("internal_error", 'unexpected internal error in fs.append')
        return None

    def builtin_mkdir(path):
        if not isinstance(path, str):
            vm.runtime_error("type", "mkdir(path) expects a string path")
        vm._ensure_path_allowed(path, "mkdir(path)")
        try:
            os.makedirs(path, exist_ok=True)
        except FileExistsError as exc:
            _trace("fs.mkdir", exc)
            return vm.make_err("io_error", f'path already exists: "{path}"')
        except PermissionError as exc:
            _trace("fs.mkdir", exc)
            return vm.make_err("io_error", f'permission denied: "{path}"')
        except FileNotFoundError as exc:
            _trace("fs.mkdir", exc)
            return vm.make_err("io_error", f'cannot create directory, parent does not exist: "{path}"')
        except OSError as exc:
            _trace("fs.mkdir", exc)
            return vm.make_err("io_error", f'file system error: "{path}"')
        except Exception as exc:
            _trace("fs.mkdir", exc)
            return vm.make_err("internal_error", 'unexpected internal error in fs.mkdir')
        return None

    def builtin_fs_mkdir(path):
        if not isinstance(path, str):
            vm.runtime_error("type", "fs.mkdir(path) expects a string path")
        vm._ensure_path_allowed(path, "fs.mkdir(path)")
        try:
            os.makedirs(path, exist_ok=False)
        except FileExistsError as exc:
            _trace("fs.mkdir", exc)
            return vm.make_err("io_error", f'path already exists: "{path}"')
        except PermissionError as exc:
            _trace("fs.mkdir", exc)
            return vm.make_err("io_error", f'permission denied: "{path}"')
        except FileNotFoundError as exc:
            _trace("fs.mkdir", exc)
            return vm.make_err("io_error", f'cannot create directory, parent does not exist: "{path}"')
        except OSError as exc:
            _trace("fs.mkdir", exc)
            return vm.make_err("io_error", f'file system error: "{path}"')
        except Exception as exc:
            _trace("fs.mkdir", exc)
            return vm.make_err("internal_error", 'unexpected internal error in fs.mkdir')
        return None

    def builtin_fs_delete(path):
        if not isinstance(path, str):
            vm.runtime_error("type", "fs.delete(path) expects a string path")
        vm._ensure_path_allowed(path, "fs.delete(path)")
        try:
            os.remove(path)
        except FileNotFoundError as exc:
            _trace("fs.delete", exc)
            return vm.make_err("io_error", f'file not found: "{path}"')
        except IsADirectoryError as exc:
            _trace("fs.delete", exc)
            return vm.make_err("io_error", f'cannot delete a directory with fs.delete: "{path}"')
        except PermissionError as exc:
            _trace("fs.delete", exc)
            return vm.make_err("io_error", f'permission denied: "{path}"')
        except OSError as exc:
            _trace("fs.delete", exc)
            return vm.make_err("io_error", f'file system error: "{path}"')
        except Exception as exc:
            _trace("fs.delete", exc)
            return vm.make_err("internal_error", 'unexpected internal error in fs.delete')
        return None

    def builtin_list_dir(path):
        if not isinstance(path, str):
            vm.runtime_error("type", "list_dir(path) expects a string path")
        vm._ensure_path_allowed(path, "list_dir(path)")
        _emit_cap("fs_list", path)
        try:
            return sorted(os.listdir(path))
        except FileNotFoundError as exc:
            _trace("fs.list_dir", exc)
            return vm.make_err("io_error", f'directory not found: "{path}"')
        except NotADirectoryError as exc:
            _trace("fs.list_dir", exc)
            return vm.make_err("io_error", f'expected a directory, got a file: "{path}"')
        except PermissionError as exc:
            _trace("fs.list_dir", exc)
            return vm.make_err("io_error", f'permission denied: "{path}"')
        except OSError as exc:
            _trace("fs.list_dir", exc)
            return vm.make_err("io_error", f'file system error: "{path}"')
        except Exception as exc:
            _trace("fs.list_dir", exc)
            return vm.make_err("internal_error", 'unexpected internal error in fs.list_dir')

    def builtin_path_join(a, b):
        _ensure_path_string(a, "path_join(a, b)")
        _ensure_path_string(b, "path_join(a, b)")
        return os.path.join(a, b)

    def builtin_path_dirname(path):
        _ensure_path_string(path, "path_dirname(path)")
        return os.path.dirname(path)

    def builtin_path_basename(path):
        _ensure_path_string(path, "path_basename(path)")
        return os.path.basename(path)

    def builtin_path_ext(path):
        _ensure_path_string(path, "path_ext(path)")
        return os.path.splitext(path)[1]

    def builtin_path_stem(path):
        _ensure_path_string(path, "path_stem(path)")
        base = os.path.basename(path)
        return os.path.splitext(base)[0]

    def builtin_path_relative(p, base):
        _ensure_path_string(p, "path_relative(p, base)")
        _ensure_path_string(base, "path_relative(p, base)")
        p_abs = os.path.isabs(p)
        base_abs = os.path.isabs(base)
        if p_abs != base_abs:
            return vm.make_err("path_error", f'cannot mix absolute and relative paths: "{p}" and "{base}"')
        try:
            return os.path.relpath(p, base)
        except ValueError as exc:
            _trace("path.relative", exc)
            return vm.make_err("path_error", f'cannot compute relative path: "{p}" from "{base}"')
        except Exception as exc:
            _trace("path.relative", exc)
            return vm.make_err("path_error", f'path error in path.relative: {exc}')

    def builtin_path_absolute(p):
        _ensure_path_string(p, "path_absolute(p)")
        try:
            return os.path.abspath(p)
        except (OSError, ValueError) as exc:
            _trace("path.absolute", exc)
            return vm.make_err("path_error", f'cannot resolve absolute path: {exc}')
        except Exception as exc:
            _trace("path.absolute", exc)
            return vm.make_err("path_error", f'path error in path.absolute: {exc}')

    registry.add("print", 1, builtin_print)
    registry.add("input", 1, builtin_input)
    registry.add("read_file", 1, builtin_read_file)
    registry.add("write_file", 2, builtin_write_file)
    registry.add("exists", 1, builtin_exists)
    registry.add("path_exists", 1, builtin_exists)
    registry.add("append_file", 2, builtin_append_file)
    registry.add("mkdir", 1, builtin_mkdir)
    registry.add("list_dir", 1, builtin_list_dir)
    registry.add("path_join", 2, builtin_path_join)
    registry.add("path_dirname", 1, builtin_path_dirname)
    registry.add("path_basename", 1, builtin_path_basename)
    registry.add("path_ext", 1, builtin_path_ext)
    registry.add("path_stem", 1, builtin_path_stem)
    registry.add("fs_mkdir", 1, builtin_fs_mkdir)
    registry.add("fs_delete", 1, builtin_fs_delete)
    registry.add("path_relative", 2, builtin_path_relative)
    registry.add("path_absolute", 1, builtin_path_absolute)
