# v5.10.0 — Stage 5 post-publish eval

**Verdict: the published package works as a new user would expect.** Run against
`pip install nodus-lang==5.10.0` from PyPI in a fresh virtualenv, from a
directory outside the repo.

| | |
|---|---|
| Installed | `nodus-lang==5.10.0`, `pip install` exit 0 |
| Resolved | `…/venv-stage5/Lib/site-packages/nodus` |
| CLI | `Nodus 5.10.0` |

Verified by **installing**, not by reading the JSON API — that API serves stale
data after an upload, has reported the previous release as latest, and at 5.6.0
reported zero files for a version that had just landed.

---

## What Stage 5 is for, and why it is not the probes again

Gate 10b asks *"can I make the artifact contradict its own claims?"* one feature
at a time. Stage 5 asks *"does this work?"* — and its distinctive value is
**using features together**, which is how #662 was caught: `extern` and a step
body's dependencies were each fine alone, and the combination made `nodus check`
reject correct programs. So the centre of this run is a single program that uses
the release's headline features at once.

### The combination: park in one process, deliver from another

```nd
workflow onboarding {
    step wait_signup { return workflow_wait("user.signed_up", {correlation_key: "u-77"}) }
    step provision after wait_signup { print("provisioning u-77"); return "provisioned" }
}
```

```
$ nodus run ops.nd --time-limit 30
parked=g_d99ee6e3

$ nodus workflow deliver user.signed_up --correlation-key u-77 --payload '{"plan":"pro"}'
  ok        : True
  matched   : ['g_d99ee6e3']
  ship step : completed
  stdout    : 'provisioning u-77'
```

Two processes. The second knew the **event type and nothing else** — no run id,
no graph id, no shared memory — and the parked run carried forward and its step
actually executed. That is #181's whole point, and before this release the
delivering process had no way to find the run at all.

---

## Everything else a new user touches

| check | result |
|---|---|
| `nodus --version` | `Nodus 5.10.0` |
| a first script runs | `sum=6` |
| `nodus docs` finds its own documentation from the install | lists `llms.txt` and the guide |
| `#754` serve confinement | default `ok=False kind=sandbox`; `allow_subprocess=True` → `ok=True` |
| `#167` `extensions=[]` | withholds orchestration, message names the grant |
| `#167` misspelled extension | **refused at construction** — the Gate 10b defect, fixed and confirmed in the published artifact |
| `#87` `runtime.capabilities()` | returns the live decision map |
| `#160` `max_memory_mb=64` | accepted |

The `extensions=["workfow"]` line is the one worth pointing at: it is the defect
Gate 10b caught on the first build, and this confirms the fix is in the artifact
that was actually published rather than only in the tree.

---

## Nothing found

No new issue filed from this stage. That is a real result rather than an absence
of effort — the previous three cycles each produced one (#691 at 5.8.0, #662 at
5.7.1), and both came from combining features, which is why the combination test
above is the shape of this run rather than a checklist of them individually.

The one thing carried forward is already known and belongs to Stage 6:
`nodus_gate --consumers` reports `nodus-run-action` stale, pinning `5.9.0` in the
README examples new users copy.
