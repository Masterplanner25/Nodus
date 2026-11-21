# A Nodus frontend written in Nodus

`lexer.nd` and `parser.nd` are ports of `src/nodus/frontend/lexer.py` and
`src/nodus/frontend/parser.py`. They exist to answer one question for #173: what
would it cost for Nodus to compile itself?

`python -m tools.selfhost_check` runs both over every tracked `.nd` file. It
checks the results against the Python frontend, token for token and node for
node, and reports the VM instructions each phase took. Its result is exact
agreement on all of them, including the two files here and
`tests/fixtures/selfhost/constructs.nd`, which uses every construct the parser
has a branch for. `tests/test_selfhost_frontend.py` holds a sample of that in
the suite.

The parser builds each node as a list, `[NodeName, field, ...]`, with the fields
in the Python dataclass's order. Two things are not ported, and neither changes
the tree:
- the checks that run after parsing, `validate_goal_pursuits` and
  `validate_step_guards`;
- the warnings for unknown type names.

## What it costs

Measured 2026-11-20 on the development machine, CPython 3.11. The VM's own
instruction counter is reliable since the module-call bounds fix: before it,
instructions run inside an imported module were not counted at all.

| Input | Lines | Lex | Parse | Per line | Time |
|---|---|---|---|---|---|
| Every tracked `.nd` file (92) | 4,488 | 9.3M (74/char) | 6.6M (263/token) | 3,540 | 12.4 s |
| The stdlib (28 files) | 1,480 | 2.4M | 1.5M | 2,630 | 3.1 s |
| `lexer.nd` + `parser.nd` | 1,896 | 4.7M | 4.3M | 4,720 | 7.4 s |

- **Throughput is about 1.3M instructions/s**, the same rate the VM reaches on
  `examples/expr_compiler.nd`.
- **The Python frontend does the whole corpus in 0.28 s**, so the Nodus one is
  about 44× slower.
- **Under PyPy**, the stdlib plus the two files here take 4.2 s, against 10.5 s
  on CPython.

**For #173 this replaces an estimate.** A self-hosted compiler would also need
code generation and optimisation, and it would be several thousand lines. At
roughly 3,500–4,700 instructions per line for the frontend, and perhaps twice
that end to end, compiling it would take on the order of **30–50M
instructions**: about 30 s on CPython today, and around 10 s under PyPy. The
earlier estimate was 100–300M. That makes self-hosting slow but practical
without a faster VM. It also makes it a heavy dependency on the VM's speed for
anyone running it.

## Where the instructions go

- **Lexing is the larger share.** There is no substring builtin, so every token's
  text is built one character at a time, and each character costs a function
  call or two. A builtin that returned `src[a:b]` would remove most of the
  per-character work.
- **Parsing costs 230–310 instructions per token.** Most of that is `peek`,
  which is called again at each `at(...)` test of the same token, and the
  record-field reads for the parser state.

## Found by writing it

Writing about 1,900 lines of real Nodus turned up four defects, all filed:
- **#949:** a local named like a parameter makes the parameter `nil` from the
  start of the function. `tokenize(text)` with a later `let text` received `nil`.
- **#952:** a `return` inside a `for ... in` loop leaves the iterator on the
  caller's stack, shifting the caller's pending operands. `parse_assignment`
  uses an index loop because of it.
- **#950:** `nodus fmt` crashed on every `else if`.
- Instructions run inside an imported module were never counted or bounded.
  Fixed in the same series.
