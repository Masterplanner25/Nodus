# v5.6.0 — Post-publish evaluation (Stage 5)

Against the **published** package, installed from PyPI as a new user would, in a
fresh venv, from a directory outside the checkout.

```
install   pip install --no-cache-dir nodus-lang==5.6.0
package   .../.venv-postpublish/Lib/site-packages/nodus
version   5.6.0
cwd       a scratch directory, not the repo
```

**Verdict: pass.** Everything the release claims works from the published
artifact, and the two corrections Gate 10b forced are visibly on the permanent
project page.

---

## The question this stage asks

Not "can I make it fail" — that is Gate 10 — but "does this work the way a new
user would expect". So every command below is one a reader is actually told to
run, and the code is copied from the documents that teach it.

## Install and identity

```
$ pip install nodus-lang==5.6.0
$ nodus --version
Nodus 5.6.0
```

Resolved package is `site-packages/nodus`, **not** the source tree. Run from a
scratch directory on purpose: the repo-root `nodus.py` shim shadows an installed
package whenever CWD is the checkout, which is the trap Gate 10 hit for the
third time this cycle and now refuses mechanically.

## First script, as `README.md` teaches it

```nd
fn main() {
    print("hello from \(1i + 1i)")
}
```

```
$ nodus run hello.nd
hello from 2
```

## The headline feature, copied verbatim from the guide

`docs/guide/workflows-and-tasks.md` §3.3, unchanged:

```nd
workflow publish {
    step discover { return ["intro.md", "guide.md", "api.md"] }
    step render each page in discover { return "rendered \(page)" }
    step index after render { return "indexed \(len(render)) pages" }
}
```

```
$ nodus run publish.nd
["rendered intro.md", "rendered guide.md", "rendered api.md"]
indexed 3 pages
{"discover": "completed", "render": "completed", "index": "completed"}
```

Three things confirmed in that one output: the body ran per item, the join
received the **list** rather than one item, and `statuses` names `render`
**once** and as `completed` — the aggregation bug fixed alongside #480.

`nodus check publish.nd` → `OK`, so static analysis understands the new form
rather than merely tolerating it.

## Parameters (#481)

```nd
workflow build(mode) { step compile { return "compiling in \(mode)" } }
```

```
$ nodus run build.nd
compiling in lite
```

## The additive claim, tested rather than asserted

5.5.0-era code using `state`, `+=` on a state cell, `checkpoint`, `after` and
`with { on: [...] }` runs unchanged:

```
$ nodus run legacy.nd
tested built
[]
```

## The staged warning (#609) is a warning

```
$ nodus run typo.nd
1
```

It runs. `nodus check` reports it, with the suggestion and the deprecation
horizon in the message itself:

```
typo.nd:1:9: warning: Unknown type name 'itn' — did you mean 'int'? It is
currently ignored, so nothing on this annotation is checked; in 6.0.0 it
becomes an error. Known types: any, bool, float, function, int, list, map,
nil, record, string.
typo.nd: OK (1 warning(s))
```

## Security posture, from the published artifact

Deny-by-default still holds for a bare embedded runtime, and the denial still
names the flag that grants it — the contract downstream confinement tests
depend on:

```
ok: False | kind: sandbox | names the flag: True
```

And **#616**, the `severity:high` fix this release carries: both the sync and
async forms of the agent call carry a capability, so the policy cannot be
bypassed by writing the async spelling.

```
both forms carry a capability: True | missing: []
```

## Agent on-ramp

```
$ nodus docs
Nodus 5.6.0 — documentation and agent material

  llms.txt
    machine-readable project index — start here if you are an agent
```

`llms.txt` ships **inside the wheel**, and the copy a user gets is current:

```
- PyPI: `nodus-lang` (v5.6.0 — current stable, published 2026-08-28)
```

That matters because it is the file an agent reads first, and it was the file
that dated 5.5.0 to the wrong day.

---

## What the project page actually says

`pyproject.toml` sets `readme = "README.md"`, so the file at tag time is the
PyPI page forever. Read back from the published metadata:

```
**Recent:** 5.6.0 is about workflows declaring what they used to only imply: ...
page still says 32 packages:  False
page says 35 packages:        True
```

Both are Gate 10b catches, and both would have been permanent. The probe found
`README.md:213` still claiming 32 standalone companion packages against a
verified live count of 35 — a paragraph the earlier seven-place sweep had
missed. Confirmed here on the published page rather than only in the repo.

## One thing that looks like a failure and is not

Immediately after upload, the PyPI JSON API reported:

```
latest: 5.5.0
5.6.0 files: []
```

with `Cache-Control: no-cache` set. This is the same stale read seen after the
`nodus-flow` publish, and it reads exactly like a failed upload. `pip install
nodus-lang==5.6.0` succeeded against the simple index at that moment, and the
JSON API caught up shortly after:

```
latest now: 5.6.0
5.6.0 files: 2
```

**Verify a publish by installing it, not by reading `info.version`.**

## Known-stale at publish time

Both are Stage 6 work and neither affects the published package:

- `nodus-vscode` — 0.1.4 packaged and committed (`31d9978`), pending a
  Marketplace upload. Until then the extension renders `each` unhighlighted.
- `nodus-run-action` — README pin still names 5.5.0.
