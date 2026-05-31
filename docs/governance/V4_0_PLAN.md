# Nodus v4.0 — Phase 0 Decisions

**Cycle:** v4.0 major release
**Phase 0 date:** 2026-05-25 (planning conversation)
**Status:** Locked. Phase 1 (design docs) follows from these decisions.
**Maintainer:** Shawn Knight (Masterplanner25)

---

## Purpose

This document captures the design decisions resolved during Phase 0 of
the v4.0 cycle. Each decision records: the question, the chosen option,
the reasoning, the rejected alternatives with their costs, and where
applicable, reconsideration triggers that would warrant revisiting.

Phase 0 produces decisions. Phase 1 produces design docs that specify
those decisions in implementable detail. Phase 2-5 execute against the
specs. This doc is the audit trail for the chain.

---

## Decision 1 — Identity: Orchestration DSL

**Question:** Is Nodus general-purpose scripting or workflow-focused
scripting? What audience does the language target?

**Decision:** Workflow-focused orchestration DSL with phased approach
(Option C).

The pitch: "You used to need Python + LangChain + bash + YAML to wire
a workflow together; now you use Nodus."

Nodus is the orchestration glue, not a Python replacement. Components
being orchestrated (general scripting, data processing, ML inference,
external APIs) stay where they live. Nodus calls them through tools,
MCP, subprocess, and HTTP.

**Phased identity:**
- **v3.x — Orchestration DSL.** Stdlib expands to make Nodus the
  credible glue layer.
- **v4.x — Orchestration DSL with self-hosting groundwork.** Stdlib
  depth increases to support bootstrapping prerequisites. MCP library
  ecosystem matures.
- **v5.x+ — Self-hosted orchestration DSL.** Bootstrapping milestone:
  Nodus compiler written in Nodus, demonstrating the language supports
  complex systems.

**Tier 3 stdlib priorities (orchestration-focused):**

In scope for v4.x:
- Environment variables (CI/CD config)
- HTTP client (call external APIs)
- Datetime (timestamps, durations, scheduling)
- Crypto / hashing (API signing, content addressing)
- Process / subprocess (call external tools)

Out of scope for v4.x (tracked as Tier 4 deferred):
- Regex (string parsing belongs to components being orchestrated)
- CSV (data processing is a component concern)
- Full general-purpose string library (orchestration needs less than that)
- Full general-purpose math library (orchestration doesn't do math)

**Reasoning:**
1. Existing investment lines up. Workflows, goals, task graphs,
   coroutines, channels — these are the moat. Optimizing for them
   leverages what's already differentiated.
2. Tier 3 scope of 5 modules is one focused release; 10-15 modules is
   a multi-release effort that drags.
3. General-purpose later is recoverable; going wide first and
   retrenching to workflows is much harder.
4. "Workflow runtime" identity matches what the language actually is.
5. "Better than Python for scripting" is a losing competitive position
   given Python's 30 years of stdlib evolution.

**Rejected alternatives:**

*Option A — General-purpose scripting.* Compete with Python, Lua,
Starlark, Ruby. Tier 3 stdlib goes wide (~10-15 modules). **Rejected
because** Nodus would need feature parity plus a compelling
differentiator. The workflow primitives (already shipped) are the
differentiator; building stdlib around them makes more sense than
competing on stdlib breadth.

*Option B — Workflow-focused only, no expansion path.* Same as Option
C but without the phased v4.x → v5.x progression. **Rejected because**
without a path toward bootstrapping, the orchestration DSL identity
caps at "useful tool" rather than "language that proves itself by
existing in itself."

**Reconsideration triggers:**
This decision should be revisited if:
- Real user demand surfaces for general-purpose scripting features
  (multiple issues, not just one)
- The orchestration DSL audience proves smaller than projected (say,
  below 500 active users after a year of v4.x)
- A specific general-purpose stdlib addition has clear orchestration
  value (e.g., regex for log parsing that orchestration scripts
  routinely need)

Until one of those triggers fires, the orchestration DSL identity
holds.

---

## Decision 1 (extension) — MCP as Library, Not Core

**Question:** Should MCP (Model Context Protocol) integration be built
into the Nodus runtime, or ship as a library through the package
registry?

**Decision:** MCP integration ships as an officially-supported library
through the package registry. The tool registry gains library-side
handler support as a small core change benefiting MCP and similar
libraries equally.

**Reasoning:**
1. Matches the existing design philosophy ("The core stays compact.
   Features that can be libraries should be libraries.")
2. Decouples Nodus release schedule from MCP protocol evolution.
3. Validates the package manager and library ecosystem.
4. Removes v3.x vs v4.x sequencing pressure on MCP.
5. Keeps the language identity clean: "Nodus is an orchestration DSL"
   not "Nodus has MCP support built in."
6. Scales to future protocols (whatever comes after MCP is also a
   library).

**Rejected alternatives:**

*Core integration.* MCP becomes runtime functionality with new
language primitives. **Rejected because** ties Nodus's identity to one
specific protocol, requires Nodus releases for protocol updates, makes
swapping protocols nearly impossible.

*No integration, document Python adapter pattern.* MCP is someone
else's problem; users wrap MCP via Python embedding. **Rejected
because** the orchestration DSL pitch requires Nodus to participate in
the agent tool ecosystem credibly. Telling users "use Python for MCP"
undermines the pitch.

**Reconsideration triggers:**
This decision should be revisited if:
- MCP library proves so essential that core integration becomes worth
  the protocol-coupling cost
- A future protocol becomes so dominant that ecosystem-wide assumption
  changes

---

## Decision 1 (horizon) — Bootstrapping is v5.x+, Not v4.x

**Question:** Where does the bootstrapping milestone (Nodus compiler
written in Nodus) fit in the roadmap?

**Decision:** Bootstrapping is a v5.x+ goal. v4.x adds stdlib depth
toward bootstrapping prerequisites but does not pursue self-hosting.

**Reasoning:**
1. v1.0 completed the bytecode/module/embedding prerequisites.
2. The "sufficiently expressive stdlib" prerequisite gap is what v4.x
   stdlib expansion partially addresses.
3. Bootstrapping is genuinely long-term work (multi-year). Naming it
   v4.x sets unrealistic expectations.
4. Bootstrapping benefits from MCP integration being mature (a
   self-hosted Nodus that can use MCP tools means the language can be
   its own development environment).
5. v4.x focus on production-readiness validates the language enough
   to make bootstrapping a credible v5.x goal.

**Rejected alternatives:**

*Bootstrap in v4.x.* **Rejected because** the work is too large for
one major cycle and the prerequisites (stdlib depth, ecosystem
validation) aren't fully there yet.

*Drop bootstrapping entirely.* **Rejected because** it's the
long-term proof that the orchestration DSL is mature enough to
support complex systems. The goal stays; the timeline is honest.

**Reconsideration triggers:**
This decision should be revisited if:
- v4.x stdlib expressive enough that writing a Nodus parser in Nodus
  becomes practically feasible
- Concrete user demand for self-hosting surfaces

---

## Decision 2 — v4.0 Scope: Roll Everything In

**Question:** What's the breaking-change scope for v4.0? What stays in,
what gets deferred to v5.x, what gets cut entirely?

**Decision:** Five-tier structure, nothing cut entirely. Every known
issue gets tracked even if deferred.

**Tier 1 — In v4.0 confirmed (breaking, high-confidence):**
- `len()` → `int`
- IEEE 754 float division decision (see Decision 10)
- Cyclic workflow returns err record + non-zero exit
- Stdlib err records get location fields (path/line/column/stack)

**Tier 2 — In v4.0 confirmed (additive, new features):**
- String interpolation
- Tool registry library-side handlers
- Test framework (`std:test`)
- Five orchestration stdlib namespaces (HTTP, env, datetime, crypto,
  process)
- Doc-vs-code reconciliation gate (#82, infrastructure)

**Tier 3 — In v4.0 after Phase 0 design decision:**
- `type()` naming reconciliation (Decision 9 resolved this)
- Equality coercion final policy (Decision 14 resolved this)
- `finally`-after-catch-return — verify status, close as
  already-fixed if so, otherwise fix

**Tier 4 — Deferred to v5.x or later, but tracked:**
- Bootstrapping milestone (years out, infrastructure prerequisite)
- General-purpose stdlib expansion (regex, CSV, full string library,
  etc.) — out of scope per orchestration DSL positioning, but tracked
  as "explicitly not pursuing unless positioning changes"
- Memory limit sandbox option (post-v1.0 item in existing roadmap)
- `try { } finally { }` without catch (syntax convenience)
- Performance optimization passes (separate effort entirely)
- Register VM conversion (long-term VM rewrite, post-bootstrap)

**Tier 5 — Cut entirely:** Nothing. The playbook discipline of "file
every finding, even cosmetic ones" applies to scope decisions too.
Anything known to be wrong gets planned out, even if deferred.

**Reasoning:**
1. v4.0 ships breaking changes; might as well bundle the breaking
   changes that have accumulated.
2. v3.x has shipped 7 release cycles in 8 months. Velocity supports a
   substantial v4.0.
3. The methodology (design upfront, eval after release) handles large
   scope well.
4. "Roll everything into v4.0" removes the artificial throttling that
   conventional release pacing would impose.

**Rejected alternatives:**

*Strict v3.x non-breaking, save everything for v4.0 = one cycle
later.* **Rejected because** there is no more v3.x in this plan —
everything between now and v4.0 is design work, not release work.

*Selective v3.x breaking changes for high-leverage fixes.* **Rejected
because** would erode the SemVer contract the project has built
credibility on.

*Cut some Tier 4 items entirely.* **Rejected because** every known
issue should be tracked, not discarded. Deferred-with-reasoning is
different from cut-as-out-of-scope.

**Reconsideration triggers:**
Tier movement (between 1-2-3-4) is fluid until Phase 1 design docs
complete. After Phase 1, tiers are locked for v4.0.

Tier 4 items revisited when v5.x planning starts.

---

## Decision 3 — Velocity: Plan Everything Now, Ship When Ready

**Question:** What's the release cadence and scope shape over the
next 12 months?

**Decision:** Roll everything into v4.0. Plan the entire release
upfront. Ship when ready. No interim v3.x releases.

**Reasoning:**
1. Demonstrated velocity (3 majors + 4 patches in 72 hours) means
   conventional pacing doesn't apply.
2. The maintainer's working pattern (design-heavy planning
   conversations producing detailed specs, then execution against
   specs in concentrated bursts) front-loads design rather than
   throttling release scope.
3. Design time is the bottleneck, not implementation time. Good Phase
   0/1 work means Phases 2-5 can sprint.
4. v4.0 with comprehensive scope is more cohesive than 4-6 v3.x
   minor releases each shipping a fraction of the orchestration DSL
   story.

**Realistic timeline:**
- Phase 0 (decisions): this planning conversation, complete
- Phase 1 (design docs): 1-2 sessions producing 8-12 design docs
- Phase 2 (non-breaking fixes): a few hours
- Phase 3 (breaking changes + new stdlib): 3-5 days focused work
- Phase 4 (docs sweep): half a day to a day
- Phase 5 (release): an hour

**Total execution: probably 3-5 days of focused work whenever the
design phase wraps and time allows.**

**Rejected alternatives:**

*Incremental polish, frequent releases.* **Rejected because** doesn't
match demonstrated velocity. Imposes overhead without serving the
user.

*v3.1 as orchestration stdlib reset release, then smaller releases.*
**Rejected because** still maintains artificial sequencing. If
everything can ship in one well-designed cycle, that's better than
two cycles.

**Reconsideration triggers:**
If Phase 1 design work surfaces a need to ship something before v4.0
(e.g., an urgent security patch to v3.0.2), reconsider scope. Until
then, plan v4.0 monolithically.

---

## Decision 4 — Test Framework: Comprehensive Scope

**Question:** What's the scope of `std:test` for v4.0?

**Decision:** Comprehensive scope (Option B) — full pytest/jest-
equivalent. Pure library, no new language syntax.

**Capabilities in v4.0:**
- Assertions (basic and structural)
- Suites and cases (block-based via `test.suite` and `test.case`)
- Lifecycle hooks (`before_all`, `after_all`, `before_each`,
  `after_each`)
- Fixtures with test/suite scopes
- Parameterized tests
- Async tests with deterministic scheduling
- Test isolation by default
- Coverage reporting (source-line in v4.0; bytecode-level deferred)
- Test discovery (`*_test.nd` files under `tests/`)
- CLI: `nodus test` with filter, parallel, watch, coverage, format flags

**Reasoning:**
1. v4.0's "production-ready" theme requires real testing capability.
   Minimal or mid-scope leaves known gaps that users would file as
   v4.0.1 issues anyway.
2. Following the playbook discipline: fix everything that's known wrong,
   even if minimal.
3. Test framework is a bounded library task with well-understood scope
   (pytest is the comparison point).
4. Coverage instrumentation is the only complex piece; source-line
   coverage is achievable and bytecode-level is a v4.x enhancement.

**Rejected alternatives:**

*Minimal scope (just assert + assert_eq + simple discovery).*
**Rejected because** users hit walls quickly. Production testing needs
fixtures and setup/teardown at minimum.

*Mid-scope (lifecycle hooks + basic fixtures, skip parameterized and
coverage).* **Rejected because** parameterized tests are essential
for orchestration testing (different inputs, same logic) and coverage
is essential for production-readiness verification.

**Reconsideration triggers:**
If implementation surfaces that something in the comprehensive scope
requires more than 5 days of work or significantly complicates other
v4.0 work, scope down. Otherwise comprehensive holds.

---

## Decision 5 — HTTP API Shape

**Question:** What's the HTTP client API surface for v4.0?

**Decision:** Sync default with async opt-in, buffered default with
streaming opt-in, rich err records with category field.

**API surface:**
- `http.get(url, options)`, `http.post`, `http.put`, `http.delete`,
  `http.patch`, `http.head`, `http.options`
- `http.get_async(url, options)` etc. for coroutine versions
- `http.stream(url, options)` for streaming responses
- Generic `http.request(method, url, options)` for custom verbs
- Response object: `status`, `headers`, `body`, `response.json()`
  convenience

**Err record shape:**
```
err {
    kind: "http_error",
    payload: {
        status: ...,        # HTTP status code
        url: ...,           # the URL requested
        method: ...,        # HTTP method
        category: ...,      # "network", "timeout", "client_error",
                            # "server_error", "decode_error"
        body: ...           # response body if available
    }
}
```

**Reasoning:**
1. Sync default matches what 80% of orchestration scripts need.
2. Async opt-in (separate function, not flag) prevents the Python
   `subprocess` shell=True footgun pattern.
3. Buffered default; streaming for large responses.
4. `category` field lets users branch on failure type without parsing
   status codes.

**Rejected alternatives:**

*Sync only.* **Rejected because** can't compose with workflows that
need parallel HTTP calls.

*Async only.* **Rejected because** ceremony for one-off scripts where
async isn't needed.

*Async via flag (Python pattern).* **Rejected because** flag-based
opt-in is too easy; separate functions force conscious choice.

**Reconsideration triggers:**
If orchestration use cases prove async-first is more common than
expected, reconsider whether sync should remain the default.

---

## Decision 6 — Datetime API Shape

**Question:** What's the datetime API surface for v4.0?

**Decision:** Aware datetimes only, Unix epoch milliseconds internal,
`std:time` namespace, chrono-style format tokens, IANA timezones.

**Key design choices:**
- All datetimes have a timezone (no naive datetimes)
- Internal representation: Unix epoch ms as `int`
- Calendar operations as stdlib functions, not type methods
- Duration as separate type
- Chrono-style format tokens (`yyyy-MM-dd HH:mm:ss`)
- `time.now()` returns UTC; `time.now_in(zone)` returns specific zone
- Err records use `kind: "time_error"` with `category` field
  (`"parse_error"`, `"invalid_zone"`, `"out_of_range"`, `"ambiguous"`)

**Reasoning:**
1. Aware-only prevents the Python naive/aware confusion that produces
   "works on my machine" bugs.
2. Epoch ms internal makes comparison and serialization trivial.
3. Chrono-style format tokens (`yyyy-MM-dd`) are more readable than
   strftime (`%Y-%m-%d`).
4. IANA identifiers are the modern standard.

**Rejected alternatives:**

*Naive default with aware opt-in (Python pattern).* **Rejected
because** the Python community spent years dealing with naive/aware
confusion. Don't repeat.

*strftime-style format tokens.* **Rejected because** the codes have
no logical structure; users memorize them rather than reason about
them.

*Calendar struct as the internal representation.* **Rejected
because** comparison, serialization, and storage are simpler with
epoch ms.

**Reconsideration triggers:**
If `zoneinfo` integration proves complex enough to warrant alternative
approaches, reconsider implementation strategy (the API surface stays
the same).

---

## Decision 7 — Crypto / Hashing API Shape

**Question:** What's the crypto and hashing API surface for v4.0?

**Decision:** Three separate namespaces (`std:hash`, `std:encoding`,
`std:secrets`), scoped tightly to orchestration needs.

**Namespaces:**
- `std:hash` — sha256, sha512, blake2b, sha1, md5; HMAC variants;
  constant-time comparison
- `std:encoding` — base64, hex, URL encoding
- `std:secrets` — cryptographically secure random for tokens

**Out of scope for v4.0:**
- Symmetric/asymmetric encryption (orchestration calls services that
  encrypt; doesn't encrypt itself)
- Key derivation (PBKDF2, Argon2, scrypt — password handling is a
  service concern)
- TLS configuration (handled by HTTP client transparently)
- Certificate handling
- Digital signatures

**API patterns:**
- One-shot for common case (`hash.sha256(data)`), streaming for large
  files (`hash.sha256_streaming()`)
- Hash values formatted via `hash.to_hex()`, `hash.to_base64()`,
  `hash.to_bytes()`
- HMAC: `hash.hmac_sha256(key, message)` — key first per RFC 2104
- Constant-time compare: `hash.compare(a, b)` (in `std:hash` namespace
  since primary use is hash comparison)
- Legacy hashes (sha1, md5) included with prominent security warnings

**Reasoning:**
1. Three namespaces with specific purposes is clearer than one
   `std:crypto` that implies more than is offered.
2. `std:secrets` name makes the security purpose obvious; users
   reaching for `math.random()` look wrong for session tokens.
3. Legacy hashes included because users interfacing with systems that
   require MD5/SHA1 shouldn't have to shell out.

**Rejected alternatives:**

*Single `std:crypto` namespace.* **Rejected because** "crypto"
implies encryption capabilities Nodus doesn't have.

*Hierarchical `crypto.hash.*`, `crypto.encoding.*`, `crypto.random.*`.*
**Rejected because** deeper paths, more typing, no real benefit over
separate namespaces.

*Format-as-argument pattern (`hash.sha256(data, "hex")`).* **Rejected
because** less composable than hash-value-with-formatters.

**Reconsideration triggers:**
If concrete encryption use cases surface (e.g., needing to encrypt
data before storing it), reconsider scope. Currently the answer is
"call an encryption service" — if that pattern proves inadequate,
revisit.

---

## Decision 8 — Subprocess API Shape

**Question:** What's the subprocess API surface for v4.0?

**Decision:** No-shell default with separate `subprocess.shell()`
function, sync default with async opt-in, comprehensive output
handling modes.

**Functions:**
- `subprocess.run(argv, options)` — sync, no-shell
- `subprocess.run_async(argv, options)` — async coroutine
- `subprocess.shell(command_string, options)` — sync, shell
- `subprocess.shell_async(command_string, options)` — async shell
- `subprocess.spawn(argv, options)` — returns process handle with
  streaming channels

**Options:**
- `output`: `"capture"` (default), `"inherit"`, `"ignore"`
- `stdout`, `stderr`: per-stream override
- `stdin`: string/bytes/nil
- `env`: map, merged with parent by default
- `env_inherit`: bool, default true
- `cwd`: working directory
- `timeout_ms`: integer, default unlimited
- `check`: bool, default true (non-zero exit → err)

**Err record:**
```
err {
    kind: "subprocess_error",
    payload: {
        category: ...,      # "exit_code", "timeout", "signal",
                            # "spawn_error", "io_error"
        command: ...,
        exit_code: ...,
        signal: ...,
        stdout: ...,
        stderr: ...,
        duration_ms: ...
    }
}
```

**Reasoning:**
1. No-shell as default prevents shell injection vulnerabilities. The
   most common security bug in Python subprocess code.
2. `subprocess.shell()` as separate function (not flag) forces
   conscious choice when shell features are needed.
3. `check: true` default matches Python's modern pattern; non-zero
   exit is failure unless opted out.
4. Comprehensive output modes (capture/inherit/ignore + per-stream
   override + merge) cover all common patterns.

**Rejected alternatives:**

*Shell as flag (`subprocess.run([...], shell=true)`).* **Rejected
because** flag-based shell opt-in produced the most common Python
security bug.

*Sync only.* **Rejected because** parallel subprocess calls are
common in orchestration.

*Streaming-only API.* **Rejected because** ceremony for simple cases.

**Reconsideration triggers:**
If MCP library implementation surfaces subprocess limitations (e.g.,
stdin streaming for long-lived MCP servers), reconsider API.

---

## Decision 9 — type() Naming Choice

**Question:** Should `type()` return naming be `"number"` and `"int"`
(current asymmetric), `"float"` and `"int"` (both specific), or
something else?

**Decision:** Both specific — `type()` returns `"float"` for floats,
`"int"` for ints. Add `math.is_numeric`, `math.is_int`, `math.is_float`
helpers.

**Breaking change:** Code using `type(x) == "number"` must update to
`type(x) == "float"` or `math.is_numeric(x)`.

**Reasoning:**
1. The orchestration DSL identity argues for precision. Workflows
   handling currency, IDs, or large counts need to know float vs int
   distinction.
2. Asymmetric naming (`"number"` and `"int"`) is what the v3.0.1
   eval flagged as friction.
3. Type system should reflect that `1i` and `1.5` are distinct values
   with distinct guarantees.

**Rejected alternatives:**

*Both general — `"number"` for everything, separate function for
int check.* **Rejected because** loses information at the type level,
defeats the purpose of having `1i` as a distinct type.

*Keep asymmetric naming.* **Rejected because** internally
inconsistent; the eval will keep finding it.

*Record-based type info `{kind: "number", subkind: "float"}`.*
**Rejected because** breaks the simplest type-check pattern.

**Reconsideration triggers:**
This decision likely won't need revisiting. The naming is internally
consistent and the migration is mechanical.

---

## Decision 10 — IEEE 754 Float Division

**Question:** Should `1.0 / 0.0` throw a runtime error (Python
behavior) or return infinity (IEEE 754 behavior)?

**Decision:** IEEE 754 semantics. `1.0 / 0.0` returns `inf`,
`0.0 / 0.0` returns `nan`, `-1.0 / 0.0` returns `-inf`.

**New stdlib additions:**
- `math.is_nan(x)`, `math.is_inf(x)`, `math.is_finite(x)`
- `math.nan`, `math.infinity`, `math.neg_infinity`

**Breaking change:** Code catching `Runtime error: Division by zero`
will silently start getting inf/nan instead. Migration guide
documents the explicit-check pattern for users who want strict
behavior.

**Reasoning:**
1. LANGUAGE_SPEC says "IEEE 754 floats." Either honor that or change
   the spec; honoring is simpler.
2. Modern language consensus is IEEE 754 (JavaScript, C, Rust, Go,
   Java, Swift). Python is the outlier.
3. Composes better with err records — division-by-zero was the only
   arithmetic that threw instead of returning a value.
4. Silent propagation weakness is mitigated by `math.is_nan` and
   `math.is_inf` checks.

**Rejected alternatives:**

*Throw on division by zero (keep current behavior).* **Rejected
because** doesn't match the spec. Users who want strict behavior can
add explicit checks.

*IEEE 754 with optional strict mode.* **Rejected because**
overengineering. Strict mode adds complexity for marginal benefit.

**Reconsideration triggers:**
This decision likely won't need revisiting once shipped. The behavior
is well-defined and matches the spec.

---

## Decision 11 — String Interpolation Syntax

**Question:** What syntax should string interpolation use?

**Decision:** Swift-style `"\(expr)"` interpolation. Arbitrary
expressions. Automatic stringification via `str()` path. Nested
interpolations supported. Format specifiers deferred to v4.x.

**Examples:**
```
"hello \(name)"
"total: \(price * quantity)"
"\(map["key"])"
"\(func(a, b))"
"outer \(inner.method("nested \(deep)"))"
```

**Reasoning:**
1. Fits Nodus's existing escape sequence convention (`\n`, `\t`,
   `\xHH`, `\uXXXX`).
2. No string prefix required — every string is potentially
   interpolated, no "you forgot the f prefix" footgun.
3. `$` preserved for future use (shell-like substitution, currency,
   regex backreferences).
4. Lexer complexity bounded — extends existing escape sequence
   handling.

**Rejected alternatives:**

*JavaScript-style `"${expr}"`.* **Rejected because** `$` has no
current meaning in Nodus; introducing it would require escape rules
for literal `$`. Users would expect bare `$name` to also work.

*Python f-string style `f"text {expr}"`.* **Rejected because**
introduces string prefix syntax; plain `"text {expr}"` would not
interpolate, surprising users.

*Scala-style `s"text $expr more"`.* **Rejected because** prefix
required + dual rule (bare `$name` vs `${expr}`) is more complex.

**Reconsideration triggers:**
Format specifiers (e.g., `"\(value:.2f)"`) deferred to v4.x. If
orchestration scripts need formatted output frequently, add then.

---

## Decision 12 — Tool Registry Library-Side Handlers

**Question:** How should libraries register their own tool handlers
in the Nodus tool registry?

**Decision:** Libraries register tools via `std:tool.register(metadata)`
at import time AND during runtime. Unregistration supported via
`std:tool.unregister(name)`. Conflict-as-error. Dotted namespacing.
Host-side adapter extension point in the embedding API.

**Registration API:**
```
import "std:tool" as tool

tool.register({
    name: "mcp.call_tool",
    handler: fn(args) { ... },
    description: "Call a tool on an MCP server",
    schema: { server: "string", tool: "string", args: "map" }
})
```

**Key design choices:**
- Dynamic registration (both at import and runtime, supporting MCP's
  dynamic tool discovery)
- Unregistration supported (MCP servers can disconnect)
- Conflict on registration produces err record (not silent override)
- Dotted namespacing (`library.tool_name`)
- Host-side adapter registry for libraries needing Python plumbing
  (added to embedding API)

**Reasoning:**
1. AI agents using tools dynamically is the whole point of having a
   tool registry. Dynamic registration enables this.
2. MCP servers can add/remove tools at runtime; Nodus registry should
   accommodate that.
3. Library registration at import time (static) handles the common
   case; runtime registration handles the dynamic case.
4. Conflict-as-error surfaces problems immediately with both library
   names visible.

**Rejected alternatives:**

*Static-only registration (initial proposal).* **Rejected because**
prevents MCP-style dynamic tool discovery, which is the agent
ecosystem's core pattern.

*Silent conflict resolution (first wins or last wins).* **Rejected
because** silent behavior is the worst option for security-sensitive
tool dispatch.

*No unregistration.* **Rejected because** dynamic registration
without unregistration is half a feature.

**Reconsideration triggers:**
If the MCP library implementation surfaces tool registry limitations,
revisit. Currently the API is designed against the MCP use case
explicitly.

---

## Decision 13 — Test Framework API Specifics

**Question:** What's the specific API shape of the comprehensive test
framework?

**Decision:** Pure library, block-based syntax via `test.suite` and
`test.case`. Full lifecycle hooks, fixtures with scopes, parameterized
tests, async tests with deterministic scheduling, test isolation by
default.

**Core API:**
```
test.suite("user account tests", fn() {
    test.before_all(fn() { ... })
    test.before_each(fn() { ... })
    test.after_each(fn() { ... })
    test.after_all(fn() { ... })

    test.fixture("authenticated_user", fn() {
        return create_user_with_token()
    })

    test.case("creates user with valid input", fn(ctx) {
        let user = ctx.fixture("authenticated_user")
        test.assert_ok(user)
    })

    test.case_async("workflow completes", fn() {
        let result = run_workflow(my_workflow)
        test.assert_ok(result)
    })

    test.parameterize([
        ["alice", 30, true],
        ["bob", 25, true],
        ["", 30, false]
    ], fn(name, age, expected_valid) {
        test.case("validates: \(name)", fn() {
            test.assert_eq(validate({name, age}).valid, expected_valid)
        })
    })
})
```

**Assertions:**
- Basic: `assert`, `assert_eq`, `assert_neq`, `assert_err`,
  `assert_ok`, `assert_kind`, `assert_throws`, `assert_close`
- Structural: `assert_contains`, `assert_has_key`, `assert_in_range`

**Discovery and CLI:**
- Files matching `*_test.nd` under `tests/`
- `nodus test [--filter | --parallel | --watch | --coverage | --format]`

**Coverage:** source-line in v4.0; bytecode-level deferred to v4.x.

**Output formats:** pretty TTY, plain text, JSON, JUnit XML.

**Reasoning:**
1. Pure library (no language syntax) matches Nodus's "small core,
   capabilities in libraries" philosophy.
2. Block-based syntax via callbacks is idiomatic to Nodus.
3. Comprehensive scope per Decision 4.
4. Test isolation by default prevents cross-test state leakage.

**Rejected alternatives:**

*New language keyword `test`.* **Rejected because** library
implementation doesn't need lexer/parser changes.

*Function naming convention `fn test_*`.* **Rejected because**
fragile — rename a function, lose the test.

*Bytecode-level coverage in v4.0.* **Rejected because** more complex
than source-line; ship simpler version first.

**Reconsideration triggers:**
If implementation surfaces wall requiring VM cooperation (e.g.,
coverage instrumentation needing bytecode hooks), revisit library-
vs-language framing.

---

## Decision 14 — Equality Coercion Final Policy

**Question:** Should `==` continue to coerce as in v3.x, or change?
Should a strict equality operator `===` be added?

**Decision:** Numeric-only coercion. `==` coerces within the number
family only (int and float compare by value). All other cross-type
comparisons return false. No `===` operator in v4.0.

**Breaking change from v3.x:**
- `0 == false` was true in v3.x, becomes false in v4.0
- `0i == false` was true in v3.x, becomes false in v4.0
- `1 == 1.0` stays true (numeric-only coercion preserves it)
- `nil` semantics unchanged

**Helpers for explicit cross-type comparison:**
- `bool.equal(value, bool_value)` for number-to-bool when wanted
- `type_eq(a, b)` for "same type AND equal" check

**Reasoning:**
1. `0 == false` is the actual footgun — JavaScript-ism that even
   JavaScript regrets.
2. Numbers comparing to numbers (across int/float) is intuitive.
3. Migration is manageable — code using `0 == false` was probably
   wrong anyway.
4. `===` operator adds equality surface area for marginal gain.

**Rejected alternatives:**

*Keep coercion as-is.* **Rejected because** v3.0.1 eval flagged the
weird cases (`"" == false` is false; users expect "all falsies
equal").

*Strict equality, no coercion.* **Rejected because** making `1 == 1.0`
false breaks intuition for orchestration where int/float mix casually.

*Add `===` alongside `==`.* **Rejected because** doubles equality
surface area; users wanting strict can use `type_eq(a, b)` helper.

**Reconsideration triggers:**
The `===` non-decision should be revisited if:
- Future eval cycles surface concrete cases where `type_eq()` is too
  verbose for common patterns
- Language adds features (generics, traits, etc.) that interact with
  type-equality semantics
- Community demand surfaces as a real pattern (multiple issues filed
  requesting it)

Until one of those triggers fires, do not add `===`.

---

## Decision 15 — Doc-vs-Code Reconciliation Gate

**Question:** How should the closure verification gate (#82) be
implemented to prevent future patch closure failures like BUG-E12?

**Decision:** Three-phase verification gate. New `nodus_gate` command
with `--static`, `--runtime`, `--closed-issues`, `--all` flags.
Integrated into both playbooks as mandatory pre-release steps.

**Phase 1 — Static:**
- Parses LANGUAGE_SPEC.md, policy docs, guide docs
- Extracts every documented symbol
- Imports Nodus and verifies each symbol resolves
- Reports missing symbols with file:line references

**Phase 2 — Runtime:**
- Finds every code block tagged `nodus` or `nd` in guide docs
- Runs each block against fresh Nodus interpreter
- For blocks with `nodus-expect=output`, asserts output matches
- Reports mismatches

**Phase 3 — Issue closure:**
- Reads [Unreleased] section of CHANGELOG.md
- Extracts referenced issue numbers
- Locates tests via convention (test_issue_75.py, docstring
  reference, or marker)
- Runs those tests against installed wheel post-TestPyPI install
- Blocks release if any test fails

**Doc conventions:**
- ` ```nodus ` — runs, verified that it doesn't error
- ` ```nodus-no-run ` — illustrative, not verified
- ` ```nodus-expect=output ` — runs, output verified against `output`

**Reasoning:**
1. Each phase catches a different failure mode (missing symbols,
   semantic drift, patch closure failures).
2. v3.0.0 had 6 missing functions; static analysis would catch them.
3. v3.0.1 had math.log argument swap; runtime verification would
   catch it.
4. v3.0.1 had BUG-E12 patch closure failure; issue verification would
   catch it.
5. v4.0's "production-ready" theme requires verifiable claims.

**Rejected alternatives:**

*Static analysis only.* **Rejected because** doesn't catch semantic
drift or claim-vs-reality drift.

*Runtime verification only.* **Rejected because** doesn't catch
patch closure failures.

*No gate, rely on test coverage.* **Rejected because** v3.0.1
demonstrated test coverage alone doesn't prevent these failure
modes.

**Reconsideration triggers:**
After v4.0 release, evaluate gate effectiveness. If false positives
are common (gate flags things that aren't actually problems), refine
the patterns. If false negatives surface (real failures slip through),
add additional checks.

---

## Decision 16 — MCP Library v0.1 Scope

**Question:** What's the scope of the MCP library v0.1?

**Decision:** Comprehensive MCP specification support. Bidirectional
(client and server roles). All three transports (stdio, HTTP,
Streamable HTTP). All current MCP capabilities. Ships with v4.0 as
flagship library validating the orchestration DSL + ecosystem story.

**Implementation sequenced in 14 phases (A-N):**
- Phase A: Foundation (JSON-RPC, MCP message types, lifecycle)
- Phase B: Stdio transport
- Phase C: Client tools (most-used capability)
- Phase D: Client resources
- Phase E: Client prompts
- Phase F: Client advanced (sampling, logging, progress, completion,
  roots)
- Phase G: HTTP transports (HTTP, SSE, Streamable HTTP)
- Phase H: Server foundation
- Phase I: Server tools (expose Nodus workflows/functions)
- Phase J: Server resources
- Phase K: Server prompts
- Phase L: Server advanced
- Phase M: Server transports
- Phase N: Polish (CLI, REPL integration, docs, test suite)

**Out of v0.1 (deferred to v0.x patches or v0.2):**
- Performance optimizations beyond correctness
- MCP spec features added after v4.0 ships
- Advanced authentication beyond bearer tokens

**Reasoning:**
1. MCP is well-bounded against a published spec; comprehensive scope
   doesn't have design uncertainty.
2. Bidirectional support unlocks both halves of the orchestration DSL
   pitch (consumer and producer).
3. v0.1 shipping with v4.0 validates the library ecosystem story.
4. Discipline of "fix everything that's known wrong" applies to MCP
   spec features.
5. Velocity supports the scope (~14-21 days focused work).

**Rejected alternatives:**

*Minimum viable (client only).* **Rejected because** half the
orchestration DSL story. Nodus would still be "useful for consuming
external services" not "part of the agent stack."

*Client + resources only.* **Rejected because** server side is what
unlocks Nodus-as-agent-tool, which is the moment Nodus becomes part
of the agent ecosystem rather than parallel to it.

*Build separately, ship later as v4.x library.* **Rejected because**
MCP at v4.0 launch validates the library ecosystem; deferring it
weakens the story.

**Spec verification discipline:**
For any library implementing an external spec (MCP, future protocols),
a final-pass spec check runs between implementation complete and
public registry release:
1. Locate spec's authoritative source
2. Read changelog/release notes between implementation start and
   current date
3. Classify changes: none, additive only, breaking/critical
4. Breaking/critical → pause, evaluate incorporation
5. Additive → note for next version, proceed
6. None → proceed as planned

Cost: ~1 hour per library check. First applied: MCP library v0.1
before v4.0 PyPI release.

**Reconsideration triggers:**
If MCP spec adds significant breaking changes between Phase 0 and
release, scope adjustment may be required. Spec verification step is
designed to catch this.

---

### Decision 16 (amendment) — MCP spec revision pin and Elicitation capability

**Date of amendment:** 2026-05-25 (same Phase 0 session, after spec
verification fetch)

**Question:** Which MCP spec revision does v0.1 implement against, and does
the implementation outline (Phase A-N) cover all current MCP capabilities?

**Decision:** `nodus-mcp` v0.1 implements against the MCP 2025-11-25
specification revision. This revision adds Elicitation as a Client feature
(server-initiated requests for additional information from users), which
the original Decision 16 implementation outline did not list as a discrete
capability.

**Amended phase plan:**

The original Decision 16 listed 14 phases (A-N). Phase F (Client advanced)
covered sampling, logging, progress, completion, and roots. The amendment
adds Elicitation to Phase F:

- Phase F (Client advanced): sampling, logging, progress, completion,
  roots, **elicitation**

No other phase reordering required. Phase F was the natural home for
Elicitation given it is a Client feature exposed by Servers (server-
initiated requests answered by Clients).

**Reasoning:**

1. The MCP spec is dated rather than versioned; pinning to the 2025-11-25
   revision provides a concrete contract.
2. Elicitation was missed in the original Decision 16 because the
   implementation outline was drafted from memory rather than against a
   fresh fetch of the spec.
3. The spec verification discipline (Decision 16 appendix) is what caught
   this gap. Applying the discipline at Phase 0 (not just before release)
   catches scope gaps earlier when they cost less to address.

**Process improvement:**

Future protocol-library decisions in the Phase 0 design phase MUST fetch
the spec before drafting the implementation outline, not after. Decision
17 (A2A library v0.1) was drafted after a fresh A2A spec fetch and does
not have an analogous omission.

**Spec verification revisit before release:**

The Decision 16 spec verification step (run between implementation
complete and public registry release) compares against this pinned
revision. Spec changes between 2025-11-25 and v4.0 ship date are
classified as additive (note for next library version, proceed),
breaking/critical (pause, evaluate), or none (proceed as planned).

---

## Decision 17 — A2A Library v0.1 Scope

**Question:** What is the scope of `nodus-a2a` v0.1, and does it ship with
v4.0?

**Decision:** Comprehensive A2A specification support. Bidirectional
(client + server roles). All three protocol bindings (JSON-RPC, gRPC,
HTTP+JSON/REST). Full A2A v1.0.0 spec coverage including Task lifecycle,
Message/Artifact/Part data model, AgentCard discovery, streaming via SSE,
push notifications via webhooks, multi-turn via contextId/taskId, and the
Extensions mechanism. Bearer-token authentication for v0.1; advanced auth
(OAuth2, OIDC, mTLS) deferred to v0.2. Ships with v4.0 as a flagship
library validating the second protocol adapter in the orchestration DSL +
ecosystem story.

**Specification pin:** A2A v1.0.0 stable release. This is a versioned
release (unlike MCP's dated revisions), which simplifies the spec
verification discipline.

**Implementation sequenced in 14 phases (A-N):**

- Phase A: Foundation (JSON-RPC, A2A data model, AgentCard parsing and
  serving)
- Phase B: HTTP+JSON transport (primary binding)
- Phase C: Client core operations (SendMessage, GetTask, CancelTask)
- Phase D: Client streaming (SendStreamingMessage, SubscribeToTask)
- Phase E: Client task management (ListTasks with pagination)
- Phase F: Client push notifications (Create/Get/List/Delete config,
  webhook delivery)
- Phase G: Client extended agent card + multi-turn (contextId, taskId,
  referenceTaskIds)
- Phase H: Server foundation (task lifecycle, contextId management)
- Phase I: Server core operations (SendMessage handler, task creation,
  GetTask, CancelTask)
- Phase J: Server streaming (SSE event delivery, multiple-stream
  broadcast)
- Phase K: Server push notification delivery (webhook POST with
  authentication)
- Phase L: gRPC binding (both client and server sides)
- Phase M: HTTP+JSON/REST binding (both client and server sides)
- Phase N: Extensions mechanism + polish (CLI integration, REPL,
  documentation, test suite)

**Out of v0.1 (deferred to v0.x patches or v0.2):**

- OAuth2, OpenID Connect, and mTLS authentication schemes
- Custom protocol bindings (the spec allows URI-identified custom
  bindings; v0.1 ships only the three standard bindings)
- Performance optimization beyond correctness
- A2A spec features added after v1.0.0

**Bidirectional rationale:**

Same reasoning as Decision 16. A client-only A2A library makes Nodus
"useful for consuming external agents." A bidirectional library makes
Nodus "part of the agent ecosystem" — workflows expose themselves as A2A
agents, and other agents (regardless of framework) can call them.

**Three-binding rationale:**

The A2A spec explicitly allows agents to support any subset of the three
bindings, declared in `AgentCard.supportedInterfaces`. A library that
supports only one binding cannot interoperate with agents using a
different binding. JSON-RPC is most common; gRPC offers performance and
strict typing; HTTP+REST offers simplicity. Supporting all three matches
A2A's design intent and makes `nodus-a2a` interoperable with the full
A2A ecosystem.

**Update delivery mechanisms:**

All three A2A delivery mechanisms ship in v0.1:

- Polling (GetTask called on a schedule)
- Streaming (SSE-based, requires `AgentCard.capabilities.streaming = true`)
- Push notifications (webhooks, requires
  `AgentCard.capabilities.pushNotifications = true`)

Client code can choose mechanism per task. Server code declares
capabilities in its AgentCard.

**Extensions mechanism:**

A2A's extension system (URI-identified, declared in AgentCard) is
supported in v0.1. Libraries can register extensions; clients and servers
can negotiate extension use via the `A2A-Extensions` header. This is
necessary for the orchestration DSL positioning — extensions are how
domain-specific capabilities layer onto A2A without modifying the core
protocol.

**Auth scope:**

v0.1 supports Bearer token authentication only. The A2A spec supports
API key, HTTP auth (Basic, Bearer, Digest), OAuth2, OpenID Connect, and
mTLS. Bearer is the most common pattern and unblocks the v4.0 launch use
cases. Advanced auth schemes ship in v0.2 (post-v4.0).

**Reasoning:**

1. Two protocol adapters at launch (MCP + A2A) is architecturally
   stronger than one. One adapter is a coincidence; two is a pattern.
   The "protocols are adapters" commitment in LIBRARY_ECOSYSTEM.md is
   validated by shipping with two adapters that both work, rather than
   shipped with one and "the pattern works for future protocols too."
2. A2A is well-bounded against a stable v1.0.0 spec. The implementation
   uncertainty is low. Like MCP, the design effort is in mapping spec
   concepts to Nodus runtime primitives, not in inventing new design.
3. A2A v0.1 shipping with v4.0 validates the Tier 3 ecosystem story at
   launch. It also makes the Nodus runtime visible to the broader A2A
   ecosystem, which has Google's institutional backing and 23.9k GitHub
   stars on the spec repo as of v4.0 cycle.
4. Velocity supports the scope. The maintainer's working pattern
   (design-heavy planning conversations + concentrated execution) handles
   bounded-task libraries well. MCP and A2A development can happen in
   parallel or sequentially after v4.0 Phase 3 stabilizes.
5. Discipline of "fix everything that's known wrong" applies to A2A
   spec features. Skipping spec features in v0.1 because they're
   "advanced" leaves known gaps. The auth deferral is the only
   exception, justified by the auth schemes being independent of A2A's
   core semantics (a v0.2 auth update doesn't change how Tasks or
   Messages work).

**Rejected alternatives:**

*Minimum viable (client only).* **Rejected because** half the
orchestration DSL story. Without a server, Nodus workflows cannot be
called by other agents — they can only call others. The bidirectional
positioning is what makes Nodus "part of the agent ecosystem."

*Client + one binding (JSON-RPC only).* **Rejected because** the A2A
ecosystem allows agents to choose their binding, and a library limited
to JSON-RPC cannot interoperate with gRPC or REST agents. Limiting
binding support is a hidden capability gap.

*Build separately, ship as v4.x library after v4.0.* **Rejected because**
MCP and A2A together at v4.0 launch validate the protocol-adapter
pattern in a way that shipping MCP alone does not. Deferring A2A
weakens the LIBRARY_ECOSYSTEM.md architectural commitment.

*Ship full auth in v0.1.* **Rejected because** the auth schemes (OAuth2,
OIDC, mTLS) are substantial implementation effort each, and bearer
tokens cover the common case. Splitting them into v0.2 lets v0.1 ship
without the auth scope dominating the cycle.

**Spec verification discipline:**

Same as Decision 16. Before v4.0 PyPI release:

1. Fetch the A2A spec at https://github.com/a2aproject/A2A
2. Check release notes between A2A v1.0.0 (the pinned version) and
   current date
3. Classify changes: none, additive only, breaking/critical
4. Breaking/critical → pause v4.0 PyPI release, evaluate incorporation
5. Additive → note for nodus-a2a v0.2, proceed with v4.0 release
6. None → proceed as planned

Cost: ~1 hour. Applied once before v4.0 PyPI release.

**Reconsideration triggers:**

This decision should be revisited if:

- A2A spec ships a v2.0 with breaking changes before v4.0 release
  (spec verification catches this)
- A2A adoption proves smaller than projected post-v4.0 (the library
  scope is large; if the protocol's reach is small, scoping down to
  client-only is reasonable for v0.2)
- A different agent-to-agent protocol gains dominance during the v4.0
  cycle (LIBRARY_ECOSYSTEM.md's "protocols are adapters" commitment
  means swapping is recoverable)

Until one of those triggers fires, the comprehensive A2A v0.1 scope
holds.

---

## Process note: this is the second amendment to Phase 0

The original Phase 0 session (2026-05-25 morning) produced 16 decisions.
Both amendments above were drafted later the same day after fetching
both protocol specs.

The pattern that produced both gaps (Decision 16 missing Elicitation,
no Decision 17 for A2A) is the same: design drafted from memory rather
than against a fresh spec fetch.

**Process improvement captured:** for any Phase 0 decision that
references an external specification (protocol library, format spec,
standard), the decision drafting MUST include a spec fetch as the
first step. This is added to PLAYBOOK_MAJOR.md Phase 0 in this prep
batch.

---

## Cross-cutting decisions captured for reference

### Decision: Spec verification before external-protocol library release

For libraries implementing external specifications. Captured in
Decision 16; applies broadly to future protocol libraries.

### Decision: Reconsideration triggers documented per decision

Future contributors (or future-maintainer) sees the reasoning, the
rejected alternatives, and what would change the answer. Prevents
relitigation. Discipline applied to: `===` operator, general-purpose
stdlib, MCP in core, bootstrapping, async stdlib functions, coverage
instrumentation, test framework library vs language.

### Decision: Nothing cut entirely (Tier 5 eliminated)

Per playbook discipline. Everything known to be wrong gets tracked,
even if deferred. Applied to v4.0 scope across all 16 decisions.

---

## Next phase

Phase 1 (design docs) produces specifications implementing these
decisions. Approximately 8-12 design docs in `docs/design/v4/`, one
per major design area:

- HTTP API specification
- Datetime API specification
- Crypto/hashing API specification
- Subprocess API specification
- String interpolation lexer/parser/compiler changes
- Tool registry library-handler API
- Test framework API (likely 2-3 docs: assertions/runner, fixtures/
  scopes, coverage)
- IEEE 754 division semantics
- type() naming + math helpers
- Equality coercion + migration
- Doc-vs-code reconciliation gate
- err record location field additions

Plus design documentation referring to the MCP library (which has its
own design phase, separate from but informed by v4.0 Phase 1).

---

## File index

| What | Where |
|------|-------|
| This document | `docs/design/v4/00-phase-0-decisions.md` |
| v4.0 plan | `docs/governance/V4_0_PLAN.md` |
| Updated vision | `LANGUAGE_VISION.md` (project root) |
| New stdlib philosophy | `docs/governance/STDLIB_PHILOSOPHY.md` |
| Design docs (Phase 1) | `docs/design/v4/` (numbered 01+) |
| Migration guide | `docs/migration/v3-to-v4.md` (Phase 4 deliverable) |

Phase 0 complete. Phase 1 begins when ready.

---

## Addendum — Scope added after Phase 0 locked

**Date:** 2026-05-30
**Status:** Implemented. Decisions below reflect choices made during execution,
not during the original Phase 0 session. The locked decisions above are unchanged.

---

### A.I.N.D.Y. Ecosystem Audit → 27-package standalone ecosystem

During the v4.0 cycle, a full dependency and capability audit of A.I.N.D.Y.
(the production AI platform that Nodus targets) produced a second build wave:
9 library candidates and 7 framework candidates, all independent of the nodus-lang
core. A second audit (OpenClaw) produced 5 additional net-new libraries.

**Decision:** Build all libraries as standalone Python packages at `C:\dev\`,
each with its own GitHub repo under Masterplanner25. No nodus-lang dependency
unless the library provides nodus-lang bindings. Test each independently.

**Reasoning:**
1. Standalone packages can be installed and used without nodus-lang. This proves
   the primitives are sound independently.
2. Individual repos with independent version histories are easier to maintain and
   publish than a monorepo.
3. Each package is testable in isolation — no cross-package contamination.

**Resulting packages (27 total across 6 tiers):**

*Group 1 — A.I.N.D.Y.-derived (no nodus-lang dep):*
`nodus-circuit-breaker` (24 tests), `nodus-auth` (36), `nodus-observability` (27),
`nodus-queue` (53), `nodus-state` (117), `nodus-observability-framework` (57),
nodus-mcp aindy bridge (81, in nodus-mcp repo as `nodus_mcp_aindy/`)

*Group 2 — OpenClaw-derived:*
`nodus-context` (29), `nodus-approvals` (32), `nodus-channels` (24),
`nodus-llm` (24), `nodus-delivery` (27)

*Group 3 — Tier 1 standalone:*
`nodus-retry` (33), `nodus-http` (13), `nodus-events` (17), `nodus-schema` (30),
`nodus-protocol` (13), `nodus-session` (15), `nodus-router` (18)

*Group 4 — Tier 2 (depends on Tier 1):*
`nodus-memory` (28), `nodus-workflow` (17), `nodus-a2a` (23, AgentCoordinator),
`nodus-adapters/base` (11)

*Group 5 — Tier 3 (depends on T1+T2):*
`nodus-agent` (28), `nodus-gateway` (19)

*Group 6 — Tier 4 (depends on all tiers):*
`nodus-extensions` (35), `nodus-governance` (28)

**Note on nodus-a2a:** The original Decision 17 nodus-a2a (A2A wire protocol adapter,
180 tests, Phases A–J) was replaced at `C:\dev\nodus-a2a` by the AgentCoordinator
layer. The original wire protocol adapter is preserved on GitHub
(`github.com/Masterplanner25/nodus-a2a`, git history intact).

---

### nodus-memory v0.1.0 and nodus-native-memory-engine v0.1.0 — companion repos

**Decision:** Two additional companion repos built alongside the standalone packages.
`nodus-memory` provides nodus-lang bindings (`attach_to_runtime`, `nm_*` host functions,
`import "nodus-memory"` in .nd code). `nodus-native-memory-engine` provides a
PyO3/Maturin Rust extension for 9 hot-path memory operations with pure-Python fallback.

The original Tier 2 LIBRARY_ECOSYSTEM entry for `nodus-memory` tracked it for
v5.0. It shipped ahead of schedule as a v0.1.0 companion repo.

**Status:** v0.1.0 COMPLETE — prepared, not yet published.
- nodus-memory: 192 tests, 97% coverage, Phases A–K
- nodus-native-memory-engine: 76 tests, PyO3/Maturin Rust, 9 operations

---

### nodus-extension v0.1.0 — extension companion repo

**Decision:** Build the extension/plugin framework as a companion repo (not in-tree).
`nodus-extension` provides typed, versioned, sandboxed plugin loading: extensions
declare `nodus-extension.json` + `extension.py`; the framework loads them via
subprocess (sandbox tier 1). Exposes `_ext_*` host functions and `import
"nodus-extension"` in .nd code.

**Status:** v0.1.0 COMPLETE — prepared, not yet published.
- 126 tests, 93% coverage, Phases A–J

---

### nodus-workflow and nodus_schema — dual implementations

**Decision:** Both `nodus_workflow` and `nodus_schema` exist in two forms: in-tree
(wired into nodus-lang's server/CLI, full orchestration surfaces) and standalone
(lighter packages without server wiring). This duplication is intentional — the in-tree
versions serve nodus-lang's own orchestration surfaces; the standalone versions serve
the ecosystem packages that need the primitives without nodus-lang itself.

| Name | In-tree location | Standalone location |
|---|---|---|
| `nodus_schema` | `src/nodus_schema/` — syscall ABI contracts | `C:\dev\nodus-schema` — general schema validation |
| `nodus_workflow` | `src/nodus_workflow/` — HTTP/CLI/SQLite orchestration | `C:\dev\nodus-workflow` — standalone FlowDefinition/SchedulerEngine |

**Rule:** Always check `python -c "import nodus_schema; print(nodus_schema.__file__)"` before
working on either — import order determines which version loads.

---

### Phase 6 — AI-Native Language Primitives (v4.0.0 pre-release cycle)

**Decision:** After completing v4.0, a further phase of work adds AI-agent-oriented
primitives directly to the nodus-lang stdlib and VM. These close the gap between the
27-package library ecosystem and the language surface.

**Why this wasn't in Phase 0:** Phase 0 focused on the orchestration DSL as a tool
for human developers. The AI-native analysis (performed against both audits) identified
a second design space: an AI agent as the primary developer of .nd code. That framing
produced different design requirements (automatic identity propagation, first-class
idempotency, enumerable syscall surface, declarative reliability).

**Five sub-phases implemented (prepared, not yet published — part of v4.0.0 pre-release cycle):**
- **6A — Execution identity:** `trace_id`, `execution_unit_id` on every VM + event.
  `std:identity`, `NodusRuntime.set_trace_id()`. All module VMs propagate identity.
- **6B — Namespaced memory:** `recall_from`, `recall_all`, `share` in `std:memory`.
  Memory builtins extracted from `VM.__init__` to `memory_module.py`.
- **6C — sys.v1.* syscall dispatch:** `syscall_runtime.py`, uniform envelope,
  4 initial syscalls, `std:sys`.
- **6D — EffectStore as language primitive:** `nodus-retry` promoted to required dep.
  `std:effects`. `NodusRuntime.set_effect_store()`.
- **6E — Retry/CB stdlib bindings:** `std:retry`, `std:circuit_breaker` as optional-dep
  stdlib modules. `_ClosureProxy`-aware closure execution.

**Deferred to Phase 7:** `@exactly_once` and `@retry(...)` annotation syntax (requires
lexer/parser/compiler changes). The runtime primitives (6D) provide the semantics;
Phase 7 adds the syntactic sugar.

**Version:** Still 4.0.0 (additions implemented during v4.0.0 pre-release hold). BYTECODE_VERSION stays at 4 (no new opcodes).

---

### Phase A–D — HandlerContract infrastructure (v4.0.0 pre-release cycle)

**Decision:** Add a formal contract type (`HandlerContract`) to `nodus_schema` for
documenting handler surfaces (tools, syscalls, extension tools) and enforce contracts
at the `tool.register()` / `tool.invoke()` layer.

**Why this wasn't in Phase 0:** Phase 0's tool registry decision (Decision 12) focused
on dynamic registration and conflict detection. The contract-enforcement layer
(effects vocabulary, returns_schema validation) emerged from the A.I.N.D.Y. audit's
observation that AI-generated tool handlers need machine-verifiable contracts.

**Four sub-phases:**
- **A — nodus_schema:** `HandlerContract` dataclass + `VALID_EFFECTS` frozenset
- **B — tool_module.py:** `effects` validation + `returns_schema` at invoke time
- **C — nodus-extension:** `ToolSurface` gains `returns_schema` and `effects` fields
- **D — nodus_gate:** `--contracts` flag (6 smoke-test checks) wired into `--all`

---

### nodus-sdk v0.1.0 — unified platform SDK

**Decision:** Build a single unified SDK package (`nodus-sdk`) that provides the
installation story for the full ecosystem. Extras-based optional deps. A factory
function (`create_runtime(**kwargs)`) auto-wires available packages. New Python
bridges (SQLAlchemy, pgvector, APScheduler, FastAPI, webhook) live in the SDK, not
as additional standalone packages.

**Why one SDK:** The 27-package ecosystem is powerful but requires knowing which 6-8
packages to combine. A single `pip install nodus-sdk[agent,sql,fastapi]` is the
production installation story.

**Status:** v0.1.0 COMPLETE — 99 tests, 9 bridge modules.
Repo: `C:\dev\nodus-sdk` / `github.com/Masterplanner25/nodus-sdk`

---

### nodus-store-sql v0.1.0 — SQLAlchemy persistence adapters

**Decision:** Promote the `packages/nodus-store-sql` incubator scaffold to a
standalone production package. The scaffold's design (frozen dataclasses + SQLAlchemy
ORM + store classes) was sound; it needed API completion (4 new methods), async
support, and test expansion.

**Why this gap existed:** The scaffold was in `packages/` as a design reference —
both audits listed it as "Done" prematurely. This was the last audit gap.

**Status:** v0.1.0 COMPLETE — 47 tests (31 sync + 16 async).
Repo: `C:\dev\nodus-store-sql` / `github.com/Masterplanner25/nodus-store-sql`

---

## Updated file index (post-addendum)

| What | Where |
|---|---|
| Original Phase 0 decisions | this document (above) |
| Ecosystem library index | `docs/governance/LIBRARY_ECOSYSTEM.md` |
| Per-package readiness | `docs/governance/ECOSYSTEM_READINESS_ASSESSMENT.md` |
| Known tech debt | `docs/governance/TECH_DEBT.md` |
| Changelog | `CHANGELOG.md` |
| Standalone packages | `C:\dev\nodus-{package}` (29 packages) |
| Incubator scaffolds | `packages/` (design references, not production) |