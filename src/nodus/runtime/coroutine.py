"""Coroutine runtime state for Nodus."""

from dataclasses import dataclass, field


@dataclass
class Coroutine:
    closure: object
    state: str = "created"
    ip: int | None = None
    stack: list = field(default_factory=list)
    frames: list = field(default_factory=list)
    handler_stack: list[tuple[int, int, int, int]] = field(default_factory=list)
    id: int | None = None
    name: str | None = None
    module: str | None = None
    resume_count: int = 0
    created_time: float | None = None
    last_resume: float | None = None
    last_run_time: float | None = None
    blocked_on: object | None = None
    blocked_reason: str | None = None
    initial_args: list = field(default_factory=list)
    last_result: object | None = None
    task_timeout_ms: float | None = None
    task_started_at: float | None = None
    workflow_context: dict | None = None
    # ASYNC-MOD-001 (#105): the module execution context (code/functions/globals/
    # ...) this coroutine should run in. Captured at spawn and on every suspend,
    # restored on resume — so a coroutine suspended inside a cross-module call
    # does not leak its swapped context to other coroutines on the shared VM.
    module_ctx: object | None = None
