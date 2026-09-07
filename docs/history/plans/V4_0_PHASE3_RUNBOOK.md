# Nodus v4.0 — Phase 3 Concentrated Burst Runbook

**Phase:** 3 (breaking changes + new stdlib + language features + tooling)
**Shape:** A (one concentrated 3-5 day burst)
**Estimated effort:** 3-5 focused days
**Working directory:** C:\dev\Coding Language
**Prerequisites:** Phase 1 (15 design docs) and Phase 2 (4 cleanup items) complete

---

## How to use this document

This is a runbook for a multi-day implementation burst, not a chat
session prompt. Read the full document before starting. Execute
sub-phases in order. Stop at each checkpoint to verify test suite
state before continuing.

The document is organized:

- **Shared infrastructure** — patterns reused across all sub-phases
- **Sub-phase 3A** — Tier 1 breaking changes (4 docs)
- **Checkpoint 3A→3B**
- **Sub-phase 3B** — Tier 2 stdlib namespaces (5 namespaces)
- **Checkpoint 3B→3C**
- **Sub-phase 3C** — Tier 2 language features + tooling (5 features)
- **Checkpoint 3C→3D**
- **Sub-phase 3D** — Tier 3 finalized (2 docs)
- **Phase 3 exit criteria**

Each sub-phase has explicit done conditions, test commands, decision
trees for likely failure modes, and rollback patterns.

---

## Items NOT in Phase 3

These items were considered but explicitly excluded:

1. **BUG-NEW-01 (#83) `1ii` lexer edge case** — labeled
   tier:3-design-needed. Design not yet locked. Deferred to v4.x as
   not blocking v4.0.

   **Note:** the maintainer has indicated they likely WILL handle
   this before v4.0 ships, but not in this Phase 3 burst. If/when
   ready, design happens in a separate chat session, then a small
   Phase 3.5 implementation pass slots in before Phase 4. The v4.0
   ship plan currently does NOT depend on #83.

2. **Other workflow error categories** (`missing_step`,
   `step_failed`, `max_depth_exceeded`) — reserved per doc 15. Only
   `cyclic_workflow` is implemented in Phase 3.

3. **Additional stdlib namespaces** beyond what Phase 1 designed
   (`std:math` extensions, `std:json` extensions, etc.) — out of
   scope.

4. **MCP and A2A library implementation** — Phase 3 produces the
   prerequisites (tool registry, stdlib namespaces); the libraries
   themselves are post-v4.0 implementation work coordinated with
   the v4.0 release.

---

## Shared infrastructure

These patterns are used across multiple sub-phases. Implementing
them correctly in 3A is foundational for 3B/3C/3D.

### Bytecode contract

**No new opcodes throughout Phase 3.** `BYTECODE_VERSION` stays at 4.

If any implementation surfaces a genuine need for a new opcode, STOP
and discuss before adding it. The v1.0 frozen-bytecode contract held
through Phase 1 design (15 docs, zero new opcodes); Phase 3
implementation should be able to preserve it.

### Err record shape (consistent across all Phase 3 work)

Every err record produced by Phase 3 code uses this shape (per doc
13):

```python
{
    "kind": str,           # category string (e.g., "http_error")
    "message": str,        # human-readable
    "path": str,           # populated by VM wrapping
    "line": int,           # populated by VM wrapping
    "column": int,         # populated by VM wrapping
    "stack": list,         # populated by VM wrapping
    "origin": str,         # "vm" | "stdlib" | "user", set by VM
    "payload": dict        # category-specific data
}
```

Stdlib functions return err records WITHOUT path/line/column/stack/
origin populated. The CALL_BUILTIN opcode wrapper adds these fields
automatically. This is the doc 13 mechanism.

This means Phase 3A doc 13 implementation is foundational for ALL
subsequent err records to work correctly. Implement doc 13 FIRST in
Phase 3A.

### Value translation (Python ↔ Nodus)

Existing infrastructure in `src/nodus/builtins/` handles value
translation. New stdlib namespaces use the same patterns:

| Python type | Nodus type |
|---|---|
| `int` | NodusInt |
| `float` | float |
| `str` | string |
| `bool` | bool |
| `None` | nil |
| `list` | list |
| `dict` | map |
| `bytes` | bytes |

Custom types (process handles, hash records, datetime values) are
wrapped as Nodus records with appropriate field access.

### Module structure

New stdlib modules follow the existing pattern:

```
src/nodus/stdlib/<namespace>.nd          # .nd module declaring exports
src/nodus/builtins/<namespace>.py        # Python-side implementation
src/nodus/builtins/<namespace>_register.py  # registration glue (if needed)
```

The exact structure depends on existing v3.x conventions in
`src/nodus/stdlib/` and `src/nodus/builtins/`. Match what's there
rather than inventing a new pattern.

### Test conventions

- Test files: `tests/test_<feature>.py`
- Each Phase 3 item adds tests; failing tests block the sub-phase
  exit
- Run after every change:
  ```powershell
  PYTHONPATH="C:/dev/Coding Language/src" `
    "C:/dev/Coding Language/.venv/Scripts/python.exe" `
    -m pytest tests/ -q
  ```
- Test count grows during Phase 3; track baseline (812 at Phase 2
  end) and report new count at each checkpoint.

### Commit cadence

Per CLAUDE.md, commits per logical change. Phase 3 sub-phase commits
follow this pattern:

- Each Tier 1 breaking change in 3A → its own commit
- Each stdlib namespace in 3B → its own commit
- Each language feature in 3C → its own commit
- Each Tier 3 finalized item in 3D → its own commit

Total Phase 3 commits: ~13 (4 in 3A, 5 in 3B, 4-5 in 3C, 2 in 3D).

CHANGELOG.md updates land in the same commit as the code change.

---

## Sub-phase 3A — Tier 1 breaking changes

Four items, implemented in this order. Order matters because doc 15
depends on doc 13.

### 3A.1 — Doc 13: Err record location fields (FIRST)

This is the foundation. Implement first because every other Phase 3
err record relies on the CALL_BUILTIN wrapping.

**Spec:** docs/design/v4/13-err-record-location-fields.md

**Implementation outline:**

1. Locate the `CALL_BUILTIN` opcode handler in the VM (likely in
   `src/nodus/vm/` or similar)
2. Wrap the return value: if the return is an err record (has `kind`
   field), augment it with:
   - `path` = source path from opcode metadata
   - `line` = source line from opcode metadata
   - `column` = source column from opcode metadata
   - `stack` = current call stack snapshot
   - `origin` = "stdlib" (for CALL_BUILTIN-returned errs)
3. Similar wrapping for the THROW opcode handler (set `origin` =
   "user", same location source)
4. Similar wrapping for VM-thrown errors (set `origin` = "vm")
5. Add the `current_call_stack()` helper that returns the frame list
6. Add the `is_err_record(value)` helper that checks for `kind` field

**Test surface:**

```python
# tests/test_err_location_fields.py

import subprocess
import tempfile
import os
import json
from pathlib import Path

NODUS_BIN = "C:/dev/Coding Language/.venv/Scripts/nodus.exe"
PYTHON_BIN = "C:/dev/Coding Language/.venv/Scripts/python.exe"
SRC_PATH = "C:/dev/Coding Language/src"


def run_nodus(script_content):
    """Run script and return parsed result + exit code."""
    with tempfile.NamedTemporaryFile(
        mode='w', suffix='.nd', delete=False, encoding='utf-8'
    ) as f:
        f.write(script_content)
        script_path = f.name
    try:
        env = os.environ.copy()
        env["PYTHONPATH"] = SRC_PATH
        result = subprocess.run(
            [NODUS_BIN, "run", script_path],
            capture_output=True, text=True, env=env, timeout=10
        )
        return result.stdout, result.stderr, result.returncode
    finally:
        Path(script_path).unlink()


def test_stdlib_err_has_path():
    """Stdlib-returned err record has path field populated."""
    script = """
let e = json.parse("{bad")
if type(e) == "error" {
    print("path:" + e.path)
    print("line:" + str(e.line))
    print("column:" + str(e.column))
    print("origin:" + e.origin)
}
"""
    stdout, stderr, rc = run_nodus(script)
    assert "path:" in stdout
    assert "line:2" in stdout    # the json.parse call is on line 2
    assert "origin:stdlib" in stdout


def test_vm_thrown_err_has_origin_vm():
    """VM-thrown err (out of bounds, etc.) has origin: vm."""
    script = """
let lst = [1, 2, 3]
let e = try { lst[10] } catch (x) { x }
if type(e) == "error" {
    print("origin:" + e.origin)
}
"""
    stdout, stderr, rc = run_nodus(script)
    assert "origin:vm" in stdout


def test_user_thrown_err_has_origin_user():
    """User throw produces err with origin: user."""
    script = """
let e = try {
    throw {kind: "my_error", message: "test"}
} catch (x) { x }
print("origin:" + e.origin)
print("path:" + e.path)
"""
    stdout, stderr, rc = run_nodus(script)
    assert "origin:user" in stdout
    assert "path:" in stdout    # path is populated even for user errs


def test_stack_includes_call_frames():
    """Err stack includes the frames leading to the call."""
    script = """
fn inner() {
    return json.parse("{bad")
}
fn outer() {
    return inner()
}
let e = outer()
if type(e) == "error" {
    print("stack_length:" + str(len(e.stack)))
}
"""
    stdout, stderr, rc = run_nodus(script)
    # Stack should include outer, inner, and the call site
    assert "stack_length:" in stdout
    # Don't assert exact length; just that it's non-empty
```

**Done condition:** all 4 tests pass; pre-existing tests still pass
(812 baseline maintained or increased).

**Likely failure modes:**

- **Source position metadata missing from opcodes.** If the VM
  doesn't currently track source positions per opcode, this is a
  prerequisite. Check `src/nodus/vm/` for source position handling.
  If missing, design how to add it before implementing the wrapping.
- **Call stack representation incompatible.** The `stack` field
  expects a list of frame records. If the VM's call stack uses a
  different structure, write a converter that produces the expected
  list shape.
- **Existing v3.x err records with manual path/line.** Some v3.x
  stdlib functions may set `path` manually. The VM wrapper should
  OVERRIDE these (the wrapper is authoritative). Verify no tests
  break from override behavior.

**Commit:** `feat(vm): err records get path/line/column/stack/origin
via CALL_BUILTIN wrapping (#78)`

CHANGELOG.md [Unreleased] entry:
```
### Changed

- All err records now have `path`, `line`, `column`, `stack`, and
  `origin` fields populated. Stdlib-returned errs use `origin: "stdlib"`;
  VM-thrown errs use `origin: "vm"`; user-thrown errs use
  `origin: "user"`. Closes BUG-V31E-04 (#78).
```

---

### 3A.2 — Doc 09: IEEE 754 float division

**Spec:** docs/design/v4/09-ieee-754-division.md

**Implementation outline:**

1. Locate the float division opcode handler
2. Remove the zero-check; let Python's float division produce inf/nan
3. Integer division opcode: keep the zero check; convert "throw" to
   "return err record" (using the doc 13 mechanism, the err gets
   location fields automatically)
4. Add `math.is_nan`, `math.is_inf`, `math.is_finite` as builtins
5. Add `math.nan`, `math.infinity`, `math.neg_infinity` as module
   constants
6. Same for modulo: float modulo by zero returns nan; integer modulo
   by zero returns err record

**Test surface:**

```python
# tests/test_ieee_754_division.py

def test_float_div_by_zero_returns_inf():
    script = """
let r = 1.0 / 0.0
print("result:" + str(r))
print("is_inf:" + str(math.is_inf(r)))
"""
    stdout, stderr, rc = run_nodus(script)
    assert "result:inf" in stdout or "result:Infinity" in stdout
    assert "is_inf:true" in stdout


def test_float_div_zero_by_zero_returns_nan():
    script = """
let r = 0.0 / 0.0
print("is_nan:" + str(math.is_nan(r)))
print("equal_self:" + str(r == r))
"""
    stdout, stderr, rc = run_nodus(script)
    assert "is_nan:true" in stdout
    assert "equal_self:false" in stdout    # nan != nan per IEEE 754


def test_negative_float_div_zero():
    script = """
let r = -1.0 / 0.0
print("result:" + str(r))
print("is_inf:" + str(math.is_inf(r)))
"""
    stdout, stderr, rc = run_nodus(script)
    assert "-inf" in stdout.lower() or "-Infinity" in stdout
    assert "is_inf:true" in stdout


def test_int_div_by_zero_returns_err():
    script = """
let e = try { 5i / 0i } catch (x) { x }
if type(e) == "error" {
    print("kind:" + e.kind)
    print("category:" + e.payload.category)
}
"""
    stdout, stderr, rc = run_nodus(script)
    assert "kind:math_error" in stdout
    assert "category:division_by_zero" in stdout


def test_math_constants():
    script = """
print("nan_check:" + str(math.is_nan(math.nan)))
print("inf_check:" + str(math.is_inf(math.infinity)))
print("neg_inf_check:" + str(math.is_inf(math.neg_infinity)))
print("infinity_gt:" + str(math.infinity > 1e308))
"""
    stdout, stderr, rc = run_nodus(script)
    assert "nan_check:true" in stdout
    assert "inf_check:true" in stdout
    assert "neg_inf_check:true" in stdout
    assert "infinity_gt:true" in stdout


def test_mixed_type_division():
    """Mixed int/float division promotes to float, uses IEEE 754."""
    script = """
let r = 1i / 0.0
print("is_inf:" + str(math.is_inf(r)))
"""
    stdout, stderr, rc = run_nodus(script)
    assert "is_inf:true" in stdout
```

**Done condition:** all tests pass; no regression in existing tests.

**Likely failure modes:**

- **Existing tests that catch division-by-zero exceptions.** Search
  for `try.*0.0|catch.*division` patterns in tests/. Update to use
  `math.is_finite()` check instead.
- **`is_nan` / `is_inf` / `is_finite` naming collision.** If the
  current math module has functions with these names that do
  something else, rename them and document the deprecation. Check
  `src/nodus/builtins/` and `src/nodus/stdlib/math.nd` for existing
  signatures.
- **`math.nan` constant string representation.** Python prints `nan`;
  the Nodus str() implementation may produce something different.
  Verify the str representation is consistent.

**Commit:** `feat(vm): IEEE 754 float division semantics; integer
division produces err record (#81)`

CHANGELOG.md entry:
```
### Changed

- Float division by zero now returns IEEE 754 inf/nan instead of
  throwing. Integer division by zero returns an err record.
- New math functions: `math.is_nan(x)`, `math.is_inf(x)`,
  `math.is_finite(x)`.
- New math constants: `math.nan`, `math.infinity`, `math.neg_infinity`.

### Migration

Code that wrapped float division in try-catch to handle division-by-
zero now silently propagates inf/nan. Use `math.is_finite()` to
detect non-finite values explicitly. See docs/design/v4/09-ieee-754-
division.md for migration patterns.
```

---

### 3A.3 — Doc 14: len() returns int

**Spec:** docs/design/v4/14-len-returns-int.md

**Implementation outline:**

1. Update `len()` builtin to return NodusInt
2. Update `count()` builtin to return NodusInt
3. Update `index_of()` and `last_index_of()` builtins to return
   NodusInt (or nil for not-found)
4. Update `range()` builtin to yield NodusInt values
5. Update LANGUAGE_SPEC.md reference for these functions

**Test surface:**

```python
# tests/test_len_returns_int.py

def test_len_string_returns_int():
    script = """
let n = len("hello")
print("type:" + type(n))
print("value:" + str(n))
"""
    stdout, stderr, rc = run_nodus(script)
    assert "type:int" in stdout
    assert "value:5" in stdout


def test_len_list_returns_int():
    script = """
let n = len([1, 2, 3])
print("type:" + type(n))
"""
    stdout, stderr, rc = run_nodus(script)
    assert "type:int" in stdout


def test_len_map_returns_int():
    script = """
let n = len({a: 1, b: 2})
print("type:" + type(n))
"""
    stdout, stderr, rc = run_nodus(script)
    assert "type:int" in stdout


def test_index_of_not_found_returns_nil():
    script = """
let r = index_of([1, 2, 3], 99)
print("result:" + str(r))
print("is_nil:" + str(r == nil))
"""
    stdout, stderr, rc = run_nodus(script)
    assert "is_nil:true" in stdout


def test_index_of_found_returns_int():
    script = """
let r = index_of([1, 2, 3], 2)
print("type:" + type(r))
print("value:" + str(r))
"""
    stdout, stderr, rc = run_nodus(script)
    assert "type:int" in stdout
    assert "value:1" in stdout


def test_count_returns_int():
    script = """
let r = count("hello world", "o")
print("type:" + type(r))
print("value:" + str(r))
"""
    stdout, stderr, rc = run_nodus(script)
    assert "type:int" in stdout
    assert "value:2" in stdout


def test_range_yields_ints():
    script = """
for i in range(3) {
    print("type:" + type(i) + " value:" + str(i))
}
"""
    stdout, stderr, rc = run_nodus(script)
    assert stdout.count("type:int") == 3
    assert "value:0" in stdout
    assert "value:1" in stdout
    assert "value:2" in stdout


def test_int_division_with_len():
    """Floor division with len() and int literal works correctly."""
    script = """
let n = len([1, 2, 3, 4, 5]) / 2i
print("type:" + type(n))
print("value:" + str(n))
"""
    stdout, stderr, rc = run_nodus(script)
    assert "type:int" in stdout
    assert "value:2" in stdout    # floor of 2.5
```

**Done condition:** all tests pass; pre-existing tests updated for
new return types.

**Likely failure modes:**

- **Tests assuming float equality.** Existing tests like
  `assert len(x) == 5.0` need updating to `len(x) == 5i`. Audit
  before fixing one-by-one.
- **`index_of` already returns nil somewhere.** Check current
  behavior. If it varies by container type, normalize all paths to
  return nil.
- **`range` is implemented as a Python generator.** Verify the
  yield path produces NodusInt values via the value translation
  layer.

**Commit:** `feat(stdlib): len/count/index_of/range return int; index_of
not-found returns nil`

---

### 3A.4 — Doc 15: Cyclic workflow err record

**Spec:** docs/design/v4/15-cyclic-workflow-err-record.md
**Depends on:** Doc 13 (already landed in 3A.1)

**Implementation outline:**

1. Locate the workflow runner cycle detection code
2. Change the cycle-detected return value from `{"error": "..."}` to
   an err record:
   ```python
   return err_record(
       kind="workflow_error",
       message=f"Dependency cycle detected: {' -> '.join(cycle + [cycle[0]])}",
       payload={
           "category": "cyclic_workflow",
           "cycle": list(cycle),
           "workflow_name": workflow.name or "<unnamed>"
       }
   )
   ```
3. The CALL_BUILTIN wrapper from doc 13 adds location fields
   automatically — no extra work needed here
4. Verify CLI exit code: an uncaught err record returned at top
   level should already exit non-zero (this is doc 13's mechanism
   working through the CLI)

**Test surface:**

```python
# tests/test_cyclic_workflow_err.py

def test_cyclic_workflow_returns_err_record():
    script = """
workflow cyclic {
    step A after B { return 1 }
    step B after A { return 2 }
}
let r = run_workflow(cyclic)
print("type:" + type(r))
if type(r) == "error" {
    print("kind:" + r.kind)
    print("category:" + r.payload.category)
}
"""
    stdout, stderr, rc = run_nodus(script)
    assert "type:error" in stdout
    assert "kind:workflow_error" in stdout
    assert "category:cyclic_workflow" in stdout


def test_cyclic_workflow_cycle_path():
    script = """
workflow cyclic {
    step A after B { return 1 }
    step B after A { return 2 }
}
let r = run_workflow(cyclic)
if type(r) == "error" {
    print("cycle:" + str(r.payload.cycle))
    print("name:" + r.payload.workflow_name)
}
"""
    stdout, stderr, rc = run_nodus(script)
    assert "cycle:" in stdout
    assert "A" in stdout
    assert "B" in stdout
    assert "name:cyclic" in stdout


def test_cyclic_workflow_cli_exit_nonzero():
    """CLI propagates cyclic workflow err to non-zero exit code."""
    with tempfile.NamedTemporaryFile(
        mode='w', suffix='.nd', delete=False, encoding='utf-8'
    ) as f:
        f.write("""
workflow cyclic {
    step A after B { return 1 }
    step B after A { return 2 }
}
run_workflow(cyclic)
""")
        script_path = f.name
    try:
        env = os.environ.copy()
        env["PYTHONPATH"] = SRC_PATH
        result = subprocess.run(
            [NODUS_BIN, "workflow", "run", script_path],
            capture_output=True, text=True, env=env, timeout=10
        )
        assert result.returncode != 0, f"expected non-zero exit, got {result.returncode}"
    finally:
        Path(script_path).unlink()


def test_self_cycle_detected():
    """Step depending on itself is detected as a cycle."""
    script = """
workflow self_cycle {
    step A after A { return 1 }
}
let r = run_workflow(self_cycle)
if type(r) == "error" {
    print("cycle:" + str(r.payload.cycle))
}
"""
    stdout, stderr, rc = run_nodus(script)
    assert "A" in stdout
```

**Done condition:** all tests pass; the CLI test confirms exit code 1
for uncaught cycle errors.

**Likely failure modes:**

- **Self-cycle detection broken.** Verify single-step cycles work.
  If detection only finds multi-step cycles, fix the algorithm.
- **Workflow name not accessible.** If `workflow.name` doesn't exist
  in the runner's data structures, use file path + line, or
  "<unnamed>" fallback.
- **CLI doesn't currently exit non-zero on err record.** If doc 13
  worked but CLI doesn't pick it up, fix the CLI's exit-code logic
  to check for err records at top-level returns.
- **Multiple cycles edge case.** If the workflow has two independent
  cycles, only the first detected one is reported. Verify the test
  doesn't assert presence of both.

**Commit:** `feat(workflow): cyclic workflows return err record; CLI exits non-zero (#79)`

CHANGELOG entry:
```
### Changed

- Cyclic workflows now return an err record with
  `kind: "workflow_error"`, `payload.category: "cyclic_workflow"`,
  and a `payload.cycle` list of step names. CLI exits with non-zero
  status on uncaught cyclic workflow errs. Closes BUG-V31E-05 (#79).
```

---

## Checkpoint 3A → 3B

Before starting 3B:

1. Run full test suite:
   ```powershell
   PYTHONPATH="C:/dev/Coding Language/src" `
     "C:/dev/Coding Language/.venv/Scripts/python.exe" `
     -m pytest tests/ -q
   ```
2. Confirm: all 812+ baseline tests still pass; new 3A tests pass
3. Confirm: 4 commits landed (one per 3A item)
4. Confirm: CHANGELOG.md [Unreleased] has 4 entries
5. Confirm: no errors in `nodus --version` or basic smoke test

If any of these fail, STOP. Diagnose before starting 3B. The
foundational doc 13 work must be solid before stdlib namespaces
build on it.

**Rollback option if 3A goes sideways:**

Each 3A item is a separate commit. Revert individually with
`git revert <commit>`. Doc 13 is the foundation; if it's broken,
revert it and all subsequent 3A work (15 depends on 13). If 09 or 14
are broken independently, revert just those.

The Phase 2 baseline (812 tests passing, commit ae0e343) is the
safe rollback point if everything goes sideways.

---

## Sub-phase 3B — Tier 2 stdlib namespaces

Five namespaces: env, http, time, crypto (3 sub-namespaces), subprocess.

Implementation order is by dependency:

1. **env** (small; inline spec; no dependencies)
2. **time** (depends on tzdata package install)
3. **crypto** (no dependencies beyond Python stdlib)
4. **http** (depends on httpx package install)
5. **subprocess** (depends on http for async patterns established
   first)

Each namespace gets:

- `.nd` module file in `src/nodus/stdlib/`
- Python builtin file in `src/nodus/builtins/`
- Test file in `tests/`
- CHANGELOG.md entry
- Its own commit

### 3B.1 — std:env (inline specification)

**Not in any Phase 1 design doc.** Specified inline here because it's
small and conventional.

**API surface:**

```nodus
import "std:env" as env

env.get(name)              // string value, or nil if unset
env.get(name, default)     // string value, or default if unset
env.set(name, value)       // sets env var; returns prev value or nil
env.unset(name)            // removes env var; returns prev value or nil
env.has(name)              // bool
env.list()                 // map of all current env vars (string → string)
env.list_keys()            // list of all env var names
```

**Behavior:**

- All values are strings. Numeric or boolean conversion is the
  caller's responsibility.
- `env.set` and `env.unset` affect the CURRENT Nodus process only.
  Child processes spawned via `subprocess` inherit the modified env
  (unless the subprocess call uses `env_inherit: false`).
- Modifications persist until script exit.
- In test mode, env changes are reverted between tests (per doc 07
  isolation).

**Err records:**

- `env.get(name)` on a non-existent var returns nil (not err)
- `env.set` with invalid name (contains `=` or null bytes) returns
  err with `kind: "env_error"`, `category: "invalid_name"`
- Other operations don't typically err

**Implementation:**

Python-side wraps `os.environ`:

```python
def builtin_env_get(name, default=None):
    return os.environ.get(name, default)

def builtin_env_set(name, value):
    if "=" in name or "\x00" in name:
        return err_record(kind="env_error",
                          payload={"category": "invalid_name", "name": name})
    prev = os.environ.get(name)
    os.environ[name] = value
    return prev

def builtin_env_unset(name):
    prev = os.environ.pop(name, None)
    return prev

def builtin_env_has(name):
    return name in os.environ

def builtin_env_list():
    return dict(os.environ)

def builtin_env_list_keys():
    return list(os.environ.keys())
```

**Test surface:**

```python
# tests/test_env.py

def test_env_get_existing():
    """env.get returns existing variable."""
    script = """
let path = env.get("PATH")
print("has_path:" + str(path != nil))
"""
    stdout, _, _ = run_nodus(script)
    assert "has_path:true" in stdout


def test_env_get_missing_returns_nil():
    script = """
let v = env.get("NONEXISTENT_VAR_XYZ123")
print("is_nil:" + str(v == nil))
"""
    stdout, _, _ = run_nodus(script)
    assert "is_nil:true" in stdout


def test_env_get_with_default():
    script = """
let v = env.get("NONEXISTENT_VAR_XYZ123", "fallback")
print("value:" + v)
"""
    stdout, _, _ = run_nodus(script)
    assert "value:fallback" in stdout


def test_env_set_and_get():
    script = """
env.set("MY_TEST_VAR", "hello")
let v = env.get("MY_TEST_VAR")
print("value:" + v)
"""
    stdout, _, _ = run_nodus(script)
    assert "value:hello" in stdout


def test_env_has():
    script = """
env.set("MY_HAS_VAR", "x")
print("has:" + str(env.has("MY_HAS_VAR")))
print("no_has:" + str(env.has("NONEXISTENT_XYZ")))
"""
    stdout, _, _ = run_nodus(script)
    assert "has:true" in stdout
    assert "no_has:false" in stdout


def test_env_set_invalid_name_err():
    script = """
let r = env.set("BAD=NAME", "value")
print("type:" + type(r))
"""
    stdout, _, _ = run_nodus(script)
    assert "type:error" in stdout
```

**Commit:** `feat(stdlib): std:env namespace for environment variables`

CHANGELOG entry:
```
### Added

- `std:env` namespace with `get`, `set`, `unset`, `has`, `list`,
  `list_keys`. All values are strings; modifications affect the
  current process only.
```

### 3B.2 — std:time (doc 02)

**Spec:** docs/design/v4/02-datetime-api.md

**Dependencies:**

- `zoneinfo` (Python 3.9+ stdlib; already available)
- `tzdata` package — add to `pyproject.toml`:
  ```toml
  dependencies = [
      ...,
      "tzdata>=2024.1",
  ]
  ```

**Implementation:**

Substantial — 7 constructors, 12 calendar operations, 6 duration
constructors, accessor methods, format engine. Follow the design doc
specification end-to-end.

Suggested implementation order:

1. Datetime record type (internal representation: epoch_ms + zone)
2. Duration record type (internal representation: total_ms)
3. `time.now()`, `time.now_in(zone)` — quick wins
4. `time.from_epoch_ms()`, `time.at()` — explicit construction
5. Accessors (`.year`, `.month`, etc.)
6. Duration constructors (`time.ms`, `time.seconds`, etc.)
7. Calendar operations (`time.add_days`, `time.add_months`, etc.)
8. Zone conversion (`time.to_zone`, `time.to_utc`)
9. Format engine (chrono-style tokens)
10. `time.parse()` with strict parsing default
11. `time.from_iso8601()`, `time.from_http_date()`
12. Quick serialization helpers (`time.to_iso8601`, etc.)

**Test surface:** see doc 02's test surface enumeration (~30+ test
cases covering all constructors, accessors, calendar operations,
format tokens, DST edge cases, year range).

Estimated implementation time: 1 day focused work.

**Likely failure modes:**

- **`zoneinfo` not loading `tzdata` package automatically.**
  Verify `import tzdata` works before constructing zones.
- **DST gap and ambiguous time defaults.** The design says default
  is to err; verify the implementation actually errs (rather than
  silently shifting).
- **Format token edge cases.** Single-character ambiguity (e.g., `M`
  vs `m`). Test all tokens.
- **Year range enforcement.** Document says 1900-2099; verify the
  implementation rejects out-of-range values cleanly.

**Commit:** `feat(stdlib): std:time namespace for datetime/duration/calendar`

### 3B.3 — std:hash, std:encoding, std:secrets (doc 03)

**Spec:** docs/design/v4/03-crypto-hashing-api.md

**Dependencies:** Python stdlib only (`hashlib`, `hmac`, `secrets`,
`base64`, `binascii`, `urllib.parse`, `uuid`). No new pyproject.toml
entries.

**Implementation:**

Three namespaces. Implementation order:

1. **std:encoding** — straightforward Python stdlib wrappers
   (base64, hex, URL encoding). No dependencies on other namespaces.
2. **std:secrets** — Python `secrets` module wrappers plus UUIDv7
   implementation. UUIDv7 needs manual implementation for Python
   < 3.14 (see doc 03 substrate section).
3. **std:hash** — 15 hash functions (5 algorithms × 3 forms) + 5
   HMAC functions + constant-time compare. Hash record type for
   return values.

**Test surface:** see doc 03's test surface enumeration.

Estimated implementation time: 1 day focused work.

**Likely failure modes:**

- **UUIDv7 implementation.** Python 3.14+ has native support; check
  Python version and implement manually if needed. Layout per doc
  03: 48-bit timestamp + 4-bit version + 12 random + 2-bit variant
  + 62 random.
- **Hash record method dispatch.** The hash record returns
  `to_hex()` etc. as methods. Verify method dispatch works on Nodus
  records (existing record-with-methods pattern).
- **`hash.compare()` constant-time guarantee.** Use `hmac.compare_digest()` from Python stdlib — it's the canonical constant-time
  comparison. Don't roll your own.

**Commit:** `feat(stdlib): std:hash, std:encoding, std:secrets namespaces`

### 3B.4 — std:http (doc 01)

**Spec:** docs/design/v4/01-http-api.md

**Dependencies:**

- `httpx` package — add to `pyproject.toml`:
  ```toml
  dependencies = [
      ...,
      "httpx>=0.27,<1",
  ]
  ```

**Implementation:**

Most substantial 3B item. The design covers sync + async + streaming
+ SSE. Follow doc 01 end-to-end.

Suggested implementation order:

1. Sync functions: `http.get`, `http.post`, etc. — basic request/
   response
2. Response record with all fields (status, headers, body, etc.)
3. Async variants: `http.get_async`, etc.
4. Streaming: `http.stream`
5. SSE: `http.sse_stream`
6. Convenience helpers (`http.get_json`, etc.)

**Test surface:** see doc 01's test surface enumeration.

Estimated implementation time: 1-1.5 days focused work.

**Likely failure modes:**

- **httpx async loop integration.** httpx async needs an asyncio
  loop; if Nodus VM doesn't have one, you need to bridge. Pattern:
  per-VM asyncio loop, run async functions on it.
- **Response body memory for large downloads.** The design says
  body is in-memory by default; for downloads use `http.stream`.
  Verify the streaming path doesn't accidentally buffer the full
  body.
- **TLS verification toggle.** The design has `verify_ssl` option;
  verify the httpx integration respects it.

**Commit:** `feat(stdlib): std:http namespace with sync/async/streaming/SSE`

### 3B.5 — std:subprocess (doc 04)

**Spec:** docs/design/v4/04-subprocess-api.md

**Dependencies:** Python stdlib only (`subprocess`, `asyncio.subprocess`).
The async loop infrastructure from std:http is reused.

**Implementation:**

7 public functions per doc 04 (including `subprocess.spawn_shell`
which was added during Phase 1 design).

Suggested order:

1. Sync: `subprocess.run`, `subprocess.shell`
2. Async: `subprocess.run_async`, `subprocess.shell_async`
3. Spawn: `subprocess.spawn`, `subprocess.spawn_shell` (with
   channel-based stdout/stderr/stdin)
4. `subprocess.shell_quote` helper

**Test surface:** see doc 04's test surface enumeration.

Estimated implementation time: 1 day focused work.

**Likely failure modes:**

- **Channel-based stream pumping for spawn.** The pump tasks need
  to read from process pipes and push to Nodus channels with
  backpressure. Per the open implementation question in doc 04:
  bounded channel, pump blocks when full.
- **Cross-platform signal mapping.** Windows job objects vs Unix
  process groups. The design table shows the mapping; verify both
  platforms work.
- **`shell_quote` for Windows.** Microsoft's argument quoting rules
  (CommandLineToArgvW) are nontrivial. Use the documented algorithm
  or find a well-tested Python library that does it.

**Commit:** `feat(stdlib): std:subprocess namespace`

---

## Checkpoint 3B → 3C

Before starting 3C:

1. Full test suite passing
2. 5 commits landed (env, time, crypto, http, subprocess)
3. CHANGELOG.md has 5 "Added" entries
4. pyproject.toml updated with `tzdata>=2024.1` and `httpx>=0.27,<1`
5. Smoke test: each namespace importable and basic function callable

If any failures, stop and diagnose. 3C builds on 3B's stdlib
namespaces (the test framework uses http and subprocess for examples).

---

## Sub-phase 3C — Tier 2 language features + tooling

Five items:

1. String interpolation (doc 05) — language change (lexer/parser/
   compiler)
2. Tool registry (doc 06) — stdlib + Python-side API
3. Test framework (doc 07) — large feature; the std:test module
4. Coverage instrumentation (doc 08) — extends test framework
5. nodus_gate (doc 12) — external Python tooling

### 3C.1 — Doc 05: String interpolation

**Spec:** docs/design/v4/05-string-interpolation.md

**Critical constraint:** no new opcodes. Compile to existing
PUSH_STRING + expression bytecode + CALL_BUILTIN str + CONCAT.

**Implementation outline:**

1. Lexer mode stack: in_string_literal vs in_interpolation modes
   with paren_depth tracking
2. Five new token types: STRING_START, STRING_END, STRING_LITERAL,
   INTERP_START, INTERP_END
3. Maximum nesting depth: 32
4. Parser: InterpolatedString AST node with list of parts
5. Compiler: emit PUSH_STRING for literal parts + expression bytecode
   + CALL_BUILTIN str + CONCAT for joining
6. Source position metadata on each interpolation for error
   reporting
7. Top-level `:` inside interpolation = parse error (reserved for
   v4.x format specifiers)
8. Maximum nesting depth: 32

**Critical test:** verify migration impact — strings with literal
`\(` in v3.x become parse errors in v4.0. Migration: replace `\(`
with `\\(`.

**Test surface:** see doc 05's enumeration.

Estimated implementation time: 0.5-1 day.

**Commit:** `feat(lang): string interpolation via \(expr) syntax`

### 3C.2 — Doc 06: Tool registry

**Spec:** docs/design/v4/06-tool-registry-library-handlers.md

**Implementation outline:**

1. Tool registry data structure (single map per VM: name → metadata)
2. `std:tool` namespace with `register`, `unregister`, `invoke`,
   `lookup`, `list_tools`, `has`
3. Metadata schema validation (required + optional fields)
4. Schema normalization (simple form → JSON Schema)
5. Host-side API: `nodus_runtime.tool_registry` exposed in embedding
6. Value translation for Python-side handlers
7. Deprecated tool warning emission

**Dependencies:**

- `jsonschema` package — add to `pyproject.toml`

**Test surface:** see doc 06's enumeration.

Estimated implementation time: 1 day.

**Commit:** `feat(stdlib): std:tool registry with library-side handler support`

### 3C.3 — Doc 07: Test framework

**Spec:** docs/design/v4/07-test-framework-api.md

**Largest single 3C item.** Estimated 1.5-2 days.

**Implementation order:**

1. Assertion library (11 assertions)
2. Suite + case + lifecycle hooks
3. Fixture system with scopes
4. Parameterized tests
5. Async support (deterministic scheduler comes later in 3C.4 with
   coverage)
6. Test isolation
7. Test runner CLI (`nodus test`)
8. Output formatters (pretty, plain, json, junit)

**Dependencies:**

- `watchdog` package (optional) — add to `pyproject.toml` as optional

**Test surface:** see doc 07's enumeration.

**Likely failure modes:**

- **Deterministic async scheduler.** Asyncio loop replacement is
  the most complex piece. Test in isolation first.
- **Test isolation tracking.** Snapshotting and reverting state is
  the second-most-complex piece. Get the simple cases (env, cwd)
  working first; add tool registry isolation last.
- **Diff rendering for complex values.** Use Python's `difflib`
  with structure-aware wrappers.

**Commit:** `feat(stdlib): std:test framework with assertions, fixtures, async, isolation`

### 3C.4 — Doc 08: Coverage instrumentation

**Spec:** docs/design/v4/08-test-framework-coverage.md

**Depends on:** 3C.3 test framework

**Implementation outline:**

1. VM event subscription (use existing source-position event
   infrastructure)
2. Coverage collector class
3. Executable line detection (compiler-side metadata)
4. Exclusion comment parsing
5. Report generation (JSON, HTML, optionally Cobertura XML, LCOV)
6. CLI flags integration

**Estimated time:** 0.5 day.

**Commit:** `feat(stdlib): std:test coverage with source-line attribution`

### 3C.5 — Doc 12: nodus_gate

**Spec:** docs/design/v4/12-doc-vs-code-gate.md

**Critical:** Python script in `tools/nodus_gate/`, NOT a Nodus
script (chicken-and-egg constraint — gate runs before wheel is
built).

**Implementation outline:**

1. CLI entry point (`tools/nodus_gate/cli.py`)
2. Markdown parser (use `mistune` or `markdown-it-py`)
3. Static phase: symbol extraction + verification
4. Runtime phase: code block execution with sandbox
5. Closed-issues phase: CHANGELOG parsing + wheel-based test
   execution
6. Wheel cache with git-status-based invalidation
7. Allowlist file support
8. Output formatters (pretty, plain, json)

**Dependencies:**

- `mistune` or `markdown-it-py` (parser)
- `build` (wheel construction)

Add to `pyproject.toml` under `[project.optional-dependencies] dev` or similar.

**Estimated time:** 1-1.5 days.

**Commit:** `feat(tools): nodus_gate three-phase verification gate`

---

## Checkpoint 3C → 3D

Before starting 3D:

1. Full test suite passing
2. 5 commits landed in 3C (interpolation, tool registry, test
   framework, coverage, gate)
3. CHANGELOG.md has 5 "Added" entries for 3C items
4. pyproject.toml updated with `jsonschema`, optionally `watchdog`,
   dev: `mistune` and `build`
5. Smoke test: each new feature usable
6. `nodus_gate --static` runs (will find drift; that's fine — it
   just needs to RUN; the drift is resolved in Phase 4)

---

## Sub-phase 3D — Tier 3 finalized

Two items remaining. Both small.

### 3D.1 — Doc 10: type() naming reconciliation

**Spec:** docs/design/v4/10-type-naming-reconciliation.md

**Implementation outline:**

1. Update `type()` builtin: change `"number"` return to `"float"`
   for float values
2. Add `math.is_numeric`, `math.is_int`, `math.is_float` as builtins
3. Audit existing v3.x tests for `"number"` references; update to
   `"float"`
4. Update LANGUAGE_SPEC.md and stdlib reference

**Test surface:** doc 10 enumeration.

Estimated time: 0.5 day (most time is the audit).

**Commit:** `feat(types): type() returns "float" for floats; new math.is_numeric/is_int/is_float`

### 3D.2 — Doc 11: Equality coercion

**Spec:** docs/design/v4/11-equality-coercion.md

**Implementation outline:**

1. Update equality opcode: restrict cross-type coercion to numeric
   types only
2. Add `type_eq(a, b)` as builtin
3. Add `bool.equal(value, bool_value)` (placement TBD per Phase 3B
   verification — could be in std:bool namespace, std:equality, or as builtin; pick based on existing v3.x bool namespace state)
4. Update LANGUAGE_SPEC.md equality section

**Test surface:** doc 11 enumeration.

Estimated time: 0.5 day.

**Commit:** `feat(types): numeric-only equality coercion; type_eq and bool.equal helpers`

---

## Phase 3 exit criteria

Phase 3 is complete when:

1. **All 15 Phase 1 design docs implemented.** Each has a
   corresponding commit and test file.
2. **`std:env` implemented** (inline spec in this runbook; no Phase
   1 doc).
3. **Test suite is green** with all new tests passing. Baseline
   (812) plus new tests; final count likely 1500-2000.
4. **CHANGELOG.md [Unreleased] is comprehensive** — every Phase 3
   commit added an entry.
5. **pyproject.toml updated** with all new dependencies (`tzdata`,
   `httpx`, `jsonschema`, optional `watchdog`, dev tools `mistune`,
   `build`).
6. **`BYTECODE_VERSION` is still 4.** No new opcodes added.
7. **Smoke test passes:** basic usage of each new namespace works in
   the REPL or via `nodus run`.
8. **No known regressions** in pre-existing v3.x functionality.

### Total commits in Phase 3

Expected count: ~16 commits.

- 3A: 4 commits (docs 13, 09, 14, 15)
- 3B: 5 commits (env, time, crypto, http, subprocess)
- 3C: 5 commits (interpolation, tool registry, test framework,
  coverage, gate)
- 3D: 2 commits (type naming, equality)

### What Phase 3 does NOT do

- Migration guide (Phase 4 deliverable)
- LANGUAGE_SPEC.md comprehensive update (Phase 4; per-feature
  updates happen in Phase 3 commits)
- nodus_gate running clean (Phase 4 reconciles findings)
- v4.0 release artifacts (Phase 5)

---

## Recovery patterns

If something breaks mid-burst:

### If a single sub-phase item fails after committing

Revert the commit: `git revert <hash>`. The next item depends on the
state at the previous successful commit, so reverting the bad one
restores the baseline.

### If a sub-phase doesn't complete

Stop at the last successful commit. The next chat session can pick up
from there with full context (this runbook + commit log + memory).

The Phase 3 burst can be paused and resumed across sessions if
needed; the runbook is the recovery point.

### If a Phase 1 design doc proves wrong during implementation

Document the discrepancy. Three options:

1. **Implement the design as written.** Sometimes the design's
   constraints force the right shape even if implementation seems
   awkward.
2. **Implement deviations and amend the design doc.** Small
   deviations get a paragraph in the design doc explaining the
   change.
3. **Stop and redesign.** If the deviation is large, pause and
   surface it in a chat session.

Default to option 1 or 2. Option 3 is the escape hatch when the
design genuinely needs revision.

### If a test suite regression appears

Bisect to find the introducing commit. The fix path:

1. Confirm the regression is in your work, not a flaky test
2. If it's clearly your work, fix forward in the next commit
3. If it's flaky, document and continue (note in session summary)

---

## Phase 3 session summary template

At the end of each Phase 3 work session, report:

1. **Sub-phase progress.** Which sub-phases / items completed.
2. **Commit log.** Each commit hash with one-line description.
3. **Test count.** Before / after, both counts.
4. **Any deviations from this runbook.** What changed, why.
5. **Open issues / findings.** Anything that surfaced that needs
   chat-session attention.
6. **Confidence in current state.** Green / yellow / red, with
   explanation.
7. **Estimated remaining time.** Hours or days based on current
   progress.

Use this template to keep the chat session in sync with Claude Code
work.

---

## Phase 3 → Phase 4 handoff

When Phase 3 is complete:

- Memory update: record Phase 3 completion with commit range
- LANGUAGE_VISION.md update (probably done in Phase 4, but verify)
- All 15 Phase 1 design docs reference implementation commits
- TECH_DEBT.md Phase 3B questions: mark resolved questions as
  RESOLVED with date; document unresolved questions
- Phase 4 prep can begin: docs sweep + migration guide + nodus_gate
  reconciliation

---

**End of Phase 3 runbook.**

This document covers the full concentrated burst. Read end-to-end
before starting. Stop at each checkpoint to verify state. The
discipline that produced clean Phase 1 and Phase 2 carries into
Phase 3; this runbook is the scaffolding.
