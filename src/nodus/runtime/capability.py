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

# `subprocess_shell_quote` is deliberately absent: it is string manipulation and
# runs nothing. Gating it would train readers that the list is approximate.


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


@dataclass(frozen=True)
class CapabilityDecision:
    """A policy's answer.

    Two-valued for now. The third value — `ask`, routed to an approval pause —
    is stage 3, and is deliberately not stubbed here: a placeholder that always
    resolves one way would be indistinguishable from the decision having been
    made, which is the failure this whole issue is about.
    """

    allowed: bool
    reason: str = ""

    @staticmethod
    def allow() -> "CapabilityDecision":
        return CapabilityDecision(True)

    @staticmethod
    def deny(reason: str) -> "CapabilityDecision":
        return CapabilityDecision(False, reason)


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
