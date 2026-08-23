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

    __slots__ = (
        "_writes",
        "_writer",
        "_steps",
        "_policies",
        "_written_values",
        "_reads_before_write",
    )

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
        # Per-cell `with { merge: ... }`, injected by the runner. Needed here
        # because the fold happens at `end_step`, where the cell's policy is what
        # decides whether there is anything to fold.
        self._policies: dict = {}
        # key -> {task_id: last value that task wrote}. Retained past the step so
        # the conflict check can distinguish two branches that *disagreed* from
        # two that happened to write the same thing.
        self._written_values: dict[str, dict[str, object]] = {}
        # key -> tasks that read it before writing it. A read-modify-write by two
        # concurrent tasks is a lost update whatever the values turn out to be.
        self._reads_before_write: dict[str, set] = {}

    def track_writes_with(self, writer) -> None:
        self._writer = writer

    def __setitem__(self, key, value):
        writer = self._writer
        if writer is not None:
            task_id = writer()
            if task_id is not None:
                self._writes.setdefault(str(key), []).append(task_id)
                # The last value each task wrote, kept past the step so the
                # end-of-run conflict check can ask whether the concurrent
                # writers actually *disagreed*. Bounded by keys x tasks.
                self._written_values.setdefault(str(key), {})[task_id] = value
                step = self._steps.get(task_id)
                if step is not None and not step.closed:
                    step.record(key, value)
        super().__setitem__(key, value)

    def __getitem__(self, key):
        """Read a cell, noting when a task reads one it has not yet written.

        That pairing -- read then write, same task, same cell -- is what a lost
        update *is*, and it is the only sound signal for one. Comparing the
        written values is not: two branches doing `counter = seen + 1i` from the
        same base both write `1`, so the values agree precisely when an update
        was lost. This method exists because that was tried first and the issue's
        own reproduction falsified it.

        Only reads that precede the task's own write count, so `x = 5i` followed
        by reading `x` is not mistaken for a read-modify-write.
        """
        writer = self._writer
        if writer is not None:
            name = str(key)
            task_id = writer()
            if task_id is not None and task_id not in self._written_values.get(name, {}):
                self._reads_before_write.setdefault(name, set()).add(task_id)
        return super().__getitem__(key)

    def written_values(self) -> dict[str, dict[str, object]]:
        return {key: dict(by_task) for key, by_task in self._written_values.items()}

    def reads_before_write(self) -> dict[str, set]:
        return {key: set(tasks) for key, tasks in self._reads_before_write.items()}

    def begin_step(self, task_id: str) -> StepWrites:
        """Open a write record for a step that is about to run.

        Re-entrant: a step resuming after a `workflow_wait` gets a fresh record,
        because the previous one was closed when it suspended.
        """
        step = StepWrites(task_id)
        self._steps[task_id] = step
        return step

    def set_policies(self, policies: dict | None) -> None:
        self._policies = policies if isinstance(policies, dict) else {}

    def merge_policy(self, key) -> str:
        entry = self._policies.get(str(key))
        if isinstance(entry, dict):
            merge = entry.get("merge")
            if isinstance(merge, str):
                return merge
        return DEFAULT_STATE_MERGE

    def pending_fold(self, task_id: str) -> dict:
        """This step's folded cells as they would land right now.

        A checkpoint has to see them: `counter += 1i; checkpoint "l"` must record
        the contributed value, or a resume from that label re-contributes and the
        total is wrong. The fold is computed into a copy -- other branches still
        must not see it before the join.
        """
        step = self._steps.get(task_id)
        if step is None or not step.has_contributions():
            return {}
        out = {}
        for key, values in step.contributions().items():
            out[key] = fold_contributions(self.merge_policy(key), self.get(key), values)
        return out

    def end_step(self, task_id: str) -> list[str]:
        """Close a step's record, folding its contributions into the cells.

        This is the join for a folded cell. The contribution never read the cell,
        so two concurrent branches each contributing `1` add to `2` however their
        reads interleaved -- which is the lost update in #485, closed.
        """
        step = self._steps.pop(task_id, None)
        if step is None:
            return []
        for key, values in step.contributions().items():
            folded = fold_contributions(self.merge_policy(key), self.get(key), values)
            self._writes.setdefault(str(key), []).append(task_id)
            dict.__setitem__(self, key, folded)
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

    __slots__ = ("task_id", "_order", "_values", "_contributions", "closed")

    def __init__(self, task_id: str | None = None):
        self.task_id = task_id
        # Ordered and deduped: a key written twice by one step is one
        # contribution from it, and order is what decides `any`.
        self._order: list[str] = []
        self._values: dict[str, object] = {}
        # key -> the values this step contributed to a folded cell, in order. A
        # list rather than one value: a step may contribute more than once, and
        # each contribution is real -- `counter += 1i` twice is +2.
        self._contributions: dict[str, list] = {}
        self.closed = False

    def record(self, key, value) -> None:
        name = str(key)
        if name not in self._values:
            self._order.append(name)
        self._values[name] = value

    def contribute(self, key, value) -> None:
        """Record a contribution to a folded cell without touching it.

        The write does *not* land here, which is the whole point: it is the
        read-modify-write on the shared cell that loses updates, and a
        contribution never reads the cell at all.
        """
        self._contributions.setdefault(str(key), []).append(value)

    def contributions(self) -> dict[str, list]:
        return {key: list(values) for key, values in self._contributions.items()}

    def has_contributions(self) -> bool:
        return bool(self._contributions)

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

    values = state.written_values()
    reads = state.reads_before_write()
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
            read_modify_write = sorted(set(pair) & reads.get(key, set()))
            conflicts.append(
                {
                    "key": key,
                    "tasks": pair,
                    "winner": task_ids[-1],
                    "read_modify_write": read_modify_write,
                    "lost_update": bool(read_modify_write)
                    or not writers_agree(values.get(key, {}), pair),
                }
            )
    return conflicts


def writers_agree(by_task: dict, tasks: list[str]) -> bool:
    """Did the concurrent writers write the same value?

    Only half the question, and the weaker half. Two branches setting a cell to
    the same constant have lost nothing whichever won; two setting it to
    different values have lost one.

    But agreement does **not** mean nothing was lost. Two branches doing
    `counter = seen + 1i` from the same base both write `1` -- the values agree
    precisely *because* an update was lost. That is why the caller pairs this
    with the read-before-write signal, which catches exactly that case.

    Unknown is treated as disagreement: a value whose `==` raises, or a writer
    with nothing recorded, must not be silently called agreement, because that is
    the direction that hides a defect.
    """
    if len(tasks) < 2:
        return True
    if any(task not in by_task for task in tasks):
        return False
    first = by_task[tasks[0]]
    for task in tasks[1:]:
        try:
            if not bool(first == by_task[task]):
                return False
        except Exception:
            return False
    return True


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
#   sum    concurrent writes add. Contributions are numbers.
#   append concurrent writes concatenate. Contributions are lists.
#
# Both fold with `+`, and the two names exist to say which -- `sum` on a list
# would silently concatenate and `append` on a number would silently add, so the
# name is what lets a wrong contribution be rejected instead of quietly doing
# something.
#
# `union` is named in #485 and is deliberately absent. It needs an
# element-equality story Nodus does not have: dedup over lists of maps has no
# defined key, and merging maps is not commutative when two branches set the same
# field. Shipping it with unclear semantics would be the same "declared but not
# enforced" shape the fold set was withheld for in the first place.
FOLD_STATE_MERGE_POLICIES = ("sum", "append")
STATE_MERGE_POLICIES = ("any", "once", *FOLD_STATE_MERGE_POLICIES)
DEFAULT_STATE_MERGE = "any"

#: What a contribution to each folded policy must be, for the error message.
FOLD_CONTRIBUTION_KINDS = {"sum": "a number", "append": "a list"}


def is_fold_policy(merge: object) -> bool:
    return merge in FOLD_STATE_MERGE_POLICIES


def check_contribution(merge: str, value) -> str | None:
    """`None` if `value` is a valid contribution to `merge`, else why not."""
    if merge == "sum":
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return "a number"
        return None
    if merge == "append":
        if not isinstance(value, list):
            return "a list"
        return None
    return None


def fold_contributions(merge: str, base, values: list):
    """Apply a step's contributions to the value already in the cell.

    Both policies fold with `+`, applied in contribution order. That is
    batching-invariant for numbers and for list concatenation --
    `fold(fold(s, xs), ys) == fold(s, xs + ys)` -- which is what makes a resume
    that regroups writes produce the same total. It is why the set is closed
    rather than a user-supplied function: the language guarantees the property by
    construction instead of making it the author's contract.
    """
    result = base
    for value in values:
        if result is None:
            result = value
            continue
        result = result + value
    return result
