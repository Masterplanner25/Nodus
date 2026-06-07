from __future__ import annotations

from typing import Protocol

from .models import MemoryLink, MemoryNode, MemoryTrace


class MemoryStore(Protocol):
    def upsert_node(self, node: MemoryNode) -> MemoryNode: ...

    def get_node(self, node_id: str) -> MemoryNode | None: ...

    def list_nodes(self, scope_id: str) -> list[MemoryNode]: ...

    def upsert_link(self, link: MemoryLink) -> MemoryLink: ...

    def list_links(self, node_id: str) -> list[MemoryLink]: ...

    def upsert_trace(self, trace: MemoryTrace) -> MemoryTrace: ...

    def get_trace(self, trace_id: str) -> MemoryTrace | None: ...


class InMemoryMemoryStore:
    def __init__(self) -> None:
        self._nodes: dict[str, MemoryNode] = {}
        self._links: list[MemoryLink] = []
        self._traces: dict[str, MemoryTrace] = {}

    def upsert_node(self, node: MemoryNode) -> MemoryNode:
        self._nodes[node.node_id] = node
        return node

    def get_node(self, node_id: str) -> MemoryNode | None:
        return self._nodes.get(node_id)

    def list_nodes(self, scope_id: str) -> list[MemoryNode]:
        return [node for node in self._nodes.values() if node.scope_id == scope_id]

    def upsert_link(self, link: MemoryLink) -> MemoryLink:
        self._links = [
            existing
            for existing in self._links
            if not (
                existing.source_node_id == link.source_node_id
                and existing.target_node_id == link.target_node_id
                and existing.relationship_type == link.relationship_type
            )
        ]
        self._links.append(link)
        return link

    def list_links(self, node_id: str) -> list[MemoryLink]:
        return [
            link
            for link in self._links
            if link.source_node_id == node_id or link.target_node_id == node_id
        ]

    def upsert_trace(self, trace: MemoryTrace) -> MemoryTrace:
        self._traces[trace.trace_id] = trace
        return trace

    def get_trace(self, trace_id: str) -> MemoryTrace | None:
        return self._traces.get(trace_id)
