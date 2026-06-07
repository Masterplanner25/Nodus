from __future__ import annotations

from typing import Protocol

from .models import MemoryNode, RecallRequest
from .policies import EmbeddingProvider, cosine_similarity
from .store import MemoryStore


class RecallStrategy(Protocol):
    name: str

    def recall(
        self,
        request: RecallRequest,
        *,
        store: MemoryStore,
        embedding_provider: EmbeddingProvider | None,
    ) -> list[MemoryNode]: ...


class TagRecallStrategy:
    name = "tag"

    def recall(
        self,
        request: RecallRequest,
        *,
        store: MemoryStore,
        embedding_provider: EmbeddingProvider | None,
    ) -> list[MemoryNode]:
        _ = embedding_provider
        nodes = store.list_nodes(request.scope_id)
        if not request.required_tags and not request.memory_types:
            return []
        tag_filter = set(request.required_tags)
        type_filter = set(request.memory_types)
        return [
            node
            for node in nodes
            if (not tag_filter or tag_filter & set(node.tags))
            and (not type_filter or node.memory_type in type_filter)
        ]


class TraceRecallStrategy:
    name = "trace"

    def recall(
        self,
        request: RecallRequest,
        *,
        store: MemoryStore,
        embedding_provider: EmbeddingProvider | None,
    ) -> list[MemoryNode]:
        _ = embedding_provider
        if not request.trace_id:
            return []
        trace = store.get_trace(request.trace_id)
        if trace is None:
            return []
        nodes: list[MemoryNode] = []
        for node_id in trace.node_ids:
            node = store.get_node(node_id)
            if node is not None and node.scope_id == request.scope_id:
                nodes.append(node)
        return nodes


class CausalRecallStrategy:
    name = "causal"

    def recall(
        self,
        request: RecallRequest,
        *,
        store: MemoryStore,
        embedding_provider: EmbeddingProvider | None,
    ) -> list[MemoryNode]:
        _ = embedding_provider
        nodes = TraceRecallStrategy().recall(request, store=store, embedding_provider=None)
        related: list[MemoryNode] = []
        seen = {node.node_id for node in nodes}
        for node in nodes:
            for link in store.list_links(node.node_id):
                target_id = link.target_node_id if link.source_node_id == node.node_id else link.source_node_id
                candidate = store.get_node(target_id)
                if candidate is not None and candidate.scope_id == request.scope_id and candidate.node_id not in seen:
                    related.append(candidate)
                    seen.add(candidate.node_id)
        return related


class SemanticRecallStrategy:
    name = "semantic"

    def recall(
        self,
        request: RecallRequest,
        *,
        store: MemoryStore,
        embedding_provider: EmbeddingProvider | None,
    ) -> list[MemoryNode]:
        if embedding_provider is None:
            return []
        query_embedding = embedding_provider.embed_text(request.query)
        ranked: list[tuple[float, MemoryNode]] = []
        for node in store.list_nodes(request.scope_id):
            if node.embedding is None:
                continue
            similarity = cosine_similarity(query_embedding, node.embedding)
            ranked.append((similarity, node))
        ranked.sort(key=lambda item: item[0], reverse=True)
        return [node for _, node in ranked[: max(request.limit * 2, request.limit)]]
