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
        parts = path.parts
        if "evals" in parts or "design" in parts or path.name == "CHANGELOG.md":
            continue  # records of what *was*; describing the old state is their job
        for number, line in enumerate(path.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
            if stale.search(line):
                hits.append(f"{path.relative_to(repo)}:{number}: {line.strip()[:90]}")
    assert not hits, "prose describes the pre-5.3.0 surface:\n       " + "\n       ".join(hits)
    return f"no artifact still describes the {len(ALL_CAPABILITIES) - 5}-name-smaller vocabulary"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--repo",
        type=Path,
        default=Path(__file__).resolve().parents[2],
        help="repo root for the prose probes (default: this checkout)",
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
