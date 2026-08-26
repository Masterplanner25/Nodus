"""Closed-issue test for #491: the agent host boundary is documented.

`agent_call` is the point where a Nodus program hands a semantic decision to the
host — the surface the "agentic hosts" positioning rests on. It appeared zero
times in `docs/guide/`, `llms.txt` and `llms-full.txt`: every hit in `docs/` was
in an eval record or a governance document, i.e. writing *about* the project
rather than *for* a user.

Two of the three assertions drive off the VM's own dispatch table rather than a
hand-written list of names, so a **new** agent builtin fails the suite until it
is documented — which is the only version of this test that keeps working. A
list of names here would be a third enumeration of the same question, and #616
is what that looks like when it drifts.
"""

import sys

from pathlib import Path

# closes: #491

_REPO_ROOT = Path(__file__).parents[2]
sys.path.insert(0, str(_REPO_ROOT / "src"))  # noqa: E402

from nodus.runtime.embedding import NodusRuntime  # noqa: E402
from nodus.vm.vm import VM  # noqa: E402

_GUIDE = _REPO_ROOT / "docs" / "guide" / "agent-host-boundary.md"
_LLMS = _REPO_ROOT / "llms.txt"
_LLMS_FULL = _REPO_ROOT / "llms-full.txt"

# `__action_agent` is the lowering target behind `action agent`, not a name a
# user writes; the guide documents the statement form instead.
_INTERNAL = {"__action_agent"}


def _agent_builtins() -> set[str]:
    vm = VM([], {}, code_locs=[])
    return {name for name in vm.builtins if "agent" in name} - _INTERNAL


def test_every_agent_builtin_is_named_in_the_guide():
    guide = _GUIDE.read_text(encoding="utf-8")
    missing = sorted(name for name in _agent_builtins() if name not in guide)
    assert not missing, (
        "agent builtins exist that docs/guide/agent-host-boundary.md never names: "
        f"{missing}. The guide is the only user-facing description of this "
        "boundary; a builtin absent from it is undiscoverable."
    )


def test_the_ai_discoverability_files_name_the_boundary():
    """`llms.txt` and `llms-full.txt` exist so an agent learns what Nodus offers.

    Neither named the builtin that makes Nodus useful to an agent host. An agent
    reading them and concluding there was no agent boundary was reading them
    correctly.
    """
    for path in (_LLMS, _LLMS_FULL):
        text = path.read_text(encoding="utf-8")
        assert "agent_call" in text, f"{path.name} does not mention agent_call"
    # The rich-summary file carries the trap, not just the name.
    full = _LLMS_FULL.read_text(encoding="utf-8")
    assert "result" in full and "agent_call" in full, (
        "llms-full.txt must say that the handler's value is under `result`, not "
        "returned directly — that is the mistake the envelope shape invites"
    )


def test_register_agent_is_on_the_runtime_and_respects_its_registry():
    """Part 2 of #491, and it is a correctness fix rather than ergonomics.

    The module-level `register_agent` defaults to the process-global registry, so
    an embedder who scoped a runtime with `agent_registry={}` and registered the
    obvious way got a handler that runtime could neither see nor call.
    """
    assert hasattr(NodusRuntime, "register_agent"), (
        "an embedder who has just used register_function reaches for "
        "register_agent on the same object"
    )
    assert hasattr(NodusRuntime, "unregister_agent")

    scoped = NodusRuntime(agent_registry={})
    scoped.register_agent("picker", lambda payload: {"choice": "rebase"})

    result = scoped.run_source('fn main() { print(agent_available()) }')
    assert "picker" in result["stdout"], (
        "registering through the runtime must land in the registry that runtime "
        "uses, or scoping silently loses the handler"
    )

    other = NodusRuntime(agent_registry={})
    assert "picker" not in other.run_source('fn main() { print(agent_available()) }')["stdout"], (
        "and it must not leak into a differently-scoped runtime"
    )


def test_the_documented_envelope_matches_what_agent_call_returns():
    """The guide lists the envelope's keys. Pin them against a real call.

    Documenting a return shape from memory is how the shape and the prose drift;
    this reads the actual envelope.
    """
    runtime = NodusRuntime(agent_registry={})
    runtime.register_agent("picker", lambda payload: {"choice": "rebase"})
    result = runtime.run_source(
        'fn main() { let v = agent_call("picker", {}); print(keys(v)) }'
    )
    keys = {k.strip().strip('"') for k in result["stdout"].strip().strip("[]").split(",")}

    guide = _GUIDE.read_text(encoding="utf-8")
    missing = sorted(k for k in keys if f"`{k}`" not in guide)
    assert not missing, f"envelope keys the guide does not name: {missing}"
