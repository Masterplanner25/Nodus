# Nodus v4.0 — Design Doc 08: Test Framework Coverage

**Phase:** 1 (design docs)
**Status:** Locked
**Implements:** Decision 4 (test framework comprehensive scope) coverage portion
**Companion to:** `07-test-framework-api.md`
**Date:** 2026-05-26
**Maintainer:** Shawn Knight (Masterplanner25)

---

## Problem statement

v4.0 ships source-line coverage as part of the test framework.
Decision 4 (Phase 0) locked the scope: source-line coverage in v4.0,
bytecode-level coverage deferred to v4.x.

This doc specifies the coverage data collection mechanism, attribution
to source files and lines, report generation, CLI integration, and
exclusion conventions. It extends `07-test-framework-api.md` with
coverage-specific functionality.

Coverage instrumentation is the most complex piece of the test
framework (per Decision 4's note). Designing it as a separate doc
keeps the test API doc focused while giving coverage the space it
needs.

---

## What Phase 0 already settled

From Decision 4:

- Source-line coverage in v4.0
- Bytecode-level coverage deferred to v4.x
- Coverage is part of the comprehensive test framework scope

From `07-test-framework-api.md`:

- `nodus test --coverage` flag enables coverage collection
- Coverage results integrate with the test runner's output

This doc resolves:

- Coverage data collection mechanism (event-based)
- Source-line attribution
- Multi-file coverage tracking
- Coverage report formats (live progress, summary, persistent reports)
- Coverage data persistence (coverage.json, coverage.html)
- Exclusion conventions
- CLI integration
- Bytecode impact (none — uses existing source-position infrastructure)

---

## Bytecode impact

**No new opcodes required. `BYTECODE_VERSION` stays at 4.**

Coverage collection uses Nodus's existing source-position event
infrastructure (the same mechanism used by `--trace-errors` and the
debugger). When `--coverage` is enabled, the VM emits a "line
executed" event whenever it crosses a new source line. A coverage
collector subscribes to these events and aggregates per-line hit
counts.

This means:

- No bytecode modification
- No two-mode compilation (the same `.ndbc` runs with or without
  coverage)
- Coverage collection adds runtime cost only when enabled
- Coverage collection is fully orthogonal to test execution

The frozen-bytecode contract from v1.0 is preserved.

---

## Data collection mechanism

### Event-based line tracking

The VM emits a `line_executed` event whenever execution crosses to a
new source line. The event carries:

```
{
    path: string,        // source file path (absolute or repo-relative)
    line: int,           // source line number
    timestamp_us: int    // microseconds since process start
}
```

The coverage collector is a subscriber that aggregates these events
into per-file hit counts:

```
{
    "src/validator.nd": {
        12: 1,    // line 12 hit once
        13: 1,
        15: 3,    // hit three times (called from three different tests)
        // line 14 missing → not covered
        ...
    },
    "src/utils.nd": {
        ...
    }
}
```

### Subscription lifecycle

When the test runner is invoked with `--coverage`:

1. Runner activates the coverage collector before any tests run
2. Collector subscribes to the VM's line-execution event source
3. Each test runs normally; events accumulate
4. After all tests complete, collector finalizes the data
5. Reports are generated (live summary + persistent files)

### Per-test attribution

By default, coverage data is aggregated across all tests. This shows
which lines are exercised by the test suite as a whole.

Per-test attribution (which test exercises which lines) is more
expensive (separate hit count per (test, line) pair) and is OFF by
default. Enable via `--coverage-per-test`:

```bash
nodus test --coverage --coverage-per-test
```

Per-test attribution enables finer-grained analysis:

- Which test is the only one covering a specific line?
- Which tests can be removed without losing coverage?

Default is aggregate-only; per-test is opt-in.

---

## Source-line attribution

### Counted lines

The VM emits a `line_executed` event for lines that contain executable
code. The compiler annotates each line with whether it's executable:

| Line type | Counted? |
|---|---|
| Comments | No |
| Blank lines | No |
| Lines containing only `{` or `}` (block delimiters) | No |
| Lines containing only `;` (statement terminator) | No |
| Lines containing code (assignments, calls, expressions, declarations) | Yes |
| Lines containing only a function definition keyword (`fn name {`) | Yes (one hit when the function is defined) |

The compiler's source-position table records executable line numbers
per source file. The coverage collector uses this to compute coverage
percentage:

```
coverage_pct = covered_lines / total_executable_lines * 100
```

### Multi-line statements

Statements spanning multiple lines (function calls with many
arguments, multi-line expressions) are counted as covered when
execution reaches them. The attribution uses the first line of the
statement.

### Branch coverage

v4.0 ships source-line coverage only, not branch coverage. Lines with
multiple paths (`if`/`else`) are counted as covered when execution
reaches them, even if only one branch is taken.

Branch coverage is deferred to v4.x as additive.

---

## Multi-file coverage tracking

Coverage spans all source files exercised during the test run. The
data structure:

```json
{
    "files": {
        "src/validator.nd": {
            "executable_lines": [12, 13, 15, 16, 17, 18, 21, 22, 25],
            "covered_lines": {"12": 1, "13": 1, "15": 3, "16": 3, "21": 1, "22": 1},
            "uncovered_lines": [17, 18, 25],
            "coverage_pct": 66.67
        },
        "src/utils.nd": {
            "..."
        }
    },
    "summary": {
        "total_files": 2,
        "total_executable_lines": 47,
        "total_covered_lines": 32,
        "overall_coverage_pct": 68.09
    },
    "timestamp": "2026-05-26T14:30:00Z",
    "test_command": "nodus test --coverage tests/"
}
```

Test files (`*_test.nd`) are EXCLUDED from coverage by default. The
goal is to measure how much of the source code under test is
exercised, not whether the tests themselves run.

---

## Report generation

### Live progress

During test execution, the coverage collector shows current coverage
in the test output:

```
 RUN  validator_test.nd
  ✓ validates non-empty input (12ms)         [cov: 12/47 lines]
  ✓ validates: alice (3ms)                    [cov: 15/47 lines]
  ✓ validates: bob (3ms)                      [cov: 15/47 lines]
  ✗ validates: empty (5ms)                    [cov: 18/47 lines]

Coverage during run: 38.30% (18/47 lines)
```

### End-of-run summary

After all tests complete, a coverage summary is shown:

```
Coverage Summary:
  src/validator.nd     66.67% (6/9 lines)
  src/utils.nd         70.00% (14/20 lines)
  src/http_helper.nd   85.71% (12/14 lines)
  ───────────────────────────────────────
  Overall              72.13% (32/47 lines)

Uncovered lines:
  src/validator.nd:17, 18, 25
  src/utils.nd:8, 12, 19, 27, 31, 34
  src/http_helper.nd:11, 23
```

### Persistent reports

Two files are written to the working directory at the end of the test
run:

**`coverage.json`** — raw coverage data in the structure shown above.
Used by CI integrations, dashboards, and other tooling.

**`coverage.html`** — rendered HTML report. Each source file gets a
page showing the source code with covered lines highlighted green,
uncovered lines highlighted red. Click-through navigation between
files.

The HTML report is intentionally simple — basic HTML with inline CSS,
no JavaScript framework, no external dependencies. It can be opened
directly in a browser or hosted on a CI build artifact server.

Both files are written to `./coverage/` by default. The directory is
configurable via `--coverage-output <path>`.

### Output format compatibility

| Format | Coverage output |
|---|---|
| `pretty` (TTY) | Live progress with colors; end summary with file table |
| `plain` | Same content, no colors |
| `json` | Coverage events interleaved with test events as JSON Lines |
| `junit` | Coverage data in `<properties>` element; full data still in `coverage.json` |

---

## Exclusion conventions

### Per-line exclusion

Lines marked with `# coverage: skip` comments are excluded from
coverage tracking:

```nodus
fn validate(input) {
    if input == nil { return false }   # coverage: skip
    let result = process(input)
    return result
}
```

Excluded lines:

- Don't count toward `total_executable_lines`
- Don't appear in `uncovered_lines` lists
- Don't reduce coverage percentage

### Block exclusion

```nodus
fn risky_operation() {
    # coverage: skip-block-start
    let unstable_value = some_external_call()
    if unstable_value == nil {
        return error("external service down")
    }
    # coverage: skip-block-end
    return process_normally()
}
```

### Per-file exclusion

Files containing `# coverage: skip-file` at the top are excluded
entirely. Used for generated code, third-party files, or files where
coverage isn't meaningful.

### Default exclusions

The runner automatically excludes:

- Test files (`*_test.nd`)
- Files in `vendor/`, `node_modules/`, `.git/`, `.venv/`
- Files in the `tests/` directory by default

### Configuring exclusions via the CLI

```bash
nodus test --coverage --coverage-exclude "src/generated/**"
nodus test --coverage --coverage-include "src/**" --coverage-exclude "src/legacy/**"
```

---

## CLI integration

### Flags

| Flag | Default | Description |
|---|---|---|
| `--coverage` | off | Enable coverage collection |
| `--coverage-per-test` | off | Track per-test attribution (more expensive) |
| `--coverage-output <path>` | `./coverage/` | Output directory for reports |
| `--coverage-exclude <pattern>` | (none) | Exclude files matching pattern |
| `--coverage-include <pattern>` | `**/*.nd` | Include only files matching pattern |
| `--coverage-min <pct>` | 0 | Fail the run if coverage is below threshold |
| `--coverage-format <fmts>` | `json,html` | Comma-separated report formats |

### Threshold gating

`--coverage-min <pct>` fails the test run if overall coverage is below
the threshold. Used in CI to enforce coverage standards:

```bash
nodus test --coverage --coverage-min 80
# Exits 1 if coverage < 80%, even if all tests pass
```

### Report format selection

`--coverage-format` controls which persistent reports are written.
Comma-separated list of: `json`, `html`, `xml` (Cobertura format),
`lcov` (LCOV format).

Default writes both `json` and `html`. Pure CI environments might
prefer `--coverage-format json,xml` to skip HTML rendering.

---

## Implementation outline

### VM event subscription

```python
class CoverageCollector:
    def __init__(self):
        self.hits = defaultdict(lambda: defaultdict(int))  # path -> line -> count

    def on_line_executed(self, event):
        self.hits[event.path][event.line] += 1

# In the test runner
vm.event_bus.subscribe("line_executed", coverage_collector.on_line_executed)
```

When `--coverage` is not set, no subscription is made, and the event
source has zero overhead.

### Executable line detection

The compiler tracks which lines are executable when building the
source-position table. This metadata is part of the compiled module:

```python
class CompiledModule:
    executable_lines: dict[str, list[int]]  # path -> sorted list of line numbers
    excluded_lines: dict[str, set[int]]     # path -> set of skipped line numbers
```

### Report generation

After tests complete:

1. Collector finalizes the hits dictionary
2. Combines with executable_lines and excluded_lines from compiled modules
3. Computes per-file and overall percentages
4. Writes `coverage.json` (raw data)
5. Renders `coverage.html` (per-file HTML with source highlighting)
6. Optionally writes other formats per `--coverage-format`

HTML rendering uses a simple template engine (Python's
`string.Template` or similar). No external dependencies; the output
is static HTML with inline CSS.

### Performance

Per-event overhead matters — the VM can emit millions of events during
a large test run. The collector must use efficient data structures
(defaultdict with int counters) and avoid string copies (use integer
line numbers and interned path strings).

Tentative overhead target: <20% slowdown when `--coverage` is enabled
on a moderate-sized test suite (100 tests, 10K lines of source).

### Test surface (Phase 3B)

- Coverage data accurate for all counted line types
- Per-file coverage percentages correct
- Exclusion comments remove lines from counts
- Per-file and per-file-block exclusion work correctly
- Threshold flag gates exit code correctly
- All report formats generated without error
- Coverage events don't fire when `--coverage` is not set (zero
  overhead)
- HTML report opens in a browser and highlights covered/uncovered
  lines correctly
- JSON report structure matches the documented schema

---

## Open implementation questions for Phase 3B

1. **Event bus implementation.** Does Nodus's existing event
   infrastructure (`--trace-errors`, debugger) support efficient
   per-line events? Tentative: extend existing event bus; profile
   overhead before committing.

2. **Source-position table size.** Adding executable_lines and
   excluded_lines per file to compiled modules adds memory. Tentative:
   small overhead; verify with realistic test suites.

3. **HTML report size for large codebases.** A project with 100K
   lines of source would produce a large coverage.html. Tentative:
   single file for v4.0; split into per-file pages if size becomes a
   problem.

4. **Coverage data merging across test runs.** Some workflows run
   tests multiple times with different configurations and want
   combined coverage. Tentative: not in v4.0; users merge JSON files
   externally. Add `--coverage-merge` flag in v4.x if demand surfaces.

5. **Line attribution for nested function definitions.** Anonymous
   functions defined inside other functions span multiple lines.
   Tentative: count the `fn` keyword line as executable; nested
   function body lines counted separately.

6. **Skip-comment parsing performance.** Parsing comments during
   compilation adds time. Tentative: only parse coverage comments when
   the compiler is invoked with coverage support enabled; falls back
   to non-coverage mode for production compilation.

---

## Capability surface ceiling

Per Phase 0 scoping and capabilities-not-orchestration principle:

- **Branch coverage** — deferred to v4.x
- **Bytecode-level coverage** — deferred to v4.x per Decision 4
- **Mutation testing** — out of scope
- **Code complexity metrics** — out of scope; possibly `nodus-metrics`
- **Coverage diff between runs** — out of scope; users diff JSON files
- **Coverage badge generation** — out of scope; standard CI tooling
  handles this from JSON output
- **Integration with specific code review tools** — out of scope; CI
  tooling handles this from JSON

---

## Cross-references

- `docs/design/v4/00-phase-0-decisions.md` Decision 4 (test framework
  comprehensive scope, coverage source-line in v4.0)
- `docs/design/v4/07-test-framework-api.md` (companion; test framework
  API)
- `docs/design/v4/13-err-record-location-fields.md` (sibling;
  coverage collector uses source-position infrastructure)
- `docs/governance/LIBRARY_ECOSYSTEM.md` § Tier 2/3 (`nodus-metrics`
  and similar deferred libraries)
- `docs/governance/TECH_DEBT.md` (Phase 3B open questions appended)

---

**Phase 1 doc 08-test-framework-coverage.md: COMPLETE.**
