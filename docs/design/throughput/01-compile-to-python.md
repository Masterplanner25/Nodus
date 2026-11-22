# Compiling Nodus functions to Python (#173)

**Status: decided 2026-11-21; phase 1 implemented in `nodus/vm/pycompile.py`.
The decisions are at the end. "Phase 1 as built" records where the implementation
departs from the plan.**

## Why

On CPython the interpreter's dispatch loop is the floor. Every instruction pays a
fixed Python cost: fetch, dict dispatch, a method call, attribute traffic. The
handler work (#965), fewer instructions (#966, #967) and fused instructions (#970)
have taken most of what is available inside that design. PyPy is about 16× on one
long run, but only 2.1–2.3× on many short ones (#973, #974), and it is a different
runtime, not a fix for CPython.

A prototype (results on #173, 2026-11-21) translated a function's optimized
bytecode into a Python function. Locals became Python locals, operand-stack slots
became temporaries, and control flow dispatched per basic block. Its results on
the self-hosted frontend:
- **50 of 75 functions** translated with a small opcode set.
- **The same output and the same `instructions_executed`** as the interpreter.
- **Compiled instructions about 4–5× faster** than interpreted ones.
- **Per-block budget checks** cost nothing measurable.
- **A `max_steps` limit** was enforced within one block.

That prototype skipped everything that makes a real version hard. This document
is about those parts.

## Goal and non-goals

**The goal:** a hot function that is eligible runs as generated Python, and a
program cannot tell, except by speed. That means:
- the same results and output;
- the same errors, with the same kind, message, location and stack trace;
- the same `instructions_executed`, and the same `max_steps`, deadline and
  capability enforcement;
- the same events for anything that observes.

**Not goals:**
- A JIT with type specialisation.
- Compiling top-level module code.
- Making suspension, `try`/`finally` or closures compile in the first phase.
- Persisting generated code in the bytecode cache in the first phase.

## Where it hooks in

**The interpreter stays the default and the fallback.** Compilation is per
`FunctionInfo` and lazy. A function is compiled after `N` calls (proposed: 32), so a
short program pays nothing. The result is cached against the function and the
chunk it belongs to.

**One dispatch point:** `CALL` to a named user function in the current chunk. That
is every call in the self-hosted frontend; it has no `CALL_VALUE` or
`CALL_METHOD`. The check is: compiled, eligible, and allowed now (see "When
compiled code may run"). If any part fails, the call takes the interpreter path
unchanged.

**Compiled code calls three kinds of thing:**
- **another compiled function**, directly, as a Python call;
- **a builtin**, through one shared method extracted from `VM.call_builtin` (see
  "Capability");
- **a user function that is eligible but not compiled**, through a synchronous
  interpreter call. That needs the callee to be unable to suspend, which
  eligibility already requires.

## Eligibility

A function is eligible when all of these hold, computed once from its bytecode:

1. **Every opcode is in the supported set.** Phase 1 supports the frontend's
   needs:
   - locals, constants and fields;
   - the arithmetic and comparison opcodes, `INDEX` and `BUILD_LIST`;
   - jumps and the fused instructions;
   - named `CALL` and `RETURN`.
2. **No cells.** The function has no upvalues and makes no closure, so no slot can
   hold a `Cell`.
3. **No `SETUP_TRY`.** Exception regions stay interpreted in phase 1.
4. **It cannot suspend.** Suspension is a least fixed point over the call graph.
   A function can suspend if it:
   - contains `YIELD`;
   - calls a builtin that can return a suspend request;
   - calls through `CALL_VALUE` or `CALL_METHOD`, where the target is unknown;
   - calls a function in another module;
   - or calls a function that can suspend.

**The suspending builtins are named once,** as a flag on the builtin's registry
entry, set where the builtin is registered. Today the builtins that can return a
suspend request are:
- `sleep`, `sleep_until` and the channel receive;
- the workflow `checkpoint`;
- the asynchronous `http` calls;
- agent calls (`VM._dispatch_agent_async`).

Some asynchronous `subprocess` operations are methods (`wait_async`). Any
`CALL_METHOD` already counts as possibly suspending, so those are covered.

The analysis and the VM read that flag, never a list of their own. That is the
recurring-bug-shape rule: name the set once and drive everything off it. An audit
of the suspend-request sites in phase 1 sets the flags.

## When compiled code may run

**Compiled code cannot pause.** So it may run only where the interpreter would
never pause mid-function:

- **No instrumentation:** `not vm._instrumented()`, meaning no debugger, profiler
  or trace. This is checked at each call, so attaching one mid-run takes effect at
  the next call.
- **No task step budget:** `vm.task_step_budget is None`. Inside a scheduled
  coroutine the interpreter yields when the task's budget runs out, so that other
  tasks get a turn. Compiled code would keep running until it returned, so a long
  loop inside a compiled function would starve every other task. Phase 1 does not
  compile in that context. Phase 4 lifts it.

Deadlines and `max_steps` do not need a pause, only an error, so compiled code
enforces them itself (see "Exactness").

## Exactness: the hard requirements

**Each of these is a requirement, not an optimisation to try later.** Each has a
test that compares a compiled run with an interpreted one.

1. **Semantics.** Every subtle operation calls the method the interpreter uses:
   `read_field`, `read_index`, `_nodus_eq`, `is_truthy`, `_binary_type_error`
   and the store-field path. Generated code may inline only the fast paths the
   interpreter's own handlers inline: exact type checks for `Record`, `str` and
   `bool`. Each inlined fast path is checked against its handler, as
   `test_vm_hot_paths.py` and `test_opcode_semantics_fused.py` do now.
2. **Counting and limits.** Each basic block adds its original instruction count
   to `instructions_executed`, then calls the interpreter's checks when
   `_next_check` is due. Limits can therefore overshoot by at most one block, which
   the prototype showed is 3 instructions on the frontend.
3. **Frames.** A compiled call pushes a `Frame` with the same fields the
   interpreter's `CALL` builds, and pops it on every exit, including exceptions.
   That keeps all of these working:
   - stack traces (`_build_error_stack`);
   - `max_frames` and `Call stack overflow`;
   - `handler_stack` depth comparisons, for an exception that propagates into an
     interpreted caller's `try`.

   It costs a frame per call. The prototype pushed none, so the cost has to be
   measured. If it matters, frames can be pooled.
4. **Locations.** Before any instruction that can raise, generated code stores
   that instruction's address in `vm.ip`. Errors are then built from
   `current_loc()` exactly as now. After the call returns, the interpreter's
   `CALL` restores `ip`.
5. **Capability (#405).** Builtins are called through one method extracted from
   `VM.call_builtin`: the arity check, `BUILTIN_CAPABILITIES`, the rebuild-effect
   handling, and the result handling. Both paths use it. This is a security
   boundary, so a second copy of that logic is not acceptable.
6. **Events.** A compiled call records `vm_call` and `vm_return` through
   `record_vm_call` and `record_vm_return`, exactly as an interpreted one does.
7. **Python recursion.** Nodus allows 10,000 frames; Python's default limit is
   1,000. A counter tracks compiled activations currently on the Python stack. At a
   cap (proposed: 200), dispatch stops choosing compiled code. The interpreter's
   own calls do not recurse in Python, so the Python stack stays bounded however
   deep the Nodus program goes.

## Generated code

The prototype's approach carries over:
- **one Python function per Nodus function;**
- **locals as Python locals;**
- **stack temporaries `s0..sN`**, from the stack depth fixed at each instruction;
- **a `while True` dispatch over basic-block leaders.**

The bytecode it starts from is the optimizer's output, fused instructions
included. Generation is deterministic, so the same bytecode always produces the
same source, which makes it testable and later cacheable.

## Testing

- **A spec per supported opcode**, run twice: on a VM, then in generated code, from
  the same state. The same pattern as `test_opcode_semantics_fused.py`.
- **A whole-suite differential mode.** A switch sets the compile threshold to
  zero, so every eligible function compiles on its first call. A CI job runs the
  suite in that mode, as the `pypy` job runs it under PyPy. That is the coverage
  that matters: 4,500 tests written against the interpreter, now run against
  compiled code.
- **`tools.selfhost_check` in both modes**, comparing tokens, trees and instruction
  counts.
- **Targeted tests for each requirement above:**
  - an error raised three compiled calls deep, checking its location and stack
    trace;
  - recursion past the depth cap;
  - `max_steps` and a deadline hit inside a compiled loop;
  - a denied capability called from compiled code;
  - an event sink attached mid-run;
  - a task budget making dispatch choose the interpreter.

## Phases

| Phase | Adds | Done when |
|---|---|---|
| 1 | Everything above, behind a switch, plus the differential CI job; also global `LOAD`/`STORE`, the `BUILD_*` opcodes, `INDEX_SET`, `MUL`/`DIV`/`MOD` and iteration (see "Phase 1 as built") | the suite passes in differential mode, and the frontend speedup is measured |
| 2 | Builtins outside the compilable categories, through the may-suspend analysis described under Eligibility. **Done** (see "Phase 2 as built"): capability-bearing builtins that cannot suspend | programs that call `http`, `subprocess` or agents in their hot paths compile |
| 3 | Cells and closures, `CALL_VALUE` with a known compiled target. **Done** (see "Phase 3 as built") | closure-heavy programs compile |
| 4 | Deoptimisation: rebuild interpreter frames from a compiled function's state at a block boundary, so it can pause | compiled code runs inside scheduled coroutines |

Phase 4 is the hard one, and it may not be worth doing.

## Phase 1 as built

Five places where the implementation departs from the plan above. Each is
narrower or safer than the plan, not looser.

1. **More opcodes than planned.** Phase 1 was to support only what the
   self-hosted frontend needed, but the frontend needed more than the plan listed.
   - **Iteration:** `reach` iterates over pending comments, and `eat` calls
     `reach`, so without iteration 31 of the frontend's 75 functions could not
     compile.
   - **Global `LOAD` and `STORE`:** `tok_name` reads the `TOKEN_NAMES` global.

   Both are exact by construction. `GET_ITER` runs the VM's handler, and
   `ITER_NEXT` calls the same `Iterator.advance()`. `LOAD` and `STORE` call
   `load_name` and `store_name`, so #671's semantics come with them. Any opcode
   without an inlined fast path calls the VM's own handler on `vm.stack`: the
   `BUILD_*` opcodes, `INDEX_SET`, `MUL`, `DIV`, `MOD`, `NEG` and `THROW`.
2. **A category allowlist instead of a may-suspend flag.** Compiled code may
   call only builtins in five `NO_AUTHORITY_BUILTINS` categories:
   - pure computation;
   - hashing;
   - path strings;
   - clock and randomness;
   - console I/O.

   These are synchronous, carry no authority, and never suspend. "In-process
   concurrency" (`sleep`, `recv`, `wait`, `run_loop`) and "orchestration"
   (`__workflow_checkpoint`, `workflow_wait`, `retry_call`) are excluded. So were
   all capability-bearing builtins in phase 1, which made #405's check
   unreachable from compiled code. Calls still went through the shared
   `invoke_builtin`. Phase 2 admits them (see "Phase 2 as built").
3. **A closed set.** A compiled function calls only builtins and other eligible
   functions, never an interpreted one. So there is no synchronous interpreter
   call on the normal path. One exists for the depth cap (`call_interpreted`):
   - it pushes the frame with a return address one past the end of the code,
     which ends a nested `execute()`;
   - it hides `handler_stack`, because nothing in a closed set has a `try`.
4. **Errors leave frames, as the interpreter does.** A compiled function pops its
   frame only on a normal return. On an error the frames stay, and
   `handle_exception` unwinds them, exactly as it does for an interpreted callee.
   Stack traces and locations then match by construction.
5. **Counting is corrected on the error path.** A block is counted when it is
   entered, so if an instruction in it raises, the rest of the block is
   subtracted. Each instruction that can raise stores its address. Before this,
   the differential tests found error runs counting a few instructions more than
   the interpreter, for example 164 against 122.

## Phase 2 as built

Compiled code may call every capability-bearing builtin that cannot suspend:
- the synchronous `http`, `subprocess`, file, environment, memory, tool and
  agent builtins;
- `syscall`.

These are in addition to the five no-authority categories from phase 1.

**The may-suspend set is declared once**, as `MAY_SUSPEND_BUILTINS` in
`runtime/capability.py`, next to the authority classification, rather than as a
flag on each registration site.

**A test derives the same set from the source and requires them equal.** It
starts from the request classes `VM.call_builtin` pauses on, `SleepRequest`,
`CheckpointRequest` and `ChannelRecvRequest`, with their subclasses
(`ChannelSendRequest`, `TaskWaitRequest`). It finds every function whose
`return` hands back a new request, the result of a function that does, or a
local bound to either, iterated to a fixed point. Then it maps builtins to the
functions that implement them. A builtin that learns to suspend fails the suite
until it is declared.

**The analysis found 20 builtins:**
- the `sleep` family, `recv`, `send` and `wait`;
- `__workflow_checkpoint` and `__action_agent`;
- the eight `http_*_async` builtins;
- `subprocess_run_async` and `subprocess_shell_async`;
- `agent_call_async`.

It flags nothing synchronous. Dropping one of them from the declared set fails
three tests. `send` and `wait` were not in the design's first list: they suspend
through `ChannelSendRequest` and `TaskWaitRequest`, subclasses of
`ChannelRecvRequest`.

**Concurrency constructors, orchestration and introspection stay out.** They are
not needed for I/O in hot paths, and each raises its own exactness questions.

## Phase 3 as built

**Closures compile**, and so do the functions that make them:
- A compiled function takes its closure's upvalue list (`up`). `LOAD_UPVALUE`
  and `STORE_UPVALUE` read and write those cells.
- A slot a closure in the body captures can hold a `Cell`, so its reads, writes,
  resets, field reads and comparisons are Cell-aware. Every other slot stays a
  plain Python local.
- `MAKE_CLOSURE` does what `capture_local` does: reuse a slot's Cell, or box the
  value in a new one and record it in the frame's locals dict too.
- Frames for closure calls come from `VM.build_closure_frame`, extracted from
  `call_closure`. The #394 step-entry guard moved with it, so the guard covers
  compiled calls as well.

**Calls through values.** A `CALL_VALUE` in compiled code goes one of two ways:
- A local closure whose function is eligible is called directly.
- Anything else goes through the VM's own `CALL_VALUE` handler, synchronously:
  module functions, proxies for another VM's closures, closures from another
  chunk, and ineligible closures. If the handler pushes a frame, its return
  address becomes one past the end of the calling chunk, which ends a nested
  `execute()`.

**Dynamic functions.** A `CALL_VALUE`'s target is only known at run time and
may be anything, including code that would suspend. So it marks its function
dynamic, and the mark spreads to every caller. A dynamic function runs compiled
only when `vm.current_coroutine is None`. That is weaker than phase 1's
condition, no task step budget, and it has to be: a coroutine resumed with
`resume(...)`, or the temporary one `run_closure` makes for a builtin's callback,
has no step budget. Outside a coroutine nothing suspends:
- `sleep`, `recv` and `yield` refuse with their own errors;
- `send` buffers.

So a synchronous call from compiled code there behaves exactly as the
interpreter would.

**A function body is what it can reach.** It is not an address range. A closure's
body is compiled inline in its parent, behind a `JUMP` over it, which caused two
problems:
- The address ranges phases 1 and 2 used cut the parent off at the closure, so
  every function that made a closure was ineligible.
- They gave the closure the rest of its parent. A block running on into that
  unreachable code counted instructions that never execute: the differential
  tests showed 124 against 106.

Bodies now come from reachability. A block ends at the next block start of any
kind, not only at reachable ones.

**Measured.** A program running `map`, `filter` and `reduce` written in Nodus,
with closures, 30 rounds over 2,000 items: 2.34–2.42 s interpreted and
1.34–1.49 s compiled, about 1.7×, with identical instruction counts. Before
phase 3 none of it compiled.

**Still interpreted:**
- `CALL_METHOD`;
- closures from another chunk (through the handler);
- anything with `try`.

Without the optimizer (`--no-opt`), functions with parameters stay interpreted:
their arguments are bound with `STORE_ARG`, and only the optimizer's fused
`ENTER` is supported.

## Imported modules (after phase 3)

**The two switches users have did not reach imported code.** Every
measurement above, and CI's `compiled` job, used `NODUS_COMPILE_FUNCTIONS`.
`NodusRuntime(compile_functions=True)` and `nodus run --compile` attach a
`CompileState` to the top-level VM only, but a call into an imported module runs
on a child VM. That child took compilation from the environment variable alone.
So with the real switches, an imported module ran entirely interpreted.

There was a second gap even with the variable set. The function a module call
enters is started by `VM.run_closure`, which jumps straight to `fn.addr` and so
skips the `CALL` hook. Only the functions it called were compiled. In the
self-hosted lexer, that is the whole `tokenize` loop.

The self-hosted parser, parsing `parser.nd`, best of three:

| Switch | Before | After |
|---|---|---|
| off | 2.28 s | 2.36 s |
| `compile_functions=True` | 2.33 s | 1.37 s |
| `NODUS_COMPILE_FUNCTIONS=1` | 1.64 s | 1.26 s |

The fix has three parts:
- **The state is host state.** `_pycompile` is in `HOST_STATE_ATTRIBUTES`, so
  `derive_child_vm` shares the parent's state with every child: module calls,
  tool handlers and resumes. It is shared, not copied, so call counts, the
  per-chunk analysis and the depth cap carry across calls.
- **Call counts are per chunk**, not per state. A shared state sees several
  modules, and two can each have a `peek`.
- **`run_closure` tries `CompileState.run_entry` first.** Its arguments must
  match the parameters exactly; on a mismatch the interpreter decides what the
  mismatch means. The temporary coroutine `run_closure` sets up keeps dynamic
  functions interpreted there, as everywhere inside a coroutine.

The tests run a program that imports a module, through the runtime flag with the
variable unset. Three of them fail on the unfixed tree.

## Call overhead (after phase 3)

**With nearly every function compiled, the cost moved to the calls between
them.** The self-hosted frontend has 74 of 75 functions eligible. Each call from
compiled code went through a helper:
- it built an argument list;
- it called `record_vm_call`;
- it ran `CompileState.allowed`;
- it built the frame with `VM.build_call_frame`, which called `current_loc`;
- it bound the parameters with a `zip`;
- it called the compiled function;
- it popped the frame and called `record_vm_return`.

**Measured by removal, not by profiler.** cProfile charges each small Python
call heavily, so it overstated every one of these. Instead, each step was taken
out of the generated code in turn, and a benchmark of 257,000 calls was timed:

| Removed | Time |
|---|---|
| nothing (helper inlined) | 0.72 s |
| the frame | 0.42 s |
| the run checks | 0.62 s |
| the event checks | 0.65 s |

**What changed:**
- **A call to an eligible user function is generated inline at its call site.**
  The steps are the helper's, in its order, and the helper remains the slow path
  for an uncompiled callee, past the depth cap or under an observer. The counters
  are kept inline, and the `record_*` methods are called only when an event is
  wanted.
- **The frame comes from `VM.call_frame_maker`.** It is made once per call site
  when the caller is compiled, and it works out what depends only on the site:
  the call's location, the return address and the callee's slot map. Per call,
  it checks `max_frames` and builds the `Frame`. A test requires it to build the
  frame `build_call_frame` builds at the same `ip`, field by field, with real
  source locations. With none, every site looks alike, which hid a mutation that
  read the wrong instruction's location. It is listed in the step-guard site map
  as a `no-closure` site.
- **A builtin that carries no authority and cannot suspend is called directly.**
  That means one not in `BUILTIN_CAPABILITIES` and not in `MAY_SUSPEND_BUILTINS`,
  with its arity correct at the call site. `plain_builtin` binds the function per
  VM when the caller compiles, so nothing VM-specific enters the shared code
  cache. The inline code does what the slow path does around the call: count it,
  emit its event if one is wanted, and turn an error record into the
  interpreter's. Capability-bearing builtins keep `invoke_builtin`, so the
  capability check still has one copy. With a profiler present, the slow path
  runs.

**Measured interleaved,** on the same source trees in one window, best of
three: this box had 0.6 GB free and sequential timings drifted by 70%.

| | `main` | after |
|---|---|---|
| call benchmark, compiled | 1.30 s | 0.75 s |
| self-hosted parser, compiled | 1.29–1.33 s | 1.00–1.12 s |
| self-hosted parser, interpreted | 2.28 s | 2.41 s (no change to that path) |
| map/filter/reduce with closures | 1.46 s | 1.42 s |

The last row barely moves because its calls go through values (`CALL_VALUE`),
which still use the helper. `Frame` with `__slots__` was measured too, and saved
only another 4%. That is not worth changing a core class.

**Still to do:** the `CALL_VALUE` fast path, for closure-heavy code. Its frame
depends on the closure, so a per-site maker does not apply directly. The #394
step-entry guard must stay on it.

## Decisions (2026-11-21)

1. **Opt-in for one release**, through `NodusRuntime(compile_functions=True)`,
   `nodus run --compile` and `NODUS_COMPILE_FUNCTIONS`. On by default after
   that, if the differential job has stayed green.
2. **The CI cost is accepted.** The `compiled` job runs the whole suite with
   `NODUS_COMPILE_FUNCTIONS=always`.
3. **The thresholds are measured, not assumed.** See "Thresholds, measured".

## Thresholds, measured (2026-11-21)

Measured on CPython 3.11 on the development machine, best of 3.

**When to compile.** Compiling costs about 1.8 ms per function; the 43 functions
the self-hosted frontend runs took 76 ms in all. A call-count threshold alone
lost most of the gain:

| Threshold | Frontend, `parser.nd` | Functions compiled |
|---|---|---|
| interpreted | 2.30 s | 0 |
| 0 (compile on the first call) | 1.24 s | 43 |
| 8, 32, 128 or 512 calls | 1.72–1.82 s | 38–39 |

The reason: `tokenize` and `parse_program` are called once per file, but hold
the program's hottest loops, and a call count never reaches them. So **a
function with a loop (a backward jump) compiles on its first call**, and any
other after 32 calls. With that rule every threshold measured 1.23–1.29 s.

Short programs pay nothing:
- `stdlib_demo` and `features_demo` compile nothing;
- `expr_compiler` compiles 12 functions and runs in the same time (0.036 s,
  against 0.038 s).

**The depth cap.** Each compiled level costs about two Python frames.
Recursing 3,000 deep from a plain `run_source`:
- caps up to 450 completed;
- 500 and above hit Python's default limit of 1,000.

The cap is 200, or a fifth of the current recursion limit if that is lower. A
host that lowers the limit then lowers the cap with it, instead of crashing.
