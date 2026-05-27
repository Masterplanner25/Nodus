# Nodus v4.0 — Design Doc 05: String Interpolation

**Phase:** 1 (design docs)
**Status:** Locked
**Implements:** Decision 11 (String Interpolation Syntax) from `00-phase-0-decisions.md`
**Date:** 2026-05-26
**Maintainer:** Shawn Knight (Masterplanner25)

---

## Problem statement

v4.0 ships string interpolation as a language-level feature. Decision 11
(Phase 0) locked the syntax: Swift-style `"\(expr)"` with arbitrary
expressions inside the parentheses, automatic stringification via the
`str()` path, nested interpolations supported, and format specifiers
deferred to v4.x.

This doc is the first Phase 1 doc that changes the language itself
(lexer, parser, compiler) rather than adding a stdlib namespace. The
design must specify lexer behavior, AST representation, compiler bytecode
emission, and edge cases.

The bytecode constraint is critical: `BYTECODE_VERSION` was frozen at
4 in v1.0. The design must add no new opcodes; instead, compile
interpolation to existing opcodes (string concatenation plus `str()`
builtin call). This preserves the frozen-bytecode contract while
delivering the user-facing feature.

---

## What Phase 0 already settled

From Decision 11:

- Swift-style `"\(expr)"` interpolation
- Arbitrary expressions inside `\(...)`
- Automatic stringification via `str()` path
- Nested interpolations supported
- Format specifiers (e.g., `"\(value:.2f)"`) deferred to v4.x
- Migration is additive; existing `+ str(x) +` concatenation unchanged

This doc resolves:

- Lexer mode-switch strategy
- Maximum nesting depth
- AST representation
- Compiler bytecode emission strategy (preserving `BYTECODE_VERSION = 4`)
- Stringification error handling with source position metadata
- Edge case handling (empty interpolation, unclosed forms, newlines)
- Escape rules for literal `\(`
- Format specifier syntax reservation
- Error message positioning

---

## Bytecode impact

**No new opcodes required. `BYTECODE_VERSION` stays at 4.**

The implementation compiles interpolated strings to existing
opcodes: `PUSH_STRING` for literal parts, expression bytecode for
interpolation expressions, `CALL_BUILTIN str` to coerce each
expression result, and `CONCAT` (or equivalent existing op) to join
the parts. The result is a string identical to what
`"hello " + str(name) + "!"` produces today.

This decision is load-bearing for the v4.0 cycle. It establishes that
substantial language features can ship without bumping bytecode
version, preserving the v1.0 frozen-bytecode contract. The choice was
made explicitly during Phase 1 design after surfacing the bytecode-
freeze constraint.

The performance cost (2-6 extra opcodes per interpolated string
versus a hypothetical dedicated opcode) is acceptable for v4.0.
Reconsideration trigger: if real-world profiling demonstrates
interpolation is a measurable hot path, v4.x MAY add a dedicated
`BUILD_INTERPOLATED_STRING` opcode, which would bump
`BYTECODE_VERSION` to 5 and require compatibility handling for v1.x-
v4.0 `.ndbc` files.

---

## Syntax (locked by Decision 11, restated for completeness)

String interpolation uses the escape sequence `\(expr)`:

```nodus
"hello \(name)"
"total: \(price * quantity)"
"\(map["key"])"
"\(func(a, b))"
"outer \(inner.method("nested \(deep)"))"
```

The escape syntax is consistent with existing escapes (`\n`, `\t`,
`\xHH`, `\uXXXX`). No string prefix is required; every string is
potentially interpolated.

To produce a literal `\(` in a string, escape the backslash:

```nodus
"literal \\(parens) here"
// Output: literal \(parens) here
```

This follows the standard escape convention: `\\` is a literal
backslash, which then sits next to `(` to produce `\(`. No new escape
syntax is introduced for the literal case.

---

## Lexer specification

### Mode stack

The lexer maintains a mode stack to handle interpolation and nested
strings. Two mode types:

- **string mode** — tokenizing a string literal; recognizes `\(` to
  open an interpolation, `"` to close the string
- **interpolation mode** — tokenizing expression tokens inside `\(...)`;
  recognizes `)` to close the interpolation (when at outermost paren
  depth), `"` to start a nested string

The lexer's overall state machine:

```
Start in: top-level mode (no string/interpolation)

In top-level mode:
  see `"`:
    emit STRING_START
    push string mode

In string mode (collecting characters into a literal buffer):
  see `\(`:
    emit STRING_LITERAL (the buffered literal text so far)
    emit INTERP_START
    push interpolation mode with paren_depth = 0
  see `"`:
    emit STRING_LITERAL (the buffered literal text so far)
    emit STRING_END
    pop string mode
  see escape sequence (`\n`, `\t`, etc.):
    append decoded character to literal buffer
  see any other character:
    append to literal buffer

In interpolation mode (tokenizing expression):
  see `)` and paren_depth == 0:
    emit INTERP_END
    pop interpolation mode
  see `(`:
    paren_depth++
    emit LPAREN
  see `)` and paren_depth > 0:
    paren_depth--
    emit RPAREN
  see `"`:
    emit STRING_START
    push string mode
  see `:` and paren_depth == 0:
    parse error: "format specifiers reserved for v4.x; remove ':' from
    top-level interpolation expression"
  see any other token:
    delegate to expression tokenizer; emit normal tokens
```

### Maximum nesting depth

The mode stack is limited to a maximum depth of 32. Exceeding this
limit emits a parse error: `"Nesting depth exceeded (32) at line N
column M"`.

32 is well beyond any reasonable use case (a real-world nesting depth
of 3-4 is rare; 32 would be 30+ levels deeper). The limit exists to
bound adversarial inputs from causing pathological lexer behavior.

### Token types

Five new token types introduced for interpolation:

| Token | Emitted when |
|---|---|
| `STRING_START` | Opening `"` of a string literal |
| `STRING_END` | Closing `"` of a string literal |
| `STRING_LITERAL` | Literal text between `STRING_START`/`STRING_END` and `INTERP_START`/`INTERP_END` |
| `INTERP_START` | The `\(` of an interpolation |
| `INTERP_END` | The `)` closing an interpolation |

Strings with no interpolations produce: `STRING_START`,
`STRING_LITERAL("text")`, `STRING_END`. The parser/compiler optimize
this to a plain string literal (see Compilation below).

Strings with one or more interpolations produce alternating
`STRING_LITERAL` and `INTERP_START`/expression-tokens/`INTERP_END`
sequences within the `STRING_START`/`STRING_END` pair.

### Empty parts

Adjacent interpolations like `"\(a)\(b)"` produce empty
`STRING_LITERAL` tokens between them. The compiler treats empty
literal parts as no-ops (skipping the `PUSH_STRING ""`); they exist
in the token stream for parser symmetry.

### Newlines inside interpolations

Newlines within `\(...)` are permitted (it is an expression context).
Newlines within string literal sections follow normal string rules:
literal newlines in source produce parse error; `\n` escape produces
a newline character.

```nodus
let result = "Sum: \(
    a + b + c
)"
// Valid: newlines inside the interpolation expression are ignored
```

---

## Parser specification

### AST node

A new AST node `InterpolatedString` represents the interpolated string:

```
InterpolatedString {
    parts: [Part, Part, ...],
    source_position: (line, column)
}

Part = StringLiteralPart { text: string }
     | InterpolationPart { expression: Expression, source_position: (line, column) }
```

The parts list alternates between `StringLiteralPart` and
`InterpolationPart`, starting and ending with `StringLiteralPart`
(possibly empty). The `source_position` on each
`InterpolationPart` records the source location of the `\(` for
error reporting.

### Parser grammar fragment

```
InterpolatedString := STRING_START StringContent STRING_END

StringContent := STRING_LITERAL
              | STRING_LITERAL Interpolation StringContent

Interpolation := INTERP_START Expression INTERP_END
```

The parser builds the `InterpolatedString` AST by collecting
alternating `STRING_LITERAL` and `Interpolation` parts. The
`Expression` is parsed using the normal expression grammar.

### Edge case errors

| Source | Error |
|---|---|
| `"\(name"` | `Unclosed interpolation expression starting at line N column M` |
| `"\(name)` | `Unclosed string literal starting at line N column M` |
| `"\()"` | `Empty interpolation expression at line N column M` |
| `"\(name: value)"` (top-level `:`) | `Format specifiers reserved for v4.x; remove ':' from top-level interpolation expression at line N column M` |
| `"\(name {})` | Falls through to expression parser; whatever error the expression parser produces |
| Nesting depth > 32 | `Nesting depth exceeded (32) at line N column M` |

### Format specifier reservation

The lexer detects `:` at paren_depth 0 inside an interpolation and
emits a parse error directing the user to remove the colon. This
reserves the `:` for future format specifier syntax (e.g.,
`"\(value:.2f)"`).

`:` inside nested brackets within an interpolation (e.g., inside a
map literal or function call) is allowed:

```nodus
// Allowed: `:` is inside a brace (record/map context), not top-level
"\(format({width: 10, precision: 2}))"

// Error: `:` is at top level of interpolation
"\(value:.2f)"
```

---

## Compiler specification

### No-interpolation strings

A string with no interpolations is compiled to a single
`PUSH_STRING` opcode, identical to v3.x behavior:

```
Source: "hello world"
Bytecode:
    PUSH_STRING "hello world"
```

No behavior change, no bytecode change, no performance impact.

### Interpolated strings

A string with N interpolations is compiled to a sequence:

```
For each part in InterpolatedString.parts:
    if part is StringLiteralPart and part.text is non-empty:
        emit PUSH_STRING part.text
    if part is InterpolationPart:
        compile part.expression (emits whatever expression bytecode)
        emit CALL_BUILTIN str 1   # coerce to string
        emit source_position metadata for error reporting

After all parts emitted, fold the stack with CONCAT operations:
    For (N_pushes - 1) iterations:
        emit CONCAT
```

Example: `"hello \(name)!"` compiles to:

```
PUSH_STRING "hello "
LOAD name
CALL_BUILTIN str 1
PUSH_STRING "!"
CONCAT
CONCAT
```

The result on the stack is the joined string.

### Optimization: empty literal parts

If a `StringLiteralPart` has empty text (e.g., between adjacent
interpolations or at the start/end), the compiler skips the
`PUSH_STRING ""` op. This avoids a pointless push and concatenation.

Example: `"\(a)\(b)"` compiles to:

```
LOAD a
CALL_BUILTIN str 1
LOAD b
CALL_BUILTIN str 1
CONCAT
```

No leading or trailing empty `PUSH_STRING`.

### Source position metadata for error messages

Each `CALL_BUILTIN str 1` emitted from an interpolation expression
includes source position metadata pointing at the `\(` of that
interpolation. This metadata travels with the bytecode (existing
infrastructure for source positions on opcodes).

When `str()` raises an error during interpolation (e.g., the
expression evaluates to a record type that has no string
representation and the user's custom `str()` overload returns an
err), the err's `message` field includes the interpolation's source
position:

```
err {
    kind: "type_error",
    message: "Cannot stringify record at interpolation in string at line 5, column 18",
    path: "myscript.nd",
    line: 5,
    column: 18,
    ...
}
```

This is sufficient precision for debugging without requiring sub-
token position tracking. The user can find the failing interpolation
by line/column.

---

## Stringification semantics

The `str()` builtin is the canonical stringification path. Decision 11
locked this. The interpolation feature does NOT introduce a new
stringification mechanism; it calls the existing `str()` builtin.

This means interpolation behavior follows from `str()` behavior:

- Strings: returned as-is
- Integers and floats: standard decimal representation
- Booleans: `"true"` / `"false"`
- `nil`: `"nil"`
- Lists, maps, records: their `str()` representation (whatever
  Nodus's `str()` produces today)
- Custom types with overloaded `str()`: respect the overload

If `str()` returns an err record, the interpolation fails with that
err, with the source position metadata added per above.

---

## Comparison with existing concatenation

Decision 11 noted that migration is additive: existing `+ str(x) +`
concatenation patterns continue to work. The two forms produce
equivalent bytecode:

```nodus
// Interpolation form
let msg = "hello \(name)!"

// Equivalent existing form
let msg = "hello " + str(name) + "!"
```

Both compile to the same opcodes (with minor differences in op
ordering — the interpolation form may push all parts before
concatenating, while the explicit form interleaves; both produce the
same final string). The interpolation form is more readable; the
explicit form remains available for users who prefer it or for
generated code.

---

## Format specifier reservation (deferred to v4.x)

Decision 11 deferred format specifiers. The syntax space `:` inside
interpolations is reserved for them. Current behavior:

- Top-level `:` inside `\(...)` is a parse error directing the user
  to v4.x
- Nested `:` (inside braces, brackets, parens) within an interpolation
  is allowed (it's part of record/map literals or named arguments)

When format specifiers are added in v4.x, the syntax is expected to be
`"\(expression:format)"` where `format` is a chrono-style or
printf-style specifier (TBD in v4.x design). The reservation ensures
v4.0 code that uses `:` accidentally doesn't compile (forcing
correction now), so v4.x can introduce format specifiers as a strict
extension.

If a user writes `"\(value:.2f)"` in v4.0, they get:

```
Parse error at line N column M:
  Format specifiers reserved for v4.x; remove ':' from top-level
  interpolation expression.
  Workaround: use str() or sprintf() helpers in v4.0:
    "\(format_decimal(value, 2))"
```

---

## Existing string features unchanged

The following remain unchanged in v4.0:

- All existing escape sequences: `\n`, `\t`, `\r`, `\0`, `\\`, `\"`,
  `\xHH`, `\uXXXX`
- String concatenation with `+`
- String comparison with `==`, `!=`, `<`, `>`
- All `std:strings` functions
- String literal syntax (no new prefix; no new delimiter)

---

## Open verification question

**Triple-quoted / multiline string literals.** Decision 11 references
existing escape sequences (`\n`, `\t`, etc.) — the design assumes
single-line string literals with C-style escapes. Whether Nodus has
multiline string syntax (e.g., triple-quoted strings `"""..."""` or
heredoc-style) is not explicitly addressed in the current LANGUAGE_SPEC
context available to this design conversation.

**Action for Phase 3B:** Before implementing the lexer changes,
confirm whether multiline strings exist in v3.x. If they do:

- Interpolation should work inside them with the same `\(...)` syntax
- The mode-stack lexer handles them naturally (multiline string just
  means newlines in the literal section don't cause parse errors)
- The design doc gets a small amendment specifying the behavior

If multiline strings don't exist in v3.x and are not being added in
v4.0, this open question becomes moot.

---

## Scope ceiling

Per Decision 11 and the capabilities-not-orchestration principle:

- **Format specifiers** are deferred to v4.x. Syntax space (`:`)
  reserved.
- **Different interpolation syntax** is not entertained. The `\(...)`
  form is locked.
- **Implicit stringification rules** that diverge from `str()` are
  not added. Interpolation always calls `str()`.
- **Conditional or default-value syntax** inside interpolations
  (e.g., `"\(name ?? 'anonymous')"`) is not introduced as new syntax.
  The existing `??` operator (if available) or `if-else` expressions
  work inside `\(...)`.
- **Localization** (e.g., `_n("\(count) item", "\(count) items",
  count)`) is not part of the interpolation feature. If/when
  localization arrives, it's a separate stdlib namespace.

### Reconsideration triggers

The interpolation design holds unless:

- Profiling demonstrates `BUILD_INTERPOLATED_STRING` opcode would
  provide meaningful performance benefit (then v4.x adds the opcode,
  bumps `BYTECODE_VERSION`)
- Real demand surfaces for format specifiers (10+ issues with concrete
  use cases) — triggers v4.x format specifier design
- Multiline string interpolation behavior needs amendment (resolved
  in Phase 3B verification)

---

## Implementation outline

### Lexer changes

The existing lexer adds:

- Mode stack data structure (currently lexer is stateful but doesn't
  use an explicit stack)
- Five new token types
- Recognition of `\(` as mode-switch trigger
- Top-level `:` detection inside interpolation mode
- Maximum nesting depth check

Existing escape sequence handling extends to recognize `\(`. Other
escapes (`\n`, `\t`, `\\`, etc.) work unchanged; `\(` was previously
invalid (or treated as literal `\` + `(`) and now triggers
interpolation.

**Potential migration concern:** if any existing v3.x code uses
`\(` in strings expecting it to be literal `\(` (e.g., regex
patterns, LaTeX, file paths), that code becomes a parse error in
v4.0. The migration is mechanical: replace `\(` with `\\(` in
string literals where literal `\(` is intended.

This is a real but small breaking change. The migration guide
addresses it explicitly. The doc-vs-code gate (`nodus_gate
--runtime`) will catch any docs that contained literal `\(` in
example strings.

### Parser changes

Add the `InterpolatedString` AST node type and grammar rule.
Existing string-literal grammar production extends to recognize the
new token sequence.

### Compiler changes

Add compilation logic for `InterpolatedString` nodes. The
compilation emits existing opcodes only:

- `PUSH_STRING` for literal parts
- Expression bytecode (whatever the inner expression compiles to)
- `CALL_BUILTIN str 1` for stringification
- `CONCAT` for joining

Source position metadata flows through the existing infrastructure.

### Formatter changes

`nodus fmt` learns to format interpolated strings:

- Multi-line interpolations indent the expression appropriately
- Single-line interpolations stay compact
- Existing string literals (no interpolation) format unchanged

### LSP and debugger considerations

Out of scope for this doc; tracked in the LSP/debugger backlog. The
key requirements:

- LSP: syntax highlight `\(` and `)` of interpolations; offer
  completion inside interpolation expressions
- Debugger: step-over treats an interpolation as a single source-level
  operation

---

## Open implementation questions for Phase 3B

1. **Mode stack data structure.** Lightweight (just a list of mode
   enums) or a richer structure (mode + per-mode state like
   paren_depth)? Tentative: richer structure for cleaner code; bounded
   memory cost (max 32 entries x constant per-entry).

2. **Recovery from unclosed forms.** When the lexer hits EOF inside a
   string or interpolation, can it recover and continue tokenizing
   for syntax highlighting purposes (LSP), or does it just abort?
   Tentative: emit an error token with the partial content; LSP can
   use this for highlighting up to the error point.

3. **Multiline string interpolation.** Per the open verification
   question. Resolve via LANGUAGE_SPEC reading before lexer work
   begins.

4. **Empty interpolation diagnostic precision.** `"\()"` could mean
   "I forgot to type the expression" or "I'm building a template
   skeleton". Tentative: hard error; users who want a template
   placeholder write `"\(\"\")"` (a literal empty string interpolation,
   which evaluates to `""`).

5. **Source position recording overhead.** Each interpolation adds a
   source-position record to the bytecode. For a script with 10,000
   interpolations, that's 10,000 small records. Tentative: piggyback
   on existing source-position infrastructure (no separate storage);
   verify this doesn't blow up `.ndbc` file sizes by more than ~5%.

6. **Migration tooling.** A v3.x to v4.0 migration tool COULD detect
   strings containing `\(` and offer to escape them as `\\(`. Tentative:
   not in v4.0; the migration guide documents the manual change.
   Reconsider if real users hit the breaking change frequently.

---

## MCP and A2A consumer validation

String interpolation has no direct dependency from `nodus-mcp` or
`nodus-a2a` libraries. Both libraries are Python-implemented
internally; they construct strings using Python-side string
formatting, not Nodus interpolation.

Indirectly, both libraries benefit when users write orchestration
code that calls them:

```nodus
// Before v4.0
let result = mcp.call_tool("read_file", {path: "/tmp/" + str(name) + ".txt"})

// v4.0 with interpolation
let result = mcp.call_tool("read_file", {path: "/tmp/\(name).txt"})
```

This is a readability improvement for consumers of the libraries, not
a requirement of the libraries themselves.

---

## Migration impact

### Additive: interpolation syntax

The `\(...)` syntax is new in v4.0. Existing code without `\(` in
string literals continues to compile unchanged.

### Breaking: literal `\(` in v3.x string literals

In v3.x, `\(` in a string literal was either:
- Treated as a literal `\` followed by `(` (most likely behavior)
- Or a lexer error (depending on how strictly the lexer rejected
  unknown escapes)

In v4.0, `\(` triggers interpolation. Existing code that contains
literal `\(` in string literals must be updated.

**Migration:** replace `\(` with `\\(` in string literals where the
literal sequence is intended. Common cases:

```nodus
// v3.x
let pattern = "search for \(\w+\)"      // regex pattern using \(
let path = "C:\(documents)\(file)"      // Windows path

// v4.0 migration
let pattern = "search for \\(\w+\\)"
let path = "C:\\(documents)\\(file)"    // or use raw paths via path.join
```

The migration is mechanical. The migration guide (Phase 4) lists this
as a v3.x to v4.0 breaking change with the search-and-replace pattern.

The `nodus_gate --runtime` check will catch any documentation
examples that contain unescaped `\(` in literals.

---

## Cross-references

- `docs/design/v4/00-phase-0-decisions.md` Decision 11 (string
  interpolation syntax)
- `docs/design/v4/00-phase-0-decisions.md` Decision 5/6/7/8 (sibling
  capability designs; no opcode changes)
- `docs/language/LANGUAGE_VISION.md` principle #4 (Extensible
  Runtime — bytecode instruction extensions allowed but treated as
  significant additions)
- `docs/language/LANGUAGE_SPEC.md` (string literal section to be
  updated in Phase 4 docs sweep)
- `docs/governance/STABILITY.md` (`BYTECODE_VERSION = 4` frozen since
  v1.0; v4.0 preserves this)
- `docs/governance/TECH_DEBT.md` (Phase 3B open questions appended)

---

## Phase 3B implementation handoff

When Phase 3B begins (string interpolation implementation), the
following artifacts are ready:

1. This design doc (`05-string-interpolation.md`)
2. Decision 11 (Phase 0)
3. Six open implementation questions enumerated above
4. Bytecode constraint locked: no new opcodes; `BYTECODE_VERSION`
   stays at 4
5. Test surface to cover:
   - All Decision 11 examples (`"hello \(name)"`, etc.)
   - Nested interpolations (depths 1, 2, 3, ..., 32)
   - Nesting depth limit enforcement (>32 produces parse error)
   - Empty interpolations (parse error)
   - Unclosed interpolations and strings (parse errors with line/column)
   - Newlines inside interpolations (allowed)
   - Newlines inside string literal parts (existing rules apply)
   - Literal `\(` via `\\(` escape
   - Top-level `:` inside interpolation (reserved-syntax parse error)
   - Nested `:` (in maps/records inside interpolation, allowed)
   - Stringification of all value types (string, int, float, bool, nil,
     list, map, record, custom)
   - Stringification failures preserve source position in err
   - Empty string `""` and no-interpolation strings (existing
     PUSH_STRING bytecode unchanged)
   - Empty literal parts between adjacent interpolations (compiler
     optimization skips `PUSH_STRING ""`)
   - Migration: v3.x scripts with `\(` produce parse errors in v4.0
   - Performance: interpolation bytecode matches `+str+` form
     performance characteristics

Estimated implementation effort: 2-3 days focused work for lexer
changes, parser AST additions, compiler bytecode emission, formatter
support, and comprehensive tests. The mode-switching lexer is the
most complex piece; the rest is straightforward extension of
existing infrastructure.

---

**Phase 1 doc 05-string-interpolation.md: COMPLETE.**
