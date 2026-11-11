"""Durable coroutines: `durable_spawn` and the checkpoint that persists (#180, stage 4b).

Decisions are in `docs/design/v5/08a-durable-coroutines-stage4.md`; this module
is D1, D2, D4 and D5 of it. In one paragraph: `durable_spawn(key, fn, args)`
starts `fn(args...)` as a coroutine backed by a run record in the workflow
store. Each `checkpoint "label"` it reaches suspends it; the scheduler captures
the continuation (stage 3) and writes it to the record **before** the coroutine
runs on. Calling `durable_spawn` again with the same key -- typically because
the program was restarted after a crash -- finds the record and, if the run is
unfinished and nobody else holds it, resumes it from its last checkpoint.

The contract is **at-least-once between checkpoints**: a crash re-runs the
work after the last checkpoint, and never the work before it.

**Who may act on a run** is decided by the store's claim, which must be
exclusive across processes (`require_exclusive_claims`, stage 4a). The claim is
renewed atomically before every write and periodically while the coroutine
runs. A holder whose renewal fails has lost the run to another process; its
copy stops at once and never writes to the record again.

What is not here yet, and lands before this ships (stage 4c, same release):
clock continuity for deadlines held in locals (D6), and resuming runs from a
long-lived host (`rehydrate_runs`).
"""

from __future__ import annotations

import hashlib
import os
import sys
import time
from dataclasses import dataclass

from nodus.orchestration.workflow_state import EXECUTION_KIND_COROUTINE

_CALLED_AS = "durable_spawn(key, fn, args)"

#: Raised when `checkpoint "label"` runs in a function that is neither a
#: workflow step nor a durable coroutine. The parser accepts it inside any
#: function, because whether a function runs durably is a run-time fact.
CHECKPOINT_NOT_DURABLE = (
    "`checkpoint` ran outside a workflow step and outside a durable coroutine, so "
    "there is nothing to record it in. Start the function with "
    "`durable_spawn(key, fn, args)` to make its checkpoints persist "
    "(docs/design/v5/08a-durable-coroutines-stage4.md), or run the work as a "
    "step of a `workflow`."
)


@dataclass
class DurableBinding:
    """What ties a live coroutine to its run record."""

    run_id: str
    key: str
    store: object
    token: str
    claim_ttl_ms: float
    renewed_at: float  # time.monotonic() of the last successful renewal
    lost: bool = False


def run_id_for(key: str) -> str:
    """The run id a key names. Derived, so finding a run by key is one lookup,
    and safe as a state id whatever the key contains."""
    return "co_" + hashlib.sha256(key.encode("utf-8")).hexdigest()[:32]


def _owner(vm) -> str:
    return f"nodus:{os.getpid()}:{id(vm):x}"


def durable_spawn(vm, key, fn, args) -> str:
    """The `durable_spawn` builtin. Returns the run id.

    Starts the run, adopts an unfinished one, or does nothing for a finished
    one or one another process holds; the run id is returned in every case.
    """
    from nodus.runtime.continuation import ContinuationRefused, encode_values
    from nodus.runtime.durability import assess_values, entry_problem

    if not isinstance(key, str) or not key.strip():
        vm.runtime_error("type", f"{_CALLED_AS}: key must be a non-empty string")
    if getattr(vm, "_suppress_flow_execution", False):
        # The module is being re-run only to re-bind its definitions, for a
        # rebuild or a sweep that is about to resume this very run (#322's
        # flag). Starting or adopting it here would race that resume.
        return run_id_for(key)
    closure = vm.ensure_function(fn, _CALLED_AS)
    if not isinstance(args, list):
        vm.runtime_error("type", f"{_CALLED_AS}: args must be a list")
    entry_fn = closure.function
    shown = getattr(entry_fn, "display_name", entry_fn.name)
    if len(args) != len(entry_fn.params):
        vm.runtime_error(
            "call",
            f"{_CALLED_AS}: `{shown}` takes {len(entry_fn.params)} argument(s), got {len(args)}")
    problem = entry_problem(closure)
    if problem is None and vm.functions.get(entry_fn.name) is not entry_fn:
        problem = (f"`{shown}` is not a top-level function of the module calling "
                   "durable_spawn, so a resume could not find it by name")
    if problem:
        vm.runtime_error("runtime", f"{_CALLED_AS} cannot make this durable: {problem}")
    report = assess_values({name: value for name, value in zip(entry_fn.params, args)})
    if not report.durable:
        vm.runtime_error("runtime", f"{_CALLED_AS}: the arguments cannot be written down.\n"
                                    + report.explain())

    store = vm.resolve_workflow_runner().store
    try:
        from nodus_lang_workflow.store import StoreUnsuitableError, require_exclusive_claims
        require_exclusive_claims(store, feature="durable_spawn")
    except StoreUnsuitableError as exc:
        vm.runtime_error("runtime", str(exc))

    from nodus_lang_workflow.models import TERMINAL_RUN_STATUSES

    run_id = run_id_for(key)
    encoded_args = encode_values(list(args))
    record = store.get_run(run_id)
    if record is None:
        metadata = {
            "durable_key": key,
            "entry": entry_fn.name,
            "args": encoded_args,
            "program_source": getattr(vm, "source_code", None),
            "source_path": getattr(vm, "source_path", None),
        }
        try:
            record = store.create_run(run_id=run_id, graph_id=run_id,
                                      workflow_name=shown,
                                      execution_kind=EXECUTION_KIND_COROUTINE,
                                      metadata=metadata)
        except Exception:
            # Another process created it between our read and our insert.
            record = store.get_run(run_id)
            if record is None:
                raise

    if record.metadata.get("durable_key") != key or record.execution_kind != EXECUTION_KIND_COROUTINE:
        vm.runtime_error("runtime", f"{_CALLED_AS}: run {run_id} exists and is not "
                                    f"the durable coroutine for key {key!r}")
    if record.metadata.get("entry") != entry_fn.name or record.metadata.get("args") != encoded_args:
        vm.runtime_error(
            "runtime",
            f"{_CALLED_AS}: a run with key {key!r} was started as "
            f"`{record.workflow_name}` with different arguments. A key names one "
            "run; use a new key for different work.")
    if record.status in TERMINAL_RUN_STATUSES:
        return run_id

    claim = store.claim_run(run_id, owner=_owner(vm))
    if claim is None:
        # Held by another process. Not ours to touch -- but say so, because a
        # program restarted straight after a crash lands here until the dead
        # process's claim expires, and silence would look like nothing to resume.
        held = store.get_run(run_id)
        holder = held.claim if held is not None else None
        remaining = ""
        if holder is not None and holder.expires_at is not None:
            from nodus.runtime.runtime_stats import store_time_ms
            seconds = max(0.0, (holder.expires_at - store_time_ms()) / 1000.0)
            remaining = f"; its claim expires in {seconds:.1f}s if that process has gone"
        print(
            f"durable_spawn: run {key!r} is held by another process "
            f"({holder.owner if holder is not None else 'unknown'}), so it is not "
            f"started here{remaining}",
            file=sys.stderr,
        )
        return run_id

    try:
        _launch(vm, store, record, claim, closure)
    except ContinuationRefused as exc:
        vm.runtime_error(
            "runtime",
            f"{_CALLED_AS}: run {key!r} cannot be resumed: {exc}. Its last "
            "checkpoint belongs to a different version of this program.")
    return run_id


def _launch(vm, store, record, claim, closure=None):
    """Start or restore the run `record` on `vm`, under `claim`, and spawn it.

    The one place a durable coroutine is put on a scheduler, shared by
    `durable_spawn` (a program re-run with its key) and `resume_durable_run` (a
    sweep). Raises `ContinuationRefused`, having released the claim, if the
    stored continuation does not fit this VM's program.
    """
    from nodus.runtime.continuation import (
        ContinuationRefused,
        decode_values,
        restore_continuation,
    )
    from nodus.runtime.coroutine import Coroutine
    from nodus.vm.types import Closure
    from nodus_lang_workflow.models import RUN_STATUS_RUNNING

    run_id = record.run_id
    continuation = record.metadata.get("continuation")
    try:
        if continuation is None:
            # Never checkpointed: start from the top, with the stored arguments.
            if closure is None:
                entry = vm.functions.get(record.metadata.get("entry"))
                if entry is None:
                    raise ContinuationRefused(
                        f"this program has no function {record.metadata.get('entry')!r}")
                closure = Closure(entry, [])
            coroutine = Coroutine(closure)
            coroutine.initial_args = decode_values(record.metadata["args"])
        else:
            coroutine = restore_continuation(vm, continuation)
            _continue_clock(vm, coroutine, record.metadata.get("clock"))
    except ContinuationRefused:
        store.release_claim(run_id, claim.token)
        raise

    record = store.get_run(run_id)
    record.status = RUN_STATUS_RUNNING
    record.claim = claim
    if continuation is not None:
        record.resume_count = (record.resume_count or 0) + 1
    store.save_run(record)

    coroutine.durable = DurableBinding(
        run_id=run_id, key=record.metadata.get("durable_key"), store=store,
        token=claim.token,
        claim_ttl_ms=float(getattr(store, "claim_ttl_ms", 30_000.0)),
        renewed_at=time.monotonic(),
    )
    vm.builtins["spawn"].fn(coroutine)
    # A durable coroutine is bounded by its checkpoints, not by a per-task
    # timeout: a timeout would settle it without a result or an error to record.
    coroutine.task_timeout_ms = None
    return coroutine


def _continue_clock(vm, coroutine, clock) -> None:
    """Make the restored coroutine's clock carry on from its checkpoint (D6).

    At the checkpoint its guest clock read `guest_ms` at wall time `wall_ms`.
    Now its guest clock should read `guest_ms` plus the wall time since, which
    is the best estimate of elapsed time across a restart. Clamped at zero, so
    a host clock that went backwards cannot make the coroutine's time run
    backwards. Before 4c the new process's clock simply started near zero, and
    a deadline held in a local meant something else.
    """
    if not isinstance(clock, dict):
        return
    guest_ms, wall_ms = clock.get("guest_ms"), clock.get("wall_ms")
    if not isinstance(guest_ms, (int, float)) or not isinstance(wall_ms, (int, float)):
        return
    elapsed = max(0.0, time.time() * 1000.0 - float(wall_ms))
    from nodus.vm.vm_chain import root_vm
    scheduler_now = root_vm(vm).scheduler.time_source.now_ms()
    coroutine.clock_offset_ms = float(guest_ms) + elapsed - scheduler_now


def resume_durable_run(vm, store, record) -> dict:
    """Resume one durable coroutine run on `vm` and drive it until it settles.

    Called by `WorkflowFrameworkRunner.sweep` for an unfinished run of kind
    `coroutine`, so a long-lived host (or `nodus workflow sweep`) can carry on a
    run whose program is not going to be started again. The same claim decides
    it as `durable_spawn` does, so a sweep and a restarted program cannot both
    resume one run. The program is rebuilt from the source stored with the run,
    not from whatever is on disk now.

    It runs **here**, as a released schedule or a due retry does in a sweep: the
    sweep is the explicit operator act that #176 requires before stored code
    runs.
    """
    from nodus.orchestration.task_graph import WorkflowRebuildError
    from nodus.runtime.continuation import ContinuationRefused
    from nodus_lang_workflow.models import RUN_STATUS_FAILED

    run_id = record.run_id
    info = {"run_id": run_id, "key": record.metadata.get("durable_key"),
            "workflow_name": record.workflow_name}
    claim = store.claim_run(run_id, owner=_owner(vm))
    if claim is None:
        return {**info, "ok": True, "status": "held_elsewhere"}
    source = record.metadata.get("program_source")
    if not isinstance(source, str):
        store.release_claim(run_id, claim.token)
        return {**info, "ok": False,
                "error": "the run stored no program source, so it cannot be rebuilt here"}
    try:
        vm.reexecute_source_for_resume(source, record.metadata.get("source_path"),
                                       what=f"durable coroutine {info['key']!r}")
        _launch(vm, store, store.get_run(run_id), claim)
    except WorkflowRebuildError as err:
        store.release_claim(run_id, claim.token)
        return {**info, "ok": False, "error": err.describe()}
    except ContinuationRefused as err:
        return {**info, "ok": False, "error": str(err)}
    vm.scheduler.run_loop()
    final = store.get_run(run_id)
    failed = final is not None and final.status == RUN_STATUS_FAILED
    out = {**info, "ok": not failed, "status": final.status if final else None}
    if failed:
        out["error"] = final.last_error
    return out


# --------------------------------------------------------------------------
# scheduler hooks


def keep_claim(scheduler, coroutine) -> bool:
    """Before each resume: renew the claim if a third of its life has passed.
    False means it was lost, and the coroutine has been stopped."""
    binding = getattr(coroutine, "durable", None)
    if binding is None or binding.lost:
        return binding is None
    if (time.monotonic() - binding.renewed_at) * 1000.0 < binding.claim_ttl_ms / 3.0:
        return True
    return _renew(scheduler, coroutine, binding)


def _renew(scheduler, coroutine, binding) -> bool:
    claim = binding.store.renew_claim(binding.run_id, binding.token)
    if claim is None:
        _lose(scheduler, coroutine, binding)
        return False
    binding.renewed_at = time.monotonic()
    return True


def _lose(scheduler, coroutine, binding) -> None:
    binding.lost = True
    coroutine.state = "finished"
    print(
        f"durable coroutine {binding.key!r} lost its claim on run {binding.run_id}: "
        "another process holds it now, so this copy has stopped",
        file=sys.stderr,
    )
    scheduler._mark_completed(coroutine)


def on_checkpoint(scheduler, coroutine, label: str) -> None:
    """The coroutine suspended at `checkpoint label`. Persist it, then let it go on.

    The write completes before this returns, and the scheduler requeues the
    coroutine only after that: no work after a checkpoint starts until the
    checkpoint is in the store. A refusal is delivered into the coroutine at the
    checkpoint, as an error it can catch.
    """
    from nodus.runtime.continuation import ContinuationRefused, capture_continuation
    from nodus.runtime.diagnostics import LangRuntimeError

    binding = coroutine.durable
    if not _renew(scheduler, coroutine, binding):
        return
    try:
        data = capture_continuation(coroutine)
    except ContinuationRefused as exc:
        hint = ""
        if exc.report is not None and any(
                "iterator" in o.detail for o in exc.report.obstacles):
            hint = ("\nA checkpoint inside a `for` body cannot be captured yet; loop "
                    "with `while` over an index instead.")
        path, line, col = _checkpoint_loc(coroutine)
        coroutine.pending_wait_error = LangRuntimeError(
            "runtime", f"checkpoint {label!r} cannot be made durable:\n{exc}{hint}",
            line=line, col=col, path=path)
        return
    store = binding.store
    record = store.get_run(binding.run_id)
    metadata = dict(record.metadata)
    metadata["continuation"] = data
    # D6: where this coroutine's clock stood, on both clocks, so a resume in a
    # process whose clock started later can continue its timeline.
    from nodus.vm.vm_chain import root_vm
    owner = getattr(coroutine, "owner_vm", None) or scheduler.vm
    guest_ms = (root_vm(owner).scheduler.time_source.now_ms()
                + float(coroutine.clock_offset_ms or 0.0))
    metadata["clock"] = {"guest_ms": guest_ms, "wall_ms": time.time() * 1000.0}
    metadata["checkpoints_reached"] = int(metadata.get("checkpoints_reached") or 0) + 1
    record.metadata = metadata
    record.current_checkpoint = label
    store.save_run(record)


def _checkpoint_loc(coroutine):
    """Where the checkpoint this coroutine is suspended at was written.

    The refusal is built here, by the scheduler, so nothing put a position on
    it: the error read `loop.nd:` with no line. The saved `ip` is one past the
    checkpoint's call, and the module's `code_locs` say where that call came from.
    """
    ctx = getattr(coroutine, "module_ctx", None)
    code_locs = ctx[4] if isinstance(ctx, tuple) and len(ctx) > 4 else None
    index = (coroutine.ip or 0) - 1
    if isinstance(code_locs, list) and 0 <= index < len(code_locs):
        return code_locs[index]
    return (None, None, None)


def on_settled(coroutine) -> None:
    """The coroutine finished or failed. Record which, once, if the run is still ours."""
    from nodus.runtime.durability import assess_values
    from nodus_lang_workflow.models import RUN_STATUS_COMPLETED, RUN_STATUS_FAILED

    binding = getattr(coroutine, "durable", None)
    if binding is None or binding.lost:
        return
    binding.lost = True  # settled: nothing further may write, including a second call
    store = binding.store
    if store.renew_claim(binding.run_id, binding.token) is None:
        return
    record = store.get_run(binding.run_id)
    metadata = dict(record.metadata)
    metadata.pop("continuation", None)
    failure = getattr(coroutine, "failure", None)
    if failure is not None:
        record.status = RUN_STATUS_FAILED
        record.last_error = str(failure)
    else:
        record.status = RUN_STATUS_COMPLETED
        result = coroutine.last_result
        if assess_values({"result": result}).durable:
            from nodus.runtime.continuation import encode_values
            metadata["result"] = encode_values([result])
        else:
            metadata["result_unrecorded"] = type(result).__name__
    record.metadata = metadata
    record.claim = None
    store.save_run(record)
