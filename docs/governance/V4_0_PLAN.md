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