# Nodus v2.0.0 — Evaluation Log
Evaluator: Claude Code (researcher mode, stress test)
Date: 2026-05-23

---

## [08:00] SETUP

- Working directory: `C:\dev\project nodus` (empty, non-git)
- Created `.venv` via `python -m venv .venv`
- Installed `nodus-lang==2.0.0` from PyPI: `Successfully installed nodus-lang-2.0.0`
- Package: 199 kB wheel, MIT license, author Shawn Knight
- Confirmed: `.\.venv\Scripts\nodus --version` → `Nodus 2.0.0`
- Created `scratch/` directory

---

## [08:01] RESEARCH PASS — PyPI JSON API

PyPI JSON: https://pypi.org/pypi/nodus-lang/2.0.0/json

- No dependencies on default install (FastAPI + uvicorn are optional under `[server]` extra)
- Requires Python >=3.10
- Classifiers: "Production/Stable", "Compilers, Interpreters"
- GitHub: https://github.com/Masterplanner25/Nodus

---

## [08:02] RESEARCH PASS — README

One-sentence canonical description from README:
> "Nodus is a bytecode-compiled scripting language and runtime … implementing the Infinity Algorithm's execution model as a first-class language construct, expressed through coroutines, task graphs, workflows, and goals on a deterministic stack-based VM."

Key claims: `nodus init`, `nodus run`, `nodus repl`, `std:` module prefix, `.nd` extension.

---

## [08:03] RESEARCH PASS — CHANGELOG (v2.0.0 focus)

v2.0.0 released 2026-05-23. Key additions:
- Comprehensive `--help` for all subcommands
- Import error messages enumerate all tried paths
- `memory_has(key)` builtin and `memory.has(key)` method
- `--trace-imports` flag with ASCII `->` and `--` (fixed from Unicode `→` `—`)
- `--trace` flag with structured opcode output
- Windows encoding bug fix: Unicode replaced with ASCII in import tracing

Noted: the description says Windows encoding fixed for `--trace-imports` specifically.

---

## [08:04] RESEARCH PASS — LANGUAGE_SPEC.md (via web fetch)

- Types: number (float-based), bool, string, nil, list, map, record
- `record {}` vs `{}` (map) are distinct types
- `while (cond)` requires parentheses; `for name in iterable {}` for iteration
- `try { } catch err { }` — catch binds without parens
- `throw <value>` — err.kind should be "thrown" for any explicit throw
- Import: `import "path"`, `import "std:module"`, `import "package:name"`
- `memory.has(key)` — fixed in v2.0.0, should return true even when nil stored
- Modulo: no `%` operator mentioned (red flag)

---

## [08:05] RESEARCH PASS — ARCHITECTURE.md

- Pipeline: lexer → parser → AST → compiler → optimizer → stack VM
- 47 stable opcodes at version 4
- Round-robin scheduler (1000 instruction budget per task)
- Workflow lowering at compile time via `_StateRewriter`
- LSP and DAP support (documented)

---

## [08:06] RESEARCH PASS — REPL.md

REPL commands documented: `:ast`, `:dis`, `:type`, `:help`, `:quit`
REPL prompt: `> ` for input, `... ` for continuation
History stored in `~/.nodus_history`
Note: `:modules`, `:reload`, `:clear`, `:reset` not mentioned in REPL.md but
`nodus repl --help` shows `:clear` and `:reset`.

---

## [08:07] RESEARCH PASS — NODUS.md

One-sentence: "a lightweight scripting language built around a bytecode compiler and stack-based VM, optimized for automation and orchestration workflows."

Slight tension with README which emphasizes "Infinity Algorithm's execution model" — NODUS.md is more grounded, README is more aspirational.

---

## [08:08] RESEARCH PASS — EXAMPLES.md

Documents: coroutines, channels, task graphs, workflows, events.
CLI commands shown: `nodus ast`, `nodus dis`, `nodus fmt`, `nodus check`
(Consistent with actual CLI help.)

---

## [08:09] RESEARCH PASS — DEVELOPMENT.md

Internal architecture: `src/nodus/frontend/lexer.py`, `parser.py`, `ast/ast_nodes.py`,
`compiler/compiler.py`, `vm/vm.py`, `orchestration/`
Not directly relevant to user evaluation but confirms the stack is Python-implemented.

---

## [08:10] BASELINE: nodus --help

Command list is extremely long — 50+ subcommands. Highlights beyond the documented set:
`nodus debug`, `nodus profile`, `nodus serve`, `nodus lsp`, `nodus dap`,
`nodus snapshot/snapshots/restore`, `nodus worker`, `nodus workflow-run/plan/resume/checkpoints`,
`nodus goal-run/plan/resume`, `nodus tool-call`, `nodus agent-call`,
`nodus memory-get/put/delete/keys`, `nodus status`, `nodus install/update/add/remove`,
`nodus package-list/deps`, `nodus cache clear`, `nodus login/logout/publish`

No documentation exists in the fetched docs for most of these.

**FINDING:** The help surface is 5-10× larger than the documented API. A new user has no guidance on what's stable vs experimental.

---

## [08:11] BASELINE: Per-subcommand --help

- `nodus run --help`: PASS — shows usage and options
- `nodus check --help`: PASS (no options listed, just description)
- `nodus fmt --help`: PASS
- `nodus ast --help`: **FAIL** — "File not found: --help" (treats --help as filename)
- `nodus dis --help`: **FAIL** — "File not found: --help" (same)
- `nodus repl --help`: PASS — lists `:help, :quit, :clear, :reset` (not :ast, :dis, :type)
- `nodus init --help`: PASS
- `nodus graph --help`: PASS (limited)
- `nodus workflow --help`: PASS (limited)

**FINDING [BUG-001]:** `nodus ast --help` and `nodus dis --help` error instead of showing help.

---

## [08:12] BASELINE: nodus run scratch/hello.nd

`print("Hello, Nodus!")` → `Hello, Nodus!` — PASS

---

## [08:13] BASELINE: nodus check scratch/hello.nd

Produced no output, exit code 0. **FINDING [BUG-002]:** No "OK" or success confirmation on clean file.
Also: `nodus check scratch/error_file.nd` where file calls `undefined_func()` → exit 0, no error.
The checker only catches syntax errors, not semantic ones. Passes a file that will fail at runtime.

---

## [08:14] BASELINE: nodus init

`nodus init --path scratch/testproj` → creates `.nodus/`, `src/main.nd`, `nodus.toml`. No output. **FINDING [BUG-003]:** Silent success — no confirmation message.
`src/main.nd` contains: `print("hello from nodus")`. Sensible default.
`nodus.toml`: `name = "testproj"`, `version = "0.1.0"`, empty `[dependencies]`.

---

## [08:15] BASELINE: Programmatic API

`from nodus import run_source; print(run_source('print(1+1)'))` →
```
2.0
<nodus.vm.vm.VM object at 0x...>
```
Two issues:
1. Numbers display as floats (`2.0` not `2`)
2. Module-level `run_source` returns a VM object, not a useful result
**FINDING [BUG-004]:** `nodus.run_source` API returns VM object; useful data is captured stdout only.

NodusRuntime.run_source: returns `dict` with `{'ok': True, 'stdout': '...', 'stderr': '...', ...}` on success. Raises exceptions on failure. The `ok` key is ALWAYS True if the call returns — errors always raise. **FINDING [BUG-005]:** NodusRuntime.run_source never returns ok=False; errors are exceptions only, not dict returns.

Default `timeout_ms=200` for NodusRuntime (from config.py). Extremely short for any non-trivial script.

---

## [08:16] STRESS TEST 3.1 — Parser/Lexer

**Empty file:** No output, no error. PASS.
**Whitespace-only file:** No output, no error. PASS.
**Comment-only file:** No output, no error. PASS.

**Unicode identifiers:** `let café = "hello"` →
`Syntax error at file:1:8: Unexpected character '?'`
Non-ASCII characters in identifiers rejected. Error message shows replacement character '?' (cp1252 encoding issue) instead of the actual character. **FINDING [BUG-006]**

**Long identifier (1000 chars):** PASS — runs fine.

**Deeply nested expressions (100 parens):** →
`Error at file: maximum recursion depth exceeded`
Python `RecursionError` leaks through. No file/line in error. **FINDING [BUG-007]** (CRITICAL)

**Unclosed string:** `print("hello` →
`Syntax error at file:1:7: Unexpected character '"'`
Confusing — the error is on the opening quote position with "Unexpected character" which is misleading. Better: "Unterminated string literal". **FINDING [BUG-008]**

**Incomplete operator:** `let x = 1 +` →
`Syntax error at file:1:12: Unexpected end of statement ? expression is incomplete`
The `?` is a non-ASCII character (likely `—`) that doesn't render in cp1252. **FINDING [BUG-009]**

**Reserved word as identifier:** `let if = 5` →
`Syntax error: Expected identifier, got 'if'` — clear. PASS.

**Modulo operator:** `print(10 % 3)` →
`Syntax error: Unexpected character '%'`
**FINDING [BUG-010]** (HIGH): `%` modulo operator is not implemented.

**Scientific notation:** `1.7976931348623157e+308` →
`Syntax error: Expected ')', got identifier ('e')`
**FINDING [BUG-011]** (HIGH): Floating-point scientific notation literals not parsed.

---

## [08:17] STRESS TEST 3.2 — Type System

**All numbers are floats:**
- `print(10 / 2)` → `5.0`
- `print(7 / 1)` → `7.0`
- `print(999999999999999999)` → `1e+18` (float precision loss)
**FINDING [BUG-012]:** No integer type; large integers silently truncate.

**Division by zero:** `print(1 / 0)` →
`Runtime error: Division by zero` — clear, correct. PASS.

**nil handling:** `print(nil + 1)` →
`Type error: Cannot add nil and number` — clear, with location. PASS.

**Cross-type comparison:**
- `"5" == 5` → `false` ✓
- `nil == false` → `false` ✓
- `nil == nil` → `true` ✓
- `0 == false` → `true` (0 is falsy — coercion!) 
- `"" == false` → `false` (empty string is NOT falsy)
**FINDING [BUG-013]:** `0 == false` is `true` (numeric zero equals boolean false). Surprising behavior.

---

## [08:18] STRESS TEST 3.3 — Control Flow

**Infinite loop with --step-limit:**
`nodus run --step-limit 1000 ...` → `Sandbox error: Execution step limit exceeded` — PASS.

**Time limit:**
`nodus run --time-limit 1 ...` → `Sandbox error: Execution timed out` — PASS.

**Deep recursion with --step-limit:**
`nodus run --step-limit 10000 scratch/recurse.nd` → `Sandbox error: Execution step limit exceeded`
No Python traceback. PASS.

**`while true` syntax:**
`while true { ... }` → `Syntax error: Expected '(', got 'true'`
Parentheses required. Undocumented but consistent with other Nodus syntax. Minor UX issue.

**`foreach` keyword:**
`foreach item in items { }` → `Syntax error: Unexpected 'in' in expression`
`foreach` is NOT valid syntax. Correct syntax is `for item in iterable { }`.
NODUS.md lists `foreach` as a supported control structure. **FINDING [BUG-014]** (docs lie)

**`for name in iterable` syntax:** PASS — works correctly for lists.

**C-style `for` loop:** `for (let i = 0; i < 3; i = i + 1) { }` — PASS.

---

## [08:19] STRESS TEST 3.4 — Module System

**Missing module:** Clear error listing all tried paths. Excellent UX. PASS.

**Import .py file:** Appends `.nd` and tries that path. Error not specialized ("trying not_nd.py.nd"). Could say "cannot import Python files". LOW.

**Path traversal (import):** `import "../../Windows/..."` →
`Import error: path escapes the project root.` — Blocked. PASS.

**Self-import:** `import "./self_import"` →
`Import error: Circular import detected: self_import.nd -> self_import.nd` — Detected. PASS.

**Circular import A↔B:** Detected with full chain: `a -> b -> a`. PASS.

---

## [08:20] STRESS TEST 3.5 — Standard Library (fs)

**fs.read missing file:** Runtime error pointing to stdlib internals (`fs.nd:2:22`), not user call site. **FINDING [BUG-015]:** Stack trace on stdlib errors shows stdlib path, not user file line.

**fs.read path traversal:**
`fs.read("../../Windows/System32/cmd.exe")` →
Tries to read the file! Fails only because cmd.exe is binary (UTF-8 decode error).
**FINDING [BUG-016]** (CRITICAL): `fs.read` does NOT block path traversal. Import system blocks `../`, fs.read does not.

**fs.read file with BOM:**
Attempting to read a file with UTF-8 BOM triggers a Python traceback in the CLI:
`UnicodeEncodeError: 'charmap' codec can't encode character '﻿'`
The CLI crashes unhandled. **FINDING [BUG-017]** (CRITICAL): Python traceback on UTF-8 BOM file read.

---

## [08:21] STRESS TEST 3.5 — Standard Library (json)

**json.parse valid JSON:** PASS — returns records for objects, lists for arrays.
**json.stringify:** PASS.
**json.parse malformed JSON:** Raises runtime error but stack trace points to `json.nd:2:23` (stdlib) not user call site. **FINDING [BUG-015] (same as above)**

**json type coercion:**
- JSON objects → Nodus records (dot-notation only, no `[]` access, no `keys()`)
- JSON arrays → Nodus lists (OK)
- JSON numbers → Nodus floats (2 → 2.0)
**FINDING [BUG-018]** (HIGH): json.parse returns records; records don't support dynamic field access. Generic JSON processing is painful.

---

## [08:22] STRESS TEST 3.5 — Standard Library (strings)

`strings.upper`, `strings.lower`, `strings.trim`, `strings.split`, `strings.contains`: PASS.
`strings.replace` → `Key error: Missing module export: replace`
**FINDING [BUG-019]** (HIGH): `strings.replace` is not implemented but is a commonly expected function.

`strings.len`: Not exported from strings module; `len()` is a global builtin. Inconsistency.

---

## [08:23] STRESS TEST 3.5 — Standard Library (memory)

`memory.has("key1")` after `memory.put("key1", "value")` → `true` ✓
`memory.has("nil_key")` after `memory.put("nil_key", nil)` → `true` ✓ (v2.0.0 fix works)
`memory.has("missing")` → `false` ✓
`memory.has("key1")` after `memory.delete("key1")` → `false` ✓

Memory API: All documented operations work correctly. The v2.0.0 `memory.has` fix is confirmed working.

---

## [08:24] STRESS TEST 3.5 — Maps vs Records

Records (`record {}`): dot-notation access only; no `[]`, no `keys()`.
Maps (`{}`): `[]` access and `keys()` work; but accessing missing key throws "Missing map key" error.
No `has_key()` builtin — must use `std:collections.has_key()`.
**FINDING [BUG-020]** (MEDIUM): No builtin map key-existence check; requires stdlib import.

---

## [08:25] STRESS TEST 3.5 — Standard Library (math)

`math.sqrt(16)` → `4.0` ✓
`math.abs(-5)` → `5.0` (via direct test) ✓
`math.floor(3.7)` → `3.0` ✓
`math.ceil(3.2)` → `4.0` ✓
`math.min(3, 5)` → `3.0` ✓
`math.max(3, 5)` → `5.0` ✓

No `math.pow`, `math.log`, `math.sin/cos/tan`, `math.pi/e` constants.
For a scripting language, math is minimal. LOW.

---

## [08:26] STRESS TEST 3.6 — REPL

Cannot test interactively (non-interactive shell). Tested via documented commands:
- `nodus repl --help` lists `:help, :quit, :clear, :reset` — no mention of `:ast, :dis, :type` from REPL.md
- `nodus ast <file>` command (non-REPL) works correctly
- `nodus dis <file>` command (non-REPL) works correctly
**FINDING [BUG-021]:** Discrepancy between REPL.md commands (:ast, :dis, :type, :modules, :reload) and what `nodus repl --help` shows (:clear, :reset).

---

## [08:27] STRESS TEST 3.7 — Workflow Runner

**Correct workflow syntax:** `for <step> after <dep> { }` — not `depends:`. Docs use `after` correctly.

**Basic workflow run:** JSON output with task metadata. `print()` inside steps is silently swallowed — no stdout from step bodies. **FINDING [BUG-022]** (HIGH).

**Failing workflow:** `throw` inside step → JSON output with `"failed": ["task_1"]` and error message. Clean propagation. PASS.

---

## [08:28] STRESS TEST 3.8 — Tracing and Observability

**--trace:** Opcode-level trace on stderr. Format: `[trace] OPCODE  line N  detail`. PASS.
**--trace-no-loc:** Removes line numbers. Trailing whitespace left in output. COSMETIC.
**--trace-imports:** Uses `->` (ASCII). v2.0.0 fix confirmed working on Windows.
**--trace with --step-limit:** Shows instructions up to limit, then error. PASS.
**Combination flags:** No unexpected interactions found. PASS.

---

## [08:29] STRESS TEST 3.9 — Error Message Quality

| Error Type | File/Line | What | Where | Suggests Fix | Nodus or Python |
|---|---|---|---|---|---|
| Unclosed string | Y | Confusing | Y | N | Nodus |
| Bad operator | Y | OK + broken char | Y | N | Nodus |
| Unicode identifier | Y | Shows '?' | Y | N | Nodus |
| Deep nesting | N | Python traceback | N | N | Python |
| Missing module | Y | Excellent (shows paths) | Y | Partly | Nodus |
| Type error (nil+num) | Y | Clear | Y | N | Nodus |
| Division by zero | Y | Clear | Y | N | Nodus |
| Undefined function | Y | Clear | Y | N | Nodus |
| Circular import | Y | Clear chain | Y | N | Nodus |
| Path traversal (import) | Y | Clear | Y | N | Nodus |
| Stdlib error | Y | Points to stdlib | N (stdlib) | N | Nodus |
| BOM file read | N | Python traceback | N | N | Python |

---

## [08:30] STRESS TEST 3.10 — Embedded API

**NodusRuntime.run_source success:** Returns `{'ok': True, 'stdout': ..., 'stderr': ..., ...}`. PASS.

**NodusRuntime error behavior:** ALL errors (step limit, runtime error, type error, sandbox) raise exceptions rather than returning `{'ok': False, ...}`. The `ok` key is always True in returned dicts.

**NodusRuntime default timeout:** 200ms (`EXECUTION_TIMEOUT_MS` in config.py). For non-trivial scripts this will time out before they finish.

**Two runtimes in same process:** Memory store is isolated between runtimes (tested via `memory.put` in rt_a, then `memory.has` in rt_b returns `false`). PASS.

**register_function:** Works for simple fixed-arity functions. PASS.

**allowed_paths sandboxing:** When `allowed_paths` is set, path violations raise NodusSandboxError. PASS for embedded mode. **But CLI mode has no path restrictions** (see BUG-016).

**inspect.getsource(NodusRuntime.run_source):** Fails with UnicodeEncodeError — the docstring contains `→` (U+2192) which cp1252 cannot encode. **FINDING [BUG-023]:** Unicode in docstrings breaks `inspect` on Windows.

---

## [08:31] SECTION 4 — Build Something Real

**Task:** JSON log transformer — reads JSON logs, computes aggregates, writes summary JSON.

**Files:** `scratch/real_task/main.nd`, `scratch/real_task/stats.nd`
**Modules used:** std:fs, std:json, std:strings, std:math, std:collections, plus local import ./stats

**Time breakdown:**
- 10 min: initial design and writing
- 15 min: debugging json.parse → record type (no dynamic field access)
  - Tried `entry["level"]` → Type error: Indexing not supported on records
  - Tried `keys(record)` → Type error: keys(x) expects a map
  - Solution: switch to function extractors passed as arguments
- 10 min: debugging map key existence (no `has_key` builtin)
  - `counts["INFO"]` on empty map → "Missing map key: INFO" (not nil)
  - Solution: import `std:collections.has_key`
- 5 min: final working version

**Total: ~40 minutes for ~100 lines across 2 files**

**Rough edges encountered:**
1. `json.parse` → records (unexpected; common assumption is map-like access)
2. Missing `has_key` builtin for maps
3. All numbers print as floats ("10.0" not "10")
4. Iterable syntax: `foreach` doesn't exist, must use `for item in list`

---

## [08:32] SECTION 5 — Meta-Observations

**Identity:** Nodus exists to provide a sandboxed, embeddable scripting language for orchestration workflows. The "Infinity Algorithm" framing in the README is aspirational and not grounded in the docs or the runtime. The practical identity (workflow runner + safe scripting) is clearer and more defensible.

**Audience:** Language hobbyists and builders who need an embeddable sandbox. NOT production scripting yet (missing: modulo, integer type, dynamic record access, robust Windows support).

**Stability:** Claims "Production/Stable" on PyPI. Does not feel stable:
- 2 CRITICAL bugs (path traversal, Python traceback on BOM)
- Missing basic operator (`%`)
- fmt --check unreliable until first format pass
- 50+ undocumented CLI commands

**Documentation truth:** Core language spec (control flow, types, modules) is accurate. Error handling semantics (err.kind for string throws) is wrong. `foreach` keyword documented but doesn't exist. REPL command lists inconsistent between REPL.md and --help output.

**Sharp corners:** 8-10 genuine "had to figure that out the hard way" moments (records vs maps, has_key, for-in syntax, modulo, scientific notation, fmt --check CRLF, workflow print, NodusRuntime exception model).
