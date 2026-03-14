"""Workflow state helpers."""

from __future__ import annotations


def clone_state(value):
    if isinstance(value, dict):
        return {k: clone_state(v) for k, v in value.items()}
    if isinstance(value, list):
        return [clone_state(v) for v in value]
    return value


def checkpoint_public(entry: dict) -> dict:
    if not isinstance(entry, dict):
        return {}
    out = {}
    for key in ("label", "step", "timestamp", "task_id"):
        if key in entry:
            out[key] = entry[key]
    return out


def checkpoints_public(entries: list) -> list[dict]:
    if not isinstance(entries, list):
        return []
    return [checkpoint_public(entry) for entry in entries if isinstance(entry, dict)]
