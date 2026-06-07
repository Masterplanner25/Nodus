# Real User Reality Audit

**Objective:** Determine what three categories of user can actually accomplish with
this system today, where they will succeed, and where they will fail.

Applies to: any language runtime at a point where real users could plausibly try it.

---

## Rules

- No vague statements. Every claim must be verifiable by trying it.
- "Mostly works" is not an answer. State exactly what succeeds and exactly what fails.
- Do not describe what the system is *designed* to do. Report what a user can *do*.
- If you cannot determine the answer without trying something, say so.

---

## User Type 1 — Script Author

A developer writing programs in the language directly. They know the syntax.
They want to express logic, call stdlib functions, handle errors, import modules.

### What succeeds today

List specific things the script author can reliably do:
(Examples: write a function, call stdlib X, import from Y, spawn a coroutine,
handle a try/catch, pass data between modules)

### What struggles today

List specific things that work sometimes or require non-obvious workarounds:
(Examples: multiline expressions, closures over mutable state, integer arithmetic,
print with multiple arguments)

### What breaks today

List things that produce incorrect output, a confusing error, or silent failure:
(Examples: a specific type coercion, a specific standard library edge case, a pattern
that parses but produces wrong output)

### First succeeding use case (specific)

The exact program a new user can write and run in under 10 minutes that does
something genuinely useful.

### First blocking failure (specific)

The exact thing a new user will try that will fail without a clear error message.

---

## User Type 2 — Library / Tool Author

A developer writing a reusable library in the language, or writing extensions
that register host functions for other scripts to call.

### What succeeds today

What can a library author reliably publish and have others use?

### What struggles today

What patterns require workarounds, undocumented APIs, or internal knowledge?

### What breaks today

What cannot be done without forking the runtime or using unsupported internals?

### First succeeding use case (specific)

The specific library pattern that a competent user can ship in a reasonable amount of time.

### First blocking failure (specific)

The specific thing a library author will hit that has no solution.

---

## User Type 3 — Embedder

A developer embedding the runtime into a host application (server, agent framework,
data pipeline). They need to start the runtime, execute scripts, pass data in and
out, observe errors, and clean up.

### What succeeds today

What embedding patterns work reliably?

### What struggles today

What embedding patterns require reading source code or working around gaps?

### What breaks today

What patterns fail silently or produce incorrect host-side behavior?

### First succeeding use case (specific)

The exact embedding call sequence that a new embedder can get working in under
an hour from documentation alone.

### First blocking failure (specific)

The exact embedding scenario that fails and cannot be worked around without modifying
the runtime.

---

## Cross-Cutting Findings

Issues that affect all three user types:

- Documentation gaps (things that are true but not written down)
- Error messages that don't point at the source of the problem
- Concepts where the mental model implied by the documentation does not match actual behavior

---

## Summary Table

| | Script Author | Library Author | Embedder |
|---|---|---|---|
| Can reliably do | | | |
| First success | | | |
| First blocker | | | |
| Overall friction | Low / Med / High | Low / Med / High | Low / Med / High |

---

**Rules:**
- All claims in this audit are falsifiable by running code.
- If a user type cannot be meaningfully tested, say why.
- Do not assume the user has read the source code.





Real User Reality Audit — Nodus v4.0.0 Runtime - 6/7/26 12:15am 

  ---
  User Type 1 — Script Author

  What succeeds today

  A script author can reliably do all of the following, confirmed by execution:

  Language core:
  - let, fn, if/else, while, for/in over lists — all work as documented
  - Recursion up to MAX_STACK_DEPTH=10,000 frames — fib(20) produces 6765
  - String interpolation: "hello \(name)" — works
  - First-class functions: closures as values, factory functions that return closures — work
  - try { ... } catch e { ... } finally { ... } with string throw — works
  - Map literals {"key": value}, record literals {key: value}, and their respective access patterns (m["key"], r.key) — work consistently
  - Named imports (import { upper } from "std:strings") and aliased imports (import "std:json" as json) — both work

  Standard library:
  - std:strings — upper, lower, trim, split, replace, contains, join all work
  - std:json — json.parse, json.stringify work
  - std:collections — map, filter work; len works
  - std:math — math_idiv, math_floor, math_abs, math_sqrt, math_random all work
  - std:http — http.get(url) returns record with .status, .body, .ok — works
  - std:fs importable; read_file, write_file, exists, list_dir work (subject to allowed_paths)
  - std:hash — hash.sha256(data).to_hex() works
  - std:subprocess — sp.run(["echo", "hello"]) returns record with .stdout, .exit_code — works

  Coroutines (with required pattern):
  fn task() { print("hello") }
  spawn(coroutine(task))
  run_loop()          ← required; without this, spawn silently does nothing

  ---
  What struggles today

  No +=, -=, *= operators. Every mutation requires the full form:
  count = count + 1i
  Error when using +=: "Unexpected '=' in expression" — no hint that the operator doesn't exist.

  Closures cannot assign to outer let variables. Attempting outer_var = new_value inside a nested function fails with "Cannot add nil and int" (or similar)
  because the inner assignment creates a new local, shadowing the outer. Workaround: use a map with quoted keys and mutate via bracket notation:
  let state = {"count": 0i}
  fn increment() {
      state["count"] = state["count"] + 1i
  }

  recv() and sleep() only work inside a coroutine. Main script is not a coroutine. Calling recv(ch) from top-level produces "recv(channel) outside
  coroutine". Error message does not say "wrap your code in spawn(coroutine(fn() {...}))" or "call run_loop()".

  spawn() output is silently discarded without run_loop(). Spawned coroutines queue but do not execute unless run_loop() is called. A script that
  spawn(coroutine(task)) and exits produces no output and no error — the task never ran.

  std:collections.reduce has an unusual argument order. Signature is reduce(items, fn_value, initial) — not (items, initial, fn). Error when called in the
  expected order: "Cannot call non-function: 0" — no mention of argument order.

  No break or continue. Error is: '"break" is not supported; use a flag variable to exit a loop' — this is the most helpful error message in the language;
  at least it tells you what to do.

  ---
  What breaks today

  Integer division silently returns float. 6i / 2i evaluates to 3.0 (float), not 3 (int). math_is_float(6i / 2i) returns true. There is no warning. A user
  expecting integer types to stay integer after division is silently working with floats. Correct form: math_idiv(6i, 2i) → 3.

  Integer division by zero returns an error record, not an exception. 1i / 0i does not throw — it returns a Record with .kind = "math_error" and .message =
  "Integer division by zero". The value is assigned to the variable; subsequent operations on it may produce type errors with no reference to the original
  divide.

  throw {map}; catch e; e["key"] fails. When a map is thrown, the catch variable e is an error Record (with fields kind, message, payload, stack) — not the
  thrown value. Accessing e["key"] produces "Indexing is only supported on lists and maps" because e is a Record. Accessing e.key produces "Missing record
  field: key" because the Record's own fields don't include the user's key. The thrown map is at e.payload["key"]. There is no documentation inline at the
  error site.

  float / 0 silently returns inf. 1.0 / 0.0 produces inf with no error, no exception, and no warning. A user expecting an error from division by zero will
  continue computing with inf silently.

  String indexing fails entirely. s[0] on a string produces "Indexing is only supported on lists and maps". There is no character access, no slicing.
  Workaround: str_split(s, "") produces a character list, but this is not documented at the error site.

  ---
  First succeeding use case (specific)

  A new user can write and run this in under 10 minutes:

  import "std:json" as json

  let raw = "[1, 2, 3, 4, 5]"
  let numbers = json.parse(raw)

  let i = 0i
  let total = 0
  while (i < len(numbers)) {
      total = total + numbers[i]
      i = i + 1i
  }
  print("Sum: \(total)")
  print("Count: \(len(numbers))")

  Output: Sum: 15.0 / Count: 5. Runs immediately with nodus run script.nd. JSON parsing, list iteration, and string interpolation all work without traps.

  ---
  First blocking failure (specific)

  A new user writing a loop with a counter will try:

  let count = 0i
  for item in items {
      count += 1i      ← produces: "Unexpected '=' in expression"
  }

  The error names no operator, gives no fix, and points at column 12 (the = character) — not +=. The user must know independently that += doesn't exist and
  write count = count + 1i. This is the most common first failure.

  ---
  User Type 2 — Library / Tool Author

  What succeeds today

  Writing and distributing a .nd library via pip:
  Any pip-installable package that declares [project.entry-points."nodus.nd"] → my_package.nd:get_nd_root becomes importable as import "my-package". This
  pipeline is documented, implemented, and used by nodus-mcp.

  All .nd language features are available in library code. Functions, closures, maps, records, stdlib imports, try/catch — all work. Library code has no
  additional restrictions vs. script code.

  Factory functions and stateful closures work:
  fn make_counter() {
      let state = {"count": 0i}
      fn inc() {
          state["count"] = state["count"] + 1i
          return state["count"]
      }
      return inc
  }
  This is the canonical pattern for stateful objects. It works reliably.

  Host function registration (for tool authors embedding the runtime):
  rt = NodusRuntime()
  rt.register_function("db_query", lambda sql: [...], arity=1)
  Registered functions are callable from .nd as named builtins. Type conversion (Python list → Nodus list) is automatic.

  ---
  What struggles today

  No access control. All top-level functions in a .nd module are exported. There is no private, internal, or underscore convention that prevents callers
  from accessing implementation functions.

  No type declarations. Library functions cannot declare parameter types. A function that expects an integer will receive a float without warning; a
  function that expects a map will receive a record without warning. Defensive checking requires manual math_is_int(x) calls.

  No way to write a library that exports constants. Top-level let values are accessible via the module namespace in some cases but the behavior is
  inconsistent. The export keyword is accepted syntactically but its semantics for values vs. functions differ.

  Registering host functions that need to signal errors back to scripts requires care. A host function that returns a Python exception escapes the
  run_source() boundary as a live Python exception (see §Embedder: what breaks). A host function that wants to signal a script-catchable error must return a
  Nodus error Record (a Python dict with kind, message, payload shape). This is not documented in register_function() docs.

  ---
  What breaks today

  A library author cannot write a module that provides new language-level builtins with special behavior (lazy eval, macro-like arguments, custom dispatch).
  The only extension point for behavior that doesn't exist in the language is register_function() on the Python side. From within .nd, a library can only
  wrap existing builtins or call host functions.

  Async library functions cannot yield or use channels without the caller knowing to call run_loop(). A library that internally spawns a coroutine and
  expects the caller to receive its result via a channel cannot guarantee the caller knows to call run_loop() before reading the result. There is no
  structured way to signal "this call requires the scheduler to run" to the caller.

  ---
  First succeeding use case (specific)

  A competent user can write and ship a utility library in a few hours:

  // mylib/format.nd
  import "std:strings" as s

  fn title_case(text) {
      let words = str_split(text, " ")
      let result = []
      let i = 0i
      while (i < len(words)) {
          let w = words[i]
          if (len(w) > 0i) {
              let first = s.upper(str_split(w, "")[0])
              let rest = str_split(w, "")
              // ... join
          }
          i = i + 1i
      }
      return result
  }

  Publishing: add [project.entry-points."nodus.nd"] to pyproject.toml, pip install, and import "my-lib" works. For simple pure-function libraries with no
  async needs, this path is smooth.

  ---
  First blocking failure (specific)

  A library author who writes a function that spawns a background task and returns a channel for the caller to read from:
  fn start_worker() {
      let ch = channel()
      spawn(coroutine(fn() {
          // ... do work
          send(ch, result)
      }))
      return ch           ← caller receives channel but coroutine hasn't run yet
  }
  The caller calls recv(start_worker()) which blocks forever or errors with "recv outside coroutine". The library cannot tell the caller to call run_loop(),
  and run_loop() inside the library function itself doesn't help — the spawned coroutine needs the caller's scheduler turn. There is no supported way to
  write a library function that starts async work and returns a value from it in one call.

  ---
  User Type 3 — Embedder

  What succeeds today

  Standard instantiation with limits:
  rt = NodusRuntime(
      max_steps=100_000,
      timeout_ms=5_000,
      allowed_paths=["/data/scripts"],
      allow_input=False,
  )
  All four parameters work. run_source() returns {"ok": bool, "stdout": str, "error": dict | None} reliably for every execution that does not raise a host
  function exception.

  Host function injection:
  rt.register_function("db_query", my_fn, arity=1)
  Functions receive Python-native arguments (int, float, str, list, dict), return Python-native values. Type conversion is automatic.

  Passing data in via initial_globals and host_globals:
  r = rt.run_source(code, initial_globals={"config": {"debug": True}})
  r = rt.run_source(code, host_globals={"items": [1, 2, 3]})
  Both work. The difference: initial_globals are script-side variables; host_globals are read-only Python objects accessible by name.

  Getting values back via host function callback:
  results = {}
  rt.register_function("write_back", lambda k, v: results.update({k: v}), arity=2)
  rt.run_source('write_back("answer", 42i)')
  # results == {"answer": 42}
  This is the only reliable pattern for getting computed values out of a script.

  Error observation:
  r = rt.run_source(code)
  if not r["ok"]:
      err = r["error"]
      # err["type"], err["kind"], err["message"], err["line"], err["column"], err["stack"]
  Syntax errors, runtime errors, and resource limit errors all return ok=False with a structured dict. Sandbox limit errors (step count exceeded, timeout,
  stdout overflow) work correctly.

  Multi-call reuse:
  r1 = rt.run_source(code_a)  # fresh VM each time
  r2 = rt.run_source(code_b)  # fresh VM, different execution context
  Variable state is fresh per call. Scripts cannot read variables from previous calls.

  ---
  What struggles today

  No way to get a return value from a script. r["result"] is always None. Top-level return in a script raises "RETURN outside function". The only extraction
  mechanisms are: stdout capture (fragile, requires parsing), or host function callback. Neither is obvious from the run_source() signature.

  Host function exceptions escape as live Python exceptions. If a registered host function raises a Python exception, it propagates through run_source() as
  a live exception — not as {"ok": False, "error": {...}}. An embedder who wraps run_source() in a try/except will catch these, but their catch block
  receives the original Python exception without any information about which script line triggered it. The script's try/catch does not intercept it:

  # Host function:
  def bad(): raise ValueError("db timeout")
  rt.register_function("db_call", bad, arity=0)

  # Script: try { db_call() } catch e { print(e.message) }
  # Result: raises ValueError in Python, bypasses the script's catch block entirely

  GLOBAL_MEMORY_STORE persists across run_source() calls. Memory written via std:memory in one execution is readable by the next execution in the same
  process. Two separate NodusRuntime instances in the same process share the same memory store. Embedders who expect isolation between scripts must know to
  not use std:memory across calls.

  Spawned coroutine output requires the script to call run_loop(). If a host registers a function that internally spawns a coroutine, and the script doesn't
  call run_loop(), the coroutine never executes. The stdout result will be empty for that work. The embedder has no way to force the scheduler to run from
  outside the script.

  ---
  What breaks today

  Host function Python exceptions break the result contract. This is the embedding equivalent of a hard requirement: every registered host function must
  catch its own Python exceptions and return a value (or raise a structured HostFunctionError manually), or the embedder's run_source() will raise instead
  of returning. This is not documented in register_function(). It cannot be worked around from the host side without wrapping every registered function:

  def safe(fn):
      def wrapper(*args):
          try:
              return fn(*args)
          except Exception as e:
              return {"kind": "host_error", "message": str(e)}  # Nodus error record shape
      return wrapper
  rt.register_function("db_call", safe(my_db_fn), arity=1)

  Without this pattern, any host function that can raise will break the documented ok=False contract.

  Tenant isolation is not achievable. Two NodusRuntime instances in the same process share GLOBAL_MEMORY_STORE, AGENT_REGISTRY, and _GRAPH_VMS. A script
  running under one runtime can write a memory key that a script running under a different runtime reads. There is no namespace= parameter, no per-instance
  memory store, and no configuration option that isolates them. An embedder who needs tenant isolation (e.g., per-user script execution in a multi-user
  server) cannot achieve it without forking the runtime or patching the module-level singletons.

  ---
  First succeeding use case (specific)

  An embedder can get this working in under an hour from the embedding guide:

  from nodus.runtime.embedding import NodusRuntime

  rt = NodusRuntime(max_steps=100_000, timeout_ms=5_000)

  # Inject a host function
  logs = []
  rt.register_function("log", lambda msg: logs.append(str(msg)), arity=1)

  # Execute a script
  result = rt.run_source('''
  import "std:json" as json
  let data = json.parse("[1, 2, 3]")
  log("processing \(len(data)) items")
  let i = 0i
  while (i < len(data)) {
      log("item: \(data[i])")
      i = i + 1i
  }
  ''')

  print("ok:", result["ok"])
  print("logs:", logs)

  This runs correctly. The guide documents register_function, run_source, and the result shape. The example is realistic and takes less than 15 minutes from
  a fresh pip install nodus-lang.

  ---
  First blocking failure (specific)

  An embedder building a multi-tenant script execution service:

  # Per-request execution — one runtime per tenant
  def run_for_tenant(tenant_id: str, code: str):
      rt = NodusRuntime(max_steps=50_000, timeout_ms=2_000)
      result = rt.run_source(f'import "std:memory" as mem\n{code}')
      rt.shutdown()
      return result

  # Tenant A writes a secret
  run_for_tenant("A", 'import "std:memory" as mem\nmem.put("secret", "tenant-A-data")')

  # Tenant B reads it
  run_for_tenant("B", 'import "std:memory" as mem\nprint(mem.get("secret"))')
  # Prints: tenant-A-data

  Tenant B reads Tenant A's memory. shutdown() does not clear GLOBAL_MEMORY_STORE. There is no API to clear it, scope it, or replace it. The only workaround
  is to never use std:memory (or std:agent) in any script that runs in a multi-tenant context — but this is not documented as a requirement and is not
  obvious from the NodusRuntime API surface.

  ---
  Cross-Cutting Findings

  Documentation gaps:

  1. run_loop() is required for spawn() to have any effect. Getting started docs mention it, but coroutine examples without it silently produce no output
  and no error.
  2. catch e binds an error Record (.kind, .message, .payload, .stack), not the thrown value. Thrown maps are at e.payload. This is discoverable only by
  experiment; error messages at access time say "Indexing is only supported on lists and maps" with no reference to .payload.
  3. std:memory persists across run_source() calls in the same process. Documented nowhere in NodusRuntime API docs as a caveat.
  4. Host function Python exceptions escape as live exceptions. register_function() docs say nothing about this. Embedders discover it only when a host
  function fails in production.

  Error messages that don't point at the source:

  ┌──────────────────────────────┬──────────────────────────────────────────────┬──────────────────────────────────────────────────┐
  │     What the user writes     │             What the error says              │             What they needed to know             │
  ├──────────────────────────────┼──────────────────────────────────────────────┼──────────────────────────────────────────────────┤
  │ x += 1i                      │ Unexpected '=' in expression                 │ += doesn't exist; use x = x + 1i                 │
  ├──────────────────────────────┼──────────────────────────────────────────────┼──────────────────────────────────────────────────┤
  │ import "std:channel"         │ Import not found: std:channel (tried ...)    │ channel() is a builtin, not a module             │
  ├──────────────────────────────┼──────────────────────────────────────────────┼──────────────────────────────────────────────────┤
  │ j.encode(data)               │ Missing module export: encode                │ The function is j.stringify(data)                │
  ├──────────────────────────────┼──────────────────────────────────────────────┼──────────────────────────────────────────────────┤
  │ recv(ch) at top level        │ recv(channel) outside coroutine              │ Wrap in spawn(coroutine(fn() {...})); run_loop() │
  ├──────────────────────────────┼──────────────────────────────────────────────┼──────────────────────────────────────────────────┤
  │ c.reduce(items, 0i, fn)      │ Cannot call non-function: 0                  │ Argument order is (items, fn, initial)           │
  ├──────────────────────────────┼──────────────────────────────────────────────┼──────────────────────────────────────────────────┤
  │ throw map; catch e; e["key"] │ Indexing is only supported on lists and maps │ Access thrown value as e.payload["key"]          │
  └──────────────────────────────┴──────────────────────────────────────────────┴──────────────────────────────────────────────────┘

  Concepts where the mental model doesn't match behavior:

  1. "Integer arithmetic with the i suffix stays integer." False. 6i / 2i = 3.0 (float). Division always produces float. math_idiv produces int. This
  diverges from every major language.
  2. "Variables are isolated between run_source() calls." True for local variables. False for std:memory and std:agent state, which persist in process-level
  singletons across all calls.
  3. "spawn() runs a concurrent task." True if run_loop() is called. False otherwise — the task is queued but never executed, silently.
  4. "ok=False means run_source() returned an error dict." True for language errors and resource limits. False when a registered host function raises a
  Python exception — in that case run_source() raises instead.

  ---
  Summary Table

  ┌───────────┬───────────────────────────────────────────────────┬───────────────────────────────────┬───────────────────────────────────────────────┐
  │           │                   Script Author                   │          Library Author           │                   Embedder                    │
  ├───────────┼───────────────────────────────────────────────────┼───────────────────────────────────┼───────────────────────────────────────────────┤
  │ Can       │ Variables, functions, for/in,                     │ Pure function libraries,          │ NodusRuntime(limits), register_function,      │
  │ reliably  │ std:strings/json/math/http/fs, recursion,         │ pip-distributable via             │ run_source, initial_globals/host_globals,     │
  │ do        │ try/catch with string throw, string               │ entry-point, factory closures,    │ ok=False error dicts, step/timeout limits     │
  │           │ interpolation, first-class functions              │ host function registration        │                                               │
  ├───────────┼───────────────────────────────────────────────────┼───────────────────────────────────┼───────────────────────────────────────────────┤
  │ First     │ JSON array transform in a while loop, string      │ Utility library of pure functions │ register_function + run_source with           │
  │ success   │ processing with std:strings — 10 min              │  distributed via pip entry-point  │ initial_globals — under 1 hour from guide     │
  ├───────────┼───────────────────────────────────────────────────┼───────────────────────────────────┼───────────────────────────────────────────────┤
  │ First     │ += produces "Unexpected '=' in expression" with   │ Async library function that       │ Host function Python exception escapes as     │
  │ blocker   │ no hint                                           │ returns a value from a spawned    │ live exception, breaking ok=False contract    │
  │           │                                                   │ coroutine — no supported pattern  │                                               │
  ├───────────┼───────────────────────────────────────────────────┼───────────────────────────────────┼───────────────────────────────────────────────┤
  │           │ Medium — core language works well; integer        │ Medium-High — pure function       │ Medium — basic embedding works from docs;     │
  │ Overall   │ division type, catch payload, no += cause         │ libraries work; anything async or │ host fn exception escape and singleton        │
  │ friction  │ repeated surprises                                │  type-safe requires workarounds   │ isolation gaps require reading source         │
  │           │                                                   │ with no clear pattern             │                                               │
  └───────────┴───────────────────────────────────────────────────┴───────────────────────────────────┴───────────────────────────────────────────────┘
