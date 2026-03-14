"""Machine-readable AST serialization for Nodus."""

from __future__ import annotations

from dataclasses import is_dataclass


def ast_to_dict(node):
    if node is None:
        return None
    if isinstance(node, list):
        return [ast_to_dict(item) for item in node]
    if isinstance(node, tuple):
        return [ast_to_dict(item) for item in node]
    if isinstance(node, set):
        return sorted((ast_to_dict(item) for item in node), key=lambda item: repr(item))
    if isinstance(node, dict):
        return {str(key): ast_to_dict(value) for key, value in node.items()}
    if is_dataclass(node):
        payload = {"type": type(node).__name__}
        for key, value in node.__dict__.items():
            if key.startswith("_"):
                continue
            payload[key] = ast_to_dict(value)
        return payload
    return node
