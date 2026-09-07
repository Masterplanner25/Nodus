# Nodus vX.Y.Z — Pre-Publish Creator Validation
# Gate 10 / Playbook A Stage 3 / Playbook B Phase 5A

**Role:** You are the creator, not an independent evaluator. You have full context.
The goal is adversarial self-testing: find every fixable bug before users encounter it.

**Install from the built wheel, not dev source:**
```powershell
python -m build --wheel
python -m venv .venv-validation
.venv-validation/Scripts/pip install dist/nodus_lang-X.Y.Z-py3-none-any.whl
```

Confirm: `.venv-validation/Scripts/nodus --version` reports the correct version.

**Disposition rule for every failure found:**
- **Fixable before publish** (clear root cause, low regression risk): fix it now, rebuild wheel, add a regression test, add to CHANGELOG
- **Not fixable before publish**: file a GitHub issue immediately with full repro; note it in the release announcement

Record results in `docs/evals/vX.Y.Z/CREATOR_VALIDATION.md` — even a clean run.

---

## Required: Run the standard test scripts

Run these three in order against the installed wheel (not dev source):

```powershell
.venv-validation/Scripts/nodus run tests/eval/quirk_probe.nd
.venv-validation/Scripts/nodus run tests/eval/language_exerciser.nd
.venv-validation/Scripts/nodus run tests/eval/framework_capabilities.nd
```

**Expected output for each:** `ALL QUIRKS CONFIRMED` / `ALL EXERCISES PASSED` / `ALL FRAMEWORK PROBES PASSED`

Any failure is a regression. Investigate before proceeding.

---

## Required: Adversarial edge case programs

Write 8-12 programs targeting the highest-risk surfaces. Cover every category below.

### Category 1: Documented quirks (verify they still hold)
Each quirk in `CLAUDE.md §"Nodus language quirks"` must behave exactly as documented.
- `len()` returns int (v4)
- No `+=` operator
- `spawn()` takes a coroutine value, not a function literal
- Multiline list/call syntax (both `[1,\n2]` and `len(\n"hi"\n)` should error)
- `print()` is single-argument
- `std:hash` returns a record, call `.to_hex()`
- `std:tool` names must be dotted
- Coroutine 200ms deadline trap (test with `timeout_ms=None`)

### Category 2: Error messages (are they user-legible?)
Trigger each of these and rate the message 1-3 (1=opaque Python traceback, 3=clear Nodus error with line/col):
- Type error: `"hello" + 42`
- Name error: `print(undefined_variable)`
- Import error: `import "does-not-exist"`
- Sandbox error: use `allowed_paths=[]` and try `read_file("something")`
- Stack overflow: infinite recursion with `--step-limit 100`
- Circular import: two files that import each other

### Category 3: v4.0 AI-native primitives
```nd
import "std:tool" as tool
import "std:identity" as identity
import "std:effects" as fx
import "std:memory" as mem
import "std:retry" as retry
import "std:circuit_breaker" as cb
```
For each:
- Register and call a tool — verify namespacing enforced
- Read trace_id and session_id — verify they return non-nil strings
- Create an effect, resolve it, verify EXACTLY_ONCE behavior
- share/recall_from/recall_all round-trip
- retry.call with a function that fails twice then succeeds
- cb.create + cb.call + cb.state cycle

### Category 4: Coroutines and channels
- Spawn 3 coroutines that all send to one channel; one receiver collects all 3
- Coroutine that throws — verify other coroutines continue (`on_error` hook)
- Channel closed while receiver is waiting — verify nil returned, not hang
- Sleep inside a coroutine with `timeout_ms=None` — verify it wakes up correctly

### Category 5: Workflows and goals
- Simple 3-step workflow with state — run to completion, check final state
- Workflow with step that fails — verify failure propagates cleanly
- Goal with `run_goal` — verify result has `goal` and `steps` keys
- Checkpoint and resume: `checkpoint "mid"`, clear graph registry, `resume_goal`
- Workflow with circular step dependency — verify error message

### Category 6: NodusRuntime embedding
```python
from nodus import NodusRuntime

# Test: on_error hook detects coroutine death
errors = []
rt = NodusRuntime(timeout_ms=None, on_error=lambda co, e: errors.append(str(e)) or False)
rt.run_source('spawn(coroutine(fn() { throw "oops" }))\nspawn(coroutine(fn() { print("ok") }))\nrun_loop()')
assert "ok" in rt.last_vm.globals  # other coroutine ran
assert len(errors) == 1 and "oops" in errors[0]

# Test: subprocess_run_async concurrency
# Three 1s subprocesses should complete in ~1s not ~3s
```

### Category 7: stdlib I/O
- `http.get` a real URL (or localhost if no network) — error message quality on failure
- `subprocess.run(["python", "-c", "print('hello')"])` — output captured
- `subprocess.run_async` with 2 concurrent 0.5s processes — verify concurrency speedup
- `fs.read` on nonexistent file — error quality
- `fs.write` outside `allowed_paths` — sandbox blocks correctly

### Category 8: Formatter and checker
```powershell
# Formatter: can it round-trip every construct from tests/eval/?
python nodus.py fmt tests/eval/quirk_probe.nd --check
python nodus.py fmt tests/eval/language_exerciser.nd --check
python nodus.py fmt tests/eval/framework_capabilities.nd --check

# Checker: catches actual syntax errors, doesn't flag valid code
```

---

## Record results

Write `docs/evals/vX.Y.Z/CREATOR_VALIDATION.md` with:
- Version and date
- Wheel build confirmed from which commit
- Results of all three standard scripts
- Category 1-8 results with pass/fail/note per item
- Any failures: fix committed (with hash) or issue filed (with number)
- Clean run note: "No issues found" if applicable

The file must exist even if everything passes — a clean run is evidence, not silence.

---

## Do not proceed to PyPI upload until:

- [ ] All three standard scripts print their success message against the installed wheel
- [ ] All 8 required categories have been exercised
- [ ] Every failure is either committed-and-fixed or filed-as-an-issue
- [ ] `docs/evals/vX.Y.Z/CREATOR_VALIDATION.md` exists and is committed

See `docs/governance/RELEASE_GATES.md §Gate 10` for the governing policy.
