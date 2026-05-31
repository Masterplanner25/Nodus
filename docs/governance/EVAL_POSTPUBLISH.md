# Nodus vX.Y.Z — Independent Post-Publish Stress-Test Evaluation
# Playbook A Stage 5 / Playbook B post-Phase 5B

You are an **independent technical evaluator**. You have no prior context on
Nodus. You are a senior engineer who saw the vX.Y.Z release announcement and
decided to spend a day evaluating whether to adopt it for a real project.

You are in **RESEARCHER MODE**: read any public documentation including the
GitHub repo, README, LANGUAGE_SPEC, ARCHITECTURE, CHANGELOG, and PyPI page.
You are doing depth, not first impressions.

Your job is to **stress test the language**. Find sharp corners, break things,
document what breaks. An honest assessment of where vX.Y.Z actually stands.

**Critical:** run in a fresh session that did NOT participate in release prep.
Use a clean venv. Install from real PyPI.

---

## SECTION 0 — SETUP

1. Confirm working directory is empty (non-git, local-only)
2. Create fresh Python venv: `python -m venv .venv && .venv/Scripts/activate`
3. Install from real PyPI: `pip install nodus-lang==X.Y.Z`
4. Confirm: `nodus --version` reports X.Y.Z
5. Create: `mkdir scratch`
6. Start: `EVAL_LOG.md` — append a timestamped entry for every noteworthy step

---

## SECTION 1 — RESEARCH PASS

Read in full before starting any tests:
- PyPI project page
- README.md (what does the landing page claim?)
- CHANGELOG.md (what is new in this release?)
- docs/language/LANGUAGE_SPEC.md (full read, note the stability labels)
- docs/runtime/ARCHITECTURE.md
- `nodus stability` (run it — what does it say?)
- docs/guide/getting-started.md

Log:
- The canonical one-sentence definition of Nodus and whether it is consistent across README, spec, and architecture docs
- Any feature that sounds impressive — flag for stress testing
- Any stability label "Experimental" — flag for gentler testing (expected to be incomplete)
- Any documentation that contradicts itself

---

## SECTION 2 — STANDARD SCRIPTS (does it work at all?)

Copy the standard evaluation scripts from the repo and run them:

```powershell
# Copy from repo (these are committed test fixtures)
# tests/eval/quirk_probe.nd
# tests/eval/language_exerciser.nd
# tests/eval/framework_capabilities.nd
```

Run against the **installed** nodus (not dev source):
```powershell
nodus run scratch/quirk_probe.nd
nodus run scratch/language_exerciser.nd
nodus run scratch/framework_capabilities.nd
```

Log every failure as a finding. A script that prints "PASS" against the installed
wheel but failed during dev is a release bug.

Also run:
- `nodus run scratch/hello.nd` (print a string)
- `nodus repl` (enter, run `1 + 1`, exit)
- `nodus check scratch/hello.nd`
- `nodus stability` (read and log what it says)
- `nodus --help` (compare to what docs say is available)

---

## SECTION 3 — STRESS TEST: BREAK IT

### 3.1 — Parser and lexer
- Empty files; whitespace-only; comments-only
- Unicode in strings and comments
- Deeply nested expressions (50+ levels)
- Malformed syntax: unclosed strings, missing operators, reserved words as identifiers
- Files with CRLF+LF mixed line endings

### 3.2 — Types and values
- `"5" == 5` — what does equality across types return?
- `nil == false` — documented behavior?
- Division by zero; modulo by zero
- Very large integers (`999999999999999i`)
- `str(nil)`, `len(nil)`, `type(nil)` — do they error or return?

### 3.3 — Control flow
- Infinite loop with `--step-limit 500` — does the limit fire? Error message quality?
- Deeply recursive function — does `--step-limit` catch it?
- `try/catch/finally` — does finally run after catch returns? (documented invariant)

### 3.4 — Module system
- Import a module that doesn't exist — error message quality?
- Circular imports — detected and reported cleanly?
- Path traversal: `import "../../etc/passwd"` — blocked?
- Module that imports itself

### 3.5 — Standard library

**Core (expected stable):**
- `std:json`: `json.parse` on malformed JSON; `json.stringify` on nested structures
- `std:fs`: read nonexistent file; write outside `allowed_paths`; path traversal in fs paths

**v4 additions (labeled Experimental — probe but don't penalize for rough edges):**
- `std:tool`: register tool with dotted name, call it; try undotted name (should error)
- `std:http`: `http.get` a real URL or localhost — error message if unreachable?
- `std:subprocess`: `subprocess.run(["echo", "hello"])` — output captured?
- `std:identity`: `trace_id()` returns a string?
- `std:effects`: EXACTLY_ONCE: resolve → complete → resolve again (should return "complete")
- `std:memory`: share/recall_from round-trip
- `std:retry`: wrap a function that fails N times then succeeds
- `std:circuit_breaker`: open/half-open/closed cycle

### 3.6 — Coroutines and channels (Experimental)
- Spawn two coroutines that send to a channel; one receiver
- Coroutine that throws — do other coroutines continue?
- `run_loop()` exits when all coroutines done — does it exit cleanly?
- Close a channel with a waiting receiver — what happens?

### 3.7 — Workflows and goals (Experimental)
- Simple 3-step workflow with state
- Step that fails — does failure message identify which step?
- Checkpoint + resume: write a checkpoint, create a new VM, resume from it
- Cycle in step dependencies — is it detected?

### 3.8 — Embedding API
```python
from nodus import NodusRuntime

# Basic embed
rt = NodusRuntime(timeout_ms=None)
r = rt.run_source('print("hello")')
assert r["ok"] and "hello" in r["stdout"]

# on_error hook
errors = []
rt2 = NodusRuntime(timeout_ms=None, on_error=lambda co, e: errors.append(str(e)) or False)
rt2.run_source('spawn(coroutine(fn() { throw "oops" }))\nrun_loop()')
# errors should contain "oops"

# Step limit
rt3 = NodusRuntime(max_steps=100)
r3 = rt3.run_source('let i = 0\nwhile (true) { i = i + 1 }')
assert not r3["ok"]
assert r3["error"]["kind"] == "sandbox"
```

### 3.9 — Error message quality (cross-cutting)
For every error triggered above, rate on:
- Does it say WHAT went wrong?
- Does it say WHERE (file, line, column)?
- Is it a Nodus error or a leaked Python traceback?
- Does it suggest a fix?

---

## SECTION 4 — BUILD SOMETHING REAL

Build **one** of the following in 50-150 lines, split across 2+ `.nd` files,
using at least 3 stdlib modules. This tests real-world usability:

- **Option A:** Log parser — read a file, extract patterns, write a summary report
- **Option B:** JSON transformer — read JSON, restructure, write JSON
- **Option C:** Tool registry demo — register 3 tools, dispatch them from a workflow
- **Option D:** Event-driven counter — coroutines, channels, and state machine

Log: how long did it take? Where did you get stuck? What docs did you re-read?
What would have made the experience smoother?

Save under `scratch/real_task/` for inclusion in the report.

---

## SECTION 5 — META-OBSERVATIONS

1. **Identity** — Does Nodus have a clear reason to exist? What niche does this version claim?
2. **Audience** — Who is this for right now? Who is it demonstrably NOT for yet?
3. **Stability labels** — Do the "Experimental" labels in `nodus stability` match your experience?
4. **Documentation truth** — Where do docs match reality? Where do they diverge?
5. **Sharp corners count** — Rough number of "had to figure that out the hard way" moments.

---

## SECTION 6 — DELIVERABLES

Write three files to the working directory:

### File 1: NODUS_EVAL_REPORT.md

  # Nodus vX.Y.Z — Independent Evaluation
  Evaluator: [role]
  Date:
  Time invested:

  ## TL;DR (3-5 sentences)
  Bottom line: is vX.Y.Z actually usable today, for whom, with what caveats?

  ## What Nodus is
  One paragraph from the research pass. Note any definition inconsistencies.

  ## Standard scripts results
  Did quirk_probe, language_exerciser, framework_capabilities all pass against the wheel?
  Any failures here are CRITICAL findings.

  ## What works well
  Specific bullet list with evidence.

  ## Sharp corners
  Bullet list linked to NODUS_EVAL_BUGS.md findings.

  ## The build-something-real experience
  Half a page on Section 4.

  ## Verdict by audience
  - For AI/agent platform developers:
  - For Python devs embedding a scripting layer:
  - For language hobbyists / evaluators:
  - For someone considering Nodus over Python/Lua/Starlark:

  ## Top 3 things vX.Y+1.0 should prioritize

### File 2: NODUS_EVAL_RUBRIC.md

Score each dimension 1-10 with one-sentence rationale backed by EVAL_LOG.md.

  Dimension                       | Score | Rationale
  --------------------------------|-------|----------
  Install and first-run UX        |       |
  CLI ergonomics                  |       |
  Error message quality           |       |
  Parser robustness               |       |
  Type system behavior            |       |
  Core stdlib completeness        |       |
  Core stdlib correctness         |       |
  Module system                   |       |
  Coroutines and channels         |       | (Experimental — note if scoring leniently)
  Workflow / goal DSL             |       | (Experimental)
  AI-native primitives (std:tool etc) |   | (Experimental)
  Embedding / programmatic API    |       |
  Documentation accuracy          |       |
  Documentation completeness      |       |
  Stability under stress          |       |
  Overall first-week usability    |       |

  Composite score: [weighted average]
  Prior version score for comparison: [from docs/evals/]
  Delta: [+N or -N]

### File 3: NODUS_EVAL_BUGS.md

For each defect:

  ### BUG-NNN: <title>
  **Severity:** CRITICAL | HIGH | MEDIUM | LOW | COSMETIC
  **Subsystem:** parser | runtime | stdlib | repl | workflow | embedding | docs
  **Affects:** vX.Y.Z
  **Repro:**
  ```
  [minimal reproduction]
  ```
  **Expected:** [what should happen]
  **Actual:** [what happened]
  **Notes:** [workaround if any; related issue number if known]

Severity definitions:
- CRITICAL: data loss, crash, security issue, or core feature does not work at all
- HIGH: documented feature broken or significantly wrong
- MEDIUM: feature works but UX is broken (bad errors, confusing semantics)
- LOW: minor surprise; workaround exists
- COSMETIC: typo, formatting, doc nit

Order by severity, then by subsystem.

---

## SECTION 7 — INTEGRITY RULES

1. No finding in a deliverable that is not supported by EVAL_LOG.md evidence.
2. Do not soften findings to be polite. Calibration > tone.
3. Distinguish "I could not find a way to do X" (docs problem) from "X does not exist" (feature gap).
4. Experimental features: note when you are being lenient because of the Experimental label. Score the stable surface at full rigor; score Experimental features on "does it work at all and is it safe to use?"
5. The TL;DR must directly answer: "what would actually stop a real user?" 30 LOW bugs is different from 1 CRITICAL bug.

---

## FINAL CHECK BEFORE WRITING DELIVERABLES

Re-read EVAL_LOG.md. Include any finding you were tempted to omit because it
felt minor — it goes in NODUS_EVAL_BUGS.md at LOW or COSMETIC. They are signal
about polish even if they didn't block your work.

Move completed deliverables to `docs/evals/vX.Y.Z/` for archival.
