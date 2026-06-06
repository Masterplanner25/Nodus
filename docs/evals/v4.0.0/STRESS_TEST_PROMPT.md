# NODUS v4.0.0 — POST-PUBLISH STRESS-TEST USER EVALUATION
#
# Lineage: v2.0.0 original → v3.0.0 major-release variant →
# EVAL_STAGE4_TEMPLATE.md (generalized) → this v4.0.0 POST-PUBLISH instance.

# =====================================================================
# SECTION 0 — RELEASE PARAMETERS
# =====================================================================
#
#   TARGET VERSION      : v4.0.0
#   RELEASE TYPE        : major
#   PRIOR BASELINE      : v3.0.2  (eval score: not formally scored; last eval was v3.0.1)
#
#   INSTALL SOURCE      : POST-PUBLISH
#     Install command:  pip install nodus-lang==4.0.0
#     Confirm version:  nodus --version   →   must report "Nodus 4.0.0"
#     A version mismatch here invalidates the entire run. STOP if it occurs.
#
#   WORKING DIRECTORY   : C:\dev\Nodustestenvv4   (empty, non-git, local-only)
#   DELIVERABLE DIR     : docs/evals/v4.0.0/   (move the four files here at end)
#
# =====================================================================

You are an independent technical evaluator. You have no prior context on
the Nodus language. Pretend you are a senior engineer who saw the v4.0.0
release announcement and decided to spend a day evaluating whether to adopt
it for a real project.

You did NOT participate in building or releasing this version. You do not
trust the release notes — you verify them. Your job is to find the sharp
corners, not to confirm that the release is good.

---

## 1. INTEGRITY RULES  (read these first, they govern everything)

1. **Log everything, fix nothing.** You are evaluating, not patching. If you
   find a bug, you record it — you do not work around it silently and you do
   not edit Nodus's source. Workarounds you discover get logged AS workarounds,
   with the underlying defect filed.

2. **No claim without evidence.** Every statement in any report file must be
   traceable to an entry in `EVAL_LOG.md`. If it isn't in the log with a
   command, input, and actual output, it does not go in a report. No claim
   from memory, no claim from the release notes, no claim you "expect" to be
   true. Run it.

3. **Paste real output.** The log contains actual terminal output — exit codes,
   error text verbatim, the actual printed result — not your summary. Summaries
   go in the report; raw evidence goes in the log.

4. **Severity is calibrated, not softened.**
   - **CRITICAL** = broken in a way that blocks a user from real work.
   - **HIGH** = a documented feature does not behave as documented.
   - **MEDIUM** = works, but with a sharp corner a real user will hit.
   - **LOW** = minor friction, papercut.
   - **COSMETIC** = output/formatting/wording. File these too — polish signal.
   Do not round a HIGH down to a MEDIUM because the rest of the release is good.

5. **Stop-and-report when reality differs from this prompt.** If the install
   doesn't resolve to v4.0.0, if a file this prompt references doesn't exist,
   STOP, log the discrepancy, and report it.

6. **Version provenance is the first log entry.** Before any test, record:
   the install command, INSTALL SOURCE = POST-PUBLISH, the resolved version
   as Nodus itself reports it, and confirmation it matches v4.0.0.

---

## 2. SETUP

In `C:\dev\Nodustestenvv4` (already exists, empty):

1. Record: OS, shell, Python version.
2. A `.venv` may already exist. If so, verify it is fresh (no nodus-lang yet).
   If not, create one: `python -m venv .venv`
3. Activate it: `.venv\Scripts\activate`
4. Install from PyPI (NOT local): `pip install nodus-lang==4.0.0`
5. Confirm: `nodus --version` → must report `Nodus 4.0.0`. STOP if mismatch.
6. Create `EVAL_LOG.md`. Write the provenance block as entry #1.
7. Create a `scratch/` subdirectory for test scripts.

Do not read Nodus's source code to form your assessment. You may read the
PUBLIC docs (README, language reference, migration guide, CLI `--help`,
GitHub repo docs/) — because a real adopter reads those — but you evaluate
SHIPPED BEHAVIOR, not intentions in the source.

---

## 3. EVALUATION ARC  (work in order, log as you go)

### 3a. First contact

Install, version check, `--help` on every entry point, run hello-world,
run whatever the README's quick-start says. Does the advertised on-ramp
actually work, exactly as written, with no undocumented step? Log every
divergence between what the docs say and what happens.

Specifically:
- `nodus --help` — do all subcommands listed in docs actually appear?
- `nodus run scratch/hello.nd` where hello.nd prints a string literal
- `nodus fmt scratch/hello.nd` — does the formatter work?
- `nodus check scratch/hello.nd` — does the checker run?
- `python -c "from nodus import NodusRuntime; rt = NodusRuntime(timeout_ms=None, max_steps=None); print(rt.run_source('print(\"hello\")'))"`

### 3b. Language core

Exercise the type system, operators, control flow, functions, data structures,
error model. Include:

**Integer vs float type model** (key v4.0.0 design decision):
- `1i + 2i` → int result?
- `1.0 + 2.0` → float result?
- `1i + 2.0` → what type? What does the doc say?
- Integer overflow behavior? (`9999999999999999i * 9999999999999999i`)
- Does `len([1,2,3])` return `3i` (int)? Does the doc say so?
- Division: `5i / 2i` → truncated int or float? `5i / 2.0`?

**Maps vs Records** (critical v4.0.0 distinction — real users hit this):
- `{key: "val"}` → record → access with `r.key`, NOT `r["key"]`
- `{"key": "val"}` → map → access with `m["key"]`, NOT `m.key`
- Confirm "Field access is only supported on records" fires if you dot a map
- Confirm "Indexing is only supported on lists and maps" fires if you index a record
- `run_workflow()` and `run_goal()` — do they return maps (bracket notation)?

**Known language constraints** (verify each, log):
- `print("a", "b")` → should error (print is single-argument). Good error message?
- `x += 1` → should error (no `+=` operator). Good error message?
- Multiline list `[1,\n2]` → should error. Good error message?
- `fn` as identifier → should error (reserved keyword). Good error message?
- `await` keyword → should not exist. `await x` — what error?

**Type coercion contracts:**
- `"5" == 5` — what does this return? What does the doc say?
- `nil == false` — same
- `0i == false` — same
- `[] == false` — same

**Error model (err records):**
- Trigger a runtime error and inspect the result shape: does `err.kind`,
  `err.message`, `err.payload` exist as documented?
- `json.parse("{invalid}")` — is the error a Nodus `err` record or a leaked
  Python exception?
- Try/catch semantics — how are errors caught in Nodus? (Document what the
  docs say, then verify behavior matches.)

**Parser adversarial input:**
- Empty file, whitespace-only file, comment-only file
- Unclosed string, unclosed bracket
- Unicode in identifiers and strings (e.g., `let café = "hello"`)
- Mixed line endings (CRLF + LF in same file)
- 100-level nested parens `((((((…)))))`
- Reserved words as identifiers: `let fn = 1` — error quality?

### 3c. Standard library

For each std: module listed in the docs, call every documented function with
valid arguments (does it work?), wrong argument counts (error quality?), and
wrong types (error quality?).

**Priority modules — test every documented function:**

`std:json`:
- `json.parse` on valid JSON, malformed JSON, empty string, non-string input
- `json.stringify` on all value types including nil

`std:fs`:
- `fs.read` on existing file, non-existent file, directory
- `fs.write`, `fs.exists`, `fs.listdir` — basic ops
- Path traversal: `fs.read("../../etc/passwd")` — does the sandbox fire?
  Test both CLI mode and NodusRuntime embedded mode (enforcement can differ).

`std:http`:
- `http.get(url)` — confirm result is a **record** (dot notation: `result.status`,
  `result.body`, `result.ok`), not a map.
- `http.post` with body

`std:subprocess`:
- `subprocess.run(["echo", "hello"])` — confirm result is a **record**
  (`result.stdout`, `result.exit_code`), not a map.

`std:hash`:
- `hash.sha256("hello")` — IMPORTANT: returns a **record**, not a string.
  Must call `.to_hex()` to get the hex string. Verify this is documented.
  What happens if you print the record directly?

`std:tool`:
- `tool.register({name: "myapp.greet", ...})` — dotted names required.
  Try a non-dotted name: `tool.register({name: "greet", ...})`. Does the
  error message say "must use dotted namespacing"?

`std:strings`, `std:math`, `std:env`, `std:encoding`, `std:secrets`,
`std:time` — at minimum: one happy-path call per documented function, one
wrong-type call.

### 3d. SURFACE TO PROBE  (v4.0.0 specific — see Section 4)

This is where v4.0.0-specific features get stress-tested.

### 3e. Migration audit  (v3.0.2 → v4.0.0)

Find or write a v3.0.2-style program that uses:
- Integer literals as plain `1`, `2`, `3` (not `1i`)
- Any syntax that changed between v3 and v4

Run it unmodified on v4.0.0. Log exactly what breaks. Then follow the
migration guide (if one exists in the docs) step-by-step and confirm it
produces working code. A migration guide that doesn't produce working
code is a HIGH finding.

If no migration guide exists for v3→v4, that is itself a HIGH finding —
log it.

### 3f. Build something real

Build ONE of the following using only PyPI-installed nodus-lang:
- A log parser that reads a file, extracts patterns, writes a summary
- A small JSON-to-JSON transformer (read JSON, restructure, write JSON)
- A multi-step workflow that reads a directory, processes files, produces a report

Constraints:
- Use idiomatic v4.0.0 Nodus (per the docs)
- 50–150 lines
- Use at least 3 `std:` modules
- Use the module system (split into 2+ .nd files)
- Save under `scratch/real_task/`

Log: how long, where you got stuck, what docs you had to re-read, what
would have made the experience smoother.

---

## 4. SURFACE TO PROBE  (v4.0.0 change surface)

### 4.1 — Coroutines and channels (new in v4.0.0)

**Claims to verify:**
- `channel()`, `send(ch, val)`, `recv(ch)`, `close(ch)` are BUILT-IN functions,
  not a stdlib module. `import "std:channel"` should fail with "Import not found."
- `coroutine(fn() {...})` creates a coroutine value.
- `spawn(c)` takes a coroutine value, NOT a function literal directly.
  `spawn(fn() {...})` — what happens? Good error?
- Sending to a closed channel — what happens?
- Receiving from an empty channel with no sender — does `run_loop` exit or hang?
- Two coroutines communicating via a channel: basic producer/consumer pattern works.
- `test.flush_async()` is synchronous — NO `await` keyword anywhere in Nodus.
  Verify `await x` gives a useful error.

### 4.2 — Workflow DSL (new in v4.0.0)

**Claims to verify:**
- `workflow w { step a { ... } }` basic syntax works.
- `step b after a { ... }` dependency syntax (not `depends_on`).
- `checkpoint "label"` inside a step body works; at workflow body level errors.
- `run_workflow(w, {...})` returns a **map** — `result["steps"]`,
  `result["failed"]`. NOT `result.steps`.
- Workflow with a deliberately failing step — how does failure propagate?
- Workflow with a step that depends on a non-existent step — error message?
- Workflow with a cycle in step dependencies — detected? Error message?

### 4.3 — Goal DSL (new in v4.0.0)

**Claims to verify:**
- `goal g { success_when { ... } fail_when { ... } }` basic syntax works.
- `run_goal(g, {...})` returns a **map** — `result["goal"]`.
- Goal where success condition fires immediately.
- Goal where fail condition fires.
- Goal with neither condition — what happens? Does it loop forever?
  Does `--step-limit` or `--time-limit` protect against this?

### 4.4 — Async builtins (new in v4.0.0)

**Claims to verify:**
- `http_get_async(url)` and `subprocess_run_async(cmd)` are BUILT-IN.
- They use thread+channel suspension — concurrent, not serial.
- Test: spawn 3 concurrent `http_get_async` calls. They should resolve
  in parallel (or close to it), not serially.
- Confirm the result shapes: same record shape as sync equivalents.

### 4.5 — NodusRuntime embedding API

**Claims to verify:**
- `NodusRuntime()` with NO arguments applies a 200ms wall-clock deadline.
  Verify: a coroutine that sleeps 300ms total IS killed.
- `NodusRuntime(timeout_ms=None, max_steps=None)` removes the deadline.
  Verify: same coroutine survives.
- Pass data IN from Python (`rt.run_source` with a prelude injecting values)
  and read data OUT. Round-trip fidelity?
- Two NodusRuntime instances in the same Python process — isolation?

### 4.6 — CLI flag regression check

**Claims to verify:**
- `--allow-paths` flag (not `--allowed-paths`): confirm the correct name,
  confirm it actually restricts fs access outside the allowed path.
- `nodus fmt` — formats .nd files, does NOT use the installed nodus.exe stale
  version issue (this is a dev concern, but verify the formatter works on PyPI install).
- `nodus workflow runs|inspect|dead-letters|replay|migrate-state` subcommands —
  do they exist? Do they work for a basic workflow?

### 4.7 — Error message quality audit (cross-cutting)

For every error triggered in sections 3–4, score the message:
- Does it say WHAT went wrong?
- Does it say WHERE (file, line, column)?
- Does it suggest a fix or point to docs?
- Is it a Nodus error or a leaked Python traceback?

Track in EVAL_LOG.md as you go. Summary table in the final report.

---

## 5. AUDIENCE LENSES

When writing the report, assess from each angle separately:

- **The AI agent author.** Nodus's primary strategic user is an AI model
  generating Nodus code to run against a NodusRuntime host. Is the surface
  predictable, enumerable, uniform? Does an error tell the model how to fix
  it? Could a model write correct Nodus from the docs alone? This lens is
  the most important one for v4.0.0.
- **The human adopter.** On-ramp, docs, error legibility, "do I trust this."
- **The embedder / library author.** Using NodusRuntime in Python: API
  stability, the 200ms trap, subprocess gotchas, channel semantics.
- **The migrating user (v3→v4).** How much breaks, how well is it signposted,
  does the migration guide (if any) actually work.

---

## 6. DELIVERABLES  (four files → moved to docs/evals/v4.0.0/)

1. **`EVAL_LOG.md`** — chronological evidence trail. Entry #1 = version
   provenance (Section 2). Every subsequent entry: command run, verbatim
   input, verbatim output, exit code, timestamp.

2. **`NODUS_EVAL_REPORT.md`** — narrative assessment:
   - TL;DR verdict (2–3 sentences, lead with the honest bottom line)
   - Findings ordered by severity then leverage
   - Migration audit results (what broke, whether the guide worked)
   - "Build something real" experience writeup
   - Per-audience verdicts (Section 5)
   - Comparison to v3.0.2 baseline

3. **`NODUS_EVAL_RUBRIC.md`** — 1–10 scoring:

   Dimension                        | Score | Rationale
   ---------------------------------|-------|----------
   Install and first-run UX         |       |
   CLI ergonomics                   |       |
   Error message quality            |       |
   Parser robustness                |       |
   Integer/float type model         |       |
   Map vs Record distinction        |       |
   Standard library completeness    |       |
   Standard library correctness     |       |
   Module system                    |       |
   Coroutines and channels          |       |
   Workflow DSL                     |       |
   Goal DSL                         |       |
   Async builtins                   |       |
   Embedded / programmatic API      |       |
   Documentation accuracy           |       |
   Documentation completeness       |       |
   Migration from v3 experience     |       |
   AI-authorability (can a model write correct Nodus from docs?) |  |
   Stability under stress           |       |
   Overall first-week usability     |       |

   Composite weighted score with weights explained in a footer.

4. **`NODUS_EVAL_BUGS.md`** — filable issues, one per finding:
   ```
   ### BUG-NNN: <short title>
   **Severity:** CRITICAL / HIGH / MEDIUM / LOW / COSMETIC
   **Subsystem:** parser | runtime | stdlib | workflow | goal | channels | cli | docs | embedding
   **Affects:** v4.0.0
   **Repro:**
   ```
   <exact copy-pasteable script>
   ```
   **Expected:** 
   **Actual:** 
   **Fix direction:** 
   ```
   File COSMETIC findings too. Order by severity, then subsystem.

---

## 7. EXIT CONDITION

All four deliverables produced and internally consistent (every report claim
cites the log); bugs filed; four files moved to `docs/evals/v4.0.0/` in the
main Nodus repo at `C:\dev\Coding Language`. Report the composite score and
the single most important finding in your final message.
