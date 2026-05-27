# Nodus v4.0 — Design Doc 12: Doc-vs-Code Reconciliation Gate

**Phase:** 1 (design docs)
**Status:** Locked
**Implements:** Decision 15 (Doc-vs-Code Reconciliation Gate) from `00-phase-0-decisions.md`
**Date:** 2026-05-26
**Maintainer:** Shawn Knight (Masterplanner25)

---

## Problem statement

v4.0 ships a three-phase verification gate (`nodus_gate`) that catches
documentation drift, missing-symbol documentation, and patch-closure
failures before release. Decision 15 (Phase 0) locked the high-level
shape: three phases (static, runtime, closed-issues), doc conventions
for code blocks, integration into both playbooks as mandatory pre-
release steps.

This doc specifies the operational details: what's scanned, how
symbols are extracted, how code blocks execute, how closed-issue tests
are located, CLI behavior, and implementation substrate. It closes the
loop on the v3.0.1 and v3.0.2 process gaps that surfaced the need for
this gate.

The gate exists because the eval cycle revealed three distinct failure
modes that conventional test coverage doesn't catch:

1. **v3.0.0 had 6 missing functions** documented in LANGUAGE_SPEC.md
   but never implemented. Static analysis would catch this.
2. **v3.0.1 had `math.log` argument swap** producing wrong results
   while doc examples assumed correct behavior. Runtime verification
   would catch this.
3. **v3.0.1 had BUG-E12 patch closure failure** where the `1I` parse
   error fix was committed to source but didn't ship in the wheel.
   Issue verification against the installed wheel would catch this.

v4.0's "production-ready orchestration DSL" theme requires verifiable
claims. The gate is the mechanism.

---

## What Phase 0 already settled

From Decision 15:

- Three-phase verification gate with `nodus_gate` command
- Phase 1 (`--static`): every documented symbol exists in shipped code
- Phase 2 (`--runtime`): every doc code block produces documented output
- Phase 3 (`--closed-issues`): every CHANGELOG-claimed fix has passing
  test against installed wheel
- `--all`: run all three
- Doc conventions:
  - ` ```nodus ` — runs, verified not to error
  - ` ```nodus-no-run ` — illustrative, not verified
  - ` ```nodus-expect=output ` — runs, output verified
- Integrated into both playbooks as mandatory pre-release steps

This doc resolves:

- Static phase: which documents are scanned, what counts as a symbol
- Runtime phase: code block isolation, output matching, sandbox
- Closed-issues phase: test location, naming conventions, wheel
  execution
- CLI specification with selective execution, caching, output formats
- Implementation substrate (Python script in `tools/nodus_gate/`)

---

## Bytecode impact

**No new opcodes required. `BYTECODE_VERSION` stays at 4.**

The gate is external tooling — a Python script that reads source code
and documentation, runs code blocks against the development Nodus VM,
and runs closed-issue tests against an installed wheel. It does not
modify the VM, the compiler, or any bytecode.

The gate runs BEFORE the wheel is built (during development) and AGAIN
after the wheel is built (during release prep). Both invocations
operate on source-code artifacts (markdown files, Python tests). No
language-level changes are required.

The frozen-bytecode contract from v1.0 is preserved.

---

## Doc conventions

Code blocks in documentation use four conventions to communicate intent
to the gate:

### ` ```nodus ` — runs, verified not to error

The most common convention. The code block is valid Nodus code; the
gate runs it during the runtime phase and verifies it doesn't error.
Output is not checked.

````markdown
Here's how to call an HTTP endpoint:

```nodus
let r = http.get("https://example.com")
```
````

### ` ```nodus-no-run ` — illustrative, not verified

The code block contains illustrative pseudocode, partial examples, or
patterns that can't be run in isolation (require external services,
contain placeholder values, demonstrate broken patterns intentionally).
The gate skips runtime verification but still uses the block for
symbol extraction during the static phase.

````markdown
This pattern is NOT supported in v4.0:

```nodus-no-run
let r = http.get(url, {retries: 3})   // no such option
```
````

### ` ```nodus-expect=output ` — runs, output verified

The code block runs AND its output is verified against an expected-
output block that immediately follows.

````markdown
Format a date for HTTP:

```nodus-expect=output
let dt = time.from_epoch_ms(1716732600000)
print(time.to_http_date(dt))
```

Output:

```
Sun, 26 May 2024 14:30:00 GMT
```
````

The gate matches the expected-output block (the first code block after
the `-expect=output` marker) against the actual stdout produced by
running the test block. Output matching rules below.

### ` ```nodus-skip ` — opt out entirely

Some code blocks should be ignored by all phases of the gate. Use
sparingly:

````markdown
The deprecated v3.x pattern:

```nodus-skip
type(x) == "number"   // v3.x; no longer valid in v4.0
```
````

This is the escape hatch for migration guides that intentionally show
broken-by-design examples. The gate doesn't scan, doesn't run, doesn't
verify.

---

## Static phase (`--static`)

### Scanned documents

By default, the static phase scans:

- `docs/language/LANGUAGE_SPEC.md`
- `docs/language/DESIGN.md`
- `docs/language/STYLE_GUIDE.md`
- `docs/guide/*.md` (all files in the guide directory, recursively)
- `docs/policy/*.md` (error surfaces, error handling policies)
- `docs/runtime/*.md` (runtime reference documentation)
- `llms.txt` (project root)
- `README.md` (project root)

NOT scanned by default:

- `docs/design/v*/` (design docs reference symbols that may not exist
  yet — forward-looking content)
- `docs/governance/` (process docs; not code-focused)
- `CHANGELOG.md` (historical record; processed by closed-issues phase
  instead)
- `docs/migration/` (migration guides; intentionally show v3.x patterns
  that don't exist in v4.0)

The `--include-design` flag opts into scanning design docs. Useful for
post-release gate runs to verify that implementation matches design
specifications.

### Symbol extraction

The gate extracts these patterns as documented symbols:

| Pattern | Extracted as |
|---|---|
| `name(...)` in prose or code block | Function call: verify `name` is callable |
| `import "namespace"` or `import "namespace" as alias` | Module reference: verify `namespace` exists |
| `module.function(...)` | Qualified function: verify `module.function` exists |
| `kind: "category_name"` in code block | Err kind: verify `category_name` is documented in error-surfaces.md |
| `category: "value"` in code block (within payload) | Err category: verify `value` is one of the documented categories |
| `nodus <subcommand>` in code block or prose | CLI command: verify subcommand exists |

The extractor uses lexical patterns. False positives are minimized by
requiring specific structural context (parentheses for function calls,
quotes for kind strings, etc.).

**Not extracted** (false-positive risk):

- Bare identifiers in prose without parentheses or other structural
  context (might be referring to a concept, not a symbol)
- Variable names in code blocks (could be anything)
- Comment-only mentions
- Strings inside `nodus-skip` or `nodus-no-run` blocks (still extracted
  for static phase; the run-skip applies to runtime phase only)

### Verification

For each extracted symbol, the gate:

1. Imports the Nodus runtime
2. Attempts to resolve the symbol (function lookup, module load, kind
   table check)
3. Reports missing symbols with file:line references

A symbol counts as "documented" if it appears in any scanned doc; the
gate produces one finding per missing symbol regardless of how many
docs reference it.

### Output

```
$ nodus_gate --static

Scanning 47 documents in docs/...
Extracting symbols...
Found 312 documented symbols

Verifying symbols against shipped code...

FAIL docs/language/LANGUAGE_SPEC.md:248
  Symbol 'strings.template' is documented but not found in shipped code.
  Suggestion: either implement strings.template or remove from docs.

FAIL docs/guide/error-handling.md:127
  Err kind 'parse_error' is documented but not in error-surfaces.md
  registered kinds.
  Suggestion: add 'parse_error' to docs/policy/error-surfaces.md or
  use a registered kind.

Summary: 2 failures across 47 documents (310/312 symbols valid)
```

False positives can be suppressed via per-block annotations or by
adding to the gate's allowlist (`.nodusgate-allow`).

---

## Runtime phase (`--runtime`)

### Code block discovery

The gate scans the same documents as the static phase (plus optional
`--include-design`). For each code block:

- ` ```nodus ` → mark for execution; verify no error
- ` ```nodus-no-run ` → skip
- ` ```nodus-expect=output ` → mark for execution; verify output
- ` ```nodus-skip ` → skip
- All other fence types → skip (Python, JSON, etc.)

### Execution context

Each code block runs in a fresh Nodus VM. State is not shared between
blocks, even within the same document.

Rationale: documentation is read non-linearly. Users don't reliably
read top-to-bottom. A block that depends on state from a previous
block is brittle (reorder one, break the next). Forcing fresh-VM
isolation means each example must be self-contained — which is
also better doc practice.

For tutorials that legitimately need sequential state, the convention
is to put the multi-step example into ONE code block. Users see the
full flow in one place.

### Sandbox

The runtime phase sandboxes execution:

| Capability | Default behavior |
|---|---|
| Timeout | 10 seconds per block |
| Network | Disabled (HTTP calls fail; document with `nodus-no-run`) |
| Subprocess | Disabled (subprocess calls fail; document with `nodus-no-run`) |
| File system | Restricted to a temp directory per block |
| Memory | Standard VM limits |

For docs that genuinely need network or filesystem access, mark them
`nodus-no-run` (the static phase still verifies symbols).

### Timeout override

Long-running examples (workflow demonstrations) can specify a longer
timeout:

````markdown
```nodus-expect=output timeout=30s
// 25-second workflow simulation
```
````

The format is `timeout=<duration>` after the convention marker. Units:
`s`, `ms`. The 10-second default catches infinite loops in broken
examples without making the gate slow.

### Output matching

For `nodus-expect=output` blocks, the expected output is the next code
block after the test block:

````markdown
```nodus-expect=output
print("hello")
print("world")
```

Output:

```
hello
world
```
````

Matching rules:

- **Exact match for short outputs** (< 10 lines): byte-for-byte after
  trailing whitespace normalization
- **Line-by-line match for longer outputs**: each line compared after
  whitespace normalization; differences reported per line
- **Trailing newlines normalized**: a single trailing newline is
  optional in expected output
- **ANSI color codes stripped**: from both expected and actual before
  comparison

If a block doesn't have an "Output:" block immediately following, the
gate reports an error: `nodus-expect=output requires an "Output:"
block to follow`.

### Output

```
$ nodus_gate --runtime

Scanning 47 documents in docs/...
Found 89 runnable code blocks

Running blocks...
[1/89] ✓ docs/guide/getting-started.md:42 (12ms)
[2/89] ✓ docs/guide/getting-started.md:58 (5ms)
...
[45/89] ✗ docs/guide/error-handling.md:127 (8ms)
  Block expected output:
    Caught: division by zero
  Actual output:
    inf
  Hint: v4.0 returns IEEE 754 infinity for float division by zero.
  Update the example for v4.0 behavior.
[46/89] ✓ ...

Summary: 1 failure across 89 blocks (88 passed)
```

---

## Closed-issues phase (`--closed-issues`)

### CHANGELOG parsing

The gate reads `CHANGELOG.md` and extracts issue references from the
`[Unreleased]` section (during pre-release verification) or the current
release section (during post-release verification).

Issue references are recognized patterns:

- `#75` (issue number)
- `closes #75`
- `(#75)`
- `BUG-V31E-01 (#75)`

For each referenced issue, the gate locates the corresponding test and
runs it against the installed wheel.

### Test location

Two conventions are supported:

**Convention 1: file-per-issue naming**

```
tests/closed_issues/issue_75.py
tests/closed_issues/issue_76.py
tests/closed_issues/issue_82.py
```

The gate looks for `tests/closed_issues/issue_<number>.py` for each
issue number in the CHANGELOG. If found, run it. If missing, fail with
a clear message.

**Convention 2: marker in existing test files**

Tests in any location can claim to close specific issues via a marker
comment:

```python
# tests/test_parser.py

# closes: #75
def test_uppercase_integer_suffix_parse_error():
    """Verify 1I produces a parse error per BUG-V31E-01."""
    ...

# closes: #76
def test_math_log_two_arg_correct():
    """Verify math.log(value, base) returns log_base(value) per BUG-V31E-02."""
    ...
```

The gate scans all test files for `# closes: #N` markers and matches
them to CHANGELOG references.

**Both conventions are accepted.** The gate accepts whichever finds
the test.

### Wheel-based execution

The gate runs closed-issue tests against the INSTALLED wheel, not the
development source. This catches packaging gaps like BUG-E12 (v3.0.1)
where the fix was committed but didn't ship.

The procedure:

1. Build a wheel from the current source: `python -m build`
2. Create a fresh virtualenv (or reuse from cache; see below)
3. Install the wheel: `pip install dist/*.whl`
4. Run the closed-issue tests against that environment
5. Report pass/fail

The fresh-virtualenv approach is what catches packaging issues —
imports happen against the installed package, not the source tree.

### Caching the wheel environment

Building and installing a wheel takes ~30 seconds. For iterative
development, the gate caches the wheel environment based on git
status:

- Cache key: git tree hash + uncommitted-changes hash
- Cache location: `.nodusgate-cache/wheels/<hash>/`
- Cache hit: skip rebuild; run tests against existing environment
- Cache miss: rebuild, install, run

`--no-cache` forces rebuild regardless of cache state. Useful in CI
where cache state may be unreliable.

### Output

```
$ nodus_gate --closed-issues

Parsing CHANGELOG.md...
Found 6 issue references in [Unreleased] section: #75, #76, #77, #78, #79, #82

Locating tests...
✓ #75 -> tests/closed_issues/issue_75.py
✓ #76 -> tests/closed_issues/issue_76.py
✗ #77 -> no test found (looked for tests/closed_issues/issue_77.py
         and # closes: #77 markers)
✓ #78 -> tests/test_err_records.py (marker)
✓ #79 -> tests/closed_issues/issue_79.py
✓ #82 -> tests/closed_issues/issue_82.py

Building wheel... (cached, skipping rebuild)
Running tests against installed wheel...

[1/5] ✓ tests/closed_issues/issue_75.py (240ms)
[2/5] ✓ tests/closed_issues/issue_76.py (180ms)
[3/5] ✓ tests/test_err_records.py::test_stdlib_err_has_location (320ms)
[4/5] ✗ tests/closed_issues/issue_79.py (190ms)
       Cyclic workflow detection: expected err record with category
       'cyclic_workflow', got map with error string.
[5/5] ✓ tests/closed_issues/issue_82.py (1240ms)

Summary: 1 missing test, 1 test failure, 4 verified
```

---

## CLI specification

### Command and flags

```
nodus_gate [phases] [options]
```

Phase selection (one or more):

| Flag | Behavior |
|---|---|
| `--static` | Run static phase only |
| `--runtime` | Run runtime phase only |
| `--closed-issues` | Run closed-issues phase only |
| `--all` | Run all three phases |

If no phase flag is specified, the gate prints usage and exits without
running any phase (prevents accidental no-op runs).

Options:

| Flag | Default | Description |
|---|---|---|
| `--include-design` | off | Include `docs/design/` in scanned documents |
| `--no-cache` | off | Skip wheel cache for closed-issues phase |
| `--verbose` | off | Show every check, not just failures |
| `--quiet` | off | Show only summary line |
| `--format <fmt>` | auto | Output format: pretty, plain, json |
| `--strict` | off | Treat warnings as failures |
| `--allowlist <path>` | `.nodusgate-allow` | Path to allowlist file |

### Allowlist file

The allowlist file (`.nodusgate-allow` by default) suppresses specific
findings:

```
# .nodusgate-allow

# Suppress missing-symbol warnings for these (intentional doc references
# to future features)
symbol:strings.template
symbol:nodus_gate.coverage_report

# Suppress specific runtime block failures (e.g., examples that depend
# on time-of-day)
block:docs/guide/getting-started.md:42
```

The allowlist is checked in. Reviewers see what's been suppressed and
can challenge stale entries.

### Exit codes

| Exit code | Meaning |
|---|---|
| 0 | All checks passed (or only allowlisted findings) |
| 1 | One or more checks failed |
| 2 | Gate configuration error (invalid flags, missing required files) |
| 3 | Internal error in the gate itself |

### Output format auto-detection

If `--format` is not specified, the format is auto-selected:

- **pretty** if stdout is a TTY (interactive use)
- **plain** if stdout is not a TTY (CI logs)

The `json` format is used by tooling that consumes gate results
programmatically (CI dashboards, PR-comment bots).

---

## Implementation outline

### Implementation substrate

The gate is a Python script in `tools/nodus_gate/`. Invocation:

```bash
python -m tools.nodus_gate.cli --static
python -m tools.nodus_gate.cli --all
```

Aliased via `nodus_gate` shell wrapper.

### Why Python, not Nodus

The gate is bootstrap-style infrastructure that runs BEFORE the wheel
is built. It can't depend on the wheel; therefore it can't be written
in Nodus (since Nodus needs the wheel to run).

This is the chicken-and-egg constraint: if the gate were written in
Nodus, a broken gate would prevent running the gate, which would
prevent diagnosing the breakage.

Python is the practical choice: available in any development
environment, mature markdown parsing libraries, runs without requiring
the artifact under test.

### Module structure

```
tools/nodus_gate/
    __init__.py
    cli.py                    # entry point and flag parsing
    static_phase.py           # symbol extraction and verification
    runtime_phase.py          # code block execution and output matching
    closed_issues_phase.py    # CHANGELOG parsing and wheel-based testing
    sandbox.py                # execution sandbox for runtime phase
    wheel_cache.py            # wheel environment caching
    markdown_parser.py        # markdown block extraction
    output.py                 # formatted output (pretty/plain/json)
```

### Dependencies

- `mistune` or `markdown-it-py` for markdown parsing
- `build` for wheel construction
- Standard library: `subprocess`, `pathlib`, `json`, `re`

Dev-only dependencies; not part of the `nodus-lang` wheel.

### Test surface (gate meta-tests)

The gate itself needs tests to verify it correctly identifies
failures. Phase 3B includes:

- Static phase: known-missing-symbol test docs → gate reports failure
- Static phase: all-symbols-present docs → gate reports success
- Runtime phase: blocks that error → gate reports failure
- Runtime phase: blocks with wrong expected output → gate reports failure
- Runtime phase: blocks with correct expected output → gate reports
  success
- Closed-issues phase: missing test for issue → gate reports failure
- Closed-issues phase: test that fails → gate reports failure
- Closed-issues phase: test that passes → gate reports success
- Cache: source change invalidates cache; no change reuses cache
- Allowlist: suppressed findings don't fail the gate
- CLI: each flag combination produces expected behavior

The gate's meta-tests live in `tests/test_gate/`.

---

## Open implementation questions for Phase 3B

1. **Markdown parser choice.** `mistune` is fast and well-maintained;
   `markdown-it-py` is more spec-compliant. Tentative: start with
   `mistune`; switch if compliance issues surface.

2. **Symbol extractor sophistication.** Initial implementation uses
   regex-based patterns. May surface false positives or miss valid
   symbols. Tentative: ship with simple patterns; iterate based on
   real-world feedback in Phase 3B and beyond.

3. **Sandbox implementation.** Disabling network and subprocess in
   the Nodus VM during runtime-phase execution requires sandbox
   support that doesn't fully exist in v3.x. Tentative: use process-
   level isolation (run the example in a subprocess with restricted
   permissions) initially; in-process sandbox in v4.x.

4. **Wheel cache invalidation precision.** Git tree hash is coarse —
   any source change invalidates cache, even changes that don't affect
   the wheel. More precise tracking is possible but complex. Tentative:
   coarse invalidation initially; optimize if cache misses become a
   bottleneck.

5. **Output matching for non-deterministic outputs.** Some examples
   print timestamps, UUIDs, or other variable values. Tentative: gate
   supports a `nondeterministic` annotation that lets the expected
   output include placeholders like `<TIMESTAMP>` that match any value.

6. **Parallel phase execution.** Static and runtime can run in
   parallel; closed-issues requires the wheel to be built first.
   Tentative: parallelize static + runtime; gate closed-issues on
   wheel availability.

---

## Integration with playbooks

The gate is integrated into both playbooks per Decision 15:

### PLAYBOOK_PATCH_MINOR.md Stage 3

Mandatory pre-release step:

1. Run `nodus_gate --static`
2. Run `nodus_gate --runtime`
3. Run `nodus_gate --closed-issues`
4. All must pass before proceeding to PyPI upload

### PLAYBOOK_MAJOR.md Phase 4 (documentation sweep)

Mandatory phase exit criterion:

- Run `nodus_gate --all`
- Reconcile any failures
- Re-run `nodus_gate --all`; all pass

Major releases run the full gate including `--include-design` if
applicable. This catches drift between design docs and shipped
implementation.

### PLAYBOOK_MAJOR.md Phase 5 (release)

The Phase 5 release sequence lists `nodus_gate --all` as the mandatory
first step (per V4_0_PLAN.md Phase 5 amendments). This doc formalizes
what that step does.

---

## Migration impact

The doc-vs-code gate is new in v4.0. No migration impact — there was
no gate in v3.x.

For existing v3.x code blocks in docs, the one-time migration is:

1. Run `nodus_gate --static` on v3.x docs to find existing missing-
   symbol drift. Fix or allowlist.
2. Run `nodus_gate --runtime` to find code blocks that don't run
   cleanly. Add `nodus-no-run` annotations as needed.
3. Run `nodus_gate --closed-issues` to find missing closed-issue tests.
   Add tests for any issues already in the CHANGELOG.

After the gate is integrated into the playbooks, drift is prevented at
the source.

---

## Capability surface ceiling

The gate is focused on three failure modes (missing symbols, output
drift, patch closure). It does NOT include:

- **Spell checking or grammar checking.** Standard tooling (`vale`,
  `aspell`) handles prose quality.
- **Style enforcement.** Linting docs for formatting consistency is out
  of scope.
- **Link checking.** `markdown-link-check` or similar handles this.
- **Coverage of documented API.** The gate verifies symbols exist; it
  doesn't verify the documented API is comprehensive.
- **Multi-language doc verification.** All Nodus docs are English in
  v4.0; localization is out of scope.

---

## Cross-references

- `docs/design/v4/00-phase-0-decisions.md` Decision 15 (doc-vs-code
  gate)
- `docs/governance/PLAYBOOK_PATCH_MINOR.md` (Stage 3 integration)
- `docs/governance/PLAYBOOK_MAJOR.md` (Phase 4 and Phase 5 integration)
- `docs/governance/V4_0_PLAN.md` (Phase 5 release sequence)
- `docs/design/v4/07-test-framework-api.md` (test framework; closed-
  issues phase uses the test framework or pytest depending on file format)
- `docs/design/v4/13-err-record-location-fields.md` (sibling; gate
  findings use err record location fields)
- `docs/governance/TECH_DEBT.md` (Phase 3B open questions appended)

---

## Phase 3B implementation handoff

When Phase 3B begins (gate implementation), the following artifacts
are ready:

1. This design doc (`12-doc-vs-code-gate.md`)
2. Decision 15 (Phase 0)
3. Six open implementation questions
4. Substrate locked: Python script in `tools/nodus_gate/`
5. Dependencies: `mistune` or `markdown-it-py` + `build`
6. Test surface enumeration

Estimated implementation effort: 3-4 days focused work. The markdown
parsing and CHANGELOG extraction are straightforward; the runtime
sandbox and wheel cache are the more complex pieces.

The gate is mandatory pre-release infrastructure. v4.0 cannot ship
without it (per Decision 15 and V4_0_PLAN.md Phase 5 step 1). Phase
3C is the natural home for gate implementation — after Phase 3A
(breaking changes) settle and the stdlib (Phase 3B) is mostly
complete.

---

**Phase 1 doc 12-doc-vs-code-gate.md: COMPLETE.**

**Phase 1: COMPLETE. All 13 design docs locked.**
