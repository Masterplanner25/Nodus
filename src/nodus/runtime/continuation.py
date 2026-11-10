"""Write a suspended coroutine down as data, and rebuild it (#180, stage 3).

`docs/design/v5/08-durable-coroutines.md` §3.1 claims that a durable checkpoint
needs no new mechanism, only the existing suspend-time capture written down.
This module is that claim made executable, in-process and with no store:
`capture_continuation` turns a suspended coroutine into plain JSON-safe data,
and `restore_continuation` builds a new coroutine from that data against a VM
running the same program. The original can then be thrown away, and the new one
continues from where it stopped, with the effects before that point not run
again.

**Refuse rather than lie** (§4.1). Capture refuses anything stage 2's
`assess_coroutine` reports, raising `ContinuationRefused` with that report.
Restore refuses a program that is not the one captured: the compiled code's
fingerprint and every function's address must match, because a saved `ip` is
an index into one particular chunk (§3.3).

**What is not captured, on purpose.**

- *Why* it was suspended. The coroutine is restored suspended and unscheduled;
  the caller decides when it runs. A remaining sleep is dropped, which is §7's
  open question 3, and a blocked coroutine is refused by the stage-2 check.
- The module's globals. They are the target VM's own, rebuilt from source, which
  is §3.1's "reconstructable" entry. A local that aliases one is refused
  (`shared_with_module`), because that sharing could not be rebuilt.
- A frame running in another module's context. Its context is the importing
  module's to rebuild, and that is stage 4's problem; it is refused here.

**A continuation is executable.** Its `ip` and every `return_ip` are jump
targets in the program, so restore only data this host wrote, from storage it
controls, exactly as a bytecode cache or the workflow store is trusted. Restore
checks the program, the functions and the #394 step-entry guard, but it cannot
tell a tampered `ip` from a genuine one.

The format is versioned (`FORMAT`) and is not a stable contract yet.
"""

from __future__ import annotations

import base64
import hashlib

from nodus.runtime.durability import DurabilityReport, assess_coroutine

FORMAT = "nodus-continuation/1"


class ContinuationRefused(Exception):
    """The continuation cannot be captured or restored, and this says why.

    `report` is the stage-2 durability report when that is the reason, and
    None when the refusal is about the program or the coroutine's state.
    """

    def __init__(self, message: str, report: DurabilityReport | None = None):
        super().__init__(message)
        self.report = report


# --------------------------------------------------------------------------
# capture


def capture_continuation(coroutine) -> dict:
    """The suspended `coroutine`'s continuation as JSON-safe data."""
    from nodus.runtime.coroutine import DEFERRED_NONE

    if getattr(coroutine, "state", None) != "suspended":
        raise ContinuationRefused(
            f"only a suspended coroutine can be captured; this one is "
            f"{getattr(coroutine, 'state', None)!r}. A running coroutine's state "
            "lives in the VM's registers until it suspends."
        )
    report = assess_coroutine(coroutine)
    if not report.durable:
        raise ContinuationRefused(report.explain(), report)

    for index, frame in enumerate(coroutine.frames):
        if getattr(frame, "cross_module_ctx", None) is not None:
            raise ContinuationRefused(
                f"frame {index} ({frame.fn_name}) is running in another module's "
                "context, which a resume would have to rebuild from that module; "
                "not supported yet"
            )

    ctx = coroutine.module_ctx
    code, functions = _ctx_code(ctx), _ctx_functions(ctx)
    heap = _Heap()
    entry_fn = coroutine.closure.function

    frames = []
    for frame in coroutine.frames:
        fn = getattr(getattr(frame, "closure", None), "function", None)
        slots = frame.locals_name_to_slot
        frames.append({
            "fn_name": frame.fn_name,
            "function": _function_ref(fn, functions) if fn is not None else None,
            "return_ip": frame.return_ip,
            "call": [frame.call_path, frame.call_line, frame.call_col],
            "locals": {name: heap.encode(value) for name, value in frame.locals.items()},
            "locals_array": (None if frame.locals_array is None
                             else [heap.encode(v) for v in frame.locals_array]),
            # The common case is the function's own slot map; say so rather than
            # copy it, so the restore can hand back that same object.
            "slots": ("function" if fn is not None and slots is fn.local_slots
                      else (None if slots is None else dict(slots))),
        })

    def deferred(value):
        return {"pending": False} if value is DEFERRED_NONE else {
            "pending": True, "value": heap.encode(value)}

    return {
        "format": FORMAT,
        "program": _fingerprint(code),
        "module": coroutine.module,
        "entry": _function_ref(entry_fn, functions),
        "ip": coroutine.ip,
        "stack": [heap.encode(v) for v in coroutine.stack],
        "frames": frames,
        "handler_stack": [list(h) for h in coroutine.handler_stack],
        "deferred_return": deferred(coroutine.deferred_return),
        "deferred_return_depth": coroutine.deferred_return_depth,
        "deferred_error": deferred(coroutine.deferred_error),
        "deferred_error_depth": coroutine.deferred_error_depth,
        "heap": heap.entries,
    }


def _function_ref(fn, functions) -> dict:
    if functions.get(fn.name) is not fn:
        raise ContinuationRefused(
            f"function {fn.display_name!r} is not in its module's function table, "
            "so nothing could find it again"
        )
    return {"name": fn.name, "addr": fn.addr}


class _Heap:
    """Containers encoded once each, by identity, so sharing and cycles survive.

    A scalar is written inline. A container is written as `{"ref": n}` and its
    contents go in `entries[n]`. That is `copy()`'s memo (#814) turned into a
    format: two names for one list are still one list after a restore, and a
    list holding itself terminates.
    """

    def __init__(self):
        self.entries: list[dict] = []
        self._index: dict[int, int] = {}
        self._keep: list = []  # ids are only unique while the object is alive

    def encode(self, value):
        from nodus.vm.types import Record

        if value is None or isinstance(value, (bool, int, float, str)):
            return value
        if isinstance(value, bytes):
            return {"bytes": base64.b64encode(value).decode("ascii")}
        if not isinstance(value, (list, dict, Record)):
            # The stage-2 check has already refused every such value; reaching
            # here means the two disagree, which must not pass silently.
            raise ContinuationRefused(
                f"cannot write down a {type(value).__name__}; the durability "
                "check should have refused it")
        marker = id(value)
        if marker in self._index:
            return {"ref": self._index[marker]}
        slot = len(self.entries)
        self._index[marker] = slot
        self._keep.append(value)
        entry: dict = {}
        self.entries.append(entry)
        if isinstance(value, list):
            entry["list"] = [self.encode(item) for item in value]
        elif isinstance(value, dict):
            entry["map"] = [[self.encode(k), self.encode(v)] for k, v in value.items()]
        else:
            entry["record"] = value.kind
            entry["fields"] = {name: self.encode(v) for name, v in value.fields.items()}
        return {"ref": slot}


# --------------------------------------------------------------------------
# restore


def restore_continuation(vm, data: dict):
    """A new, suspended, unscheduled coroutine rebuilt from `data` against `vm`.

    `vm` must be running the program the data was captured from. The caller
    schedules the result (`vm.scheduler.spawn(co)`).
    """
    from nodus.runtime.coroutine import DEFERRED_NONE, Coroutine
    from nodus.vm.types import Closure, Frame

    if not isinstance(data, dict) or data.get("format") != FORMAT:
        raise ContinuationRefused(
            f"not a continuation in format {FORMAT!r}: {data.get('format') if isinstance(data, dict) else type(data).__name__!r}")

    ctx = vm._capture_module_ctx()
    code, functions = _ctx_code(ctx), _ctx_functions(ctx)
    if _fingerprint(code) != data["program"]:
        raise ContinuationRefused(
            "this VM is running a different program from the one the continuation "
            "was captured in, so its saved instruction pointer would land in "
            "unrelated code")

    def function(ref):
        fn = functions.get(ref["name"])
        if fn is None or fn.addr != ref["addr"]:
            raise ContinuationRefused(
                f"function {ref['name']!r} is missing or has moved in this program")
        return fn

    heap = _decode_heap(data["heap"])

    def decode(value):
        if isinstance(value, dict):
            if "ref" in value:
                return heap[value["ref"]]
            if "bytes" in value:
                return base64.b64decode(value["bytes"])
        return value

    _fill_heap(data["heap"], heap, decode)

    entry = Closure(function(data["entry"]), [])
    # #394: rebuilding a frame is a way into a function, so it is a door into a
    # workflow step body like the four the guard already covers. The resume
    # checks the entry closure again, but nothing re-checks a deeper frame, so
    # every frame's function is checked here, including a frame that carries no
    # closure (an ordinary named call), found by its internal name. The decision
    # stays in `guard_step_entry`; a continuation never carries the runner's
    # authorization, because capture refuses a step coroutine.
    vm.guard_step_entry(entry)
    frames = []
    for raw in data["frames"]:
        fn = function(raw["function"]) if raw["function"] is not None else None
        named = fn if fn is not None else functions.get(raw["fn_name"])
        if named is None:
            raise ContinuationRefused(
                f"a frame runs {raw['fn_name']!r}, which is not a function of this "
                "program, so nothing could check what it is")
        vm.guard_step_entry(entry if named is entry.function else Closure(named, []))
        # The entry frame runs the coroutine's own closure; keep it the same
        # object, as a fresh start does.
        closure = None if fn is None else (entry if fn is entry.function else Closure(fn, []))
        slots = raw["slots"]
        if slots == "function":
            slots = fn.local_slots if fn is not None else None
        path, line, col = raw["call"]
        frames.append(Frame(
            return_ip=raw["return_ip"],
            locals={name: decode(v) for name, v in raw["locals"].items()},
            fn_name=raw["fn_name"],
            call_line=line,
            call_col=col,
            call_path=path,
            closure=closure,
            locals_array=(None if raw["locals_array"] is None
                          else [decode(v) for v in raw["locals_array"]]),
            locals_name_to_slot=slots,
        ))

    def deferred(raw):
        return decode(raw["value"]) if raw["pending"] else DEFERRED_NONE

    coroutine = Coroutine(closure=entry, state="suspended")
    coroutine.ip = data["ip"]
    coroutine.stack = [decode(v) for v in data["stack"]]
    coroutine.frames = frames
    coroutine.handler_stack = [tuple(h) for h in data["handler_stack"]]
    coroutine.deferred_return = deferred(data["deferred_return"])
    coroutine.deferred_return_depth = data["deferred_return_depth"]
    coroutine.deferred_error = deferred(data["deferred_error"])
    coroutine.deferred_error_depth = data["deferred_error_depth"]
    coroutine.module_ctx = ctx
    coroutine.owner_vm = vm
    coroutine.module = data.get("module")
    return coroutine


def _decode_heap(entries: list[dict]) -> list:
    """Empty containers first, so a reference to any of them -- including a
    container's reference to itself -- resolves before anything is filled."""
    from nodus.vm.types import Record

    out: list = []
    for entry in entries:
        if "list" in entry:
            out.append([])
        elif "map" in entry:
            out.append({})
        else:
            out.append(Record({}, entry["record"]))
    return out


def _fill_heap(entries: list[dict], heap: list, decode) -> None:
    for entry, target in zip(entries, heap):
        if "list" in entry:
            target.extend(decode(v) for v in entry["list"])
        elif "map" in entry:
            for key, value in entry["map"]:
                target[decode(key)] = decode(value)
        else:
            for name, value in entry["fields"].items():
                target.fields[name] = decode(value)


# --------------------------------------------------------------------------
# program identity


def _ctx_code(ctx):
    # Layout stated once, beside `VM._capture_module_ctx`.
    return ctx[0]


def _ctx_functions(ctx) -> dict:
    from nodus.vm.vm import VM
    return VM._ctx_functions(ctx)


def _fingerprint(code) -> str:
    """The compiled program's identity. §3.3 measured that identical source
    compiles identically across processes; this is what makes a mismatch a
    refusal rather than a jump into unrelated code."""
    return hashlib.sha256(repr(code).encode("utf-8")).hexdigest()
