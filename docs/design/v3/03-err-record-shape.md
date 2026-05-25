# Design Doc: err Record Shape and Map Key Semantics

**Doc ID:** `docs/design/v3/03-err-record-shape.md`
**Status:** Phase 1 design — proposed
**Author:** Shawn Knight
**Decision date:** 2026-05-24
**Closes:** [#44](https://github.com/Masterplanner25/Nodus/issues/44) (BUG-043), [#41](https://github.com/Masterplanner25/Nodus/issues/41) (BUG-040)
**Cross-reference:** V3_0_PLAN.md §1.A design question 3

---

## 1. Problem statement

Two related issues affect the shape contract of Nodus records and maps. Both involve implicit behavior that users have hit and reported as bugs.

### 1.1 BUG-043: err.payload absent vs nil mismatch

The err record contract is documented as having a `payload` field for attached structured data. In practice, the field is sometimes absent from the record entirely and sometimes present with value `nil`. Concrete failure:

```nodus
let r = some_op()
if not r.ok {
    print(r.err.payload)   // sometimes prints nil, sometimes throws "no such field: payload"
}
```

Users cannot write reliable code against the err contract because the shape is unstable.

### 1.2 BUG-040: bare identifier map keys

Map literal syntax accepts bare identifiers as keys. The behavior surprises users:

```nodus
let key = "foo"
let m = {key: "bar"}
// produces: {"foo": "bar"}  -- key was evaluated as a variable
// users from Python/JS expect: {"key": "bar"}  -- key as literal string
```

The current behavior is not wrong per se — it's a design choice — but the v2.1.1 handoff flagged it as a sharp edge that users keep hitting. There's no syntax to make a literal map with key `"key"` other than quoting it explicitly, but bare identifiers silently shadow that intent.

### 1.3 Why combine these issues

Both touch the shape of records and maps. The err record is itself a record-with-a-map-payload, so the two decisions interact:

- If `err.payload` is always present, what shape does it take when it holds structured data?
- If structured data uses map literals, how do users write reliable map literals?

Treating these as one design avoids inconsistent decisions across the two issues.

### 1.4 What this doc does NOT do

- Change the records vs maps distinction itself. Records remain fixed-shape, maps remain dynamic. The boundary is unchanged.
- Add type annotations or schemas to records or maps. Untyped semantics preserved.
- Touch other err.* fields beyond `payload`. The full err record audit (BUG-044) lives in Phase 2.

---

## 2. Decision summary

| Item | Locked value |
|------|--------------|
| `err.payload` shape | Always present on every err record. Defaults to `nil`. |
| `err.payload` type | Either `nil` or a map. Never a record, list, scalar, or other shape. |
| Bare identifier map keys | **Syntax error at parse time.** Map keys must be string literals, variable expressions in parens, or explicit string-coerced values. |
| Variable as map key | Wrap in parens: `{(key): "bar"}` |
| Literal string key | Quote it: `{"key": "bar"}` |
| Migration path | Mechanical: find `{ident: value}` patterns, decide intent, rewrite. Parser error message points at the fix. |

---

## 3. err.payload contract

### 3.1 Shape

Every err record has a `payload` field. The field is always present. Its value is one of:

- `nil` — no structured data attached (the common case)
- A map (string keys, any values) — structured data attached

No other shape is permitted. err.payload is never a list, scalar, record, or function value.

### 3.2 Why always present

Records in Nodus have fixed shape. If `err.payload` is sometimes absent, then err is not actually one record type — it's a family of record types with overlapping fields. That breaks the mental model:

```nodus
// Should this work?
if err.payload != nil { use(err.payload) }
// If payload is sometimes absent, this throws "no such field" instead of evaluating the comparison.
```

Always-present-defaults-nil keeps the comparison sound. Users write the natural code; the language behaves predictably.

### 3.3 Why nil vs absent matters for migration

This is a breaking change for v3.x. Code that currently does:

```nodus
if has_key(err, "payload") { ... }
```

becomes:

```nodus
if err.payload != nil { ... }
```

The `has_key(err, "payload")` form is no longer meaningful because the answer is always `true`. The migration is mechanical and the v2→v3 migration guide will list the pattern.

### 3.4 Why map (not record) for the payload value

When err.payload holds structured data, it's a map, not a record. Reasoning:

1. Error sites in the stdlib (per design doc 2's mapping tables) attach varying structured data. A `parse_error` from JSON might attach `{"line": 5, "column": 12}`. A `type_error` from `math.idiv` might attach `{"got": "float", "expected": "int"}`. These shapes are unrelated. Forcing them into a single record type would either bloat the record with always-nil fields, or split err.payload across multiple record types — neither is good.

2. User code that reads err.payload typically wants to look up specific keys, not assume a fixed shape. Map semantics match the access pattern.

3. Map keys in err.payload are always strings (per §4 below). Users can rely on string-keyed access.

### 3.5 Documented payload keys per err.kind

Phase 4 documentation lists, for each err.kind defined in design doc 2, which payload keys may be present. Example excerpt for `parse_error`:

```
err.kind == "parse_error"
err.payload may contain:
  "input"  (string)  -- the input that failed to parse, when applicable
  "line"   (int)     -- line number, when applicable
  "column" (int)     -- column number, when applicable
  "reason" (string)  -- short reason fragment, when applicable
err.payload may be nil if no structured data is attached
```

This documentation is per-err.kind in `error-handling.md`. Stdlib functions that produce err records must populate the documented keys when the information is available.

---

## 4. Map literal key syntax

### 4.1 Current (v2.x) behavior

Map literals accept bare identifiers as keys:

```nodus
let key = "foo"
let m = {key: "bar"}
// m == {"foo": "bar"}  -- key was evaluated as the variable
```

There is no syntax for a literal string key matching a variable name in scope. Users must quote: `{"key": "bar"}`.

### 4.2 New (v3.0) behavior

**Bare identifiers in map literal key position are a parse error.** The parser refuses to accept `{ident: value}` and emits a specific error message pointing at the fix.

Valid map key syntaxes in v3.0:

```nodus
{"foo": "bar"}              // literal string key
{(key): "bar"}              // variable expression in parens — evaluates `key`
{strings.upper("foo"): "bar"}  // any expression in parens — but parens not required if it's already a non-identifier expression like a function call
```

Wait — that last form needs a decision. Two sub-options:

- **Strict:** any non-string-literal key requires parens. `{strings.upper("foo"): "bar"}` is a parse error; must be `{(strings.upper("foo")): "bar"}`.
- **Lenient:** only bare identifiers require parens. Function calls and other complex expressions are allowed unparenthesized.

The strict version is more consistent but more verbose. The lenient version is friendlier but requires the parser to distinguish "bare identifier" from "more complex expression starting with identifier" — which is a real distinction the parser can make.

**My lock: lenient.** Only bare single identifiers require parens. `{strings.upper("foo"): "bar"}` is valid because `strings.upper("foo")` is a function call, not a bare identifier. The rule is: "a key that is exactly one identifier token must be parenthesized." Function calls, indexed access, and other expressions are fine.

### 4.3 Parser error message

When the parser encounters a bare identifier in map key position, it emits:

```
parse error at line N column M: bare identifier "foo" cannot be a map key.
  - to use the variable's value as the key, write: {(foo): ...}
  - to use the literal string "foo" as the key, write: {"foo": ...}
```

The error explicitly lists both fixes. Users don't have to read the migration guide to resolve the error.

### 4.4 Record vs map literal disambiguation

Records use `{field: value}` syntax with bare identifiers as field names. This is unchanged. The parser distinguishes records from maps by context — record literals are typed at the use site, map literals are introduced by collection-context syntax or by explicit `map{...}` syntax.

But wait — that's not how current Nodus works. Per the v2.1.1 handoff and BUG-030, "unquoted keys silently make records not maps." That means the syntax `{key: value}` is currently a record literal if the key is a bare identifier, and a map literal if the key is quoted.

This design doc must clarify the disambiguation rule going forward. Two options:

- **Option A: syntax fully determines record vs map.** Bare-identifier keys → record. Quoted keys → map. Mixed keys are a parse error.
- **Option B: explicit constructor required for maps.** `map{...}` for maps, `{...}` always for records. Bare-identifier rule from §4.2 becomes "fields in records must be bare identifiers; map literals must use `map{...}` syntax."

Option A preserves the current implicit distinction but bans bare-identifier confusion within maps. Option B is more explicit but adds new syntax and requires migration of every map literal.

**My lock: Option A.** Reasoning:

1. Option B is too disruptive — every existing map literal needs rewriting. That's a much bigger migration than this doc otherwise creates.
2. The "syntax determines shape" rule is teachable: bare identifiers mean record, quoted keys mean map.
3. With bare identifiers banned from map key position (per §4.2), the rule is unambiguous: `{foo: bar}` is a record literal with field `foo`. `{"foo": bar}` is a map literal with key `"foo"`. `{(foo): bar}` is a map literal with key evaluated from variable `foo`. Mixed-form literals like `{foo: 1, "bar": 2}` are a parse error because they're ambiguous.

### 4.5 Migration patterns

The v2→v3 migration guide lists the common patterns:

```nodus
// v2.x ambiguous map literal — was a record, user wanted a map
let config = {host: "localhost", port: 8080}
// In v2.x this was a RECORD with fields `host` and `port`.
// If the user wanted a map, v3.0 requires explicit:
let config = {"host": "localhost", "port": 8080}  // now a map

// v2.x map literal with variable key — was actually working
let key = "foo"
let m = {key: "bar"}
// In v2.x this was a record-or-map (BUG-040) and surprised users.
// v3.0 requires explicit:
let m = {(key): "bar"}  // map with variable key
// or:
let m = {"key": "bar"}  // literal string key
```

The first pattern is the silent-breakage case — code that worked as a record in v2.x because the user wrote it like a Python dict but Nodus interpreted it as a record. v3.0 doesn't break this code (it still parses as a record), but the migration guide must warn users to audit map-like literals to confirm intent.

### 4.6 Parser changes required

The parser must:

1. Detect bare identifier in map-literal key position. "Map-literal context" is determined by the keys observed so far — once a quoted key appears, the literal is a map and bare identifiers are illegal as keys.
2. Detect mixed-form literals (some quoted keys, some bare). Emit parse error.
3. Emit the error message from §4.3 with the offending identifier.

These are local parser changes, not grammar restructuring. The current parser already distinguishes records from maps by key form; this doc tightens the rule to ban the ambiguous case.

---

## 5. Interactions with design docs 1 and 2

### 5.1 Integer type (doc 1)

No interaction. Integer literals (`1i`) are not valid map keys regardless — keys must be strings. If a user writes `{1: "foo"}`, that's a parse error in v3.0 just as it was in v2.x.

### 5.2 Python error replacement (doc 2)

This doc finalizes the err.payload shape that doc 2 depends on. Doc 2 §5 mapping tables produce err records with documented payload keys per §3.5 above. The Phase 3 implementation of doc 2 must populate payload as a map (per §3.4) using the documented keys.

Specifically:

- `parse_error` payloads use keys `"input"`, `"line"`, `"column"`, `"reason"`
- `type_error` payloads use keys `"got"`, `"expected"`, `"function"`
- `io_error` payloads use keys `"path"`, `"operation"`
- Other kinds use keys documented per err.kind in `error-handling.md`

This per-kind payload key catalog is a Phase 4 documentation deliverable. Phase 3 implementation must follow it.

---

## 6. Implementation outline

High-level only. Phase 3 produces the concrete PRs.

### 6.1 err record construction

- All err record construction in the stdlib goes through a helper function (already part of doc 2's `_err_record()`)
- The helper enforces `payload` is always present, value is `nil` or a map
- Type assertion on construction catches violations during development

### 6.2 Parser changes for map literals

- Update the map literal parsing rule to reject bare identifiers in key position
- Update the record literal parsing rule to accept only bare identifiers in field position
- Mixed-form literal detection: track the form of the first key, reject any key of a different form
- Emit the §4.3 error message with line/column accuracy

### 6.3 Test coverage

Minimum required tests for Phase 3 exit:

- err record always has `payload` field after construction in every stdlib err site
- err record `payload` is `nil` by default; setting it to a non-map type throws (programming error, not user error)
- Parse error fires on `{key: value}` where `key` is a bare identifier in map context
- Parse error message includes both fix suggestions from §4.3
- `{"key": value}` parses as map literal with string key
- `{(key): value}` parses as map literal with variable-keyed entry
- `{key: value}` parses as record literal with field `key` (existing behavior preserved)
- `{key: 1, "other": 2}` parse error (mixed form)
- Function call expressions as map keys work without parens: `{strings.upper("foo"): "bar"}`

### 6.4 Documentation impact (Phase 4)

- Update `types-and-values.md` records vs maps section to reflect the locked rule from §4
- Update `working-with-maps.md` with the new key syntax and migration patterns from §4.5
- Update `error-handling.md` with the locked `err.payload` contract and the per-err.kind payload key catalog from §3.5 and §5.2
- Migration guide section per §7

---

## 7. Migration impact

### 7.1 What breaks

**Map literals with bare identifier keys:** every map literal using bare identifiers as keys must be rewritten. This affects code that:

- Used variable values as keys: `{key: value}` → `{(key): value}`
- Intended literal string keys but wrote them bare: `{key: value}` → `{"key": value}`

**The first case is detectable by parse error.** Users running v3.0 on v2.x code see the parse error from §4.3 and can fix it locally.

**The second case is not detectable** — the code continues to parse as a record literal, which may be wrong if the user intended a map. The migration guide must explicitly call this out and recommend an audit.

**Code that uses `has_key(err, "payload")`:** must change to `err.payload != nil`. The `has_key` form is still valid syntax but always returns `true` for err records, making the check meaningless. Parse-time detection is impossible; runtime behavior change is silent.

### 7.2 What users do

Migration guide section will include:

1. **"err.payload is always present"** — replace `has_key(err, "payload")` with `err.payload != nil`. Provide search-and-replace pattern.
2. **"Map literals with bare keys are now parse errors"** — run v3.0 on existing code; the parser flags every site. Decide per-site whether to quote (`"key"`) or parenthesize (`(key)`).
3. **"Map literals that look like Python dicts may have been records all along"** — audit `{name: value}` patterns to confirm intent. If you wanted a map, quote the keys.
4. **"err.payload is a map when non-nil"** — code reading payload data should use map access patterns.

### 7.3 Backward compatibility surface

- The err record gains stable shape (positive — better for users)
- Map literal syntax gets stricter (negative for migration cost, positive long-term)
- Record literal syntax is unchanged
- No new keywords introduced
- No new operators introduced

---

## 8. Open implementation questions

These do not gate Phase 1 exit but need answers during Phase 3:

1. **Parens vs other syntax for variable keys.** §4.2 locks `(key)`. Alternatives like `[key]` (square brackets, JS-style) or `${key}` (template-style) exist. Parens are the safest because they don't add a new bracket-meaning pair. Confirm during Phase 3.
2. **Empty map literal.** `{}` is currently a parse-time ambiguity (empty record vs empty map). Resolve in Phase 3 — likely declares `{}` as empty record, `map{}` or `{:}` for explicit empty map. Or punt to v3.1.
3. **Map literal with all numeric keys.** `{1: "a", 2: "b"}` was a parse error in v2.x (keys must be strings). v3.0 keeps this restriction; confirm the parse error message is clear.
4. **err.payload immutability.** Should the payload map be immutable once attached, or can scripts mutate it? §3 doesn't specify. Phase 3 decides — likely immutable for safety (errors shouldn't be modifiable after the fact).

---

## 9. Cross-references

- **Phase 0 decision (V3_0_PLAN.md §0a):** no direct decision; this doc resolves the design questions left open for Phase 1
- **Phase 1 design doc 1 (01-integer-type.md):** no interaction (per §5.1)
- **Phase 1 design doc 2 (02-python-error-replacement.md):** depends on this doc's err.payload contract. Doc 2's mapping tables produce err records that must follow §3 shape and §5.2 payload key conventions.
- **Phase 2 BUG-030 ([#31](https://github.com/Masterplanner25/Nodus/issues/31)):** "unquoted keys silently make records not maps" — this doc resolves the underlying ambiguity. BUG-030 becomes a documentation issue (Phase 4) once the parser change ships.
- **Phase 2 BUG-039 ([#40](https://github.com/Masterplanner25/Nodus/issues/40)):** "multi-line map literals fail when value starts on new line" — independent parser bug, Phase 2 Batch 2B. Not affected by this doc's changes.
- **Phase 2 BUG-044 ([#45](https://github.com/Masterplanner25/Nodus/issues/45)):** "err record has 4 undocumented fields" — separate audit issue. This doc only specifies `payload`; the other 3 fields are scope for BUG-044 in Phase 2 Batch 2B.

---

## 10. Exit checklist

Phase 1 exits this design doc when:

- [ ] Doc reviewed and decisions in §2 confirmed final
- [ ] Doc committed to `docs/design/v3/03-err-record-shape.md`
- [ ] [#44](https://github.com/Masterplanner25/Nodus/issues/44) (BUG-043) updated with link to this doc, converted to `phase:3-breaking`
- [ ] [#41](https://github.com/Masterplanner25/Nodus/issues/41) (BUG-040) updated with link to this doc, converted to `phase:3-breaking`
- [ ] BUG-030 ([#31](https://github.com/Masterplanner25/Nodus/issues/31)) re-tagged as documentation issue dependent on this doc's parser change
- [ ] Cross-reference verified with design doc 2 — payload keys per err.kind catalog drafted
- [ ] V3_0_PLAN.md §1.A updated to mark err record shape design doc complete (Phase 1 exits)