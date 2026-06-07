from __future__ import annotations

from nodus_memory import (
    MemoryFramework,
    MemoryLink,
    MemoryNode,
    MemoryTrace,
    RecallRequest,
)


class StubEmbeddingProvider:
    def embed_text(self, text: str) -> list[float]:
        lowered = text.lower()
        return [
            1.0 if "failure" in lowered else 0.0,
            1.0 if "deploy" in lowered else 0.0,
            1.0 if "success" in lowered else 0.0,
        ]


def build_framework() -> MemoryFramework:
    return MemoryFramework(embedding_provider=StubEmbeddingProvider())


def seed_memory(memory: MemoryFramework) -> None:
    memory.write_node(
        MemoryNode(
            node_id="n1",
            content="Deployment failure due to missing migration",
            tags=["deploy", "failure"],
            node_type="event",
            memory_type="failure",
            source="runtime",
            scope_id="scope-a",
            trace_id="trace-1",
            embedding=None,
            impact_score=4.0,
            usage_count=2,
            success_rate=0.0,
        )
    )
    memory.write_node(
        MemoryNode(
            node_id="n2",
            content="Deployment success after applying migration",
            tags=["deploy", "success"],
            node_type="event",
            memory_type="outcome",
            source="runtime",
            scope_id="scope-a",
            trace_id="trace-1",
            embedding=None,
            impact_score=3.0,
            usage_count=1,
            success_rate=1.0,
        )
    )
    memory.write_node(
        MemoryNode(
            node_id="n3",
            content="General coding insight about tests",
            tags=["tests", "insight"],
            node_type="note",
            memory_type="insight",
            source="runtime",
            scope_id="scope-a",
            trace_id="trace-2",
            embedding=None,
            impact_score=1.0,
            usage_count=0,
            success_rate=None,
        )
    )
    memory.link_nodes(MemoryLink("n1", "n2", "causal", 0.9))
    memory.write_trace(MemoryTrace("trace-1", ["n1", "n2"]))
    memory.write_trace(MemoryTrace("trace-2", ["n3"]))


def test_node_write_and_trace_round_trip() -> None:
    memory = build_framework()
    seed_memory(memory)
    assert memory.store.get_node("n1") is not None
    trace = memory.store.get_trace("trace-1")
    assert trace is not None
    assert trace.node_ids == ["n1", "n2"]


def test_tag_recall() -> None:
    memory = build_framework()
    seed_memory(memory)
    result = memory.recall(
        RecallRequest(
            query="deploy",
            scope_id="scope-a",
            strategy_names=["tag"],
            limit=5,
            token_budget=50,
            required_tags=["deploy"],
        )
    )
    assert {node.node_id for node in result.nodes} == {"n1", "n2"}


def test_trace_and_causal_recall() -> None:
    memory = build_framework()
    seed_memory(memory)
    result = memory.recall(
        RecallRequest(
            query="deploy",
            scope_id="scope-a",
            strategy_names=["trace", "causal"],
            limit=5,
            token_budget=50,
            trace_id="trace-1",
        )
    )
    assert {node.node_id for node in result.nodes} == {"n1", "n2"}


def test_semantic_recall_prefers_failure_query() -> None:
    memory = build_framework()
    seed_memory(memory)
    result = memory.recall(
        RecallRequest(
            query="deployment failure",
            scope_id="scope-a",
            strategy_names=["semantic"],
            limit=2,
            token_budget=50,
        )
    )
    assert result.nodes[0].node_id == "n1"
    assert "similarity" in result.score_breakdowns["n1"]


def test_context_respects_token_budget() -> None:
    memory = build_framework()
    seed_memory(memory)
    context = memory.build_context(
        RecallRequest(
            query="deploy failure success",
            scope_id="scope-a",
            strategy_names=["semantic", "tag"],
            limit=5,
            token_budget=5,
            required_tags=["deploy"],
        )
    )
    assert context.used_tokens <= 5
    assert context.truncated is True


def test_feedback_updates_usage_and_success_rate() -> None:
    memory = build_framework()
    seed_memory(memory)
    updated = memory.record_feedback(node_ids=["n3"], success=True)
    assert updated[0].usage_count == 1
    assert updated[0].success_rate == 1.0
