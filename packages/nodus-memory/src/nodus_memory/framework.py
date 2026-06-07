from __future__ import annotations

from .models import MemoryContext, MemoryLink, MemoryNode, MemoryTrace, RecallRequest, RecallResult
from .policies import (
    ContextAssembler,
    DefaultContextAssembler,
    DefaultFeedbackPolicy,
    DefaultScoringPolicy,
    EmbeddingProvider,
    FeedbackPolicy,
    ScoringPolicy,
    TokenCounter,
    WhitespaceTokenCounter,
)
from .store import InMemoryMemoryStore, MemoryStore
from .strategies import (
    CausalRecallStrategy,
    RecallStrategy,
    SemanticRecallStrategy,
    TagRecallStrategy,
    TraceRecallStrategy,
)


class MemoryFramework:
    def __init__(
        self,
        *,
        store: MemoryStore | None = None,
        embedding_provider: EmbeddingProvider | None = None,
        token_counter: TokenCounter | None = None,
        scoring_policy: ScoringPolicy | None = None,
        feedback_policy: FeedbackPolicy | None = None,
        context_assembler: ContextAssembler | None = None,
        strategies: dict[str, RecallStrategy] | None = None,
    ) -> None:
        self.store = store or InMemoryMemoryStore()
        self.embedding_provider = embedding_provider
        self.token_counter = token_counter or WhitespaceTokenCounter()
        self.scoring_policy = scoring_policy or DefaultScoringPolicy()
        self.feedback_policy = feedback_policy or DefaultFeedbackPolicy()
        self.context_assembler = context_assembler or DefaultContextAssembler()
        self.strategies = strategies or {
            TagRecallStrategy.name: TagRecallStrategy(),
            TraceRecallStrategy.name: TraceRecallStrategy(),
            CausalRecallStrategy.name: CausalRecallStrategy(),
            SemanticRecallStrategy.name: SemanticRecallStrategy(),
        }

    def write_node(self, node: MemoryNode) -> MemoryNode:
        if node.embedding is None and self.embedding_provider is not None:
            node.embedding = self.embedding_provider.embed_text(node.content)
        return self.store.upsert_node(node)

    def link_nodes(self, link: MemoryLink) -> MemoryLink:
        return self.store.upsert_link(link)

    def write_trace(self, trace: MemoryTrace) -> MemoryTrace:
        return self.store.upsert_trace(trace)

    def _rank_and_assemble(
        self,
        request: RecallRequest,
    ) -> tuple[list[tuple[float, MemoryNode, dict[str, float]]], MemoryContext]:
        query_embedding = self.embedding_provider.embed_text(request.query) if self.embedding_provider is not None else None
        candidates: dict[str, MemoryNode] = {}
        for strategy_name in request.strategy_names:
            strategy = self.strategies[strategy_name]
            for node in strategy.recall(request, store=self.store, embedding_provider=self.embedding_provider):
                if node.scope_id == request.scope_id:
                    if request.memory_types and node.memory_type not in request.memory_types:
                        continue
                    candidates[node.node_id] = node

        scored: list[tuple[float, MemoryNode, dict[str, float]]] = []
        for node in candidates.values():
            score, breakdown = self.scoring_policy.score(
                node,
                request=request,
                query_embedding=query_embedding,
                store=self.store,
            )
            scored.append((score, node, breakdown))
        scored.sort(key=lambda item: item[0], reverse=True)
        trimmed = scored[: request.limit]
        context = self.context_assembler.assemble(
            [node for _, node, _ in trimmed],
            token_budget=request.token_budget,
            token_counter=self.token_counter,
        )
        return trimmed, context

    def recall(self, request: RecallRequest) -> RecallResult:
        trimmed, context = self._rank_and_assemble(request)
        retained_ids = set(context.node_ids)
        filtered = [(score, node, breakdown) for score, node, breakdown in trimmed if node.node_id in retained_ids]
        return RecallResult(
            nodes=[node for _, node, _ in filtered],
            scores={node.node_id: score for score, node, _ in filtered},
            score_breakdowns={node.node_id: breakdown for _, node, breakdown in filtered},
            truncated=context.truncated,
        )

    def build_context(self, request: RecallRequest) -> MemoryContext:
        _, context = self._rank_and_assemble(request)
        return context

    def record_feedback(self, *, node_ids: list[str], success: bool) -> list[MemoryNode]:
        updated: list[MemoryNode] = []
        for node_id in node_ids:
            node = self.store.get_node(node_id)
            if node is None:
                continue
            revised = self.feedback_policy.apply(node, success=success)
            self.store.upsert_node(revised)
            updated.append(revised)
        return updated
