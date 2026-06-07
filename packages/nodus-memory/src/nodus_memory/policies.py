from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import replace
from typing import Protocol

from .models import MemoryContext, MemoryNode, RecallRequest
from .store import MemoryStore


class EmbeddingProvider(Protocol):
    def embed_text(self, text: str) -> list[float]: ...


class TokenCounter(Protocol):
    def count_tokens(self, text: str) -> int: ...


class ScoringPolicy(Protocol):
    def score(
        self,
        node: MemoryNode,
        *,
        request: RecallRequest,
        query_embedding: list[float] | None,
        store: MemoryStore,
    ) -> tuple[float, dict[str, float]]: ...


class FeedbackPolicy(Protocol):
    def apply(self, node: MemoryNode, *, success: bool) -> MemoryNode: ...


class ContextAssembler(Protocol):
    def assemble(
        self,
        nodes: Sequence[MemoryNode],
        *,
        token_budget: int,
        token_counter: TokenCounter,
    ) -> MemoryContext: ...


class WhitespaceTokenCounter:
    def count_tokens(self, text: str) -> int:
        return len([part for part in text.split() if part.strip()])


def cosine_similarity(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    mag_a = math.sqrt(sum(x * x for x in a))
    mag_b = math.sqrt(sum(y * y for y in b))
    if mag_a == 0.0 or mag_b == 0.0:
        return 0.0
    return dot / (mag_a * mag_b)


class DefaultScoringPolicy:
    def score(
        self,
        node: MemoryNode,
        *,
        request: RecallRequest,
        query_embedding: list[float] | None,
        store: MemoryStore,
    ) -> tuple[float, dict[str, float]]:
        _ = store
        similarity = 0.0
        if query_embedding is not None and node.embedding is not None:
            similarity = max(0.0, cosine_similarity(query_embedding, node.embedding))
        tag_bonus = 0.1 if request.required_tags and set(request.required_tags) & set(node.tags) else 0.0
        trace_bonus = 0.15 if request.trace_id and node.trace_id == request.trace_id else 0.0
        impact_component = max(0.0, min(1.0, node.impact_score / 5.0))
        usage_component = min(1.0, node.usage_count / 10.0)
        success_component = max(0.0, min(1.0, node.success_rate or 0.0))
        score = (
            similarity * 0.45
            + impact_component * 0.20
            + usage_component * 0.10
            + success_component * 0.10
            + tag_bonus
            + trace_bonus
        )
        breakdown = {
            "similarity": round(similarity, 4),
            "impact": round(impact_component, 4),
            "usage": round(usage_component, 4),
            "success": round(success_component, 4),
            "tag_bonus": round(tag_bonus, 4),
            "trace_bonus": round(trace_bonus, 4),
        }
        return round(score, 4), breakdown


class DefaultFeedbackPolicy:
    def apply(self, node: MemoryNode, *, success: bool) -> MemoryNode:
        count = node.usage_count + 1
        previous_success = node.success_rate if node.success_rate is not None else 0.0
        updated_success = ((previous_success * node.usage_count) + (1.0 if success else 0.0)) / count
        return replace(
            node,
            usage_count=count,
            success_rate=round(updated_success, 4),
        )


class DefaultContextAssembler:
    def assemble(
        self,
        nodes: Sequence[MemoryNode],
        *,
        token_budget: int,
        token_counter: TokenCounter,
    ) -> MemoryContext:
        items: list[MemoryNode] = []
        used_tokens = 0
        truncated = False
        for node in nodes:
            node_tokens = token_counter.count_tokens(node.content)
            if used_tokens + node_tokens > token_budget:
                truncated = True
                break
            items.append(node)
            used_tokens += node_tokens
        return MemoryContext(
            items=list(items),
            node_ids=[node.node_id for node in items],
            used_tokens=used_tokens,
            token_budget=token_budget,
            truncated=truncated,
        )
