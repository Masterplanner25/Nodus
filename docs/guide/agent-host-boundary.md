# The Agent Host Boundary

`agent_call` is where a Nodus program hands a **semantic decision** to the host.

Nodus has no model in it. That is deliberate, and it is the reason this boundary
exists: anything requiring judgement — *rebase or merge? is this review
adequate? which of these three plans?* — cannot be decided by the runtime, so it
is delegated across a typed boundary to a handler the host registers.

Everything else in the language is about getting *to* that boundary and acting on
what comes back: workflows sequence it, `state` carries it, checkpoints make it
resumable, and the capability policy bounds what the program may do with the
answer.

If you are looking for **tools** rather than agents — deterministic functions a
script calls by name — see [ai-primitives.md](ai-primitives.md) for `std:tool`.
The distinction is in [§6](#6-agents-vs-tools).

---

## 1. The five builtins

| Builtin | Arity | What it does |
|---|---|---|
| `agent_call(name, payload)` | 2 | Call a registered handler, block for the result |
| `agent_call_async(name, payload)` | 2 | Same, from inside a coroutine |
| `agent_available()` | 0 | List of registered agent names |
| `agent_describe(name)` | 1 | That agent's spec, or `nil` if unknown |
| `action agent "name" with { … }` | — | Statement form, valid **only inside a workflow step** |

No import — these are builtins, like `channel()` and `spawn()`.

---

## 2. Registering a handler

From Python, on the runtime:

```python
from nodus import NodusRuntime

def git_strategist(payload):
    local = payload.get("local_commits", 0)
    return {"choice": "rebase" if local < 5 else "merge", "why": "commit count"}

runtime = NodusRuntime()
runtime.register_agent("git_strategist", git_strategist,
                       description="picks rebase vs merge")
```

The handler takes the payload as a **dict** and returns any JSON-safe value.

### Use the runtime method, not the module-level function

There is also `nodus.services.agent_runtime.register_agent`. It registers into
the **process-global** registry, and `NodusRuntime.register_agent` registers into
whichever registry *that runtime* uses. Those differ the moment you scope one:

```python
runtime = NodusRuntime(agent_registry={})        # per-tenant registry
register_agent("picker", handler)                # module-level -> the GLOBAL one
```

```
scoped runtime sees      : []
calling it              : false | [{"type": "AgentError", "message": "No handler registered for agent 'picker'", "agent": "picker"}]
```

Registered, and invisible to the runtime that scoped its registry. Use
`runtime.register_agent(...)` and the two cannot disagree. `runtime.unregister_agent(name)`
is scoped the same way.

Pass `agent_registry={}` when a host serves more than one tenant: agents are
**not** isolated per runtime by default, because a guest cannot register one —
registration is host-only — so the shared registry holds only what the host put
there.

---

## 3. Calling it, and the envelope

`agent_call` does **not** return the handler's value directly. It returns a
nine-key envelope, and the handler's value is under `result`:

```nodus-no-run
fn main() {
    let verdict = agent_call("git_strategist", {"local_commits": 2i})
    print("keys:   \(keys(verdict))")
    print("ok:     \(verdict["ok"])")
    print("result: \(verdict["result"])")
}
```

```
keys:   ["ok", "stage", "filename", "stdout", "stderr", "result", "errors", "diagnostics", "error"]
ok:     true
result: {"choice": "rebase", "why": "commit count"}
```

| Key | Meaning |
|---|---|
| `ok` | did the agent call succeed |
| `result` | **the handler's return value** |
| `errors` | list of `{type, message, agent}` when `ok` is false |
| `stage` | always `"agent_call"` |
| `filename`, `stdout`, `stderr`, `diagnostics`, `error` | describe the **calling script**, not the agent |

Those last five are the script-execution envelope showing through. They are not
about the agent, and reading them as if they were is a mistake the shape invites.

**The trap.** Reaching straight for the handler's field is the natural thing to
write and it fails:

```nodus-no-run
let verdict = agent_call("git_strategist", {"local_commits": 2i})
print(verdict["choice"])        // Missing map key: "choice"
```

Always go through `result`.

---

## 4. Failure is soft — check `ok`

**An agent failure does not fail the run.** If the agent is not registered, or
the handler raises, `agent_call` returns an envelope with `ok: false` and the
script keeps going:

```
false
[{"type": "AgentError", "message": "No handler registered for agent 'nope'", "agent": "nope"}]
```

```
false
[{"type": "AgentError", "message": "the model refused", "agent": "boom"}]
```

In both cases the *run* succeeded. That is deliberate — a host handler failing is
an outcome the program may want to handle, not a crash — but it means **an
unchecked `agent_call` looks like it worked**. Branch on `ok`:

```nodus-no-run
let verdict = agent_call("git_strategist", {"local_commits": 2i})
if (verdict["ok"]) {
    return verdict["result"]["choice"]
}
return "unavailable"
```

Inside a workflow step, an unchecked read of `result` on a failed call raises
`Missing map key`, which fails the *step* — so the step lands in `failed` and is
absent from `steps`, while the run's own `error` stays `nil`. If a step vanished
without an error, this is the first thing to check.

---

## 5. Introspection

```nodus-no-run
fn main() {
    print("available: \(agent_available())")
    print("describe:  \(agent_describe("git_strategist"))")
}
```

```
available: ["git_strategist"]
describe:  {"name": "git_strategist", "description": "picks rebase vs merge", "parameters": {"type": "object"}}
```

`agent_describe` returns `nil` for an unknown name — it does not raise. The
`parameters` field comes from the `payload_schema` you register; it defaults to
`{"type": "object"}` and is **not enforced** against the payload.

---

## 6. Agents vs tools

Both cross into host Python. They differ in what they are *for*:

| | `std:tool` | `agent_call` |
|---|---|---|
| Decides | nothing — deterministic work | the judgement the runtime cannot make |
| Schema | declared and **enforced** | declared and **not** enforced |
| Names | must be dotted (`myapp.greet`) | any non-empty string |
| Failure | raises | soft — `ok: false` in the envelope |
| Registration | `runtime.tool_registry.register({...})` | `runtime.register_agent(...)` |

Reach for a tool when the host does something; reach for an agent when the host
*decides* something.

---

## 7. In a workflow

The realistic shape — decide in one step, act in the next, with the decision
flowing along the `after` edge (see
[workflows-and-tasks.md §3.1](workflows-and-tasks.md)):

```nodus-no-run
workflow sync {
    step decide {
        let verdict = agent_call("strategist", {"local": 2i})
        if (verdict["ok"]) { return verdict["result"]["choice"] }
        return "unavailable"
    }
    step apply after decide { return "applying \(decide)" }
}

fn main() {
    let r = run_workflow(sync)
    print(r["steps"]["apply"])
}
```

```
applying rebase
```

Because the decision is a step's return value, it is **persisted with the run**
and survives a resume — the host is not asked twice for a decision already made.

### The statement form

Inside a step, `action agent` calls an agent for its effect. Note `with`, and
that the payload is a **named** map (unquoted keys):

```nodus-no-run
step decide {
    action agent "strategist" with { local: 2i }
    return "asked"
}
```

It is a statement, not an expression — use `agent_call` when you want the result.
Outside a step it is refused: `action expressions are only valid inside steps`.

### Async

`agent_call_async` is the coroutine form, for fanning out several decisions:

```nodus-no-run
fn main() {
    let c = coroutine(fn() {
        let v = agent_call_async("strategist", {"local": 9i})
        print("async result: \(v["result"])")
    })
    spawn(c)
    run_loop()
}
```

```
async result: {"choice": "merge"}
```

---

## 8. Bounding a handler

A host handler is arbitrary Python and cannot be preempted. `agent_timeout_ms=`
on `NodusRuntime` bounds the **wait**, not the handler: at the deadline the call
returns and the handler is abandoned on a daemon thread. Abandoned calls are
recorded — `runtime.abandoned_agent_calls()` and
`runtime.abandoned_agent_call_count()` — so an operator can answer *"is something
stuck?"*.

The tightest of a step's `timeout_ms` (minus time already spent) and this default
wins.

---

## 9. See also

- **[ai-primitives.md](ai-primitives.md)** — `std:tool`, and the rest of the
  AI-native surface.
- **[embedding-nodus.md](embedding-nodus.md)** — `NodusRuntime`,
  `register_function`, sandboxing, type marshaling.
- **[workflows-and-tasks.md](workflows-and-tasks.md)** — steps, `after` edges,
  checkpoints and resume.
