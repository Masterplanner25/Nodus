# Stage 5 — post-publish eval, v5.0.1

**Date:** 2026-08-17 · **Verdict: clean, no findings.**

Run against the **published** package from PyPI, in venvs with no dev source on
the path. Gate 10 asks "what can I make fail?" against a local wheel; this asks
"does this work the way a new user would expect?" against the artifact they will
actually receive.

---

## 0. What this release is

5.0.1 is a patch whose entire content came from a downstream adoption report on
5.0.0. It publishes surfaces embedders were previously reaching by scraping our
source, and it is the release that makes 5.0.0 adoptable at all — five companions
had capped `nodus-lang<5.0.0`.

That shapes the eval: the load-bearing question is not "does the language still
work" but "can a user actually install this alongside the ecosystem, and are the
newly promised surfaces really there?"

## 1. Install

```
$ pip install nodus-lang
$ nodus --version
Nodus 5.0.1
```

### One real trap, worth recording

**The first install attempt returned 5.0.0.** Not a failed upload — pip had a
cached index page from earlier verification runs in this session. `pip install
--no-cache-dir` gave 5.0.1 immediately, and the simple index already listed it:

```
index versions: ['4.1.1', '4.2.0', '5.0.0', '5.0.1']
```

This is the same shape as the `nodus-vscode` Marketplace lag recorded in the 5.0.0
Stage 6 sweep, where a gallery-API check straight after upload still reported the
previous version. **In both cases the correct move is to check the authoritative
index, not to re-upload.** A re-upload here would have failed anyway — PyPI
rejects a duplicate filename — but the same reflex against a Marketplace or a
GitHub release is destructive, and release immutability makes the GitHub case
permanent.

## 2. New-user flow

```
$ nodus init
Initialized Nodus project at …\proj\
$ ls
nodus.toml  src
$ nodus run src/main.nd
hello from nodus
```

Scaffold, run, output — no surprises. Note `nodus init` puts the entry point at
`src/main.nd` rather than the project root; a user who runs `ls` and sees only
`nodus.toml` and `src` has one directory to look in, which is fine, but the init
message does not name the file it created.

## 3. The surfaces this release promises

All present and correct in the published wheel:

```
GATED_BUILTIN_NAMES: 31
groups: ['allow_env', 'allow_network', 'allow_subprocess']
active_vm(): VM
denial kind: sandbox | names flag: True
override refused: Cannot override built-in function: syscall
```

That is, in order: the gated surface is enumerable as data (#441); `active_vm()`
exists and returns a VM (#442); a refusal carries `kind="sandbox"` and names the
granting flag (#444); and `register_function` still refuses to override a builtin
(#443).

## 4. The reason this release exists — cross-checked against the actual complaint

The aindy-runtime report gave a reproduction. Run verbatim against PyPI:

```
$ pip install "nodus-lang==5.0.1" "nodus-mcp>=0.1.2"
nodus-lang  5.0.1
nodus-mcp   0.1.3
```

Before today this was `ResolutionImpossible`. The whole published ecosystem also
resolves and runs together — nodus-lang with nodus-mcp, nodus-extension,
nodus-sdk, nodus-mcp-server and nodus-jupyter installed side by side, a script
executing, and `subprocess_run` still refused by default.

Constraint check against the published index:

```
All 6 companions admit nodus-lang 5.0.1.
```

## 5. Cross-checks against the release claims

| Claim in `CHANGELOG.md` / `README.md` | Verified how |
|---|---|
| "`GATED_BUILTINS` … 31 builtins" | counted from the published package: 31 |
| "the denial names the flag" | `allow_env` present in the refusal message |
| "`_get_active_vm()` retained" | present, and returns the same object as `active_vm()` |
| "bytecode unchanged, `BYTECODE_VERSION` 4" | Gate 10 opcode phase: 49 opcodes, version 4 |
| README banner "v5.0.0 stable on PyPI" | **now stale again — see findings** |

## 6. Findings

**One, cosmetic, filed as follow-up rather than fixed in this release.**

The `README.md` banner now reads *"v5.0.0 stable on PyPI"* — corrected from 4.2.0
in this very release, and stale again the moment 5.0.1 published. That is the
third consecutive cycle in which a version string in prose has gone stale, and it
will happen every cycle as long as the banner names a version and nothing checks
it.

The durable fix is not to correct it again. Either the banner drops the version
(the PyPI badge above it is already live and self-updating), or a gate phase
checks version strings in prose against `version.py`. Recommending the former —
the badge makes the banner's version redundant, and a doc that cannot go stale
beats a gate that catches it going stale.

Not blocking: the badge is correct, PyPI is correct, and no install path is
affected.

> **Addendum, same day — the fix landed too late for this release.**
>
> The banner was changed to drop the version entirely, as recommended. But it was
> changed **after** `v5.0.1` was tagged and built, and `pyproject.toml` sets
> `readme = "README.md"` — so the README is the PyPI *long description*.
> <https://pypi.org/project/nodus-lang/5.0.1/> therefore still displays
> "**v5.0.0** stable on PyPI" while `main` is correct. Verified against the
> published metadata, not assumed.
>
> Not fixable: PyPI rejects a re-upload of an existing version, and cutting a
> 5.0.2 for a banner is not proportionate. The corrected README ships with the
> next release.
>
> The durable lesson is a sequencing one, now in `CLAUDE.md` step 2: **finish
> README edits before tagging.** Anything else in the repo can be fixed in the
> next commit; the README cannot, because the release carries a frozen copy of it.
> This eval caught the staleness and then reintroduced it by fixing it at the
> wrong moment — which is worth recording precisely because the finding and the
> mistake had the same author.

## 7. Known issues shipping, restated

Unchanged from 5.0.0; none introduced here. #411 (`@exactly_once` is forgeable) is
the highest-signal open item, with #387 its structural twin. See the Gate 10
document §5.

## 8. Not covered

- **Non-Windows platforms.** Everything here ran on Windows 11. The wheel is
  `py3-none-any`, so platform risk is low, but it is untested from this machine.
- **Upgrade-in-place from 4.x.** Every venv here was fresh. A user upgrading
  across the 5.0.0 major still meets the deny-by-default break, which is
  documented in `docs/migration/v5.0-deny-by-default.md` and unchanged by 5.0.1.
- **Coverage** was not re-measured; the 76.82% baseline is now 262 tests stale.
