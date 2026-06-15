# `nodus-memory`

> **Status:** v0.1.0 implemented and **published on PyPI** ✅ — `C:\dev\nodus-memory`, 28 tests (Tier 2 core: MemoryNode,
> InMemoryStore, recall, scoring, feedback). Original full adapter
> (192 tests, nodus-lang integration) preserved at github.com/Masterplanner25/nodus-memory.
> This document is the original design spec; the Tier 2 implementation was built against it.

## Summary

`nodus-memory` is a Python-first memory framework for AI-native runtimes. Its
public Python API is the canonical contract that a future thin Nodus builtin
will wrap. The framework exists to make memory a first-class execution
primitive with causal links, recall strategies, deterministic scoring,
token-budgeted context assembly, and feedback-driven learning loops.

V1 scope is a reusable framework shell with in-memory defaults. It is not just
a vector store adapter and not just a prompt helper.

## Public Python API

Required public types:

- `MemoryFramework`
- `MemoryNode`
- `MemoryLink`
- `MemoryTrace`
- `RecallRequest`
- `RecallResult`
- `MemoryContext`
- `RecallStrategy` protocol
- `ScoringPolicy` protocol
- `FeedbackPolicy` protocol
- `ContextAssembler` protocol
- `EmbeddingProvider` protocol
- `TokenCounter` protocol
- `MemoryStore` protocol
- `MemoryFrameworkError`

Canonical surface:

```python
memory = MemoryFramework(...)
memory.write_node(node)
memory.link_nodes(link)
result = memory.recall(request)
context = memory.build_context(request)
memory.record_feedback(node_ids=[...], success=True)
```

Future thin builtins should wrap these typed operations instead of re-creating
memory semantics in the runtime layer.

## Public Model Contracts

### `MemoryNode`

Required fields:

- `node_id: str`
- `content: str`
- `tags: list[str]`
- `node_type: str`
- `memory_type: str`
- `source: str | None`
- `scope_id: str`
- `trace_id: str | None`
- `embedding: list[float] | None`
- `impact_score: float`
- `usage_count: int`
- `success_rate: float | None`
- `metadata: dict[str, object]`
- `created_at: datetime`
- `updated_at: datetime`

### `MemoryLink`

Required fields:

- `source_node_id: str`
- `target_node_id: str`
- `relationship_type: str`
- `weight: float`
- `created_at: datetime`

### `MemoryTrace`

Required fields:

- `trace_id: str`
- `node_ids: list[str]`
- `metadata: dict[str, object]`

### `RecallRequest`

Required fields:

- `query: str`
- `scope_id: str`
- `strategy_names: list[str]`
- `limit: int`
- `token_budget: int`
- `required_tags: list[str]`
- `memory_types: list[str]`
- `trace_id: str | None`
- `operation_type: str | None`

### `RecallResult`

Required fields:

- `nodes: list[MemoryNode]`
- `scores: dict[str, float]`
- `score_breakdowns: dict[str, dict[str, float]]`
- `truncated: bool`

### `MemoryContext`

Required fields:

- `items: list[MemoryNode]`
- `node_ids: list[str]`
- `used_tokens: int`
- `token_budget: int`
- `truncated: bool`

## Core Interfaces

### `MemoryStore`

Required operations:

- `upsert_node(node: MemoryNode) -> MemoryNode`
- `get_node(node_id: str) -> MemoryNode | None`
- `list_nodes(scope_id: str) -> list[MemoryNode]`
- `upsert_link(link: MemoryLink) -> MemoryLink`
- `list_links(node_id: str) -> list[MemoryLink]`
- `upsert_trace(trace: MemoryTrace) -> MemoryTrace`
- `get_trace(trace_id: str) -> MemoryTrace | None`

### `EmbeddingProvider`

Required method:

```python
embed_text(text: str) -> list[float]
```

### `RecallStrategy`

Required method:

```python
recall(request: RecallRequest, *, store: MemoryStore, embedding_provider: EmbeddingProvider | None) -> list[MemoryNode]
```

### `ScoringPolicy`

Required method:

```python
score(node: MemoryNode, *, request: RecallRequest, query_embedding: list[float] | None, store: MemoryStore) -> tuple[float, dict[str, float]]
```

### `ContextAssembler`

Required method:

```python
assemble(nodes: list[MemoryNode], *, token_budget: int, token_counter: TokenCounter) -> MemoryContext
```

### `FeedbackPolicy`

Required method:

```python
apply(node: MemoryNode, *, success: bool) -> MemoryNode
```

## Architecture

Split the framework into five layers:

1. Pure memory models
2. Store and provider protocols
3. Recall strategy layer
4. Scoring and context assembly layer
5. Framework orchestration layer

### Pure memory models

Contains:

- node, link, trace, request, result, and context models
- framework error types

No backend-specific imports are allowed here.

### Store and provider protocols

Contains:

- store interface
- embedding provider interface
- token counter interface

This layer remains backend-agnostic.

### Recall strategy layer

Contains:

- semantic recall
- tag/filter recall
- trace-local recall
- causal-neighbor expansion

Strategies may be composed in one request.

### Scoring and context assembly layer

Contains:

- deterministic multi-signal scoring
- token-budgeted packing
- explainable score breakdowns

### Framework orchestration layer

Contains:

- write node
- link nodes
- write traces
- recall pipeline
- context building
- feedback recording

## Behavior

V1 recall flow:

1. normalize request
2. optionally embed query
3. fetch candidates from requested strategies
4. merge and deduplicate candidates
5. score candidates with explainable components
6. sort and trim to request limit
7. assemble token-budgeted context
8. return ranked results and context metadata

Framework rules:

- `scope_id` is mandatory and is the primary namespace boundary
- explainability is part of the API through score breakdowns
- context assembly must expose truncation and token usage explicitly
- feedback should update usage counts and success-rate signals deterministically

The framework must not:

- expose SQLAlchemy or vector backend details in the public API
- assume one embedding provider
- assume one tokenization backend
- hard-code prompt templates

## Package Dependencies

Core required:

- none beyond Python stdlib typing, math, and datetime facilities

Optional:

- none in core v1

V1 should include in-memory reference implementations for store, embedding, and
token counting so the framework is testable without external infrastructure.

## Test Plan

Required tests:

- node write/read round trip
- link creation and causal expansion
- trace creation and trace-local recall
- tag strategy recall
- semantic strategy recall with deterministic embedding provider
- candidate merge and dedup across strategies
- deterministic score calculation with explainable breakdowns
- token-budgeted context truncation
- feedback updates usage and success rate
- build-context and recall remain consistent on the same request

## Acceptance Criteria

- A future thin Nodus builtin can read, write, recall, and score memory through
  a stable Python API.
- The framework is useful without SQL, pgvector, or provider SDKs.
- Recall, scoring, and context assembly are explainable and deterministic.
- Store, embedding, and token counting remain replaceable adapters.
