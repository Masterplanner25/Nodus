# Design Doc: Python Error Replacement (Stdlib-Only Replace)

**Doc ID:** `docs/design/v3/02-python-error-replacement.md`
**Status:** Phase 1 design — proposed
**Author:** Shawn Knight
**Decision date:** 2026-05-24
**Closes:** [#39](https://github.com/Masterplanner25/Nodus/issues/39) (BUG-038), [#46](https://github.com/Masterplanner25/Nodus/issues/46) (BUG-045)
**Phase 0 decision reference:** V3_0_PLAN.md §0a, decision 4

---

## 1. Problem statement

Nodus stdlib functions that wrap Python operations currently leak Python error messages verbatim into user-facing errors. Two concrete examples:

```nodus
let result = json.parse("{bad")
// err.message currently:
// "Expecting property name enclosed in double quotes: line 1 column 2 (char 1)"

let content = fs.read("/missing/file")
// err.message currently:
// "[Errno 2] No such file or directory: '/missing/file'"
```

Both error messages sound like Python because they are Python. This breaks the language's voice — Nodus parse errors, runtime errors, and stdlib errors should all sound like they come from the same source. Phase 0 decision 4 selected **Replace, stdlib only:** Nodus catches Python exceptions at every stdlib boundary and rewraps them in Nodus-shaped err records.

This doc specifies the taxonomy of err kinds, the message style guide, the debug escape hatch, and the per-surface mapping for implementation.

### What this doc does NOT do

- Re-litigate Replace vs Annotate vs Document. That decision is locked.
- Change the embedding API surface — host Python code calling `runtime.run()` continues to receive Python exceptions per decision 4 scope clarification.
- Cover parser or runtime errors that already use Nodus voice (those are already correct).
- Change the err record shape itself — that's Phase 1 design doc 3.

---

## 2. Scope: which Python errors get replaced

Not every Python operation in the stdlib leaks. Functions that operate on already-Nodus data (string manipulation, collection access, math operations) rarely raise Python exceptions in normal use. The surfaces in scope for Replace are those that:

1. Wrap Python I/O or parsing operations that fail with Python-specific messages, AND
2. Currently produce err records with leaked Python text in `err.message`

**In scope (Replace required):**

| Stdlib namespace | Functions | Python exceptions wrapped |
|------------------|-----------|---------------------------|
| `json` | `parse`, `parse_int`, `stringify` | `json.JSONDecodeError`, `TypeError`, `ValueError` |
| `fs` | `read`, `write`, `exists`, `list_dir`, `delete`, `mkdir`, any other file ops | `FileNotFoundError`, `PermissionError`, `IsADirectoryError`, `NotADirectoryError`, `FileExistsError`, `OSError` (catchall) |
| `path` | `join`, `ext`, `dirname`, `basename`, `absolute`, `relative` | `ValueError`, `TypeError` from pathlib |
| `math` | `parse_int`, `idiv`, `sqrt`, `log`, `pow`, divide-by-zero paths in any op | `ValueError`, `ZeroDivisionError`, `OverflowError` |

**Out of scope (Python exceptions are acceptable here):**

| Surface | Why excluded |
|---------|--------------|
| `strings.*` | Pure string ops; Python str methods rarely raise. If they do (e.g., bad encoding), the error is genuinely about the input and Python's message is informative enough. Revisit if BUG reports surface. |
| `collections.*` | Dict/list ops; same reasoning. `KeyError` already gets caught and converted to err record elsewhere; this doc doesn't touch that path. |
| Embedding boundary | Decision 4 scope: host Python receives Python exceptions. |
| Parser errors | Already in Nodus voice. |
| Runtime errors (uncaught references, type mismatches) | Already in Nodus voice. |

**Catchall safety net:** Any Python exception that escapes a wrapped stdlib function and would otherwise leak to user code gets caught by a top-level wrapper and converted to an `internal_error` err record with message `"unexpected internal error in <function name>"`. The original Python traceback goes to the `--trace-errors` output (see §6). This ensures no leak path exists even for unanticipated exceptions.

---

## 3. err.kind taxonomy

The full set of err kinds that stdlib code may produce in v3.0. Each kind is namespaced informally by purpose — there is no enforced hierarchy.

| err.kind | When it fires | Example trigger |
|----------|---------------|-----------------|
| `parse_error` | Input string cannot be parsed in the expected format | `json.parse("{bad")`, `math.parse_int("foo")` |
| `type_error` | Argument is the wrong type for the operation | `math.idiv(7, 2)` (expects two ints, got float), `json.stringify(some_function)` |
| `value_error` | Argument is the right type but an invalid value | `math.sqrt(-1)` (negative), `math.log(0)` (zero) |
| `math_error` | Domain or arithmetic error in math operation | `math.idiv(7i, 0i)` (division by zero), `math.pow(0, -1)` (zero to negative power) |
| `io_error` | File or path operation failed for an I/O reason | `fs.read("/missing")` (file not found), `fs.write("/readonly")` (permission denied) |
| `path_error` | Path manipulation failed for a structural reason | `path.relative("relative_path", "absolute_path")` (mixing relative and absolute) |
| `internal_error` | Catchall for unexpected Python exceptions in wrapped surfaces | Any unanticipated leak |

**Existing err.kind values** continue to fire for their current cases:
- `runtime_error`, `name_error`, `index_error`, `key_error`, `divide_error` (for `/` by zero) — already in Nodus voice, not affected by this doc.

**Design note on granularity:** `io_error` is intentionally broad rather than splitting into `file_not_found`, `permission_denied`, etc. Reasoning:

1. User code that needs to distinguish (e.g., "retry on permission denied, fail on not found") can branch on `err.message` or a future structured field. Adding 6+ separate err kinds for file ops bloats the taxonomy with minor distinctions.
2. The `err.message` always names the specific failure ("file not found", "permission denied") in Nodus voice, so the information is preserved.
3. If users actually need programmatic distinction, v3.1 can add an `err.subkind` field. Not worth the design cost in v3.0.

Same reasoning for `parse_error` not splitting into `json_parse_error` vs `int_parse_error` — the message names the format.

---

## 4. Message style guide

Every err.message produced by replaced surfaces follows these rules.

### 4.1 Voice and tense

- **Present tense, declarative.** "file not found" not "could not find file" or "the file was not found".
- **Lowercase first letter.** Errors compose into longer strings; lowercase reads better when prefixed with context.
- **No trailing period.** Errors compose with other text; the consumer adds punctuation.
- **No "Error:" prefix.** The err record itself signals error status; prefixing the message is redundant.

### 4.2 Structure

Every message has this shape:

```
<what failed>: <specific detail>
```

Examples:

```
file not found: "/missing/file.txt"
not an integer: "3.14"
invalid JSON at line 1 column 2: expected property name
permission denied: "/etc/shadow"
division by zero
not a valid path component: ".."
```

**The "specific detail" half is the actionable information.** It names the offending input, the position, or the specific constraint that failed. The "what failed" half is short and consistent across similar errors.

### 4.3 Quoting

- **User-supplied strings are quoted with double quotes** in messages: `"foo"`, `"/path/to/file"`.
- **Numbers, positions, and structural values are unquoted:** `line 5`, `column 12`, `position 42`.
- **Reserved words and Nodus syntax in error context are backticked:** when explaining a parser hint inside a message, `` `let` `` not `let`.

### 4.4 What stays out of messages

- **No Python module names.** "json module failed" leaks implementation.
- **No Python exception class names.** "JSONDecodeError" leaks implementation.
- **No tracebacks.** Tracebacks belong in `--trace-errors` output, not `err.message`.
- **No hints about Nodus internals.** "internal: vm.py:142 raised" leaks implementation.

### 4.5 Position information

When the underlying Python error provides line/column information (JSON parse errors, file format errors), preserve it in Nodus voice:

```
Python:  "Expecting property name enclosed in double quotes: line 1 column 2 (char 1)"
Nodus:   "invalid JSON at line 1 column 2: expected property name"
```

When the underlying error provides errno or syscall information, abstract it:

```
Python:  "[Errno 2] No such file or directory: '/missing/file'"
Nodus:   "file not found: \"/missing/file\""

Python:  "[Errno 13] Permission denied: '/etc/shadow'"
Nodus:   "permission denied: \"/etc/shadow\""

Python:  "[Errno 21] Is a directory: '/tmp'"
Nodus:   "expected a file, got a directory: \"/tmp\""
```

---

## 5. Per-surface error mapping

Concrete mappings from Python exception → Nodus err record. Implementation in Phase 3 follows these tables.

### 5.1 `json` namespace

| Operation | Python exception | err.kind | err.message template |
|-----------|------------------|----------|----------------------|
| `json.parse(s)` | `json.JSONDecodeError` | `parse_error` | `"invalid JSON at line {line} column {col}: {reason}"` |
| `json.parse(s)` | `TypeError` (non-string arg) | `type_error` | `"json.parse expects a string, got {type}"` |
| `json.parse_int(s)` | `ValueError` (not parseable) | `parse_error` | `"not a valid integer: \"{input}\""` |
| `json.parse_int(s)` | `ValueError` (has decimal) | `parse_error` | `"not an integer (has decimal): \"{input}\""` |
| `json.parse_int(s)` | `ValueError` (scientific notation) | `parse_error` | `"not an integer (scientific notation): \"{input}\""` |
| `json.stringify(v)` | `TypeError` (non-serializable) | `type_error` | `"cannot serialize to JSON: value of type {type} is not JSON-compatible"` |
| `json.stringify(v)` | `ValueError` (circular ref) | `value_error` | `"cannot serialize to JSON: circular reference detected"` |

**`{reason}` translation table for JSONDecodeError:**

| Python text fragment | Nodus translation |
|----------------------|-------------------|
| "Expecting property name" | "expected property name" |
| "Expecting value" | "expected a value" |
| "Expecting ',' delimiter" | "expected `,` separator" |
| "Expecting ':' delimiter" | "expected `:` after key" |
| "Unterminated string" | "unterminated string" |
| "Invalid \\escape" | "invalid escape sequence" |
| "Extra data" | "unexpected content after JSON value" |

If a JSONDecodeError text doesn't match any known fragment, fall back to: `"invalid JSON at line {line} column {col}"` (omit the reason clause rather than leak Python text).

### 5.2 `fs` namespace

| Operation | Python exception | err.kind | err.message template |
|-----------|------------------|----------|----------------------|
| `fs.read(path)` | `FileNotFoundError` | `io_error` | `"file not found: \"{path}\""` |
| `fs.read(path)` | `PermissionError` | `io_error` | `"permission denied: \"{path}\""` |
| `fs.read(path)` | `IsADirectoryError` | `io_error` | `"expected a file, got a directory: \"{path}\""` |
| `fs.read(path)` | `UnicodeDecodeError` | `io_error` | `"file is not valid UTF-8: \"{path}\""` |
| `fs.read(path)` | `OSError` (other) | `io_error` | `"cannot read file: \"{path}\""` |
| `fs.write(path, content)` | `PermissionError` | `io_error` | `"permission denied: \"{path}\""` |
| `fs.write(path, content)` | `IsADirectoryError` | `io_error` | `"expected a file, got a directory: \"{path}\""` |
| `fs.write(path, content)` | `FileNotFoundError` (parent dir missing) | `io_error` | `"cannot write file, parent directory does not exist: \"{path}\""` |
| `fs.write(path, content)` | `OSError` (other) | `io_error` | `"cannot write file: \"{path}\""` |
| `fs.exists(path)` | `PermissionError` | `io_error` | `"permission denied: \"{path}\""` |
| `fs.list_dir(path)` | `FileNotFoundError` | `io_error` | `"directory not found: \"{path}\""` |
| `fs.list_dir(path)` | `NotADirectoryError` | `io_error` | `"expected a directory, got a file: \"{path}\""` |
| `fs.list_dir(path)` | `PermissionError` | `io_error` | `"permission denied: \"{path}\""` |
| `fs.delete(path)` | `FileNotFoundError` | `io_error` | `"file not found: \"{path}\""` |
| `fs.delete(path)` | `PermissionError` | `io_error` | `"permission denied: \"{path}\""` |
| `fs.delete(path)` | `IsADirectoryError` | `io_error` | `"expected a file, got a directory: \"{path}\""` |
| `fs.mkdir(path)` | `FileExistsError` | `io_error` | `"path already exists: \"{path}\""` |
| `fs.mkdir(path)` | `PermissionError` | `io_error` | `"permission denied: \"{path}\""` |
| `fs.mkdir(path)` | `FileNotFoundError` (parent missing) | `io_error` | `"cannot create directory, parent does not exist: \"{path}\""` |
| Any `fs.*` | `OSError` (uncategorized) | `io_error` | `"file system error: \"{path}\""` |
| Any `fs.*` | `TypeError` (bad arg type) | `type_error` | `"{function} expects a string path, got {type}"` |

**Sandbox violation (BUG-046, already shipped in v2.1.1) is unchanged** — it produces its existing err record. Replace only affects errors that previously leaked Python text; the sandbox path already used Nodus voice.

### 5.3 `path` namespace

| Operation | Python exception | err.kind | err.message template |
|-----------|------------------|----------|----------------------|
| `path.join(*parts)` | `TypeError` (non-string) | `type_error` | `"path.join expects strings, got {type} at position {n}"` |
| `path.ext(p)` | `TypeError` (non-string) | `type_error` | `"path.ext expects a string, got {type}"` |
| `path.relative(p, base)` | `ValueError` (mixing rel/abs) | `path_error` | `"cannot compute relative path: \"{p}\" and \"{base}\" must both be absolute or both be relative"` |
| `path.absolute(p)` | `OSError` | `path_error` | `"cannot resolve absolute path: \"{p}\""` |

Path operations are mostly pure string manipulation; few raise exceptions. Most `path.*` functions never need wrapping.

### 5.4 `math` namespace

| Operation | Python exception | err.kind | err.message template |
|-----------|------------------|----------|----------------------|
| `math.parse_int(s)` | `ValueError` | `parse_error` | `"not an integer: \"{input}\""` |
| `math.idiv(a, b)` | `ZeroDivisionError` | `math_error` | `"division by zero"` |
| `math.idiv(a, b)` | type mismatch (Nodus-level check, not Python) | `type_error` | `"math.idiv requires int args, got {a_type} and {b_type}"` |
| `math.sqrt(n)` | `ValueError` (negative) | `value_error` | `"math.sqrt requires a non-negative number, got {n}"` |
| `math.log(n)` | `ValueError` (zero or negative) | `value_error` | `"math.log requires a positive number, got {n}"` |
| `math.log(n, base)` | `ValueError` (base ≤ 0 or base == 1) | `value_error` | `"math.log requires a positive base not equal to 1, got {base}"` |
| `math.pow(a, b)` | `OverflowError` | `math_error` | `"math.pow result is too large: {a}^{b}"` |
| `math.pow(0, b)` where b < 0 | `ZeroDivisionError` | `math_error` | `"math.pow: zero raised to a negative power"` |

---

## 6. Debug escape hatch

Replace removes Python text from `err.message`. For language maintenance (Shawn investigating bug reports) and for advanced users debugging stdlib failures, the underlying Python detail must remain reachable.

### 6.1 `--trace-errors` CLI flag

New CLI flag for `nodus run` and `nodus workflow run`:

```
nodus run --trace-errors script.nod
nodus workflow run --trace-errors my_flow
```

When set, any err record produced by a Replace-wrapped surface causes Nodus to print the original Python exception and traceback to stderr, in addition to whatever the script does with the err record. Format:

```
[trace-errors] err{kind: "io_error", message: "file not found: \"/missing\""}
  produced by: fs.read at script.nod:12
  underlying Python exception: FileNotFoundError
  [Errno 2] No such file or directory: '/missing'
  Traceback (most recent call last):
    File "/path/to/nodus/stdlib/fs.py", line 47, in read
      ...
```

The trace goes to stderr; the script's normal output goes to stdout. The script's behavior is unchanged — `err.message` still contains only the Nodus message, the trace is purely diagnostic.

### 6.2 Environment variable equivalent

`NODUS_TRACE_ERRORS=1` produces the same behavior as `--trace-errors`. Useful for CI environments where adding the flag is awkward.

### 6.3 No programmatic access from Nodus code

User Nodus code cannot read the original Python exception. The escape hatch is for the host (CLI user or environment), not for the script. This is deliberate:

1. Scripts that need to handle different error conditions should branch on `err.kind` and `err.message`, not on hidden Python details.
2. Exposing Python exceptions to Nodus code would make Replace meaningless — users could read the leaked text from a different field.
3. v3.1 may add `err.subkind` for programmatic distinction; the trace is not the right channel for that.

### 6.4 Performance and side effects

`--trace-errors` adds minimal overhead because tracebacks are only captured when an exception fires in a wrapped surface. Normal hot-path code has no cost. The flag never changes script behavior; it only adds output.

---

## 7. Catchall wrapper

Every Replace-wrapped stdlib function has the same structural pattern:

```python
def _wrap_python_errors(func_name, *expected_exceptions_and_handlers):
    """Decorator factory for Replace wrapping."""
    def decorator(stdlib_fn):
        def wrapped(*args, **kwargs):
            try:
                return stdlib_fn(*args, **kwargs)
            except expected_exceptions_and_handlers as e:
                # Map to err record using the per-surface table from §5
                return _to_err(func_name, e)
            except Exception as e:
                # Catchall: anything unexpected becomes internal_error
                # Original exception goes to trace-errors output
                _record_for_trace(func_name, e)
                return _err_record(
                    kind="internal_error",
                    message=f"unexpected internal error in {func_name}"
                )
        return wrapped
    return decorator
```

This pattern is the only Python-level mechanism that touches every wrapped surface. Once implemented, adding a new wrapped surface means:

1. Define the per-surface mapping (which Python exceptions, what err.kind, what message template)
2. Apply the decorator to the stdlib function
3. Add tests for each exception case

No new Python code touches the err record format directly; everything goes through `_err_record()` and `_to_err()`.

---

## 8. Implementation outline

High-level only. Phase 3 produces the concrete PRs.

### 8.1 New runtime module

- `src/nodus/runtime/error_wrap.py` (or similar) containing `_wrap_python_errors`, `_to_err`, `_err_record`, `_record_for_trace`
- Single source of truth for the mapping logic; the per-surface tables in §5 become Python dicts here

### 8.2 Stdlib refactor

- `json` module: wrap `parse`, `parse_int`, `stringify`
- `fs` module: wrap all file operations
- `path` module: wrap the operations that can raise (most don't)
- `math` module: wrap `parse_int`, `idiv`, `sqrt`, `log`, `pow`

### 8.3 CLI changes

- Add `--trace-errors` flag to `nodus run` and `nodus workflow run`
- Read `NODUS_TRACE_ERRORS` environment variable as fallback
- Plumb the flag through to the runtime so wrapped stdlib functions know whether to record traces

### 8.4 Test coverage

Minimum required tests for Phase 3 exit:

- One test per row in the §5 mapping tables (success case + each mapped Python exception case)
- Catchall test: trigger an unexpected Python exception in a wrapped surface, confirm `internal_error` err record with no Python text leak
- `--trace-errors` test: confirm trace output goes to stderr with Python details, confirm script output is unchanged
- `NODUS_TRACE_ERRORS=1` test: same behavior as the flag
- Confirm `strings.*` and `collections.*` are NOT wrapped (Python errors continue through; this is intentional and documented)

### 8.5 Documentation impact (Phase 4)

- New file: `docs/policy/error-surfaces.md` documenting the Replace contract, the in-scope surfaces, and the `--trace-errors` escape hatch
- Update `error-handling.md` guide to reflect new err.kinds (`io_error`, `path_error`, `internal_error`, `value_error`)
- Update each affected stdlib reference in `standard-library.md` with the new err.kind/err.message they produce
- Migration guide section per §9.2

---

## 9. Migration impact

### 9.1 What breaks

**User code that depends on err.message text:** any code that string-matches on Python error text breaks. Concrete examples:

```nodus
// v2.x code (breaks in v3.0)
let result = fs.read(path)
if not result.ok and strings.contains(result.err.message, "No such file") {
    // handle missing file
}
```

This must migrate to either err.kind-based branching or the new Nodus-voice text:

```nodus
// v3.0 idiomatic
let result = fs.read(path)
if not result.ok and result.err.kind == "io_error" and strings.contains(result.err.message, "file not found") {
    // handle missing file
}
```

The kind-based branch is the recommended pattern. String matching against Nodus voice still works but is fragile to future wording changes.

**Tests that assert specific Python error text:** rewrite to assert err.kind plus the relevant fragment of Nodus voice.

### 9.2 What users do

Migration guide section will include:

1. **"Most code needs no changes"** — code that uses err records without inspecting `err.message` text is unaffected
2. **"If you string-match on err.message"** — examples of v2.x patterns and v3.0 equivalents (see §9.1)
3. **"New err.kinds to know"** — `io_error`, `path_error`, `internal_error`, `value_error` with brief descriptions
4. **"How to debug stdlib errors"** — point at `--trace-errors` flag and the new `docs/policy/error-surfaces.md`
5. **"Surfaces NOT wrapped"** — note that `strings.*` and `collections.*` still produce Python error text in rare failure cases; this is intentional and documented

### 9.3 Backward compatibility for err record shape

This doc does NOT change the err record shape. New err.kinds are added, but the fields (`kind`, `message`, `payload`, etc.) and their types remain whatever Phase 1 design doc 3 decides. The migration impact here is purely about message content and new kind values.

---

## 10. Scope ceiling (anti-bloat clause)

Per the V3_0_PLAN.md §3 risk register, the Phase 1 risk is that Python error replacement taxonomy exceeds estimated scope. This doc declares its own ceiling:

- **In scope:** the four namespaces in §2 (json, fs, path, math)
- **In scope:** the err.kinds in §3
- **In scope:** the mappings in §5
- **In scope:** the `--trace-errors` escape hatch

If Phase 3 implementation discovers stdlib surfaces beyond these four namespaces that leak Python text, the discovered surfaces are added to the design doc and implemented — but if the discovered surface count exceeds 3 additional namespaces, narrow Replace to the original four and defer the rest to v3.1.

If Phase 3 implementation discovers more than 20 distinct Python exception types that need mapping beyond what §5 enumerates, narrow the mapping to the highest-leverage 20 and route the rest through the catchall `internal_error` for v3.0. v3.1 expands the explicit mapping.

These ceilings exist so the doc 2 scope does not balloon and gate v3.0 ship.

---

## 11. Cross-references

- **Phase 0 decision 4 (V3_0_PLAN.md §0a):** establishes Replace, stdlib only
- **Phase 1 design doc 1 (01-integer-type.md):** introduces err kinds `parse_error`, `math_error`, `type_error` that are part of this taxonomy; this doc enumerates the full set
- **Phase 1 design doc 3 (03-err-record-shape.md, forthcoming):** decides the err record shape (`err.payload` absent vs nil, bare identifier map keys); this doc treats the shape as a given
- **Phase 2 BUG-032 ([#33](https://github.com/Masterplanner25/Nodus/issues/33)):** `type()` vs `rt.typeof()` reconciliation affects how the `{type}` substitution in message templates renders. Phase 3 implementation must wait for or coordinate with the BUG-032 fix.

---

## 12. Decision summary

| Item | Locked value |
|------|--------------|
| Scope | Four namespaces: `json`, `fs`, `path`, `math`. Strings, collections, embedding, parser, runtime are not Replace-wrapped. |
| New err.kinds | `parse_error`, `type_error`, `value_error`, `math_error`, `io_error`, `path_error`, `internal_error` |
| Message style | Present tense, lowercase, no trailing period, no "Error:" prefix, structure: `"<what failed>: <specific detail>"` |
| Escape hatch | `--trace-errors` CLI flag + `NODUS_TRACE_ERRORS=1` env var, output to stderr |
| Programmatic access to Python exception from Nodus code | None — escape hatch is for host, not script |
| Catchall | `internal_error` for any unexpected Python exception in a wrapped surface |
| Scope ceilings | No more than 4 namespaces (extend by 3 max), no more than 20 distinct exception types in explicit mapping |

---

## 13. Open implementation questions

These do not gate Phase 1 exit but need answers during Phase 3:

1. **JSON parse line/column accuracy:** Python's `JSONDecodeError` gives line and column. Confirm these are 1-indexed (Python's are; Nodus convention should match).
2. **Path quoting on Windows:** `\"C:\\Users\\Shawn\"` reads oddly in error messages. Consider forward-slash normalization in `err.message` paths regardless of OS, or keep platform-native. Phase 3 decides.
3. **Trace output format:** §6.1 shows a draft format. Real format may differ once the trace plumbing is implemented. Lock format during Phase 3.
4. **Test for "every wrapped surface has at least one Python exception mapped":** consider a meta-test that asserts the §5 tables are complete by inspecting the source. Optional polish.

---

## 14. Exit checklist

Phase 1 exits this design doc when:

- [ ] Doc reviewed and decisions in §12 confirmed final
- [ ] Doc committed to `docs/design/v3/02-python-error-replacement.md`
- [ ] [#39](https://github.com/Masterplanner25/Nodus/issues/39) (BUG-038) updated with link to this doc, converted to `phase:3-breaking`
- [ ] [#46](https://github.com/Masterplanner25/Nodus/issues/46) (BUG-045) updated with link to this doc, converted to `phase:3-breaking`
- [ ] Cross-reference verified with design doc 1 — `parse_error`, `math_error`, `type_error` shared correctly
- [ ] V3_0_PLAN.md §1.A updated to mark Python error replacement design doc complete