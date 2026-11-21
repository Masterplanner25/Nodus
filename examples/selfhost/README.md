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

Measured 2026-11-21 on the development machine, CPython 3.11, after the parser
restructure described below and the VM work in #965-#967 and #970. The VM's own
instruction counter is reliable since the module-call bounds fix: before it,
instructions run inside an imported module were not counted at all.

| Input | Lines | Lex | Parse | Per line | Time |
|---|---|---|---|---|---|
| Every tracked `.nd` file (95) | 6,401 | 6.9M (36.9/char) | 4.0M (102/token) | 1,710 | 9.7 s |
| The stdlib (28 files) | 1,470 | 1.1M | 0.6M | 1,210 | 1.5 s |
| `lexer.nd` + `parser.nd` | 1,839 | 2.4M | 1.4M | 2,060 | 3.2 s |

Lines are `wc -l`. An earlier version of this table gave the corpus as 4,488
lines, and so 3,540 instructions per line. The tree held 95 files totalling
about 6,400 lines then too, so that figure was about 40% too high. The other two
rows were right.

Before the VM work the corpus row was 8.8M + 5.4M instructions in 11.8 s. Of
the difference:
- **fewer instructions** came from the optimizer, which runs again since #966:
  - assignment statements no longer read back what they stored;
  - uncaptured slots are no longer reset (#967);
  - three common sequences are fused into one instruction each (#970, the
    provisional opcodes proposed in #969): 8.2M + 5.0M became 6.9M + 4.0M;
- **cheaper instructions** came from the opcode handlers (#965).

A fused instruction does the work of several, so its time falls by less than its
instruction count. Over this corpus the fused instructions cut instructions by
16-20%. Time fell 8-9% when the frontend parsed `parser.nd` on `main` and on
#970 alternately in one window; single runs on this machine swing about 10%,
so the table's times are not a measurement of that difference.

- **Throughput is about 1.1M instructions/s.** The count is lower than before
  the fused instructions, because each now does more.
- **The Python frontend does the whole corpus in about 0.41 s** (best of 3 on
  2026-11-21), so the Nodus one is about 24× slower. This README used to say
  0.28 s and 40×; that time did not reproduce.
- **Under PyPy** this check is about **2.1–2.3× faster** than on CPython. CI
  runs it in both the `pypy` and the `test` job (#973). On 2026-11-21 the whole
  corpus took 1.84 s and 3.22 s under PyPy, against 4.31 s and 6.81 s on CPython,
  in two runs. The jobs run on different runners, so the ratio is approximate.
  PyPy's usual ~16× (`docs/language/LANGUAGE_VISION.md`) is for one long run.
  This check is 190 short ones, averaging about 57k instructions each, and most
  end before the JIT pays off. Application Control on the development machine
  blocks the local PyPy interpreter, so CI is where this is measured.

**For #173 this replaces an estimate.** A self-hosted compiler would also need
code generation and optimisation, and it would be several thousand lines. At
roughly 1,200-2,100 instructions per line for the frontend, and perhaps twice
that end to end, compiling it would take on the order of **12-21M
instructions**: about 11-19 s on CPython today.
- The first estimate was 100-300M instructions.
- The first measurement said 30-50M, with the line-count error above.
- After the parser restructure it was 15-30M.
- After the VM work in #965-#967 it was 15-25M.

Self-hosting is slow but practical without a faster VM. It also makes it a heavy
dependency on the VM's speed for anyone running it.

## Where the instructions go

- **Lexing is the larger share, and the cost is the scan, not the text.** This
  section first said that a builtin returning `src[a:b]` would remove most of
  the per-character work. That was a prediction, and it was wrong.
  `substring` now exists, and the lexer uses it to cut each token out in one
  call. Lexing went from 76.6 to 73.1 instructions per character, about 5%.
  The rest was the scanning loop: every character went through one or two
  function calls (`char_at`, `is_digit`, `is_ident_char`) and several
  comparisons. `str_span` and `str_span_until` now find where a run ends in
  one call. With them, each identifier, number, comment, whitespace run and
  plain stretch of a string literal costs two builtin calls, whatever its
  length. Lexing went from 73.1 to **47.4** instructions per character, 35%
  fewer, and 10.8 s to 7.6 s over the corpus. What remains is per token, not
  per character: the dispatch in `scan_token`, the keyword lookup and building
  each token record.
- **Parsing went from 267 to 136 instructions per token, 49% fewer**, and from
  9.3 s to 4.4 s over the corpus. The cost was the parser's design, not the VM.
  A profile of parsing `parser.nd` showed `peek` and `at` taking 55% of it:
  78,000 peeks for about 10,000 tokens. Each one stepped over comments by
  reading the parser record, and each level of the expression ladder called
  `at` once per operator it knew. Three changes:
  - **Comments come out of the token list once**, in `new_parser`. Each is kept
    against the token it precedes and handled when the cursor reaches that
    token. That is when the Python parser's `peek` would have stepped over it,
    so the same `last_tok` decides where it belongs, and the trees still agree.
    The current token is then a field, `p.tok`.
  - **Each expression level reads the token kind once** and compares the local.
  - **The five binary levels are one precedence loop**, `parse_binary`. That is
    five calls fewer for every operand.

  What remains is spread out. The largest single piece is `eat`, at about 42
  instructions per call, most of them field reads and writes on the parser
  record. Lexing is the larger phase again.

## Found by writing it

Writing about 1,900 lines of real Nodus turned up four defects, all filed:
- **#949:** a local named like a parameter makes the parameter `nil` from the
  start of the function. `tokenize(text)` with a later `let text` received `nil`.
  Now fixed, and `tokenize` is back to taking `text`.
- **#952:** a `return` inside a `for ... in` loop leaves the iterator on the
  caller's stack, shifting the caller's pending operands. Now fixed.
  `tests/test_return_stack_depth.py` holds it. The self-host check used to
  cover it too, through a `return` inside a `for` loop in `parse_assignment`;
  the restructure removed that loop.
- **#950:** `nodus fmt` crashed on every `else if`.
- Instructions run inside an imported module were never counted or bounded.
  Fixed in the same series.
