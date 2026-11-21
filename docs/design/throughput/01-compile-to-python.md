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
| 2 | Builtins outside the compilable categories, through the may-suspend analysis described under Eligibility | programs that call `http`, `subprocess` or agents in their hot paths compile |
| 3 | Cells and closures, `CALL_VALUE` with a known compiled target | closure-heavy programs compile |
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
   (`__workflow_checkpoint`, `workflow_wait`, `retry_call`) are excluded. So are
   all capability-bearing builtins, which makes #405's check unreachable from
   compiled code in phase 1. It still goes through the shared `invoke_builtin`
   anyway. The may-suspend analysis moves to phase 2.
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

## Decisions (2026-11-21)

1. **Opt-in for one release**, through `NodusRuntime(compile_functions=True)`,
   `nodus run --compile` and `NODUS_COMPILE_FUNCTIONS`. On by default after
   that, if the differential job has stayed green.
2. **The CI cost is accepted.** The `compiled` job runs the whole suite with
   `NODUS_COMPILE_FUNCTIONS=always`.
3. **The thresholds are measured, not assumed.** See "Thresholds, measured".
