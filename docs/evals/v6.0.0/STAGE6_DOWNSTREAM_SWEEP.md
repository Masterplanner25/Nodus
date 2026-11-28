# v6.0.0 — Stage 6 downstream republish sweep

**Date:** 2026-11-28, after the PyPI upload and the GitHub release
(https://github.com/Masterplanner25/Nodus/releases/tag/v6.0.0).

Four questions: do companion ranges admit the new version, has any companion
drifted from what it published, which non-PyPI consumers did the release leave
behind, and is work left uncommitted in any checkout.

## 1. Ranges — `tools/check_downstream_constraints.py`

**All 8 companions admit nodus-lang 6.0.0**, resolved from published metadata.

| companion | published | nodus-lang range |
|---|---|---|
| nodus-a2a-wire | 0.1.0 | `>=4.0.0` |
| nodus-extension | 0.1.2 | `>=4.0.0` |
| nodus-jupyter | 0.1.0 | `>=4.0.0` |
| nodus-mcp | 0.1.6 | `>=4.0.0` |
| nodus-mcp-server | 0.2.1 | `>=5.15.1` |
| nodus-native-memory-engine | 0.1.1 | `>=4.0.0` |
| nodus-sdk | 0.2.0 | `>=4.0.0` |
| nodus-workflow-ai | 0.1.0 | `>=5.8.0` |

No companion caps nodus-lang, per the 2026-08-17 policy. A major therefore
reaches every companion's users with no companion release, which is why Gate 10a
ran their suites against 6.0.0 first (`CREATOR_VALIDATION.md`): no code break.

## 2. Publish drift — `tools/check_publish_drift.py`

**All 13 companions match what they published**, by file content against each
downloaded sdist. No companion has unpublished work.

## 3. Non-PyPI consumers — `nodus_gate --consumers`

Two needed republishing, both because `nodus_version` moved 5.21.0 → 6.0.0:

- **nodus-run-action → v1.0.24.** README examples pin `version: '6.0.0'`. The
  action itself is unchanged and uses nothing 6.0.0 removed (checked: no `.tl`,
  no `language` launcher). Tagged `v1.0.24`, the floating `v1` moved to the same
  commit (`19c7a41`), GitHub release created.
- **nodus-wiki → `fc50f45`.** Beyond the banners (Home, Getting-Started, Roadmap,
  _Footer, _Sidebar) and Security's supported-versions table (5.x now
  "upgrade first", pointing at the migration guide), five passages described
  5.x behaviour and were corrected: `.tl` in the import resolution order;
  `durable_spawn` needing `NODUS_WORKFLOW_STORE_BACKEND=sqlite`; the default-store
  change as a future warning (now a refusal); `nodus check --staged` as the way to
  see 6.0.0 breakage; type annotations as "hints".

`tools/consumers.json` records both (`published` and `fingerprint: 6.0.0`), in
this PR. `nodus-vscode` was in step: keywords unchanged. **`--consumers`: 3/3 in
step.**

## 4. Work left behind

`git status` in each of the 14 companion checkouts: **all clean and in step with
their remotes** (nodus-mcp, nodus-a2a, a2a-wire-pub, nodus-memory,
nodus-native-memory-engine, nodus-extension, nodus-sdk, nodus-store-sql,
nodus-workflow-ai, nodus-jupyter, nodus-mcp-server, nodus-workflow, nodus-vscode,
nodus-run-action).

**One thing is not work left behind but needs an owner's decision:**
`C:\dev\nodus-mcp-server\.nodus\workflow_framework\runs\` holds 215 JSON run
records (gitignored, so `git status` does not show them). Under 6.0.0 the default
store refuses to open there until they are migrated
(`nodus workflow migrate-store --to sqlite`) or the JSON store is kept
(`NODUS_WORKFLOW_STORE_BACKEND=local`). Left untouched, since they may be real
runs from a local MCP server.

## Verdict

**Clean.** Every range admits 6.0.0, nothing drifted, both stale consumers are
republished, and no checkout holds uncommitted work.
