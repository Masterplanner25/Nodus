# Nodus v4.0 — Design Doc 15: Cyclic Workflow Err Record

**Phase:** 1 (design docs)
**Status:** Locked
**Implements:** BUG-V31E-05 (#79), V4_0_PLAN.md Tier 1 breaking change (Phase 3A item)
**Date:** 2026-05-27
**Maintainer:** Shawn Knight (Masterplanner25)

---

## Problem statement

BUG-V31E-05 (issue #79): when `run_workflow` is called on a workflow
with a dependency cycle, the function returns a plain map with an
`"error"` string key and the script exits with code 0. This is the
worst of both possible behaviors:

- The result is not an err record (so `type(result) == "error"`
  doesn't catch it — the standard Nodus error pattern is broken)
- The exit code is 0 (so CI/shell scripts can't detect the failure
  via standard exit-code checking)

The original v3.0.0 fix (closing BUG-050) addressed silent
exit-zero-with-no-output, which was worse. The v3.0.0 fix produced
an error message but did not deliver the Nodus error contract.

v4.0 fixes this properly: cyclic workflows return an err record with
the standard shape, and the CLI propagates that to a non-zero exit
code via the existing error-handling plumbing.

This doc was added to Phase 1 retroactively (on 2026-05-27) when the
gap was identified during Phase 3 planning. Phase 1 is now 15 docs
total.

---

## What V4_0_PLAN.md already settled

From the Tier 1 breaking change list:

- Cyclic workflow returns err record + non-zero exit

From BUG-V31E-05 (#79):

- Current behavior: returns map with `"error"` key, exits 0
- Expected behavior: returns err record with `kind: "workflow_error"`
  OR exits non-zero (or both)

This doc resolves:

- Exact err record shape (kind, payload structure)
- CLI exit code propagation mechanism
- Other workflow error category scoping (just `cyclic_workflow` in
  v4.0; others reserved)
- Multi-cycle reporting
- Migration story
- Bytecode impact (none)

---

## Bytecode impact

**No new opcodes required. `BYTECODE_VERSION` stays at 4.**

The workflow runner is implemented Python-side. The change is in the
runner's cycle-detection logic: when a cycle is found, construct an
err record instead of a plain map and return it. The CALL_BUILTIN
opcode wrapper from `13-err-record-location-fields.md` automatically
adds `path`, `line`, `column`, `stack`, and `origin: "stdlib"` to the
returned record.

CLI exit-code propagation uses existing infrastructure: if a script's
top-level execution returns an err record without it being caught,
the CLI exits non-zero. This already works for VM-thrown errors;
making cyclic workflows return an err record means the existing exit-
code path handles them correctly without new code.

The frozen-bytecode contract from v1.0 is preserved.

---

## Err record shape

When `run_workflow(cyclic_workflow)` is called on a workflow with a
dependency cycle:

```nodus
err {
    kind: "workflow_error",
    message: "Dependency cycle detected: A -> B -> A",
    path: ...,         // from CALL_BUILTIN wrapping (caller's file)
    line: ...,         // caller's line
    column: ...,       // caller's column
    stack: ...,        // call stack
    origin: "stdlib",
    payload: {
        category: "cyclic_workflow",
        cycle: ["A", "B"],
        workflow_name: "my_workflow"
    }
}
```

### Field semantics

**`kind: "workflow_error"`** — new kind in v4.0. Distinguishes
workflow-related errors from other categories. Registered in
`docs/policy/error-surfaces.md` (Phase 4 update).

**`message`** — Human-readable description with the cycle path
embedded. Format: `"Dependency cycle detected: <step1> -> <step2> ->
... -> <step1>"`. The first step name appears at both ends to show
the cycle visually.

**`payload.category: "cyclic_workflow"`** — Distinguishes this
specific workflow error from other potential workflow errors (see
Other Categories below).

**`payload.cycle`** — List of step names in cycle order. The list
starts at one step in the cycle and walks around it (without
repeating the start at the end; the visual repetition is only in
the message). For the cycle `A -> B -> A`, the list is `["A", "B"]`.

**`payload.workflow_name`** — The name of the workflow as declared
in source (or `"<unnamed>"` if anonymous). Useful when a script
contains multiple workflows and only some have cycles.

### What's NOT in the payload

- **Source positions for each step.** The step names are sufficient;
  users look up the step definitions in their source. Including line
  numbers would bloat the payload for marginal benefit.
- **All cycles when multiple exist.** Only the first detected cycle
  is reported (see Multi-cycle handling below).
- **Suggested fixes.** "Remove this dependency" suggestions are out
  of scope; the user sees the cycle and resolves it.

---

## CLI exit code propagation

When `nodus workflow run cyclic.nd` is invoked on a script containing
a cyclic workflow:

1. The script executes; `run_workflow(cyclic)` returns an err record
2. The err record propagates as the script's result
3. The CLI sees an err record as the top-level result and exits
   with code 1
4. Stderr contains the formatted error: kind, message, and the cycle
   payload
5. Stdout is empty (no successful result to print)

This is the same exit-code mechanism that VM-thrown errors and other
stdlib err records use. No new CLI logic is required; the change is
that `run_workflow` now produces an err record (which the existing
plumbing already handles).

### User-handled case

If the script catches the err explicitly:

```nodus
let result = run_workflow(cyclic_workflow)
if type(result) == "error" {
    print("Workflow failed: " + result.message)
    exit(0)   // user chose to exit 0 despite the failure
}
```

The CLI exits with whatever the script returns. The user has
explicit control. Default (uncaught err) exits 1; explicit handling
can exit any code.

---

## Other workflow error categories

`kind: "workflow_error"` covers two implemented categories and two
reserved categories:

| Category | What it covers | Status in v4.0 |
|---|---|---|
| `"cyclic_workflow"` | Dependency cycle in workflow graph | **Implemented** (this doc) |
| `"missing_tasks"` | Tasks stuck with unresolvable dependencies (Python API only) | **Implemented** (Phase 3A amendment) |
| `"step_failed"` | Step raised err during execution | Reserved; currently handled differently |
| `"max_depth_exceeded"` | Workflow nesting too deep | Reserved; may not exist yet |

### `missing_tasks` category

Implemented during Phase 3A when the `if pending:` fallback path was
converted from a plain dict to an err record. This category fires
when the task graph scheduler completes but tasks remain pending
because their declared dependencies were never added to the graph.

**Reachability:** Not reachable via Nodus workflow syntax — the
parser validates all `after` dependency names at compile time and
raises `LangSyntaxError: Unknown workflow dependency: <name>` for any
reference to an undefined step. `missing_tasks` is reachable only
via the Python `task_graph` embedding API when a `TaskNode` lists a
dependency that is absent from the `TaskGraph.tasks` list.

**Payload shape:**

```python
{
    "category": "missing_tasks",
    "tasks": ["step_name_1", "step_name_2"],  # list of stuck step names
    "workflow_name": "my_workflow"             # or None
}
```

`tasks` lists the step names (resolved via `task_to_step` metadata;
falls back to raw task IDs) of all tasks that were stuck. Unlike
`cyclic_workflow`, there is no `cycle` field — the stuck tasks are
the artifact, not an ordered cycle path.

Future v4.x or v5.x design docs may address `step_failed` and
`max_depth_exceeded` if real demand surfaces.

---

## Multi-cycle handling

A workflow may have multiple independent cycles. For example:

```nodus
workflow has_two_cycles {
    step A after B { return 1 }
    step B after A { return 2 }   // cycle 1: A -> B -> A

    step C after D { return 3 }
    step D after C { return 4 }   // cycle 2: C -> D -> C

    step E after A { return 5 }   // also has cycle via A
}
```

Only the first detected cycle is reported. Once a cycle is
detected, the workflow cannot run (further validation is moot). The
user resolves the first cycle, re-runs, and gets the next cycle if
one remains.

This is consistent with how compilers report syntax errors: usually
the first error is the most useful; subsequent errors may be
cascading consequences of the first.

The `payload.cycle` field shows the first cycle. The user gets a
clear path: identify cycle 1, fix it, re-run, see cycle 2 (if any),
fix it, repeat until no cycles remain.

### Detection order

The order in which cycles are detected depends on the cycle-detection
algorithm. Typical depth-first-search-based detection finds the
cycle starting from the first step encountered. This is the natural
ordering and doesn't need additional specification.

For deterministic output across runs, step names within a cycle are
listed in the order encountered during detection (not alphabetically
or otherwise canonicalized).

---

## Migration impact

### Breaking change

Code that detected cycles by checking the result map breaks:

```nodus
// v3.x — relies on the map-with-error-key pattern
let result = run_workflow(cyclic)
if type(result) == "map" and result["error"] != nil {
    print("Cycle detected: " + result["error"])
}

// v4.0 — uses standard err record pattern
let result = run_workflow(cyclic)
if type(result) == "error" and result.payload.category == "cyclic_workflow" {
    print("Cycle detected: " + result.message)
    print("Cycle path: " + str(result.payload.cycle))
}
```

### Migration patterns

| v3.x pattern | v4.0 pattern |
|---|---|
| `type(result) == "map" and result["error"] != nil` | `type(result) == "error" and result.payload.category == "cyclic_workflow"` |
| `result["error"]` (the error message string) | `result.message` |
| CI scripts checking `nodus workflow run` exit code | Unchanged behavior; exit code 1 now means workflow failed (was 0 in v3.x for cyclic workflows) |

### CI script impact

CI scripts that ran `nodus workflow run` and checked exit codes are
affected:

```bash
# v3.x — false success for cyclic workflows
nodus workflow run my_workflow.nd
if [ $? -eq 0 ]; then
    echo "Workflow succeeded"   # WRONG — also matches cyclic failure
fi

# v4.0 — correct: exit 1 for failures (including cycles)
nodus workflow run my_workflow.nd
if [ $? -eq 0 ]; then
    echo "Workflow succeeded"   # Now correctly excludes cycle failures
fi
```

This is a positive breaking change — code that previously had a
false-positive success indicator now works correctly. Users who
relied on the exit-0 behavior for some workaround migrate to
explicit catch + `exit(0)` if they really want that behavior.

### Documentation

`docs/migration/v3-to-v4.md` (Phase 4) includes a section on the
cyclic workflow err record change with the migration patterns above.

`docs/policy/error-surfaces.md` (Phase 4) gets the new
`workflow_error` kind and `cyclic_workflow` category documented.

---

## Implementation outline

### Workflow runner change

The Python-side workflow runner detects cycles and currently returns
a map with `"error"` key. The change:

```python
# Before (v3.x or current state)
def run_workflow(workflow):
    cycle = detect_cycle(workflow.dependencies)
    if cycle:
        return {
            "error": f"Dependency cycle: {' -> '.join(cycle)}"
        }
    # ... normal execution

# After (v4.0)
def run_workflow(workflow):
    cycle = detect_cycle(workflow.dependencies)
    if cycle:
        # Repeat first step at end for visual cycle path
        cycle_path = " -> ".join(cycle + [cycle[0]])
        message = f"Dependency cycle detected: {cycle_path}"

        # Construct err record (CALL_BUILTIN wrapper adds location fields)
        return err_record(
            kind="workflow_error",
            message=message,
            payload={
                "category": "cyclic_workflow",
                "cycle": list(cycle),
                "workflow_name": workflow.name or "<unnamed>"
            }
        )
    # ... normal execution
```

### Cycle detection

Existing v3.x cycle detection logic is reused (no algorithmic
change). The change is in what happens when a cycle is found.

### Test surface (Phase 3A)

- Cyclic workflow returns err record (not map)
- `err.kind` is `"workflow_error"`
- `err.payload.category` is `"cyclic_workflow"`
- `err.payload.cycle` is the list of step names
- `err.payload.workflow_name` is the workflow's declared name
- `err.path`, `err.line`, `err.column`, `err.stack` are populated
  (from CALL_BUILTIN wrapping)
- `err.origin` is `"stdlib"`
- Multiple cycles in one workflow: first detected cycle is reported
- CLI: `nodus workflow run cyclic.nd` exits with code 1
- CLI: stderr contains formatted error
- CLI: stdout is empty
- User-handled case: script catches err and exits 0
- Migration: existing v3.x check pattern (`type(result) == "map"`)
  no longer matches; test confirms migration needed
- Documentation examples using the new pattern verified by
  `nodus_gate --runtime`

---

## Open implementation questions for Phase 3B

1. **Cycle detection algorithm.** Verify the current Python-side
   detection produces deterministic step ordering within a cycle.
   If non-deterministic, fix to ensure same output across runs.

2. **Self-cycle detection.** ✅ RESOLVED. `step a after a` passes the
   parser (the step name exists; the parser validates name presence,
   not cycle absence). The DFS detector catches it at runtime:
   `cycle = ["a"]`, message `"Dependency cycle detected: a -> a"`.
   Covered by `test_self_cycle_detected` and `test_self_cycle_message_format`.

3. **`workflow_name` for anonymous workflows.** What goes in the
   `workflow_name` field for workflows without explicit names?
   Tentative: `"<unnamed>"` string. Verify v3.x has a way to
   identify the workflow (file path? line number?) and include that.

4. **CALL_BUILTIN wrapping verification.** Ensure the err record
   returned by `run_workflow` properly receives location fields from
   the CALL_BUILTIN wrapper. This depends on
   `13-err-record-location-fields.md` being implemented first.

5. **Test for multi-cycle workflows.** Construct a workflow with
   two independent cycles; verify first cycle is reported, second
   is not.

6. **Migration audit.** Check the v3.x test suite and docs for any
   examples using the map-with-error-key pattern. Update to the
   err record pattern; ensure `nodus_gate --runtime` catches any
   examples in docs.

---

## Capability surface ceiling

Per the capabilities-not-orchestration principle, NOT included:

- **Cycle visualization or rendering.** Just the list in
  `payload.cycle`. Tools that want to render cycles (Mermaid
  diagrams, etc.) consume the list and render externally.
- **Auto-resolution suggestions.** "Remove this edge to break the
  cycle" suggestions. Out of scope; the user sees the cycle and
  makes architectural decisions.
- **Other workflow error categories.** `"missing_step"`,
  `"step_failed"`, `"max_depth_exceeded"` are reserved but not
  designed in v4.0.
- **Cycle-detection-as-a-tool.** A standalone `cycle_detect()`
  function separate from `run_workflow`. Not in v4.0; users who
  need to check before running do it themselves.

### Reconsideration triggers

Scope expands if:

- Real user issues request the other workflow error categories
- Cyclic workflow scenarios surface that the simple cycle list
  doesn't capture well (e.g., conditional cycles based on data)
- The err record shape proves insufficient for tooling integration

---

## MCP and A2A consumer validation

`nodus-mcp` and `nodus-a2a` don't directly use workflow execution
(workflows are a Nodus runtime feature, not a protocol feature).
However, both libraries' error handling pattern uses err records
with category-based dispatch:

```nodus
let result = some_operation()
if type(result) == "error" {
    if result.payload.category == "cyclic_workflow" { handle_cycle() }
    else if result.payload.category == "..." { handle_other() }
}
```

The cyclic workflow err record fits this pattern naturally. No
library-specific consumer validation is needed; the err record shape
is consistent with all other v4.0 err records.

---

## Cross-references

- BUG-V31E-05 (#79) — original bug surfacing this
- `docs/governance/V4_0_PLAN.md` (Tier 1 breaking change list)
- `docs/design/v4/13-err-record-location-fields.md` (sibling; the
  CALL_BUILTIN wrapping adds location fields to this err record
  automatically)
- `docs/language/LANGUAGE_SPEC.md` (Phase 4 update: err record
  section)
- `docs/policy/error-surfaces.md` (Phase 4 update: workflow_error
  kind and cyclic_workflow category documented; other categories
  marked reserved)
- `docs/migration/v3-to-v4.md` (Phase 4 deliverable: cyclic workflow
  migration patterns)
- `docs/governance/TECH_DEBT.md` (Phase 3B open questions appended)

---

## Phase 3A implementation handoff

When Phase 3A implements this:

1. Update workflow runner to construct err record on cycle detection
2. Verify err record receives location fields from CALL_BUILTIN
   wrapping (depends on `13-err-record-location-fields.md`
   implementation order)
3. Update CHANGELOG.md noting the breaking change (cycle detection
   now returns err record, exit code 1)
4. Add tests for all err record fields and CLI exit code behavior
5. Audit existing v3.x tests for map-with-error-key pattern; update
   to err record pattern
6. Update LANGUAGE_SPEC.md workflow section to describe the err
   record

Estimated effort: half a day. The implementation is small; the test
updates and migration audit are the time sinks.

This depends on `13-err-record-location-fields.md` being implemented
first (so the location fields are present in the err record
returned by the workflow runner). Implementation order in Phase 3A:
doc 13 → doc 15.

---

**Phase 1 doc 15-cyclic-workflow-err-record.md: COMPLETE.**

**Phase 1 now: 15 of 15 design docs locked.**
