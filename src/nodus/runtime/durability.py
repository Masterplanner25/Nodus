"""Could this coroutine's continuation be written down? (#180, stage 2)

`docs/design/v5/08-durable-coroutines.md` decides that a `checkpoint` inside a
bare coroutine is a *position*: a resume continues from it, and the effects
before it do not run again. §4.1 adds the rule that makes that safe to promise:
**it must refuse rather than lie**, naming what blocks it. This module is that
refusal's reasoning, with nothing persisted and no store involved.

`assess_coroutine(co)` reads a live coroutine and returns every obstacle it
finds, not just the first, each with *where* it is. It never raises on an
obstacle and never changes the coroutine. Whether to refuse is the caller's
decision; what to say when refusing is this module's.

**What it is not.** It is not a serialiser, and `durable` here means *nothing
this check knows of stands in the way*, not *a serialiser has been shown to
work*. Stage 3 (in-process capture, discard, rebuild) is what can falsify the
second claim. Two things are deliberately out of scope until the design settles
them (§7): a coroutine that is *sleeping*, whose wake time lives in the
scheduler rather than on the coroutine, and the module context, which §3.1
records as reconstructable by re-loading the module.

**Why not `is_json_safe`.** That answers a narrower question, transport over
JSON. It refuses a record, which is data with an obvious written form, and it
recurses without bound on a cycle, which `copy()` (#814) supports on purpose.
The line drawn here is `copy()`'s: data is copyable, and a function, method,
channel, coroutine, task or host object is not.
"""

from __future__ import annotations

from dataclasses import dataclass

# Every reason a coroutine can fail the check, named once. Order is the order
# a reader should meet them: whether resuming means anything at all, then the
# entry point, then the captured environment, then values.
OBSTACLE_KINDS: tuple[str, ...] = (
    # Settled: there is no continuation left to resume.
    "not_resumable",
    # A workflow step's coroutine. Its durability is the workflow's: it is
    # re-entered by name from the top (#486), and persisting its frame would
    # give it the opposite semantics to every other step.
    "workflow_step",
    # Parked on a channel, a task or async I/O. The position is capturable, but
    # what it waits for does not survive the process (§7, question 2).
    "blocked",
    # The entry closure cannot be found again by name: anonymous, nested inside
    # another function, or from another module. §5 rejects inferring one.
    "unnamed_entry",
    # A closure in the continuation captures a variable, or a frame holds a
    # variable some closure captured. Cell values may be data, but Cell
    # *identity* cannot be rebuilt: two closures sharing one variable (#671)
    # would come back holding two (§3.4, obstacle 2).
    "captured_cell",
    # A value that cannot be written down: a function, channel, coroutine,
    # task, method, host object, or a `for` loop's iterator (§3.4, obstacle 3).
    "live_value",
    # A container the continuation holds that module-level state also holds.
    # A resume rebuilds module state from source, so the two would come back as
    # separate containers and a write through one would stop showing in the
    # other. The same silent split as a captured cell, through a different door.
    "shared_with_module",
)

_OBSTACLE_KIND_SET = frozenset(OBSTACLE_KINDS)

# The only settled state the runtime assigns. A failed or cancelled coroutine
# is also "finished", with `failure` set, so naming more here would read as
# coverage of states that never occur.
_SETTLED_STATES = frozenset({"finished"})


@dataclass(frozen=True)
class Obstacle:
    kind: str
    where: str
    detail: str

    def __post_init__(self) -> None:
        if self.kind not in _OBSTACLE_KIND_SET:
            raise ValueError(f"unknown durability obstacle kind: {self.kind!r}")

    def __str__(self) -> str:
        return f"{self.where}: {self.detail}"


@dataclass(frozen=True)
class DurabilityReport:
    obstacles: tuple[Obstacle, ...]

    @property
    def durable(self) -> bool:
        return not self.obstacles

    def kinds(self) -> set[str]:
        return {obstacle.kind for obstacle in self.obstacles}

    def explain(self) -> str:
        if self.durable:
            return "durable: nothing found that would stop this continuation being written down"
        lines = [f"not durable ({len(self.obstacles)} obstacle"
                 f"{'' if len(self.obstacles) == 1 else 's'}):"]
        lines.extend(f"  - [{o.kind}] {o}" for o in self.obstacles)
        return "\n".join(lines)


def assess_coroutine(coroutine) -> DurabilityReport:
    """Every reason `coroutine`'s continuation could not be made durable.

    Reads the state `VM.save_current_coroutine_state` captures (§3.1). For a
    coroutine that is running, that is the live state: the VM's stack and frame
    list *are* the coroutine's own lists while it runs, which
    `tests/test_durable_coroutine_premises.py` pins.
    """
    found: list[Obstacle] = []
    entry = getattr(coroutine, "closure", None)
    entry_fn = getattr(entry, "function", None)
    entry_label = _fn_label(entry_fn)

    state = getattr(coroutine, "state", None)
    if state in _SETTLED_STATES:
        found.append(Obstacle(
            "not_resumable", "coroutine",
            f"it is {state}, so there is no continuation to resume",
        ))

    if getattr(coroutine, "step_authorized", False) or getattr(entry_fn, "step_owner", None):
        owner = getattr(entry_fn, "step_owner", None) or "a workflow step"
        found.append(Obstacle(
            "workflow_step", "coroutine",
            f"it runs the body of {owner}. A step resumes by re-entering from the "
            "top (#486); use `checkpoint` there, not a captured position",
        ))

    reason = getattr(coroutine, "blocked_reason", None)
    if reason:
        found.append(Obstacle(
            "blocked", "coroutine",
            f"it is parked ({reason}); what it waits on does not survive the process",
        ))

    # A step body is always anonymous, so saying so again adds nothing.
    if entry_fn is not None and "workflow_step" not in {o.kind for o in found}:
        problem = _entry_identity_problem(entry_fn)
        if problem:
            found.append(Obstacle("unnamed_entry", f"entry {entry_label}", problem))

    module_containers = _module_containers(coroutine)
    walker = _ValueWalker(found, module_containers)

    seen_closures: set[int] = set()
    for closure, where in _closures_in_continuation(coroutine, entry, entry_label):
        if id(closure) in seen_closures:
            continue
        seen_closures.add(id(closure))
        upvalues = getattr(closure, "upvalues", None) or []
        if upvalues:
            names = _upvalue_names(closure)
            found.append(Obstacle(
                "captured_cell", where,
                f"it captures {_name_list(names, len(upvalues))} from an enclosing "
                "function; a resume could rebuild the values but not the sharing",
            ))

    for index, frame in enumerate(getattr(coroutine, "frames", None) or []):
        frame_where = f"frame {index} ({_display(getattr(frame, 'fn_name', None))})"
        for name, value in _frame_locals(frame):
            if _is_cell(value):
                found.append(Obstacle(
                    "captured_cell", f"{frame_where}, local `{name}`",
                    "a closure captured this variable; a resume could rebuild its "
                    "value but not the closure's view of it",
                ))
                continue
            walker.check(value, f"{frame_where}, local `{name}`", root=name)

    for depth, value in enumerate(getattr(coroutine, "stack", None) or []):
        walker.check(value, f"operand stack slot {depth}", root=None)

    for attr, label in (("deferred_return", "a return deferred by `finally`"),
                        ("deferred_error", "an error deferred by `finally`")):
        value = getattr(coroutine, attr, None)
        if value is not None and not _is_deferred_none(value):
            walker.check(value, label, root=None)

    return DurabilityReport(tuple(found))


# --------------------------------------------------------------------------
# entry identity


def _entry_identity_problem(fn) -> str | None:
    """Why the entry cannot be found again by name, or None if it can.

    A named top-level function *of an imported module* passes: the module loader
    gives it its plain name, and the coroutine records the module it was spawned
    in (`Coroutine.module`), so (module, name) identifies it. The `__modN__`
    prefix is the bundling loader's (`tooling/loader.py`), and N is the module's
    import order, an index exactly as `__anon_N` is.
    """
    name = getattr(fn, "name", "") or ""
    shown = getattr(fn, "display_name", name) or name
    if shown.startswith("__anon"):
        return ("it is an anonymous function, so nothing in a fresh process can "
                "name it. Its compiler-assigned index renames when an earlier "
                "closure is added (durable-coroutines design, section 5); spawn "
                "a named top-level function instead")
    if name.startswith("__mod"):
        return (f"`{shown}` carries a bundled-module prefix numbered by import "
                "order, which renames when an import is added")
    if "__fn" in name:
        return (f"`{shown}` is defined inside another function, so it is not "
                "reachable by name from module level")
    return None


# --------------------------------------------------------------------------
# closures, frames, cells


def _closures_in_continuation(coroutine, entry, entry_label):
    if entry is not None:
        yield entry, f"entry {entry_label}"
    for index, frame in enumerate(getattr(coroutine, "frames", None) or []):
        closure = getattr(frame, "closure", None)
        if closure is not None:
            yield closure, f"frame {index} ({_fn_label(getattr(closure, 'function', None))})"


def _upvalue_names(closure) -> list[str]:
    fn = getattr(closure, "function", None)
    return [getattr(up, "name", "?") for up in (getattr(fn, "upvalues", None) or [])]


def _frame_locals(frame):
    """A frame's locals: the dict, then the slot array by name (slot wins)."""
    merged = dict(getattr(frame, "locals", None) or {})
    array = getattr(frame, "locals_array", None)
    slots = getattr(frame, "locals_name_to_slot", None)
    if array is not None and slots:
        for name, index in slots.items():
            if 0 <= index < len(array):
                merged[name] = array[index]
    return sorted(merged.items())


def _is_cell(value) -> bool:
    from nodus.vm.types import Cell
    return isinstance(value, Cell)


def _is_deferred_none(value) -> bool:
    from nodus.runtime.coroutine import DEFERRED_NONE
    return value is DEFERRED_NONE


# --------------------------------------------------------------------------
# values


def _module_containers(coroutine) -> dict[int, str]:
    """id -> global name, for every container reachable from module state.

    The coroutine's own module context, plus the caller context saved on any
    cross-module frame, because each is a module whose state a resume would
    rebuild from source.
    """
    contexts = [getattr(coroutine, "module_ctx", None)]
    for frame in getattr(coroutine, "frames", None) or []:
        contexts.append(getattr(frame, "cross_module_ctx", None))
    out: dict[int, str] = {}
    seen_globals: set[int] = set()
    for ctx in contexts:
        globals_ = _ctx_globals(ctx)
        if globals_ is None or id(globals_) in seen_globals:
            continue
        seen_globals.add(id(globals_))
        for name, value in globals_.items():
            if isinstance(name, str) and name.startswith("__"):
                continue
            _collect_containers(value, out, name)
    return out


def _ctx_globals(ctx):
    # The tuple's layout is stated once, beside `VM._capture_module_ctx`.
    if not isinstance(ctx, tuple) or len(ctx) < 4:
        return None
    globals_ = ctx[3]
    return globals_ if isinstance(globals_, dict) else None


def _collect_containers(value, out: dict[int, str], name: str) -> None:
    from nodus.vm.types import Record
    stack = [value]
    while stack:
        node = stack.pop()
        if not isinstance(node, (list, dict, Record)) or id(node) in out:
            continue
        out[id(node)] = name
        if isinstance(node, list):
            stack.extend(node)
        elif isinstance(node, dict):
            stack.extend(node.values())
        else:
            stack.extend(node.fields.values())


class _ValueWalker:
    """Walks values held by the continuation, reporting each obstacle once.

    Shared structure inside the continuation is fine: a serialiser can keep it
    with a memo, as `copy()` does. So each container is visited once, which also
    makes a cycle terminate.
    """

    def __init__(self, found: list[Obstacle], module_containers: dict[int, str]):
        self._found = found
        self._module = module_containers
        self._visited: set[int] = set()
        self._reported_shared: set[int] = set()

    def check(self, value, where: str, *, root: str | None) -> None:
        from nodus.vm.types import Record

        stack = [(value, root)]
        while stack:
            node, path = stack.pop()
            if node is None or isinstance(node, (bool, int, float, str, bytes)):
                continue
            if not isinstance(node, (list, dict, Record)):
                self._found.append(Obstacle(
                    "live_value", _at(where, path, root), _live_description(node)))
                continue
            if id(node) in self._module:
                # Reported once per container, and not descended: everything
                # inside it is module state too, so its contents add only noise.
                if id(node) not in self._reported_shared:
                    self._reported_shared.add(id(node))
                    self._found.append(Obstacle(
                        "shared_with_module", _at(where, path, root),
                        f"this {_container_word(node)} is also held by module-level "
                        f"`{self._module[id(node)]}`; a resume rebuilds module state "
                        "from source, so the two would come back as separate copies",
                    ))
                continue
            if id(node) in self._visited:
                continue
            self._visited.add(id(node))
            if isinstance(node, list):
                for index, item in enumerate(node):
                    stack.append((item, f"{path or ''}[{index}]"))
            elif isinstance(node, dict):
                for key, item in node.items():
                    stack.append((item, f'{path or ""}["{key}"]'))
            else:
                for field_name, item in node.fields.items():
                    stack.append((item, f"{path}.{field_name}" if path else field_name))


def _at(where: str, path: str | None, root: str | None) -> str:
    if path is None or path == root:
        return where
    return f"{where}, at `{path}`"


def _container_word(node) -> str:
    if isinstance(node, list):
        return "list"
    if isinstance(node, dict):
        return "map"
    return "record"


def _live_description(node) -> str:
    from nodus.orchestration.task_graph import TaskGraph, TaskNode
    from nodus.runtime.channel import Channel
    from nodus.runtime.coroutine import Coroutine
    from nodus.vm.types import BuiltinMethod, Closure
    from nodus.vm.vm import Iterator

    if isinstance(node, Iterator):
        return ("a `for` loop's iterator, which keeps its position in host state; "
                "the operand stack is not empty inside a `for` body")
    if isinstance(node, Closure):
        return f"a function ({_fn_label(getattr(node, 'function', None))}), which has no written form"
    if isinstance(node, Channel):
        return "a channel, whose other end does not survive the process"
    if isinstance(node, Coroutine):
        return "a coroutine, which is itself live state"
    if isinstance(node, (TaskNode, TaskGraph)):
        return "a task, which is live scheduler state"
    if isinstance(node, BuiltinMethod):
        return "a method of a host-provided record"
    return f"a host object ({type(node).__name__}), which has no written form"


# --------------------------------------------------------------------------
# names


def _display(name) -> str:
    if not name:
        return "?"
    from nodus.compiler.compiler import display_name
    return f"`{display_name(name)}`"


def _fn_label(fn) -> str:
    if fn is None:
        return "?"
    return f"`{getattr(fn, 'display_name', None) or getattr(fn, 'name', '?')}`"


def _name_list(names: list[str], count: int) -> str:
    if not names:
        return f"{count} variable{'s' if count != 1 else ''}"
    return ", ".join(f"`{n}`" for n in names)
