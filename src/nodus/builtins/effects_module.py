"""EffectStore builtins — EXACTLY_ONCE idempotency primitives."""

from __future__ import annotations

import json

try:
    from nodus_retry.effect import compute_action_id
except ImportError:
    import hashlib as _hashlib
    import json as _json

    def compute_action_id(action_type: str, input_payload: dict, *, scope: str) -> str:  # type: ignore[misc]
        payload_bytes = _json.dumps(
            {"action_type": action_type, "payload": input_payload, "scope": scope},
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
        return _hashlib.sha256(payload_bytes).hexdigest()
from nodus.vm.types import Record


def register(vm, registry) -> None:
    def effect_resolve(action_id):
        if not isinstance(action_id, str):
            vm.runtime_error("type", "effect_resolve(action_id) expects a string")
        already_done, cached = vm.effect_store.resolve(action_id)
        cached_val = Record(cached) if isinstance(cached, dict) else cached
        return Record({"done": already_done, "cached": cached_val})

    def effect_pending(action_id, input_hash):
        if not isinstance(action_id, str):
            vm.runtime_error("type", "effect_pending(action_id, input_hash) expects strings")
        if not isinstance(input_hash, str):
            vm.runtime_error("type", "effect_pending(action_id, input_hash) expects strings")
        vm.effect_store.pending(action_id, input_hash)
        return None

    def effect_complete(action_id, status, result):
        if not isinstance(action_id, str):
            vm.runtime_error("type", "effect_complete: action_id must be a string")
        if not isinstance(status, str):
            vm.runtime_error("type", "effect_complete: status must be a string")
        result_dict = None
        if isinstance(result, dict):
            result_dict = result
        elif isinstance(result, Record):
            result_dict = result.fields
        vm.effect_store.complete(action_id, status, result_dict)
        return None

    def effect_action_id(action_type, payload_map, scope):
        if not isinstance(action_type, str):
            vm.runtime_error("type", "effect_action_id: action_type must be a string")
        if not isinstance(scope, str):
            vm.runtime_error("type", "effect_action_id: scope must be a string")
        if isinstance(payload_map, Record):
            payload_dict = payload_map.fields
        elif isinstance(payload_map, dict):
            payload_dict = payload_map
        else:
            vm.runtime_error("type", "effect_action_id: payload must be a map")
        try:
            serializable = json.loads(json.dumps(payload_dict, default=str))
        except Exception:
            serializable = {}
        return compute_action_id(action_type, serializable, scope=scope)

    def effect_store_size():
        return len(vm.effect_store)

    registry.add("effect_resolve", 1, effect_resolve)
    registry.add("effect_pending", 2, effect_pending)
    registry.add("effect_complete", 3, effect_complete)
    registry.add("effect_action_id", 3, effect_action_id)
    registry.add("effect_store_size", 0, effect_store_size)
