"""Memory builtins — flat KV and namespaced recall/share operations."""

from __future__ import annotations

from nodus.services.memory_runtime import (
    recall_all,
    recall_from,
    share,
)


def register(vm, registry) -> None:
    # Existing flat KV operations (extracted from VM.__init__ inline dict)
    registry.add("memory_get", 1, vm.builtin_memory_get)
    registry.add("memory_put", 2, vm.builtin_memory_put)
    registry.add("memory_delete", 1, vm.builtin_memory_delete)
    registry.add("memory_keys", 0, vm.builtin_memory_keys)
    registry.add("memory_has", 1, vm.builtin_memory_has)

    # Namespaced memory operations (Phase 6B)
    def memory_recall_from(ns, key):
        try:
            return recall_from(ns, key, vm=vm)
        except ValueError as err:
            vm.runtime_error("type", str(err))

    def memory_recall_all(ns):
        try:
            return recall_all(ns, vm=vm)
        except ValueError as err:
            vm.runtime_error("type", str(err))

    def memory_share(ns, key, value):
        try:
            return share(ns, key, value, vm=vm)
        except ValueError as err:
            vm.runtime_error("type", str(err))

    registry.add("memory_recall_from", 2, memory_recall_from)
    registry.add("memory_recall_all", 1, memory_recall_all)
    registry.add("memory_share", 3, memory_share)
