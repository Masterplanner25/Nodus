# Nodus v4.0 — Design Doc 13: Err Record Location Fields

**Phase:** 1 (design docs)
**Status:** Locked
**Implements:** Decision 14 (err record location fields) from `00-phase-0-decisions.md`
**Closes:** Issue #78 (BUG-V31E-04)
**Date:** 2026-05-26
**Maintainer:** Shawn Knight (Masterplanner25)

---

## Problem statement

In v3.x, err records returned from stdlib functions and VM operations lack
location information. A user receives an err record and cannot tell which
line of source code produced it. This makes debugging err-propagation
chains tedious and forces users to add their own location bookkeeping.

Issue #78 (BUG-V31E-04) tracked this as a confirmed bug: err records
produced by builtin functions (`std:http`, `std:subprocess`, etc.) have
no `path`, `line`, or `column` fields. The fix requires VM-level
augmentation at the `CALL_BUILTIN` dispatch point.

---

## What Phase 0 already settled

From Decision 14:

- All err records (VM-thrown AND stdlib-returned) get `path`, `line`,
  `column`, `stack`, and `origin` fields
- VM adds these fields at the `CALL_BUILTIN` dispatch point (not in each
  stdlib function)
- `origin` field distinguishes source: `"vm"`, `"stdlib"`, `"user"`
- User-created err records via `err { ... }` syntax get `origin: "user"`
  and the VM fills in location fields if they are absent
- Closes issue #78

This doc resolves:

- Exact field shapes and types
- Re-throw semantics (do location fields update on re-throw?)
- What happens when an err is returned from within Nodus user code vs.
  passed through
- Bytecode impact (none)

---

## Bytecode impact

**No new opcodes required. `BYTECODE_VERSION` stays at 4.**

The augmentation happens at the existing `CALL_BUILTIN` opcode dispatch —
an interceptor that runs after the builtin returns and before the result
is pushed onto the stack. No new opcode is introduced. The `CALL_BUILTIN`
opcode shape is unchanged; only its post-call logic is extended.

VM-thrown err records (from opcodes like `DIV` for integer division by
zero) are augmented at the point of creation using the VM's existing
program counter, which already knows the source location. No opcode
shape changes.

---

## Err record field specification

### Full field set

Every err record in v4.0 has these fields:

```nodus
err {
    kind: string,           // error category; stdlib-defined or user-defined
    message: string,        // human-readable description
    path: string | nil,     // source file path; nil if REPL or unknown
    line: int | nil,        // 1-indexed line number; nil if unknown
    column: int | nil,      // 1-indexed column number; nil if unknown
    stack: list | nil,      // call stack frames; nil if not available
    origin: string,         // "vm" | "stdlib" | "user"
    payload: record | nil   // optional; operation-specific detail
}
```

### Field descriptions

**`kind`** — a dot-namespaced string identifying the error category.
Examples: `"math_error"`, `"io_error"`, `"http_error"`, `"type_error"`,
`"user_error"`. The `kind` field is stable across versions for known
categories; user-defined kinds can be any string.

**`message`** — a complete sentence suitable for display to a developer.
Not localized. Written for humans reading debug output, not for machine
parsing. Stdlib messages follow the pattern: `"<operation>: <reason>"`.

**`path`** — absolute path to the source file being executed when the
err was produced. `nil` in REPL sessions, `nil` for errs created with
`err { ... }` that don't include a `path` field and where the VM cannot
determine the call site.

**`line`** — 1-indexed line number in `path`. `nil` if unknown. The VM
reads this from the current instruction's source map entry.

**`column`** — 1-indexed column number in `path`. `nil` if unknown.
Column is the start of the expression that produced the err (e.g., for
a `CALL_BUILTIN`, the column of the function call expression).

**`stack`** — list of call stack frame records, innermost first:

```nodus
[
    { path: string, line: int, column: int, name: string | nil },
    ...
]
```

The `name` field is the function name or `nil` for anonymous/top-level
frames. The stack list may be empty if the call depth is zero (top-level
expression). `nil` only if stack collection is disabled (future
configuration option).

**`origin`** — one of three string values:

| Value | Meaning |
|---|---|
| `"vm"` | Produced by the VM itself (e.g., integer division by zero, type coercion failure) |
| `"stdlib"` | Returned by a stdlib function via the `CALL_BUILTIN` dispatch |
| `"user"` | Created by user code via `err { ... }` literal syntax |

**`payload`** — an optional record with operation-specific detail. For
stdlib functions, this is the extra diagnostic context (e.g., HTTP status
code, subprocess exit code). For VM-thrown errs, this includes the
operation name and operands. For user errs, this is whatever the user
includes. `nil` if no payload.

### Example — stdlib err (http timeout)

```nodus
err {
    kind: "http_error",
    message: "http.get: request timed out after 30s",
    path: "/app/src/api_client.nd",
    line: 42,
    column: 18,
    stack: [
        { path: "/app/src/api_client.nd", line: 42, column: 18, name: "fetch_user" },
        { path: "/app/src/main.nd", line: 7, column: 5, name: nil }
    ],
    origin: "stdlib",
    payload: {
        category: "timeout",
        url: "https://api.example.com/users/1",
        timeout_seconds: 30
    }
}
```

### Example — VM err (integer division by zero)

```nodus
err {
    kind: "math_error",
    message: "Integer division by zero",
    path: "/app/src/calc.nd",
    line: 15,
    column: 12,
    stack: [
        { path: "/app/src/calc.nd", line: 15, column: 12, name: "divide" }
    ],
    origin: "vm",
    payload: {
        category: "division_by_zero",
        operation: "div",
        numerator: 5,
        denominator: 0
    }
}
```

### Example — user err

```nodus
// Source: user writes this
let e = err {
    kind: "validation_error",
    message: "Email address is required",
    payload: { field: "email" }
}

// v4.0: the VM fills in location fields if absent
err {
    kind: "validation_error",
    message: "Email address is required",
    path: "/app/src/validate.nd",
    line: 22,
    column: 9,
    stack: [ { path: "/app/src/validate.nd", line: 22, column: 9, name: "validate_user" } ],
    origin: "user",
    payload: { field: "email" }
}
```

---

## VM augmentation points

### CALL_BUILTIN post-call interceptor

After a builtin returns a value, the `CALL_BUILTIN` dispatch checks:

```python
result = call_builtin(name, args)
if is_err_record(result):
    result = augment_err_location(result, current_frame, origin="stdlib")
stack.push(result)
```

`augment_err_location` fills in `path`, `line`, `column`, `stack`, and
`origin` if they are absent. It never overwrites fields the stdlib
function set itself (though no current stdlib function sets these fields —
they are all set by the VM interceptor).

### VM-thrown err records

At the point a VM opcode produces an err (e.g., integer division by zero):

```python
e = err_record(kind="math_error", message="Integer division by zero", ...)
e = augment_err_location(e, current_frame, origin="vm")
return e
```

The VM already tracks source location via the source map. The `augment`
call reads `current_frame.source_map[current_pc]` → (path, line, column).

### User err literal

When the compiler sees an `err { ... }` literal, it emits a
`BUILD_ERR_RECORD` instruction (existing opcode). In v4.0, the VM also
runs augmentation after building the record:

```python
e = build_err_record(fields_from_stack)
if "path" not in e:
    e = augment_err_location(e, current_frame, origin="user")
stack.push(e)
```

User code can override location fields by including them in the err
literal — the augmentation only fills absent fields.

---

## Re-throw semantics

When user code re-throws or re-returns an err record, the location fields
are **not updated**. The err retains the location where it was originally
created.

```nodus
// func_a creates the err at line 10
let e = call_that_fails()   // e.line == 10; e.path == "src/other.nd"

// func_b returns it; location is NOT updated to func_b's line
return e   // e.line still == 10
```

**Rationale:** The original creation site is the most useful location for
debugging. Re-throw updating would hide the actual source of the problem.
The `stack` field already captures the full call chain; the `path/line/column`
fields point to where the err originated.

### Wrapping pattern

Users who want to annotate an err with additional context should create
a new err with the original as payload:

```nodus
let inner = operation_that_may_fail()
if is_err(inner) {
    return err {
        kind: "service_error",
        message: "Failed to process order",
        payload: { cause: inner, order_id: id }
    }
}
```

The new err gets location fields from its own creation site. The original
err is preserved in the `payload.cause` field with its original location.

---

## Interaction with err record patterns in other docs

### Doc 09 — integer division by zero

The integer-division err record specified in doc 09 now has the full
location field set. The doc 09 specification shows an earlier shape;
this doc supersedes it for the location fields. The `payload` content
from doc 09 is unchanged.

### Doc 01 — std:http

All HTTP err records gain location fields via the `CALL_BUILTIN`
interceptor. The stdlib functions do not need to change; augmentation
is transparent.

### Docs 02, 03, 04 — std:time, std:hash/encoding/secrets, std:subprocess

Same: all err records from these namespaces gain location fields
automatically via the interceptor.

---

## Migration impact

### Is this a breaking change?

**Additive, not breaking.** Existing code that reads `err.message` or
`err.kind` continues to work. Code that checks for absent fields
(`if err.path == nil`) may now see a non-nil value where it expected nil
— but this is the correct behavior (fields are now present).

Code that pattern-matches on the exact field set of an err record (e.g.,
`match err { kind: k, message: m }`) continues to work; additional fields
do not break record pattern matching in v4.0 (extra fields are ignored by
the pattern).

The only technically breaking scenario: code that checked `"path" not in err`
as a sentinel for "this err has no location info" and used that check to
take a different path. In v4.0, `path` is always present (or `nil`), but
the field exists. This is an edge case; the migration guide will note it.

### Documentation

`docs/migration/v3-to-v4.md` (Phase 4 deliverable) gets a section:

> ### Err records now include location fields
>
> All err records in v4.0 include `path`, `line`, `column`, `stack`, and
> `origin` fields. These fields were absent in v3.x. Existing code that
> reads `err.kind` or `err.message` is unaffected. Code that checked for
> the absence of `path` as a sentinel must be updated.

---

## Implementation outline

### augment_err_location function

```python
def augment_err_location(err, frame, origin):
    loc = frame.source_map.get(frame.pc, None)
    if "path" not in err:
        err["path"] = loc.path if loc else None
    if "line" not in err:
        err["line"] = loc.line if loc else None
    if "column" not in err:
        err["column"] = loc.col if loc else None
    if "stack" not in err:
        err["stack"] = build_stack_trace(frame)
    if "origin" not in err:
        err["origin"] = origin
    return err
```

### build_stack_trace function

```python
def build_stack_trace(frame):
    frames = []
    current = frame
    while current is not None:
        loc = current.source_map.get(current.pc, None)
        frames.append({
            "path": loc.path if loc else None,
            "line": loc.line if loc else None,
            "column": loc.col if loc else None,
            "name": current.function_name  # None for top-level frames
        })
        current = current.caller
    return frames
```

### Test surface

Phase 3B test cases:

- stdlib err record has `path`, `line`, `column`, `stack`, `origin` fields
- `origin` is `"stdlib"` for builtin-returned errs
- `origin` is `"vm"` for VM-thrown errs (integer div-by-zero etc.)
- `origin` is `"user"` for err literals created in Nodus code
- `path` matches the source file path of the call site
- `line` matches the line number of the CALL_BUILTIN instruction
- User err literal with explicit `path` field keeps its value (no overwrite)
- Re-thrown err keeps original location (not updated to re-throw site)
- `stack` is a non-empty list for code in a function call
- `stack` is an empty list for top-level code
- REPL-mode errs: `path` is nil, `line` and `column` may be nil or 1-indexed
- Err records from all existing stdlib namespaces have location fields

---

## Open implementation questions for Phase 3B

1. **Source map completeness.** Verify that the compiler emits source map
   entries for every `CALL_BUILTIN` instruction — not just for some
   expressions. If the source map has gaps (no entry for a given PC), the
   augmentation produces `path: nil, line: nil, column: nil`. A gap
   analysis is needed during Phase 3B.

2. **REPL source map.** In REPL sessions, the `path` is not a real file
   path. Decide on the convention: `nil`, `"<repl>"`, or `"<stdin>"`.
   The `nil` convention is simplest; `"<repl>"` is more readable in
   error output.

3. **Performance of stack trace collection.** `build_stack_trace` walks
   the call stack on every err return. For deeply nested calls this may
   be non-trivial. Profile with a 100-deep call stack. If it's a
   regression, consider lazy stack collection (build on first access).

4. **User err literal — BUILD_ERR_RECORD opcode.** Verify the existing
   `BUILD_ERR_RECORD` opcode is the right place to hook augmentation.
   If user errs are built via a different path (e.g., via dict
   construction and a cast), find the correct interception point.

5. **Embedding API.** Python host code that creates Nodus err records
   directly (via the embedding API) should also have location fields.
   Decide whether the embedding API fills location fields or leaves them
   nil. Nil is acceptable for embedding; document the behavior.

6. **Err records in async context.** Verify that async builtin calls
   (e.g., `http.get_async`) go through the same `CALL_BUILTIN`
   interceptor and get location fields. If async builtins have a separate
   dispatch path, hook it separately.

---

## Cross-references

- `docs/design/v4/00-phase-0-decisions.md` Decision 14 (err record
  location fields)
- `docs/design/v4/09-ieee-754-division.md` (sibling; integer division
  err record gains location fields via this doc's mechanism)
- `docs/design/v4/01-http-api.md` (sibling; all http err records gain
  location fields via CALL_BUILTIN interceptor)
- `docs/design/v4/02-datetime-api.md`, `03-crypto-hashing-api.md`,
  `04-subprocess-api.md` (siblings; same — all stdlib namespaces)
- GitHub Issue #78 / BUG-V31E-04 (the originating bug report)
- `docs/language/LANGUAGE_SPEC.md` (Phase 4 update: err record section
  gets the full field specification including location fields)
- `docs/migration/v3-to-v4.md` (Phase 4 deliverable: note on err record
  field additions)
- `docs/governance/TECH_DEBT.md` (Phase 3B open questions appended)

---

**Phase 1 doc 13-err-record-location-fields.md: COMPLETE.**
