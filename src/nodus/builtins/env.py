"""Environment variable builtins for the Nodus VM (std:env)."""

import os


def register(vm, registry) -> None:
    """Register env_* builtins onto the registry."""

    def _validate_name(name):
        if not isinstance(name, str):
            vm.runtime_error("type", "env: variable name must be a string")
        if "=" in name or "\x00" in name:
            return vm.make_err(
                "env_error",
                f"invalid environment variable name: {name!r}",
                payload={"category": "invalid_name", "name": name},
            )
        return None

    def builtin_env_get(name, default=None):
        if not isinstance(name, str):
            vm.runtime_error("type", "env.get: name must be a string")
        return os.environ.get(name, default)

    def builtin_env_set(name, value):
        err = _validate_name(name)
        if err is not None:
            return err
        if not isinstance(value, str):
            vm.runtime_error("type", "env.set: value must be a string")
        prev = os.environ.get(name)
        os.environ[name] = value
        return prev

    def builtin_env_unset(name):
        if not isinstance(name, str):
            vm.runtime_error("type", "env.unset: name must be a string")
        return os.environ.pop(name, None)

    def builtin_env_has(name):
        if not isinstance(name, str):
            vm.runtime_error("type", "env.has: name must be a string")
        return name in os.environ

    def builtin_env_list():
        return dict(os.environ)

    def builtin_env_list_keys():
        return list(os.environ.keys())

    registry.add("env_get", (1, 2), builtin_env_get)
    registry.add("env_set", 2, builtin_env_set)
    registry.add("env_unset", 1, builtin_env_unset)
    registry.add("env_has", 1, builtin_env_has)
    registry.add("env_list", 0, builtin_env_list)
    registry.add("env_list_keys", 0, builtin_env_list_keys)
