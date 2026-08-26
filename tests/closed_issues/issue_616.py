"""Closed-issue test for #616: BUILTIN_NAMES must equal the VM dispatch table.

`BUILTIN_NAMES` is a hand-maintained set. The VM's dispatch table is the thing
that decides what actually runs. They had drifted by seven names, and two guards
consult the stale one:

- `register_function`'s "cannot override a builtin" check — a **security
  boundary** per CLAUDE.md, because a host installing a fail-loud guard under a
  guest-reachable name needs to know the guard is the only thing there.
  `register_function("chr", ...)` was accepted and `chr(65i)` returned
  `"HIJACKED"`.
- The capability classification. `tests/test_capability_coverage.py` requires
  `BUILTIN_CAPABILITIES | NO_AUTHORITY_BUILTINS == BUILTIN_NAMES` so that a new
  builtin fails the suite until someone decides which side it is on — but that
  totality was measured against the *stale* set, so the seven were outside the
  classification entirely. **`agent_call_async` was one of them**, and its sync
  twin `agent_call` is governed by `agent.call`: a `DenyList("agent.call")`
  refused `agent_call` and permitted `agent_call_async` against the same agent.

The fix is this test. Adding the seven names repairs today; anchoring the
totality to the dispatch table is what stops the eighth.
"""

import sys

from pathlib import Path

# closes: #616

_REPO_ROOT = Path(__file__).parents[2]
sys.path.insert(0, str(_REPO_ROOT / "src"))  # noqa: E402

from nodus.builtins.nodus_builtins import BUILTIN_NAMES  # noqa: E402
from nodus.runtime.capability import (  # noqa: E402
    BUILTIN_CAPABILITIES,
    NO_AUTHORITY_BUILTIN_NAMES,
)
from nodus.runtime.embedding import NodusRuntime  # noqa: E402
from nodus.vm.vm import VM  # noqa: E402


def _dispatch_table() -> set[str]:
    """The authority: what the VM will actually dispatch.

    Read out of a constructed VM rather than parsed, which is the mechanism
    `nodus_gate --opcodes` already uses for the instruction set.
    """
    return set(VM([], {}, code_locs=[]).builtins)


def test_builtin_names_equals_the_vm_dispatch_table():
    table = _dispatch_table()
    names = set(BUILTIN_NAMES)
    missing = sorted(table - names)
    extra = sorted(names - table)
    assert not missing and not extra, (
        "BUILTIN_NAMES has drifted from the VM dispatch table. Everything that "
        "consults BUILTIN_NAMES — register_function's override guard, the "
        "capability classification, the compiler — is deciding against a set "
        "that is not what runs.\n"
        f"  in the VM table but not in BUILTIN_NAMES: {missing}\n"
        f"  in BUILTIN_NAMES but not in the VM table: {extra}"
    )


def test_the_capability_classification_covers_the_dispatch_table():
    """The totality must be measured against what runs, not against a copy.

    `test_capability_coverage.py` already pins the classification to
    BUILTIN_NAMES. This pins the other end, which is the link that was missing:
    with both, a new builtin is unclassified *and* fails the suite.
    """
    classified = set(BUILTIN_CAPABILITIES) | set(NO_AUTHORITY_BUILTIN_NAMES)
    unclassified = sorted(_dispatch_table() - classified)
    assert not unclassified, (
        "builtins the VM dispatches that carry no capability decision: "
        f"{unclassified}. Decide: governed (BUILTIN_CAPABILITIES) or "
        "deliberately unauthorised (NO_AUTHORITY_BUILTINS)."
    )


def test_an_async_builtin_carries_its_sync_twins_capability():
    """The specific bypass, pinned so it cannot come back quietly."""
    assert BUILTIN_CAPABILITIES.get("agent_call_async") == BUILTIN_CAPABILITIES.get("agent_call"), (
        "agent_call_async must be governed by the same capability as agent_call, "
        "or a policy denying one is bypassed by writing the other"
    )


def test_the_override_guard_refuses_every_dispatched_builtin():
    """Behaviour, not just the set — the guard reads BUILTIN_NAMES today, but
    this asserts the property that matters regardless of what it reads."""
    runtime = NodusRuntime()
    accepted = []
    for name in sorted(_dispatch_table()):
        try:
            runtime.register_function(name, lambda *args: "HIJACKED", arity=1)
        except ValueError:
            continue
        accepted.append(name)
    assert not accepted, (
        "register_function accepted names that shadow real builtins: "
        f"{accepted}. That guard is a security boundary — a host installing a "
        "fail-loud guard under a guest-reachable name must know the guard is "
        "the only thing there."
    )
