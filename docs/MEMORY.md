# Nodus Memory Integration

Nodus has first-class memory primitives backed by A.I.N.D.Y.'s Memory Bridge.

## Core primitives (always available)

### recall(query, tags, limit)
Retrieve relevant memories before executing a task.

### remember(content, type, tags)
Store a memory after task execution.

### suggest(query, tags)
Get suggestions based on past successful outcomes.

### record_outcome(node_id, outcome)
Record whether a recalled memory was helpful.

## stdlib module (import memory)
Extended memory operations via the memory stdlib.

## The execution loop
recall -> execute -> remember -> record_outcome

This loop is what makes Nodus tasks self-improving over time -
each execution makes future executions smarter.

## Federation (Multi-Agent Memory)

Agent memory is namespaced (e.g. "arm", "genesis", "nodus").
Each agent has private memory and can share nodes across agents.

### Shared vs Private
- Shared memory: visible to all agents for the same user
- Private memory: visible only to the source agent

### Cross-agent queries
Use federation helpers to query shared memory from other agents:

- `memory.recall_from(agent, query, tags, limit)`
- `memory.recall_all(query, tags, limit)`
- `memory.share(node_id)`

Genesis and ARM automatically share insights by default.
