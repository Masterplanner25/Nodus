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

# #473: authority that is not a sandbox flag. The vocabulary stopped at the four
# `NodusRuntime` confinement switches, so a policy could not see -- and therefore
# could not refuse -- tool invocation, syscalls, agent dispatch or the memory
# store. A `CapabilityPolicy` that denied everything denied none of them, and
# `DenyList("tool.invoke")` raised `unknown capability`.
#
# `memory.read` / `memory.write` are spelled to match what `SyscallSpec` has
# always declared for the memory syscalls (#478), so the two surfaces name the
# same authority rather than two spellings of it.
TOOL_INVOKE = "tool.invoke"
SYSCALL = "syscall"
AGENT_CALL = "agent.call"
MEMORY_READ = "memory.read"
MEMORY_WRITE = "memory.write"

ALL_CAPABILITIES = frozenset({
    SUBPROCESS, NETWORK, ENV, FS_READ, FS_WRITE,
    TOOL_INVOKE, SYSCALL, AGENT_CALL, MEMORY_READ, MEMORY_WRITE,
})


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
    for name in ("write_file", "write_file_bytes", "append_file", "mkdir",
                 "fs_mkdir", "fs_delete")
})
# #467: FS_READ was declared and attached to nothing, so reads were invisible to
# a policy for the same reason writes were visible -- the map, not the
# chokepoint. These are exactly the builtins that reach `_ensure_path_allowed`
# without writing; `path_join` and its neighbours are string manipulation and
# touch no filesystem.
BUILTIN_CAPABILITIES.update({
    name: FS_READ
    for name in (
        "read_file", "read_file_bytes", "list_dir", "path_exists", "exists",
        "hash_md5_file", "hash_sha1_file", "hash_sha256_file",
        "hash_sha512_file", "hash_blake2b_file",
    )
})
BUILTIN_CAPABILITIES.update({
    name: TOOL_INVOKE
    for name in ("tool_call", "tool_invoke", "__action_tool")
})
BUILTIN_CAPABILITIES.update({
    name: SYSCALL
    for name in ("syscall",)
})
BUILTIN_CAPABILITIES.update({
    name: AGENT_CALL
    # #616: `agent_call_async` was in the VM dispatch table but not in
    # BUILTIN_NAMES, so it fell outside this classification entirely. A
    # DenyList("agent.call") refused `agent_call` and permitted
    # `agent_call_async` against the same agent -- the async form of a
    # governed builtin escaping the policy that governs it.
    for name in ("agent_call", "agent_call_async", "__action_agent")
})
BUILTIN_CAPABILITIES.update({
    name: MEMORY_READ
    for name in (
        "memory_get", "memory_has", "memory_keys",
        "memory_recall_all", "memory_recall_from", "__action_memory_get",
    )
})
BUILTIN_CAPABILITIES.update({
    name: MEMORY_WRITE
    for name in (
        "memory_put", "memory_delete", "memory_share", "__action_memory_put",
    )
})

# `subprocess_shell_quote` is deliberately absent: it is string manipulation and
# runs nothing. Gating it would train readers that the list is approximate.
#
# The `__action_*` names are the lowerings of the `action` DSL forms. They are
# listed explicitly because `action tool "x"` reaches `__action_tool` without
# passing through `tool_call`, and a host cannot shadow either -- a builtin
# cannot be overridden, deliberately (#441-#444). Gating one spelling and not
# the other is the sibling-path shape, so both are named.


# Every builtin that carries no authority, and why.
#
# This exists so the classification is *total*. Without it, "is this builtin
# governed?" is answered by whether someone remembered to add it, which is how
# `tool_call`, `syscall`, `agent_call` and the whole memory surface stayed
# ungoverned from 5.0.0 through 5.2.0 while the chokepoint that would have
# caught them worked perfectly.
#
# `tests/test_capability_coverage.py` requires
# `BUILTIN_CAPABILITIES | NO_AUTHORITY_BUILTINS == BUILTIN_NAMES`, so a **new**
# builtin fails the suite until somebody decides which side it is on. That is
# the same shape as `TASK_STATUSES` and `FLOW_DECLARATIONS`: name the set once,
# and let a test drive off it.
NO_AUTHORITY_BUILTINS: dict[str, tuple[str, ...]] = {
    "pure computation": (
        # #616: unclassified rather than deliberately unauthorised -- they
        # were absent from BUILTIN_NAMES, which is the set this totality is
        # measured against. They compute and touch nothing.
        "chr", "ord", "collection_validate_reduce_fn",
        "bool_equal", "collection_len", "count", "has_key", "index_of",
        "json_parse", "json_parse_int", "json_stringify", "keys",
        "last_index_of", "len", "list_pop", "list_push", "map_has_key", "push",
        "range", "str", "str_contains", "str_endswith", "str_lower",
        "str_replace", "str_split", "str_startswith", "str_trim", "str_upper",
        "values", "type", "type_eq",
        "math_abs", "math_bit_and", "math_bit_lshift", "math_bit_not",
        "math_bit_or", "math_bit_rshift", "math_bit_xor", "math_ceil",
        "math_floor", "math_idiv", "math_infinity", "math_is_finite",
        "math_is_float", "math_is_inf", "math_is_int", "math_is_nan",
        "math_is_numeric", "math_log", "math_max", "math_min", "math_nan",
        "math_neg_infinity", "math_parse_int", "math_pow", "math_round",
        "math_sqrt", "math_to_float", "math_to_int",
        "encoding_base64_decode", "encoding_base64_encode",
        "encoding_base64_url_decode", "encoding_base64_url_encode",
        "encoding_hex_decode", "encoding_hex_encode",
        "encoding_hex_encode_upper", "encoding_url_decode",
        "encoding_url_decode_form", "encoding_url_encode",
        "encoding_url_encode_form",
        "subprocess_shell_quote",
    ),
    "hashing of values already in hand": (
        "hash_blake2b", "hash_blake2b_builder", "hash_hmac_blake2b",
        "hash_hmac_md5", "hash_hmac_sha1", "hash_hmac_sha256",
        "hash_hmac_sha512", "hash_md5", "hash_md5_builder", "hash_sha1",
        "hash_sha1_builder", "hash_sha256", "hash_sha256_builder",
        "hash_sha512", "hash_sha512_builder", "hash_compare",
    ),
    "path strings, touching no filesystem": (
        "path_absolute", "path_basename", "path_dirname", "path_ext",
        "path_join", "path_relative", "path_stem",
    ),
    "process-local clock and randomness": (
        "clock", "math_random",
        "secrets_random_bytes", "secrets_random_int",
        "secrets_token_alphanumeric", "secrets_token_base64",
        "secrets_token_hex", "secrets_token_urlsafe", "secrets_uuid_v4",
        "secrets_uuid_v7",
        "time_add", "time_add_days", "time_add_months", "time_add_years",
        "time_at", "time_days", "time_duration_between", "time_end_of_day",
        "time_format", "time_from_epoch_ms", "time_from_http_date",
        "time_from_iso8601", "time_hours", "time_minutes", "time_ms",
        "time_now", "time_now_in", "time_parse", "time_seconds",
        "time_start_of_day", "time_start_of_month", "time_start_of_week",
        "time_start_of_year", "time_subtract", "time_to_epoch_ms",
        "time_to_http_date", "time_to_iso8601", "time_to_utc", "time_to_zone",
        "time_weeks",
    ),
    # #395/#157: `cancel` and `wait` are here deliberately, and 04 SS10.2 gives
    # the reason. Cancellation *removes* authority rather than granting it -- a
    # guest that can cancel its own coroutines can already achieve the same
    # effect by returning -- and `wait` only reads an outcome the guest's own
    # task produced. Neither reaches anything outside the program, so neither is
    # in the class CapabilityPolicy exists to bound. The host-facing run-level
    # cancel is a Python API and is not guest-reachable at all.
    "in-process concurrency": (
        "__sleep", "cancel", "channel", "close", "coroutine", "coroutine_status",
        "wait", "recv", "resume", "run_loop", "send", "sleep", "spawn",
    ),
    "introspection of the running program": (
        "runtime_capabilities", "runtime_clear_events", "runtime_event_count", "runtime_events",
        "runtime_execution_unit_id", "runtime_fields", "runtime_fn_arity",
        "runtime_fn_module", "runtime_fn_name", "runtime_has",
        "runtime_module_fields", "runtime_scheduler_stats",
        "runtime_session_id", "runtime_stack_depth", "runtime_stack_frame",
        "runtime_task", "runtime_tasks", "runtime_time", "runtime_trace_id",
        "runtime_typeof",
    ),
    # Running a workflow grants nothing a direct call would not: every builtin
    # the steps reach passes this same chokepoint. Gating the orchestrator as
    # well would refuse the *shape* of a program rather than its authority.
    "orchestration of work that is itself governed": (
        "__action_emit", "current_workflow_id", "emit", "graph", "plan_goal",
        "plan_graph", "plan_workflow", "resume_goal", "resume_graph",
        "resume_workflow", "run_goal", "run_graph", "run_workflow", "task",
        "workflow_checkpoints", "workflow_resume_payload", "workflow_state",
        # #481: reads an argument the *caller* bound at run_workflow. It
        # reaches nothing the step could not already reach.
        "workflow_arg",
        "workflow_wait",
        "cb_call", "retry_call",
        "effect_action_id", "effect_complete", "effect_pending",
        "effect_resolve", "effect_store_size",
        # #616: the same family, and unclassified for the same reason — they
        # were absent from BUILTIN_NAMES, which is the set this totality is
        # measured against, so "total" was true of the wrong set.
        "effect_get_result", "state_contribute", "__workflow_checkpoint",
    ),
    # Naming what exists is not reaching it. A denied `tool_call` is still
    # denied after `tool_list` names the tool, and hiding the catalogue while
    # leaving the call ungoverned would be the wrong half.
    "discovery, not invocation": (
        "agent_available", "agent_describe", "cb_available", "cb_create",
        "cb_reset", "cb_state", "retry_available", "syscall_list",
        "tool_available", "tool_describe", "tool_has", "tool_list",
        "tool_lookup",
    ),
    # A guest-registered tool runs guest code, so registering one confers no
    # authority the guest did not already have. Note these mutate the *VM*
    # registry; tools a host registers through `NodusRuntime.tools` live in a
    # separate Python-side registry that `tool_unregister` cannot reach.
    "guest-scoped registry mutation": (
        "tool_register", "tool_unregister",
    ),
    # `print` writes to the host's captured stdout. `input` reads stdin and is
    # gated at registration by `allow_input`, which defaults to False -- a
    # separate mechanism that predates the policy layer.
    "host-mediated console i/o": (
        "print", "input",
    ),
    "test harness, host-invoked": (
        "test_advance_clock", "test_after_all", "test_after_each",
        "test_assert", "test_assert_close", "test_assert_contains",
        "test_assert_eq", "test_assert_err", "test_assert_has_key",
        "test_assert_in_range", "test_assert_kind", "test_assert_neq",
        "test_assert_ok", "test_assert_throws", "test_before_all",
        "test_before_each", "test_case", "test_case_async", "test_cleanup",
        "test_fixture", "test_flush_async", "test_parameterize", "test_skip",
        "test_suite",
    ),
}

#: Flattened view of :data:`NO_AUTHORITY_BUILTINS`.
NO_AUTHORITY_BUILTIN_NAMES = frozenset(
    name for names in NO_AUTHORITY_BUILTINS.values() for name in names
)


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

    @property
    def grant(self) -> str:
        """How a host turns this back on, for the denial message.

        A property rather than a formatted string at the call site, because
        `DomainBuiltinGroup` is granted by a *list* rather than a boolean (#167)
        and both are blocked by the same `block_group`. Each group type says how
        it is granted; the message template stays one sentence.
        """
        return f"{self.flag}=True"


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
class DomainBuiltinGroup:
    """One slice of the agentic surface, and what withholding it costs (#167).

    Deliberately **not** a `GatedBuiltinGroup`, though the fields line up. That
    one answers *"which builtins does capability flag X withhold"* — a security
    question, answered by a boolean, denying by default. This answers *"which
    builtins make up domain surface Y"* — a composition question, answered by a
    list, and granting everything by default because withholding a domain is a
    choice about what the runtime is *for*, not about what a program may be
    trusted with. Same shape, different question; merging them would put one
    name on two decisions.

    The attribute names match `GatedBuiltinGroup` so `BuiltinRegistry.block_group`
    serves both without knowing which it has. That much sharing is the point:
    a withheld builtin should refuse identically however it came to be withheld.
    """

    name: str
    """The extension name — what goes in `NodusRuntime(extensions=[...])`."""

    capability: str
    """The capability label recorded on the `capability_denied` event."""

    description: str
    """The human phrase used in the denial message ("workflow orchestration")."""

    arity: tuple[int, ...]
    """Arity accepted by the blocked stubs. Wide, for the reason
    `GatedBuiltinGroup.arity` gives: the stub must accept whatever the real
    builtin would, or the caller gets an arity error instead of the refusal."""

    names: tuple[str, ...]
    """The builtins withheld when this extension is not selected."""

    @property
    def grant(self) -> str:
        """How a host turns this back on, for the denial message."""
        return f'extensions=["{self.name}"]'


#: The agentic surface, sliced into what a host might want whole or not at all.
#:
#: An embedder who wants Nodus as a general-purpose scripting engine carried the
#: whole orchestration and agent surface regardless — 34 builtins for workflows,
#: tools, agents, syscalls and memory actions, on every VM, with no way to omit
#: them short of forking (#167).
#:
#: **Everything is granted unless a host says otherwise**, which is the opposite
#: default from `GATED_BUILTINS` and deliberately so. Denying a capability
#: protects against a program; omitting a domain narrows what the runtime is,
#: and a runtime that silently lost `run_workflow` on upgrade would be a far
#: worse failure than one that carries a surface nobody calls.
#:
#: `emit` is *not* here on purpose. It takes a name and a JSON payload and puts
#: an event on the bus — general-purpose observability that a lean runtime still
#: wants. `__action_emit` is here, because it is the lowering of an `action`
#: statement, which only exists inside a flow.
DOMAIN_BUILTIN_GROUPS: dict[str, DomainBuiltinGroup] = {
    "workflow": DomainBuiltinGroup(
        name="workflow",
        capability="workflow",
        description="workflow, goal and graph orchestration",
        arity=(0, 1, 2, 3, 4),
        names=(
            "task", "graph", "run_graph", "plan_graph", "resume_graph",
            "run_workflow", "plan_workflow", "resume_workflow",
            "run_goal", "plan_goal", "resume_goal",
            "workflow_state", "workflow_arg", "state_contribute",
            "workflow_resume_payload", "workflow_wait", "workflow_checkpoints",
            "current_workflow_id", "__workflow_checkpoint", "__action_emit",
        ),
    ),
    "tool": DomainBuiltinGroup(
        name="tool",
        capability=TOOL_INVOKE,
        description="tool invocation",
        arity=(0, 1, 2),
        names=("tool_call", "tool_available", "tool_describe", "__action_tool"),
    ),
    "agent": DomainBuiltinGroup(
        name="agent",
        capability=AGENT_CALL,
        description="agent invocation",
        arity=(0, 1, 2),
        names=(
            "agent_call", "agent_call_async", "agent_available", "agent_describe",
            "__action_agent",
        ),
    ),
    "syscall": DomainBuiltinGroup(
        name="syscall",
        capability=SYSCALL,
        description="syscall dispatch",
        arity=(0, 1, 2),
        names=("syscall", "syscall_list"),
    ),
    "memory": DomainBuiltinGroup(
        name="memory",
        capability=MEMORY_WRITE,
        description="memory actions",
        arity=(1, 2),
        names=("__action_memory_put", "__action_memory_get"),
    ),
}

def validate_extensions(extensions) -> None:
    """Refuse an unknown domain-surface name, or return quietly (#167).

    One implementation, two callers — `NodusRuntime.__init__` and
    `VM._withhold_unselected_extensions` — because "is this a real extension
    name?" answered in two places is the shape this codebase catalogues, and
    here the two answered at *different times*: the VM refused at construction
    and the runtime did not refuse until its first `run_source`.

    That gap was found by Gate 10b against the built wheel, not by the suite,
    because `tests/test_domain_extensions.py` constructed a `VM` directly. The
    documented embedding entry point is `NodusRuntime`, so the tested path and
    the documented path were different ones.

    `None` means every surface and is not an error; only a name that is not a
    group is. Refused rather than ignored, per #490: a typo that silently
    withheld the surface it meant to grant is the "accepted and ignored" third
    state.
    """
    if extensions is None:
        return
    unknown = set(extensions) - set(DOMAIN_BUILTIN_GROUPS)
    if unknown:
        raise ValueError(
            f"Unknown extension(s): {', '.join(sorted(unknown))}. "
            f"Known: {', '.join(sorted(DOMAIN_BUILTIN_GROUPS))}."
        )


DOMAIN_BUILTIN_NAMES: frozenset[str] = frozenset(
    name for group in DOMAIN_BUILTIN_GROUPS.values() for name in group.names
)
"""Every builtin belonging to some domain extension, flattened."""


# Where the two structures name different sets, and why.
#
# `BUILTIN_CAPABILITIES` and `DOMAIN_BUILTIN_GROUPS` both partition builtins by
# surface, and #756 was filed because they disagreed about the agent surface.
# They answer different questions and are *meant* to disagree in places: one
# asks what authority a call carries, the other what the runtime is composed of.
# That makes an unexamined disagreement indistinguishable from drift, which is
# the whole difficulty -- so the disagreements are listed here with a reason,
# and `tests/test_domain_extensions.py` fails on one that is not.
#
# The direction that matters is `governed but ungrouped`: a builtin that
# requires `agent.call` and is *not* withheld by `extensions=["..."]` stays
# reachable in a runtime whose host believed it had removed the agent surface.
# Every entry below is the benign form of that -- state it, or a later addition
# is the harmful form and nothing says so.
DOMAIN_SURFACE_DIVERGENCES: dict[str, tuple[str, ...]] = {
    # `tool_call` reaches a tool the *host* registered; `tool_invoke` reaches
    # one the *guest* registered with `tool_register`, which runs guest code and
    # confers nothing the guest did not already have -- which is why
    # `tool_register` and `tool_unregister` sit in NO_AUTHORITY_BUILTINS under
    # "guest-scoped registry mutation". So it is an invocation (authority
    # governs it) without being part of the host tool surface (composition does
    # not withhold it). `extensions=[]` leaves it reachable, deliberately.
    "guest-registered tools: an invocation, but not the host's tool surface": (
        "tool_invoke",
    ),
    # The `memory` group is the two `action memory` lowerings, as its
    # description ("memory actions") says. The `memory_*` family is the
    # general-purpose per-runtime store -- isolated per `NodusRuntime` since
    # #185, reaching nothing outside the process -- and a runtime narrowed to
    # "a general-purpose scripting engine" still wants it. Authority governs
    # it via `memory.read` / `memory.write`; a host that wants it gone uses a
    # `capability_policy`, not `extensions=`.
    "the general-purpose store, not the `action memory` lowerings": (
        "memory_get", "memory_has", "memory_keys", "memory_recall_all",
        "memory_recall_from", "memory_put", "memory_delete", "memory_share",
    ),
    # A group carries one `capability` label, used on the `capability_denied`
    # event when the whole surface is withheld; the memory surface spans two
    # authorities. The group names the stronger one, so a withheld
    # `__action_memory_get` reports `memory.write`. Grouping is unaffected --
    # both lowerings are withheld together, which is the part that matters.
    "one group label over a surface that spans two authorities": (
        "__action_memory_get",
    ),
}


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

    **It refuses invocation, not discovery, and that is deliberate.** Denying
    `agent.call` stops `agent_call`; it does not stop `agent_available()` or
    `agent_describe(name)`, because the discovery verbs carry no authority — see
    `NO_AUTHORITY_BUILTINS["discovery, not invocation"]`, which states the
    reasoning and is what `tests/test_capability_coverage.py` measures totality
    against.

    What that means concretely, because "carries no authority" and "reveals
    nothing" are not the same claim and only the first is being made:

    - `agent_available()` / `tool_available()` / `tool_has()` return **names**.
    - `agent_describe()` / `tool_describe()` return the **host-authored
      description and parameter schema** the host registered.
    - `syscall_list()` returns full specs, including which capability each
      syscall requires.

    So a guest that is refused every call can still enumerate the surface and
    read what the host wrote about it. If that matters for your deployment,
    the boundary to use is `extensions=` (#167), which withholds the builtins
    entirely rather than refusing them at call time — a withheld
    `agent_describe` is a refusing stub with nothing behind it.
    `tests/test_discovery_disclosure.py` pins exactly what is and is not visible.
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
            if not isinstance(arg, str):
                continue
            inside, root = _is_inside_nodus_state(arg)
            if inside:
                where = "" if root == ".nodus" else f" at {root!r}"
                return CapabilityDecision.deny(
                    f"writing to the runtime's own state directory{where} is never "
                    f"permitted ({arg!r})"
                )
        return None


def _is_inside_nodus_state(path: str) -> "tuple[bool, str | None]":
    """True when *path* points inside runtime-owned state.

    Two rules, and #585 is why the second exists. Matching a literal `.nodus`
    path segment protected the *default* location only: relocating the store with
    `NODUS_WORKFLOW_STORE_ROOT` moved it somewhere with no such segment, and the
    Floor stopped covering it. Demonstrated rather than reasoned about — with
    that variable set, a guest calling `fs.write("../relocated/pwned.txt", ...)`
    wrote into the live run store, while the identical write to the default
    location was denied. So the check now also asks whether the path is inside a
    root the runtime is *currently* using.

    Segment comparison, not substring: a file innocently named
    `my.nodus-notes.txt` is not caught, and `../.nodus/x` is.
    """
    from nodus.runtime.state_paths import is_inside_run_state

    return is_inside_run_state(path)


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
    "writable_paths",
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
