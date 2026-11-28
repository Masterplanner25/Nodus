# v6-flip: rebuild-effect
"""What a rebuild does when the program's top level has an effect (#917).

A rebuild -- a workflow resume, a sweep, a durable coroutine's resume -- re-runs
a program's stored source only to re-bind its definitions (#322). Since #909 it
skips `main()` and the scheduling builtins. What it still runs is any other
top-level call that reaches outside the program: a file write, an HTTP request,
a subprocess, a host function. Each one happens again on every rebuild.

This module decides what happens instead, in one place, consulted from the two
chokepoints a call outside the program goes through: the builtin capability
check in `VM.call_builtin` and `NodusRuntime._invoke_host_function`.

**What counts as an effect** is decided by capability (`BUILTIN_CAPABILITIES`),
so a new builtin is classified the day it gets a capability, with no list here
to keep in step. Reads are not effects: re-reading config is what a rebuild needs,
and doing it twice harms nothing. `env` holds reads and writes, so it is split by
builtin. `network` counts as an effect, GET included: a request can change
something at the other end, and a rebuild should not depend on the network.
Host functions count as effects unless registered `rebuild_safe=True`, because
only the host knows whether one is a pure lookup.

**Modes.** `"refuse"`, the default since 6.0.0, raises at the call, naming it
and its line. `"warn"` reports each effect and lets it run, which was the
default through 5.x. `"allow"` is the operator's override for runs whose
*stored* source has a top-level effect. A
resume rebuilds from the source stored with the run, so fixing the program does
not fix such a run, and refusing it would strand it.
"""

from __future__ import annotations

from nodus.runtime.capability import (
    AGENT_CALL,
    BUILTIN_CAPABILITIES,
    ENV,
    FS_READ,
    FS_WRITE,
    MEMORY_READ,
    MEMORY_WRITE,
    NETWORK,
    SUBPROCESS,
    SYSCALL,
    TOOL_INVOKE,
)

REBUILD_EFFECT_MODES: tuple[str, ...] = ("warn", "refuse", "allow")

# v6-flip: rebuild-effect
#: The mode when nothing chose one. "refuse" since 6.0.0 (#917); "warn" in 5.x.
DEFAULT_REBUILD_EFFECTS = "refuse"

#: Capabilities whose builtins change something outside the program.
EFFECT_CAPABILITIES = frozenset({
    FS_WRITE, MEMORY_WRITE, SUBPROCESS, NETWORK, AGENT_CALL, TOOL_INVOKE, SYSCALL,
})
#: Capabilities whose builtins only read. Every capability is in exactly one of
#: these two sets, or is `ENV`, which is split by builtin below;
#: `tests/test_rebuild_effects.py` fails on a capability in neither.
READ_CAPABILITIES = frozenset({FS_READ, MEMORY_READ})
ENV_WRITE_BUILTINS = frozenset({"env_set", "env_unset"})


def is_rebuild_effect(builtin_name: str) -> bool:
    """Does calling this builtin change something outside the program?"""
    capability = BUILTIN_CAPABILITIES.get(builtin_name)
    if capability is None:
        return False
    if capability == ENV:
        return builtin_name in ENV_WRITE_BUILTINS
    return capability in EFFECT_CAPABILITIES


#: The process-wide override (6.0.0, #917). A mode set on the VM -- through
#: `sweep(rebuild_effects=)`, `new_vm(rebuild_effects=)` or
#: `nodus workflow sweep --rebuild-effects` -- wins over it.
REBUILD_EFFECTS_ENV = "NODUS_REBUILD_EFFECTS"


def rebuild_mode(vm) -> str | None:
    """The mode in force if `vm` is rebuilding a program, else None.

    Read from the root VM: a stdlib wrapper such as `fs.write_file` runs its
    builtin on a per-call child VM, and the rebuild is the root's.

    **The environment variable is the door every resume path shares.** `sweep`
    takes a mode, but it does not resume a run that is waiting on an event, and
    `nodus workflow resume`, `deliver`, `resume_workflow()` and `nodus serve`
    take none. When the default became "refuse", a run stored by 5.x with a
    top-level effect would have had no way through on those paths. So the
    override lives here, where all of them already ask, rather than as a flag
    on each. An unknown value falls back to the default, which refuses.
    """
    import os

    from nodus.vm.vm_chain import root_vm

    root = root_vm(vm)
    if not getattr(root, "_suppress_flow_execution", False):
        return None
    mode = (getattr(root, "rebuild_effects", None) or os.environ.get(REBUILD_EFFECTS_ENV)
            or DEFAULT_REBUILD_EFFECTS)
    return mode if mode in REBUILD_EFFECT_MODES else DEFAULT_REBUILD_EFFECTS


def handle_rebuild_effect(vm, name: str, kind: str) -> None:
    """Apply the rebuild mode to a top-level effect `name` (a builtin or a host function).

    The one place the decision is made. A no-op outside a rebuild, or when the
    call is not an effect -- the callers ask `is_rebuild_effect` (builtins) or
    the runtime's `rebuild_safe` set (host functions) first.
    """
    mode = rebuild_mode(vm)
    if mode is None or mode == "allow":
        return
    # The user's line, not a stdlib wrapper's own (#922).
    path, line, col = vm.user_facing_loc()
    where = f"{path}:{line}:{col}" if path and line is not None else (path or "the top level")
    remedy = ("move the call into `fn main()`, which a rebuild skips"
              if kind == "builtin" else
              "move the call into `fn main()`, or register the function with "
              "`rebuild_safe=True` if it only reads")
    if mode == "refuse":
        vm.runtime_error(
            "sandbox",
            f"a rebuild re-ran {kind} `{name}` at {where}, which reaches outside the "
            f"program, and rebuild effects are refused. To resume a run whose stored "
            f"source does this, set NODUS_REBUILD_EFFECTS=allow (or pass "
            f"rebuild_effects=\"allow\"); to stop doing it, {remedy}.")
    import warnings

    # "warn", chosen explicitly: no longer a staged flip, so a plain warning.
    message = (f"a rebuild re-ran {kind} `{name}` at {where}, which reaches outside the "
               f"program, so it happened again (rebuild_effects=\"warn\"). By default "
               f"this is refused; {remedy} (#917).")
    warnings.warn(message, RuntimeWarning, stacklevel=3)
