"""What in this project breaks at the next major, found without running it.

`nodus check --staged`. The register is `nodus/support/staged_flips.json`, the
same file `nodus_gate --flips` checks against `src/` -- one list, so the report
cannot enumerate a different set of flips than the tree promises.

**Four of the five are answerable from source. One is not, and this says so.**
That is the whole design (`docs/design/v6/01-readiness.md` gate G3): a report
that looks complete and is not would be the failure #797 already taught this
project to distrust -- a notice can be careful, correct, and still leave someone
believing something false. Every flip appears in the output with its status,
including the one nothing looked at.

| flip | how |
|---|---|
| `unknown-type-name` | the parser records them; this reads what `check` already produces |
| `concurrent-write` | which step writes which cell, against the graph's ordering |
| `worker-dispatcher` | `worker:` declarations, reported rather than judged |
| `default-store-sqlite` | a filesystem question: does the local store hold runs |
| `record-equality` | **not checkable from source** -- needs both `==` operands' runtime types |
| `rebuild-effect` | top-level effects outside `main` in a file that can be rebuilt: builtins, stdlib wrappers, declared `extern` host functions; a run's report adds undeclared host functions |

The concurrent-write check is worth understanding, because its answer is
*stronger* than the runtime warning's. Which step writes which cell is known at
lowering time, and so is the ordering relation, so this reports every pair that
could race on some interleaving. The runtime warning reports the pair that
raced on the interleaving that happened. Measured on a three-step probe, this
found a pair the run did not.
"""

from __future__ import annotations

import functools
import json
import os
from dataclasses import dataclass, field
from pathlib import Path

from nodus.frontend.lexer import tokenize
from nodus.frontend.parser import Parser
from nodus.orchestration.workflow_state import (
    DEFAULT_STATE_MERGE,
    FOLD_STATE_MERGE_POLICIES,
)
from nodus.support.staging import read_staged_flip_report, report_path

_REGISTER = Path(__file__).resolve().parent.parent / "support" / "staged_flips.json"

#: Flips this module can answer from source. Anything in the register and not
#: here is reported as unchecked -- deliberately, so adding a sixth flip to the
#: register makes the report say "nobody looked at this" rather than omit it.
_STATIC = {
    "unknown-type-name",
    "concurrent-write",
    "worker-dispatcher",
    "default-store-sqlite",
    "rebuild-effect",
}

#: Checked from source *and* merged with what runs observed. A static check
#: here sees builtins, stdlib wrappers and declared `extern` host functions,
#: but a host function called without an `extern` declaration is only visible
#: when it runs, so a run's report adds to the source scan rather than being
#: discarded by it (#922).
_STATIC_AND_OBSERVED = {"rebuild-effect"}

# v6-flip: concurrent-write
#: A cell whose declaration says the author meant it: explicit last-write-wins,
#: or a fold that combines rather than loses. Same rule the runtime warning
#: uses, read from the declaration instead of the run.
#:
#: Derived from the vocabulary rather than re-listed -- `nodus_gate --shapes`
#: reported the hand-written version as a new species-B instance the moment it
#: landed, against `STATE_MERGE_POLICIES` in `workflow_state.py`, which is
#: exactly right: two lists of the same words with nothing keeping them equal.
#: `once` is deliberately not here -- it already *errors* on a concurrent
#: write today, so it is not something 6.0.0 changes.
_SILENCING_MERGES = frozenset({DEFAULT_STATE_MERGE, *FOLD_STATE_MERGE_POLICIES})


@dataclass
class Finding:
    flip: str
    where: str
    message: str
    line: int | None = None
    col: int | None = None

    def render(self) -> str:
        if self.line:
            position = f"{self.where}:{self.line}:{self.col or 1}"
        else:
            position = self.where
        return f"{position}: {self.message}"


@dataclass
class FlipReport:
    name: str
    issue: object
    summary: str
    checked: bool
    findings: list = field(default_factory=list)
    observed: int = 0
    reason: str = ""


@dataclass
class ReadinessReport:
    target: str = ""
    roots: list = field(default_factory=list)
    flips: list = field(default_factory=list)
    observed_report: bool = False
    error: str | None = None

    @property
    def findings(self) -> list:
        return [f for flip in self.flips for f in flip.findings]

    @property
    def unchecked(self) -> list:
        return [flip for flip in self.flips if not flip.checked]


def load_register(path: Path | None = None) -> tuple[dict, str | None]:
    """The staged-flip register, as shipped inside the package."""
    target = path or _REGISTER
    try:
        data = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return {}, f"staged-flip register could not be read: {target}: {exc}"
    flips = data.get("flips")
    if not isinstance(flips, dict):
        return {}, f"staged-flip register has no 'flips' object: {target}"
    return data, None


def _flow_defs(nodes):
    """Every workflow/goal declaration, including nested ones."""
    for node in nodes or ():
        if type(node).__name__ in {"WorkflowDef", "GoalDef"}:
            yield node
        for attr in ("body", "stmts"):
            inner = getattr(node, attr, None)
            if isinstance(inner, list):
                yield from _flow_defs(inner)


def _step_option(step, key: str):
    """A literal option off `step ... with { key: "value" }`, or None."""
    options = getattr(step, "options", None)
    for entry in getattr(options, "items", None) or ():
        name, value = entry
        if getattr(name, "v", None) == key:
            return getattr(value, "v", None)
    return None


def _declared_merge(state_decl):
    options = getattr(state_decl, "options", None)
    for entry in getattr(options, "items", None) or ():
        name, value = entry
        if getattr(name, "v", None) == "merge":
            return getattr(value, "v", None)
    return None


def _cell_writes(flow) -> dict:
    """`step name -> cells it writes`, from the lowering's own walk.

    Deliberately reuses `_StateRewriter` rather than walking the AST again:
    "what does this step body do with state cells" is one question, and
    answering it a second time here is the shape `nodus_gate --shapes` reports.
    """
    from nodus.orchestration.workflow_lowering import _StateRewriter

    cells = {str(getattr(s, "name", s)) for s in (getattr(flow, "states", None) or [])}
    usage = {}
    for step in flow.steps:
        rewriter = _StateRewriter(
            cells,
            "__workflow_state",
            initial_locals=set(step.deps or []),
            tracked_cells=cells,
        )
        rewriter.rewrite_stmt(step.body)
        usage[step.name] = frozenset(rewriter.cell_writes)
    return usage


def _unordered_pairs(flow, writers: dict) -> list:
    """Co-writers of one cell that nothing orders relative to each other."""
    forward = [s for s in flow.steps if getattr(s, "compensates", None) is None]
    direct = {s.name: set(s.deps or []) for s in forward}

    def ancestors(name, seen=frozenset()):
        found = set()
        for dep in direct.get(name, ()):
            if dep in seen:
                continue
            found.add(dep)
            found |= ancestors(dep, seen | {dep})
        return found

    out = []
    for cell, names in sorted(writers.items()):
        ordered = sorted(names)
        for i, a in enumerate(ordered):
            for b in ordered[i + 1:]:
                if b in ancestors(a) or a in ancestors(b):
                    continue
                out.append((cell, a, b))
    return out


#: A file that calls one of these, or declares a workflow or goal, can be
#: rebuilt: its stored source is re-run when one of its runs is resumed.
_REBUILD_ENTRY_CALLS = frozenset({"run_workflow", "run_goal", "durable_spawn"})
_STDLIB_DIR = Path(__file__).resolve().parent.parent / "stdlib"


def _children(node):
    """Child AST nodes of `node`, through its fields and lists."""
    for value in vars(node).values() if hasattr(node, "__dict__") else ():
        for child in (value if isinstance(value, list) else [value]):
            if hasattr(child, "__dict__") and type(child).__module__.endswith("ast_nodes"):
                yield child


def _walk_ast(node):
    yield node
    for child in _children(node):
        yield from _walk_ast(child)


@functools.lru_cache(maxsize=None)
def _stdlib_effects(module: str) -> dict:
    """`fn name -> effect builtin it calls`, for `std:<module>`, read from its source.

    Read rather than listed, so a stdlib wrapper added or changed later is
    classified by what it actually calls, with the runtime's own rule.
    """
    from nodus.frontend.ast.ast_nodes import Call, FnDef, Var
    from nodus.runtime.rebuild_effects import is_rebuild_effect

    path = _STDLIB_DIR / f"{module}.nd"
    try:
        tree = Parser(tokenize(path.read_text(encoding="utf-8"))).parse()
    except Exception:
        return {}
    effects: dict = {}
    for fn in tree:
        if not isinstance(fn, FnDef):
            continue
        for node in _walk_ast(fn.body):
            if (isinstance(node, Call) and isinstance(node.callee, Var)
                    and is_rebuild_effect(node.callee.name)):
                effects[fn.name] = node.callee.name
                break
    return effects


def _call_start(call):
    """(line, col) of the start of what `call` calls (#921's rule)."""
    from nodus.frontend.ast.ast_nodes import Attr, Call, Index
    node = call.callee
    while isinstance(node, (Attr, Call, Index)):
        if isinstance(node, Attr):
            node = node.obj
        elif isinstance(node, Index):
            node = node.seq
        else:
            node = node.callee
    tok = getattr(node, "_tok", None) or getattr(call, "_tok", None)
    return (tok.line, tok.col) if tok is not None else (None, None)


def _rebuild_effect_findings(path: str, tree) -> list:
    """Top-level effects a rebuild of this file would run again (#922, flip #917).

    What runs when a stored run is resumed is the program's top level, minus
    `main` and the scheduling builtins (#909). So: every statement outside a
    function body, and the body of every same-file function those statements
    call, except `main`. Closures are not entered -- defining one runs nothing,
    and one handed to `spawn` is not started by a rebuild.
    """
    from nodus.frontend.ast.ast_nodes import (
        Attr, Call, ExportList, ExprStmt, ExternDecl, FnDef, FnExpr, GoalDef,
        GoalPursuit, Import, Var, WorkflowDef,
    )
    from nodus.runtime.rebuild_effects import is_rebuild_effect

    rebuildable = any(isinstance(node, (WorkflowDef, GoalDef, GoalPursuit)) for node in tree) or any(
        isinstance(node, Call) and isinstance(node.callee, Var)
        and node.callee.name in _REBUILD_ENTRY_CALLS
        for root in tree for node in _walk_ast(root))
    if not rebuildable:
        return []

    functions = {node.name: node for node in tree if isinstance(node, FnDef)}
    externs = {node.name for node in tree if isinstance(node, ExternDecl)}
    std_aliases = {}
    for node in tree:
        if isinstance(node, Import) and node.path.startswith("std:"):
            module = node.path[len("std:"):]
            std_aliases[node.alias or module.split("/")[-1]] = module

    found: list = []
    entered: set = set()

    def report(call, what: str, via, host: bool) -> None:
        line, col = _call_start(call)
        where = f" (in `{via}`, called at top level)" if via else ""
        remedy = ("move the call into `fn main()`, or have the host register the "
                  "function with `rebuild_safe=True` if it only reads"
                  if host else "move the call into `fn main()`, which a rebuild skips")
        kind = "host function" if host else "call to"
        # v6-flip: rebuild-effect
        found.append(Finding(
            "rebuild-effect", path,
            f"top-level {kind} {what}{where} runs again each time a stored run of "
            f"this program is resumed, and is refused at 6.0.0; {remedy}.",
            line=line, col=col,
        ))

    def visit(node, via) -> None:
        if isinstance(node, (FnExpr, FnDef)):
            return
        if isinstance(node, Call):
            callee = node.callee
            if isinstance(callee, Var):
                name = callee.name
                if is_rebuild_effect(name):
                    report(node, f"`{name}`", via, host=False)
                elif name in externs:
                    report(node, f"`{name}`", via, host=True)
                elif name in functions and name != "main" and name not in entered:
                    entered.add(name)
                    visit(functions[name].body, via or name)
            elif isinstance(callee, Attr) and isinstance(callee.obj, Var):
                module = std_aliases.get(callee.obj.name)
                builtin = _stdlib_effects(module).get(callee.name) if module else None
                if builtin:
                    report(node, f"`{callee.obj.name}.{callee.name}` (`{builtin}`)", via, host=False)
        for child in _children(node):
            visit(child, via)

    skipped = (FnDef, ExternDecl, Import, ExportList, WorkflowDef, GoalDef, GoalPursuit)
    for stmt in tree:
        if isinstance(stmt, skipped):
            continue
        # A top-level `main()` is skipped by a rebuild (#909); its body is not entered.
        if (isinstance(stmt, ExprStmt) and isinstance(stmt.expr, Call)
                and isinstance(stmt.expr.callee, Var) and stmt.expr.callee.name == "main"):
            continue
        visit(stmt, None)
    return found


def _scan_source(path: str, code: str) -> dict:
    """Per-flip findings for one file's source."""
    findings: dict[str, list] = {"concurrent-write": [], "worker-dispatcher": []}
    ast = Parser(tokenize(code)).parse()
    findings["rebuild-effect"] = _rebuild_effect_findings(path, ast)
    for flow in _flow_defs(ast):
        flow_name = getattr(flow, "name", "?")
        silenced = {
            str(getattr(decl, "name", decl))
            for decl in (getattr(flow, "states", None) or [])
            if _declared_merge(decl) in _SILENCING_MERGES
        }
        usage = _cell_writes(flow)
        writers: dict[str, set] = {}
        for step_name, cells in usage.items():
            for cell in cells:
                writers.setdefault(cell, set()).add(step_name)
        writers = {c: n for c, n in writers.items() if c not in silenced and len(n) > 1}
        # v6-flip: concurrent-write
        for cell, a, b in _unordered_pairs(flow, writers):
            findings["concurrent-write"].append(
                Finding(
                    "concurrent-write", path,
                    f"in workflow '{flow_name}', steps '{a}' and '{b}' both write "
                    f"state '{cell}' and nothing orders them. If they disagree, one "
                    f"update is lost -- an error at 6.0.0. Declare "
                    f"`with {{ merge: \"sum\" }}` (or \"append\") to combine them, "
                    f"or `merge: \"any\"` for deliberate last-write-wins.",
                )
            )
        # v6-flip: worker-dispatcher
        for step in flow.steps:
            worker = _step_option(step, "worker")
            if worker is None:
                continue
            findings["worker-dispatcher"].append(
                Finding(
                    "worker-dispatcher", path,
                    f"in workflow '{flow_name}', step '{step.name}' declares "
                    f"worker '{worker}'. Run without a registered dispatcher it "
                    f"executes in-process with no isolation, which is an error at "
                    f"6.0.0. Run under `nodus serve` with a registered worker, or "
                    f"pass `worker_dispatcher=` to NodusRuntime.",
                )
            )
    return findings


def _local_store_findings(project_root: str | None) -> list:
    """Does an unconfigured local workflow store hold runs? (#174/#797)

    Not a source question. The same three conditions the runtime notice uses,
    asked of the filesystem instead of a live store -- a project that chose
    `local` means it, and one with no runs has nothing to migrate.
    """
    if os.environ.get("NODUS_WORKFLOW_STORE_BACKEND"):
        return []
    root = project_root or os.getcwd()
    runs = Path(root) / ".nodus" / "workflow_framework" / "runs"
    try:
        count = sum(1 for entry in runs.iterdir() if entry.suffix == ".json")
    except OSError:
        return []
    if not count:
        return []
    # v6-flip: default-store-sqlite
    return [
        Finding(
            "default-store-sqlite", str(runs),
            f"{count} run record(s) in the file-backed JSON store, which is not "
            f"the default at 6.0.0. Runs recorded here are not visible to a "
            f"SQLite store, so an in-flight waiting run would become unresumable "
            f"rather than move. Migrate with "
            f"`nodus workflow migrate-store --to sqlite` (non-destructive, has a "
            f"real --dry-run), or set NODUS_WORKFLOW_STORE_BACKEND=local to keep "
            f"the JSON store deliberately.",
        )
    ]


def scan(
    *,
    sources: list[tuple[str, str]],
    type_warnings: list[dict] | None = None,
    project_root: str | None = None,
    register_path: Path | None = None,
    dynamic_report: str | None = None,
) -> ReadinessReport:
    """Build the readiness report.

    `sources` is `(path, code)` for each file walked; `type_warnings` is what
    `check_source` already produced for #609, passed in rather than recomputed.
    `dynamic_report` overrides `NODUS_STAGED_FLIP_REPORT` for tests.
    """
    report = ReadinessReport()
    data, error = load_register(register_path)
    if error:
        report.error = error
        return report
    report.target = str(data.get("target", "the next major"))
    report.roots = [path for path, _ in sources]

    collected: dict[str, list] = {}
    for path, code in sources:
        try:
            found = _scan_source(path, code)
        except Exception:
            # A file that does not parse is `check`'s own error to report, and
            # it has already reported it. Readiness says nothing about it rather
            # than claiming a clean scan of a file it could not read.
            continue
        for flip, items in found.items():
            collected.setdefault(flip, []).extend(items)

    collected["unknown-type-name"] = [
        Finding(
            "unknown-type-name",
            str(warning.get("file", report.roots[0] if report.roots else "?")),
            str(warning.get("message", "")),
            line=warning.get("line"),
            col=warning.get("column"),
        )
        for warning in (type_warnings or [])
    ]
    collected["default-store-sqlite"] = _local_store_findings(project_root)

    # What earlier runs actually hit, if anyone asked for a report. This is the
    # only answer #545 has, and it *upgrades* a flip from "not checked" to
    # "checked by running" rather than being merged into the static findings --
    # the distinction matters, because a dynamic result covers the paths that
    # ran and a static one covers the source.
    observed: dict[str, list] = {}
    for record in read_staged_flip_report(dynamic_report):
        observed.setdefault(record["flip"], []).append(
            Finding(
                record["flip"],
                str(record.get("where") or "(observed at run time)"),
                str(record.get("message", "")),
            )
        )
    report.observed_report = bool(observed) or bool(dynamic_report or report_path())

    for name, entry in sorted((data.get("flips") or {}).items()):
        entry = entry or {}
        seen = observed.get(name, [])
        checked = name in _STATIC or bool(seen)
        findings = list(collected.get(name, []))
        if name not in _STATIC or name in _STATIC_AND_OBSERVED:
            findings.extend(seen)
        report.flips.append(
            FlipReport(
                name=name,
                issue=entry.get("issue", "?"),
                summary=str(entry.get("summary", "")),
                checked=checked,
                findings=findings,
                observed=len(seen),
                reason="" if checked else _unchecked_reason(name),
            )
        )
    return report


def _unchecked_reason(name: str) -> str:
    if name == "record-equality":
        return (
            "not checkable from source: it depends on the runtime type of both "
            "`==` operands, and annotations are optional and unenforced. Run the "
            "program or its tests with NODUS_STAGED_FLIP_REPORT=<path> set, then "
            "re-run this -- the warning fires exactly when a comparison's answer "
            "will change, and what it finds is reported here"
        )
    return "no static check is implemented for this flip"
