# v5.3.0 — Post-Publish Eval (Stage 5)

Against the **published** package, installed the way a new user installs it.
Prompt: `docs/governance/EVAL_POSTPUBLISH.md`.

| | |
|---|---|
| Package | <https://pypi.org/project/nodus-lang/5.3.0/> |
| Install | `pip install nodus-lang` into a fresh venv |
| Resolved | `nodus-lang 5.3.0` |
| Date | 2026-08-25 |
| Verdict | **PASS** |

Distinct from Gate 10 by design: Gate 10 asks *"what can I make fail?"* against a
local wheel; this asks *"does this work the way a new user would expect?"* against
the artifact on PyPI. The two have caught different things — 5.0.3 passed Gate 10
and was caught here.

---

## 0. One wrinkle worth recording: index lag

The first `pip install nodus-lang` **immediately** after upload resolved to
**5.2.0**, and `https://pypi.org/pypi/nodus-lang/json` still reported 5.2.0 as
latest with no 5.3.0 files. The simple index already carried both artifacts:

```
5.3.0 artifacts on the index: ['nodus_lang-5.3.0-py3-none-any.whl',
                               'nodus_lang-5.3.0.tar.gz']
```

`pip install --no-cache-dir --upgrade nodus-lang` then resolved 5.3.0 correctly.

Not a defect, and it settles on its own — but it is a real few-minute window in
which a new user gets the previous release, and it means **a version check run
straight after upload is not evidence of anything**. The same shape as the
nodus-vscode marketplace note: validation takes minutes, and a check made
immediately reports the old version.

---

## 1. Install and identify

```
$ pip install nodus-lang
$ nodus --version
Nodus 5.3.0
```

No dependency conflicts, no build step — the wheel is pure Python.

---

## 2. First program

```nodus
fn main() {
    print("hello from \(1i + 1i)")
}
```

```
$ nodus run hello.nd
hello from 2
```

---

## 3. The headline: a policy that denies now denies

The release's lede is that declarations bind. The sharpest case is a
`CapabilityPolicy`, which through 5.2.0 could not see four whole effect surfaces:

```python
from nodus.runtime.capability import CapabilityDecision, CapabilityPolicy, DenyList

DenyList("tool.invoke")          # raised `unknown capability` through 5.2.0

class NoMemory(CapabilityPolicy):
    def check(self, r):
        if r.capability.startswith("memory."):
            return CapabilityDecision.deny("no memory for guests")
        return None
```

```
capabilities: 10
blocked : True | Blocked: no memory for guests
```

Ten capability names, up from five. `memory_put` is refused, and the refusal
carries the host's own reason rather than a generic message.

---

## 4. The two-tier filesystem split, from the CLI

The concrete thing #467 was filed for: an agent with read-only context and an
editable subtree.

```
$ nodus run agent.nd --allow-paths <root> --writable-paths <root>/src
Sandbox error at agent.nd:5:31: write_file(path, content) blocked:
    path 'ctx/out.txt' is readable but not writable
read ctx  -> 8
write src -> ok
```

Reads the context, writes the editable tree, refuses the write into context —
and the message names *which* constraint failed rather than a flat "not
permitted".

---

## 5. The manifest a new user actually has

This is the one change in 5.3.0 that makes previously-working input fail, so it
is the important new-user check. A `nodus.toml` of the shape people write:

```toml
[project]
name = "myapp"
entry = "workflows/boot.nd"

[runtime]
log_level = "info"
```

```
$ nodus run
nodus.toml declares things Nodus does not read:
  unknown table [project] -- did you mean [package]?
  unknown table [runtime] -- Nodus has no [runtime] table

nodus.toml supports [package], [dependencies], and [package] keys: name,
version, registry_url, entry.
```

The failure is loud, names every offending table, and suggests the one-word fix.
Through 5.2.0 this manifest loaded and every line of it was discarded in silence
— `nodus run` then reported `File not found: ...\src\main.nd`, naming a file the
author never mentioned.

**This is a break, and it should be read as one.** A project whose manifest
carries an unknown table stops loading until it is corrected. The judgement was
that a manifest is configuration read once at load rather than behaviour observed
during a run, so a warning there would be read by nobody — but a user upgrading
into it deserves the CHANGELOG entry, which it has.

---

## 6. Upgrade in place — the gap Gate 10 could not cover

Gate 10 uses a fresh venv, so it says nothing about upgrading over an existing
install with a warm bytecode cache. Tested here:

```
installed: 5.2.0
$ nodus run flow.nd
total=2
cache after 5.2.0 run:
  .nodus/cache/a4b8f077...nbc
  .nodus/graphs/g_33806815.json

$ pip install --upgrade nodus-lang     ->  5.3.0
$ nodus run flow.nd                    # same file, stale 5.2.0 cache present
total=2
```

Correct, and the cache was genuinely invalidated rather than reused — the entry
now embeds `5.3.0`:

```
version string embedded in the cache entry: 5.3.0
```

That is the #411/#449 version key doing its job. Worth confirming rather than
assuming: a stale `.nodus/` surviving a version bump is precisely the failure that
made a compiler edit look inert.

---

## 7. What this did not cover

- **A real third-party project hitting the manifest break.** The two manifests on
  record were checked by hand. There is no way to survey manifests elsewhere.
- **Optional extras.** `nodus-lang[retry]` not installed; `doctor` correctly warns
  that `@retry` falls back to the in-memory effect store.
- **Companion co-install.** Stage 6 covers it, resolving published metadata rather
  than reading a range by eye.
- **Platforms.** Windows 11, CPython 3.11.9.
- **`allow_subprocess=True` with `writable_paths`.** The runtime's writes and a
  subprocess's redirect targets are scoped; what a spawned child writes is not,
  and cannot be from in-process.
