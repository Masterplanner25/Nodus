"""Gate 10b: probe what the release *claims*, not what its code does.

Run this **before tagging**. Every other gate reads the code; this one reads the
sentences shipped alongside it, and those are the artifacts nothing else covers.
At 5.1.0 it caught four documents describing a task-status vocabulary the release
did not have -- one of them `README.md`, which `readme = "README.md"` makes the
permanent PyPI page. Run after the tag, that correction is impossible.

Two kinds of check, deliberately:

* **behaviour** -- exercise each thing the release says it added, through the
  package that actually resolves. Answers "does the claim hold".
* **prose** -- read the repo's own artifacts and compare them against the
  runtime's vocabulary. Answers "does anything still describe the previous
  release". That is the half that has caught things.

Usage::

    python tests/eval/release_claims_probe.py [--repo PATH]

Exits non-zero if any probe fails. Prints the resolved package path and version
first, because validating the wrong tree is the failure mode Gate 10 has already
had once -- 5.0.3 passed with 32 green probes against a tree that was not the one
being shipped.
"""

from __future__ import annotations

import argparse
import io
import json
import os
import contextlib
import re
import sys
from pathlib import Path

RESULTS: list[tuple[bool, str, str]] = []

#: Prose asserting that a fold policy is *unavailable* -- the claim this cycle
#: kept invalidating as `STATE_MERGE_POLICIES` grew from (any, once) to
#: (+ sum, append) to (+ union) across three PRs.
#:
#: Deliberately about unavailability, not refusal. An earlier version used a bare
#: "is refused" and flagged the *correct* sentence "under a fold policy, `+=`
#: contributes and `=` is refused" -- where what is refused is the assignment
#: form, not the policy. A probe that cries wolf on true prose gets switched off.
#: `_selfcheck()` holds it to both directions.
STALE_FOLD_CLAIM = (
    r"(fold(ing)?|merge:|`sum`|`append`|`union`)[^.\n]{0,80}"
    r"(not available|deliberately absent|is refused where|not yet available)"
    r"|union[^.\n]{0,60}(deliberately absent|not available)"
)

#: Sentences the pattern must catch, and sentences it must leave alone. Kept
#: beside the pattern so tightening it cannot quietly stop catching anything.
_STALE_EXAMPLES = [
    "Folding (`sum`, `append`, `union`) is **not available**. A fold needs a branch",
    'Writing `merge: "sum"` is refused where you write it rather than quietly behaving',
    "`union` is deliberately absent. It needs an element-equality story Nodus lacks",
]
_LIVE_EXAMPLES = [
    "**Under a fold policy, `+=` contributes and `=` is refused.**",
    "`counter += 1i` means *contribute one*, folded at the join.",
    "**Records are refused in a union contribution.** Records compare by identity,",
    '| `"union"` | concurrent writes concatenate, **dropping duplicates** |',
]


def probe(name: str):
    def wrap(fn):
        def run(*args, **kwargs):
            try:
                detail = fn(*args, **kwargs)
                RESULTS.append((True, name, detail or ""))
            except AssertionError as exc:
                RESULTS.append((False, name, str(exc)))
            except Exception as exc:  # a probe that errors is a failed probe
                RESULTS.append((False, name, f"{type(exc).__name__}: {exc}"))
        return run
    return wrap


def run_nd(source: str) -> dict:
    from nodus.runtime.embedding import NodusRuntime

    return NodusRuntime(timeout_ms=None, max_steps=None).run_source(
        source, filename="<probe>"
    )


def cli(argv: list[str]) -> tuple[int, str]:
    from nodus.cli.cli import main

    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        code = main(argv)
    return code, buf.getvalue()


# ---------------------------------------------------------------- behaviour


@probe("fold: sum combines concurrent contributions")
def probe_sum():
    result = run_nd(
        """
workflow race {
    state counter = 0i with { merge: "sum" }
    step a { sleep(20i); counter += 1i; return 1i }
    step b { sleep(20i); counter += 1i; return 2i }
    step j after a, b { return 0i }
}
fn main() { let r = run_workflow(race); print("C=\\(r["state"]["counter"])") }
"""
    )
    assert result.get("ok"), result.get("errors")
    out = result.get("stdout") or ""
    assert "C=2" in out, f"expected C=2, got {out.strip()!r}"
    return "the #485 reproduction now totals 2"


@probe("fold: append and union both land, union deduplicates")
def probe_append_union():
    result = run_nd(
        """
workflow g {
    state log = [] with { merge: "append" }
    state seen = [] with { merge: "union" }
    step a { sleep(10i); log += ["a"]; seen += ["x", "y"]; return 1i }
    step b { sleep(10i); log += ["b"]; seen += ["y", "z"]; return 2i }
    step j after a, b { return 0i }
}
fn main() {
    let r = run_workflow(g)
    print("LOG=\\(len(r["state"]["log"])) SEEN=\\(len(r["state"]["seen"]))")
}
"""
    )
    assert result.get("ok"), result.get("errors")
    out = (result.get("stdout") or "").strip()
    assert "LOG=2 SEEN=3" in out, out
    return "append keeps both, union drops the shared element"


@probe("fold: `=` on a folded cell is refused at compile time")
def probe_assign_refused():
    result = run_nd(
        """
workflow bad {
    state counter = 0i with { merge: "sum" }
    step a { counter = 5i; return 1i }
}
fn main() { run_workflow(bad) }
"""
    )
    assert not result.get("ok"), "a plain assignment to a folded cell was accepted"
    message = (result.get("errors") or [{}])[0].get("message", "")
    assert "+=" in message, message
    assert result.get("stage") != "execute" or "final value" in message, message
    return "refused before the program runs"


@probe("fold: a record element in a union contribution is refused, citing #545")
def probe_union_record():
    result = run_nd(
        """
workflow bad {
    state seen = [] with { merge: "union" }
    step a { seen += [record {x: 1i}]; return 1i }
}
fn main() { let r = run_workflow(bad); print("F=\\(len(r["failed"]))") }
"""
    )
    stderr = result.get("stderr") or ""
    assert "compare by identity" in stderr, stderr[:200]
    assert "#545" in stderr, "the refusal does not name the tracking issue"
    return "names the workaround and #545"


@probe("conflicts: silent when nothing was lost, loud when something was")
def probe_conflict_precision():
    agree = run_nd(
        """
workflow w {
    state x = 0i
    step a { sleep(10i); x = 5i; return 1i }
    step b { sleep(10i); x = 5i; return 2i }
    step j after a, b { return 0i }
}
fn main() { run_workflow(w) }
"""
    )
    assert "both wrote state" not in (agree.get("stderr") or ""), (
        "agreeing constant writes warned; that noise is what #544 removed"
    )
    lost = run_nd(
        """
workflow w {
    state x = 0i
    step a { let s = x; sleep(20i); x = s + 1i; return 1i }
    step b { let s = x; sleep(20i); x = s + 1i; return 2i }
    step j after a, b { return 0i }
}
fn main() { run_workflow(w) }
"""
    )
    stderr = lost.get("stderr") or ""
    assert "read it before writing" in stderr, stderr[:200]
    assert "6.0.0" in stderr, "the warning does not announce the flag day"
    return "read-modify-write named; agreement silent"


@probe("cli: graph show renders mermaid and dot")
def probe_graph_show(repo: Path):
    import tempfile

    src = """
workflow build {
    step fetch { return "d" }
    step compile after fetch { return "o" }
    step lint after fetch { return "c" }
    step package after compile, lint { return "a" }
}
let p = plan_workflow(build)
"""
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "g.nd"
        path.write_text(src, encoding="utf-8")
        code, mermaid = cli(["nodus", "graph", "show", str(path)])
        assert code == 0, f"graph show exited {code}"
        assert "flowchart TD" in mermaid, mermaid[:120]
        code, dot = cli(["nodus", "graph", "show", str(path), "--format", "dot"])
        assert code == 0
        assert dot.lstrip().startswith("digraph"), dot[:120]
        assert "rank=same" in dot, "parallel levels are not pinned"
    return "both formats, with levels ranked"


@probe("cli: doctor reports the resolved package and parses as JSON")
def probe_doctor():
    code, out = cli(["nodus", "doctor", "--json"])
    payload = json.loads(out)
    assert "checks" in payload and payload["checks"], out[:200]
    names = {c["name"] for c in payload["checks"]}
    assert {"nodus package", "version sync"} <= names, names
    assert code in (0, 1)
    return f"{len(payload['checks'])} checks, ok={payload['ok']}"


@probe("cli: completion emits all four shells with LF endings")
def probe_completion():
    from nodus.cli.completion import SHELLS, generate

    for shell in SHELLS:
        script = generate(shell)
        assert script.strip(), f"{shell} generated nothing"
        assert "\r\n" not in script, f"{shell} carries CRLF"
        assert "doctor" in script, f"{shell} omits a shipped command"
    return f"{len(SHELLS)} shells"


@probe("#532: publish parses the --project-root it documents")
def probe_publish_flag():
    from nodus.cli.cli import _parse_flags
    from nodus.cli.commands import flags_for

    with_values, no_values = flags_for("publish")
    positional, flags = _parse_flags(["--project-root", "/tmp/p"], with_values, no_values)
    assert positional == [], f"the flag was swallowed as a positional: {positional}"
    assert flags.get("--project-root") == "/tmp/p"
    return "no longer publishes the CWD"


@probe("#533: graph and workflow --help print their real help")
def probe_group_help():
    for name in ("graph", "workflow"):
        code, out = cli(["nodus", name, "--help"])
        assert code == 0
        assert "No detailed option help" not in out, f"{name} still prints the stub"
        assert "Subcommands:" in out, f"{name} help lists no subcommands"
    return "both reach the table"


@probe("#522: a default run retains no VM bookkeeping events")
def probe_event_retention():
    from nodus.runtime.embedding import NodusRuntime
    from nodus.runtime.runtime_events import VM_BOOKKEEPING_EVENTS

    runtime = NodusRuntime(timeout_ms=None, max_steps=None)
    runtime.run_source(
        'fn f(a) { return a }\nlet t = 0i\nfor i in range(0i, 30i) { t = t + f(i) }\nprint("\\(t)")\n',
        filename="<probe>",
    )
    vm = runtime.active_vm()
    kept = {e.type for e in vm.event_bus.events()} & VM_BOOKKEEPING_EVENTS
    assert kept == set(), f"still retaining {kept}"
    assert vm.function_calls > 0, "the aggregate counter went dark with the events"
    return f"0 retained, {vm.function_calls} calls still counted"


# --------------------------------------------------------------------- prose


@probe("prose: no artifact still says the fold policies are unavailable")
def probe_no_stale_fold_claim(repo: Path):
    """The 5.1.0 lesson, applied to this release's moving vocabulary.

    `STATE_MERGE_POLICIES` changed three times across this cycle -- (any, once),
    then + sum/append, then + union -- and prose written at each step described
    the set as it stood. Anything still saying a fold is refused is now false.
    """
    stale = re.compile(STALE_FOLD_CLAIM, re.IGNORECASE)
    hits = []
    for path in [
        repo / "README.md",
        repo / "llms.txt",
        repo / "llms-full.txt",
        *sorted((repo / "docs" / "guide").glob("*.md")),
        *sorted((repo / "docs" / "runtime").glob("*.md")),
    ]:
        if not path.is_file():
            continue
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if stale.search(line):
                hits.append(f"{path.relative_to(repo).as_posix()}:{number}")
    assert not hits, f"stale fold claims: {hits}"
    return "checked README, llms*.txt, guide, runtime docs"


@probe("prose: the documented policy vocabulary matches the runtime's")
def probe_policy_vocabulary(repo: Path):
    from nodus.orchestration.workflow_state import STATE_MERGE_POLICIES

    guide = (repo / "docs" / "guide" / "workflows-and-tasks.md").read_text(
        encoding="utf-8"
    )
    for policy in STATE_MERGE_POLICIES:
        assert f'"{policy}"' in guide, f"the guide never mentions merge: {policy!r}"
    return f"all {len(STATE_MERGE_POLICIES)} policies documented"


@probe("selfcheck: the stale-claim pattern is falsifiable both ways")
def probe_pattern_selfcheck():
    """A prose probe that cannot fail is worse than no prose probe.

    Checks the pattern against sentences it must catch *and* sentences it must
    not, because tightening it after a false positive is exactly when it
    silently stops catching anything.
    """
    stale = re.compile(STALE_FOLD_CLAIM, re.IGNORECASE)
    missed = [s for s in _STALE_EXAMPLES if not stale.search(s)]
    assert not missed, f"pattern no longer catches: {missed}"
    wrong = [s for s in _LIVE_EXAMPLES if stale.search(s)]
    assert not wrong, f"pattern flags correct prose: {wrong}"
    return f"{len(_STALE_EXAMPLES)} caught, {len(_LIVE_EXAMPLES)} left alone"


@probe("prose: every new command appears in the global help")
def probe_new_commands_listed():
    _code, help_text = cli(["nodus", "--help"])
    for command in ("doctor", "completion", "graph"):
        assert command in help_text, f"{command} missing from nodus --help"
    return "doctor, completion, graph listed"


# -------------------------------------------------------- 5.3.0: declarations
# Every surface below accepted something that read as a decision and enforced
# none of it. Each probe exercises the claim the release makes about one.


@probe("5.3.0: a deny-everything policy reaches tool/syscall/agent/memory")
def probe_policy_sees_authority():
    from nodus.runtime.capability import (
        AGENT_CALL, ALL_CAPABILITIES, MEMORY_READ, MEMORY_WRITE, SYSCALL,
        TOOL_INVOKE, CapabilityDecision, CapabilityPolicy, DenyList,
    )
    from nodus.runtime.embedding import NodusRuntime

    for name in (TOOL_INVOKE, SYSCALL, AGENT_CALL, MEMORY_READ, MEMORY_WRITE):
        assert name in ALL_CAPABILITIES, f"{name} missing from ALL_CAPABILITIES"
        DenyList(name)  # raised `unknown capability` through 5.2.0

    seen: list[str] = []

    class DenyAll(CapabilityPolicy):
        def check(self, request):
            seen.append(request.capability)
            return CapabilityDecision.deny("probe")

    result = NodusRuntime(timeout_ms=None, capability_policy=DenyAll()).run_source(
        'fn main() { memory_put("k", "leaked") print("REACHED") }'
    )
    assert "REACHED" not in (result.get("stdout") or ""), "the write was not stopped"
    assert result["error"]["kind"] == "sandbox", result["error"]
    assert MEMORY_WRITE in seen, f"policy saw {seen}"
    return f"{len(ALL_CAPABILITIES)} capabilities; memory_put denied as {MEMORY_WRITE}"


@probe("5.3.0: every builtin is classified as bearing authority or not")
def probe_classification_total():
    from nodus.builtins.nodus_builtins import BUILTIN_NAMES
    from nodus.runtime.capability import BUILTIN_CAPABILITIES, NO_AUTHORITY_BUILTIN_NAMES

    unclassified = set(BUILTIN_NAMES) - set(BUILTIN_CAPABILITIES) - set(NO_AUTHORITY_BUILTIN_NAMES)
    assert not unclassified, f"unclassified: {sorted(unclassified)}"
    overlap = set(BUILTIN_CAPABILITIES) & set(NO_AUTHORITY_BUILTIN_NAMES)
    assert not overlap, f"classified both ways: {sorted(overlap)}"
    return f"{len(BUILTIN_NAMES)} builtins = {len(BUILTIN_CAPABILITIES)} governed + {len(NO_AUTHORITY_BUILTIN_NAMES)} not"


@probe("5.3.0: a syscall's declared capability is enforced")
def probe_syscall_capability():
    from nodus.runtime.capability import MEMORY_WRITE, CapabilityDecision, CapabilityPolicy
    from nodus.runtime.embedding import NodusRuntime
    from nodus.services.syscall_runtime import list_syscalls

    class DenyWrites(CapabilityPolicy):
        def check(self, request):
            if request.capability == MEMORY_WRITE:
                return CapabilityDecision.deny("probe")
            return None

    result = NodusRuntime(timeout_ms=None, capability_policy=DenyWrites()).run_source(
        'fn main() { let w = syscall("sys.v1.memory.put", {"key": "k", "value": "v"})'
        ' print("REACHED") }'
    )
    assert "REACHED" not in (result.get("stdout") or ""), "the syscall ran anyway"
    assert result["error"]["kind"] == "sandbox", result["error"]
    published = {spec["full_name"]: spec["capability"] for spec in list_syscalls()}
    assert published["sys.v1.memory.put"] == MEMORY_WRITE, published
    return "sys.v1.memory.put refused by a policy denying memory.write"


@probe("5.3.0: writable_paths splits read-only context from editable files")
def probe_writable_paths():
    import os
    import tempfile

    from nodus.runtime.embedding import NodusRuntime

    with tempfile.TemporaryDirectory() as raw:
        root = os.path.realpath(raw)
        os.makedirs(os.path.join(root, "ctx"))
        os.makedirs(os.path.join(root, "src"))
        with open(os.path.join(root, "ctx", "readme.txt"), "w") as handle:
            handle.write("hi")
        cwd = os.getcwd()
        os.chdir(root)
        try:
            result = NodusRuntime(
                timeout_ms=None,
                allowed_paths=[root],
                writable_paths=[os.path.join(root, "src")],
            ).run_source(
                'fn main() {\n'
                '    print("read=\\(len(read_file("ctx/readme.txt")))")\n'
                '    write_file("src/out.txt", "ok")\n'
                '    print("wrote-src")\n'
                '    write_file("ctx/out.txt", "no")\n'
                '    print("WROTE-CTX")\n'
                '}'
            )
        finally:
            os.chdir(cwd)
    out = result.get("stdout") or ""
    assert "read=2" in out, out
    assert "wrote-src" in out, out
    assert "WROTE-CTX" not in out, "wrote into read-only context"
    assert "readable but not writable" in result["error"]["message"], result["error"]
    return "readable context, editable subtree, refusal names the reason"


@probe("5.3.0: nodus.toml refuses what it does not read, and entry binds")
def probe_manifest():
    import os
    import tempfile

    from nodus.tooling.project import ManifestError, load_project, project_entry_path

    with tempfile.TemporaryDirectory() as root:
        manifest = os.path.join(root, "nodus.toml")
        with open(manifest, "w", newline="\n") as handle:
            handle.write('[project]\nname = "x"\nentry = "workflows/boot.nd"\n')
        try:
            load_project(root)
            raise AssertionError("[project] was accepted")
        except ManifestError as exc:
            assert "did you mean [package]?" in str(exc), str(exc)

        with open(manifest, "w", newline="\n") as handle:
            handle.write('[package]\nname = "x"\nentry = "workflows/boot.nd"\n')
        entry = project_entry_path(load_project(root))
        assert entry.endswith(os.path.join("workflows", "boot.nd")), entry
    return "[project] refused with the fix named; entry selects the file"


@probe("5.3.0: an unhonoured worker: declaration warns")
def probe_worker_warns():
    result = run_nd(
        'workflow w { step s with { worker: "hardened-sandbox" } { return 1i } }\n'
        "fn main() { let r = run_workflow(w) }"
    )
    stderr = result.get("stderr") or ""
    assert "no worker dispatcher is registered" in stderr, repr(stderr)
    assert "6.0.0" in stderr, "the flag day is not announced"
    assert "worker_dispatcher=" in stderr, "the embedded remedy is not named"
    return "warns, names both remedies, announces the flag day"


@probe("5.3.0: a conditional edge is marked in the plan and drawn")
def probe_conditional_edges(repo: Path):
    from nodus.orchestration.graph_render import to_dot, to_mermaid
    from nodus.runtime.embedding import NodusRuntime

    runtime = NodusRuntime(timeout_ms=None)
    result = runtime.run_source(
        'workflow d {\n'
        '    step build { checkpoint "flaky" return "ok" }\n'
        '    step notify after build with { on: ["failed"] } { return "a" }\n'
        '    step verify after build when reached("flaky") { return "c" }\n'
        '    step done after build { return "f" }\n'
        '}\n'
        "let p = plan_workflow(d)\n"
    )
    assert result.get("ok"), result.get("errors")
    plan = runtime.active_vm().last_graph_plan
    assert plan["conditional_edges"] == [["build", "verify"]], plan["conditional_edges"]
    assert plan["edge_conditions"] == {"build->notify": ["failed"]}, plan["edge_conditions"]
    mermaid, dot = to_mermaid(plan), to_dot(plan)
    assert "|failed|" in mermaid and "-.->" in mermaid, mermaid
    assert '[label="failed"]' in dot and "[style=dashed]" in dot, dot
    return "on: labels the edge, when dashes it, in both formats"


@probe("5.3.0: a step guard error names `when`, not goal `until`")
def probe_guard_error():
    result = run_nd(
        "workflow w { step a { return 1i } "
        "step b after a when (a < 5i) { return 2i } }\nfn main() { }"
    )
    assert not result.get("ok"), "the data predicate parsed"
    message = result["errors"][0]["message"]
    assert "step guard `when`" in message, message
    assert "goal `until`" not in message, message
    assert "checkpoint" in message, "the error names no way forward"
    return "names its own clause and points at the idiom that works"


@probe("5.3.0: prose does not still describe the pre-5.3.0 capability surface")
def probe_no_stale_capability_claim(repo: Path):
    """The half that has caught things: artifacts describing the old vocabulary.

    Two claims went stale this cycle -- that the capability set is five names,
    and that the embedder runbook's `allow_*` switches "default to permissive"
    (backwards since 5.0.0, and fixed in this release).
    """
    from nodus.runtime.capability import ALL_CAPABILITIES

    stale = re.compile(
        r"allow_\*[^.\n]{0,60}default to permissive"
        r"|`?allowed_paths`?[^.\n]{0,40}(single flat list|no read-vs-write)"
        r"|FS_READ[^.\n]{0,50}(never used|attached to nothing|declared and never)"
        r"|`?SyscallSpec\.capability`?[^.\n]{0,60}(enforced nowhere|never enforced)",
        re.IGNORECASE,
    )
    hits: list[str] = []
    for path in sorted(repo.glob("docs/**/*.md")) + sorted(repo.glob("*.md")) + [
        repo / "llms.txt", repo / "llms-full.txt"
    ]:
        if not path.is_file():
            continue
        if _is_a_record_of_what_was(path):
            continue
        for number, line in enumerate(path.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
            if stale.search(line):
                hits.append(f"{path.relative_to(repo)}:{number}: {line.strip()[:90]}")
    assert not hits, "prose describes the pre-5.3.0 surface:\n       " + "\n       ".join(hits)
    return f"no artifact still describes the {len(ALL_CAPABILITIES) - 5}-name-smaller vocabulary"


def _is_a_record_of_what_was(path: Path) -> bool:
    """Is this artifact a pinned record rather than a live description?

    Evals, design docs and the CHANGELOG describe what *was* -- that is their
    job, so a stale-sounding sentence in them is correct. Two more belong in
    that class and were found by this probe rather than reasoned about:

    * `EXTERNAL_AUDIT_LEDGER.md` records what an outside audit claimed **at a
      named commit** ("Audited at commit 3376702, v4.1.1"), with the issue
      number beside it. The claim was true then and the issue says what
      happened since.
    * `Session Handoff Summary.md` is untracked working scratch, not a shipped
      artifact -- it is not in git and never reaches a user.

    Exemptions weaken the probe, so each one is named and argued rather than
    globbed.
    """
    parts = path.parts
    if "evals" in parts or "design" in parts:
        return True
    return path.name in {
        "CHANGELOG.md",
        "EXTERNAL_AUDIT_LEDGER.md",
        "Session Handoff Summary.md",
    }


# ------------------------------------------------- 5.4.0: resume, inspect, say
#
# The release's three claims, probed as claims: a resume that tells the truth,
# an inspection that costs nothing, and three things that could not be said.


@probe("5.4.0: a tolerated failure completes the run and is reported separately")
def probe_allow_failure():
    result = run_nd(
        "workflow w {\n"
        '    step flaky with { allow_failure: true } { throw "boom" }\n'
        "    step solid { return 1i }\n"
        "}\n"
        "fn main() { let r = run_workflow(w); print(\"R=\\(r)\") }"
    )
    assert result.get("ok"), result.get("error")
    out = result["stdout"]
    assert '"failed": []' in out, out[:200]
    assert '"tolerated": ["flaky"]' in out, out[:200]
    assert '"flaky": "failed"' in out, "the status stopped telling the truth"
    return "run completes; status still `failed`; verdict says `tolerated`"


@probe("5.4.0: try/finally needs no catch, and the error still propagates")
def probe_try_finally():
    ok = run_nd(
        'fn main() { try { print("W") } finally { print("C") } }'
    )
    assert ok.get("ok"), ok.get("error")
    assert "W" in ok["stdout"] and "C" in ok["stdout"], ok["stdout"]
    raised = run_nd('fn main() { try { throw "boom" } finally { print("C") } }')
    assert not raised.get("ok"), "the rethrow was swallowed"
    assert "C" in raised["stdout"], "finally did not run on the throwing path"
    bare = run_nd("fn main() { try { print(1i) } }")
    assert not bare.get("ok"), "a try with neither clause was accepted"
    return "cleanup form runs, rethrows, and a bare `try` is still refused"


@probe("5.4.0: a bounded channel makes a fast producer wait")
def probe_channel_backpressure():
    result = run_nd(
        "fn main() {\n"
        "    let ch = channel(1i)\n"
        '    let p = coroutine(fn() { send(ch, "a"); print("sent a"); '
        'send(ch, "b"); print("sent b"); close(ch) })\n'
        '    let c = coroutine(fn() { let x = recv(ch); print("got \\(x)"); '
        'let y = recv(ch); print("got \\(y)") })\n'
        "    spawn(p)\n    spawn(c)\n    run_loop()\n"
        "}"
    )
    assert result.get("ok"), result.get("error")
    out = result["stdout"]
    assert out.index("got a") < out.index("sent b"), (
        "the second send did not wait for a free slot:\n" + out
    )
    deadlocked = run_nd(
        "fn main() {\n"
        "    let ch = channel(1i)\n"
        '    let p = coroutine(fn() { send(ch, "a"); send(ch, "b") })\n'
        "    spawn(p)\n    run_loop()\n"
        "}"
    )
    assert not deadlocked.get("ok"), "a parked sender with no receiver completed"
    assert "blocked on send()" in str(deadlocked), str(deadlocked)[:200]
    return "send blocks until recv frees a slot; a stuck sender is a named deadlock"


@probe("5.4.0: `nodus graph` plans without executing the file")
def probe_graph_does_not_execute(repo: Path):
    import tempfile

    with tempfile.TemporaryDirectory() as td:
        script = Path(td) / "probe.nd"
        probe_file = Path(td) / "executed.txt"
        script.write_text(
            'import "std:fs" as fs\n'
            f'fs.write("{probe_file.as_posix()}", "ran")\n'
            "workflow w { step a { return 1i } step b after a { return 2i } }\n"
            "let r = run_workflow(w)\n",
            encoding="utf-8",
        )
        code, out = cli(["nodus", "graph", str(script), "--allow-paths", td])
        assert code == 0, f"static plan failed: {out[:200]}"
        assert '"nodes": ["a", "b"]' in out, out[:200]
        assert not probe_file.exists(), "inspecting the file executed it"
        code, out = cli(["nodus", "graph", "show", str(script)])
        assert code == 0 and "flowchart TD" in out, out[:200]
        assert not probe_file.exists(), "graph show executed the file"
    return "plan and diagram produced; the file's side effect never happened"


@probe("5.4.0: a resume refuses a graph whose shape has drifted")
def probe_topology_validation():
    """Behaviour, not prose. An earlier cut of this probe asserted that
    "Dependency cycle" did not appear in the validator's *source* -- and failed,
    because the docstring explains the false diagnosis it exists to prevent.
    A probe that flags correct prose gets switched off; assert on the raise."""
    from nodus.orchestration.task_graph import TaskGraph, TaskNode, WorkflowRebuildError
    from nodus.orchestration.workflow_lowering import graph_topology
    from nodus.vm.vm import VM

    a = TaskNode(task_id="task_1", function=None, step_name="a")
    b = TaskNode(task_id="task_2", function=None, step_name="b", dependencies=[a])
    topology = graph_topology([a, b])
    assert topology == {"steps": ["a", "b"], "edges": [["a", "b"]]}, topology

    graph = TaskGraph([a, b], metadata={})
    vm = VM([], {}, code_locs=[])
    drifted = {"workflow_topology": {"steps": ["a"], "edges": []}}
    try:
        vm._validate_rebuilt_topology(graph, drifted, "w", "workflow", "g_probe")
    except WorkflowRebuildError as err:
        message = str(err)
        assert "planned against a different version" in message, message
        assert "steps added: b" in message, message
        assert "Dependency cycle" not in message, "the false diagnosis is back"
    else:
        raise AssertionError("a drifted topology was accepted")

    vm._validate_rebuilt_topology(graph, {"workflow_topology": topology}, "w", "workflow", "g_probe")
    return "matching shape passes; a drifted one names the real cause, not a cycle"


@probe("5.4.0: a checkpoint resume of a waiting run is refused")
def probe_waiting_resume_refused():
    from nodus_lang_workflow import runner as runner_module

    source = inspect_source(runner_module.WorkflowFrameworkRunner.resume_workflow)
    assert "waiting_run_checkpoint_resume" in source, "the refusal is gone"
    assert "discards the payload" in source, "the payload-eating case is unguarded"
    assert 'state.get("status") == "waiting"' in source, (
        "the refusal no longer consults the persisted state, so a stale "
        "administrative wait would be refused"
    )
    return "refused on genuinely-waiting runs only, both argument shapes"


@probe("5.4.0: a persist failure names the cell, and durable:false protects it")
def probe_persist_naming():
    named = run_nd(
        "workflow nocp {\n"
        "    state ch = 0i\n"
        "    step a { ch = channel(); return 1i }\n"
        "}\n"
        "fn main() { let r = run_workflow(nocp) }"
    )
    assert not named.get("ok"), "a live handle persisted"
    text = str(named)
    assert "state cell 'ch'" in text, text[:300]
    assert "durable: false" in text, "the error names no remedy"
    live = run_nd(
        "workflow live {\n"
        "    state ch = 0i with { durable: false }\n"
        '    step a { ch = channel(); checkpoint "cp"; return 1i }\n'
        "}\n"
        'fn main() { let r = run_workflow(live); let f = r["failed"]; print("F=\\(f)") }'
    )
    assert live.get("ok"), f"durable:false did not protect the value: {live.get('error')}"
    assert "F=[]" in live["stdout"], live["stdout"]
    return "the cell is named; `durable: false` survives a mid-step checkpoint"


@probe("5.4.0: a goal whose every checkpoint is conditional is refused")
def probe_goal_waypoint():
    result = run_nd(
        "workflow tune {\n"
        "    state tries = 0\n"
        "    step look { tries = tries + 1; let s = workflow_state(); "
        'if (s["tries"] >= 3) { checkpoint "good_enough" } return s["tries"] }\n'
        "}\n"
        "goal reach over tune {\n"
        '    until reached("good_enough")\n'
        "    budget { max_iterations: 5, deadline_ms: 30000 }\n"
        "}\n"
        "fn main() { let r = run_goal(reach) }"
    )
    assert not result.get("ok"), "the non-iterating goal compiled"
    text = str(result)
    assert "cannot iterate" in text, text[:300]
    assert "runs on every pass" in text, "the error names no fix"
    return "refused at compile time, naming the waypoint remedy"


@probe("5.4.0: `nodus check` enters workflow step bodies")
def probe_check_enters_steps():
    from nodus.tooling.runner import check_source

    bad = check_source(
        "fn greet(name: string, times: int) -> string { return name }\n"
        'workflow w { step a { return greet(42i, "no") } }\n',
        filename="<probe>",
    )
    assert not bad["ok"], "a typed violation inside a step still passes check"
    assert "expected string but got int" in str(bad), str(bad)[:200]
    host = check_source(
        "workflow w { step a { return maybe_a_host_function(1i) } }\n",
        filename="<probe>",
    )
    assert host["ok"], (
        "unknown free names are now rejected -- that is #489's decision to make, "
        "and taking it here breaks every embedded program"
    )
    return "step bodies type-checked; unknown host-shaped calls still permitted"


#: Sentences that were TRUE before 5.4.0 and are false now.
#:
#: One constant, not one per caller. It was written out twice -- once in the
#: probe and once in the self-check that is supposed to hold the probe honest --
#: so the self-check validated a *copy*, and tightening either one would have
#: silently left the other unchanged. That is the shape this codebase catalogues,
#: sitting inside a detector for it.
#:
#: The `nodus graph` clause carries a negation guard. Without it the pattern
#: fired on **"`nodus graph` no longer executes the file it inspects"** -- a
#: correct historical row in CLAUDE.md's "what stopped working" table, added
#: 2026-08-29, after 5.7.1's Gate 10b had already run 72/72. The words between
#: the subject and the verb are invisible to a regex, exactly as `not` is
#: invisible to GitHub's closes-parser. A probe that cries wolf on true prose
#: gets switched off, so the guard is the fix rather than an exemption for the
#: one file -- that table gains a row every release.
STALE_5_4_CLAIM = re.compile(
    r"`?finally`?[^.\n]{0,40}requires[^.\n]{0,20}`?catch`?"
    r"|try/finally[^.\n]{0,40}(alone is a syntax error|is a syntax error)"
    r"|(channels?|send)[^.\n]{0,60}(no backpressure|raises? instead of block)"
    r"|`?waiting_senders`?[^.\n]{0,40}(dead code|never read)"
    r"|`?nodus graph`?(?![^.\n]{0,50}(no longer|does not|doesn't|never|stopped|instead of))"
    r"[^.\n]{0,50}(executes the file|runs the file)"
    r"|(analyzer|check)[^.\n]{0,60}never enters[^.\n]{0,30}step bodies"
    r"|`?STEP_OPTION_KEYS`?[^.\n]{0,40}(is seven|seven entries)"
    r"|does not check[^.\n]{0,60}undefined variable",
    re.IGNORECASE,
)


@probe("5.4.0: prose does not still describe the pre-5.4.0 surface")
def probe_no_stale_5_4_claims(repo: Path):
    """The half that has caught something every cycle.

    Each pattern is a sentence that was TRUE before this release and is false
    now. Evals, design docs and the CHANGELOG are exempt: recording what was is
    their job.
    """
    stale = STALE_5_4_CLAIM
    hits: list[str] = []
    for path in sorted(repo.glob("docs/**/*.md")) + sorted(repo.glob("*.md")) + [
        repo / "llms.txt", repo / "llms-full.txt"
    ]:
        if not path.is_file():
            continue
        if _is_a_record_of_what_was(path):
            continue
        for number, line in enumerate(
            path.read_text(encoding="utf-8", errors="replace").splitlines(), 1
        ):
            if stale.search(line):
                hits.append(f"{path.relative_to(repo)}:{number}: {line.strip()[:90]}")
    assert not hits, "prose describes the pre-5.4.0 surface:\n       " + "\n       ".join(hits)
    return "no artifact still states a restriction this release removed"


@probe("5.4.0: the stale-claim pattern still catches its own examples")
def probe_5_4_pattern_selfcheck():
    """A prose probe that cannot fail is worse than none (the lesson from the
    vacuous boundary test at 5.3.0). Hold the pattern to both directions."""
    must_catch = [
        "`finally` requires `catch` — `try/catch/finally` is the only form",
        "try/finally alone is a syntax error",
        "Channels have no backpressure: send on a full channel raises",
        "`waiting_senders` is dead code and never read",
        "`nodus graph` executes the file it is asked to inspect",
        "the analyzer never enters workflow step bodies at all",
        "Does not check undefined variable/function references",
    ]
    must_ignore = [
        "`try { } finally { }` works without a catch",
        "a bounded channel blocks the sender until a slot frees",
        "`nodus graph` plans without executing the file",
        # The rows that made the negation guard necessary. A regex cannot
        # see a negation: the true sentence and the stale one differ only by
        # two words it steps straight over.
        "| 5.4.0 | `nodus graph` no longer executes the file it inspects (#400) |",
        "`nodus graph` does not execute the file it is asked to inspect",
        "`nodus check` now enters workflow step bodies",
        "STEP_OPTION_KEYS gained an eighth entry, allow_failure",
    ]
    pattern = STALE_5_4_CLAIM
    missed = [s for s in must_catch if not pattern.search(s)]
    assert not missed, f"pattern stopped catching: {missed}"
    false_positives = [s for s in must_ignore if pattern.search(s)]
    assert not false_positives, f"pattern cries wolf on: {false_positives}"
    return f"{len(must_catch)} stale forms caught, {len(must_ignore)} true sentences ignored"


def inspect_source(obj) -> str:
    import inspect as _inspect

    return _inspect.getsource(obj)


# ---------------------------------------------------------------------------
# 5.5.0
# ---------------------------------------------------------------------------


@probe("5.5.0: a step body cannot be called directly")
def probe_step_entry_guard():
    result = run_nd(
        "workflow build {\n"
        '    step lint { return "linted" }\n'
        '    step test after lint { return "tested" }\n'
        "}\n"
        'fn main() { print(build["steps"][1]["fn"](nil)) }'
    )
    assert not result.get("ok"), "a step body was still callable out of order"
    message = str(result.get("error", {}).get("message", ""))
    assert "build.test" in message, message
    assert "cannot be called directly" in message, message
    routed = run_nd(
        "workflow build {\n"
        '    step lint { return "linted" }\n'
        '    step test after lint { return "tested" }\n'
        "}\n"
        'fn main() { let r = run_workflow(build); print("R=\\(r["steps"])") }'
    )
    assert routed.get("ok"), "the routed path broke: " + str(routed.get("error"))
    assert "linted" in routed["stdout"] and "tested" in routed["stdout"], routed["stdout"]
    return "direct call refused by name; the routed run still executes both steps"


@probe("5.5.0: the flow value's shape is unchanged")
def probe_flow_shape_intact():
    """The fix must break the bypass and nothing else -- `keys(build)` still reads."""
    result = run_nd(
        "workflow build { step a { return 1i } }\n"
        'fn main() { print("K=\\(keys(build))"); print("N=\\(len(build["steps"]))") }'
    )
    assert result.get("ok"), result.get("error")
    assert "__workflow__" in result["stdout"], result["stdout"]
    assert "N=1" in result["stdout"], result["stdout"]
    return "keys() and steps[] still read; only entry is refused"


@probe("5.5.0: NODUS_RUN_STATE_ROOT moves both halves of a run")
def probe_run_state_root():
    import subprocess
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp) / "work"
        work.mkdir()
        state = Path(tmp) / "state"
        (work / "wf.nd").write_text(
            "workflow demo { step a { return 1i } }\n"
            "let r = run_workflow(demo)\n"
            'print("ok=\\(r["failed"])")\n',
            encoding="utf-8",
        )
        env = {**os.environ, "NODUS_RUN_STATE_ROOT": str(state)}
        proc = subprocess.run(
            [sys.executable, "-m", "nodus", "run", "wf.nd"],
            cwd=str(work), capture_output=True, text=True, env=env, timeout=120,
        )
        assert proc.returncode == 0, proc.stderr[-400:]
        graphs = list((state / "graphs").glob("*.json")) if (state / "graphs").is_dir() else []
        runs_dir = state / "workflow_framework" / "runs"
        records = list(runs_dir.glob("*.json")) if runs_dir.is_dir() else []
        assert graphs, "the graph half did not follow the root"
        assert records, "the record half did not follow the root"
        assert not (work / ".nodus" / "graphs").exists(), "graphs stayed in the CWD"
    return "graph state and run record both land under the one variable"


@probe("5.5.0: the capability floor follows relocated state")
def probe_floor_follows_state():
    import tempfile

    from nodus.runtime.state_paths import RUN_STATE_ROOT_ENV, is_inside_run_state

    saved = os.environ.get(RUN_STATE_ROOT_ENV)
    try:
        with tempfile.TemporaryDirectory() as tmp:
            os.environ[RUN_STATE_ROOT_ENV] = tmp
            inside, _root = is_inside_run_state(os.path.join(tmp, "graphs", "g.json"))
            assert inside, "a guest could write into relocated run state"
            outside, _ = is_inside_run_state(os.path.join(tmp, "..", "ordinary.txt"))
            assert not outside, "the floor is denying ordinary writes"
    finally:
        if saved is None:
            os.environ.pop(RUN_STATE_ROOT_ENV, None)
        else:
            os.environ[RUN_STATE_ROOT_ENV] = saved
    return "relocated state is covered; an ordinary path is not"


@probe("5.5.0: nodus docs points at this version, from the install")
def probe_nodus_docs():
    from nodus.cli.docs import bundled_llms_txt, report
    from nodus.support.version import __version__

    bundled = bundled_llms_txt()
    assert bundled is not None, "llms.txt is not bundled, so an install has no index"
    assert Path(bundled).is_file(), bundled
    data = report()
    assert data["version"] == __version__, data["version"]
    web = [e for e in data["entries"] if not e["local"]]
    assert web, "every entry claims to be local, which cannot be right"
    for entry in web:
        assert f"/blob/v{__version__}/" in entry["where"], entry["where"]
        assert "/blob/main/" not in entry["where"], (
            "a docs link points at main; an agent on an older release would read "
            "the wrong guide, which is how the shipped skill went stale"
        )
    return f"{len(data['entries'])} entries, links pinned to v{__version__}"


@probe("5.5.0: the editor and the runtime resolve an import identically")
def probe_one_resolver():
    import tempfile

    from nodus.runtime import module_loader as runtime_loader
    from nodus.tooling import loader as tooling_loader

    assert tooling_loader.resolve_import_path is runtime_loader.resolve_import_path, (
        "the import resolvers are two objects again"
    )
    with tempfile.TemporaryDirectory() as base:
        try:
            tooling_loader.resolve_import_path(
                "std:channel", base, {"project_root": base}, None, "t.nd"
            )
        except AssertionError:
            raise
        except Exception as exc:
            assert "built-in" in str(exc), (
                "the editor lost the specific built-ins-are-not-a-module message: "
                + str(exc)[:120]
            )
        else:
            raise AssertionError("std:channel resolved as a module")
    return "same object, and the specific std:channel message survives"


@probe("5.5.0: the LSP indexes step bodies")
def probe_lsp_indexes_steps():
    from nodus.frontend.lexer import tokenize
    from nodus.frontend.parser import Parser
    from nodus.lsp import server as lsp

    source = (
        "workflow build {\n"
        "    step lint { let inside_step = 42i return inside_step }\n"
        "}\n"
    )
    tokens = tokenize(source)
    parsed = Parser(tokens).parse()
    stmts = parsed if isinstance(parsed, list) else getattr(parsed, "stmts", parsed)
    indexer = lsp._DocumentIndexer(server=None, path="d.nd", uri="file:///d.nd",
                                   text=source, tokens=tokens, ast=stmts)
    indexer.build()
    names = {d.name for d in indexer.definitions}
    assert "inside_step" in names, sorted(names)
    return "a step-body local is indexed, so hover and go-to-definition work there"


@probe("5.5.0: diagnostics do not flag a destructured name as undefined")
def probe_no_false_undefined():
    import tempfile

    from nodus.tooling.diagnostics import WorkspaceDiagnosticEngine

    def undefined(src):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "t.nd")
            with io.open(path, "w", encoding="utf-8") as handle:
                handle.write(src)
            result = WorkspaceDiagnosticEngine(project_root=tmp).analyze(path, source=src)
            return [d.message for ds in (result.diagnostics_by_file or {}).values()
                    for d in ds if d.message.startswith("Undefined")]

    control = undefined("let a = undefined_name\nprint(a)\n")
    assert control, "the analyzer reports nothing at all, so the silence below is vacuous"
    assert [] == undefined("let [alpha, beta] = [1i, 2i]\nprint(alpha)\nprint(beta)\n"), (
        "a correctly destructured name is still reported as undefined"
    )
    assert undefined('print("v=\\(undefined_name)")\n'), (
        "a typo in a string interpolation is still accepted in silence"
    )
    return "no false positive on destructuring; interpolation typos now caught"


@probe("5.5.0: no artifact still describes 5.4.0 as current")
def probe_no_stale_5_4_current(repo: Path):
    """The half that has caught something every cycle it has run."""
    from nodus.support.version import __version__

    offenders = []
    for rel in ("README.md", "llms.txt", "llms-full.txt", "CLAUDE.md",
                "skills/nodus.skill", "skills/project-CLAUDE.md",
                "skills/project-AGENTS.md",
                "docs/governance/ECOSYSTEM_READINESS_ASSESSMENT.md"):
        path = repo / rel
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        for lineno, line in enumerate(text.splitlines(), 1):
            if "5.4.0" not in line:
                continue
            lowered = line.lower()
            if any(marker in lowered for marker in
                   ("current", "is at", "live on pypi", "package version is",
                    'version: "', "nodus-lang 5.4.0")):
                offenders.append(f"{rel}:{lineno}: {line.strip()[:90]}")
    assert not offenders, (
        f"artifact(s) still call 5.4.0 current while shipping {__version__}:\n  "
        + "\n  ".join(offenders)
    )
    return "8 artifacts checked; none calls 5.4.0 current"


@probe("5.5.0: the shipped skill no longer teaches the removed timeout trap")
def probe_skill_is_current(repo: Path):
    from nodus.runtime.embedding import NodusRuntime
    from nodus.support.version import __version__

    skill = (repo / "skills" / "nodus.skill").read_text(encoding="utf-8", errors="replace")
    assert 'version: "%s"' % __version__ in skill, "the skill's frontmatter version is stale"

    # The claim the skill used to make, checked against the runtime rather than
    # against memory.
    assert NodusRuntime().timeout_ms is None, (
        "NodusRuntime has a default deadline again; the skill's advice needs revisiting"
    )
    assert "Default is `timeout_ms=200`" not in skill, (
        "the skill still teaches a 200ms default that does not exist"
    )
    for flag in ("allow_subprocess", "allow_network", "allow_env"):
        assert flag in skill, (
            "the skill says nothing about %s, the breaking change of the 5.x line" % flag
        )
    return "version matches, the removed trap is gone, deny-by-default is covered"


@probe("5.5.0: README has no relative links")
def probe_readme_absolute(repo: Path):
    """PyPI strips them, and the long description is immutable per release."""
    import re

    text = (repo / "README.md").read_text(encoding="utf-8", errors="replace")
    targets = re.findall(r"\]\(([^)]+)\)", text)
    relative = [t for t in targets
                if not t.startswith(("http://", "https://", "#", "mailto:"))]
    assert not relative, "relative link(s) PyPI will drop: %s" % relative[:5]
    for needle in ("llms.txt", "nodus.skill"):
        assert needle in text, "the README no longer mentions %s" % needle
    return "%d links, all absolute" % len(targets)


@probe("5.5.0: TECH_DEBT does not list this release's fixes as open debt")
def probe_debt_register_current(repo: Path):
    """The 5.4.0 cycle shipped with #400/#401/#402 still listed as open."""
    text = (repo / "docs" / "governance" / "TECH_DEBT.md").read_text(
        encoding="utf-8", errors="replace")
    fixed = ("#394", "#584", "#585", "#596", "#597", "#598", "#602", "#605")
    stale = []
    for issue in fixed:
        for line in text.splitlines():
            if line.strip().startswith("- **%s " % issue) and "RESOLVED" not in line:
                stale.append(line.strip()[:90])
    assert not stale, "TECH_DEBT still calls these open:\n  " + "\n  ".join(stale)
    return "%d fixed issues, none still listed as open debt" % len(fixed)


# ------------------------------------------------------- 5.6.0: the DSL cluster


@probe("5.6.0: a step maps over a list, and stays one step")
def probe_each_fanout():
    r = run_nd(
        'workflow w {\n'
        '    step plan { return ["a", "b", "c"] }\n'
        '    step process each item in plan { return "did \\(item)" }\n'
        '    step collect after process { return len(process) }\n'
        '}\n'
        'fn main() {\n'
        '    let r = run_workflow(w)\n'
        '    print(r["steps"]["process"])\n'
        '    print(r["steps"]["collect"])\n'
        '    print(r["statuses"]["process"])\n'
        '}\n'
    )
    assert r["ok"], r.get("error")
    lines = r["stdout"].strip().splitlines()
    assert '["did a", "did b", "did c"]' in lines[-3], lines
    assert lines[-2] == "3", "the join must receive the list, not one item: " + str(lines)
    # One step, not three: `statuses` names it once, and as itself.
    assert lines[-1] == "completed", lines
    return "fan-out runs per item; the join receives the list"


@probe("5.6.0: an empty producer skips, an unmappable one fails")
def probe_each_edges():
    empty = run_nd(
        'workflow w {\n'
        '    step plan { return [] }\n'
        '    step process each item in plan { return item }\n'
        '}\n'
        'fn main() { let r = run_workflow(w)\n'
        '    print(r["statuses"]["process"]); print(r["steps"]["process"]) }\n'
    )
    assert empty["ok"], empty.get("error")
    lines = empty["stdout"].strip().splitlines()
    assert lines[-2] == "skipped", lines
    assert lines[-1] == "[]", lines

    bad = run_nd(
        'workflow w {\n'
        '    step plan { return nil }\n'
        '    step process each item in plan { return item }\n'
        '}\n'
        'fn main() { let r = run_workflow(w)\n'
        '    print(r["statuses"]["process"]); print(r["error"]) }\n'
    )
    assert bad["ok"], bad.get("error")
    blines = bad["stdout"].strip().splitlines()
    assert blines[-2] == "failed", blines
    assert "'plan'" in blines[-1], blines[-1]
    assert "NoneType" not in blines[-1], "leaks a Python type name: " + blines[-1]
    return "empty -> skipped; unmappable -> failed, naming the producer"


@probe("5.6.0: workflows and goals take parameters")
def probe_workflow_parameters():
    r = run_nd(
        'workflow build(mode) {\n'
        '    step compile { return "compiling in \\(mode)" }\n'
        '}\n'
        'fn main() {\n'
        '    print(run_workflow(build, {mode: "lite"})["steps"]["compile"])\n'
        '    print(run_workflow(build, {"mode": "full"})["steps"]["compile"])\n'
        '}\n'
    )
    assert r["ok"], r.get("error")
    assert "compiling in lite" in r["stdout"], r["stdout"]
    assert "compiling in full" in r["stdout"], "the map spelling must bind too"
    return "record and map spellings both bind"


@probe("5.6.0: a step can declare its output type")
def probe_step_returns():
    good = run_nd(
        'workflow w { step fetch with { returns: "map" } { return {"rows": 42i} } }\n'
        'fn main() { print(run_workflow(w)["steps"]["fetch"]["rows"]) }\n'
    )
    assert good["ok"], good.get("error")
    assert "42" in good["stdout"], good["stdout"]

    # An unknown type name is an error here, not a warning: the option is new,
    # so nothing can rely on a misspelling being ignored.
    bad = run_nd(
        'workflow w { step fetch with { returns: "mapp" } { return {} } }\n'
        'fn main() {}\n'
    )
    assert not bad["ok"], "an unknown `returns:` type must be refused"
    message = (bad.get("error") or {}).get("message") or ""
    assert "mapp" in message, message
    return "declared, and a misspelling is refused"


@probe("5.6.0: a goal can be bounded by what it spends")
def probe_budget_limits():
    from nodus.frontend.lexer import tokenize
    from nodus.frontend.parser import Parser

    src = (
        'workflow tune { step tweak { checkpoint "good_enough"\n'
        '    return 1i } }\n'
        'goal reach over tune {\n'
        '    until reached("good_enough")\n'
        '    budget { max_iterations: 3, limits: {steps: 100000i} }\n'
        '}\n'
    )
    Parser(tokenize(src)).parse()  # raises if `limits` is not accepted
    return "`budget { limits: ... }` parses"


@probe("5.6.0: an unrecognised type name is reported, not silently `any`")
def probe_unknown_type_name():
    from nodus.frontend.lexer import tokenize
    from nodus.frontend.parser import Parser

    parser = Parser(tokenize("fn f(x: itn) { return x }"))
    parser.parse()
    found = [str(d) for d in getattr(parser, "unknown_type_names", [])]
    assert found, "a misspelled type name must be recorded, not silently accepted"
    assert any("itn" in f for f in found), found
    return "misspellings are recorded (a warning until 6.0.0)"


@probe("5.6.0: the agent registry is a published surface")
def probe_register_agent():
    from nodus.runtime.embedding import NodusRuntime

    rt = NodusRuntime(timeout_ms=None, max_steps=None)
    for name in ("register_agent", "unregister_agent"):
        assert hasattr(rt, name), f"NodusRuntime.{name} is missing"
    rt.register_agent("probe.echo", lambda payload: {"echoed": payload})
    # `agent_available()` takes no arguments and lists what is registered.
    r = rt.run_source('fn main() { print(agent_available()) }', filename="<probe>")
    assert r["ok"], r.get("error")
    assert "probe.echo" in r["stdout"], r["stdout"]

    rt.unregister_agent("probe.echo")
    after = rt.run_source('fn main() { print(agent_available()) }', filename="<probe>")
    assert after["ok"], after.get("error")
    assert "probe.echo" not in after["stdout"], "unregister_agent did not remove it"
    return "register_agent / unregister_agent present, and both take effect"


@probe("5.6.0: `each` is a named keyword, so editors can highlight it")
def probe_each_is_a_keyword():
    from nodus.frontend.lexer import ALL_KEYWORDS

    # The claim this probe exists for: `each` shipped as a bare literal in the
    # parser once already, and `nodus_gate --consumers` could not see it because
    # the keyword fingerprint it compares never moved.
    for word in ("each", "checkpoint", "state"):
        assert word in ALL_KEYWORDS, f"{word!r} is not in ALL_KEYWORDS"
    return f"ALL_KEYWORDS names {len(ALL_KEYWORDS)} words, `each` among them"


@probe("5.6.0: RuntimeService.close() waits for its sweeper")
def probe_service_close_joins():
    import threading

    from nodus.services.server import RuntimeService

    service = RuntimeService(worker_sweep_interval_ms=10)
    entered, release = threading.Event(), threading.Event()
    original = service._run_workflow_sweep_once

    def slow():
        entered.set()
        release.wait(timeout=5.0)
        return original()

    service._run_workflow_sweep_once = slow
    try:
        assert entered.wait(timeout=5.0), "the sweeper never ran"
        thread = service._sweeper_thread
        release.set()
        service.close()
        assert not thread.is_alive(), "close() returned with the sweeper still running"
    finally:
        release.set()
        service.close()
    return "close() joins, so a caller may remove the store directory"


# ------------------------------------------------------------ 5.6.0: the prose


@probe("5.6.0 prose: nothing still calls 5.5.0 the current release")
def probe_no_stale_5_5_current(repo: Path):
    stale = []
    for rel in (
        "README.md", "llms.txt", "llms-full.txt",
        "docs/governance/ECOSYSTEM_READINESS_ASSESSMENT.md",
        "skills/nodus.skill", "skills/project-CLAUDE.md", "skills/project-AGENTS.md",
    ):
        path = repo / rel
        if not path.exists():
            continue
        for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if "5.5.0" not in line:
                continue
            low = line.lower()
            if any(k in low for k in ("current", "latest", "stable on pypi", "version:")):
                stale.append(f"{rel}:{n}")
    assert not stale, "still describes 5.5.0 as current: " + ", ".join(stale)
    return "no artifact calls 5.5.0 current"


@probe("5.6.0 prose: the guide documents mapping a step over a list")
def probe_guide_documents_each(repo: Path):
    guide = repo / "docs/guide/workflows-and-tasks.md"
    text = guide.read_text(encoding="utf-8")
    assert "each page in discover" in text, "no worked `each` example in the guide"
    for claim in ("skipped", "1024"):
        assert claim in text, f"the guide never mentions {claim!r}"
    return "section 3.3 documents the fan-out, its edges and its bound"


@probe("5.6.0 prose: the companion count matches the verified live count")
def probe_package_count(repo: Path):
    wrong = []
    for rel in (
        "README.md", "llms.txt", "llms-full.txt",
        "docs/governance/ECOSYSTEM_READINESS_ASSESSMENT.md", "CLAUDE.md",
    ):
        path = repo / rel
        if not path.exists():
            continue
        for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if re.search(r"\b32[- ](?:package|standalone)\b", line):
                wrong.append(f"{rel}:{n}")
    assert not wrong, "stale package count (should be 35): " + ", ".join(wrong)
    return "no artifact still says 32"


# --- 5.7.0 ------------------------------------------------------------------


@probe("5.7.0: `extern` declares a host surface and `nodus check` gets strict")
def probe_extern_declares_host_surface():
    from nodus.tooling.runner import check_source

    declared = 'extern delegate(who: string, task: string) -> string\n'
    typo = declared + 'fn main() { print(delegat("a", "b")) }\n'
    result = check_source(typo, filename="t.nd")
    assert not result["ok"], "an undeclared name passed in a file that declares an extern"
    assert "delegat" in (result.get("error") or {}).get("message", "")
    good = declared + 'fn main() { print(delegate("a", "b")) }\n'
    assert check_source(good, filename="t.nd")["ok"], "a declared name was rejected"
    return "declaring a host surface makes an unknown call an error"


@probe("5.7.0: a runtime refuses a program whose extern it has not registered")
def probe_extern_preflight():
    from nodus.runtime.embedding import NodusRuntime

    program = 'extern delegate(who: string) -> string\nfn main() { print(delegate("x")) }\n'
    refused = NodusRuntime(timeout_ms=None).run_source(program)
    assert not refused["ok"], "an unregistered extern ran"
    assert "has not registered" in (refused.get("error") or {}).get("message", "")

    runtime = NodusRuntime(timeout_ms=None)
    runtime.register_function("delegate", lambda who: "handled " + str(who), arity=1)
    ok = runtime.run_source(program)
    assert ok["ok"], ok.get("error")
    assert "handled x" in (ok.get("stdout") or "")
    return "refused before running; runs once registered"


@probe("5.7.0: a file with no extern is unchanged (strictness is per file)")
def probe_undeclared_file_unchanged():
    from nodus.tooling.runner import check_source

    result = check_source(
        "fn main() { print(totally_made_up_function(1i)) }\n", filename="t.nd"
    )
    assert result["ok"], (
        "a file declaring nothing became strict -- that would reject every "
        "embedded program written before declarations existed"
    )
    return "an undeclared file still accepts unknown free calls"


@probe("5.7.0: register_function takes a schema")
def probe_host_function_schema():
    from nodus.runtime.embedding import NodusRuntime

    def write_file(path, contents):
        return "wrote " + str(path)

    runtime = NodusRuntime(timeout_ms=None)
    runtime.register_function(
        "host_write", write_file, arity=2,
        schema={"path": "string", "contents": "string"},
    )
    bad = runtime.run_source('fn main() { print(host_write(42i, {"a": 1i})) }')
    assert not bad["ok"], "wrong argument types reached the host function"
    assert "must be a string" in (bad.get("error") or {}).get("message", "")

    plain = NodusRuntime(timeout_ms=None)
    plain.register_function("host_write", write_file, arity=2)
    assert plain.run_source('fn main() { print(host_write(42i, {"a": 1i})) }')["ok"], (
        "a registration without a schema changed behaviour"
    )
    return "typed args refused; an unschemaed registration is unchanged"


@probe("5.7.0: workflow_wait declares its resume payload shape")
def probe_wait_payload_schema():
    from nodus.runtime.embedding import NodusRuntime

    source = (
        "workflow w {\n"
        '    step a { return workflow_wait("approval", {schema: {approved: "bool"}}) }\n'
        "}\n"
        "fn main() {\n"
        "    let r = run_workflow(w)\n"
        '    print("R=\\(resume_workflow(r["graph_id"], nil, {approved: "yes"}))")\n'
        "}\n"
    )
    result = NodusRuntime(timeout_ms=None).run_source(source)
    assert result["ok"], result.get("error")
    out = result.get("stdout") or ""
    assert '"ok": false' in out, "a payload violating the declared schema was accepted"
    assert "must be a boolean" in out
    return "a mismatched resume payload is refused at the resume call"


@probe("5.7.0: compensation unwinds in reverse completion order")
def probe_compensation_unwind_order():
    from nodus.runtime.embedding import NodusRuntime

    source = (
        "workflow saga {\n"
        '    step reserve { return "res" }\n'
        '    step charge after reserve { return "ch" }\n'
        '    step ship after charge { throw "boom" }\n'
        '    step release compensates reserve { return "released" }\n'
        '    step refund compensates charge { return "refunded" }\n'
        "}\n"
        'fn main() { let r = run_workflow(saga); print("C=\\(r["compensation"])") }\n'
    )
    result = NodusRuntime(timeout_ms=None).run_source(source)
    assert result["ok"], result.get("error")
    out = result.get("stdout") or ""
    assert '"step": "refund"' in out and '"step": "release"' in out, out
    assert out.index('"step": "refund"') < out.index('"step": "release"'), (
        "compensation ran in the wrong order -- later work must unwind first"
    )
    return "refund (later) unwinds before release (earlier)"


@probe("5.7.0: a compensated run cannot be resumed")
def probe_compensated_run_is_terminal():
    from nodus.runtime.embedding import NodusRuntime

    source = (
        "workflow saga {\n"
        '    step reserve { checkpoint "cp"\n        return "res" }\n'
        '    step ship after reserve { throw "boom" }\n'
        '    step release compensates reserve { return "released" }\n'
        "}\n"
        "fn main() {\n"
        "    let r = run_workflow(saga)\n"
        '    print("A=\\(resume_workflow(r["graph_id"], "cp"))")\n'
        "}\n"
    )
    result = NodusRuntime(timeout_ms=None).run_source(source)
    assert result["ok"], result.get("error")
    assert "was compensated" in (result.get("stdout") or ""), "a compensated run was resumable"
    return "resume refused, naming the reason"


@probe("5.7.0: a failed pass does not satisfy a goal")
def probe_failed_pass_does_not_satisfy():
    from nodus.runtime.embedding import NodusRuntime

    source = (
        'workflow tune { step attempt { checkpoint "good"\n        throw "nope" } }\n'
        'goal reach over tune { until reached("good") budget { max_iterations: 2i } }\n'
        'fn main() { print("R=\\(run_goal(reach))") }\n'
    )
    result = NodusRuntime(timeout_ms=None).run_source(source)
    assert result["ok"], result.get("error")
    out = result.get("stdout") or ""
    assert "exhausted its budget" in out, out
    assert "goal_satisfied" not in out, "a failed pass still reported the goal satisfied"
    return "a checkpoint recorded before a throw no longer satisfies `until`"


@probe("5.7.0: fmt keeps a mapped step's `each` clause")
def probe_fmt_keeps_each():
    from nodus.tooling.formatter import format_source

    out = format_source(
        "workflow w {\n"
        "    step discover { return [1i] }\n"
        "    step render each page in discover { return page }\n"
        "}\n"
    )
    assert "each page in discover" in out, out
    assert "step render after discover" not in out, "fmt rewrote `each` as `after` again"
    return "a mapped step round-trips through fmt"


@probe("5.7.0: fmt keeps a goal budget's declared bounds")
def probe_fmt_keeps_budget_limits():
    from nodus.tooling.formatter import format_source

    flow = 'workflow t { step a { checkpoint "g"\n        return 1i } }\n'
    single = format_source(
        flow + 'goal r over t { until reached("g") budget { max_iterations: 3i } }\n'
    )
    assert "budget { max_iterations: 3i }" in single, single
    limited = format_source(
        flow
        + 'goal r over t { until reached("g") '
        + 'budget { max_iterations: 3i, limits: { tokens: 100i } } }\n'
    )
    assert "limits: { tokens: 100i }" in limited, "fmt dropped the limits bound"
    return "single-dimension budgets format, and limits survives"


@probe("5.7.0: the new keywords are named where tooling reads them")
def probe_new_keywords_named():
    from nodus.frontend.lexer import ALL_KEYWORDS

    for word in ("extern", "compensates"):
        assert word in ALL_KEYWORDS, repr(word) + " is not in ALL_KEYWORDS"
    return "ALL_KEYWORDS names {} words, including extern and compensates".format(
        len(ALL_KEYWORDS)
    )


@probe("5.7.0: nothing still calls 5.6.0 the current release")
def probe_no_stale_5_6_current(repo: Path):
    """The half that has caught things: prose describing the previous release.

    Deliberately narrow -- it looks for 5.6.0 asserted as *current*, not every
    mention. A historical "shipped in 5.6.0" is correct and must not be
    rewritten; a blanket sweep at 5.5.0 turned four such facts into lies.
    """
    pattern = re.compile(
        r"(current(ly)?|latest|published version|now on PyPI)[^.\n]{0,40}5\.6\.0"
        r"|5\.6\.0[^.\n]{0,40}(is current|current stable|latest release)",
        re.IGNORECASE,
    )
    hits = []
    candidates = (
        list(repo.glob("*.md"))
        + list(repo.glob("*.txt"))
        + list((repo / "docs").rglob("*.md"))
        + list((repo / "skills").glob("*"))
    )
    for path in candidates:
        if not path.is_file() or "evals" in path.parts or "CHANGELOG" in path.name:
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for n, line in enumerate(text.splitlines(), 1):
            if pattern.search(line):
                hits.append("{}:{}".format(path.relative_to(repo), n))
    assert not hits, "still describes 5.6.0 as current: " + ", ".join(hits[:6])
    return "no artifact calls 5.6.0 the current release"



@probe("5.7.1: a step body may read its dependencies, including under `extern`")
def probe_step_deps_are_bound():
    """The 5.7.0 regression, and the analyzer defect under it (#662).

    Deliberately exercises the *pair*: a file that declares an `extern` AND
    reads a dependency by name. Neither feature was broken alone, which is why
    5.7.0's 71 probes were green -- the compensation probes declared no extern
    and the extern probes read no dependency. Stage 5 found it by running both
    together as a user would.
    """
    from nodus.tooling.diagnostics import WorkspaceDiagnosticEngine
    from nodus.tooling.runner import check_source

    def undefined(source):
        result = WorkspaceDiagnosticEngine().analyze("m.nd", source=source)
        return [
            d.message
            for diags in result.diagnostics_by_file.values()
            for d in diags
            if "Undefined" in d.message
        ]

    # All three binding forms, none of which should be flagged.
    assert undefined(
        "workflow w { step a { return 1i } step b after a { return a } }"
    ) == [], "an `after`-bound dependency is reported undefined"
    assert undefined(
        "workflow w { step d { return [1i] } step r each p in d { return p } }"
    ) == [], "an `each` loop variable is reported undefined"
    assert undefined(
        "workflow w { step a { return 1i } "
        'step s after a { throw "x" } '
        "step u compensates a { return a } }"
    ) == [], "a compensated step's name is reported undefined"

    # And the analyzer is not simply permissive now.
    assert undefined(
        "workflow w { step a { return 1i } step b after a { return nope } }"
    ) == ["Undefined variable: nope"], "a genuine typo stopped being reported"

    # The pair: strict mode plus a dependency read. This is what 5.7.0 rejected.
    source = (
        "extern notify(who: string) -> string\n"
        "workflow saga {\n"
        '    step reserve { return "res-1" }\n'
        '    step ship after reserve { throw "carrier down" }\n'
        '    step release compensates reserve { return "released \\(reserve)" }\n'
        "}\n"
        'fn main() { print(notify("x")) }\n'
    )
    result = check_source(source, filename="saga.nd")
    assert result["ok"], (
        "nodus check rejected a correct program that declares an extern and "
        "reads a dependency: " + str(result.get("error"))
    )
    return "after/each/compensates bind; typos still caught; strict mode accepts a dep read"


# --- 5.8.0 -------------------------------------------------------------------


@probe("5.8.0: `retry.until` retries on a predicate and carries the failing result")
def probe_retry_until_carrier():
    """The carrier is the claim, not the loop.

    An implementation that re-calls the function and ignores what it returned
    passes a happy-path assertion and is a blind re-roll -- precisely the thing
    the construct exists to avoid. So the probe reads what the *next attempt
    received*, not only the final value.
    """
    result = run_nd(
        'import "std:retry" as retry\n'
        "fn main() {\n"
        "    let seen = []\n"
        "    let r = retry.until(\n"
        "        fn(previous) { seen = list_push(seen, previous); return len(seen) },\n"
        "        fn(value) { return value >= 3i },\n"
        '        {"max_attempts": 5i}\n'
        "    )\n"
        '    print("seen=\\(seen) value=\\(r["value"]) satisfied=\\(r["satisfied"]) attempts=\\(r["attempts"])")\n'
        "}\n"
    )
    assert result["ok"], result.get("error")
    text = result.get("stdout") or ""
    assert "seen=[nil, 1, 2]" in text, "the previous result did not reach the next attempt: " + text
    assert "value=3 satisfied=true attempts=3" in text, text
    return "carrier delivers nil, 1, 2; stops at the first satisfying value"


@probe("5.8.0: `retry.until` is bounded even when the caller declares no bound")
def probe_retry_until_implicit_cap():
    """A predicate that never holds and no policy is an unbounded loop.

    `budget` grew the same guarantee in #488, where mutation testing found that
    removing it hung the suite. The step limit is deliberately set high enough
    that a *step limit* firing could not be mistaken for the bound holding.
    """
    from nodus.runtime.embedding import NodusRuntime

    result = NodusRuntime(timeout_ms=None, max_steps=5_000_000).run_source(
        'import "std:retry" as retry\n'
        "fn main() {\n"
        "    let r = retry.until(fn() { return 0i }, fn(v) { return false }, nil)\n"
        '    print("attempts=\\(r["attempts"]) satisfied=\\(r["satisfied"])")\n'
        "}\n",
        filename="<probe>",
    )
    assert result["ok"], result.get("error")
    text = result.get("stdout") or ""
    assert "attempts=10000" in text, "no implicit cap: " + text
    assert "satisfied=false" in text, text
    return "an undeclared bound is 10,000 attempts, and exhaustion reports rather than raises"


@probe("5.8.0: `cancel(t)` stops a task, running `finally` and not `catch`")
def probe_cancel_runs_finally_not_catch():
    """Both halves matter. A cancel that ran `catch` would let a task swallow
    its own cancellation; a cancel that skipped `finally` would leak whatever the
    task held.
    """
    result = run_nd(
        "fn main() {\n"
        "    let t = spawn(coroutine(fn() {\n"
        '        try { sleep(50i); print("BODY AFTER SLEEP") }\n'
        '        catch e { print("CATCH RAN") }\n'
        '        finally { print("finally ran") }\n'
        "    }))\n"
        "    spawn(coroutine(fn() { sleep(1i); cancel(t) }))\n"
        "    run_loop()\n"
        "}\n"
    )
    assert result["ok"], result.get("error")
    text = result.get("stdout") or ""
    assert "finally ran" in text, "cancel skipped finally: " + text
    assert "CATCH RAN" not in text, "a task swallowed its own cancellation"
    assert "BODY AFTER SLEEP" not in text, "the task kept running past the cancel"
    return "finally runs, catch does not, the body does not resume"


@probe("5.8.0: cancel and wait compose -- a waiter is released, not orphaned")
def probe_cancel_releases_waiters():
    """The product of the two features, which is what 5.7.1 taught to probe.

    #395 (cancel) and #157 (wait) each pass alone on an implementation where a
    cancelled task's waiters are simply never woken -- the cancel works, the
    wait works, and the *pair* hangs until the step limit. The only way to see
    it is to run both.
    """
    result = run_nd(
        "fn main() {\n"
        "    let t = spawn(coroutine(fn() { sleep(50i); return 1i }))\n"
        '    spawn(coroutine(fn() { try { wait(t) } catch e { print("waiter saw: \\(e.message)") } }))\n'
        "    spawn(coroutine(fn() { sleep(1i); cancel(t) }))\n"
        "    run_loop()\n"
        '    print("run_loop returned")\n'
        "}\n"
    )
    assert result["ok"], result.get("error")
    text = result.get("stdout") or ""
    assert "run_loop returned" in text, "the waiter was orphaned: " + text
    assert "Task cancelled" in text, "the waiter was released without being told why: " + text
    return "a waiter on a cancelled task is woken and told the task was cancelled"


@probe("5.8.0: `cancelled` is one vocabulary, not three spellings")
def probe_cancelled_vocabulary():
    """The shape this codebase catalogues: a status enumerated in several places
    with one member missing. Both tuples are read from the runtime, so a fourth
    site that re-enumerates by hand is what this would catch.
    """
    from nodus.runtime.coroutine import BLOCKED_REASON_SET
    from nodus_lang_workflow.models import (
        RUN_STATUS_CANCELLED,
        RUN_STATUSES,
        TERMINAL_RUN_STATUSES,
    )

    assert RUN_STATUS_CANCELLED == "cancelled", RUN_STATUS_CANCELLED
    assert RUN_STATUS_CANCELLED in RUN_STATUSES, RUN_STATUSES
    assert RUN_STATUS_CANCELLED in TERMINAL_RUN_STATUSES, TERMINAL_RUN_STATUSES
    assert "task_wait" in BLOCKED_REASON_SET, sorted(BLOCKED_REASON_SET)
    return "cancelled is a run status and terminal; task_wait is a named blocked reason"


@probe("5.8.0: `nodus workflow cancel` exists and its help says what it does")
def probe_workflow_cancel_verb():
    from nodus.cli.commands import flags_for

    from nodus.cli.commands import command_help

    flags_for("workflow", "cancel")  # raises if the subcommand is not registered

    # argv includes the program name -- `cli(["workflow", "--help"])` consumes
    # "workflow" as argv[0] and prints the general usage, which is a probe that
    # passes on a CLI with no such verb at all.
    code, out = cli(["nodus", "workflow", "--help"])
    assert code == 0, code
    assert "cancel <graph_id>" in out, "workflow --help does not list cancel: " + out[:400]
    assert "cancel <graph_id>" in command_help("workflow"), "help table and CLI disagree"
    return "the verb is in the command table and `nodus workflow --help` documents it"


@probe("5.8.0: a function assigning to a module-top-level `let` updates it (#671)")
def probe_toplevel_assignment():
    """A behaviour change, not a fix -- a program that relied on the old silence
    now sees its globals mutate. Nothing can have depended on a write vanishing,
    but it is a change in what running code does, so it is probed as a claim.
    """
    result = run_nd(
        "let g = 7i\n"
        "fn setit() { g = 99i }\n"
        "fn main() { setit(); print(g) }\n"
    )
    assert result["ok"], result.get("error")
    assert "99" in (result.get("stdout") or ""), (
        "the assignment still wrote a frame-local: " + (result.get("stdout") or "")
    )
    return "the write reaches the module global rather than a frame slot"


@probe("5.8.0: a named import of a builtin name is refused, and says how to fix it (#680)")
def probe_builtin_import_refused():
    """The message is the deliverable. Refusing without naming the collision
    reproduces the original defect one layer up -- the program failed somewhere
    else entirely, naming neither the import nor the shadowing.
    """
    import tempfile

    with tempfile.TemporaryDirectory() as td:
        mod = Path(td) / "mod.nd"
        mod.write_text("fn sleep(a, b) { return a }\n", encoding="utf-8")
        main = Path(td) / "main.nd"
        main.write_text('import { sleep } from "./mod.nd"\nfn main() { print(1i) }\n', encoding="utf-8")

        from nodus.runtime.embedding import NodusRuntime

        result = NodusRuntime(timeout_ms=None).run_file(str(main))

    assert not result["ok"], "the shadowing import was accepted: " + str(result)
    message = (result.get("error") or {}).get("message", "")
    assert "sleep" in message, message
    assert "as" in message, "the message does not offer the namespace form: " + message
    return "refused at load, naming the collision and the namespace form that works"


@probe("5.8.0: a runtime-built graph names its steps, and results are keyed by name (#679)")
def probe_named_runtime_steps():
    result = run_nd(
        "fn main() {\n"
        '    let a = task(fn() { return "A" }, {"name": "fetch"})\n'
        '    let b = task(fn() { return "B" }, {"name": "render", "after": [a]})\n'
        "    let r = run_graph([a, b])\n"
        '    print("steps=\\(keys(r["steps"]))")\n'
        "}\n"
    )
    assert result["ok"], result.get("error")
    text = result.get("stdout") or ""
    assert "fetch" in text and "render" in text, (
        "per-step results are not keyed by the declared name: " + text
    )
    return "declared step names key the result map"


@probe("5.8.0: the plan-then-act example runs and hands off (#465)")
def probe_plan_then_act_example(repo: Path):
    example = repo / "examples" / "plan_then_act.nd"
    assert example.is_file(), "the deliverable for #465 is missing: {}".format(example)
    result = run_nd(example.read_text(encoding="utf-8"))
    assert result["ok"], result.get("error")
    text = result.get("stdout") or ""
    assert "failed: []" in text, text
    assert "applied: 1. rename the symbol" in text, (
        "the second step did not consume the first step's plan: " + text
    )
    return "the example runs clean and the plan reaches the acting step"


@probe("5.8.0: no artifact still calls 5.7.1 the current release")
def probe_no_stale_5_7_current(repo: Path):
    """The prose half. Narrow on purpose: it looks for 5.7.1 asserted as
    *current*, not every mention -- a historical "fixed in 5.7.1" is correct and
    a blanket sweep at 5.5.0 turned four such facts into lies.
    """
    pattern = re.compile(
        r"(current(ly)?|latest|published version|now on PyPI)[^.\n]{0,40}5\.7\.1"
        r"|5\.7\.1[^.\n]{0,40}(is current|current stable|latest release)",
        re.IGNORECASE,
    )
    hits = []
    candidates = (
        list(repo.glob("*.md"))
        + list(repo.glob("*.txt"))
        + list((repo / "docs").rglob("*.md"))
        + list((repo / "skills").glob("*"))
    )
    for path in candidates:
        if not path.is_file() or "evals" in path.parts or "CHANGELOG" in path.name:
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for n, line in enumerate(text.splitlines(), 1):
            if pattern.search(line):
                hits.append("{}:{}".format(path.relative_to(repo), n))
    assert not hits, "still describes 5.7.1 as current: " + ", ".join(hits[:6])
    return "no artifact calls 5.7.1 the current release"


# ------------------------------------------- 5.9.0: silent wrongness, and bytes
#
# Every claim below is probed **in the position its documentation points at**,
# which is #691's lesson rather than a preference: `retry.until` had a full suite,
# nine gate phases and 83 release probes behind it and did not work inside a step
# body, because every one of them ran in `fn main()`. A probe that exercises the
# easy position proves the easy position.


@probe("#691: a callback into a module runs, inside a step body")
def probe_callback_into_module_in_step():
    import tempfile

    with tempfile.TemporaryDirectory() as td:
        mod = Path(td) / "m.nd"
        mod.write_text(
            "fn no_loop(f) { return f() }\n"
            "fn in_loop(f) { let n = 0i let last = nil "
            "while (n < 2i) { last = f() n = n + 1i } return last }\n",
            encoding="utf-8",
        )
        from nodus.runtime.embedding import NodusRuntime

        # `run_file`, not `run_source`: a relative import resolves against the
        # process CWD, and `filename` is only a label (#521). The regression
        # tests take the same route for the same reason.
        main_nd = Path(td) / "main.nd"
        main_nd.write_text(
            'import "./m.nd" as m\n'
            "workflow w {\n"
            '    step a { print("got \\(m.no_loop(fn() { return 7i }))") return "ok" }\n'
            "}\n"
            'fn main() { let r = run_workflow(w) print("failed: \\(r["failed"])") '
            'print("steps: \\(r["steps"])") }\n',
            encoding="utf-8",
        )
        result = NodusRuntime(timeout_ms=None, max_steps=None,
                              allowed_paths=[td]).run_file(str(main_nd))
    assert result.get("ok"), result.get("errors")
    out = result.get("stdout") or ""
    # The silent case is the one that mattered: it printed nothing after the call
    # and reported `failed: []` with `steps: {}`.
    assert "got 7" in out, f"the step truncated at the module call: {out.strip()!r}"
    assert '"a": "ok"' in out, f"the step was not recorded: {out.strip()!r}"
    return "a step body's callback reaches the module and the step is recorded"


@probe("#696: a closure returned from a module runs at top level")
def probe_closure_returned_from_module():
    import tempfile

    with tempfile.TemporaryDirectory() as td:
        mod = Path(td) / "f.nd"
        mod.write_text(
            "fn make_adder(n) { return fn(x) { return x + n } }\n"
            "fn counter() { let n = 0i return fn() { n = n + 1i return n } }\n"
            "fn pad_a() { return 1i }\nfn pad_b() { return 2i }\n",
            encoding="utf-8",
        )
        from nodus.runtime.embedding import NodusRuntime

        main_nd = Path(td) / "main.nd"
        main_nd.write_text(
            'import "./f.nd" as f\n'
            "fn main() {\n"
            '    print("adder: \\(f.make_adder(3i)(10i))")\n'
            "    let c = f.counter()\n"
            '    print("counter: \\(c()) \\(c()) \\(c())")\n'
            "}\n",
            encoding="utf-8",
        )
        result = NodusRuntime(timeout_ms=None, max_steps=None,
                              allowed_paths=[td]).run_file(str(main_nd))
    assert result.get("ok"), result.get("errors")
    out = result.get("stdout") or ""
    assert "adder: 13" in out, f"a returned closure lost its upvalue: {out.strip()!r}"
    assert "counter: 1 2 3" in out, f"a stateful factory closure failed: {out.strip()!r}"
    return "a factory function exported by a module works, upvalues and all"


@probe("#704: an edit at the same mtime is not served from cache")
def probe_cache_notices_content():
    import os as _os
    import tempfile

    from nodus.runtime.embedding import NodusRuntime

    with tempfile.TemporaryDirectory() as td:
        prog = Path(td) / "prog.nd"
        prog.write_text('fn main() { print("first") }\n', encoding="utf-8")
        mtime = _os.stat(prog).st_mtime_ns
        first = NodusRuntime(timeout_ms=None, allowed_paths=[td]).run_file(str(prog))
        assert "first" in (first.get("stdout") or ""), first

        # Force the mtime back, which is what the platform does for free inside
        # its timestamp resolution -- whole seconds on some interpreters.
        prog.write_text('fn main() { print("second") }\n', encoding="utf-8")
        _os.utime(prog, ns=(mtime, mtime))
        second = NodusRuntime(timeout_ms=None, allowed_paths=[td]).run_file(str(prog))
        out = second.get("stdout") or ""
    assert "second" in out, f"a rewritten file ran the cached program: {out.strip()!r}"
    assert "first" not in out, f"stale output leaked: {out.strip()!r}"
    return "the program that runs is the program on disk"


@probe("#170: binary file I/O round-trips bytes text mode cannot carry")
def probe_binary_file_io():
    import tempfile

    from nodus.runtime.embedding import NodusRuntime

    with tempfile.TemporaryDirectory() as td:
        target = str(Path(td) / "raw.bin").replace("\\", "/")
        result = NodusRuntime(timeout_ms=None, allowed_paths=[td]).run_source(
            'import "std:fs" as fs\n'
            "fn main() {\n"
            "    fs.write_bytes(\"%s\", [0i, 128i, 26i, 255i, 10i])\n"
            '    print("back: \\(fs.read_bytes("%s"))")\n'
            '    print("as text: \\(fs.read("%s").kind)")\n'
            "}\n" % (target, target, target),
            filename="<probe>",
        )
    assert result.get("ok"), result.get("errors")
    out = result.get("stdout") or ""
    # 0x80 and 0xFF are not valid UTF-8 and 0x1A is end-of-file in Windows text
    # mode -- which is the whole reason the pair exists.
    assert "back: [0, 128, 26, 255, 10]" in out, f"bytes did not survive: {out.strip()!r}"
    assert "as text: io_error" in out, (
        f"reading the same file as text should fail, got {out.strip()!r}"
    )
    return "bytes survive a round trip that text mode refuses"


@probe("prose: nothing still calls 5.8.0 the current release")
def probe_no_stale_580_claim(repo: Path):
    pattern = re.compile(
        r"(current|latest|newest)[^.\n]{0,40}\b5\.8\.0\b"
        r"|\b5\.8\.0\b[^.\n]{0,40}(current|latest|is live|stable on PyPI)",
        re.I,
    )
    hits = []
    for path in sorted(repo.rglob("*.md")) + sorted(repo.glob("*.txt")) + \
            sorted(repo.glob("skills/*")):
        parts = set(path.parts)
        if parts & {".git", ".venv", "node_modules", "evals", "dist", "build"}:
            continue
        if not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for n, line in enumerate(text.splitlines(), 1):
            if pattern.search(line):
                hits.append("{}:{}".format(path.relative_to(repo), n))
    assert not hits, "still describes 5.8.0 as current: " + ", ".join(hits[:6])
    return "no artifact calls 5.8.0 the current release"



@probe("#754: submitted code cannot shell out on the serve path")
def probe_serve_denies_submitted_code():
    """The claim the release leads with, checked against the shipped wheel.

    Paired with a control that must run, because every deny case passes
    vacuously if the program never executed -- which is how the first probe for
    this issue read an empty stdout as a refusal.
    """
    import os
    import tempfile

    from nodus.services.server import RuntimeService

    source = (
        'import "std:subprocess" as sp\n'
        'let r = sp.run(["%s", "-c", "print(1)"])\n'
        'print("exit=\\(r.exit_code)")\n' % sys.executable.replace("\\", "/")
    )
    cwd = os.getcwd()
    with tempfile.TemporaryDirectory() as td:
        os.chdir(td)
        try:
            control = RuntimeService().execute(
                {"code": 'print("ran")\n', "filename": "<probe>"}
            )
            denied = RuntimeService().execute({"code": source, "filename": "<probe>"})
            granted = RuntimeService(allow_subprocess=True).execute(
                {"code": source, "filename": "<probe>"}
            )
        finally:
            os.chdir(cwd)

    assert control.get("ok") and "ran" in (control.get("stdout") or ""), (
        "the control never ran, so the refusal below proves nothing"
    )
    assert not denied.get("ok"), "submitted code shelled out on the default serve path"
    assert (denied.get("error") or {}).get("kind") == "sandbox", denied.get("error")
    assert "allow_subprocess" in ((denied.get("error") or {}).get("message") or ""), (
        "the refusal must name the capability that grants it"
    )
    assert granted.get("ok") and "exit=0" in (granted.get("stdout") or ""), (
        f"--allow-subprocess did not grant it: {granted.get('error')}"
    )
    return "denied by default, granted explicitly, and the control still runs"


@probe("#167: extensions= withholds a domain surface, None carries it")
def probe_extensions_select_surfaces():
    from nodus.runtime.capability import DOMAIN_BUILTIN_GROUPS
    from nodus.runtime.embedding import NodusRuntime

    src = 'workflow w { step a { return 1i } }\nfn main() { run_workflow(w); print("ran") }\n'
    full = NodusRuntime(timeout_ms=None).run_source(src, filename="<probe>")
    lean = NodusRuntime(timeout_ms=None, extensions=[]).run_source(src, filename="<probe>")
    picked = NodusRuntime(timeout_ms=None, extensions=["workflow"]).run_source(
        src, filename="<probe>"
    )

    assert full.get("ok"), f"the default must be unchanged: {full.get('error')}"
    assert not lean.get("ok"), "extensions=[] still ran a workflow"
    assert (lean.get("error") or {}).get("kind") == "sandbox", lean.get("error")
    assert 'extensions=["workflow"]' in ((lean.get("error") or {}).get("message") or ""), (
        "the refusal must name the grant"
    )
    assert picked.get("ok"), f"extensions=['workflow'] must grant it: {picked.get('error')}"

    try:
        NodusRuntime(extensions=["workfow"])
    except ValueError as err:
        assert "workfow" in str(err) and "workflow" in str(err), str(err)
    else:  # pragma: no cover - the point of the probe
        raise AssertionError("a misspelled extension was accepted")

    assert set(DOMAIN_BUILTIN_GROUPS) == {"workflow", "tool", "agent", "syscall", "memory"}, (
        sorted(DOMAIN_BUILTIN_GROUPS)
    )
    return "None carries every surface; [] withholds them; a typo is refused"


@probe("#181: an event reaches a parked run by type, with no run id")
def probe_deliver_by_event_type():
    import os
    import tempfile

    from nodus.tooling import runner as tooling_runner
    from nodus_lang_workflow.runner import (
        get_default_workflow_runner,
        reset_default_workflow_runner,
    )

    src = (
        'workflow order {\n'
        '    step park { return workflow_wait("order.paid", {correlation_key: "c1"}) }\n'
        '    step ship after park { return "shipped" }\n'
        '}\n'
        'fn main() { print(run_workflow(order)["graph_id"]) }\n'
    )
    cwd = os.getcwd()
    with tempfile.TemporaryDirectory() as td:
        os.chdir(td)
        try:
            reset_default_workflow_runner()
            result, vm = tooling_runner.run_source(src, filename="<probe>", timeout_ms=30000)
            assert result.get("ok"), result.get("error")
            graph_id = (result.get("stdout") or "").strip()

            wr = get_default_workflow_runner()
            waiting = wr.store.list_runs_waiting_for("order.paid")
            assert [r.run_id for r in waiting] == [graph_id], (
                f"lookup by event type found {[r.run_id for r in waiting]}"
            )
            report = wr.deliver_event(lambda _rec: vm, "order.paid", payload={"amount": 1})
            assert report.get("ok"), report.get("error")
            statuses = report["delivered"][0]["result"]["statuses"]
            assert statuses.get("ship") == "completed", statuses

            empty = wr.deliver_event(lambda _rec: vm, "nothing.listens")
            assert empty.get("ok") and empty["matched"] == [], empty
        finally:
            reset_default_workflow_runner()
            os.chdir(cwd)
    return "found by event type, carried the run forward, and matching nothing is not an error"


@probe("#174: an unconfigured local store holding runs says so, once")
def probe_store_transition_warning():
    import os
    import tempfile
    import warnings as _warnings

    from nodus_lang_workflow.runner import (
        get_default_workflow_runner,
        reset_default_store_warning,
        reset_default_workflow_runner,
    )
    from nodus_lang_workflow.store import WORKFLOW_STORE_BACKEND_ENV

    cwd = os.getcwd()
    saved = os.environ.pop(WORKFLOW_STORE_BACKEND_ENV, None)
    with tempfile.TemporaryDirectory() as td:
        os.chdir(td)
        try:
            reset_default_workflow_runner()
            reset_default_store_warning()
            with _warnings.catch_warnings(record=True) as quiet:
                _warnings.simplefilter("always")
                get_default_workflow_runner()
            assert not [w for w in quiet if issubclass(w.category, DeprecationWarning)], (
                "an empty store must stay quiet"
            )

            get_default_workflow_runner().store.create_run(
                run_id="g_probe", graph_id="g_probe",
                workflow_name="probe", execution_kind="workflow",
            )
            reset_default_workflow_runner()
            reset_default_store_warning()
            with _warnings.catch_warnings(record=True) as loud:
                _warnings.simplefilter("always")
                get_default_workflow_runner()
            found = [w for w in loud if issubclass(w.category, DeprecationWarning)]
            assert len(found) == 1, [str(w.message) for w in found]
            assert "migrate-store" in str(found[0].message), str(found[0].message)
            assert "6.0.0" in str(found[0].message), str(found[0].message)
        finally:
            reset_default_workflow_runner()
            if saved is not None:
                os.environ[WORKFLOW_STORE_BACKEND_ENV] = saved
            os.chdir(cwd)
    return "quiet when empty, one actionable warning when runs are at risk"


@probe("prose: nothing still calls 5.9.0 the current release")
def probe_no_stale_590_claim(repo: Path):
    pattern = re.compile(
        r"(current|latest|newest)[^.\n]{0,40}\b5\.9\.0\b"
        r"|\b5\.9\.0\b[^.\n]{0,40}(current|latest|is live|stable on PyPI)",
        re.I,
    )
    hits = []
    for path in sorted(repo.rglob("*.md")) + sorted(repo.glob("*.txt")) + \
            sorted(repo.glob("skills/*")):
        parts = set(path.parts)
        if parts & {".git", ".venv", "node_modules", "evals", "dist", "build"}:
            continue
        if not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for n, line in enumerate(text.splitlines(), 1):
            if pattern.search(line):
                hits.append("{}:{}".format(path.relative_to(repo), n))
    assert not hits, "still describes 5.9.0 as current: " + ", ".join(hits[:6])
    return "no artifact calls 5.9.0 the current release"


@probe("prose: the README's serve banner matches the shipped behaviour")
def probe_readme_serve_banner(repo: Path):
    """`readme = \"README.md\"` makes this the permanent PyPI page, and the
    banner previously said the CLI never constructs a NodusRuntime -- true, and
    read as "serve is permissive", which #754 made false."""
    text = (repo / "README.md").read_text(encoding="utf-8", errors="replace")
    assert "nodus serve` *is* affected" in text or "nodus serve` **is** affected" in text, (
        "the capability banner does not mention that serve is now confined"
    )
    assert "--allow-subprocess" in text, "the banner must name how to grant it back"
    return "the banner names serve, and how to grant what it now denies"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--repo",
        type=Path,
        default=Path(__file__).resolve().parents[2],
        help="repo root for the prose probes (default: this checkout)",
    )
    parser.add_argument(
        "--require-installed",
        action="store_true",
        help=(
            "fail if `nodus` resolves inside --repo. Gate 10b validates the "
            "built wheel, and the repo-root `nodus.py` shim shadows an "
            "installed package whenever CWD is the repo."
        ),
    )
    args = parser.parse_args()

    # A probe that dies while *reporting* a failure is worse than no probe: it
    # turns a real finding into a traceback. Windows consoles default to cp1252,
    # and the artifacts this reads contain emoji.
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass

    # Resolved path and version first, always. Validating the wrong tree is the
    # failure mode this header exists to make visible (5.0.3 shipped past 32
    # green probes run against a tree that was not the one being released).
    import nodus
    from nodus.support import version as version_module

    package_dir = Path(version_module.__file__).resolve().parents[1]
    print("=" * 72)
    print(f"  package   {package_dir}")
    print(f"  version   {version_module.__version__}")
    print(f"  import    {getattr(nodus, '__file__', '?')}")
    print(f"  repo      {args.repo}")
    print("=" * 72)

    # The wrong-tree trap, made mechanical. The repo-root `nodus.py` shim
    # inserts `src/` on `sys.path` and re-execs the package from there, so ANY
    # process whose CWD is the repo resolves `nodus` to the source tree no
    # matter what is installed. Python puts the working directory first on
    # `sys.path`, so this needs no PYTHONPATH and leaves no trace in `pip list`.
    #
    # 5.0.3 shipped past 32 green probes run against the wrong tree. 5.5.0 hit
    # it and caught it by reading this header; its eval wrote the cause up in
    # full. 5.6.0 hit it again anyway -- which is why it is a check now, and not
    # a paragraph in the previous release's eval where nobody reads it in time.
    # Specifically the source tree, not merely "somewhere under the repo": a
    # validation venv created inside the checkout resolves correctly and must
    # not be refused. The trap is `<repo>/src/nodus`, which is what the shim
    # points at.
    is_source_tree = False
    try:
        package_dir.relative_to(Path(args.repo).resolve() / "src")
        is_source_tree = True
    except ValueError:
        pass
    if is_source_tree:
        print()
        print("  !! `nodus` resolved INSIDE the repo, not to an installed package.")
        print("     To validate a wheel, run from a directory outside the repo:")
        print("     the repo-root nodus.py shim shadows site-packages via CWD.")
        if args.require_installed:
            print()
            print("  refusing to validate the source tree (--require-installed)")
            return 2
    print()

    probe_sum()
    probe_append_union()
    probe_assign_refused()
    probe_union_record()
    probe_conflict_precision()
    probe_graph_show(args.repo)
    probe_doctor()
    probe_completion()
    probe_publish_flag()
    probe_group_help()
    probe_event_retention()
    probe_pattern_selfcheck()
    probe_no_stale_fold_claim(args.repo)
    probe_policy_vocabulary(args.repo)
    probe_new_commands_listed()

    # 5.3.0
    probe_policy_sees_authority()
    probe_classification_total()
    probe_syscall_capability()
    probe_writable_paths()
    probe_manifest()
    probe_worker_warns()
    probe_conditional_edges(args.repo)
    probe_guard_error()
    probe_no_stale_capability_claim(args.repo)

    # 5.4.0
    probe_allow_failure()
    probe_try_finally()
    probe_channel_backpressure()
    probe_graph_does_not_execute(args.repo)
    probe_topology_validation()
    probe_waiting_resume_refused()
    probe_persist_naming()
    probe_goal_waypoint()
    probe_check_enters_steps()
    probe_5_4_pattern_selfcheck()

    # --- 5.5.0 ---
    probe_step_entry_guard()
    probe_flow_shape_intact()
    probe_run_state_root()
    probe_floor_follows_state()
    probe_nodus_docs()
    probe_one_resolver()
    probe_lsp_indexes_steps()
    probe_no_false_undefined()
    probe_no_stale_5_4_current(args.repo)
    probe_skill_is_current(args.repo)
    probe_readme_absolute(args.repo)
    probe_debt_register_current(args.repo)
    probe_no_stale_5_4_claims(args.repo)

    # --- 5.6.0 ---
    probe_each_fanout()
    probe_each_edges()
    probe_workflow_parameters()
    probe_step_returns()
    probe_budget_limits()
    probe_unknown_type_name()
    probe_register_agent()
    probe_each_is_a_keyword()
    probe_service_close_joins()
    probe_no_stale_5_5_current(args.repo)
    probe_guide_documents_each(args.repo)
    probe_package_count(args.repo)

    # --- 5.7.0 ---------------------------------------------------------------
    probe_extern_declares_host_surface()
    probe_extern_preflight()
    probe_undeclared_file_unchanged()
    probe_host_function_schema()
    probe_wait_payload_schema()
    probe_compensation_unwind_order()
    probe_compensated_run_is_terminal()
    probe_failed_pass_does_not_satisfy()
    probe_fmt_keeps_each()
    probe_fmt_keeps_budget_limits()
    probe_new_keywords_named()
    probe_no_stale_5_6_current(args.repo)

    # --- 5.7.1 ---------------------------------------------------------------
    probe_step_deps_are_bound()

    # --- 5.8.0 ---------------------------------------------------------------
    probe_retry_until_carrier()
    probe_retry_until_implicit_cap()
    probe_cancel_runs_finally_not_catch()
    probe_cancel_releases_waiters()
    probe_cancelled_vocabulary()
    probe_workflow_cancel_verb()
    probe_toplevel_assignment()
    probe_builtin_import_refused()
    probe_named_runtime_steps()
    probe_plan_then_act_example(args.repo)
    probe_no_stale_5_7_current(args.repo)

    # 5.9.0
    probe_callback_into_module_in_step()
    probe_closure_returned_from_module()
    probe_cache_notices_content()
    probe_binary_file_io()
    probe_no_stale_580_claim(args.repo)

    # 5.10.0
    probe_serve_denies_submitted_code()
    probe_extensions_select_surfaces()
    probe_deliver_by_event_type()
    probe_store_transition_warning()
    probe_no_stale_590_claim(args.repo)
    probe_readme_serve_banner(args.repo)

    failed = [r for r in RESULTS if not r[0]]
    for ok, name, detail in RESULTS:
        mark = "PASS" if ok else "FAIL"
        print(f"[{mark}] {name}")
        if detail:
            print(f"       {detail}")
    print()
    print(f"{len(RESULTS) - len(failed)}/{len(RESULTS)} probes passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
