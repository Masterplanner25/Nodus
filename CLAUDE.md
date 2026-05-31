# Nodus — Claude Instructions

## Project identity

Nodus (`nodus-lang` on PyPI) is a bytecode-compiled scripting language and
runtime implemented in Python. Working directory: `C:\dev\Coding Language`.
Source lives under `src/nodus/`. Tests under `tests/`.

## Running code during development

The project `.venv` has an older PyPI install that takes precedence over
`src/` in `sys.path`. Always prefix with `PYTHONPATH` to get the dev source:

```powershell
PYTHONPATH="C:/dev/Coding Language/src" "C:/dev/Coding Language/.venv/Scripts/python.exe" ...
PYTHONPATH="C:/dev/Coding Language/src" "C:/dev/Coding Language/.venv/Scripts/nodus.exe" run script.nd
PYTHONPATH="C:/dev/Coding Language/src" "C:/dev/Coding Language/.venv/Scripts/python.exe" -m pytest tests/
```

Without `PYTHONPATH`, you get the installed package, not the current source.
Verify with: `nodus --version` — should match `src/nodus/support/version.py`.

## GitHub API

The `gh` CLI **is installed** and authenticated as `Masterplanner25`. Use it
directly for issue/PR/release operations:

```powershell
gh issue create --title "..." --body "..."
gh repo create Masterplanner25/name --public
gh release create vX.Y.Z --notes "..."
```

For raw API calls not covered by `gh`, use `urllib.request` with a token
retrieved from:

```bash
git credential fill <<< $'protocol=https\nhost=github.com'
```

Repo: `https://api.github.com/repos/Masterplanner25/Nodus`

Standard issue shape:

```python
{
    'title': 'BUG-NNN: short description',
    'body': '## Summary\n\n...\n\n## Reproduction\n\n...\n\n## Expected behavior\n\n...\n\n## Fix direction\n\n...\n\n## Affected versions\n\nv2.1.1 (current).',
    'labels': ['bug', 'subsystem:X', 'severity:low|medium|high|critical'],
    'milestone': 3   # v2.2 milestone
}
```

Write the script to a temp file and run it — inline heredocs with
triple-quoted strings cause PowerShell/Bash quoting issues.

## Version sync — must keep in step

Two files must always match:

- `src/nodus/support/version.py` — `__version__ = "X.Y.Z"`
- `pyproject.toml` — `version = "X.Y.Z"`

Release order: bump both files → move `[Unreleased]` in `CHANGELOG.md` to
the new version section → commit → `git tag vX.Y.Z` → `git push origin main
--tags` → build wheel → upload to PyPI.

PyPI upload — use explicit flags; `~/.pypirc` may have an empty password field
which causes a 403:

```powershell
"C:/dev/Coding Language/.venv/Scripts/python.exe" -m twine upload --username __token__ --password <token> dist/*
```

Token: retrieve from the user at upload time. Never store in any file.

Full release checklist: `docs/release.md`.

## Guide file testing standard

Every code example in `docs/guide/` must be run and produce verbatim output.
Protocol for each guide file:

1. Create a temp test directory: `/tmp/<guide-name>-tests/`
2. Run each example against dev source using the `PYTHONPATH` prefix above
3. Paste output verbatim into the doc — no invented output
4. Any surprising behavior gets a numbered finding (F32, F33, …) in a
   `<!-- TESTED ... -->` comment block at the bottom of the file
5. File behavioral findings as GitHub issues before committing

Guide files live in `docs/guide/`. The full guide index is in
`docs/guide/getting-started.md §7` and `llms.txt`.

## Key file locations

| What | Where |
|------|-------|
| Version | `src/nodus/support/version.py` |
| Changelog | `CHANGELOG.md` |
| Bug/issue list | GitHub Issues (Masterplanner25/Nodus) |
| Semver policy | `docs/release.md#semantic-versioning` |
| Compatibility policy | `docs/governance/COMPATIBILITY_MODEL.md` |
| Deprecation timeline | `docs/governance/COMPATIBILITY.md` |
| Stability index (surface-by-surface) | `docs/governance/LANGUAGE_STABILITY_INDEX.md` |
| Security posture | `docs/governance/SECURITY_POSTURE.md` |
| Release gates | `docs/governance/RELEASE_GATES.md` |
| Tech debt | `docs/governance/TECH_DEBT.md` |
| Docset index (reader entry point) | `docs/governance/DOCSET_INDEX.md` |
| Ecosystem maturity | `docs/governance/ECOSYSTEM_READINESS_ASSESSMENT.md` |
| Runtime invariants | `docs/runtime/EXECUTION_INVARIANTS.md` |
| Failure model | `docs/runtime/FAILURE_AND_DEGRADATION_MODEL.md` |
| Embedder runbook | `docs/runtime/OPERATOR_OR_EMBEDDER_RUNBOOK.md` |
| Guide files | `docs/guide/` |
| Runtime reference docs | `docs/runtime/` |
| Governance docs | `docs/governance/` |
| Release playbook | `docs/governance/RELEASE_PLAYBOOK.md` |
| Skills | `.claude/commands/` |
| Doc-vs-code gate | `tools/nodus_gate/` — run `python -m tools.nodus_gate.cli --all` |
| Library entry-point contract | `docs/guide/library-entry-points.md` |
| nodus-mcp companion repo | `C:\dev\nodus-mcp` / github.com/Masterplanner25/nodus-mcp |
| nodus-a2a companion repo | `C:\dev\nodus-a2a` / github.com/Masterplanner25/nodus-a2a |
| nodus-memory companion repo | `C:\dev\nodus-memory` / github.com/Masterplanner25/nodus-memory |
| nodus-native-memory-engine repo | `C:\dev\nodus-native-memory-engine` / github.com/Masterplanner25/nodus-native-memory-engine |
| nodus-extension companion repo | `C:\dev\nodus-extension` / github.com/Masterplanner25/nodus-extension |
| Ecosystem incubator specs | `docs/ecosystem/` — spec docs for planned libraries |
| Ecosystem incubator scaffolds | `packages/` — Python-first scaffolds for planned libraries |

## Test suite

```powershell
# Full suite
PYTHONPATH="C:/dev/Coding Language/src" "C:/dev/Coding Language/.venv/Scripts/python.exe" -m pytest tests/ -q

# Coverage (excludes 3 timing-sensitive tests)
PYTHONPATH="C:/dev/Coding Language/src" "C:/dev/Coding Language/.venv/Scripts/python.exe" -m pytest tests/ --cov=src/nodus --cov-fail-under=60 --ignore=tests/test_scheduler_fairness.py -q
```

Coverage baseline: 77% overall. Gate: 60%. See `docs/governance/TECH_DEBT.md`
for the per-module breakdown and the three deselected flaky tests.

**Known pre-existing failure:** `tests/test_goal_dsl.py::GoalDslTests::test_resume_goal`
fails with `KeyError: 'goal'`. This is a regression from before Phase 3 and is unrelated
to any recent work. Do not investigate it unless goal DSL work is explicitly in scope.

## .nd file formatting — authoritative command

**Always use `python nodus.py fmt` — never `nodus.exe` or bare `nodus fmt`.**

`nodus.exe` in `.venv` is the stale installed package (e.g. old release). CI runs
`python nodus.py fmt --check {}` which loads from `src/` (the dev source). Using
`nodus.exe` writes a format that diverges from what CI checks → commits pass locally
but fail CI. This is the writer-vs-checker split that broke the stdlib format gate
repeatedly across multiple pushes.

To format .nd files correctly (matches CI exactly):
```powershell
# Format one file
python nodus.py fmt src/nodus/stdlib/hash.nd

# Format all stdlib .nd files
python nodus.py fmt src/nodus/stdlib/*.nd

# Verify (verbatim CI check):
find . -name "*.nd" -not -path "./.git/*" -not -path "./.venv/*" -not -path "./tmp_demo/*" -not -path "./tests/fixtures/fmt/*" | xargs -I {} python nodus.py fmt --check {}
```

A pre-commit hook enforces this: if staged `.nd` files fail `python nodus.py fmt --check`,
the commit is blocked and the exact fix command is printed. Hook lives at `.git/hooks/pre-commit`
(not tracked by git — reinstall after fresh clone with `chmod +x .git/hooks/pre-commit`).

## Lint gate (ruff)

Ruff runs in CI and blocks merges. Check locally before pushing:

```powershell
& "C:/dev/Coding Language/.venv/Scripts/python.exe" -m ruff check src/ tests/
```

Two rules come up repeatedly:

- **F401 unused import** — just remove it; never suppress with `# noqa`.
- **E402 module-level import not at top** — occurs in test files that do
  `sys.path.insert` before imports (intentional path isolation pattern).
  Suppress with `# noqa: E402` on each affected import line. Do not
  restructure the path manipulation to avoid it.

**Pre-existing violations:** `ruff check src/` always shows ~33 pre-existing
errors in `src/nodus/vm/vm.py` (E702), `src/nodus/builtins/time_module.py`
(E701, F841), `src/nodus/builtins/encoding_module.py` (F401), and
`src/nodus/builtins/secrets_module.py` (F401). These pre-date Phase 3C and
are known. Do not introduce them into new code, but do not treat them as a
blocker for your own changes. When verifying a commit, run ruff scoped to the
files you actually changed rather than the whole `src/` tree.

## Git commit syntax (PowerShell)

Multi-line commit messages require a PowerShell here-string — bash `<<EOF`
syntax is not valid in PowerShell:

```powershell
git commit -m @'
Subject line here

Body paragraph here.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
'@
```

The closing `'@` must be at column 0 with no leading whitespace. For commits
that need a file (e.g. cross-repo where stdin is awkward), write the message
to `.git\COMMIT_MSG_TEMP` with `Out-File -Encoding utf8` then use
`git commit -F ".git\COMMIT_MSG_TEMP"`.

## Doc-vs-code gate (nodus_gate)

The gate is mandatory before any release. Run from the nodus-lang root:

```powershell
PYTHONPATH="C:/dev/Coding Language/src;C:/dev/Coding Language" `
  "C:/dev/Coding Language/.venv/Scripts/python.exe" `
  -m tools.nodus_gate.cli --all
```

- `--static`: verifies documented symbols exist in the codebase (76 symbols)
- `--runtime`: runs all ` ```nodus ` and ` ```nodus-expect=output ` blocks
  in docs (180 blocks); expects 0 failures with the `.nodusgate-allow`
  allowlist in place
- `--closed-issues`: runs closed-issue tests for CHANGELOG-referenced issues

The allowlist at `.nodusgate-allow` suppresses intentionally non-runnable
doc blocks (multi-file examples, error demos). New failing blocks go in the
allowlist OR are fixed before release.

## nodus-mcp companion library

- Repo: `C:\dev\nodus-mcp` / `github.com/Masterplanner25/nodus-mcp`
- **Status: v0.1.0 COMPLETE — prepared, not yet published.**
  All 14 phases done (Phase 1 design docs + Phases A–N implementation).
  361 tests pass (Phase A–N nodus-lang adapter + aindy bridge adapter tests).
  BYTECODE_VERSION 4, no new opcodes.
  Publication waits for nodus-a2a v0.1.0 (coordinated three-artifact launch).
- **Dual layout**: `src/nodus_mcp/` = full MCP protocol library (Phase A–N);
  `nodus_mcp_aindy/` = aindy-derived bridge adapter (wraps ToolRegistry as MCP server).
  The pyproject.toml `where = ["src"]` installs the Phase A–N library; the aindy
  adapter is importable as `nodus_mcp_aindy` but is not the primary package.
- Dev install: `pip install -e . --no-deps`
- Run tests: `cd C:\dev\nodus-mcp && PYTHONPATH="C:/dev/Coding Language/src" "C:/dev/Coding Language/.venv/Scripts/python.exe" -m pytest tests/ -q`
- **egg-info pitfall**: If `nodus_mcp.egg-info/` appears in the repo root (generated
  by old `setup.py develop` runs), pytest adds the rootdir to sys.path and
  `importlib.metadata` finds the stale egg-info instead of the site-packages dist-info.
  This breaks entry-point discovery. Fix: `rm -rf nodus_mcp.egg-info && pip install -e . --no-deps`.
  The `*.egg-info/` is in `.gitignore`.
- Entry-point contract: `[project.entry-points."nodus.nd"]` → callable returns
  absolute path to `.nd` root dir — see `docs/guide/library-entry-points.md`
- Key documented contracts (see `docs/governance/TECH_DEBT.md`):
  - TD-007: server-initiated requests over HTTP are stdio-only (no SSE/push)
  - TD-008: `_validate_args` is top-level type checking only (not full JSON Schema)
  - TD-009: resource read handler must raise `KeyError` for unknown URI → -32601
  - TD-010: `requestState` is on the wire; never checkpoint secrets in sentinel state
- **Next: coordinated three-artifact publication** — nodus-lang 4.0.0 + nodus-mcp 0.1.0.
  ⚠️ **nodus-a2a v0.1.0 (A2A wire protocol adapter) was REPLACED at `C:\dev\nodus-a2a`.**
  The original 180-test A2A protocol adapter is preserved on GitHub
  (`github.com/Masterplanner25/nodus-a2a`) but local code is now the Tier 2
  AgentCoordinator. Treat as a two-artifact coordinated launch (nodus-lang + nodus-mcp).

## nodus-a2a companion library

⚠️ **LOCAL REPO REPLACED.** The original A2A wire protocol adapter (Phases A–J, 180 tests,
published-ready) was overwritten at `C:\dev\nodus-a2a` by the Tier 2 AgentCoordinator
standalone package. The original code is preserved at
`github.com/Masterplanner25/nodus-a2a` (git history intact).

**Original A2A wire protocol adapter (on GitHub, NOT at local path):**
- 180 tests, nodus-lang dep, A2A 1.0 spec (message-only, HTTP+JSON/REST)
- `/.well-known/agent-card.json`, `application/a2a+json`, stdlib `ThreadingHTTPServer`
- Skill `/nodus-a2a-phase` references this version

**Current local `C:\dev\nodus-a2a` (AgentCoordinator layer, 23 tests):**
- `AgentRegistry`, `AgentCoordinator` (local/delegate mode), `DelegationRequest`
- `DeadLetterService`, `StuckRunWatchdog`
- No nodus-lang dependency; standalone coordination primitives

## Nodus language quirks (relevant when writing test .nd code)

These burn time when forgotten:

- **No `await` keyword.** `test.flush_async()` is synchronous — no `await`.
- **No `+=` operator.** Use `x = x + 1i`. In closures, you can't assign
  outer `let` variables at all — use a map and mutate a field: `state.count = state.count + 1i`.
- **Async test two-flush pattern:** `spawn → flush (task sleeps) → advance_clock(N) → flush (task wakes)`.
  Skipping either flush or the advance causes the test to pass vacuously.
- **`spawn()` takes a coroutine value**, not a function literal. Use
  `let c = coroutine(fn() {...})` then `spawn(c)`.
- **`fn` is a reserved keyword** — can't use as a parameter name in `.nd` files.
- **Multiline list literals and function calls cannot span newlines.** Both
  `[1,\n2]` and `len(\n"hi"\n)` give "Unexpected end of statement". Keep on one line.
- **`print()` is single-argument.** `print("label:", value)` → syntax error.
  Use string interpolation: `print("\(label): \(value)")`.
- **`std:hash` returns a hash record, not a string.** `hash.sha256(data)` returns
  a record with methods; call `.to_hex()` to get hex: `hash.sha256(data).to_hex()`.
- **`std:tool` names must be dotted.** `tool.register({name:"greet",...})` silently
  returns an error. Use `"myapp.greet"`. Error message says "must use dotted namespacing".
- **Coroutine execution limits (scheduler quirk):** The default 200ms deadline
  (`EXECUTION_TIMEOUT_MS=200`) counts wall-clock time including cooperative sleep.
  A coroutine that sleeps 4 × 100ms will be killed after 200ms total even though it
  consumed no CPU. Workaround: `nodus run --time-limit N`. SCHED-001, deferred to 4.0.1.

## Security boundary test rule

Any fix for a security boundary (path traversal, sandbox escape, allowed_paths
enforcement, resource limits) must have tests covering BOTH CLI mode and
`NodusRuntime` embedded mode. The enforcement code path can differ between
contexts. See `docs/governance/TECH_DEBT.md § Testing Methodology`.

## Documentation governance

The governing docset layer was established in a 2026-05-29 sweep. Key rules:

- **`docs/governance/DOCSET_INDEX.md`** — the reader entry point and precedence list.
  When docs conflict, DOCSET_INDEX.md defines which wins.
- **`docs/governance/DOCSET_ALIGNMENT_AUDIT.md`** — 14 findings from the sweep;
  tracks what still needs fixing.
- **`docs/governance/HIGH_CONFLICT_DOC_RECONCILIATION_PLAN.md`** — ranked list
  of still-unresolved doc conflicts.

Remaining doc tasks before Phase 5 publish:
1. ~~nodus-a2a `pyproject.toml` metadata~~ — DONE (added in breakage gate prep)
2. `RELEASE_CHECKLIST.md` post-release section still has old commands — batch to 4.0.1
3. `LIBRARY_ECOSYSTEM.md` STDLIB_PHILOSOPHY.md cross-refs — stub exists; expand post-launch
4. nodus-a2a #2 (exception str verbatim to client) — add doc note or accept as known gap

nodus-mcp spec version: README says "2026-07-28 RC" (authoritative). Verify CHANGELOG reflects it.

## nodus-memory companion library

⚠️ **LOCAL REPO REPLACED.** The original nodus-lang-integrated memory adapter (Phases A–K,
192 tests, hatchling, `src/` layout, nodus-lang dep) was overwritten at `C:\dev\nodus-memory`
by the Tier 2 full memory library. Original preserved on GitHub.

**Original nodus-lang adapter (on GitHub, NOT at local path):**
- 192 tests, nodus-lang dep, Phases A–K, hatchling build, `src/nodus_memory/` layout
- `MemoryStore`, `MemoryConfig`, `attach_to_runtime(runtime, store)`, `nm_*` host functions
- `import "nodus-memory"` → `share`, `recall_from`, `forget`, `tag`, `link`, `recall_all`
- Skill `/nodus-memory-phase` v0.2 plan targets this architecture

**Current local `C:\dev\nodus-memory` (Tier 2 full library, 28 tests):**
- `MemoryNode`, `InMemoryStore`, MAS `build_path()`/`glob_match()`
- `score_nodes()`, `update_feedback()`, `recall()`/`recall_async()`, `EmbeddingProvider` protocol
- Depends on `nodus-events>=0.1.0`; optional `pgvector` and `openai` extras
- Flat layout (`nodus_memory/`), setuptools build
- Run tests: `cd C:\dev\nodus-memory && python -m pytest -q`

## nodus-native-memory-engine companion library

- Repo: `C:\dev\nodus-native-memory-engine` / `github.com/Masterplanner25/nodus-native-memory-engine`
- **Status: v0.1.0 COMPLETE — prepared, not yet published.**
  PyO3/Maturin Rust extension. 76 tests. Pure-Python fallback for all 9 operations.
  Publication follows nodus-memory.
- **Build requires Rust:** `VIRTUAL_ENV="C:/dev/Coding Language/.venv" maturin develop --release`
  Rust 1.93.1, PyO3 0.22.6, maturin 1.12.6 all installed.
- **9 operations:** `cosine_similarity`, `batch_cosine_similarity`, `compute_weight`,
  `batch_compute_weights`, `argsort_by_weight`, `traverse_chain`, `would_create_cycle`,
  `rank_by_similarity`, `rank_blended`
- `is_native()` → True when Rust extension loaded; falls back to pure Python silently.
- Run tests: `cd C:\dev\nodus-native-memory-engine && "C:/dev/Coding Language/.venv/Scripts/python.exe" -m pytest -q`

## nodus-extension companion library

- Repo: `C:\dev\nodus-extension` / `github.com/Masterplanner25/nodus-extension`
- **Status: v0.1.0 COMPLETE — prepared, not yet published.**
  Phases A–J done. 126 tests, 93% coverage. BYTECODE_VERSION 4, no new opcodes.
  Publication follows nodus-memory.
- **Purpose:** Typed, versioned, sandboxed plugin framework. Third-party developers
  write `nodus-extension.json` + `extension.py`; the framework loads them via subprocess.
- **Python API:** `ExtensionRegistry`, `ExtensionHost`, `attach_to_runtime(runtime, registry)`
- **Nodus bindings:** `import "nodus-extension"` → `ext_load(path)`, `ext_list()`,
  `ext_invoke(name, tool, args_json)`, `ext_describe(name)`
- **Host functions use `_ext_` prefix** (not `ext_`): `_ext_load`, `_ext_list`, etc.
  The .nd wrappers are named `ext_load`, `ext_list` etc. (same split as nodus-memory)
- **ext_invoke takes args as JSON string** — not a Nodus map. Caller must pass e.g.
  `ext_invoke("myext", "tool.name", "{\"key\": \"value\"}")`.
- **Sandbox tier 1 only** (subprocess, insecure-dev). OCI/VM deferred to v0.2.
- **Capability gate:** extension must declare `"tool.invoke"` to call tools.
- Dev install: `pip install -e . --no-deps` (from `C:\dev\nodus-extension`)
- Run tests: `cd C:\dev\nodus-extension && PYTHONPATH="C:/dev/Coding Language/src" "C:/dev/Coding Language/.venv/Scripts/python.exe" -m pytest tests/ -q`

## Standalone package ecosystem (at `C:\dev\`)

All packages have GitHub repos under Masterplanner25. No nodus-lang dependency unless noted.
Test command: `cd C:\dev\<pkg> && python -m pytest -q`.

### Group 1 — AINDY-derived (7 packages)

| Package | Tests | Key deps | Key abstraction |
|---------|-------|----------|----------------|
| nodus-circuit-breaker | 24 | none | Three-state CB, sync+async, optional Prometheus |
| nodus-auth | 36 | python-jose, passlib, **bcrypt<5.0**, pydantic | JWT/API-key/bcrypt; **bcrypt must be <5.0** (passlib 1.7.4 incompatible with 5.x) |
| nodus-observability | 27 | python-json-logger (otel/prometheus optional) | Trace ContextVars, init_otel(), create_registry(), configure_logging() |
| nodus-queue | 53 | tenacity (redis optional) | RedisQueueBackend LPUSH/BRPOP+Lua, DLQ, delayed jobs; Redis tests need live Redis — skip with `--ignore=tests/test_redis_backend.py` |
| nodus-state | 117 | none | FlowStatus/UnitStatus/AgentStatus, WaitCondition, ResumeSpec, ExecutionContext, SessionKey |
| nodus-observability-framework | 57 | nodus-observability, fastapi optional | AIMetrics (8), RequestMetricWriter, middleware, health router, ExecutionBlock streaming, CostAttribution/CostTracker |
| nodus-mcp (aindy bridge) | 81 | mcp>=1.0.0 | ToolDefinition, ToolRegistry, NodusServer, MCPClientAdapter; flat code at `nodus_mcp_aindy/` in C:\dev\nodus-mcp |

### Group 2 — OpenClaw-derived (5 packages)

| Package | Tests | Key deps | Key abstraction |
|---------|-------|----------|----------------|
| nodus-context | 29 | none | ContextBudget, ContextWindow (add/compact/guard_tool_results), DropToolInternalsStrategy, SummarizeStrategy |
| nodus-approvals | 32 | none | ApprovalGate (check/approve/deny/poll), ApprovalPolicy (fnmatch rules), PairingStore (6-digit codes) |
| nodus-channels | 24 | none | ChannelAdapter protocol, ChannelRegistry, HealthMonitor (CONNECTED→DEGRADED→DISCONNECTED) |
| nodus-llm | 24 | nodus-circuit-breaker | CredentialStore, FailoverClient (5m→10m→20m→40m→1h backoff), OpenAI/Anthropic providers |
| nodus-delivery | 27 | nodus-channels | DeliveryPlan, SizeChunker, ParagraphChunker, MarkdownBlockChunker, DeliveryRouter |

### Group 3 — Tier 1: Buildable standalone (7 packages)

| Package | Tests | Key deps | Key abstraction |
|---------|-------|----------|----------------|
| nodus-retry | 33 | none | RetryPolicy (6 named), execute_with_retry sync+async, EffectStore/InMemoryEffectStore, compute_action_id() |
| nodus-http | 13 | httpx, nodus-circuit-breaker | HttpClient (circuit breaker + retry + trace headers), HttpResponse, RetryConfig; **requires `respx` for tests** |
| nodus-events | 17 | redis (optional) | EventBus (Redis pub/sub, source-instance dedup, pre-rehydration buffer), AuditStore, publish_event() |
| nodus-schema | 30 | none | validate_payload(), parse_versioned_name(), resolve_version(), SchemaRegistry, SchemaEntry |
| nodus-protocol | 13 | none | RequestEnvelope, ResponseEnvelope, EventEnvelope, JSON encode()/decode() with _type discriminator |
| nodus-session | 15 | none | SessionEntry (transcript, provenance), InMemorySessionStore, SessionPruningPolicy, SessionManager |
| nodus-router | 18 | none | RouteBinding (fnmatch), RoutingTable (priority-sorted), RouteResolver (default agent fallback) |

### Group 4 — Tier 2: Requires Tier 1 (4 packages + 1 additive)

| Package | Tests | Key deps | Key abstraction |
|---------|-------|----------|----------------|
| nodus-memory | 28 | nodus-events; pgvector/openai optional | MemoryNode, InMemoryStore, MAS build_path()/glob_match(), score_nodes(), update_feedback(), recall()/recall_async(), EmbeddingProvider |
| nodus-workflow | 17 | nodus-state, nodus-events | FlowDefinition/FlowNode/FlowEdge, FlowStatus/FlowRun, SchedulerEngine (priority queue + WAIT/RESUME), FlowExecutor, FlowRehydrator |
| nodus-a2a | 23 | none | AgentRegistry, AgentCoordinator (local/delegate), DelegationRequest, DeadLetterService, StuckRunWatchdog |
| nodus-adapters/base | 11 | nodus-channels | BaseChannelAdapter (reconnect backoff, health recording), ConnectionManager; path: `C:\dev\nodus-adapters\base` |

### Group 5 — Tier 3: Requires T1+T2 (2 packages)

| Package | Tests | Key deps | Key abstraction |
|---------|-------|----------|----------------|
| nodus-agent | 28 | nodus-state, nodus-retry | AgentRun, CapabilityToken (HMAC-SHA256), mint_token()/validate_token(), LocalPlanner/LLMPlanner, DuplicateSubmissionGuard, AgentExecutor |
| nodus-gateway | 19 | nodus-protocol, websockets | GatewayServer (WebSocket + handler dispatch + idempotency cache), GatewayClient, HandlerRegistry, EventBroadcaster; **requires nodus-protocol installed** |

### Group 6 — Tier 4: Requires All (2 packages)

| Package | Tests | Key deps | Key abstraction |
|---------|-------|----------|----------------|
| nodus-extensions | 35 | none | ExtensionManifest (ABI versioning), HookRunner (phase hooks), SubprocessSandboxRunner/OciSandboxRunner, ExtensionRegistry (disk discovery); **asyncio.run() not get_event_loop()** |
| nodus-governance | 28 | none | OperatorScope/ScopeBundle (PERM_* constants), PolicyBundle, TrustSurface (deny-by-default allowlist/blocklist), AuditTrail (append-only, multi-field query) |

### Repo alignment status (2026-05-31)

All 29 standalone packages have been aligned to a standard repo structure:
README, CHANGELOG, LICENSE, CONTRIBUTING, SECURITY, correct `.gitignore`,
correct `pyproject.toml` (URLs, testpaths, dev extra). All have GitHub repos
under Masterplanner25. Do not assume new packages are aligned — run a survey
before working on any new standalone package.

### Dependency audit findings (critical pattern)

During the repo alignment sweep, **many packages declared required deps that
had zero runtime imports.** The pattern: dep was imported via `TYPE_CHECKING`,
`try/except ImportError`, or injected as a constructor parameter — all meaning
the package works without it. Fixed packages and what was removed:

| Package | Wrong deps removed |
|---|---|
| nodus-agent | nodus-llm, nodus-memory, nodus-events, nodus-retry, nodus-state, nodus-mcp, nodus-a2a, nodus-approvals (all 8) |
| nodus-extensions | nodus-schema, nodus-observability (both) |
| nodus-gateway | nodus-protocol, nodus-session, nodus-router, nodus-channels, nodus-agent, nodus-events (6 of 7; websockets → optional) |
| nodus-governance | nodus-auth, nodus-approvals, nodus-events (all 3) |
| nodus-llm | nodus-circuit-breaker (TYPE_CHECKING only) |
| nodus-memory | nodus-events (Tier 2 has no external imports) |
| nodus-observability | python-json-logger (try/except ImportError fallback) |
| nodus-router | nodus-session (try/except ImportError fallback) |
| nodus-workflow | nodus-events, nodus-queue, nodus-retry, nodus-state (all 4) |

**Rule:** Before adding a dep, check that it has a module-level unconditional
import with no fallback. `TYPE_CHECKING`, `try/except ImportError`, and
constructor injection all mean optional.

### `.nodus/` cache in standalone packages

When nodus-lang tests run inside a standalone package directory, nodus may
write a `.nodus/` cache directory (bytecode cache, graph state). This has been
added to `.gitignore` in all repos but watch for it in new packages — it can
contain hundreds of files that should never be committed.

### Ecosystem dependency notes

- **nodus-gateway** requires `nodus-protocol` installed before tests run
- **nodus-http** requires `respx` for tests (`pip install respx`)
- **nodus-delivery** requires `nodus-channels`; **nodus-llm** accepts any `.chat()` client (protocol-based)
- **nodus-memory** (Tier 2) is pure stdlib — does NOT require nodus-events
- **nodus-a2a** (Tier 2) is the AgentCoordinator layer (pure stdlib) — NOT the A2A wire protocol adapter
- **nodus-extensions** test fix: use `asyncio.run()` not `asyncio.get_event_loop().run_until_complete()` (Python 3.11+)
- nodus-queue redis tests need a live Redis server — always run with `--ignore=tests/test_redis_backend.py` in dev
- **nodus-mcp** test_phase_m.py has 2 port-conflict-sensitive tests — they pass individually but fail in full suite runs (pre-existing race condition, not a code bug)

### Dual-implementation names (same name, different scope)

Two pairs of packages share names but are NOT the same package:

| Name | In-tree (src/nodus_X/) | Standalone (C:\dev\nodus-X) |
|------|----------------------|---------------------------|
| **nodus_schema** | `src/nodus_schema/` — runtime ABI contracts for syscalls and extension surfaces; used by nodus-lang internally | `C:\dev\nodus-schema` — general schema validation library (SchemaRegistry, parse_versioned_name); standalone |
| **nodus_workflow** | `src/nodus_workflow/` — full workflow orchestration layer wired into the nodus-lang server (HTTP/CLI surfaces, 7-state lifecycle, SQLite store) | `C:\dev\nodus-workflow` — standalone workflow primitives (FlowDefinition, SchedulerEngine); lighter, no server wiring |

Importing `nodus_schema` or `nodus_workflow` in a Python script may find either version depending on install order. Always check `import nodus_schema; print(nodus_schema.__file__)` before working on these.

## Ecosystem incubators (`packages/` in this repo)

Eight Python-first scaffold packages live at `C:\dev\Coding Language\packages\`.
They are **design references / API contracts**, not production implementations.

- `nodus-a2a-spec`, `nodus-agent`, `nodus-event`, `nodus-events`, `nodus-http`,
  `nodus-memory-spec`, `nodus-retry`
- **`nodus-store-sql` has been promoted** — no longer an incubator scaffold;
  production package at `C:\dev\nodus-store-sql` (47 tests, sync+async)
- **Never pip-install the `-spec` packages alongside the production packages** —
  `nodus-memory-spec` and `nodus-a2a-spec` share Python module names with the
  production packages in `C:\dev\`. Installing both in the same venv causes import conflicts.
- Run incubator tests from within each package directory:
  ```powershell
  cd "C:\dev\Coding Language\packages\nodus-memory" && python -m pytest -q
  ```
  The `pythonpath = ["src"]` in each package's pytest config provides the import path.
- Spec docs live at `docs/ecosystem/` (NODUS_HTTP.md, NODUS_RETRY.md, etc.)

## nodus-workflow (in-tree framework)

- **Location:** `src/nodus_workflow/` (in this repo, not a separate package yet)
- **Status:** Near-runtime-complete. Core semantics complete; production hardening
  and packaging documented in `plans/nodus-workflow-framework.md`.
- **Test file:** `tests/test_nodus_workflow_framework.py` (30 tests)
- **7 run states:** `pending → running → waiting → retry_scheduled → completed / failed / dead_lettered`
- **Backends:** `LocalWorkflowStore` (file-backed) and `SQLiteWorkflowStore` (cross-process)
- **VM builtins added:** `workflow_wait(event_type, ...)`, `resume_workflow(id, checkpoint, payload)`,
  `workflow_resume_payload()` — delegate to `get_default_workflow_runner()`
- **CLI:** `nodus workflow runs|inspect|dead-letters|replay|migrate-state`
- **HTTP:** `GET /workflow/runs`, `GET /workflow/runs/{id}`, `GET /workflow/dead-letters`, `POST /workflow/replay`
- **Server flags:** `--workflow-store-backend {local|sqlite}`, `--workflow-store-path PATH`

**Operational gotcha — local store scan performance:**
The `LocalWorkflowStore` scans all `.nodus/workflow_framework/runs/*.json` on every sweep.
670+ accumulated files cause >2s per sweep, breaking the `test_worker_death_detected_by_sweeper`
test (500ms deadline). Fix: use SQLite temp store in tests, OR clean `.nodus/workflow_framework/runs/`
(safe — test artifacts only).

**Circular import:** `nodus.vm.vm` imports `get_default_workflow_runner` from `nodus_workflow.runner`
at top level. Works at runtime (nodus initializes first) but fails if `nodus_workflow` is imported
before `nodus` in a fresh process.

## nodus_schema (in-tree package)

- **Location:** `src/nodus_schema/` (in this repo, not a separate package yet)
- **Exports:** `SyscallSpec`, `parse_syscall_name()`, `resolve_version()`,
  `validate_input()`, `validate_output()`, `validate_payload()`, extension ABI models.

## nodus-sdk companion package

- Repo: `C:\dev\nodus-sdk` / `github.com/Masterplanner25/nodus-sdk`
- **Status: v0.1.0 COMPLETE — prepared, not yet published.**
  99 tests. Unified platform SDK auto-wiring the 27-package ecosystem.
- **Install:** `pip install nodus-sdk[agent,sql,fastapi]` (extras-based)
- **Key exports:** `NodusSDKRuntime`, `create_runtime(**kwargs)`, `detect_available()`
- **9 bridges:** redis, http, llm, observability (wrappers), sql, vector, scheduler, webhook, api (new)
- **Bridge return type:** host functions return maps not Records — `.nd` must use `r["key"]` not `r.key`
- **FastAPI bridge:** `create_nodus_router(rt)` → POST /run, GET /health, GET /syscalls, memory CRUD
- **NodusTraceMiddleware:** reads X-Trace-ID header → `runtime.set_trace_id()`
- Run tests: `cd C:\dev\nodus-sdk && PYTHONPATH="C:/dev/Coding Language/src" python -m pytest -q`

## nodus-store-sql companion package

- Repo: `C:\dev\nodus-store-sql` / `github.com/Masterplanner25/nodus-store-sql`
- **Status: v0.1.0 COMPLETE — prepared, not yet published.**
  47 tests (31 sync + 16 async). Promoted from `packages/nodus-store-sql` incubator scaffold.
- **Three stores:** `RunStore` (optimistic locking), `EventStore` (append-only), `JobStore` (atomic claiming)
- **Async:** `AsyncSqlStore` via `sqlalchemy.ext.asyncio`; test with `sqlite+aiosqlite:///:memory:`
- **Tables:** `nodus_runs`, `nodus_events`, `nodus_jobs`
- **No Alembic:** `create_all()` is the dev schema bootstrap; production manages migrations independently
- Run tests: `cd C:\dev\nodus-store-sql && python -m pytest -q`

## SemVer policy — version only increments on PyPI publication

The version number in `src/nodus/support/version.py` and `pyproject.toml` is **4.0.0**.
It stays at 4.0.0 until the package is actually published to PyPI.

All additions made after the original v4.0.0 scope (Phase 6 AI-native primitives,
Phase A-D HandlerContract, nodus-sdk, nodus-store-sql, repo alignment sweep) are part
of the **v4.0.0 pre-release cycle** — not a new minor version. Do not bump to 4.1.0
unless 4.0.0 has shipped. The last published release is **v3.0.2**.

Both `version.py` and `pyproject.toml` must stay in sync at all times (Version sync
section above). If you ever see them at 4.1.0, revert to 4.0.0.

## Embedding API — known blockers and operational traps

These were identified by a raw-path readiness probe and are filed as GitHub issues.
Full analysis: `C:\dev\nodus-mcp\docs\design\06-embedding-runtime-blockers.md`.
All entries are also in `docs/governance/TECH_DEBT.md`.

**EMBED-001 (#97) — The 200ms default trap (hits every first-time embedder):**
`NodusRuntime()` with NO arguments applies a **200ms wall-clock deadline** — the same
as `nodus run`. Any coroutine sleeping cumulatively more than 200ms (workflows, async
loops, MCP/A2A request handlers) will be killed silently.

```python
# WRONG for any long-lived use:
rt = NodusRuntime()

# CORRECT for servers, MCP hosts, workflow engines, anything with sleep:
rt = NodusRuntime(timeout_ms=None, max_steps=None)
```

**EMBED-002 (#98, open) — No `on_error` hook:**
`NodusRuntime` does not expose `Scheduler.run_loop`'s `on_error` parameter. After
`run_source()` returns, a coroutine that died from an error and one that completed
normally are indistinguishable (`state="finished"`, `last_result=None` for both).
Workaround: require handlers to catch their own errors and write structured error
records to a result channel (in-Nodus catch pattern).

**EMBED-003 (#99, open) — `subprocess_spawn` thread leak:**
Two daemon pump threads are created per `subprocess_spawn`. If `run_loop` exits
before the subprocess terminates (output channel never consumed), threads accumulate.
They're daemon threads so they don't block exit, but they pile up per session.
No `NodusRuntime.shutdown()` exists — `reset()` only clears `last_vm`.

**EMBED-004 (#100, open) — `*_async` builtins are fully serial:**
`http_get_async`, `subprocess_run_async` etc. block the GIL. Five concurrent 200ms
HTTP calls take ~1s total, not 200ms. The genuine concurrency path is `subprocess_spawn`
+ channel reads via `_io_channels` daemon threads — not `*_async` builtins.

**CHAN-001 (open) — silent coroutine orphan on empty `recv()`:**
A coroutine blocked on `recv()` of an empty channel is silently stranded — `run_loop`
exits when it sees no pending work. The only workaround is:
(a) pre-populate the channel before `run_loop`, or
(b) use the subprocess-pipe pattern (daemon thread feeds `ch.queue` continuously).
The `_io_channels` workaround requires touching a private scheduler attribute and has
a close-ordering race. Do not use it directly.

## Phase 5/6 publish status (as of 2026-05-31)

nodus-lang is at **4.0.0** (not yet published; pre-release additions implemented
beyond original scope). Last published PyPI release: **v3.0.2**.

**Current test count:** 1,612 passing (nodus-lang), 2 pre-existing failures
(`test_resume_goal` — KeyError 'goal', pre-Phase-3 regression;
`test_worker_death_detection` — timing-sensitive sweeper test).

**Wheels to rebuild before publish:** nodus-lang 4.0.0 wheel must be rebuilt
(Phase 6 + Phase A-D changes since the 4.0.0 wheel). nodus-mcp wheel remains
valid (no code changes). All other packages need initial wheels.

**Publish sequence** (do NOT run until explicitly asked):

Round 1 — Zero-dep standalone packages (publish first; no install-order risk):
```
nodus-circuit-breaker 0.1.0   nodus-retry 0.1.0 ← MUST be before nodus-lang!
nodus-channels 0.1.0           nodus-protocol 0.1.0
nodus-schema (standalone) 0.1.0  nodus-approvals 0.1.0
nodus-context 0.1.0            nodus-state 0.1.0
nodus-session 0.1.0            nodus-governance 0.1.0
nodus-agent 0.1.0              nodus-workflow (standalone) 0.1.0
nodus-a2a (AgentCoordinator) 0.1.0  nodus-extensions 0.1.0
nodus-store-sql 0.1.0
```

Round 2 — Packages with external-only deps (PyPI already has them):
```
nodus-auth 0.1.0        (python-jose, passlib, bcrypt, pydantic)
nodus-observability 0.1.0   (python-json-logger optional)
nodus-queue 0.1.0       (tenacity; redis optional)
nodus-events 0.1.0      (redis optional)
nodus-router 0.1.0      (nodus-session optional)
nodus-delivery 0.1.0    (nodus-channels)
nodus-http 0.1.0        (httpx)
nodus-llm 0.1.0         (openai/anthropic optional)
nodus-adapters-base 0.1.0  (nodus-channels)
nodus-gateway 0.1.0     (websockets optional)
nodus-observability-framework 0.1.0  (nodus-observability)
```

Round 3 — nodus-lang itself (after nodus-retry is on PyPI):
```
1. git tag v4.0.0 && git push origin main --tags
2. python -m build   (from C:\dev\Coding Language)
3. Upload nodus-lang 4.0.0 to real PyPI (token from user at upload time)
4. Confirm: pip install nodus-lang==4.0.0
```

Round 4 — nodus-lang companion packages (require nodus-lang on PyPI):
```
nodus-extension 0.1.0      (nodus-lang, pydantic)
nodus-memory 0.1.0         (nodus-lang adapter — original, on GitHub)
nodus-mcp 0.1.0            (nodus-lang, httpx — separate repo, own PyPI token)
nodus-native-memory-engine 0.1.0   (PyO3/Maturin wheel, no nodus-lang dep)
```

Round 5 — SDK and high-level packages:
```
nodus-sdk 0.1.0   (nodus-lang, nodus-schema, nodus-protocol, nodus-retry)
```

After all packages are up:
- Create GitHub releases for all published packages
- Update ECOSYSTEM_READINESS_ASSESSMENT.md to reflect published status
- Verify: pip install nodus-sdk[full] pulls in the full ecosystem cleanly

**PyPI token note:** Each package in a separate repo (nodus-mcp, nodus-extension,
nodus-memory, nodus-native-memory-engine) needs its own project-specific PyPI token.
nodus-lang packages use the main nodus-lang token. Retrieve from user at upload time —
never store tokens in any file.
