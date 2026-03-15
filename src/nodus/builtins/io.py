"""I/O and filesystem builtin functions for the Nodus VM."""

import os


def register(vm, registry) -> None:
    """Register I/O and path builtins onto the registry."""

    def _ensure_path_string(value, name: str):
        if not isinstance(value, str):
            vm.runtime_error("type", f"{name} expects a string path")

    def builtin_print(value):
        print(vm.value_to_string(value, quote_strings=False))
        return None

    def builtin_input(prompt):
        return vm.input_fn(vm.value_to_string(prompt, quote_strings=False))

    def builtin_read_file(path):
        if not isinstance(path, str):
            vm.runtime_error("type", "read_file(path) expects a string path")
        vm._ensure_path_allowed(path, "read_file(path)")
        try:
            with open(path, "r", encoding="utf-8") as f:
                return f.read()
        except Exception as err:
            vm.runtime_error("runtime", f"read_file failed for {path!r}: {err}")

    def builtin_write_file(path, content):
        if not isinstance(path, str):
            vm.runtime_error("type", "write_file(path, content) expects string path")
        vm._ensure_path_allowed(path, "write_file(path, content)")
        text = vm.value_to_string(content, quote_strings=False)
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(text)
        except Exception as err:
            vm.runtime_error("runtime", f"write_file failed for {path!r}: {err}")
        return None

    def builtin_exists(path):
        if not isinstance(path, str):
            vm.runtime_error("type", "exists(path) expects a string path")
        vm._ensure_path_allowed(path, "exists(path)")
        return os.path.exists(path)

    def builtin_append_file(path, content):
        if not isinstance(path, str):
            vm.runtime_error("type", "append_file(path, content) expects string path")
        vm._ensure_path_allowed(path, "append_file(path, content)")
        text = vm.value_to_string(content, quote_strings=False)
        try:
            with open(path, "a", encoding="utf-8") as f:
                f.write(text)
        except Exception as err:
            vm.runtime_error("runtime", f"append_file failed for {path!r}: {err}")
        return None

    def builtin_mkdir(path):
        if not isinstance(path, str):
            vm.runtime_error("type", "mkdir(path) expects a string path")
        vm._ensure_path_allowed(path, "mkdir(path)")
        try:
            os.makedirs(path, exist_ok=True)
        except Exception as err:
            vm.runtime_error("runtime", f"mkdir failed for {path!r}: {err}")
        return None

    def builtin_list_dir(path):
        if not isinstance(path, str):
            vm.runtime_error("type", "list_dir(path) expects a string path")
        vm._ensure_path_allowed(path, "list_dir(path)")
        try:
            return sorted(os.listdir(path))
        except Exception as err:
            vm.runtime_error("runtime", f"list_dir failed for {path!r}: {err}")

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
        ext = os.path.splitext(path)[1]
        if ext.startswith("."):
            return ext[1:]
        return ext

    def builtin_path_stem(path):
        _ensure_path_string(path, "path_stem(path)")
        base = os.path.basename(path)
        return os.path.splitext(base)[0]

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
