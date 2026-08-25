"""Coroutine runtime state for Nodus."""

from dataclasses import dataclass, field

# Sentinel for "no deferred return / no deferred re-raise pending". Defined here
# rather than in vm.py because the deferred state is per-coroutine: it is saved
# and restored with the rest of a coroutine's execution context, and `None` can
# not stand in for "nothing pending" (a function may defer a return of nil).
DEFERRED_NONE = object()


@dataclass
class Coroutine:
    closure: object
    state: str = "created"
    ip: int | None = None
    stack: list = field(default_factory=list)
    frames: list = field(default_factory=list)
    handler_stack: list[tuple[int, int, int, int]] = field(default_factory=list)
    # Actions owed to a finally block this coroutine suspended inside: a return
    # deferred by RETURN, or an exception deferred by a raising catch (#361).
    # Per-coroutine, so two coroutines suspended in a finally cannot consume each
    # other's pending action (#371).
    deferred_return: object = DEFERRED_NONE
    deferred_return_depth: int = 0
    deferred_error: object = DEFERRED_NONE
    deferred_error_depth: int = 0
    # The VM this coroutine must be resumed on — the one that spawned it. Set by
    # the `spawn` builtin. Only differs from the scheduler's own VM for a
    # coroutine spawned inside a module function, whose code, builtins and
    # `functions` table belong to that module's detached VM (#339).
    owner_vm: object | None = None
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
    # #502: a timeout the coroutine has been told about but not yet unwound for.
    # The scheduler used to drop a timed-out coroutine where it stood, so its
    # pending `finally` blocks never ran -- a step holding a lock lost its release
    # in exactly the circumstances cleanup exists for, and runtime invariant
    # I-VM-06 says `finally` always executes. Set here instead, so the coroutine
    # is resumed once more to unwind before the error is delivered.
    cancelling: object = None
    workflow_context: dict | None = None
    # #394: set by the graph runner on the coroutine it creates for a step, and
    # by nothing else. A guest's own `coroutine(step_fn)` carries False, so the
    # coroutine door into a step body is closed while the runner's stays open.
    # It rides on the coroutine for the same reason `workflow_context` does --
    # the runner creates it here and the scheduler enters the closure later.
    step_authorized: bool = False
    # ASYNC-MOD-001 (#105): the module execution context (code/functions/globals/
    # ...) this coroutine should run in. Captured at spawn and on every suspend,
    # restored on resume — so a coroutine suspended inside a cross-module call
    # does not leak its swapped context to other coroutines on the shared VM.
    module_ctx: object | None = None
