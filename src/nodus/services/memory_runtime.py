"""Runtime memory store for Nodus built-ins and services."""

from __future__ import annotations

from nodus.vm.runtime_values import clone_json_value, is_json_safe, payload_keys


class MemoryStore:
    def __init__(self, initial: dict | None = None):
        self._values: dict[str, object] = {}
        if isinstance(initial, dict):
            for key, value in initial.items():
                if isinstance(key, str) and is_json_safe(value):
                    self._values[key] = clone_json_value(value)

    def get(self, key: str):
        return clone_json_value(self._values.get(key))

    def put(self, key: str, value):
        self._values[key] = clone_json_value(value)
        return clone_json_value(value)

    def delete(self, key: str):
        existed = key in self._values
        value = clone_json_value(self._values.pop(key, None))
        return existed, value

    def keys(self) -> list[str]:
        return sorted(self._values.keys())

    def items(self) -> dict[str, object]:
        return clone_json_value(self._values)

    def snapshot(self) -> dict[str, object]:
        return self.items()

    def load_snapshot(self, values: dict | None) -> None:
        self._values = {}
        if isinstance(values, dict):
            for key, value in values.items():
                if isinstance(key, str) and is_json_safe(value):
                    self._values[key] = clone_json_value(value)


GLOBAL_MEMORY_STORE = MemoryStore()


def get_store(vm=None) -> MemoryStore:
    store = getattr(vm, "memory_store", None) if vm is not None else None
    if isinstance(store, MemoryStore):
        return store
    return GLOBAL_MEMORY_STORE


def get_value(key: str, *, vm=None):
    _validate_key(key)
    store = get_store(vm)
    present = key in store.keys()
    value = store.get(key)
    _emit(vm, "memory_get", key=key, value=value, found=present)
    return value


def put_value(key: str, value, *, vm=None):
    _validate_key(key)
    if not is_json_safe(value):
        raise ValueError("Memory values must be JSON-safe")
    store = get_store(vm)
    stored = store.put(key, value)
    _emit(vm, "memory_put", key=key, value=stored)
    return stored


def delete_value(key: str, *, vm=None):
    _validate_key(key)
    store = get_store(vm)
    existed, value = store.delete(key)
    _emit(vm, "memory_delete", key=key, value=value, found=existed)
    return existed


def list_keys(*, vm=None) -> list[str]:
    return get_store(vm).keys()


def export_memory(*, vm=None) -> dict[str, object]:
    return get_store(vm).items()


def _validate_key(key) -> None:
    if not isinstance(key, str) or not key:
        raise ValueError("Memory keys must be non-empty strings")


def _emit(vm, event_type: str, *, key: str, value=None, found: bool | None = None) -> None:
    if vm is None or getattr(vm, "event_bus", None) is None:
        return
    data = {"key": key, "payload_keys": payload_keys(value)}
    if found is not None:
        data["found"] = bool(found)
    if hasattr(vm, "runtime_adapter_event_data"):
        data.update(vm.runtime_adapter_event_data({"key": key}, ok=found if found is not None else None))
    vm.event_bus.emit_event(event_type, name=key, data=data)
