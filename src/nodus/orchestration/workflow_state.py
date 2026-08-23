"""Workflow state helpers."""

from __future__ import annotations


def clone_state(value):
    if isinstance(value, dict):
        return {k: clone_state(v) for k, v in value.items()}
    if isinstance(value, list):
        return [clone_state(v) for v in value]
    return value


def checkpoint_public(entry: dict) -> dict:
    if not isinstance(entry, dict):
        return {}
    out = {}
    for key in ("label", "step", "timestamp", "task_id"):
        if key in entry:
            out[key] = entry[key]
    return out


def checkpoints_public(entries: list) -> list[dict]:
    if not isinstance(entries, list):
        return []
    return [checkpoint_public(entry) for entry in entries if isinstance(entry, dict)]


class TrackedState(dict):
    """Workflow state that remembers which task wrote each key.

    Two fan-out branches that read a state key, yield, and write it back lose one
    of the writes: the read-modify-write window is opened by *any* suspension, so
    the last write in wins and the other increment is simply gone. The run reports
    `ok`, nothing is in `failed`, and the value is wrong (#485).

    The reason it goes unnoticed is that the cooperative scheduler serialises a
    step body that never yields, so the obvious test passes and teaches you that
    concurrent state writes are safe. They are safe only until a step does
    something real -- an agent call, an HTTP request, a channel receive. Those are
    what fan-out branches are *for*.

    This does not fix it. Fixing it means the write, not the cell, becomes the
    unit with a policy -- a branch contributing a value the runtime applies at the
    join, rather than assigning into a slot another branch is halfway through
    reading. That is a state-model change and it wants deciding alongside the type
    (#479) and durability (#498) axes, which attach to the same declaration.

    What this does is make it **loud**. Recording the writer per key costs one
    dict append and turns a silent wrong answer into a diagnosable one, which is
    worth having before the larger design lands rather than after.
    """

    __slots__ = ("_writes", "_writer", "_steps")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # key -> ordered task ids that wrote it. A list rather than a set: the
        # order is what tells you which write won.
        self._writes: dict[str, list[str]] = {}
        # Injected by the runner. Returns the task id currently executing, or None
        # outside a step -- state written by the initializer has no writer and is
        # not a conflict with anything.
        self._writer = None
        # task_id -> StepWrites, open for the duration of that step. The write
        # *values* live here; `_writes` above only ever knew who wrote, which is
        # enough to warn and not enough to merge.
        self._steps: dict[str, StepWrites] = {}

    def track_writes_with(self, writer) -> None:
        self._writer = writer

    def __setitem__(self, key, value):
        writer = self._writer
        if writer is not None:
            task_id = writer()
            if task_id is not None:
                self._writes.setdefault(str(key), []).append(task_id)
                step = self._steps.get(task_id)
                if step is not None and not step.closed:
                    step.record(key, value)
        super().__setitem__(key, value)

    def begin_step(self, task_id: str) -> StepWrites:
        """Open a write record for a step that is about to run.

        Re-entrant: a step resuming after a `workflow_wait` gets a fresh record,
        because the previous one was closed when it suspended.
        """
        step = StepWrites(task_id)
        self._steps[task_id] = step
        return step

    def end_step(self, task_id: str) -> list[str]:
        """Close a step's write record and return the keys it wrote."""
        step = self._steps.pop(task_id, None)
        if step is None:
            return []
        return step.close()

    def open_step(self, task_id: str) -> StepWrites | None:
        return self._steps.get(task_id)

    def writers(self) -> dict[str, list[str]]:
        return {key: list(ids) for key, ids in self._writes.items()}


class StepWrites:
    """What one step wrote, recorded per key, closed when the step ends.

    This is the write-side half of the model #485 needs: a step's writes become a
    *record* the runtime can act on at the join, rather than only a mutation that
    has already happened. Step 3 turns that record into a fold; today it is
    observed and the write still lands exactly when it always did.

    **Reads are deliberately not isolated, and that is a correction to the plan.**
    The scoping comment on #485 proposed a per-task overlay that steps read
    through -- a snapshot at step start, applied at step end. Implemented, it
    changed a correct program into a wrong one:

        step a { counter = counter + 1i }
        step b { counter = counter + 1i }

    With no suspension the scheduler runs these one after the other, so `b` reads
    what `a` wrote and the answer is 2. Snapshotting at step start makes both read
    0 and the answer becomes 1 -- the lost update the issue is about, newly
    introduced in the case that did not have it, by the change meant to fix it.

    And the fold does not need it. Under `merge: "sum"`, `counter += 1i`
    contributes `1`, and that `1` comes from the expression, not from reading the
    cell. Read isolation is a separable property with its own cost, so it is not
    smuggled in here; it is recorded on the issue as its own decision.
    """

    __slots__ = ("task_id", "_order", "_values", "closed")

    def __init__(self, task_id: str | None = None):
        self.task_id = task_id
        # Ordered and deduped: a key written twice by one step is one
        # contribution from it, and order is what decides `any`.
        self._order: list[str] = []
        self._values: dict[str, object] = {}
        self.closed = False

    def record(self, key, value) -> None:
        name = str(key)
        if name not in self._values:
            self._order.append(name)
        self._values[name] = value

    def keys_written(self) -> list[str]:
        return list(self._order)

    def value_of(self, key: str):
        return self._values[str(key)]

    def items(self):
        return [(key, self._values[key]) for key in self._order]

    def close(self) -> list[str]:
        """End of step. Idempotent; returns the keys this step wrote.

        Called from every path a task leaves `running` by -- success on either
        execution path, failure, and suspension at a `workflow_wait`. Idempotent
        because those paths are not mutually exclusive in every ordering.

        This is where a fold will be applied. It is deliberately inert today: a
        policy that changed behaviour before the emission model exists would be
        the "declared but not enforced" shape this codebase already has five
        instances of.
        """
        if self.closed:
            return []
        self.closed = True
        return list(self._order)


def concurrent_write_conflicts(state, ordered) -> list[dict]:
    """Keys written by two tasks that the graph does not order.

    The test is **structural, not temporal**. An earlier attempt compared the
    recorded start/finish timings, and it flagged a plain sequential `a -> b -> c`
    writing one key: those steps are instant, so their millisecond timestamps are
    identical and every interval overlaps every other. Wall-clock cannot tell
    "sequential and fast" from "concurrent" at that resolution.

    Dependency order can, exactly: if there is a path from one task to the other,
    they cannot run at the same time, whatever the clock says.

    It also reports the case that has not gone wrong *yet*. Two independent steps
    that happen to be serialised -- because neither yielded -- are still declared
    concurrent, and the warning is the point: the cooperative scheduler makes the
    obvious test pass and teaches you that concurrent state writes are safe. They
    are safe only until a step does something real. Flagging on declaration warns
    before the step grows its first `sleep` or agent call, which is the only
    moment the warning is cheap to act on.

    `ordered(a, b)` returns True when the graph orders those two task ids either
    way round.
    """
    if not isinstance(state, TrackedState):
        return []

    conflicts: list[dict] = []
    for key, task_ids in sorted(state.writers().items()):
        distinct = list(dict.fromkeys(task_ids))
        if len(distinct) < 2:
            continue
        pair = None
        for i, first in enumerate(distinct):
            for second in distinct[i + 1:]:
                if not ordered(first, second):
                    pair = [first, second]
                    break
            if pair:
                break
        if pair:
            conflicts.append({"key": key, "tasks": pair, "winner": task_ids[-1]})
    return conflicts


# How concurrent writes to one cell combine.
#
#   any    last write wins. Today's behaviour and the default -- but saying it out
#          loud is what silences the concurrent-write warning, so the warning is
#          quieted by stating intent rather than by ignoring it.
#   once   a second concurrent writer is an error.
#
# No fold (`sum`, `append`, `union`) yet, deliberately. Folding means a branch
# contributes a value the runtime applies at the join rather than assigning into a
# shared slot -- the emission model, which is a change to what a state write *is*
# and not something a policy name can bolt on. Shipping `merge: "sum"` that
# quietly still last-write-wins would be the "declared but not enforced" shape
# this codebase already has five instances of, so it waits for the machinery.
#
# When it arrives it should be a closed set rather than a user function: a fold
# must be batching-invariant -- reducer(reducer(s, xs), ys) == reducer(s, xs + ys)
# -- or a resume that regroups writes produces a different total, silently.
# LangGraph's DeltaChannel makes that the author's contract; a fixed set lets the
# language guarantee it by construction.
STATE_MERGE_POLICIES = ("any", "once")
DEFAULT_STATE_MERGE = "any"
