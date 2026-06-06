# NODUS v4.0.0 — POST-PUBLISH STRESS-TEST EVAL LOG

Chronological evidence trail. Every entry has command, input, verbatim output, exit code.

---

## Entry #1 — Version provenance

**Install command:** `pip install nodus-lang==4.0.0` (pre-installed in `.venv` per setup)
**Install source:** POST-PUBLISH (PyPI)

```
$ nodus.exe --version
Nodus 4.0.0

$ python --version
Python 3.11.9

$ PSVersion
5.1.26100.8457

$ pip show nodus-lang
Name: nodus-lang
Version: 4.0.0
Location: C:\dev\Nodustestenvv4\.venv\Lib\site-packages
Requires: httpx, tzdata

OS: Microsoft Windows 11 Home
```

**Import resolution check (CRITICAL — confirm not using dev source):**
```
$ Set-Location C:\dev\Nodustestenvv4
$ python -c "import nodus; print(nodus.__file__)"
C:\dev\Nodustestenvv4\.venv\Lib\site-packages\nodus\__init__.py

$ python -c "from nodus.support.version import __version__; print(__version__)"
4.0.0
```

**GOTCHA NOTE:** When cwd is `C:\dev\Coding Language` (the dev repo, contains a top-level
`nodus.py`), `import nodus` resolves to the dev `nodus.py` shim, NOT the installed package.
All eval commands MUST run with cwd = `C:\dev\Nodustestenvv4` to use the PyPI install.
Verified: from the test env cwd, the installed site-packages copy is used. Resolved version 4.0.0. **MATCHES. Proceeding.**

---

## Entry #2 — First contact (run/check/fmt/embed)

```
$ nodus run scratch\hello.nd        → hello, world         exit=0
$ nodus check scratch\hello.nd      → scratch\hello.nd: OK exit=0
$ nodus fmt scratch\hello.nd        → (formatted, no output) exit=0
$ python scratch\embed_hello.py
{'ok': True, 'stage': 'execute', 'filename': '<memory>', 'stdout': 'hello\n', 'stderr': '', 'result': None, 'errors': [], 'diagnostics': [], 'error': None}
```
`nodus --help` lists all subcommands (run/check/fmt/repl/workflow/goal-run/serve/etc.). On-ramp works as advertised.
NOTE: help text shows a mojibake char ("�") where an arrow should be in the stability tier lines (Windows console cp encoding). COSMETIC.

## Entry #3 — Integer/float type model

types.nd / types2.nd output:
```
1i + 2i        → 3      type int
1.0 + 2.0      → 3.0    type float
1i + 2.0       → 3.0    type float   (mixed promotes to float)
5i / 2i        → 2.5    type float   (division ALWAYS float, never truncates)
5i / 2.0       → 2.5
len([1i,2i,3i])→ 3      type int
9999999999999999i * 9999999999999999i → 99999999999999980000000000000001  type int (arbitrary precision; NO overflow)
```

## Entry #4 — Maps vs Records

maprec.nd: `{key:"val"}` → record, `r.key`="val", type=record. `{"key":"val"}` → map, `m["key"]`="val", type=map.
dotmap.nd (dot a map):
```
Type error at ...dotmap.nd:2:7: Field access is only supported on records
```
idxrec.nd (index a record):
```
Type error at ...idxrec.nd:2:9: Indexing is only supported on lists and maps
```
Both documented messages fire exactly, with file:line:col. PASS.

## Entry #5 — Known language constraints

```
print("a","b")  → Syntax error ...:1:10: Expected ')', got ','
x += 1i         → Syntax error ...:2:4: Unexpected '=' in expression
[1i,\n2i]       → Syntax error ...:1:13: Unexpected end of statement - expression is incomplete
let fn = 1i     → Syntax error ...:1:5: Expected identifier, got 'fn'
await foo()     → Name error ...:1:9: Undefined variable: await   (await parsed as identifier; no dedicated "await unsupported" message)
```
All have file:line:col. `await` message is generic (treats it as an undefined var) — minor AI-authorability gap.

## Entry #6 — Type coercion (strict equality, no coercion)

coerce.nd:
```
"5" == 5i   → false
nil == false→ false
0i == false → false
[] == false → false
```
No implicit coercion. Strict.

## Entry #7 — Error model (err records + try/catch)

errmodel.nd: `json.parse("{invalid}")` → type=error, .kind=parse_error,
  .message="invalid JSON at line 1 column 2: expected property name"  (Nodus err record, NOT leaked Python exception)
trycatch.nd:
```
key
Missing map key: "missing"
3
["at <main> (...trycatch.nd:3:13)"]
always runs
thrown
boom
nil
```
try/catch/finally + throw all work as documented. err.kind/.message/.line/.stack/.payload present.
NOTE: bare `import "std:json"` (without `as json`) succeeds but binds NO name → `json` is undefined.
  Correct form is `import "std:json" as json`. (Bare import is legal but useless — minor.)

## Entry #8 — Parser adversarial input

```
empty.nd          → exit 0 (no error)
ws.nd             → exit 0
commentonly.nd    → exit 0
unclosed_str.nd   → Syntax error ...:1:9: Unterminated string literal
unclosed_bracket  → Syntax error ...:1:20: Expected ']', got end of statement
unicode.nd (let café=) → Syntax error ...:1:8: Identifiers must use ASCII letters only: '<char>'
nested (100 parens) → Syntax error ...:1:57: Expression too deeply nested (max depth: 50)  (NO crash/stack overflow)
unicode_str.nd    → café 日本語 🎉 / len=10 (codepoints) — unicode in STRINGS works
crlf.nd (mixed CRLF+LF) → 3 (handled fine)
```

## Entry #9 — stdlib: json/hash/strings/math

stdlib1.nd:
```
json.stringify({"a":1i,"b":[true,nil]}) → {"a": 1, "b": [true, null]}
json.parse("[1,2,3]")                   → [1.0, 2.0, 3.0]   (JSON ints become FLOATS — documented)
json.stringify(nil)                     → null
hash.sha256("hello") type               → hash (record)
  .to_hex()                             → 2cf24dba...9824 (correct)
  print(record)                         → record {"to_hex":<builtin-method>,...,"algorithm":"sha256","length":32}
strings.upper("hello")  → HELLO
strings.split("a,b,c",",") → ["a","b","c"]
strings.trim("  hi  ")  → hi
math.sqrt(16.0) → 4.0
math.sqrt(-1.0) → err record: "math.sqrt requires a non-negative number, got -1.0"  type error
```
jsonint.nd: json.parse("42")→42.0 (float); parse({"n":7})["n"]→7.0 float; stringify(parse("42"))→42 (round-trips). DOCUMENTED in working-with-json.md.

## Entry #10 — stdlib: fs + path traversal sandbox (CLI vs EMBEDDED)

fstest.nd: write/read/exists work; read nonexistent → err record "file not found".
traversal.nd CLI (no flag):
```
Sandbox error ...:2:17: read_file(path) blocked: path '../../...etc/hosts' escapes the project root
```
traversal.nd CLI (--allow-paths scratch): still blocked.
EMBEDDED (scratch\embed_sandbox.py):
```
=== default (no allowed_paths) ===
ok: True | stdout: 'string\n' | error: None      <-- READ SUCCEEDED, returned a string
=== with allowed_paths=[scratch] ===
ok: False | ... error: sandbox "read_file(path) blocked for path: '../../...etc/hosts'"
```
embed_traversal.py default printed the FULL CONTENTS of C:\Windows\System32\drivers\etc\hosts.
**FINDING (HIGH/security): default NodusRuntime() embedded has NO filesystem sandbox.** CLI is
default-secure (project-root jail); embedded default is open. Documented as opt-in allowed_paths,
but the asymmetry is a trap for the primary audience (AI agents in embedded hosts). allowed_paths
mitigation WORKS when passed.

## Entry #11 — stdlib: http / subprocess (record shapes)

httpsub.nd:
```
http.get("https://example.com") type → http_response;  .status=200  .ok=true  len(.body)>0=true
subprocess.run(["cmd","/c","echo","hello"]) type → subprocess_result; .exit_code=0  .stdout="hello\n"
```
Both records, dot notation, as documented. NOTE: no network sandbox flag exists (http open by default in CLI).

## Entry #12 — stdlib: tool (dotted-name requirement)

tooltest.nd (multi-line record literal in call works):
```
tool.register({name:"myapp.greet",...}) type → record
tool.has("myapp.greet") → true
tool.invoke("myapp.greet",{name:"World"}) → Hello World
tool.register({name:"greet",...}) type → error
  .message → "tool.register: tool name 'greet' must use dotted namespacing (e.g. 'myapp.tool_name')"
```
Excellent actionable error message.

## Entry #13 — stdlib: encoding/time/env + wrong-type

stdlib2.nd:
```
encoding.base64_encode("hello") → aGVsbG8=
time.now() type → datetime
env.get("PATH") != nil → true
env.get("NONEXISTENT_VAR_XYZ") → nil
strings.upper(42i) → Type error ...:14:21: upper(x) expects a string  (clean, positioned)
```
b64.nd / b64str.nd — base64_decode returns BYTES not string:
```
base64_decode(base64_encode("hello")) → 68656c6c6f   type=bytes  (hex display of "hello")
base64_decode(base64_encode("hello world")) == "hello world" → false
str(<bytes>) → 68656c6c6f20776f726c64  (hex, not text)
```
**FINDING (HIGH/docs): standard-library.md §std:encoding claims `base64_decode(b64)` returns `"hello world"`
(a string). It actually returns `bytes` that print/compare as hex. The documented round-trip is broken —
no obvious bytes→string path; str(bytes)=hex, ==string=false.**

## Entry #14 — Workflow DSL

wf_basic.nd:
```
compile / test / package / deploy
type(run_workflow result): map
r["steps"]: {"compile": nil, "test": nil, "package": nil, "deploy": nil}  (keyed by STEP NAME)
r["failed"]: []
plan_workflow levels: [["compile"], ["test","package"], ["deploy"]]
```
wf_checkpoint.nd: `checkpoint "mid"` inside step → works ("a done").
wf_cp_bad.nd (checkpoint at workflow body level):
```
Syntax error ...:2:5: workflow body must contain state declarations or steps
```
wf_baddep.nd (after nonexistent):
```
Syntax error ...:3:5: Unknown workflow dependency: nonexistent   (compile-time)
```
wf_cycle.nd / wf_cycle2.nd:
```
type → error;  message "Dependency cycle detected: a -> b -> a";  .kind = workflow_error
```

## Entry #15 — Workflow failure propagation + DIV-BY-ZERO (key finding)

wf_fail.nd (step does `let x = 1i / 0i`):
```
good ran
this should NOT run     <-- downstream DID run
r["error"] → Key error: Missing map key "error"  (no error key exists)
r["failed"] → []        (failure NOT recorded)
```
wf_fail2.nd full result stringify (success-shaped despite the "failing" step):
```
{"tasks":{...null}, "steps":{"good":null,"will_fail":null,"downstream":null},
 "failed":[], "cache_hits":[], "state":{}, "checkpoints":[], "workflow":"wf", ...}
```
Doc (workflows-and-tasks.md §5) claims: r["error"]="Division by zero", r["failed"]=["task_2"],
downstream does NOT run. NONE of that happened.

ROOT CAUSE — divzero.nd / divzero_catch.nd / divzero3.nd:
```
let x = 1i / 0i ; print(type(x)) → error   ; print(x) → "Integer division by zero"
```
`1i / 0i` RETURNS AN ERR RECORD AS A VALUE — it does NOT throw.
try/catch around it: catch block does NOT fire (caught flag = false).
`1.0 / 0.0` → inf (IEEE, no error).
math.idiv(10i,0i) → err record "division by zero".

So div-by-zero is errors-as-value, never thrown → try/catch can't catch it → workflow step
"succeeds" → downstream runs, failed=[]. 

wf_throw.nd (step does explicit `throw "boom"`): workflow DOES handle real throws correctly:
```
failed: ["task_2"];  steps: {"good": null}   (downstream skipped)
```
So workflow failure propagation works for THROWS, but div-by-zero (and math errors) never throw.

**FINDING (HIGH/runtime+docs): division by zero is NOT catchable.** error-handling.md line 17
says "division by zero ... catchable with try/catch" and line 233 documents kind="runtime"
message "Division by zero". Actual: `1i/0i` returns an err record as a value, never throws;
try/catch never fires; workflow steps that divide by zero report success and run downstream.
This silently defeats workflow failure detection for arithmetic errors.

## Entry #16 — Goal DSL (PROMPT vs REALITY discrepancy)

goal_doc.nd (documented step-based form, goal==workflow):
```
tagging / publishing
type(run_goal result): map
r["goal"]: release
r["steps"]: {"tag": nil, "publish": nil}
```
goal_swfw.nd (eval prompt §4.3 form `success_when {} fail_when {}`):
```
Syntax error ...:2:5: goal body must contain state declarations or steps
```
**DISCREPANCY (integrity rule 5):** The eval prompt §4.3 describes a goal DSL with
`success_when`/`fail_when` blocks. That form DOES NOT EXIST in shipped v4.0.0. The public
docs (workflows-and-tasks.md §7) say goal==workflow with identical step/after syntax — and
that is what ships. Evaluated the shipped (documented) form; it works. The prompt's claimed
goal surface was never shipped (or removed). Goals cannot "loop forever" — they are finite DAGs.

CLI: `nodus workflow run scratch\wf_basic.nd --workflow build` runs (re-executes workflow, prints
JSON payload). `nodus workflow list` shows persisted snapshots incl. status=failed for the throw case
(g_9c63e80f) — so the CLI layer DOES track failure even though in-script run_workflow map didn't.
All documented subcommands present: run/list/resume/dead-letters/runs/inspect/replay/migrate-state/cleanup.
NOTE: `nodus goal-run --help` → "File not found: --help" (goal-run takes a file, no --help). LOW.

## Entry #17 — Coroutines & channels

chan_basic.nd (producer/consumer): producer sends 0,1,2 + close; consumer prints got:0/1/2 then
CRASHES on `break`:
```
Name error ...:16:13: Undefined variable: break
got: 0 / got: 1 / got: 2
```
**FINDING (MEDIUM): `break` (and `continue`) not supported.** LANGUAGE_SPEC.md line 77 documents
loops as "Mostly stable (missing break/continue)" — so it's a KNOWN limitation, but the runtime
error is "Undefined variable: break", which misleads (a model/human reads it as a typo, not a
missing feature). breaktest.nd confirms: `while {... break ...}` → "Undefined variable: break".

chan_import.nd: `import "std:channel"` → "Import error: Import not found: std:channel (tried ...)" — as documented.
spawn_fn.nd: `spawn(fn(){...})` → "Type error: spawn(coroutine) expects a coroutine" — excellent.
chan_closed.nd: recv on closed-empty → nil; send on closed → "Runtime error: send on closed channel".
chan_empty.nd (recv with no sender, --time-limit 5): "waiting..." then "run_loop exited" — run_loop
EXITS (does not hang); the blocked coroutine is silently stranded (CHAN-001). No hang = robust, but silent orphan.

## Entry #18 — Async builtins (concurrency)

scratch\async_concurrency.py (doc example from embedding-nodus.md, PY path backslashes fixed):
```
ok: True | stdout: 'a\nb\nc\n' | elapsed: 1.36s   (3 x 1s subprocess_run_async → ~1.3s, NOT ~3s)
```
TRUE CONCURRENCY CONFIRMED for subprocess_run_async in spawned coroutines.
NOTE (LOW/docs): the doc example as written uses `PY = sys.executable`; on Windows that path has
backslashes → injected into Nodus source → "Unsupported escape sequence: \d". Doc example is not
Windows-portable as written.

## Entry #19 — NodusRuntime 200ms deadline (EMBED-001)

scratch\deadline.py (5M-iteration busy loop):
```
default NodusRuntime():          [0.44s] ok:False  error: sandbox "Execution timed out"   <-- KILLED
NodusRuntime(timeout_ms=None):   [110.45s] ok:True  stdout:"finished busy loop"            <-- SURVIVED
```
200ms deadline trap CONFIRMED. Mitigation (timeout_ms=None, max_steps=None) works.
PERFORMANCE DATA POINT: 5,000,000 loop iterations took 110 SECONDS without a deadline
(~45k iterations/sec). The tree-walking VM is very slow for compute-bound code.

## Entry #20 — Embedding round-trip + isolation

scratch\embed_roundtrip.py:
```
round-trip prelude (let input_value=42i; computed=input_value*2i) → stdout "84\nhello world\n"
register_function("get_secret", lambda) → "secret: injected-from-python"
ISOLATION: rt_a.register_function only_a → rt_a sees "A"; rt_b → ok:False "Undefined function: only_a"
```
Two NodusRuntime instances are isolated. register_function works. Round-trip fidelity good.

## Entry #21 — CLI flag regression

scratch\readhello.nd / readoutside.nd:
```
--allowed-paths scratch → "File not found: --allowed-paths"  (wrong flag name, treated as file arg)
--allow-paths scratch (read inside scratch) → "hello, world"  exit 0
--allow-paths scratch (read outside.txt) → Sandbox error: read_file(path) blocked for path: 'outside.txt'  exit 1
```
Correct flag is `--allow-paths`; it actually restricts. `--allowed-paths` does not exist.

## Entry #22 — Migration audit (v3.0.2 → v4.0.0)

v3style.nd (plain `let count = 3`, `total = total + i`, dot-access on json.parse):
```
Type error ...:14:7: Field access is only supported on records   (data.name on json.parse map)
3.0    <-- total printed as FLOAT 3.0, not int 3
```
plainlit.nd:
```
type(3)  → float       type(3i) → int
3 / 2    → 1.5         type(3/2) → float
3 + 4    → 7.0
```
**KEY MIGRATION FINDING:** plain integer literals (`3`, `0`) are now FLOATS in v4. A v3 program
with bare ints does NOT error — it silently runs with all-float arithmetic. Combined with json.parse
dot-access breaking, a v3 program "half-runs": some lines work (as floats), dot-access throws.

DIV-BY-ZERO RECONCILED with CHANGELOG: int div-by-zero returning an err-as-value (kind=math_error,
origin=vm) is INTENTIONAL, DOCUMENTED v4 behavior (CHANGELOG "Doc 09", migration guide §4 note).
divzero_kind.nd confirms: .kind=math_error, .origin=vm, .message="Integer division by zero".
=> My earlier "div-by-zero bug" downgrades to: (a) docs CONFLICT — error-handling.md line 17/233
still says div-by-zero is "catchable with try/catch" (kind "runtime"), contradicting CHANGELOG +
reality (err-as-value, not thrown, kind math_error); (b) a workflow TRAP — a step that divides by
zero gets an err-value, never throws, so the step "succeeds" + downstream runs + failed=[].

Migration guide (docs/migration/v3-to-v4.md) EXISTS and is thorough. mig_verify.nd — every documented
helper works:
```
math.is_float(3.0)→true  math.is_int(3i)→true  math.is_numeric(3i)→true  math.is_numeric(3.0)→true
type_eq(1i,1.0)→false    bool.equal(true,true)→true   index_of([1i,2i,3i],9i)→nil
"Hello, \(name)!"→Hello, world!   "1 + 1 = \(1i + 1i)"→1 + 1 = 2
```
mig_cycle.nd — cyclic workflow err payload exactly as documented:
```
type→error  .kind→workflow_error  payload["category"]→cyclic_workflow  payload["cycle"]→["a","b"]
```
**GAP:** the migration guide does NOT mention that plain integer literals become floats, nor the
json.parse dot→bracket break prominently (only LANGUAGE_SPEC notes it). The single most common v3
pattern (bare integer literals) silently changes semantics with no guide entry.

## Entry #23 — Build something real (JSON directory → report)

Built scratch/real_task/: main.nd (entry) + stats.nd (export fn helper module). Reads 4 JSON order
files from data/, aggregates totals/status-counts/spend-by-customer, writes report.json.
Modules: std:fs, std:json, std:strings, std:math (4) + local "./stats" module. ~75 lines total.

STICKING POINTS (each cost a run + doc lookup):
1. `strings.ends_with(name, ".json")` → "Missing module export: ends_with". std:strings has NO
   ends_with/starts_with — only `contains`. Worked around with strings.contains(name, ".json").
   FINDING (MEDIUM/stdlib): no ends_with/starts_with/has_prefix/has_suffix in std:strings.
2. `push(orders, parsed)` → "Undefined function: push". The TOP-LEVEL builtin is `list_push`;
   `push` only exists as `col.push` via `import "std:collections"`. The docs list BOTH `list_push`
   (builtin, no import) and `push` (collections module) — easy to grab the wrong one.
   FINDING (LOW/docs): two names for list append (`list_push` builtin vs `push` in std:collections)
   is a discoverability trap.

WHAT WORKED FIRST TRY: export fn / import "./stats" as stats; has_key; math.round; string
interpolation in print; fs.listdir/read/write; json.parse/stringify; map mutation via bracket notation.

Final run:
```
loaded 4 orders
wrote report to scratch/real_task/report.json
{"order_count": 4, "grand_total": 218.75, "by_status": {"shipped": 2, "pending": 1, "cancelled": 1}, "spend_by_customer": {"alice": 179.75, "bob": 12, "carol": 27}}
```
Aggregation correct (alice 49.5+130.25=179.75). nodus check main.nd / stats.nd → OK. nodus fmt
main.nd → reflowed multi-line map literal to one line + stripped blank lines; re-run still correct.
NOTE: json.stringify dropped .0 from whole floats (12.0→12, 27.0→27) — documented behavior.

EXPERIENCE: ~15 min. The two stickly points were both stdlib-discoverability (missing ends_with;
list_push vs push). Error messages were precise enough ("Missing module export: ends_with",
"Undefined function: push") that the fix was fast. Map vs record bracket/dot discipline held up well.
A model writing this from the docs would hit the same two snags but recover from the error text.

## Entry #24 — Error message quality summary (cross-cutting)

Every error triggered carried file:line:col and a Nodus-typed prefix (Type error / Syntax error /
Name error / Sandbox error / Runtime error / Key error / Import error / Thrown error). NO leaked
Python tracebacks observed in any test (CLI or embedded). Embedded errors come back as structured
dicts (type/kind/message/path/line/column/stack). Standouts: tool.register dotted-name error suggests
the fix format; spawn(fn) error names the expected type. Weak spots: `break`→"Undefined variable:
break" (misleads); `await`→"Undefined variable: await" (no "not supported" hint); div-by-zero
err-as-value contradicts error-handling.md's "catchable" claim.

## Entry #25 — Stability index + iteration

`nodus stability` (exit 0): clearly marks Coroutines/Channels (Phase B), Goal DSL (Phase C),
Workflow DSL (Phase D), Static types as EXPERIMENTAL ("behavior may change in any release").
Core language, error model, embedding API, std:json/std:fs = STABLE. std:math/strings/collections/path
+ for-in + yield = MOSTLY STABLE. This appropriately tempers severity of workflow/channel sharp corners.
COSMETIC: the em-dash renders as mojibake "�" in --help and stability output on Windows console.

Exit-code check (all 0): stability, --version, --help, status. (An earlier "exit=-1" was a PowerShell
2>&1 NativeCommandError artifact, NOT a real Nodus exit code — re-verified clean.)

forin.nd / mapiter.nd:
```
for x in [10i,20i,30i] → 10/20/30                  (list iteration works)
has_key(m,"a")→true  has_key(m,"z")→false
for k in m  → Type error: "Value is not iterable"  (maps NOT directly iterable)
for k in keys(m) → "a = 1" / "b = 2"  values(m)→[1,2]   (documented form works, insertion order)
```
`for k in m` is correctly rejected per docs (use keys(m)). MINOR: error "Value is not iterable"
could hint "use keys(m) to iterate a map".
