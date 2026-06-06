# NODUS v4.0.0 — Scoring Rubric

Independent post-publish evaluation. Scores 1–10. Every rationale traces to `EVAL_LOG.md`.
Install: `nodus-lang==4.0.0` from PyPI, verified `Nodus 4.0.0`, import resolves to the installed
site-packages copy (not dev source).

| Dimension | Score | Rationale |
|-----------|:----:|-----------|
| Install and first-run UX | 9 | `pip install` clean (deps: httpx, tzdata). `--version` matches. hello-world, `check`, `fmt`, and the embedding one-liner all worked first try. Only blemish: a mojibake glyph in help output. (LOG #1, #2) |
| CLI ergonomics | 8 | Rich, well-organized `--help`; every documented subcommand present and working (run/check/fmt/workflow/goal-run/stability/...). `--allow-paths` enforces correctly. Minor: wrong flag names surface as "File not found: --flag"; `goal-run --help` treats `--help` as a file. (LOG #2, #16, #21) |
| Error message quality | 8 | Consistently typed (`Type error`/`Syntax error`/`Name error`/`Sandbox error`/`Key error`/`Import error`) with file:line:col. NO leaked Python tracebacks anywhere. Standouts: tool dotted-name error suggests the fix; `spawn(fn)` names the expected type. Dragged down by `break`/`await`→"Undefined variable" and the stale div-by-zero docs. (LOG #24) |
| Parser robustness | 9 | Empty/whitespace/comment-only files exit clean. Unterminated string/bracket, 100-deep parens (depth-50 cap, no crash), mixed CRLF/LF, unicode-in-strings all handled gracefully with positioned errors. (LOG #8) |
| Integer/float type model | 8 | Coherent and arbitrary-precision: `1i+2i`=int, mixed promotes to float, division always float, no overflow. Strict, well-defined. Cost a point because bare literals defaulting to float is a silent footgun for migrators and isn't surfaced in the migration guide. (LOG #3, #22) |
| Map vs Record distinction | 9 | The two documented error strings fire verbatim with position; record=dot, map=bracket held up across every test including the real task. Clear and enforced. The friction is inherent to having two collection types, not a defect. (LOG #4) |
| Standard library completeness | 6 | Broad surface (json/fs/http/subprocess/hash/strings/math/encoding/time/env/secrets/tool/test/async/collections...). But missing `starts_with`/`ends_with` bit me immediately in a real task, and list-append has two confusingly-split names. (LOG #13, #23) |
| Standard library correctness | 7 | json/hash/http/subprocess/math/strings/tool all behaved as documented with good typed errors. Knocked down by `base64_decode` returning bytes-as-hex while the doc promises a string round-trip (HIGH). (LOG #9, #11, #12, #13) |
| Module system | 9 | `export fn` + `import "./mod" as alias` worked first try in the real task; named imports and stdlib imports documented and consistent. `check` validates each file. Solid. (LOG #23) |
| Coroutines and channels | 6 | Producer/consumer, closed-channel semantics (`recv`→nil, `send`→error), `spawn(fn)` rejection, and `import "std:channel"` rejection all behaved as documented. But the canonical consumer loop needs `break` (unsupported), empty-channel `recv` silently strands the coroutine, and the whole surface is flagged Experimental. (LOG #17) |
| Workflow DSL | 6 | Dependencies/topological levels, `plan_workflow`, checkpoints, cyclic detection, bad-dep compile error, and real-throw failure propagation all work. But the documented failing-step example (`1/0`) does NOT fail the step — downstream runs and `failed` is empty — and the result map omits the doc's `"error"` key. Experimental. (LOG #14, #15) |
| Goal DSL | 7 | `goal == workflow` with identical step/after syntax works; `run_goal` returns a map with `r["goal"]`. NOTE: the `success_when`/`fail_when` form (from the eval prompt) does not exist in shipped v4 — the shipped surface matches the public docs, not the prompt. Scored on what ships. (LOG #16) |
| Async builtins | 8 | `subprocess_run_async` in spawned coroutines is genuinely concurrent (3×1s → ~1.3s), exactly as documented. Same record shape as sync. Minus a point for the non-portable Windows doc example. (LOG #18) |
| Embedded / programmatic API | 8 | `run_source` returns a clean structured dict; round-trip injection, `register_function`, and two-runtime isolation all work. The 200ms deadline trap is real but documented, and `timeout_ms=None` fixes it. Held back from 9 by the open-by-default filesystem sandbox (BUG-001). (LOG #10, #19, #20) |
| Documentation accuracy | 6 | Mostly excellent and verifiable — the migration guide's helpers and cyclic-workflow payload matched reality exactly. But three real contradictions: base64 round-trip, div-by-zero "catchable", and the workflow failing-step example. Each is a doc that promises behavior the runtime does not deliver. (LOG #13, #15, #22) |
| Documentation completeness | 8 | Deep guide set (types, json, maps, modules, error-handling, workflows, embedding, stdlib), a real migration guide, and a `stability` index that honestly labels experimental surfaces. Gaps: integer-literal migration note, `starts_with`/`ends_with`. (LOG #22, #25) |
| Migration from v3 experience | 7 | A real, accurate, verifiable v3→v4 guide exists (every example I ran worked). But it omits the single most common change — bare integer literals are now floats — and the `json.parse` dot→bracket break, so a v3 program silently "half-runs". (LOG #22) |
| AI-authorability | 7 | Strong fundamentals for a model: enumerable surface, uniform typed errors with positions, no Python leakage, a machine-readable `stability` index, errors that often name the fix. Undercut by misleading messages on common keywords (`break`/`await`→"Undefined variable") and doc/runtime contradictions a model would trust and get wrong. (LOG #5, #17, #24) |
| Stability under stress | 8 | No crashes, no hangs, no segfaults across adversarial parser input, deep nesting, empty channels, concurrent subprocesses, and div-by-zero. Deadlines and depth caps fire predictably. The slow tree-walking VM (~45k loop iters/sec) is the main stress concern. (LOG #8, #17, #19) |
| Overall first-week usability | 7 | A capable, internally-consistent language with an honest stability story and a working embedding path. A real task came together in ~15 min with two stdlib-discoverability snags. The HIGH items (embedded sandbox default, base64 docs) and the experimental-DSL sharp corners are what a team would weigh before adopting. |

---

## Composite weighted score: **7.3 / 10**

### Weights and computation

Weighted toward what matters for adoption and for Nodus's stated primary audience (AI agents
authoring code against an embedded host).

| Dimension | Score | Weight |
|-----------|:----:|:-----:|
| Install and first-run UX | 9 | 1.0 |
| CLI ergonomics | 8 | 0.5 |
| Error message quality | 8 | 1.5 |
| Parser robustness | 9 | 1.0 |
| Integer/float type model | 8 | 1.0 |
| Map vs Record distinction | 9 | 1.0 |
| Standard library completeness | 6 | 1.0 |
| Standard library correctness | 7 | 1.0 |
| Module system | 9 | 0.5 |
| Coroutines and channels | 6 | 0.5 |
| Workflow DSL | 6 | 0.5 |
| Goal DSL | 7 | 0.25 |
| Async builtins | 8 | 0.5 |
| Embedded / programmatic API | 8 | 1.5 |
| Documentation accuracy | 6 | 1.5 |
| Documentation completeness | 8 | 1.0 |
| Migration from v3 experience | 7 | 0.75 |
| AI-authorability | 7 | 1.5 |
| Stability under stress | 8 | 1.0 |
| Overall first-week usability | 7 | 1.0 |

Weighted sum = 133.875 over total weight 18.25 → **7.34**, rounded to **7.3 / 10**.

**Weighting rationale:** Error quality, embedding API, documentation accuracy, and AI-authorability
carry 1.5 each because they are the load-bearing surfaces for a runtime whose headline use case is an
AI model generating code against a `NodusRuntime`. The experimental DSLs (workflow/goal/channels) are
weighted at 0.25–0.5 because the shipped `nodus stability` index explicitly labels them Experimental —
their sharp corners are disclosed, not hidden. Core-language and parser dimensions sit at 1.0.
