Start or continue a nodus-mcp Phase 1 design doc or Phase A-N implementation
phase. Walks through the phase in order, checking the decisions doc and
any existing design docs before writing or implementing anything.

Arguments: $ARGUMENTS
(Pass "phase1" to write the next Phase 1 design doc, or a phase letter like
"A", "B", "C" to implement that phase. If omitted, determine from context.)

## Pre-flight checks

Before touching any files:

1. Read `C:\dev\nodus-mcp\docs\design\00-decisions.md` — confirm all 16 Phase 0
   decisions are settled. If any are open, stop and ask.
2. Read existing Phase 1 design docs in `C:\dev\nodus-mcp\docs\design\` —
   understand what's already been designed.
3. For implementation phases: read the relevant Phase 1 design doc(s) first.
   Do not implement against an unwritten design doc.
4. Check `C:\dev\nodus-mcp\tests\test_install_roundtrip.py` passes:
   ```powershell
   cd C:\dev\nodus-mcp
   PYTHONPATH="C:/dev/Coding Language/src" `
     "C:/dev/Coding Language/.venv/Scripts/python.exe" `
     -m pytest tests/ -q
   ```

## Phase 1 design doc sequence

Five design docs, in this order (write each before implementing anything
that depends on it):

1. `01-adapter-mapping.md` — stateless request model → tool registry
2. `02-elicitation.md` — MRTR loop, callback wiring, timeout, err contract
3. `03-transports.md` — stdio + HTTP shared-core design
4. `04-server-mode.md` — registry → MCP enumeration, server elicitation
5. `05-deprecated-features.md` — Roots + Sampling handling

## Phase A-N implementation sequence (from 00-decisions.md)

- Phase A: Foundation (JSON-RPC, MCP message types, lifecycle)
- Phase B: Stdio transport
- Phase C: Client tools (tools/call, MRTR loop)
- Phase D: Client resources
- Phase E: Client prompts
- Phase F: Client advanced (Roots, Sampling, Elicitation via SEP-2322)
- Phase G: HTTP transport (stateless; RC collapsed pre-RC HTTP/Streamable HTTP)
- Phase H: Server foundation
- Phase I: Server tools (NodusRuntime.tool_registry → MCP enumeration)
- Phase J: Server resources
- Phase K: Server prompts
- Phase L: Server advanced
- Phase M: Server transport
- Phase N: Polish (CLI, REPL, docs, test suite)

## Key constraints (from Phase 0 decisions)

- Target spec: **2026-07-28 RC** (stateless; no session init handshake)
- No session objects in the API
- Tool namespace: `mcp.<alias>.<tool_name>`
- Elicitation encapsulated in Python handler (invisible to Nodus scripts)
- Bearer token auth only in v0.1
- Roots + Sampling included; Tasks/MCP Apps/Logging deferred to v0.2+
- `std:tool` registry is source of truth; `std:tools` is a separate domain

## Dev environment

```powershell
# nodus-mcp tests
cd C:\dev\nodus-mcp
PYTHONPATH="C:/dev/Coding Language/src" `
  "C:/dev/Coding Language/.venv/Scripts/python.exe" -m pytest tests/ -q

# nodus-lang tests still pass (regression guard)
cd "C:/dev/Coding Language"
PYTHONPATH="C:/dev/Coding Language/src" `
  "C:/dev/Coding Language/.venv/Scripts/python.exe" -m pytest tests/ -q `
  --ignore=tests/test_scheduler_fairness.py
```

nodus-lang dev source is at `C:\dev\Coding Language\src`. The nodus-mcp
venv is the same as nodus-lang's: `C:\dev\Coding Language\.venv`.

## Commit and push

Commit to `C:\dev\nodus-mcp` with message format:
```
feat(phaseX): <description>

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>
```

Push to `github.com/Masterplanner25/nodus-mcp` after each phase is complete.
