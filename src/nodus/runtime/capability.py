"""Capability policy at the boundary Nodus already owns (#405).

Every call a guest program can make into the host passes through one of two
dispatch sites, and guest code cannot route around either: Nodus has no imports
into the host, no `eval`, and no attribute access across the boundary. That
property is what makes an in-process capability jail possible here and not in a
Python library, and all three external architecture audits identified using it as
the highest-leverage change available.

**Two chokepoints, not one.** `docs/governance/CAPABILITY_POLICY_DESIGN.md` §8
stages builtins as step 4, after host functions. Measured, that ordering would
produce an audit trail that misses everything anyone cares about: `subprocess_run`,
`http_get` and `env_get` are *builtins*, registered through
`BuiltinRegistry.register_all` and dispatched by `VM.call_builtin`. They never
touch `_invoke_host_function`. So both sites are covered from the start.

This module is **stdlib-only and lives in core**, per the seam decided in that
document: a bare `NodusRuntime()` in a process with no companion package must
still enforce, because a differentiator cannot be an optional dependency.
`nodus-governance` is a rule *source* and an audit *sink*; core decides. The types
here are deliberately named `Capability*` rather than `Policy*` — two things named
`Policy` in one ecosystem, meaning "operator authority" and "guest authority", is
a NAME-COL-001 repeat waiting to happen.

## What this stage does and does not do

Implemented (stages 1–2 of that document's staging):

- a policy consulted at **both** chokepoints, defaulting to allow, so nothing
  changes for anyone who does not set one;
- `capability_denied` on the event bus, so a refusal is *recorded* rather than
  only raised — including for the pre-existing `allow_subprocess=False` style
  blocks, which until now emitted nothing structured;
- capability requirements declared per builtin and per host function, so
  authority is a property of the callable rather than of the runtime.

Not implemented, and deliberately: the three-valued `allow | ask | deny` cascade
with its unbypassable floor, layered rule sources, approval caching, attenuation,
and deny-by-default. Those are where the design questions are, and
deny-by-default is a compatibility decision rather than an engineering one.
"""

from __future__ import annotations

from dataclasses import dataclass, field


# Capability names. Kept as a closed, enumerable set rather than free-form
# strings: the point of declaring authority is that a reader — or an operator
# reviewing a generated program — can see the whole surface at once.
SUBPROCESS = "subprocess"
NETWORK = "network"
ENV = "env"
FS_READ = "fs.read"
FS_WRITE = "fs.write"

ALL_CAPABILITIES = frozenset({SUBPROCESS, NETWORK, ENV, FS_READ, FS_WRITE})


# Which builtins require which capability.
#
# Only builtins named here consult the policy. That is a performance decision and
# a design one: `len`, `push` and `str` carry no authority, and making the hot
# path pay for a policy lookup on every call to them would be a real cost for no
# benefit. It also means this mapping IS the capability surface of the language,
# in one readable place, which is the property `docs/design/v5/00-domain-statement.md`
# asks of anything in the domain.
BUILTIN_CAPABILITIES: dict[str, str] = {
    name: SUBPROCESS
    for name in (
        "subprocess_run", "subprocess_run_async", "subprocess_shell",
        "subprocess_shell_async", "subprocess_spawn", "subprocess_spawn_shell",
    )
}
BUILTIN_CAPABILITIES.update({
    name: NETWORK
    for name in (
        "http_get", "http_post", "http_put", "http_delete", "http_patch",
        "http_head", "http_options_verb", "http_request",
        "http_get_async", "http_post_async", "http_put_async",
        "http_delete_async", "http_patch_async", "http_head_async",
        "http_options_async", "http_request_async",
        "http_stream", "http_sse",
    )
})
BUILTIN_CAPABILITIES.update({
    name: ENV
    for name in ("env_get", "env_set", "env_unset", "env_has", "env_list", "env_list_keys")
})
BUILTIN_CAPABILITIES.update({
    name: FS_WRITE
    for name in ("write_file", "append_file", "mkdir", "fs_mkdir", "fs_delete")
})

# `subprocess_shell_quote` is deliberately absent: it is string manipulation and
# runs nothing. Gating it would train readers that the list is approximate.


@dataclass(frozen=True)
class GatedBuiltinGroup:
    """One registration-time capability gate: a flag, and what it withholds."""

    flag: str
    """The `NodusRuntime` keyword that grants this group — e.g. `allow_subprocess`."""

    capability: str
    """The capability label recorded on the `capability_denied` event."""

    description: str
    """The human phrase used in the denial message ("subprocess execution")."""

    arity: tuple[int, ...]
    """Arity accepted by the blocked stubs. Wide on purpose: the stub must accept
    whatever the real builtin would, so the caller gets the sandbox refusal rather
    than an arity error that hides it."""

    names: tuple[str, ...]
    """The builtins withheld when the flag is False."""


# The registration-time gates, as data.
#
# This is a *different* list from `BUILTIN_CAPABILITIES` above, and the difference
# is the point. `BUILTIN_CAPABILITIES` says which builtins consult the policy at
# call time; this says which are never registered at all when the corresponding
# flag is False. The two overlap but are not identical — see the
# `subprocess_shell_quote` note above and `tests/test_gated_builtins.py`, which
# pins the relationship so a new builtin added to one list and not the other
# fails the suite instead of drifting quietly.
#
# Exposed as data because downstream embedders need to enumerate the gated surface
# to assert their own confinement. Before this, the only way to get these names was
# to regex the source of `BuiltinRegistry.register_all` — which aindy-runtime did,
# and which broke on the 5.0.0 refactor that moved the names into the `else:`
# branch, silently capturing flag names out of `_denied_reason` and reporting them
# as leaked builtins. A list that downstream must scrape is a list that breaks
# quietly on our refactors and loudly on theirs.
GATED_BUILTINS: dict[str, GatedBuiltinGroup] = {
    "allow_env": GatedBuiltinGroup(
        flag="allow_env",
        capability=ENV,
        description="environment variable access",
        arity=(0, 1, 2),
        names=(
            "env_get", "env_set", "env_unset", "env_has", "env_list", "env_list_keys",
        ),
    ),
    "allow_network": GatedBuiltinGroup(
        flag="allow_network",
        capability=NETWORK,
        description="network access",
        arity=(1, 2, 3),
        names=(
            "http_get", "http_post", "http_put", "http_delete", "http_patch",
            "http_head", "http_options_verb", "http_request",
            "http_get_async", "http_post_async", "http_put_async",
            "http_delete_async", "http_patch_async", "http_head_async",
            "http_options_async", "http_request_async",
            "http_stream", "http_sse",
        ),
    ),
    "allow_subprocess": GatedBuiltinGroup(
        flag="allow_subprocess",
        capability=SUBPROCESS,
        description="subprocess execution",
        arity=(1, 2, 3),
        names=(
            "subprocess_run", "subprocess_run_async", "subprocess_shell",
            "subprocess_shell_async", "subprocess_spawn", "subprocess_spawn_shell",
            "subprocess_shell_quote",
        ),
    ),
}

GATED_BUILTIN_NAMES: frozenset[str] = frozenset(
    name for group in GATED_BUILTINS.values() for name in group.names
)
"""Every builtin withheld by some capability flag, flattened."""


@dataclass(frozen=True)
class CapabilityRequest:
    """What is being asked for, at the moment of asking."""

    capability: str | None
    """The declared capability, or None when the callable declares none."""

    target: str
    """The builtin or host-function name."""

    kind: str
    """`"builtin"` or `"host_function"` — which chokepoint this came through."""

    args: tuple = ()
    """The call's arguments, so a policy can decide on *what* rather than only
    *whether* — `http_get("https://internal/…")` is a different request from
    `http_get("https://example.com")`. Marshalled host values at the host-function
    site; runtime values at the builtin site."""


ALLOW = "allow"
ASK = "ask"
DENY = "deny"


@dataclass(frozen=True)
class CapabilityDecision:
    """A policy's answer: `allow`, `ask` or `deny`.

    The middle value is the load-bearing one, and all three reference systems in
    `CAPABILITY_POLICY_DESIGN.md` have it. `ask` means *this needs a human*, and
    what happens when there is nobody to ask is the decision that matters:
    **`ask` with no approval channel is `deny`, never "run anyway."** Codex
    reaches the same answer (`Prompt` under `AskForApproval::Never` becomes
    `Forbidden`), and the alternative silently converts an unanswered question
    into permission.
    """

    outcome: str = ALLOW
    reason: str = ""

    @property
    def allowed(self) -> bool:
        """Kept so existing callers reading `.allowed` stay correct: only an
        outright allow is permission. `ask` is not."""
        return self.outcome == ALLOW

    @staticmethod
    def allow() -> "CapabilityDecision":
        return CapabilityDecision(ALLOW)

    @staticmethod
    def ask(reason: str) -> "CapabilityDecision":
        return CapabilityDecision(ASK, reason)

    @staticmethod
    def deny(reason: str) -> "CapabilityDecision":
        return CapabilityDecision(DENY, reason)


class CapabilityPolicy:
    """Decides whether a guest call proceeds.

    Subclass and override `check`. The default allows everything, which is what
    keeps this stage additive: a runtime with no policy behaves exactly as before.
    """

    def check(self, request: CapabilityRequest) -> CapabilityDecision:
        return CapabilityDecision.allow()


class AllowAll(CapabilityPolicy):
    """The default. Explicit so that "no policy" is a visible choice in a trace
    rather than an absence someone has to infer."""


@dataclass
class DenyList(CapabilityPolicy):
    """Refuse the named capabilities, allow the rest.

    A convenience for the common embedding case, not the eventual model — the
    layered, tiered rule sources of the design document are stage 3.
    """

    denied: frozenset = field(default_factory=frozenset)

    def __init__(self, *capabilities: str) -> None:
        unknown = set(capabilities) - ALL_CAPABILITIES
        if unknown:
            # Better to reject a typo than to silently permit what the caller
            # believed they had forbidden.
            raise ValueError(
                f"unknown capability {sorted(unknown)}; known: {sorted(ALL_CAPABILITIES)}"
            )
        self.denied = frozenset(capabilities)

    def check(self, request: CapabilityRequest) -> CapabilityDecision:
        if request.capability in self.denied:
            return CapabilityDecision.deny(
                f"{request.capability} is not granted to this runtime"
            )
        return CapabilityDecision.allow()


class ApprovalChannel:
    """Where an `ask` decision goes.

    An embedder supplies one to make `ask` mean something. Without one there is
    nobody to ask, and an unanswered question must not become permission — see
    `CapabilityDecision`.
    """

    def request(self, request: "CapabilityRequest", reason: str) -> bool:
        raise NotImplementedError


class Floor:
    """Consulted before any policy, and **it can only restrict**.

    The reason this exists now rather than later: all three systems in
    `CAPABILITY_POLICY_DESIGN.md` added a bypass mode under pressure and
    retrofitted a floor beneath it afterwards. Nodus has no bypass mode yet, so
    building the floor first is free; retrofitting is not.

    `check` returns a decision to impose, or `None` to abstain. **There is no way
    for a floor to return `allow`** — a floor that could grant would let it
    override a policy's refusal, which is the opposite of a floor. It can only
    make the answer stricter than the policy would have.
    """

    def check(self, request: "CapabilityRequest") -> "CapabilityDecision | None":
        return None


class NodusStateFloor(Floor):
    """Refuse guest writes into the runtime's own durable state.

    `.nodus/` holds the workflow store, graph state and the bytecode cache. A
    guest that can write there can forge run records — verified before writing
    this: with default settings a script overwrote
    `.nodus/workflow_framework/runs/<id>.json` with `{"forged": true}` and the
    run reported success.

    This is Nodus's equivalent of the paths Claude Code protects even under
    `bypassPermissions` (`.git/`, shell rc files). Reads are untouched; only
    writes are refused.
    """

    def check(self, request: "CapabilityRequest") -> "CapabilityDecision | None":
        if request.capability != FS_WRITE:
            return None
        for arg in request.args:
            if isinstance(arg, str) and _is_inside_nodus_state(arg):
                return CapabilityDecision.deny(
                    f"writing to the runtime's own state directory is never permitted "
                    f"({arg!r})"
                )
        return None


def _is_inside_nodus_state(path: str) -> bool:
    """True when *path* points inside a `.nodus/` directory.

    Compares normalised path segments rather than substrings, so a file
    innocently named `my.nodus-notes.txt` is not caught and
    `../.nodus/x` is.
    """
    import os

    normalised = os.path.normpath(path).replace("\\", "/")
    return any(segment == ".nodus" for segment in normalised.split("/"))


DEFAULT_FLOOR = NodusStateFloor()


# Every piece of VM state that carries authority. A VM derived from another must
# inherit all of it, or the derivation is a sandbox escape.
#
# This list exists because the same bug shipped three times in one day — a check
# that lives on one path while a sibling path bypasses it (#392's
# `inline_retries`, #399's rebuild guard, and this module's own first version,
# where `import "std:subprocess"` ran on a child VM that had not inherited the
# policy). Derivation sites are where it recurs, because each one hand-copies
# whatever its author remembered.
#
# `tests/test_vm_authority_inheritance.py` asserts every derivation site
# preserves every attribute named here, so adding one without teaching the sites
# about it fails the suite rather than opening a hole.
AUTHORITY_ATTRIBUTES: tuple[str, ...] = (
    "allowed_paths",
    "fs_root",
    "allow_subprocess",
    "allow_network",
    "allow_env",
    "allowed_commands",
    "allowed_hosts",
    "capability_policy",
    "capability_floor",
    "approval_channel",
)


def inherit_authority(child, parent) -> None:
    """Copy every authority-bearing attribute from *parent* to *child*.

    Use this at any site that derives a VM from another. Copying by list rather
    than by hand is the point: the failure mode is not getting one wrong, it is
    forgetting that a new one exists.
    """
    if parent is None or child is None:
        return
    for attribute in AUTHORITY_ATTRIBUTES:
        if hasattr(parent, attribute):
            setattr(child, attribute, getattr(parent, attribute))


def emit_denied(event_bus, request: CapabilityRequest, reason: str) -> None:
    """Record a refusal on the event bus.

    Until now a sandbox denial raised `LangRuntimeError` and emitted nothing
    structured, so there was no way to answer "what did this program try to do
    that it was not allowed to?" — which is the question an operator running
    generated code actually has.
    """
    if event_bus is None:
        return
    try:
        event_bus.emit_event(
            "capability_denied",
            name=request.target,
            data={
                "capability": request.capability,
                "target": request.target,
                "kind": request.kind,
                "reason": reason,
            },
        )
    except Exception:
        # An audit sink must never be the thing that breaks the run it audits.
        pass
