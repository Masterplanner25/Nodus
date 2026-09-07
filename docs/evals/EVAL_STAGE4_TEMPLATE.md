# NODUS vX.Y.Z — STRESS-TEST USER EVALUATION (TEMPLATE)
#
# This is the GENERALIZED, version-agnostic stress-test prompt. It is the
# canonical Stage-4 eval prompt for any release. Each cycle, copy this file,
# fill the FILL-ME fields in Section 0, work the ADAPTATION CHECKLIST at the
# bottom, then hand the result to a FRESH evaluator session.
#
# Lineage: adapted from the v2.0.0 original → v3.0.0 major-release variant →
# this generalized template. Keep the lineage note when you copy.

# =====================================================================
# SECTION 0 — RELEASE PARAMETERS  (FILL THESE BEFORE RUNNING)
# =====================================================================
#
#   TARGET VERSION      : vX.Y.Z
#   RELEASE TYPE        : [ major | minor | patch ]
#   PRIOR BASELINE      : v(N-1)  (eval score: __ / 10)
#
#   INSTALL SOURCE      : [ PRE-PUBLISH  | POST-PUBLISH ]
#     - PRE-PUBLISH  → install the LOCAL build under test. Do NOT pull from
#                      PyPI. Record exact install command and resolved
#                      version (e.g. editable install, built wheel, or
#                      `.nodus/modules/` local-wins path). The point of a
#                      pre-publish run is to break it BEFORE the tag exists.
#     - POST-PUBLISH → install the published artifact from PyPI by exact
#                      pinned version. Confirm the resolved version matches
#                      TARGET VERSION before doing anything else. A version
#                      mismatch here invalidates the entire run.
#
#   WORKING DIRECTORY   : an EMPTY, NON-GIT, local-only directory
#                         (the v3.0.0 model used `C:\dev\nd testing\`)
#   DELIVERABLE DIR     : docs/evals/vX.Y.Z/   (move the four files here at end)
#
#   CHANGE SURFACE      : the specific things this release changed —
#                         breaking changes, new semantics, new opt-in syntax,
#                         migration paths, CLI changes. List them in the
#                         "SURFACE TO PROBE" block in Section 4. For a PATCH
#                         eval, scope the whole run to ONLY the patched
#                         surfaces (the v2.0.1 model: eval only the fixes from
#                         the prior eval, not a full re-run).
#
# =====================================================================

You are an independent technical evaluator. You have no prior context on
the Nodus language. Pretend you are a senior engineer who saw the vX.Y.Z
release announcement and decided to spend a day evaluating whether to adopt
it for a real project.

You did NOT participate in building or releasing this version. You do not
trust the release notes — you verify them. Your job is to find the sharp
corners, not to confirm that the release is good.

---

## 1. INTEGRITY RULES  (read these first, they govern everything)

1. **Log everything, fix nothing.** You are evaluating, not patching. If you
   find a bug, you record it — you do not work around it silently and you do
   not edit Nodus's source. Workarounds you discover get logged AS
   workarounds, with the underlying defect filed.

2. **No claim without evidence.** Every statement in any report file must be
   traceable to an entry in `EVAL_LOG.md`. If it isn't in the log with a
   command, input, and actual output, it does not go in a report. No claim
   from memory, no claim from the release notes, no claim you "expect" to be
   true. Run it.

3. **Paste real output.** The log contains actual terminal output — exit
   codes, error text verbatim, the actual printed result — not your summary
   of what happened. Summaries go in the report; raw evidence goes in the log.

4. **Severity is calibrated, not softened.**
   - **CRITICAL** = broken in a way that blocks a user from real work.
   - **HIGH** = a documented feature does not behave as documented.
   - **MEDIUM** = works, but with a sharp corner a real user will hit.
   - **LOW** = minor friction, papercut.
   - **COSMETIC** = output/formatting/wording. File these too — they are
     polish signal even when they block nothing.
   Do not round a HIGH down to a MEDIUM because the rest of the release is
   good. Do not round a MEDIUM up because you want the report to look
   thorough. The fix decision is not yours; accurate severity is.

5. **Stop-and-report when reality differs from this prompt.** If the install
   doesn't resolve to TARGET VERSION, if a file this prompt references
   doesn't exist, if the change surface described here doesn't match what
   shipped — STOP, log the discrepancy, and report it. Do not proceed on a
   wrong assumption.

6. **Version provenance is the first log entry.** Before any test, record:
   the install command, the install source (PRE/POST-PUBLISH), the resolved
   version as Nodus itself reports it, and confirmation it matches TARGET
   VERSION. (Prior cycles were burned by dev/CI version divergence — a
   wrong resolved version makes every finding meaningless.)

---

## 2. SETUP

In the empty working directory:

1. Record the environment: OS, shell, Python version, how Nodus is installed
   per Section 0's INSTALL SOURCE.
2. Install Nodus per INSTALL SOURCE. Capture the exact command and output.
3. Ask Nodus for its own version. Confirm it equals TARGET VERSION. Log it.
   If it does not match → STOP (integrity rule 5).
4. Create `EVAL_LOG.md` and write the provenance block as entry #1.

Do not read Nodus's source code to form your assessment. You may read the
PUBLIC docs (README, language reference, migration guide, CLI `--help`) —
because a real adopter reads those — but you evaluate SHIPPED BEHAVIOR, not
intentions in the source.

---

## 3. EVALUATION ARC  (work in order, log as you go)

### 3a. First contact
Install, version check, `--help` on every entry point, run the simplest
possible program ("hello world" equivalent), run whatever the README's
quick-start tells you to. Does the advertised on-ramp actually work, exactly
as written, with no undocumented step? Log every divergence between what the
docs say and what happens.

### 3b. Language core
Exercise the type system, operators, control flow, functions, data
structures, and error model. Feed adversarial input to every wrapped surface
(json, fs, path, math, etc.): malformed input, wrong types, empty, huge,
boundary values. Confirm error messages are Nodus's own — log any Python
traceback or Python-implementation text that leaks through to the user.
Confirm documented equality/coercion contracts hold by testing them.

### 3c. The error contract
If the release documents an error shape (e.g. an always-present `err.payload`,
per-kind payload keys, an error-kind taxonomy), test the contract directly:
the always-present guarantees AND the per-kind specifics. Test any documented
escape hatch (e.g. a trace/verbose flag). A documented error contract that
doesn't hold is a HIGH at minimum.

### 3d. SURFACE TO PROBE  (release-specific — see Section 4)
This is where you validate the things THIS release changed. Section 4 lists
them. Each item gets: does the changed behavior actually do what the release
claims, under normal AND adversarial use?

### 3e. Migration audit  (skip for patch releases unless behavior changed)
Take real working code from the PRIOR version. Run it on TARGET VERSION
unmodified. Log exactly what breaks. Then follow the migration guide
step-by-step and confirm it actually gets the code working. A migration guide
that doesn't produce working code is a HIGH. Note anything that breaks that
the migration guide fails to mention — those are the worst findings, because
a real adopter hits them with no warning.

### 3f. Build something real
Pick a small but genuine task — not a toy, something with a handful of moving
parts (e.g. read input, transform, branch on a condition, handle an error
path, produce output). Build it the way a real adopter would, reaching for
the docs as needed. This section surfaces the undocumented gotchas the
structured tests miss — in prior cycles it was consistently the most valuable
part for next-version planning. Log the friction: every moment you had to
guess, every place the docs were silent, every workaround you needed.

---

## 4. SURFACE TO PROBE  (FILL PER RELEASE)

> Replace this block each cycle with the specific change surface. Be concrete
> and adversarial — name the feature, name the claim, name the test.
>
> Example shape (from the v3.0.0 cycle — DELETE and replace):
>   - Integer opt-in (`1i` literal): does it solve the documented bug? Does
>     mixed int/float arithmetic behave as spec'd? Does the embedding-API
>     marshaling change actually fire?
>   - Python error replacement across json/fs/path/math: adversarial input,
>     confirm zero Python text leaks, test the `--trace-errors` escape hatch.
>   - `err.payload` always-present contract + documented per-kind keys.
>   - Parser error quality on the newly-rejected syntax (e.g. bare identifier
>     map keys) — is the message actionable?
>   - Migration from v(N-1): real prior code, unmodified, on the new version.
>   - CLI changes (e.g. `--help` grouping fix): validate the specific fix.
>   - Documented coercion contracts: `0 == false`, `"5" == 5`, etc.
>
> For a PATCH eval: this section IS the whole eval. List only the fixes the
> patch claims to deliver; validate each fix specifically; do not re-run the
> full arc.

[ FILL ME ]

---

## 5. AUDIENCE LENSES

When writing the report, assess the release from each angle separately —
the same finding can be CRITICAL for one and irrelevant to another:

- **The AI agent author.** Nodus's strategic user is an AI generating Nodus
  code. Is the surface predictable, enumerable, uniform? Does an error tell
  the agent how to fix it? Could a model write correct Nodus from the docs
  alone?
- **The human adopter.** On-ramp, docs, error legibility, "do I trust this."
- **The migrating user.** Coming from v(N-1): how much breaks, how well is it
  signposted, does the migration guide actually work.

---

## 6. DELIVERABLES  (four files, in the working dir, then moved to docs/evals/vX.Y.Z/)

1. **`EVAL_LOG.md`** — chronological evidence trail. Entry #1 is version
   provenance (Section 2). Every subsequent entry: what you ran, the verbatim
   input, the verbatim output, exit code, timestamp. This is the floor —
   nothing in the other three files may make a claim not backed here.

2. **`NODUS_EVAL_REPORT.md`** — narrative assessment:
   - TL;DR verdict (2–3 sentences, lead with the honest bottom line)
   - Findings, ordered by severity then leverage
   - Migration audit results (what broke, whether the guide worked)
   - "Build something real" experience writeup (the friction log, narrated)
   - Per-audience verdicts (Section 5)
   - Comparison to the v(N-1) baseline: better/worse, where, why

3. **`NODUS_EVAL_RUBRIC.md`** — 1–10 scoring across ~20 dimensions
   (install/on-ramp, docs, type system, error model, error-message quality,
   CLI, stdlib coverage, adversarial robustness, migration experience,
   AI-authorability, performance-feel, etc.). Weighted composite score.
   Explicit comparison to the prior baseline composite. Track the TREND, not
   the absolute number.

4. **`NODUS_EVAL_BUGS.md`** — filable issues, one per finding:
   - `BUG-NNN` title
   - subsystem label
   - severity label (Section 1 rule 4)
   - milestone routing suggestion (patch / next-minor / next-major)
   - repro (exact, copy-pasteable)
   - expected vs actual
   - fix direction (a pointer, not a patch)
   File COSMETIC findings too.

---

## 7. EXIT CONDITION

All four deliverables produced and internally consistent (every report claim
cites the log); bugs filed; four files moved to `docs/evals/vX.Y.Z/`. Report
the composite score and the single most important finding in your final
message.

---
---

# ADAPTATION CHECKLIST  (do this every time you copy this template)

- [ ] Section 0: fill TARGET VERSION, RELEASE TYPE, PRIOR BASELINE + its score.
- [ ] Section 0: set INSTALL SOURCE to PRE-PUBLISH or POST-PUBLISH and write
      the exact install command for that source. (v4.0 is held off PyPI — a
      pre-publish run installs the local/editable build, NOT PyPI.)
- [ ] Section 0: set the working dir (empty, non-git) and the deliverable dir.
- [ ] Section 4: DELETE the example block, write the real change surface for
      this release — every breaking change, new semantic, migration path,
      CLI change, named with a concrete adversarial test.
- [ ] If RELEASE TYPE = patch: scope Section 3 to 3d only, pointed at the
      patched surfaces; note in Section 4 that this is a fixes-only re-run.
- [ ] Update the lineage note at the top with this version.
- [ ] Hand the filled prompt to a FRESH evaluator session — one that did not
      do the release prep. Independence is the whole point.

# BEFORE/AFTER-PUBLISH USAGE

- **Before publish** (break it while you still can): INSTALL SOURCE =
  PRE-PUBLISH, against the local build. Findings route to "fix before tag" vs
  "ship and file." This is the gate that decides whether the tag goes out.
- **After publish** (confirm the artifact users actually get): INSTALL SOURCE
  = POST-PUBLISH, against the pinned PyPI version. This catches packaging /
  publish-path defects the local build can't show — the classic case being a
  resolved-version mismatch or a missing-in-the-wheel module. Run it as soon
  as the artifact is live.
