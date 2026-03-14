"""Tokenization and keyword handling for Nodus."""

import re
from dataclasses import dataclass

from nodus.runtime.diagnostics import LangSyntaxError


@dataclass
class Tok:
    kind: str
    val: str
    line: int
    col: int


TOKEN_RE = re.compile(
    r"""
    (?P<WS>[ \t]+)
  | (?P<COMMENT1>\#.*)
  | (?P<COMMENT2>//.*)
  | (?P<NL>\n+)
  | (?P<STR>"(?:\\.|[^"\\])*")
  | (?P<NUM>\d+(\.\d+)?)
  | (?P<ID>[A-Za-z_][A-Za-z0-9_]*)
  | (?P<OP>&&|\|\||==|!=|<=|>=|->|[+\-*/=(){}\[\],;:.<>!])
    """,
    re.VERBOSE,
)

KEYWORDS = {
    "let",
    "print",
    "if",
    "else",
    "while",
    "for",
    "true",
    "false",
    "fn",
    "return",
    "nil",
    "import",
    "as",
    "export",
    "from",
    "try",
    "catch",
    "throw",
    "record",
    "in",
    "yield",
    "workflow",
    "goal",
    "step",
    "after",
    "with",
    "action",
}

ESCAPE_MAP = {
    "n": "\n",
    "t": "\t",
    '"': '"',
    "\\": "\\",
}


def decode_string_literal(token_text: str) -> str:
    s = token_text[1:-1]
    out = []
    i = 0

    while i < len(s):
        ch = s[i]
        if ch != "\\":
            out.append(ch)
            i += 1
            continue

        i += 1
        if i >= len(s):
            raise SyntaxError("Unterminated escape sequence in string literal")

        esc = s[i]
        if esc not in ESCAPE_MAP:
            raise SyntaxError(f"Unsupported escape sequence: \\{esc}")

        out.append(ESCAPE_MAP[esc])
        i += 1

    return "".join(out)


def tokenize(src: str) -> list[Tok]:
    if src.startswith("\ufeff"):
        src = src[1:]
    src = src.replace("\r\n", "\n").replace("\r", "\n")

    pos = 0
    line = 1
    col = 1
    out: list[Tok] = []

    while pos < len(src):
        start_line = line
        start_col = col
        m = TOKEN_RE.match(src, pos)
        if not m:
            raise LangSyntaxError(f"Unexpected character {src[pos]!r}", line=start_line, col=start_col)

        kind = m.lastgroup
        text = m.group(kind)
        pos = m.end()

        if kind in {"WS"}:
            col += len(text)
            continue
        if kind in {"COMMENT1", "COMMENT2"}:
            out.append(Tok("COMMENT", text, start_line, start_col))
            col += len(text)
            continue
        if kind == "NL":
            out.append(Tok("SEP", "\n", start_line, start_col))
            line += len(text)
            col = 1
            continue
        if kind == "NUM":
            out.append(Tok("NUM", text, start_line, start_col))
            col += len(text)
            continue
        if kind == "STR":
            try:
                val = decode_string_literal(text)
            except SyntaxError as err:
                raise LangSyntaxError(str(err), line=start_line, col=start_col)
            out.append(Tok("STR", val, start_line, start_col))
            col += len(text)
            continue
        if kind == "ID":
            if text in KEYWORDS:
                out.append(Tok(text.upper(), text, start_line, start_col))
            else:
                out.append(Tok("ID", text, start_line, start_col))
            col += len(text)
            continue
        if kind == "OP":
            if text == ";":
                out.append(Tok("SEP", text, start_line, start_col))
            else:
                out.append(Tok(text, text, start_line, start_col))
            col += len(text)

    out.append(Tok("EOF", "", line, col))
    return out
