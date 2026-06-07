# Security Model Audit

**Objective:** Establish the factual security posture of this language runtime —
where enforcement lives, how it is applied, whether it can be bypassed, and
what the failure mode is when it is absent.

Applies to: any language runtime that executes untrusted or partially-trusted code.

---

## Rules

- Describe what EXISTS. Do not suggest improvements or redesigns.
- Every enforcement claim must name the module, function, or mechanism that
  enforces it.
- "Partial" requires an explanation of what is enforced and what is not.
- YES / PARTIAL / NO at the end of each section.

---

## Section 1 — Sandbox Inventory

List every enforcement boundary that exists in the runtime. For each:

- What does it prevent?
- Where in the code is it enforced? (file:function or file:line)
- Does it apply in CLI mode, embedded mode, or both?
- Can it be disabled by the script itself?

Common categories (add or remove as appropriate):

| Boundary | What it prevents | Where enforced | CLI / Embedded / Both | Script-bypassable |
|----------|-----------------|----------------|----------------------|-------------------|
| Filesystem access | | | | |
| Network access | | | | |
| Subprocess invocation | | | | |
| Environment variable read | | | | |
| Memory/CPU limits | | | | |
| Import restrictions | | | | |
| Host function access | | | | |

---

## Section 2 — Auth Flow Trace

Trace the path of a request from entry point to execution, for each mode.

### CLI mode

```
nodus run script.nd
→ [step 1: what happens here?]
→ [step 2]
→ [VM begins executing]
→ [first builtin call]
```

At each step: is there any authentication or authorization check? Name it or note its absence.

### Embedded mode

```
NodusRuntime.run_source(code) [or equivalent]
→ [step 1]
→ [VM begins executing]
→ [host function call]
```

At each step: is there any authentication or authorization check? Name it or note its absence.

### Serve / HTTP mode (if applicable)

```
POST /run
→ [authentication layer?]
→ [authorization check?]
→ [code string submitted to VM]
```

Is the HTTP endpoint authenticated by default, or does auth require explicit configuration?

---

## Section 3 — Layer Classification

For each security concern, state where responsibility lives.

| Concern | Language/VM | Stdlib | Embedding API | Host application | Not enforced |
|---------|-------------|--------|---------------|-----------------|--------------|
| Filesystem sandboxing | | | | | |
| Network restrictions | | | | | |
| Request authentication | | | | | |
| Tenant isolation | | | | | |
| Capability escalation prevention | | | | | |
| Audit logging | | | | | |
| Resource exhaustion prevention | | | | | |

---

## Section 4 — Violations and Gaps

For each of the following, state: enforced / bypassable / not present.

If bypassable, describe the bypass path (not to enable it, but to document the gap).

- Can a script read files outside a declared allowed path?
- Can a script open a network connection the host did not configure?
- Can a script invoke arbitrary subprocesses?
- Can a script exhaust memory without the host being able to stop it?
- Can a script run indefinitely without the host being able to stop it?
- Can a script read or modify other scripts' runtime state?
- Can a host function registration be overridden by a script?

For each gap: is it documented? Is there a known workaround?

---

## Section 5 — User / Tenant Context Propagation

How does identity travel through the execution system?

- Is there a concept of a "current user" or "current tenant" in the runtime?
- If so, where is it set and where can it be read?
- Can a script query its own execution context (who am I, what am I allowed)?
- Is identity propagated into async/coroutine execution?
- Can identity be spoofed by a script?

**Summary:** YES (full propagation) / PARTIAL (propagated but escapable) / NO (no identity concept in runtime)

---

## Section 6 — Enforcement Consistency

Is the same enforcement applied uniformly across all entry points?

- Are sandbox rules identical for CLI, embedded, and serve modes?
- Are there any features available in one mode but not another that create a
  privilege difference?
- Does a difference in default configuration between modes create a security gap?
  (e.g. sandbox off by default in embedded, on by default in CLI)

List any inconsistencies found.

---

## Section 7 — Audit and Observability

Can a host reconstruct what happened during a script execution from logs or trace data?

- Is there an execution trace that records which builtins were called?
- Is there a log of which filesystem paths were accessed?
- Is there a record of which host functions were invoked and with what arguments?
- Can the host receive a callback on every capability use (hook pattern)?

**Summary:** YES / PARTIAL / NO

---

## Current State Summary

Answer for each: **YES / PARTIAL / NO**

| Question | Answer |
|----------|--------|
| Safe to run untrusted scripts by default? | |
| Auth required before any code executes (serve mode)? | |
| Filesystem sandbox enforced without host configuration? | |
| Network access restricted without host configuration? | |
| Resource exhaustion (CPU/memory) bounded by default? | |
| Tenant isolation possible with current API? | |
| All enforcement consistent across CLI, embedded, serve? | |
| Security gaps documented publicly? | |

---

## Final Verdict

One sentence: What is the honest security posture of this runtime for an embedder
who follows the documented configuration but does not read the source?

---

**Rules:**
- Do not suggest improvements.
- PARTIAL requires: what is enforced, what is not, and where the gap is.
- Source code locations must be specific enough that a reader can verify them.




Security Model Audit — Nodus v4.0.0 Runtime - 6/6/26 - 11:55pm 

  ---
  Section 1 — Sandbox Inventory

  Enforcement mechanism: _ensure_path_allowed

  The central enforcement function is VM._ensure_path_allowed() at vm.py:544:

  def _ensure_path_allowed(self, path: str, op_name: str) -> None:
      normalized = os.path.normcase(os.path.abspath(path))
      if self.allowed_paths is None:
          if self.fs_root is not None and not self._path_within_root(normalized, self.fs_root):
              self.runtime_error("sandbox", f"{op_name} blocked: path {path!r} escapes the project root")
          return
      if not self.allowed_paths:
          self.runtime_error("sandbox", f"{op_name} is not permitted")
      for root in self.allowed_paths:
          if self._path_within_root(normalized, root):
              return
      self.runtime_error("sandbox", f"{op_name} blocked for path: {path!r}")

  This function is the sole enforcement point for all path-based restrictions. Two distinct modes:
  1. allowed_paths is None and fs_root is not None: allows any path within fs_root
  2. allowed_paths is a non-empty list: allows only paths within listed roots

  Boundary table

  ┌─────────────────┬─────────────────────────────┬────────────────────────────────────────────────────────┬────────────────────┬──────────────────────┐
  │    Boundary     │      What it prevents       │                     Where enforced                     │   CLI / Embedded   │  Script-bypassable   │
  ├─────────────────┼─────────────────────────────┼────────────────────────────────────────────────────────┼────────────────────┼──────────────────────┤
  │ Filesystem      │ Access outside              │ vm.py:544 (_ensure_path_allowed), called from          │ Both               │ NO — enforced before │
  │ read/write      │ allowed_paths or fs_root    │ io.py:29,57,82,95,120,143,166,189                      │                    │  the OS call         │
  ├─────────────────┼─────────────────────────────┼────────────────────────────────────────────────────────┼────────────────────┼──────────────────────┤
  │ Filesystem via  │ Subprocess stdout/stderr    │                                                        │                    │                      │
  │ subprocess      │ redirect outside allowed    │ subprocess_module.py:150,164,172,329                   │ Both               │ NO — checked before  │
  │ redirect        │ paths; subprocess cwd       │                                                        │                    │ subprocess.Popen     │
  │                 │ outside allowed paths       │                                                        │                    │                      │
  ├─────────────────┼─────────────────────────────┼────────────────────────────────────────────────────────┼────────────────────┼──────────────────────┤
  │ Subprocess      │ — nothing —                 │ Not enforced                                           │ Both               │ NOT APPLICABLE — not │
  │ command binary  │                             │                                                        │                    │  enforced            │
  ├─────────────────┼─────────────────────────────┼────────────────────────────────────────────────────────┼────────────────────┼──────────────────────┤
  │ Network access  │ — nothing —                 │ Not enforced                                           │ Both               │ NOT APPLICABLE — not │
  │ (HTTP)          │                             │                                                        │                    │  enforced            │
  ├─────────────────┼─────────────────────────────┼────────────────────────────────────────────────────────┼────────────────────┼──────────────────────┤
  │ Environment     │ — nothing —                 │ Not enforced                                           │ Both               │ NOT APPLICABLE — not │
  │ variable access │                             │                                                        │                    │  enforced            │
  ├─────────────────┼─────────────────────────────┼────────────────────────────────────────────────────────┼────────────────────┼──────────────────────┤
  │ Instruction     │ Infinite loops; excessive   │ vm.py:record_instruction(), calls record_instruction() │                    │ NO — checked inside  │
  │ count (CPU      │ computation                 │  every instruction, checks max_steps every 100         │ Both               │ the dispatch loop    │
  │ proxy)          │                             │ instructions                                           │                    │                      │
  ├─────────────────┼─────────────────────────────┼────────────────────────────────────────────────────────┼────────────────────┼──────────────────────┤
  │ Wall-clock time │ Long-running scripts        │ vm.py:record_instruction(), deadline =                 │ Both (different    │ NO — checked in      │
  │                 │ blocking the host           │ time.monotonic() + timeout_ms/1000                     │ defaults — see §6) │ dispatch loop        │
  ├─────────────────┼─────────────────────────────┼────────────────────────────────────────────────────────┼────────────────────┼──────────────────────┤
  │ Call stack      │ Stack overflow from         │ vm.py:1762 — "Call stack overflow" sandbox error;      │ Both               │ NO                   │
  │ depth           │ infinite recursion          │ vm.py:2379                                             │                    │                      │
  ├─────────────────┼─────────────────────────────┼────────────────────────────────────────────────────────┼────────────────────┼──────────────────────┤
  │                 │                             │                                                        │ CLI via            │                      │
  │ Stdout volume   │ Unbounded print output      │ tooling/sandbox.py:capture_output() — intercepts       │ run_file();        │ NO                   │
  │                 │                             │ sys.stdout, truncates at MAX_STDOUT_CHARS              │ Embedded via       │                      │
  │                 │                             │                                                        │ run_source()       │                      │
  ├─────────────────┼─────────────────────────────┼────────────────────────────────────────────────────────┼────────────────────┼──────────────────────┤
  │ stdin blocking  │ Scripts calling input() in  │ embedding.py — allow_input=False default replaces      │ Embedded only      │ NO                   │
  │                 │ embedded context            │ input() with a function that raises                    │                    │                      │
  ├─────────────────┼─────────────────────────────┼────────────────────────────────────────────────────────┼────────────────────┼──────────────────────┤
  │ Memory          │ — nothing —                 │ Not enforced                                           │ Both               │ NOT APPLICABLE — not │
  │ allocation      │                             │                                                        │                    │  enforced            │
  ├─────────────────┼─────────────────────────────┼────────────────────────────────────────────────────────┼────────────────────┼──────────────────────┤
  │ Import path     │ Relative imports escaping   │ module_loader.py:204 — _loading set +                  │                    │                      │
  │ traversal       │ project root                │ _circular_import_error(); path normalization against   │ Both               │ NO                   │
  │                 │                             │ project root                                           │                    │                      │
  ├─────────────────┼─────────────────────────────┼────────────────────────────────────────────────────────┼────────────────────┼──────────────────────┤
  │ Builtin         │ Scripts redefining built-in │ Scripts have no mechanism to modify vm.builtins;       │                    │                      │
  │ override from   │  function names             │ register_function() (Python-side only) blocks names in │ Both               │ NO                   │
  │ script          │                             │  BUILTIN_NAMES (embedding.py:343)                      │                    │                      │
  └─────────────────┴─────────────────────────────┴────────────────────────────────────────────────────────┴────────────────────┴──────────────────────┘

  ---
  Section 2 — Auth Flow Trace

  CLI mode

  nodus run script.nd
  → cli.py:main() — parses --allow-paths (or reads NODUS_ALLOWED_PATHS env var via _resolve_allowed_paths())
  → No authentication check.
  → runner.py:run_file() — computes fs_root from project root or CWD (runner.py:181–189)
  → VM constructed with allowed_paths=None, fs_root=project_root
  → sandbox.py:configure_vm_limits() — sets max_steps=10_000_000, deadline=now+0.2s
  → Module loader compiles source; imports resolved against project root
  → No authentication check.
  → VM.execute() begins dispatching opcodes
  → First fs.* builtin call → _ensure_path_allowed() checks against fs_root
  → No authentication check at any step.

  Authentication: absent at every step. CLI assumes the invoking OS user is trusted.

  Embedded mode

  NodusRuntime.run_source(code)
  → embedding.py:run_source() — resolves max_steps, timeout_ms from instance defaults
  → No authentication check.
  → VM constructed with host-supplied allowed_paths (default: None → unrestricted)
  → sandbox.py:configure_vm_limits() — applies host-supplied limits (timeout_ms default: None → no deadline)
  → No authentication check.
  → VM.execute() begins dispatching opcodes
  → First builtin call — fs: _ensure_path_allowed() (enforced if allowed_paths set); http: no check; subprocess command: no check; env: no check
  → Host function call → Python callable executes directly in host process
  → No authentication or authorization check at any step.

  Authentication: absent. Authorization is entirely the host's responsibility. The runtime provides no callback or hook to approve individual capability
  uses at runtime.

  Serve / HTTP mode

  POST /execute
  → server.py:do_POST() at line 1152 — calls is_authorized(request.headers.get("Authorization"))
  → is_authorized() at line 453:
       if not self.auth_token:   # ← auth_token defaults to None
           return True           # ← all requests authorized when no token configured
       if not auth_header: return False
       return auth_header.strip() == f"Bearer {self.auth_token}"
  → If authorized: _read_json(self) → service.execute(payload)
  → VM constructed with server's allowed_paths (default: None → unrestricted unless --allow-paths set)
  → VM executes; same enforcement as embedded mode above

  Auth is optional by default. auth_token defaults to None in RuntimeService.__init__() (server.py:340). is_authorized() returns True for any request when
  no token is configured. To enable auth: --auth-token CLI flag or NODUS_SERVER_TOKEN env var (cli.py:1669, cli.py:97). The FastAPI variant (server.py:1278)
  only registers the auth_middleware if service.auth_token is truthy — no middleware = no check.

  Auth scheme when enabled: Bearer token, constant-time comparison against a pre-configured static string. No session tokens, no OAuth, no JWT validation.

  ---
  Section 3 — Layer Classification

  ┌────────────────────────────┬─────────────────────────────────┬────────────┬────────────────────────┬─────────────────┬───────────────────────────┐
  │          Concern           │           Language/VM           │   Stdlib   │     Embedding API      │      Host       │       Not enforced        │
  │                            │                                 │            │                        │   application   │                           │
  ├────────────────────────────┼─────────────────────────────────┼────────────┼────────────────────────┼─────────────────┼───────────────────────────┤
  │                            │                                 │ Called     │ allowed_paths          │ Can configure   │                           │
  │ Filesystem sandboxing      │ ✓ vm._ensure_path_allowed()     │ from fs    │ parameter controls it  │ allowed_paths   │ —                         │
  │                            │                                 │ builtins   │                        │                 │                           │
  ├────────────────────────────┼─────────────────────────────────┼────────────┼────────────────────────┼─────────────────┼───────────────────────────┤
  │ Network restrictions       │ —                               │ —          │ —                      │ —               │ ✓ No layer enforces it    │
  ├────────────────────────────┼─────────────────────────────────┼────────────┼────────────────────────┼─────────────────┼───────────────────────────┤
  │                            │                                 │            │                        │ ✓ Host must     │                           │
  │ Request authentication     │ —                               │ —          │ —                      │ wrap            │ —                         │
  │                            │                                 │            │                        │ run_source()    │                           │
  ├────────────────────────────┼─────────────────────────────────┼────────────┼────────────────────────┼─────────────────┼───────────────────────────┤
  │                            │                                 │            │                        │                 │ ✓ GLOBAL_MEMORY_STORE is  │
  │ Tenant isolation (memory)  │ —                               │ —          │ —                      │ —               │ shared across all VM      │
  │                            │                                 │            │                        │                 │ instances                 │
  ├────────────────────────────┼─────────────────────────────────┼────────────┼────────────────────────┼─────────────────┼───────────────────────────┤
  │ Capability escalation      │ ✓ Builtins cannot be overridden │ —          │ ✓ register_function()  │ —               │ Subprocess/env/HTTP caps  │
  │ prevention                 │  from script                    │            │ blocks builtin names   │                 │ uncontrolled              │
  ├────────────────────────────┼─────────────────────────────────┼────────────┼────────────────────────┼─────────────────┼───────────────────────────┤
  │                            │ ✓ Event bus emits coroutine     │            │ add_sink() lets host   │                 │ Per-builtin-call          │
  │ Audit logging              │ lifecycle, errors, graph events │ —          │ attach observers       │ —               │ (fs/http/subprocess) not  │
  │                            │                                 │            │                        │                 │ emitted                   │
  ├────────────────────────────┼─────────────────────────────────┼────────────┼────────────────────────┼─────────────────┼───────────────────────────┤
  │ Resource exhaustion        │ ✓ record_instruction(),         │            │ Per-call and           │ Can override    │                           │
  │ (CPU/time/stack/stdout)    │ deadline, stack depth check,    │ —          │ per-runtime limit      │ defaults        │ Memory not covered        │
  │                            │ stdout cap                      │            │ params                 │                 │                           │
  └────────────────────────────┴─────────────────────────────────┴────────────┴────────────────────────┴─────────────────┴───────────────────────────┘

  ---
  Section 4 — Violations and Gaps

  Can a script read files outside a declared allowed path?

  Via read_file(): ENFORCED. _ensure_path_allowed() is called at io.py:29 before the open() call. Traversal via ../ is blocked by os.path.abspath()
  normalization at vm.py:545.

  Via subprocess: BYPASSABLE. subprocess.run(["cat", "/etc/passwd"]) — the binary path (/usr/bin/cat) and its arguments are not checked by
  _ensure_path_allowed. Only the subprocess cwd and redirect file paths are checked (subprocess_module.py:150,164,172). A script with access to the
  subprocess builtin can read any file the host OS user can read.

  Via symlink in project root: BYPASSABLE. SECURITY_POSTURE.md:164 — "A symlink inside the project root that points outside can be used to bypass
  containment." The _path_within_root() check at vm.py:538 uses os.path.commonpath on the resolved path, so symlinks are followed before the check.

  Documented: YES — SECURITY_POSTURE.md §5 states "Subprocess execution: allows arbitrary process execution." The symlink bypass is noted at §9.

  ---
  Can a script open a network connection the host did not configure?

  NOT PRESENT. http_module.py contains no call to _ensure_path_allowed() or any equivalent. The http.get(), http.post(), http.stream(), and http.request()
  functions call httpx directly. No allowed-hosts list, no network restriction parameter, no host callback before the connection is made.

  Workaround: The host can omit the HTTP builtin by not including std:http in the project, but there is no supported mechanism to do this via the embedding
  API without forking the builtin registry.

  Documented: YES — SECURITY_POSTURE.md §5: "Network access: std:http (v4.0+) allows arbitrary outbound HTTP. There is no allowed_hosts restriction in
  v3.0.2."

  ---
  Can a script invoke arbitrary subprocesses?

  YES. subprocess.run(["rm", "-rf", "/data"]) — the argv_or_cmd argument to _do_run() at subprocess_module.py:129 is passed directly to subprocess.Popen.
  Only cwd (line 150) and stdout/stderr redirect paths (lines 164, 172) are validated against allowed_paths. The subprocess binary, its arguments, and its
  inherited file descriptors are unrestricted.

  subprocess.shell(cmd) makes this worse: is_shell=True passes cmd to the OS shell, enabling all shell expansion and redirection.

  Documented: YES — SECURITY_POSTURE.md §5: "The process itself is not sandboxed (no allow_subprocess flag; if the stdlib is available, it is available)."

  ---
  Can a script exhaust memory without the host being able to stop it?

  YES. config.py defines no MAX_MEMORY limit. Python's GC imposes no script-level limit. A script can execute:
  let huge = []
  while (true) { huge = huge + [0i] }
  This will allocate unbounded list memory until the host process receives an MemoryError or the OS OOM killer terminates it. The step limit and timeout
  limit CPU time but do not bound heap allocation.

  Documented: YES — SECURITY_POSTURE.md §5: "Memory exhaustion: No limit on heap allocation."

  ---
  Can a script run indefinitely without the host being able to stop it?

  PARTIAL. The step limit (MAX_STEPS=10_000_000) and timeout (EXECUTION_TIMEOUT_MS=200 in CLI) bound pure computation. Both are enforced in
  record_instruction() at vm.py.

  Gap 1: When NodusRuntime() is created with no arguments, timeout_ms=None — no deadline. The step limit applies, but 10,000,000 steps of I/O-heavy code
  (HTTP, subprocess) can take arbitrarily long because I/O wait time does not advance the step counter.

  Gap 2: time.sleep() in scheduler.py:185 advances wall clock without advancing vm.deadline only when explicitly compensated: vm.deadline +=
  time.monotonic() - _t0. This means a script that triggers sleep-then-wake cycles can extend its wall clock lifetime past the nominal timeout_ms because
  the scheduler compensates for its own sleep overhead.

  ---
  Can a script read or modify other scripts' runtime state?

  YES. GLOBAL_MEMORY_STORE = MemoryStore() at memory_runtime.py:47 is a process-level singleton. Every std:memory read/write operation from any script in
  any NodusRuntime instance in the same process shares this store. Script A can read keys written by Script B if both run in the same process.

  YES via AGENT_REGISTRY. AGENT_REGISTRY: dict[str, dict] = {} at agent_runtime.py:10 is also a process-level singleton. Agent registrations from one
  execution are visible to all subsequent executions.

  Not documented explicitly as a multi-tenant limitation in SECURITY_POSTURE.md. The doc covers CLI and embedded but does not address multiple concurrent
  NodusRuntime instances sharing state.

  ---
  Can a host function registration be overridden by a script?

  NO. Scripts have no mechanism to modify vm.builtins. The Python-side register_function() (embedding.py:343) prevents registration of any name in
  BUILTIN_NAMES, so host functions cannot shadow builtins. Scripts cannot call register_function() — it is a Python method, not a language builtin. Scripts
  can call host functions by name but cannot add, remove, or replace entries in the builtin table.

  ---
  Section 5 — User / Tenant Context Propagation

  Identity fields on the VM (vm.py:282–284):
  self.session_id: str | None = None
  self.trace_id: str | None = None

  Where set:
  - NodusRuntime.set_trace_id(id) at embedding.py:370 — sets _pending_trace_id, applied to VM at run_source() start (embedding.py:576)
  - session_id is set by the server mode (services/server.py) when managing sessions; in embedded mode it defaults to None unless the host sets it directly
  on the VM via last_vm.session_id (internal access)

  Where readable from scripts: std:identity module exposes two functions:
  - identity.trace_id() → calls runtime_trace_id() → returns vm.trace_id (identity_module.py:7)
  - identity.session_id() → calls runtime_session_id() → returns vm.session_id (identity_module.py:11)

  Propagation to spawned coroutines: All coroutines share the same VM instance. vm.trace_id and vm.session_id are fields on the VM object, not on the
  coroutine. A spawned coroutine reading identity.trace_id() reads from the same VM field as the main coroutine. Identity IS propagated — not by copying to
  the coroutine, but because all coroutines execute on the same VM.

  Spoofing by script: Scripts can READ session_id and trace_id but cannot write to them. There is no set_trace_id() or set_session_id() builtin. Scripts
  cannot spoof their own identity fields.

  Tenant data isolation: ABSENT. Two scripts running as "different tenants" in separate NodusRuntime instances share GLOBAL_MEMORY_STORE and AGENT_REGISTRY.
  A script that knows another tenant's memory key can read or overwrite that tenant's data. There is no per-instance or per-session memory namespace.

  Summary: PARTIAL — trace ID and session ID are propagated consistently through async execution and readable by scripts but not writable. Tenant data
  isolation (memory, agents) is not enforced by any mechanism in the runtime.

  ---
  Section 6 — Enforcement Consistency

  Inconsistencies found

  1. Filesystem restriction defaults differ between CLI and embedded.

  ┌───────────────────────────┬─────────────────────────────────────────┬───────────────────────┬─────────────────────────────────────────┐
  │           Mode            │             fs_root default             │ allowed_paths default │                 Effect                  │
  ├───────────────────────────┼─────────────────────────────────────────┼───────────────────────┼─────────────────────────────────────────┤
  │ CLI (nodus run)           │ Project root or CWD (runner.py:181–189) │ None                  │ All fs.* ops restricted to project root │
  ├───────────────────────────┼─────────────────────────────────────────┼───────────────────────┼─────────────────────────────────────────┤
  │ Embedded (NodusRuntime()) │ None                                    │ None                  │ All fs.* ops unrestricted               │
  └───────────────────────────┴─────────────────────────────────────────┴───────────────────────┴─────────────────────────────────────────┘

  _ensure_path_allowed() when both are None: if self.allowed_paths is None: ... return — the function returns immediately without any check (vm.py:546–551).
  An embedder who creates NodusRuntime() with no arguments and does not set allowed_paths gets an unrestricted filesystem. A CLI user gets project-root
  containment automatically.

  2. Wall-clock timeout defaults differ.

  ┌──────────────────────────┬────────────────────────────────────────────────────────────────────────────┬─────────────────────────────────────────────┐
  │           Mode           │                             timeout_ms default                             │                   Result                    │
  ├──────────────────────────┼────────────────────────────────────────────────────────────────────────────┼─────────────────────────────────────────────┤
  │ CLI (nodus run)          │ EXECUTION_TIMEOUT_MS = 200 ms                                              │ Script killed after 200ms wall clock        │
  ├──────────────────────────┼────────────────────────────────────────────────────────────────────────────┼─────────────────────────────────────────────┤
  │ Embedded                 │ None                                                                       │ No deadline; script bounded only by step    │
  │ (NodusRuntime())         │                                                                            │ count                                       │
  ├──────────────────────────┼────────────────────────────────────────────────────────────────────────────┼─────────────────────────────────────────────┤
  │ CLI (nodus serve)        │ Inherits server-level setting; no per-script timeout unless --time-limit   │ Potentially unbounded per execution         │
  │                          │ passed                                                                     │                                             │
  └──────────────────────────┴────────────────────────────────────────────────────────────────────────────┴─────────────────────────────────────────────┘

  3. Auth in serve mode is opt-in, not opt-out.

  is_authorized() at server.py:453–455 returns True unconditionally when auth_token is None. An operator who starts nodus serve --host 0.0.0.0 without
  --auth-token exposes unauthenticated code execution to any host that can reach the port. The SECURITY_POSTURE.md §7 warns against internet exposure
  without a reverse proxy, but the default behavior is unauthenticated.

  4. Subprocess availability is identical across modes.

  There is no allow_subprocess flag in NodusRuntime. The subprocess builtin is either present (always, in all modes) or removed (requires not importing
  std:subprocess in the script). This means an embedder cannot disable subprocess access via the public API — only by preventing the script from importing
  the module, which is not controllable via the embedding API.

  5. NODUS_ALLOWED_PATHS env var applies in CLI but not embedded.

  cli.py:76–81 reads NODUS_ALLOWED_PATHS as a fallback for --allow-paths. NodusRuntime does not read this env var — an operator who configures
  NODUS_ALLOWED_PATHS in the environment for CLI protection gets no equivalent protection in embedded mode without passing allowed_paths explicitly.

  ---
  Section 7 — Audit and Observability

  What the event bus records

  RuntimeEventBus at runtime/runtime_events.py:50. Sinks are attached via add_sink() at line 97. Events carry timestamp, trace_id, execution_unit_id,
  coroutine_id, name, and a data dict.

  Emitted by the scheduler (scheduler.py):
  - coroutine_spawn, coroutine_resume, coroutine_complete, coroutine_sleep, coroutine_wake, coroutine_yield

  Emitted by the VM (vm.py):
  - runtime_error, vm_exception
  - graph_plan_created, goal_action_start, goal_action_fail, goal_action_complete (domain events)
  - runtime_adapter_event_data enriches events with workflow_id, goal_id, step_name, session_id, trace_id

  Emitted by coroutine builtins (builtins/coroutine.py):
  - channel_send, channel_wake, channel_close, channel_recv

  What the event bus does NOT record

  - read_file() calls and paths accessed — io.py emits no events
  - write_file() calls — io.py emits no events
  - http.get() calls and URLs — http_module.py emits no events
  - subprocess.run() calls and commands — subprocess_module.py emits no events
  - env.get() / env.set() calls — env.py emits no events
  - Individual host function invocations
  - Memory store reads/writes

  Host observability hooks

  The event bus add_sink() provides a streaming hook, but what it streams is coroutine lifecycle and domain graph events — not capability use. There is no
  per-builtin-call hook, no pre/post-call interceptor for builtins, and no way to audit "which filesystem paths did this script touch" from event data
  alone.

  Summary: PARTIAL — coroutine lifecycle and graph orchestration are observable. Capability use (filesystem access, network calls, subprocess invocations,
  environment reads) is not observable from the event bus. A host cannot reconstruct the full capability surface used by a script from event log data.

  ---
  Current State Summary

  ┌───────────────────────────────────────┬─────────────────────────────────────────────────────────────────────────────────────────────────────────────┐
  │               Question                │                                                   Answer                                                    │
  ├───────────────────────────────────────┼─────────────────────────────────────────────────────────────────────────────────────────────────────────────┤
  │ Safe to run untrusted scripts by      │ NO — embedded NodusRuntime() defaults provide no filesystem restriction, no timeout, and unrestricted       │
  │ default?                              │ network and subprocess access                                                                               │
  ├───────────────────────────────────────┼─────────────────────────────────────────────────────────────────────────────────────────────────────────────┤
  │ Auth required before any code         │ NO — auth is opt-in via --auth-token or NODUS_SERVER_TOKEN; default is unauthenticated                      │
  │ executes (serve mode)?                │                                                                                                             │
  ├───────────────────────────────────────┼─────────────────────────────────────────────────────────────────────────────────────────────────────────────┤
  │ Filesystem sandbox enforced without   │ PARTIAL — CLI auto-restricts to project root; embedded requires explicit allowed_paths                      │
  │ host configuration?                   │                                                                                                             │
  ├───────────────────────────────────────┼─────────────────────────────────────────────────────────────────────────────────────────────────────────────┤
  │ Network access restricted without     │ NO — no enforcement in any mode                                                                             │
  │ host configuration?                   │                                                                                                             │
  ├───────────────────────────────────────┼─────────────────────────────────────────────────────────────────────────────────────────────────────────────┤
  │ Resource exhaustion (CPU/memory)      │ PARTIAL — instruction count and wall-clock time are bounded in CLI (200ms default); memory is never         │
  │ bounded by default?                   │ bounded; embedded has no timeout by default                                                                 │
  ├───────────────────────────────────────┼─────────────────────────────────────────────────────────────────────────────────────────────────────────────┤
  │ Tenant isolation possible with        │ NO — GLOBAL_MEMORY_STORE and AGENT_REGISTRY are process-level singletons; no per-instance isolation         │
  │ current API?                          │                                                                                                             │
  ├───────────────────────────────────────┼─────────────────────────────────────────────────────────────────────────────────────────────────────────────┤
  │ All enforcement consistent across     │ NO — filesystem default, timeout default, and auth requirement all differ by mode                           │
  │ CLI, embedded, serve?                 │                                                                                                             │
  ├───────────────────────────────────────┼─────────────────────────────────────────────────────────────────────────────────────────────────────────────┤
  │ Security gaps documented publicly?    │ PARTIAL — SECURITY_POSTURE.md documents subprocess, HTTP, and memory gaps; does not document multi-tenant   │
  │                                       │ memory isolation failure or the CLI-vs-embedded default divergence                                          │
  └───────────────────────────────────────┴─────────────────────────────────────────────────────────────────────────────────────────────────────────────┘

  ---
  Final Verdict

  An embedder who follows the documented minimum configuration (allowed_paths, max_steps, timeout_ms) gets filesystem sandboxing and resource limits, but
  runs untrusted code that can make arbitrary outbound HTTP requests, invoke arbitrary OS subprocesses, read any process environment variable, allocate
  unbounded host memory, and share memory namespace with every other script running in the same process — none of which the documented configuration
  controls.