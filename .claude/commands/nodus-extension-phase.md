Start or continue a nodus-extension Phase 0 decisions doc, Phase 1 design doc, or
Phase A-Z implementation phase. Walks through the phase in order, checking
existing design docs before writing or implementing anything.

Arguments: $ARGUMENTS
(Pass "phase0" for v0.2 decisions, "phase1" for next design doc,
or a phase letter like "A", "B" to implement that phase. If omitted,
determine from context.)

## Repository

- Path: `C:\dev\nodus-extension`
- GitHub: `github.com/Masterplanner25/nodus-extension`
- Package: `nodus_extension` (src layout, hatchling)
- Python: `>=3.11`, shared venv at `C:\dev\Coding Language\.venv`
- Key dep: `pydantic>=2.0` (for manifest validation)

## Pre-flight checks

Before any work:

1. Read `C:\dev\nodus-extension\docs\design\00-decisions.md` — confirm D1-D10 are settled.
2. Read all design docs in `C:\dev\nodus-extension\docs\design\`:
   - `01-manifest.md` — manifest format, ABI surface versioning
   - `02-capabilities.md` — capability gates
   - `03-sandbox.md` — subprocess IPC, NDJSON protocol
   - `04-registry.md` — ExtensionRegistry
   - `05-bindings.md` — Nodus language bindings, _ext_* prefix
   - `06-deferred.md` — v0.2 planning seed
3. Run tests to confirm baseline is green:
   ```powershell
   cd C:\dev\nodus-extension
   PYTHONPATH="C:/dev/Coding Language/src" "C:/dev/Coding Language/.venv/Scripts/python.exe" -m pytest tests/ -q
   ```
   Expected: 126 passed (v0.1.0 baseline).

## v0.1.0 completed phases (do not re-implement)

- A — Package skeleton, error hierarchy (8 types), nodus.nd entry-point
- B — ExtensionManifest + ToolSurface (Pydantic), Provenance (origin/trust/owner)
- C — Capability enum (7 caps), CapabilityGate allowlist enforcement
- D — SandboxRunner ABC, SubprocessRunner (tier 1), worker.py NDJSON IPC
- E — ExtensionHost (load/unload, capability gate wiring, describe)
- F — ExtensionRegistry (multi-extension manager)
- G — tool_registry bridge: tool/v1alpha1 surfaces → NodusRuntime.tool_registry
- H — Nodus language bindings: attach_to_runtime, _ext_* host functions, index.nd
- I — CLI (python -m nodus_extension)
- J — Invariants + integration + packaging

## v0.2 deferred features (from 06-deferred.md)

| DD | Feature | Complexity | Blocker |
|----|---------|-----------|---------|
| DD-1 | OCI container sandbox (DockerRunner) | Medium | Docker installed; adds `[docker]` extra |
| DD-2 | VM strong-sandbox (Firecracker/gVisor) | High | External infra; deferred until demand |
| DD-3 | Additional ABI surfaces (node, webhook, flow, planner_backend) | High | Blocked on nodus-workflow + agent framework |
| DD-4 | Trust enforcement (CapabilityPolicy) | Low | Code signing / attestation infrastructure |
| DD-5 | Hot-reload | Medium | File watcher + subprocess restart |
| DD-6 | Pure .nd extensions | Medium | Nodus execution host in worker |
| DD-7 | nodus-observability integration | Low | Blocked on nodus-observe (v5.0 roadmap) |
| DD-8 | Extension marketplace / registry discovery | High | External service required |

**Most actionable for v0.2 (no external blockers):**
DD-1, DD-4, DD-5, DD-6

## v0.2 proposed phase sequence (Phase 0 must confirm these)

```
Phase 0: Lock v0.2 decisions (D11+): Docker dep strategy, trust enforcement model,
         hot-reload atomicity contract, .nd extension worker protocol
Phase 1: Design docs — DockerRunner, CapabilityPolicy, hot-reload
Phase A: DockerRunner implementing SandboxRunner ABC ([docker] optional extra)
Phase B: CapabilityPolicy — blocks extensions below configured trust tier
Phase C: Hot-reload — file watcher, subprocess restart, ExtensionHost.reload()
Phase D: Pure .nd extensions — Nodus host in worker, NDJSON → run_source() mapping
Phase E: Invariants + integration + packaging for v0.2
```

Note: DD-3 (additional ABI surfaces) requires nodus-workflow and an agent framework
to exist first — it's a dependency, not a timeline decision.

## Key existing surfaces (do not break)

- `SandboxRunner` ABC — `start()`, `stop()`, `invoke()`, `is_alive()`
- `MemoryBackend`-style design: implementations swap in without API changes
- `Capability` enum (7 values) — adding new caps is additive (no removals)
- `CapabilityGate.require(cap)` — single enforcement point before every privileged op
- `attach_to_runtime(runtime, registry)` — registers `_ext_*` host functions (not `ext_*`)
- `_ext_` prefix for host functions — the .nd wrappers are `ext_load`, `ext_invoke` etc.
- `ext_invoke(name, tool, args_json)` — args is a JSON string, not a Nodus map
- Manifest format: `nodus-extension.json`, abi_version="1", tool/v1alpha1 surfaces

## Extension developer contract (do not break)

Extension `extension.py` uses:
```python
from nodus_extension.worker import register_tool, run_loop
register_tool("myapp.tool", lambda args: ...)
run_loop()
```
NDJSON IPC: `{"id":"uuid","op":"invoke","name":"tool.name","args":{...}}\n`

Any new sandbox tier must support the same `extension.py` contract.

## Dev environment

```powershell
# Run tests
cd C:\dev\nodus-extension
PYTHONPATH="C:/dev/Coding Language/src" "C:/dev/Coding Language/.venv/Scripts/python.exe" -m pytest tests/ -q

# Coverage gate: 75%
PYTHONPATH="C:/dev/Coding Language/src" "C:/dev/Coding Language/.venv/Scripts/python.exe" -m pytest tests/ --cov=nodus_extension --cov-fail-under=75 -q

# Install dev mode (hatchling, --no-deps to skip nodus-lang 4.0 PyPI check)
"C:/dev/Coding Language/.venv/Scripts/python.exe" -m pip install -e . --no-deps

# Test the hello-ext fixture end-to-end
PYTHONPATH="C:/dev/Coding Language/src" "C:/dev/Coding Language/.venv/Scripts/python.exe" -m nodus_extension invoke tests/fixtures/hello-ext test.hello.greet "{}"
```

## Commit format

```powershell
git commit -m @'
feat(phaseX): description

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
'@
```

Push to `github.com/Masterplanner25/nodus-extension` after each phase.
