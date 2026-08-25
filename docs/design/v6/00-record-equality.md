# Record equality becomes structural (#545)

**Status: decided 2026-08-25. Staged: warning in the next 5.x release, flip at
6.0.0 alongside #547 (concurrent state writes) and #492 (`worker:`).**

## The problem

`record {x: 1i} == record {x: 1i}` is `false`. The equivalent map is `true`.
Records compare by identity — `Record.__eq__` ends in `self is other` — while
numbers, strings, bools, nil, lists and maps all compare structurally at any
depth. The rule existed only in an `__eq__` body until #551 documented it, and
it has two undocumented exceptions: `datetime` and `duration` records compare
by value.

The trap propagates outward (a map holding a record compares `false` because
the nested records do), and it closed off `merge: "union"` for record
elements: dedup by identity removes nothing, so #485 shipped `union` refusing
records outright rather than silently behaving as `append`.

## The decision

**Option 1 of #545: record `==` becomes structural.** Two records are equal
when their `kind` and their `fields` are, recursing with the same equality
lists and maps already use. `==` is a **Stable** surface, so the flip lands at
6.0.0; until then, a comparison whose answer will change — two distinct
records that field-by-field comparison calls equal — prints a one-time
warning, matching the staging of #547 and #492.

The 6.0.0 semantics are implemented now, as `structural_eq` in
`src/nodus/vm/types.py`. In 5.x it is consulted only to detect divergence; at
6.0.0 `Record.__eq__` delegates to it and the warning is deleted.

## Why this option

- **Consistency is the rule being restored, not invented.** Records are the
  lone non-structural value, and the exception has exceptions. Whichever way
  a user guesses, part of the language contradicts them.
- **The hashing obstacle does not exist.** Records cannot be map keys —
  `is_valid_map_key` restricts keys to strings and numbers — so a structural
  `__eq__` never needs a structural `__hash__` at the language surface.
- **Mutability is no objection.** Records are mutable (`user.age = 31`), but
  so are maps and lists, and those are structural.
- **`union` needs zero new machinery.** `_dedup` (`workflow_state.py`) is
  O(n²) membership via `_nodus_eq`, no hashing; the flip makes union over
  records correct by construction, and the `check_contribution` refusal is
  deleted with it.
- **6.0.0 already exists as a scheduled breaking window** with a warn-now
  cohort, so the cost of the honest fix is unusually low.

The rejected alternative — document identity and add a structural helper —
leaves the natural spelling giving the wrong answer silently, forever, with a
bolt-on giving the right one.

## Sub-decisions

1. **The `datetime` and `duration` carve-outs survive, because they are
   semantics, not implementation accidents.** `datetime` compares by
   **instant**: `epoch_ms` only, zone ignored, so two records for the same
   moment in different zones are equal — naive field comparison would break
   that. `duration` compares by **length**: `total_ms` only (its other fields
   are derived, so this is an optimization rather than a difference). Both are
   now stated in `structural_eq`'s docstring and here, rather than living
   silently in `__eq__`.
2. **Function-valued fields compare by identity**, the way functions compare
   everywhere else in the language. Consequence: a record whose methods are
   built per instance (`std:hash` results, user records with `fn` fields) is
   equal only to itself even after the flip. If that bites for `std:hash`, the
   module can share its `BuiltinMethod` instances across records (or `hash`
   gets a digest carve-out like `datetime`'s) — a follow-up, not part of this
   decision.
3. **`kind` must match.** A user record whose fields happen to mirror a
   `datetime`'s is not equal to it.
4. **Leaf fields compare with the equality nested map values already get** —
   Python `==`, so `1i` equals `1.0` at any depth, matching today's nested-map
   behaviour.
5. **Ordering (`<`, `<=`, `>`, `>=`) is untouched.** It remains defined for
   `datetime`/`duration` pairs only. Only `==`/`!=` change.

## What the flip PR must do (6.0.0)

- `Record.__eq__` delegates to `structural_eq`; delete
  `_warn_structural_eq_change` and the flag. Cycles already terminate
  (pair-tracking, coinductive); an extremely deep non-cyclic structure raises
  `RecursionError` exactly as Python's own list/map equality does today, which
  is the consistent answer. The 5.x staging check swallows that error instead,
  because a warning probe must never change a program's outcome.
- Decide `__hash__`: today it is `id(self)`, which the flip makes inconsistent
  for *Python-side* set/dict use of `Record` (the language surface is
  unaffected — records cannot be map keys). Audit internal uses; the likely
  right answer is `__hash__ = None` unless something in-tree depends on
  hashing records.
- Delete the record refusal in `check_contribution` (`workflow_state.py`) and
  its `_holds_an_incomparable_record` walker; `union` accepts records.
- Rewrite `tests/test_record_equality_staging.py` into tests of the structural
  semantics, keeping the `# closes: #545` marker.
- Update `docs/guide/types-and-values.md` §"Equality" and
  `docs/design/v4/11-equality-coercion.md`; update the `merge: "union"` docs
  and the #485 error-message reference to this issue.

## The #479 coupling, dissolved

The v5.3.0 handoff suggested deciding this alongside #479, "where a typed cell
would say what element identity means." Examined, the dependency runs the
other way:

- The static type vocabulary (`frontend/type_system.py`) is flat — `any, int,
  float, string, bool, list, record, function, nil`; no `list<T>`, no map
  type, no record shapes. A cell type that could *express* element identity is
  a type-system project #479 does not propose.
- A typed cell would fix only `union`; ordinary `a == b` would stay a trap.
- Cell merging is runtime and cross-process; static cell types cannot reach
  `_dedup` without a second, runtime schema vocabulary.

With equality structural, element identity **is** value equality, uniformly,
and cells need no identity declaration. #479 stays what it says it is: static
ergonomics (`returns:` on a step, tool schema derived from the handler's
signature), buildable independently on the flat vocabulary, sharing whatever
schema vocabulary it settles with #472's resume payload.
