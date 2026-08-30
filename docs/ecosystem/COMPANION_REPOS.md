# Companion repositories — working notes

Per-repo detail for the first-party companions: where the checkout is, how to run
its tests, and the gotchas that have cost time. Extracted from `CLAUDE.md`, which
keeps only the index and the traps you can hit without opening this file.

**Published versions are deliberately not listed here.** They went stale every
cycle when they were. Two scripts read them live:

```powershell
# published version of each companion, and whether its checkout has drifted from it
PYTHONPATH="C:/dev/Coding Language/src;C:/dev/Coding Language" `
  "C:/dev/Coding Language/.venv/Scripts/python.exe" -m tools.check_publish_drift

# does each companion's declared range still admit the current nodus-lang?
PYTHONPATH="C:/dev/Coding Language/src;C:/dev/Coding Language" `
  "C:/dev/Coding Language/.venv/Scripts/python.exe" -m tools.check_downstream_constraints
```

For what exists at all and in what tier, see [`README.md`](./README.md) — which is
also the list the PyPI project count is re-derived from.

---

## nodus-mcp

`C:\dev\nodus-mcp` · `github.com/Masterplanner25/nodus-mcp` · on PyPI

MCP protocol library. `nodus-lang` cap is floated. BYTECODE_VERSION 4, no new
opcodes.

**Dual layout.** `src/nodus_mcp/` is the full MCP protocol library (Phases A–N);
`nodus_mcp_aindy/` is the aindy-derived bridge adapter wrapping `ToolRegistry` as
an MCP server. `pyproject.toml`'s `where = ["src"]` installs the Phase A–N
library; the aindy adapter is importable as `nodus_mcp_aindy` but is not the
primary package.

```powershell
pip install -e . --no-deps
cd C:\dev\nodus-mcp
PYTHONPATH="C:/dev/Coding Language/src" "C:/dev/Coding Language/.venv/Scripts/python.exe" -m pytest tests/ -q
```

**egg-info pitfall.** If `nodus_mcp.egg-info/` appears in the repo root (left by
old `setup.py develop` runs), pytest adds the rootdir to `sys.path` and
`importlib.metadata` finds the stale egg-info instead of the site-packages
dist-info, breaking entry-point discovery. Fix:
`rm -rf nodus_mcp.egg-info && pip install -e . --no-deps`. It is gitignored.

**`test_phase_m.py` holds two port-binding tests** that pass individually and can
fail in a loaded full-suite run. This is a recorded flake in
`tools/dependent_flakes.json` — which *classifies* a red run and never passes one.

Entry-point contract: `[project.entry-points."nodus.nd"]` → callable returning the
absolute path to the `.nd` root dir. See `docs/guide/library-entry-points.md`.
Key contracts: TD-007–010 in `docs/governance/TECH_DEBT.md`.

---

## nodus-a2a — and the two `C:\codev` directories

`C:\dev\nodus-a2a` · `github.com/Masterplanner25/nodus-a2a` · on PyPI

The local checkout is the **Tier 2 AgentCoordinator** (23 tests, no nodus-lang
dependency): `AgentRegistry`, `AgentCoordinator` (local/delegate mode),
`DelegationRequest`, `DeadLetterService`, `StuckRunWatchdog`. This is what is on
PyPI and the only one `check_publish_drift` tracks.

### The wire adapter is a different package

The original A2A **wire-protocol** adapter (`A2AHttpServer`, transport layer,
nodus-lang dep) is **188 tests** and is a CrewAI-showcase spin-off, not a
maintained companion. Published 2026-08-26 as **`nodus-a2a-wire` 0.1.0** (#477),
module `nodus_a2a_wire`, no runtime dependencies.

**There are two `C:\codev` directories and they are not interchangeable. The one
named `nodus-a2a-wire` is the one that is *not* the wire repo.**

| Directory | Remote | Branch | What it actually is |
|---|---|---|---|
| `C:\codev\nodus-a2a-wire` | **`nodus-a2a`** | detached at `10746ce` | a worktree of the *coordinator* repo's old history — pulls and pushes go to the wrong project |
| `C:\codev\a2a-wire-pub` | **`nodus-a2a-wire`** | `main` | the one that corresponds to `github.com/Masterplanner25/nodus-a2a-wire` |

Use **`a2a-wire-pub`** for anything touching that GitHub repo.

### Three things the publish needed, and the middle one is the lesson

- `name = "nodus-a2a"` → `nodus-a2a-wire`; the distribution name was taken.
- **The Python module was `nodus_a2a` — the same module the published coordinator
  ships.** Renaming the distribution alone would have left both writing one
  directory into site-packages. Measured: installing the wire adapter over the
  coordinator left `AgentCoordinator`, `AgentRegistry` and `DeadLetterService`
  **gone**, with pip reporting success both times. This is NAME-COL-001 again —
  the distribution name is what a user types, the module name is what Python
  resolves, and fixing one does not fix the other.
- **`nodus-lang` was declared and never imported.** `grep -rnE "^\s*(from|import)\s+nodus" src/`
  was empty; the one test import sat in a `try/except ImportError` that skips. Per
  the dependency-audit rule that is not a dependency — it is a `dev` extra now.

**`twine` 6.2.0 rejects hatchling's `Metadata-Version: 2.5`** as invalid. Upgrade
to 7.0.0; it looks like a broken package and is a stale validator.

---

## nodus-memory

`C:\dev\nodus-memory` · `github.com/Masterplanner25/nodus-memory` · on PyPI

The local checkout is the **Tier 2 full library** (28 tests): `MemoryNode`,
`InMemoryStore`, MAS `build_path()`/`glob_match()`, `score_nodes()`,
`update_feedback()`, `recall()`/`recall_async()`, `EmbeddingProvider` protocol. No
runtime dependencies; optional `pgvector` and `openai` extras. Flat layout
(`nodus_memory/`), setuptools build.

```powershell
cd C:\dev\nodus-memory && python -m pytest -q
```

**The nodus-lang adapter exists in git history only.** The 192-test version with
`attach_to_runtime`, `nm_*` host functions and `import "nodus-memory"` was deleted
from the tree by `6d3a241`. It is **not** on PyPI and **not** the current tree on
GitHub — recover it with:

```powershell
git show f02ab1e:src/nodus_memory/nodus_bindings.py
```

or give it its own repo the way `nodus-a2a-wire` got one.

---

## nodus-native-memory-engine

`C:\dev\nodus-native-memory-engine` · on PyPI

PyO3/Maturin Rust extension with a pure-Python fallback for every operation.
`is_native()` is True when the Rust extension loaded. Auto-wired into
nodus-memory.

```powershell
# build (Rust 1.93.1, PyO3 0.22.6, maturin 1.12.6 all installed)
VIRTUAL_ENV="C:/dev/Coding Language/.venv" maturin develop --release

cd C:\dev\nodus-native-memory-engine
"C:/dev/Coding Language/.venv/Scripts/python.exe" -m pytest -q
```

---

## nodus-extension

`C:\dev\nodus-extension` · on PyPI · BYTECODE_VERSION 4, no new opcodes

Typed, versioned, sandboxed plugin framework. Third-party developers write
`nodus-extension.json` + `extension.py`; the framework loads them via subprocess.

- **Python API:** `ExtensionRegistry`, `ExtensionHost`, `attach_to_runtime(runtime, registry)`
- **Nodus bindings:** `import "nodus-extension"` → `ext_load(path)`, `ext_list()`,
  `ext_invoke(name, tool, args_json)`, `ext_describe(name)`
- **Host functions use an `_ext_` prefix** (`_ext_load`, …); the `.nd` wrappers are
  `ext_load` etc. Same split as nodus-memory.
- **`ext_invoke` takes args as a JSON string**, not a Nodus map —
  `ext_invoke("myext", "tool.name", "{\"key\": \"value\"}")`.
- **Sandbox tier 1 only** (subprocess, insecure-dev). OCI/VM deferred to v0.2.
- **Capability gate:** an extension must declare `"tool.invoke"` to call tools.

```powershell
pip install -e . --no-deps
cd C:\dev\nodus-extension
PYTHONPATH="C:/dev/Coding Language/src" "C:/dev/Coding Language/.venv/Scripts/python.exe" -m pytest tests/ -q
```

---

## nodus-sdk

`C:\dev\nodus-sdk` · on PyPI · 99 tests

Unified platform SDK auto-wiring the companion ecosystem.
`pip install nodus-sdk[agent,sql,fastapi]`.

- **Key exports:** `NodusSDKRuntime`, `create_runtime(**kwargs)`, `detect_available()`
- **9 bridges:** redis, http, llm, observability (wrappers), sql, vector,
  scheduler, webhook, api
- **Bridge return type: host functions return maps, not Records** — `.nd` must use
  `r["key"]`, never `r.key`
- **FastAPI bridge:** `create_nodus_router(rt)` → `POST /run`, `GET /health`,
  `GET /syscalls`, memory CRUD
- **`NodusTraceMiddleware`** reads the `X-Trace-ID` header → `runtime.set_trace_id()`

```powershell
cd C:\dev\nodus-sdk && PYTHONPATH="C:/dev/Coding Language/src" python -m pytest -q
```

Its `test_version_string` asserted `0.1.0` from 2026-07-12 until 0.1.2, so the
suite shipped one guaranteed failure for a month and the v5.0.0 Stage 6 sweep
recorded it as a known-stale test rather than fixing it.

---

## nodus-store-sql

`C:\dev\nodus-store-sql` (branch `master`) · on PyPI · 47 tests (31 sync + 16 async)

Promoted from the `packages/nodus-store-sql` incubator scaffold.

- **Three stores:** `RunStore` (optimistic locking), `EventStore` (append-only),
  `JobStore` (atomic claiming)
- **Async:** `AsyncSqlStore` via `sqlalchemy.ext.asyncio`; test with
  `sqlite+aiosqlite:///:memory:`
- **Tables:** `nodus_runs`, `nodus_events`, `nodus_jobs`
- **No Alembic:** `create_all()` is the dev schema bootstrap; production manages
  migrations independently

**Async tests need `aiosqlite`**, which is not installed by default —
`pip install aiosqlite` if they fail with `ModuleNotFoundError`.

---

## nodus-workflow-ai

`C:\dev\nodus-workflow-ai` · on PyPI since 2026-08-30 (#93) · 28 tests

#93's bridge: a generated plan validated before it runs, under a grant narrowed to
what it declared. Floor `nodus-lang>=5.8.0`, because per-step results keyed by a
declared name (#679) shipped there.

Deliberately **not** a planner (`nodus-agent` has two), **not** an executor
(`run_graph` is), and **not** a loop (`goal … over … until` is). Two things carry
the weight: `validate_plan` checks the whole plan **before any step runs**, and the
narrowed grant means a plan runs under the tools it *declared*, not the host's
ambient policy.

It was the first companion registered in `check_downstream_constraints.py`'s
`UNPUBLISHED_COMPANIONS` with a floor naming a version that did not exist yet.

Design record: `docs/design/v5/07-generated-plans.md`.

---

## nodus-flow

`C:\dev
odus-workflow` (directory not renamed) · `github.com/Masterplanner25/nodus-flow` · on PyPI

**Published as `nodus-workflow` until 0.2.0** (#483). Renamed because the name read
as *the engine behind the `workflow` keyword*, which it is not — it is a set of
lightweight workflow primitives (`FlowDefinition`, `SchedulerEngine`, no server
wiring). The in-tree `src/nodus_lang_workflow/` is the orchestration framework
wired into the nodus-lang server; the two are different scope and different code.

`COMPANION_LIBRARY_CONTRACT.md` §8b forbids naming a package after a construct it
does not implement, which is the rule this rename established. The old PyPI name
remains a working deprecation alias.

It had also sat outside the drift sweep under **both** names — a published
first-party package nothing was checking. `check_publish_drift.py` carries a
comment about it, and the same miss recurred at 5.8.0 with `nodus-a2a-wire` and
`nodus-workflow-ai` missing from `README.md`'s package list.

---

## nodus-jupyter

`C:\dev\nodus-jupyter` (branch `master`) · on PyPI

Jupyter kernel for `.nd` files; works in JupyterLab, Jupyter Notebook and VS Code
notebooks.

```powershell
pip install nodus-jupyter && python -m nodus_jupyter install
```

32 unit tests, which require `ipykernel` installed.

---

## nodus-mcp-server

`C:\dev\nodus-mcp-server` · on PyPI · `pipx install nodus-mcp-server`

Standalone MCP tool server. **6 tools:** `nodus_run_goal`, `nodus_run_workflow`,
`nodus_resume_workflow`, `nodus_store_memory`, `nodus_recall`, `nodus_list_graphs`.

**Two transports:**

- **Claude Desktop (stdio):** add to `claude_desktop_config.json` under `mcpServers`
- **ChatGPT Desktop (HTTP/SSE):** `nodus-mcp-server --http --port 8765`, tunnelled
  via ngrok

**HTTP transport uses `StreamableHTTPSessionManager`** (MCP SDK 1.28.0), single
endpoint `POST /mcp`. The old `SseServerTransport` (two-endpoint SSE) is **broken
— do not use it.**

- **ngrok static domain:** `nodusmcpserver.ngrok.io` (paid plan). ChatGPT Desktop
  requires public HTTPS; the server runs plain HTTP and ngrok terminates SSL.
  Point ChatGPT at `https://nodusmcpserver.ngrok.io/mcp`.
- **Windows auto-startup:** `HKCU:\Software\Microsoft\Windows\CurrentVersion\Run`
  runs `C:\Users\shawn\.nodus-mcp-server\startup.ps1` at login (no admin needed);
  starts the server plus ngrok.
- **Shared memory:** Claude Desktop and ChatGPT Desktop read/write the same SQLite
  DB at `~/.nodus-mcp-server/data/memory.db`, so memory written in one is readable
  by the other.

**`goal` vs `workflow` naming:** `goal` is outcome-oriented and single-shot (steps
are implementation details); `workflow` is process-oriented and resumable (the
pipeline itself is the point, and it returns a `graph_id`). Since #409 a goal is a
workflow *plus a predicate and a budget* — see the `goal … over …` form — which is
a real distinction rather than a naming one. Retry behaviour was unified across
both kinds in #392/#393; the decision lives in `_retry_is_swept()` and must not be
reintroduced anywhere else.

```powershell
cd C:\dev\nodus-mcp-server && python -m pytest -q
```

---

## nodus-vscode (VS Code Marketplace — not PyPI)

`C:\dev\nodus-vscode` · publisher `MasterplanInfiniteWeave`

The published version is recorded in `tools/consumers.json`, **not** in prose —
that line sat a version behind for a full cycle when it was written down here.

**It must be republished when the keyword set changes.** `nodus_gate --consumers`
fingerprints the keywords in this tree and flags the extension when they move.
This extension is not on PyPI, so the Stage 6 content-hash sweep structurally
cannot see it.

- **Phase 1:** TextMate grammar, 23 snippets, bracket/fold config
- **Phase 2:** diagnostics via `nodus check` (fallback; skipped once LSP starts)
- **Phase 3:** Run File (`Ctrl+Alt+N`), Format File, DAP debugger (`Ctrl+Alt+D`, `nodus dap`)
- **Phase 4:** LSP via `nodus lsp` — hover docs, go-to-definition, completions

**Build:** `cd C:\dev\nodus-vscode && npm run package` (needs `@vscode/vsce`).

### Publishing — the update path is not the first-publish path

`package.json` `publisher` must be `MasterplanInfiniteWeave`, and bump `version`
before packaging.

- **Updating an existing extension** (the normal case): go to
  <https://marketplace.visualstudio.com/manage/publishers/MasterplanInfiniteWeave>,
  find **Nodus Language**, use the row's **`…` menu → Update**, upload the new
  `.vsix`. Validation takes ~4 minutes, and a gallery-API check immediately after
  upload still reports the previous version — that is not a failure.
- **First publish only:** `+ New extension` → `Visual Studio Code`. Using this for
  an update is wrong; the extension already exists.
- **Or by CLI:** `npx vsce publish -p <PAT>` (`vsce` is already in
  `node_modules`). The PAT is an Azure DevOps token with **Marketplace → Manage**
  scope and organization set to **All accessible organizations** — scoping it to a
  single org is the failure that looks like a bad token.

**Verify a publish** without a browser: POST to
`https://marketplace.visualstudio.com/_apis/public/gallery/extensionquery`,
`filterType 7` = extension name, value `MasterplanInfiniteWeave.nodus-lang`;
latest is `versions[0]`.

**Key settings:** `nodus.executablePath` (default `nodus`), `nodus.lspCommand`
(array; useful for dev source:
`["C:/dev/Coding Language/.venv/Scripts/python.exe", "C:/dev/Coding Language/nodus.py", "lsp"]`).

**LSP note:** VS Code spawns the **installed** `nodus.exe`, not dev source, so LSP
server changes need a new nodus-lang release to take effect in the extension.

---

## nodus-run-action (GitHub Action — not PyPI)

`C:\dev\nodus-run-action` · `uses: Masterplanner25/nodus-run-action@v1`

Published version is in `tools/consumers.json`. **Three modes:** `file` (run a
`.nd` script), `test-path` (run a test suite), `fmt-check` (format gate).

**Its README pins a `nodus-lang` version, and that pin is what new users copy**, so
it goes stale at every release and hands them an old runtime. Invisible to the
Stage 6 content-hash sweep because it is not on PyPI — `nodus_gate --consumers` is
what catches it, and has.

Republishing means: update the pins, tag, **and move the floating `v1` tag**.
Verify against the remote, since `rev-parse` on an annotated tag returns the tag
object rather than the commit:

```powershell
git ls-remote origin 'refs/tags/v1*'
```

No local test suite — tests run in CI via the action itself.

---

## PyPI tokens

Each package in a separate repo needs its own project-scoped token **or** the
account-scoped token in `~/.pypirc`, which also creates a *new* project on first
upload — no pre-creation step is required (established publishing
`nodus-workflow-ai`). Retrieve from the user at upload time; **never store a token
in any file in any repo.**

Rate limits apply to **new project creation** (~a few per hour), not to version
uploads on existing projects.
