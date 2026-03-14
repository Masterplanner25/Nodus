"""Compatibility shim for legacy task_graph imports."""

from nodus.orchestration import task_graph as _task_graph

_GRAPH_REGISTRY = _task_graph._GRAPH_REGISTRY
_GRAPH_VMS = _task_graph._GRAPH_VMS

from nodus.orchestration.task_graph import *  # noqa: F401,F403

__all__ = list(getattr(_task_graph, "__all__", [])) + [
    "_GRAPH_REGISTRY",
    "_GRAPH_VMS",
]
