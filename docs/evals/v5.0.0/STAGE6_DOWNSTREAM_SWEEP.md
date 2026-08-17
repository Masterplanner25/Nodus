# Stage 6 — downstream republish sweep, v5.0.0

Run after PyPI publication and the GitHub release. Purpose: find companions that
the new release breaks, admits by accident, or leaves behind.

**Date:** 2026-08-17 · **Verdict at sweep time: one outstanding item** (`nodus-vscode`).
**Closed the same day** — see §5.

This release is the first **major**, so the sweep carries a question the previous
ones did not: every companion pins `nodus-lang` with an **open-ended** range, so
they all admit 5.0.0 automatically. That is the risk, not the reassurance — an
unbounded range means pip installs a breaking release without asking.

---

## 1. Dependency ranges

| Companion | `nodus-lang` range | Admits 5.0.0 |
|---|---|---|
| nodus-mcp | `>=4.0.0` | yes |
| nodus-mcp-server | `>=4.0.5` | yes |
| nodus-extension | `>=4.0.0` | yes |
| nodus-jupyter | `>=4.0.0` | yes |
| nodus-sdk | `>=4.0.0` | yes |
| nodus-native-memory-engine | `>=4.0.0` | yes |
| nodus-a2a, nodus-memory, nodus-store-sql, nodus-workflow, nodus-vscode, nodus-run-action | no dep | n/a |

**No companion caps its range**, so all six pick up 5.0.0 on a fresh install. That
made the compatibility check below mandatory rather than optional.

## 2. Do they still work under 5.0.0?

Every dependent suite run with `nodus-lang==5.0.0` installed.

| Companion | Result |
|---|---|
| nodus-mcp-server | **25 passed** |
| nodus-mcp | 362 passed, 1 failed — `test_phase_m.py::test_m2_bearer_wrong_returns_401`, the port-conflict flake `CLAUDE.md` documents as pre-existing |
| nodus-extension | **126 passed** |
| nodus-jupyter | **32 passed** |
| nodus-native-memory-engine | **76 passed** |
| nodus-sdk | 98 passed, 1 failed — `test_version_string` asserts its own version is `0.1.0` while the package is `0.1.1`. **Unrelated to nodus-lang**; a stale test in that repo |

**No companion is broken by 5.0.0.** Both failures are pre-existing and neither
touches the capability change.

## 3. The one behaviour change downstream

`nodus-mcp-server` constructs two runtimes (`server.py`):

```python
_runtime      = NodusRuntime(timeout_ms=None, max_steps=None, allowed_paths=[])
_exec_runtime = NodusRuntime(..., allow_network=False, allow_subprocess=False)
```

`_exec_runtime` — the arbitrary-code path — **already** denied both explicitly.
`_runtime` used the defaults, so it now denies too.

That is a real change, in the safe direction, and it matches the author's evident
intent: the stricter posture was already applied where it was thought to matter,
and 5.0.0 extends it to the sibling. Its suite passes, so nothing depended on the
old permissiveness.

For an MCP server exposed to Claude Desktop and ChatGPT, model-generated
workflows running with subprocess access is precisely the risk deny-by-default
exists to address.

## 4. Working-tree drift

`git status --porcelain` across all twelve checkouts: **0 uncommitted files**.

Only one companion was touched this cycle, so the "what changed but was not
published" question is answered directly rather than by heuristic — which is the
point of `CLAUDE.md`'s instruction to hash content rather than count commits
("commits since the version bump" produced four false positives in the v4.2.0
sweep).

## 5. Outstanding — resolved

> **Closed 2026-08-17.** `nodus-vscode` **0.1.2** is live on the Marketplace
> (`MasterplanInfiniteWeave.nodus-lang`, updated `2026-08-17T15:37:26Z`, verified
> via the gallery API). The five keywords highlight; nothing from this release is
> outstanding.
>
> One operational note for the next cycle: Marketplace validation took **~4
> minutes**, and a gallery-API check run immediately after upload still reported
> `0.1.1`. That is validation in progress, not a failed publish — do not re-upload
> on the strength of the first check.

The item as recorded at sweep time:

- **`nodus-vscode` needs its VSIX republished.** The grammar was updated for the
  five new `goal` keywords — `over`, `until`, `budget`, `reached`, `retry` —
  in `0aa588c`, committed and pushed, but the Marketplace upload is manual
  (Gate 3b) and has not happened. Until it does, the new syntax renders as plain
  identifiers, which is the exact failure #357 was filed for.

  `package.json` is still at `0.1.1`; publishing needs a version bump first.

  **This is not on PyPI, so no content-hash check can detect it** — it is
  findable only by remembering that a keyword was added. That is why
  `CLAUDE.md` calls it out by name.

- **`nodus-sdk`'s `test_version_string`** is stale in its own repo. One line, not
  a nodus-lang problem, noted so it is not rediscovered.

## 6. Also done during the sweep

The development venv's installed `nodus-lang` was **4.0.8** — five releases
behind, and the root of the stale-`nodus.exe` hazard `CLAUDE.md` documents (the
formatter writer-vs-checker split that broke the format gate repeatedly).
Upgraded to 5.0.0, so `.venv/Scripts/nodus.exe` now matches `src/`.
