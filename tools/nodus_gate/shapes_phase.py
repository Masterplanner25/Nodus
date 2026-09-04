"""Shapes phase: the recurring bug shape, caught the day it is introduced.

This codebase's most common defect is not a wrong check. It is **a correct check
that only one of several paths goes through** — twenty-one instances across
v5.0.0-5.4.0, catalogued in CLAUDE.md. Every one was found the same way: a bug
report, then a human asking "what else has this shape?".

This phase asks that question mechanically. It does not find bugs; it finds
*places where one question is answered in more than one voice*, which is where
the bugs have come from. Four species leave a syntactic trace:

  A. **One question, N implementations.** `resolve_import_path` exists twice, 159
     lines and 55, and the short one has no entry-point lookup — so a pip-installed
     companion import resolves at runtime and reads as "Import not found" in the
     editor (#598). `_walk_stmt` exists twice, and #401 fixed one of them (#597).
     Detected as: same name, same parameter list, ≥2 files, non-trivial bodies.

  B. **One vocabulary, two enumerations, already drifted.** `_StateRewriter` knew
     `=`, `x[i] =` and `x.f =` but not `+=` (#518); four sites enumerated
     declaration forms and three had never heard of `goal … over …` (#487).
     Detected as: two collections of string literals where one is a strict subset
     of a comparable-sized other.

  B=. **The same, still in agreement** (#685). B fires only *after* a vocabulary
     diverges, which is the expensive half: the pre-drift state is the one where
     the fix is a single import. Two equal enumerations are still two voices; they
     happen to be saying the same thing today, and nothing makes them. Detected
     as: two *module-level named constants* with equal string members, related
     names, and at least `MIN_EQUAL_MEMBERS` of them. An alias
     (`B = A`) is not a literal and is never collected -- an alias is the fix, and
     a detector that flagged the fixed state would teach people to silence it.

  D. **Process-global state, shared by every participant.** Per-tenant memory and
     run ownership were module-scope globals, so every runtime in a process shared
     them (#185/#390). Detected as: a module-level name rebound via `global`, or a
     mutable container mutated in place.

Species C (a cache is a sibling path — #453, #521, #400, #394) and E (the bound is
on the wrong substrate — #424, #596) are **not** detected. C needs to know which
inputs a cache key *should* include, and E is a design insight. Both are recorded
here so the absence is deliberate rather than an oversight.

**Advisory by default**, like `--consumers`. A duplicated question is a design
debt, not a broken tree, and blocking an unrelated merge on it would get the phase
switched off. `--strict` fails.

**Everything currently in the tree is in the manifest.** That is the whole design:
the value is not the present list, it is that the *next* duplicated question shows
up as NEW against a recorded baseline instead of surfacing as issue #23 of the
series. An entry needs a stated reason — `intentional` for a real protocol,
`tracked` for a known debt with an issue. "Looks fine" is how a real one gets lost,
which is the lesson `tools/dependent_flakes.json` already carries.
"""

from __future__ import annotations

import ast
import io
import json
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

MANIFEST = Path("tools") / "shape_manifest.json"

# Species A: below this many statements a shared name is a coincidence, not a
# shared decision. Tuned against the known instances: the smallest true positive
# (`try_resolve_with_extensions`) has 9.
MIN_BODY_STATEMENTS = 8

# Species B: two collections are the *same* vocabulary only if comparable in size.
# A 6-member list inside a 120-member one is two different things. The real
# instances were 3-of-4 (#518) and 4-of-8 (#473).
MIN_SUBSET_RATIO = 0.6
MAX_MISSING_MEMBERS = 4

# Species B=: two *equal* vocabularies. Equality alone is far too weak a signal,
# so this is a floor beneath the name-stem test, not the discriminator. Tuned
# against the motivating instance (#685): the run-status pair had 5 members.
MIN_EQUAL_MEMBERS = 4

MUTATING_METHODS = {"append", "update", "add", "pop", "clear",
                    "setdefault", "extend", "remove", "discard"}


@dataclass
class Finding:
    species: str
    key: str
    summary: str
    detail: list[str] = field(default_factory=list)
    verdict: str | None = None   # "intentional" / "tracked" when in the manifest
    why: str = ""
    sites: int = 0
    recorded_sites: int | None = None

    @property
    def is_new(self) -> bool:
        return self.verdict is None

    @property
    def grew(self) -> bool:
        """A known duplication that has gained another implementation.

        Without this the phase has a hole: the key is name+params, so adding a
        THIRD copy of an already-tracked function matched the existing entry and
        said nothing. Caught by probing the detector with a deliberate duplicate
        of `resolve_import_path` -- which is already in the manifest -- and
        watching it report 0 new.
        """
        return (self.recorded_sites is not None
                and self.sites > self.recorded_sites)


@dataclass
class ShapesResult:
    findings: list[Finding] = field(default_factory=list)
    error: str | None = None
    scanned: int = 0

    @property
    def new(self) -> list[Finding]:
        return [f for f in self.findings if f.is_new]

    @property
    def grown(self) -> list[Finding]:
        return [f for f in self.findings if f.grew]

    @property
    def known(self) -> list[Finding]:
        return [f for f in self.findings if not f.is_new]

    @property
    def stale_entries(self) -> list[str]:
        """Manifest entries nothing matches any more — the debt was paid."""
        return getattr(self, "_stale", [])


def _modules(root):
    src = Path(root) / "src"
    for path in sorted(src.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        try:
            source = io.open(path, encoding="utf-8").read()
            yield path.relative_to(root).as_posix(), ast.parse(source)
        except (SyntaxError, UnicodeDecodeError, OSError):
            continue


def _param_names(fn: ast.AST) -> tuple[str, ...]:
    args = fn.args
    names = [p.arg for p in (args.posonlyargs + args.args + args.kwonlyargs)]
    return tuple(n for n in names if n not in ("self", "cls"))


def _species_a(trees) -> list[Finding]:
    """One question, N implementations.

    Same name *and* same parameter list is the discriminator that matters. Name
    alone gives 84 hits here, nearly all coincidence (`write`, `visit`, `check`);
    adding the parameter list cuts it to 22 and keeps every known true positive.
    Two functions that take the same arguments under the same name are answering
    the same question, whatever their bodies say.
    """
    by_key: dict[tuple, list] = defaultdict(list)
    for rel, tree in trees:
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            if node.name.startswith("__"):
                continue
            statements = len([s for s in ast.walk(node) if isinstance(s, ast.stmt)])
            by_key[(node.name, _param_names(node))].append((rel, node.lineno, statements))

    findings = []
    for (name, params), sites in sorted(by_key.items()):
        # The size threshold filters *sites*, not the group (#736). It used to
        # be `if any(n < MIN_BODY_STATEMENTS ...): continue` -- a whole-group
        # veto, so one small sibling hid every real implementation beside it. A
        # trivial body is not evidence of a duplicated question; a trivial body
        # next to two substantial ones is not evidence of its absence.
        #
        # It hid three groups here, two of them genuine: `_root_vm(vm)` in three
        # builtin modules, byte-identical, one of them documented as a copy of
        # another; and `run()` byte-identical across the DAP and LSP servers. The
        # veto scales with the number of small same-named functions in the tree,
        # so the detector was quietly weakening as the codebase grew -- while
        # reporting `0 new`, which is the reading that costs most.
        sites = [site for site in sites if site[2] >= MIN_BODY_STATEMENTS]
        if len(sites) < 2 or len({rel for rel, _, _ in sites}) < 2:
            continue
        key = f"A:{name}({','.join(params)})"
        where = [f"{rel}:{line} ({n} stmts)" for rel, line, n in sites]
        findings.append(Finding(
            species="A",
            key=key,
            summary=f"{name}({', '.join(params)}) implemented in {len(sites)} places",
            detail=where,
            sites=len(sites),
        ))
    return findings


def _string_members(node) -> frozenset[str] | None:
    """The string members of a literal collection, or None if it is not one.

    One answer for both species-B detectors. They ask the same question -- "is
    this expression an enumerated vocabulary of strings?" -- and two copies of it
    would be the shape this file exists to report, in this file.
    """
    elts = None
    if isinstance(node, (ast.Set, ast.List, ast.Tuple)):
        elts = node.elts
    elif (isinstance(node, ast.Call)
          and getattr(node.func, "id", "") in {"frozenset", "set"}
          and node.args
          and isinstance(node.args[0], (ast.Set, ast.List, ast.Tuple))):
        elts = node.args[0].elts
    if not elts:
        return None
    values = [e.value for e in elts
              if isinstance(e, ast.Constant) and isinstance(e.value, str)]
    if len(values) < 3 or len(values) != len(elts):
        return None
    return frozenset(values)


def _literal_collections(trees):
    for rel, tree in trees:
        for node in ast.walk(tree):
            members = _string_members(node)
            if members is not None:
                yield rel, node.lineno, members


def _module_constants(trees):
    """Module-level names bound to a literal collection of strings.

    Deliberately narrower than `_literal_collections`, and the narrowing is the
    signal. A *named* vocabulary at module scope is a declaration that something
    is the set; an anonymous literal inside an expression is usually an argument.
    Comparing every equal anonymous pair in `src/` would report `{"true","false"}`
    against itself all day.

    An alias -- `_REHYDRATABLE_STATUSES = REHYDRATABLE_RUN_STATUSES` -- has an
    `ast.Name` value, not a literal, so it is not collected. That matters: an
    alias is the *fix* for this shape, and a detector that flagged the fixed state
    would train people to silence it.
    """
    for rel, tree in trees:
        for node in tree.body:
            if (isinstance(node, ast.Assign)
                    and len(node.targets) == 1
                    and isinstance(node.targets[0], ast.Name)):
                name, value = node.targets[0].id, node.value
            elif (isinstance(node, ast.AnnAssign)
                  and isinstance(node.target, ast.Name)
                  and node.value is not None):
                name, value = node.target.id, node.value
            else:
                continue
            members = _string_members(value)
            if members is not None:
                yield rel, node.lineno, name, members


def _name_tokens(name: str) -> frozenset[str]:
    """`_REHYDRATABLE_STATUSES` -> {rehydratable, statuses}."""
    return frozenset(t for t in name.strip("_").lower().split("_") if t)


def _species_b(trees) -> list[Finding]:
    """One vocabulary, two enumerations — one of them short."""
    collections = list(_literal_collections(trees))
    findings = []
    seen: set[str] = set()
    for i, (rel_a, line_a, a) in enumerate(collections):
        for rel_b, line_b, b in collections[i + 1:]:
            if a == b or not (a < b or b < a):
                continue
            short, long_ = (a, b) if a < b else (b, a)
            if len(short) < MIN_SUBSET_RATIO * len(long_):
                continue
            missing = sorted(long_ - short)
            if len(missing) > MAX_MISSING_MEMBERS:
                continue
            # Keyed on file pair and the difference, never line numbers, so the
            # manifest survives an edit above the collection.
            key = f"B:{min(rel_a, rel_b)}|{max(rel_a, rel_b)}|missing={','.join(missing)}"
            if key in seen:
                continue
            seen.add(key)
            findings.append(Finding(
                species="B",
                key=key,
                summary=f"vocabulary in {rel_a}:{line_a} lacks {missing} "
                        f"that {rel_b}:{line_b} has",
                detail=[f"{rel_a}:{line_a}", f"{rel_b}:{line_b}",
                        f"missing: {', '.join(missing)}"],
            ))
    return findings


def _species_b_equal(trees) -> list[Finding]:
    """One vocabulary, two enumerations that still agree (#685).

    Species B above requires one set to be a strict subset of the other, so it
    reports a vocabulary that has **already drifted** and is silent on one that
    is **about to**. That is backwards: the pre-drift state is the cheaper one to
    fix and the only one where the fix is free.

    It is not a missing case so much as half the definition. This file's own
    docstring says the phase finds *places where one question is answered in more
    than one voice* -- two equal enumerations are two voices, they simply happen
    to be saying the same thing today. Nothing makes them agree, so adding a
    member means N edits where the one you miss is silent. #518 (`_StateRewriter`
    without `+=`) and #487 (three of four sites not knowing `goal … over …`) were
    both found by a human *after* the divergence shipped.

    Three discriminators, because equality alone is far too noisy:

      1. **Both are module-level named constants** -- see `_module_constants`.
      2. **The names share a stem**, compared as token sets with leading
         underscores stripped. `REHYDRATABLE_RUN_STATUSES` and
         `_REHYDRATABLE_STATUSES` differ by an underscore and a dropped word;
         two unrelated sets that coincide in members almost never do.
      3. **A size floor**, so two equal three-member sets stay quiet.

    Advisory, like the rest of the phase, and `tools/shape_manifest.json` is
    where a deliberate pair goes -- some equal vocabularies really are two
    questions that happen to share members today.
    """
    constants = list(_module_constants(trees))
    findings = []
    seen: set[str] = set()
    for i, (rel_a, line_a, name_a, a) in enumerate(constants):
        for rel_b, line_b, name_b, b in constants[i + 1:]:
            if a != b or len(a) < MIN_EQUAL_MEMBERS:
                continue
            tokens_a, tokens_b = _name_tokens(name_a), _name_tokens(name_b)
            if not (tokens_a <= tokens_b or tokens_b <= tokens_a):
                continue
            # Keyed on the file pair and both names -- never line numbers, and
            # never the members, so renaming a member does not orphan the entry.
            left, right = sorted([f"{rel_a}::{name_a}", f"{rel_b}::{name_b}"])
            key = f"B=:{left}|{right}"
            if key in seen:
                continue
            seen.add(key)
            findings.append(Finding(
                species="B=",
                key=key,
                summary=f"{name_a} ({rel_a}:{line_a}) and {name_b} "
                        f"({rel_b}:{line_b}) enumerate the same {len(a)} members "
                        f"independently — nothing keeps them in step",
                detail=[f"{rel_a}:{line_a} {name_a}",
                        f"{rel_b}:{line_b} {name_b}",
                        f"members: {', '.join(sorted(a))}"],
            ))
    return findings


def _species_d(trees) -> list[Finding]:
    """Process-global state, shared by every participant."""
    findings = []
    for rel, tree in trees:
        module_level = {}
        for node in tree.body:
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        module_level[target.id] = node
            elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
                module_level[node.target.id] = node

        rebound, mutated = set(), set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Global):
                rebound.update(node.names)
            # A *store* only. `_MONTH_FULL[i]` reading a frozen lookup table is
            # not shared mutable state, and counting reads buried the real hits
            # under a pile of constants.
            if (isinstance(node, ast.Subscript) and isinstance(node.value, ast.Name)
                    and isinstance(node.ctx, (ast.Store, ast.Del))):
                mutated.add(node.value.id)
            if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                    and isinstance(node.func.value, ast.Name)
                    and node.func.attr in MUTATING_METHODS):
                mutated.add(node.func.value.id)

        for name, node in module_level.items():
            if name.startswith("__"):
                continue
            why = []
            if name in rebound:
                why.append("rebound via `global`")
            if name in mutated:
                value = getattr(node, "value", None)
                container = isinstance(value, (ast.Dict, ast.List, ast.Set)) or (
                    isinstance(value, ast.Call)
                    and getattr(value.func, "id", "") in {"dict", "list", "set", "defaultdict"})
                if container:
                    why.append("mutable container, mutated in place")
            if why:
                findings.append(Finding(
                    species="D",
                    key=f"D:{rel}::{name}",
                    summary=f"{name} is process-global state ({'; '.join(why)})",
                    detail=[f"{rel}:{node.lineno}"],
                ))
    return findings


def _load_manifest(root) -> tuple[dict, str | None]:
    path = Path(root) / MANIFEST
    if not path.is_file():
        return {}, f"{MANIFEST.as_posix()} not found — the baseline is what makes a new shape visible"
    try:
        data = json.loads(io.open(path, encoding="utf-8").read())
    except (OSError, json.JSONDecodeError) as exc:
        return {}, f"{MANIFEST.as_posix()} could not be read: {exc}"
    entries = data.get("entries")
    if not isinstance(entries, dict):
        return {}, f"{MANIFEST.as_posix()} has no `entries` object"
    return entries, None


def run_shapes_phase(root) -> ShapesResult:
    # `_find_root()` hands back a str; every other phase takes it as given.
    root = Path(root)
    result = ShapesResult()
    entries, error = _load_manifest(root)
    if error:
        # A manifest that cannot be read is a failure, not a pass. The check is
        # not allowed to succeed by being unable to run -- same rule as
        # `--consumers`, and the same reason.
        result.error = error
        return result

    trees = list(_modules(root))
    result.scanned = len(trees)

    findings = (_species_a(trees) + _species_b(trees)
                + _species_b_equal(trees) + _species_d(trees))
    for finding in findings:
        entry = entries.get(finding.key)
        if isinstance(entry, dict):
            finding.verdict = entry.get("verdict")
            finding.why = entry.get("why", "")
            recorded = entry.get("sites")
            if isinstance(recorded, int):
                finding.recorded_sites = recorded
    result.findings = findings

    matched = {f.key for f in findings}
    result._stale = sorted(k for k in entries if k not in matched)
    return result
