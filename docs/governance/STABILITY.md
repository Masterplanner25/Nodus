# Nodus Stability Policy

**Last reviewed:** 2026-09-01, against 5.9.0
**Status:** Summary — `LANGUAGE_STABILITY_INDEX.md` is the governing classification
**Maintainer:** Shawn Knight (Masterplanner25)

> **The per-surface classification lives in
> [`LANGUAGE_STABILITY_INDEX.md`](./LANGUAGE_STABILITY_INDEX.md), and only there.**
> Do not restate it here. This document defines what the three levels *mean*;
> that document says which level each surface is at.

---

## Stability levels

| Level | What it promises |
|-------|------------------|
| **Stable** | Behaviour and syntax are expected to remain compatible. |
| **Mostly Stable** | Minor refinements may occur in minor releases. Breakage is avoided but not guaranteed. |
| **Experimental** | Semantics or syntax may change in any release. Do not take production dependencies on an experimental surface without tracking `CHANGELOG.md`. |

`LANGUAGE_STABILITY_INDEX.md §10` states the criteria a surface must meet to
graduate from one level to the next.

---

## Where to look

| Question | Document |
|---|---|
| What level is *this* surface at? | `LANGUAGE_STABILITY_INDEX.md` — syntax, stdlib, embedding API, bytecode, CLI, tooling servers, error shapes |
| What counts as a breaking change? | `COMPATIBILITY_MODEL.md` |
| When does a deprecated thing go away? | `COMPATIBILITY.md` |
| What is frozen at the bytecode layer? | `FREEZE_PROPOSAL.md`, and `nodus_gate --opcodes` enforces it |

---

## Why the flat lists that used to be here are gone

This document carried its own three-column list of Stable / Mostly Stable /
Experimental surfaces, written 2026-05-29 and never updated. Reviewed against the
tree on 2026-09-01, it was wrong in both directions on the surfaces users ask
about most:

- **`workflow` / `goal` / `step` were listed Experimental.** They graduated to
  **Mostly Stable** at v4.0.5. So did `spawn` / `coroutine` / `channel`, also
  listed Experimental here. Nine releases of understating a guarantee that had
  already been made.
- **`export` was listed Stable.** The index has it Mostly Stable — visibility
  rules may still be refined. That direction is worse: it promises more than the
  project intends to keep.
- **It named 47 stable opcodes.** There are **49**. `MOD` and `RESET_LOCAL_IDX`
  were added after the v1.0 freeze; a 2026-08-07 sweep corrected the count in
  `FREEZE_PROPOSAL.md` and `LANGUAGE_STABILITY_INDEX.md`, filed [#366](https://github.com/Masterplanner25/Nodus/issues/366),
  and missed this file.
- **It was silent on everything shipped since**: `match`, `break` / `continue`,
  string interpolation, `yield`, compound assignment, the integer suffix, the
  explicit `record { … }` form, `goal … over …`.

Every surface it covered is covered by `LANGUAGE_STABILITY_INDEX.md` at finer
grain, including the two it held that looked unique — workflow persistence format
(§5) and the package manager (§6). So there was nothing to migrate, only a second
copy of one question to stop maintaining.

This is the repository's standing rule about duplicated enumerations, applied to
a document rather than to code: **name the set once.** A summary that restates a
classification will drift from it, and a governing document that has drifted is
worse than one that points somewhere.
