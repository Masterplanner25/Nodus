# Debugger

Nodus includes a simple interactive debugger for step/next/continue debugging with line breakpoints.

## Usage

```bash
nodus debug script.nd
```

The debugger starts paused before the first instruction.

## Commands

- `step`    Execute the next instruction and pause.
- `next`    Step over calls; pause after the current line completes.
- `continue`  Run until a breakpoint is hit.
- `break <line>`  Set a line-based breakpoint.
- `stack`   Show a simplified call stack.
- `locals`  Show current locals (or globals if no frame).
- `quit`    Stop execution.

## Notes
- Breakpoints are line-based and use source line numbers.
- The debugger operates on bytecode locations, so pauses can occur within a line with multiple expressions.
- The debugger is intentionally minimal and intended for small scripts and orchestration flows.
