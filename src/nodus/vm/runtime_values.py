"""Shared JSON-safe runtime value helpers."""

from __future__ import annotations

import copy


def is_json_safe(value) -> bool:
    if value is None:
        return True
    if isinstance(value, (bool, int, float, str)):
        return True
    if isinstance(value, list):
        return all(is_json_safe(item) for item in value)
    if isinstance(value, dict):
        return all(isinstance(key, str) and is_json_safe(item) for key, item in value.items())
    return False


def clone_json_value(value):
    return copy.deepcopy(value)


def payload_keys(value) -> list[str]:
    if not isinstance(value, dict):
        return []
    return sorted(str(key) for key in value.keys())
