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

# Simple single-character escape sequences.
# \x and \u are handled separately in decode_string_literal because they
# consume additional hex-digit characters from the source text.
ESCAPE_MAP = {
    "n": "\n",
    "t": "\t",
    "r": "\r",
    "0": "\0",
    '"': '"',
    "\\": "\\",
}


def decode_string_literal(
    token_text: str,
    *,
    line: int | None = None,
    col: int | None = None,
) -> str:
    """Decode a quoted string token into its runtime string value.

    Raises LangSyntaxError (with source location when provided) for any
    malformed escape sequence so that callers do not need a try/except.

    Supported escape sequences:
        \\\\  backslash
        \\"   double quote
        \\n   newline (U+000A)
        \\t   horizontal tab (U+0009)
        \\r   carriage return (U+000D)
        \\0   null byte (U+0000)
        \\xHH two-digit hex byte  (e.g. \\x41 -> 'A')
        \\uXXXX four-digit Unicode code point (e.g. \\u03B1 -> 'α')
    """
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
            raise LangSyntaxError(
                "Unterminated escape sequence in string literal",
                line=line,
                col=col,
            )

        esc = s[i]

        # \xHH — two-digit hex byte
        if esc == "x":
            hex_digits = s[i + 1 : i + 3]
            if len(hex_digits) < 2:
                raise LangSyntaxError(
                    r"Incomplete \x escape: expected 2 hex digits",
                    line=line,
                    col=col,
                )
            try:
                out.append(chr(int(hex_digits, 16)))
            except ValueError:
                raise LangSyntaxError(
                    rf"Invalid \x escape: \x{hex_digits}",
                    line=line,
                    col=col,
                )
            i += 3
            continue

        # \uXXXX — four-digit Unicode code point
        if esc == "u":
            hex_digits = s[i + 1 : i + 5]
            if len(hex_digits) < 4:
                raise LangSyntaxError(
                    r"Incomplete \u escape: expected 4 hex digits",
                    line=line,
                    col=col,
                )
            try:
                out.append(chr(int(hex_digits, 16)))
            except ValueError:
                raise LangSyntaxError(
                    rf"Invalid \u escape: \u{hex_digits}",
                    line=line,
                    col=col,
                )
            i += 5
            continue

        if esc not in ESCAPE_MAP:
            raise LangSyntaxError(
                f"Unsupported escape sequence: \\{esc}",
                line=line,
                col=col,
            )

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
            # decode_string_literal raises LangSyntaxError directly; no try/except needed.
            val = decode_string_literal(text, line=start_line, col=start_col)
            out.append(Tok("STR", val, start_line, start_col))
            # A string token may span multiple lines if it contains a literal
            # newline character (matched by [^"\\] in the regex).  Update line
            # and col correctly so subsequent tokens have accurate positions.
            newlines_in_str = text.count("\n")
            if newlines_in_str > 0:
                line += newlines_in_str
                col = len(text) - text.rfind("\n")
            else:
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
